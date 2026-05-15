"""Pass 4 (Lean): synthesis memo writer.

Reads Pass 1 XML + Pass 2 intake JSON, writes a focused analyst memo
with inline citations. Default model: Sonnet 4.6. /deep mode escalates
to Opus 4.6 with critic + verification.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional

from llm import call_llm_json


SYNTH_SYSTEM_PROMPT = """You are a senior forensic analyst at a Philippine property and legal practice.
You read documents that have already been entity-extracted and classified. Your job: produce
a TIGHT, citation-grounded analyst memo that surfaces what the human owner needs to know.

Hard rules:
- Every factual claim MUST have an inline citation in the form [page N] or [page N, sig block]
  pointing to where in the source XML the claim is grounded.
- If you cannot cite the source for a claim, do not make the claim.
- Do NOT speculate, do NOT extrapolate, do NOT cite Philippine law you weren't given.
- Be useful. Surface the 2-3 things the owner ACTUALLY needs to know, not a wall of text.
"""


SYNTH_USER_PROMPT_TEMPLATE = """Document XML (Pass 1 output):
{xml}

Intake analysis (Pass 2 output):
{intake_json}

Write the analyst memo as a JSON object:

{{
  "headline": "<one sentence: what is this doc, in one breath>",
  "case_file": "<from intake>",
  "executive_summary": "<2-3 sentences capturing the substance, with citations>",
  "key_facts": [
    "<fact with inline [page N] citation>",
    "..."
  ],
  "what_changed": [
    "<things this doc reveals/changes vs prior context — empty list if doc is routine>"
  ],
  "questions_raised": [
    "<specific questions raised by this doc that would benefit from a human answer>"
  ],
  "referenced_but_missing": [
    "<documents/annexes cited in the text but not present in the file>"
  ],
  "procedural_dates": [
    {{"date": "YYYY-MM-DD", "event": "...", "implication": "..."}}
  ],
  "strategic_implication": "<1-2 sentences on what this means for the case posture, with citations>",
  "owner_action_required": "<short: 'none' | 'reply by [date]' | 'review and decide' | 'forward to counsel'>",
  "memo_confidence": 0.0-1.0
}}

Rules:
- If novelty_score < 0.3 in the intake: keep the memo minimal (headline + executive_summary + owner_action_required only). Most fields can be empty arrays/strings.
- If novelty_score >= 0.7: be thorough across all sections.
- Every entry in key_facts and strategic_implication MUST cite [page N].
- procedural_dates: include only dates with actual case-process implication (deadlines, hearing dates, statutory windows). Skip incidental dates like "office hours."
- owner_action_required: keep terse. The owner should know in 2 seconds what they need to do.
"""


def pass4_synthesis(
    xml: str,
    intake: Dict[str, Any],
    *,
    deep_mode: bool = False,
) -> Dict[str, Any]:
    """Generate the analyst memo. deep_mode escalates to Opus."""
    prompt = SYNTH_USER_PROMPT_TEMPLATE.format(
        xml=xml[:50000],
        intake_json=_compact_intake(intake),
    )
    return call_llm_json(
        prompt,
        weight="heavy" if deep_mode else "medium",   # Opus if deep, else Sonnet
        system=SYNTH_SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.0,
        timeout_s=240.0,
    )


def _compact_intake(intake: Dict[str, Any]) -> str:
    """Strip heavy entity payload to what synthesis actually needs."""
    import json as _json
    compact = {
        "classification": intake.get("classification", {}),
        "document_meta": intake.get("document_meta", {}),
        "execution_status": {k: v for k, v in (intake.get("execution_status") or {}).items()
                             if k in ("completion_state", "is_signed", "is_notarized",
                                      "is_filed_or_recorded", "is_marked_draft", "execution_date")},
        "entities_summary": {
            "people": [(p.get("name"), p.get("role")) for p in (intake.get("entities") or {}).get("people", [])][:15],
            "organizations": [(o.get("name"), o.get("type")) for o in (intake.get("entities") or {}).get("organizations", [])][:10],
            "reference_numbers": [(r.get("number"), r.get("type")) for r in (intake.get("entities") or {}).get("reference_numbers", [])][:10],
            "key_dates": [(d.get("date"), d.get("context")) for d in (intake.get("entities") or {}).get("dates", [])][:10],
            "referenced_but_missing": [r.get("reference") for r in (intake.get("entities") or {}).get("document_references", [])
                                       if not r.get("is_attached")],
        },
        "novelty_score": intake.get("novelty_score"),
        "tags": intake.get("tags", []),
    }
    return _json.dumps(compact, indent=2)
