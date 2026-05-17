#!/usr/bin/env python3
"""satisfaction_evaluator — Haiku-driven check of whether an answer fully
addresses the atomic question that was asked.

Per [[feedback_atomic_inquiry_with_followups]]: after Jonathan answers an
atomic intake-item, we ask Haiku: was the response complete? If not, what's
the minimal follow-up?

Cost: ~$0.001 per evaluation. Cost-logged via llm_billing.

Usage from tg_dispatcher: called whenever an answered row has
intake_response_id NOT NULL.

Returns: {"satisfied": bool, "follow_up": str|null, "reason": str}
"""
import json
import re
import sys

sys.path.insert(0, "/root/landtek")
from landtek_core import get
from llm_billing import anthropic_call

SYSTEM = """You evaluate whether a human's answer fully addresses the atomic
factual question that was asked in a legal-ops intake. Be strict — partial
answers fail. The goal is forensic-grade completeness.

A satisfied answer:
  • provides the SPECIFIC factual element requested (date, name, amount,
    document reference, yes/no with justification)
  • doesn't punt to "later" or "I'll check"
  • doesn't substitute related but different info

A NOT satisfied answer might:
  • be vague ("yes" without supporting detail when detail was requested)
  • redirect ("I'll look into it")
  • give the wrong type of info ("the date" when asked "who")
  • be incomplete (1 of 3 sub-elements provided)

If NOT satisfied, propose ONE minimal follow-up question that targets the
missing element. Don't ask multiple follow-ups; pick the most important.

OUTPUT JSON ONLY (no prose, no fences):
{"satisfied": bool, "follow_up": str | null, "reason": str (<200 chars)}"""


def evaluate(client, question: str, answer: str, intake_context: str | None = None):
    user = f"QUESTION (atomic intake-item): {question}\n\nANSWER from Jonathan: {answer}"
    if intake_context:
        user += f"\n\nINTAKE CONTEXT: {intake_context}"

    msg = anthropic_call(
        client,
        called_from="satisfaction_evaluator",
        purpose="answer_completeness",
        case_file=None,
        model="claude-haiku-4-5-20251001",
        max_tokens=250,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    out = msg.content[0].text.strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return {"satisfied": False, "follow_up": None,
                "reason": f"evaluator_no_json: {out[:120]}"}
    try:
        r = json.loads(m.group(0))
        # Defensive defaults
        return {
            "satisfied": bool(r.get("satisfied", False)),
            "follow_up": (r.get("follow_up") or None),
            "reason": str(r.get("reason", ""))[:300],
        }
    except Exception as e:
        return {"satisfied": False, "follow_up": None,
                "reason": f"evaluator_parse_error: {str(e)[:120]}"}


if __name__ == "__main__":
    # Self-test
    import anthropic
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    test_cases = [
        ("What is the recipient's complete service address for the demand letter?",
         "Registry of Deeds Camarines Norte, J.P. Burgos St., Daet, Camarines Norte 4600"),
        ("Was the demand letter reviewed by counsel?",
         "yes"),
        ("What is the recipient's complete service address?",
         "I'll get it later."),
    ]
    for q, a in test_cases:
        print(f"\nQ: {q}\nA: {a}")
        r = evaluate(client, q, a)
        print(f"  → {r}")
