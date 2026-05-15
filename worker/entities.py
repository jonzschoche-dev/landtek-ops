"""Pass 2: entity extraction. Reads Pass 1 XML, returns rich entities.

Single LLM call with ONE focus: extract entities. No classification, no
synthesis. The pure extraction prompt yields 2-3x more entities than asking
for entities + classification + summary in the same call.
"""
from __future__ import annotations
from typing import Dict, Any

from llm import call_llm_json


PASS2_SYSTEM_PROMPT = """You are a forensic entity-extraction specialist for Philippine legal/property documents.
Your job is ONE thing: extract every entity in the document with rich context. Do not classify the document.
Do not summarize. Do not synthesize. Just enumerate entities thoroughly and accurately.

Be exhaustive. Subtle entities matter:
- A counterparty's organization mentioned only in passing
- A reference number cited in a parenthetical
- A document referenced as "see attached" but not directly named
- A signatory's title that disambiguates from a similarly-named person
- A date implied by "30 days from receipt" rather than stated explicitly
- A jurisdiction implied by which court/agency is named

When the source XML tags content as <signature_block>, treat names there as signatories with high confidence on their role.
When content is in a <table>, dates and money in those cells often anchor key facts.
When a page is <unreadable/>, do NOT extract entities from that page — do not invent.
"""


PASS2_USER_PROMPT_TEMPLATE = """Document XML (output of Pass 1 OCR + normalization):

{xml}

Extract ALL entities. Return JSON with exactly this schema:

{{
  "people": [
    {{
      "name": "<full name as it appears>",
      "title": "<Atty., Mayor, Engr., etc., or null>",
      "role": "<attorney | client | counterparty | signatory | witness | judge | official | other>",
      "organization": "<organization they're associated with, or null>",
      "appears_in_signature_block": true/false,
      "first_mentioned_page": <int>,
      "evidence_quote": "<short quote from the doc that supports this entry, <100 chars>"
    }}
  ],
  "organizations": [
    {{
      "name": "<organization name>",
      "type": "<lgu | court | agency | corporation | law_firm | counterparty | other>",
      "jurisdiction": "<city/province/national, or null>",
      "first_mentioned_page": <int>,
      "evidence_quote": "<short quote, <100 chars>"
    }}
  ],
  "places": [
    {{
      "name": "<place name>",
      "type": "<address | jurisdiction | property_location | landmark | other>",
      "first_mentioned_page": <int>
    }}
  ],
  "dates": [
    {{
      "date": "YYYY-MM-DD or null if relative",
      "raw": "<as it appears, e.g. 'April 23, 2026' or '30 days from receipt'>",
      "context": "<filing | deadline | hearing | meeting | effective | signed | dated | other>",
      "associated_event": "<short description of what this date refers to>",
      "first_mentioned_page": <int>
    }}
  ],
  "amounts": [
    {{
      "value": "<as it appears>",
      "currency": "<PHP | USD | other | null>",
      "context": "<short description of what this amount refers to>",
      "first_mentioned_page": <int>
    }}
  ],
  "reference_numbers": [
    {{
      "number": "<as it appears>",
      "type": "<docket | CTN | CART | case | mpsa | tax_dec | tct | tcp | reference | other>",
      "context": "<short description of what this number is for>",
      "first_mentioned_page": <int>
    }}
  ],
  "document_references": [
    {{
      "reference": "<e.g. 'Annex A', 'Exhibit 1', 'prior submission dated March 12'>",
      "is_attached": true/false,
      "what_it_is": "<short description>",
      "first_mentioned_page": <int>
    }}
  ],
  "extraction_notes": [
    "<any observations about ambiguities, possible aliases, missing info, etc.>"
  ]
}}

Rules:
- Use null for any field you genuinely don't know (do NOT guess).
- Every person/org entry MUST have first_mentioned_page set to a real page number.
- Do not invent entities for unreadable pages.
- If the same name appears in multiple roles (e.g. signatory AND attorney), create one entry with the most specific role and note the multi-role in extraction_notes.
- Reference numbers: capture every distinct one, even if cited only once.
- Document references: include anything cited as 'see attached', 'Annex A', 'as discussed in our letter dated...', etc.
"""


def pass2_extract_entities(xml: str) -> Dict[str, Any]:
    """Run Pass 2 entity extraction on Pass 1 XML output."""
    prompt = PASS2_USER_PROMPT_TEMPLATE.format(xml=xml[:60000])  # cap input
    return call_llm_json(
        prompt,
        weight="medium",                # Sonnet 4.6
        system=PASS2_SYSTEM_PROMPT,
        max_tokens=6000,
        temperature=0.0,
        timeout_s=180.0,
    )
