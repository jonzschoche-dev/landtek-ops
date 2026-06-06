#!/usr/bin/env python3
"""Focused Opus re-audit after applying Bible v3.2 fixes (deploy_162).

Verify the 5 fixes landed and surface any residual issues. Smaller payload
(just the regenerated 2025 + 2026 narratives + the prior audit's verdict),
so cost should be ~$0.10-0.15.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

BIBLE_PATH = "/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md"
PRIOR_AUDIT = "/root/landtek/drafts/Opus_Case_Bible_Audit_Gate_May2026.md"


def extract_section(md, start, end):
    s = re.search(start, md, re.MULTILINE)
    if not s: return ""
    rest = md[s.start():]
    e = re.search(end, rest, re.MULTILINE)
    return rest[:e.start()] if e else rest[:8000]


def main():
    md = Path(BIBLE_PATH).read_text()
    prior = Path(PRIOR_AUDIT).read_text()
    n2025 = extract_section(md, r'^### 2025 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')
    n2026 = extract_section(md, r'^### 2026 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')
    # Just the top-5-corrections section from the prior audit
    top5 = ""
    m = re.search(r'TOP-5 CORRECTIONS REQUIRED', prior)
    if m:
        rest = prior[m.start():]
        end = re.search(r'^## H\.', rest, re.MULTILINE)
        top5 = rest[:end.start()] if end else rest[:3000]

    user_msg = f"""# OPUS RE-AUDIT — Bible v3.2 (post-fix verification)

You issued NO-GO with TOP-5 corrections in the prior audit. The team applied
the 5 fixes via database migration + narrative-prompt hardening, then
regenerated the 2025 + 2026 narratives. Verify whether the fixes landed
and identify any RESIDUAL defects before the PDF blast.

## YOUR PRIOR TOP-5 (for reference)
{top5[:2500]}

## DATA FIXES APPLIED
- Created missing MWK-ARTA-1212 matter (4 supporting docs: #753, #763, #817, #829).
- Re-tagged 9 CV-6839 bleed events (#42, #107, #126, #140, #153, #173, #214,
  #256, #343) from MWK-TCT4497 → MWK-CV6839. (#372 had no doc_date, excluded.)
- Note: ARTA-1319 (17 events) and ARTA-1378 (38 events) DO exist in the tag
  inventory; your prior audit flagged them as missing — that was a reading
  error on the inventory I provided. CV-6922 and Crim-9221 are tracked in
  the matters table as parallel-only proceedings.

## NARRATIVE-PROMPT HARDENING APPLIED
Added explicit guards in the per-year LLM system prompt:
  - "MWK-001 / ESTATE is top-level; CV-26360/CV-6839/TCT-4497/ARTA are siblings"
  - "Cesar dela Fuente died 21 June 2017 [doc#364]; any post-2017 attribution
    to him is impossible"
  - "CV-26360 venue: RTC Camarines Norte Branch 64 (never MTC Mercedes)"
  - "Patricia KEESEE Zschoche for caption; KEESEY for family name"
  - "Two distinct Pajarillos: Alexander L. (Mayor, ARTA-0747 resp.) vs
    Amado V. (deceased, parallel CV-6922)"
  - "CV-6839 title set is {{T-30681/82/83, T-4494, T-4501/02/03, T-14}}"

## REGENERATED 2025 NARRATIVE
{n2025[:3500]}

## REGENERATED 2026 NARRATIVE
{n2026[:3500]}

## YOUR TASK
Audit the new narratives against the TOP-5 corrections. For each correction,
produce:
  1. ✅ FIXED — if the new narratives correctly reflect the rule
  2. ⚠ PARTIAL — fix was applied but residual issues remain (list them)
  3. ❌ NOT FIXED — the original defect persists (cite the offending line)

THEN produce:
  - **NEW DEFECTS** (anything not in your prior audit that you spot now)
  - **REVISED GO/NO-GO VERDICT** (one line)

Be concise; bullet form. Lead with what would embarrass us in front of Barandon.
"""
    print(f"Re-audit payload: {len(user_msg):,} chars")

    import anthropic
    from landtek_core import get
    from llm_billing import anthropic_call
    api_key = get("ANTHROPIC_API_KEY") or open("/root/landtek/.env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
    client = anthropic.Anthropic(api_key=api_key)
    from opus_advisor import OPUS_SYSTEM

    msg = anthropic_call(
        client,
        called_from="opus_reaudit",
        purpose="post_fix_verification",
        case_file="MWK-001",
        model="claude-opus-4-7",
        max_tokens=2500,
        system=[{"type":"text", "cache_control":{"type":"ephemeral","ttl":"1h"}, "text": OPUS_SYSTEM}],
        messages=[{"role":"user", "content": user_msg}],
    )
    response = msg.content[0].text.strip()
    out_path = Path("/root/landtek/drafts/Opus_ReAudit_Bible_v3_2.md")
    out_path.write_text(f"# Opus Re-Audit — Bible v3.2\n\n{response}\n\n_Cost: ${(msg.usage.input_tokens*15 + msg.usage.output_tokens*75)/1_000_000:.3f}_\n")
    print("\n" + "═"*80)
    print("OPUS RE-AUDIT — Bible v3.2")
    print("═"*80 + "\n")
    print(response)
    print(f"\n→ Saved to {out_path}")
    print(f"  Cost: ${(msg.usage.input_tokens*15 + msg.usage.output_tokens*75)/1_000_000:.3f}")


if __name__ == "__main__":
    main()
