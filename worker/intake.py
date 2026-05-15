"""Pass 2 (Lean): combined entity extraction + classification + execution-marker detection.

ONE Sonnet call replaces what was previously 3 passes (extraction, classification,
self-consistency). Output is a structured dict that downstream passes consume:
- entities (people/orgs/places/dates/amounts/refs/document_references)
- classification (case_file, confidence, reasoning)
- execution_status (signed/notarized/filed/draft - drives version-chain detection)
- smart_filename
- novelty_score (rough — drives whether deep-dive is worth it)

Cost target: ~$0.05/doc avg on Sonnet 4.6.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional

from llm import call_llm_json


INTAKE_SYSTEM_PROMPT = """You are a forensic intake analyst for a Philippine legal/property practice.
For each document you process, you do FOUR things in a single pass:
1. Extract every entity with rich context (people, orgs, places, dates, amounts, ref numbers, document references)
2. Classify the document against the provided active cases
3. Detect execution status (draft, signed, notarized, filed, recorded) for version-chain awareness
4. Score novelty (how much new information is in this doc relative to prior context)

Be exhaustive on entities. Subtle ones matter:
- A counterparty's organization mentioned only in passing
- A reference number cited in a parenthetical
- A document referenced as 'see attached' but not directly named
- A signatory whose title disambiguates from a similarly-named person
- A date implied by '30 days from receipt' rather than stated explicitly

Be precise on execution status. Philippine legal markers:
- Notarial acknowledgment: 'SUBSCRIBED AND SWORN to before me this ___ day of ___'
- Notary block lists: notary name, commission number, Doc No., Page No., Book No., Series of
- Filing/recording marks: court receipt stamp, Registry of Deeds annotation, TCT/OCT numbers
- Draft markers: 'DRAFT', 'FOR SIGNATURE', 'WORKING DRAFT' in headers/footers
- A document is fully_executed only if signatures + dates are filled AND notarial block is present where applicable

Be conservative on classification confidence:
- 0.9+: parties/case-numbers explicitly tie to one case
- 0.6-0.9: case is plausibly indicated but not conclusive
- <0.6: insufficient cues — use 'Unknown' as case_file but note candidates in reasoning
"""


INTAKE_USER_PROMPT_TEMPLATE = """Active cases known to the system:
{case_block}

Document XML (from Pass 1 OCR + normalization):
{xml}

Return a single JSON object with this exact schema:

{{
  "classification": {{
    "case_file": "<existing case_file from list above, proposed new label like 'Surname-001', or 'Unknown'>",
    "is_new_case": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "specific cue-based reasoning citing entities or text that drove the choice",
    "candidate_cases": ["<other plausible case_files in priority order>"]
  }},
  "document_meta": {{
    "document_type": "Letter | Contract | Court Filing | Government Submission | Permit | Title | Receipt | Email | Memo | Other",
    "document_date": "YYYY-MM-DD or null",
    "smart_filename": "YYYY-MM-DD_descriptive_name.pdf",
    "summary": "2-3 sentence factual summary"
  }},
  "execution_status": {{
    "completion_state": "draft | partially_executed | fully_executed | filed | recorded",
    "is_signed": true/false,
    "signature_blocks": [{{"name": "...", "date": "YYYY-MM-DD or null"}}],
    "is_notarized": true/false,
    "notary": {{
      "name": null,
      "commission_number": null,
      "doc_no": null, "page_no": null, "book_no": null, "series_of": null,
      "place_of_execution": null,
      "acknowledgment_quote": null
    }},
    "is_filed_or_recorded": true/false,
    "registration_marks": [],
    "is_marked_draft": true/false,
    "draft_label_text": null,
    "execution_date": "YYYY-MM-DD or null"
  }},
  "entities": {{
    "people": [
      {{"name": "...", "title": null, "role": "attorney|client|counterparty|signatory|witness|judge|official|other",
        "organization": null, "appears_in_signature_block": true/false,
        "first_mentioned_page": <int>, "evidence_quote": "<short quote, <100 chars>"}}
    ],
    "organizations": [
      {{"name": "...", "type": "lgu|court|agency|corporation|law_firm|counterparty|other",
        "jurisdiction": null, "first_mentioned_page": <int>, "evidence_quote": "<short quote>"}}
    ],
    "places": [{{"name": "...", "type": "address|jurisdiction|property_location|landmark|other", "first_mentioned_page": <int>}}],
    "dates": [{{"date": "YYYY-MM-DD or null", "raw": "<as appears>", "context": "filing|deadline|hearing|meeting|effective|signed|dated|other",
                "associated_event": "...", "first_mentioned_page": <int>}}],
    "amounts": [{{"value": "...", "currency": "PHP|USD|other|null", "context": "...", "first_mentioned_page": <int>}}],
    "reference_numbers": [{{"number": "...", "type": "docket|CTN|CART|case|mpsa|tax_dec|tct|tcp|reference|other",
                            "context": "...", "first_mentioned_page": <int>}}],
    "document_references": [
      {{"reference": "<e.g. 'Annex A', 'prior submission dated March 12'>",
        "is_attached": true/false, "what_it_is": "...", "first_mentioned_page": <int>}}
    ]
  }},
  "novelty_score": 0.0-1.0,
  "novelty_reasoning": "1 sentence on why this score (relative to typical inbox docs)",
  "tags": ["short topical tags"],
  "extraction_notes": ["any ambiguities, possible aliases, missing info"]
}}

Rules:
- Use null for any field you genuinely don't know — do NOT guess.
- Every person/org entry MUST have first_mentioned_page set.
- Do not invent entities for pages tagged <unreadable/>.
- For document_references: include EVERY 'see attached', 'Annex A', 'prior letter dated...', etc.
  Set is_attached=false for items cited but not present in this PDF.
- For execution_status.notary: leave all fields null if no notarial block is present.
- novelty_score: 0.1-0.3 for routine acks/confirmations, 0.4-0.6 for substantive correspondence,
  0.7-0.9 for new evidence/decisions/filings, 1.0 for case-altering material.
"""


def _format_cases(cases: List[Dict[str, Any]]) -> str:
    if not cases:
        return "(no existing cases — propose a new case_file label or use 'Unknown')"
    lines = []
    for c in cases:
        cf = c.get("case_file", "")
        client = c.get("client_name", "?") or "?"
        goals = (c.get("current_goals") or "")[:200]
        summary = (c.get("intelligence_summary") or "")[:300]
        lines.append(f"- {cf}: client={client}. goals={goals} | summary={summary}")
    return "\n".join(lines)


def pass2_intake(xml: str, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lean intake: one Sonnet call producing entities + classification + execution status."""
    prompt = INTAKE_USER_PROMPT_TEMPLATE.format(
        case_block=_format_cases(cases),
        xml=xml[:60000],
    )
    return call_llm_json(
        prompt,
        weight="medium",        # Sonnet 4.6
        system=INTAKE_SYSTEM_PROMPT,
        max_tokens=8000,
        temperature=0.0,
        timeout_s=240.0,
    )
