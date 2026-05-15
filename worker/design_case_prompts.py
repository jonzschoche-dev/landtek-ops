"""Ask Gemini Pro to draft case-specific analysis prompts for the two immediate clients.

Idea: rather than us writing a generic 'summarize this case' prompt, we let Gemini Pro
(senior reasoning model) study the case characteristics, the Philippine legal context
for each, and design the optimal prompt structure to send to Gemini Flash during the
actual bootstrap.

Output: /root/landtek/case_analysis_prompts.json — bootstrap_case_intel.py reads this
and uses the case-specific prompt for each case instead of a one-size-fits-all template.
"""
from __future__ import annotations
import os, sys, json, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config import GEMINI_API_KEY

GEMINI_MODEL = os.getenv("GEMINI_DESIGN_MODEL", "gemini-1.5-flash")
OUTPUT_FILE = Path("/root/landtek/case_analysis_prompts.json")


META_PROMPT = """You are a senior legal-tech consultant in the Philippines designing AI prompts
for a property + legal case management system. The system has two active matters whose Google
Drive folders need to be analyzed by a downstream Gemini Flash call.

Your job: design a TAILORED analysis prompt for each case. The prompts must be calibrated to
Philippine legal context — Mining Act of 1995 (RA 7942), DENR Administrative Orders, Civil Code
(RA 386), Code of Conduct (RA 6713), Ease of Doing Business Act (RA 11032), Local Government
Code (RA 7160), CARP/RA 6657 if relevant, Rules of Court, etc. Do not assume US/foreign law.

THE TWO CASES:

1. **Paracale-001** — Allan Inocalla, gold mining concession matter
   Location: Paracale, Camarines Norte (a known small-scale gold mining municipality)
   Likely substance: MPSA application or dispute (Mineral Production Sharing Agreement),
   DENR/MGB processing, possibly small-scale vs large-scale mining tensions, environmental
   compliance certificate (ECC) issues, possibly LGU revenue-sharing or zoning, possibly
   conflicts with surface owners or agrarian beneficiaries (DAR).
   Documents likely include: MPSA application packet, DENR correspondence, MGB orders,
   ECC, geological/feasibility studies, financial statements, LGU permits.

2. **MWK-001** — Mary Worrick Keesey estate matter
   Location: Mercedes, Camarines Norte
   Likely substance: estate / heirship administration. Patricia Keesey Zschoche is the
   client / attorney-in-fact (Jonathan Paul Zschoche acts on her behalf). LGU of Mercedes
   under Mayor Alexander Pajarillo has been allegedly obstructing release of certified
   records for over a year. Active ARTA filings (CTN SL-2026-0423-1891), CART proceedings
   (Resolutions 1-6 Series 2026 issued April 6, 2026), procedural complaint pending
   supervisory review, referral to CSC under RA 6713 + RA 11032.
   Documents likely include: TCT/OCT titles, deed of extrajudicial settlement, special
   power of attorney, BIR estate tax filings, ARTA submissions, CART hearing transcripts,
   demand letters to LGU, DILG referrals.

FOR EACH CASE, return a JSON object with this schema:

{{
  "case_file": "Paracale-001 or MWK-001",
  "context_priming": "<3-5 sentences orienting the downstream analyst to THIS specific case — what's the posture, what's typical, what's unusual>",
  "key_questions_to_answer": [
    "<5-10 specific questions the analyst should answer from the Drive contents and conversation history>"
  ],
  "watch_for": [
    "<patterns, red flags, document types, dates, or party behaviors that warrant special attention for THIS case>"
  ],
  "philippine_legal_context": "<2-3 sentences naming the most relevant statutes, agencies, and procedural rules>",
  "domain_specific_fields": [
    {{"field_name": "...", "description": "<what to extract>", "example": "..."}}
  ],
  "evidence_priorities": [
    "<which document categories matter most for this case posture>"
  ],
  "draft_analysis_prompt": "<the actual prompt text the bootstrap will send to Gemini Flash to produce the case intelligence summary. Include placeholders {context_block} for the Drive+conversation+document data and {case_file} for the case label. The prompt must request structured JSON output with at minimum: client_name, key_parties, key_locations, key_agencies, key_reference_numbers, current_goals, key_risks, open_gaps, next_milestone, intelligence_summary (3-5 paragraphs), plus the domain_specific_fields you defined.>"
}}

Return: {{"prompts": [<Paracale-001 object>, <MWK-001 object>]}}

Be specific to these clients, not generic. Surface what an experienced Philippine paralegal
would notice immediately."""


def design_prompts():
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}")
    body = {
        "contents": [{"parts": [{"text": META_PROMPT}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8000,
            "responseMimeType": "application/json",
        },
    }
    r = requests.post(url, json=body, timeout=240)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:500]}")
    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def main():
    print(f"Asking {GEMINI_MODEL} to design case-specific analysis prompts...")
    result = design_prompts()
    print("\n" + "="*72)
    print("DESIGNED PROMPTS")
    print("="*72)
    for p in result.get("prompts", []):
        print(f"\n--- {p.get('case_file')} ---")
        print(f"Context priming:\n  {p.get('context_priming')}")
        print(f"\nKey questions to answer:")
        for q in p.get("key_questions_to_answer", []):
            print(f"  - {q}")
        print(f"\nWatch for:")
        for w in p.get("watch_for", []):
            print(f"  - {w}")
        print(f"\nPhilippine legal context:\n  {p.get('philippine_legal_context')}")
        print(f"\nDomain-specific fields:")
        for f in p.get("domain_specific_fields", []):
            print(f"  - {f.get('field_name')}: {f.get('description')}")
        print(f"\nEvidence priorities:")
        for e in p.get("evidence_priorities", []):
            print(f"  - {e}")
        print(f"\nDraft analysis prompt (first 800 chars):")
        print(f"  {(p.get('draft_analysis_prompt') or '')[:800]}...")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"\n\n→ Full designed prompts saved to: {OUTPUT_FILE}")
    print(f"   bootstrap_case_intel.py will use this file when --use-designed flag is passed.")


if __name__ == "__main__":
    main()
