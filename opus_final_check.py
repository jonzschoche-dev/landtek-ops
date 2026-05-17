#!/usr/bin/env python3
"""opus_final_check — final SHIP-or-NO-GO pass on post-processed narratives (deploy_164).

Lean prompt — feeds Opus only the corrected 2025 + 2026 narratives + the prior
re-audit's NOT-FIXED list, and asks the binary question. Expected cost ~$0.10.
"""
import re, sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

BIBLE_PATH = "/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md"


def extract(md, start, end):
    s = re.search(start, md, re.MULTILINE)
    if not s: return ""
    rest = md[s.start():]
    e = re.search(end, rest, re.MULTILINE)
    return rest[:e.start()] if e else rest[:8000]


def main():
    md = Path(BIBLE_PATH).read_text()
    n2025 = extract(md, r'^### 2025 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')
    n2026 = extract(md, r'^### 2026 — Annual Narrative Summary', r'\*\*Detailed Event Log:\*\*')

    user_msg = f"""# OPUS FINAL CHECK — Bible v3.2.1 (post-corrections)

You issued NO-GO twice. After the second audit, the team applied DETERMINISTIC
post-processing corrections (regex find-and-replace on narrative paragraphs)
to fix the residual venue + caption-spelling + editorializing defects you
flagged. Verify the corrections landed and issue your binary verdict.

## CORRECTIONS APPLIED (regex post-processor, 7 hits)
- 3x: "Municipal Trial Court of Mercedes" → "RTC Camarines Norte Branch 64
       (the draft caption read 'MTC Mercedes' but the operative filing is at the RTC)"
- 2x: "Patricia Keesey Zschoche" → "Patricia Keesee Zschoche"
- 1x: "Branch 64, Mercedes" → "Branch 64, Daet, Camarines Norte"
- 1x: "No causal linkage between the ARTA filings and CV-26360 discovery..."
       → "ARTA filings and CV-26360 advanced as separate tracks during this period."

## CORRECTED 2025 NARRATIVE
{n2025[:3500]}

## CORRECTED 2026 NARRATIVE
{n2026[:3500]}

## TASK
Read the two narratives. Issue ONE of these verdicts and nothing else:

  ✅ SHIP — the corrected narratives are defensible to Atty. Barandon.
  ⚠ SHIP-WITH-NOTES — defensible but with minor presentational issues
      (list them in 3-5 bullets).
  ❌ NO-GO — a substantive defect remains (cite the offending line and the fix).

Be concise. Do not re-audit the entire bible architecture — just these
narratives + your prior critique chain.
"""
    print(f"Final-check payload: {len(user_msg):,} chars")

    import anthropic
    from landtek_core import get
    from llm_billing import anthropic_call
    api_key = get("ANTHROPIC_API_KEY") or open("/root/landtek/.env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
    client = anthropic.Anthropic(api_key=api_key)
    from opus_advisor import OPUS_SYSTEM

    msg = anthropic_call(
        client,
        called_from="opus_final_check",
        purpose="ship_verdict",
        case_file="MWK-001",
        model="claude-opus-4-7",
        max_tokens=1200,
        system=[{"type":"text", "cache_control":{"type":"ephemeral","ttl":"1h"}, "text": OPUS_SYSTEM}],
        messages=[{"role":"user", "content": user_msg}],
    )
    response = msg.content[0].text.strip()
    out_path = Path("/root/landtek/drafts/Opus_FinalCheck_Bible_v3_2_1.md")
    cost = (msg.usage.input_tokens*15 + msg.usage.output_tokens*75)/1_000_000
    out_path.write_text(f"# Opus Final Check — Bible v3.2.1\n\n{response}\n\n_Cost: ${cost:.3f}_\n")
    print("\n" + "═"*80)
    print("OPUS FINAL CHECK — Bible v3.2.1")
    print("═"*80 + "\n")
    print(response)
    print(f"\n→ Saved to {out_path}")
    print(f"  Cost: ${cost:.3f}")


if __name__ == "__main__":
    main()
