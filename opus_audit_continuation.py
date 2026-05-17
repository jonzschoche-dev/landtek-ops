#!/usr/bin/env python3
"""Continuation of opus_audit_gate to deliver truncated sections E (rest), F, G, H."""
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

AUDIT_PATH = "/root/landtek/drafts/Opus_Case_Bible_Audit_Gate_May2026.md"


def main():
    prior = Path(AUDIT_PATH).read_text()
    # Send Opus what we have so it can pick up exactly where it cut off
    user_msg = f"""# CONTINUATION — Opus Audit Gate

Your prior response was truncated at max_tokens. Below is everything you produced
(sections A–start of E). Complete the audit by producing ONLY these remaining
sections, in order:

  E. 2026 NARRATIVE AUDIT (the table you started — finish it; do not redo)
  F. CROSS-REF INDEX SPOT-CHECK (the high-risk entries: T-4497, T-30681,
     T-30682, T-30683, T-4501-3, ARTA-0690/0747/0792/1210/1321/1891)
  G. FORWARD-RISK MEMO with subsections:
       - Safe to use now
       - Verify before showing to counsel
       - Do not rely upon yet
       - TOP-5 CORRECTIONS REQUIRED BEFORE FINAL PDF (the absolute must-fix list)
  H. GO/NO-GO VERDICT (one line)

The cross-ref data and 2026 narrative are in your context from the prior turn.
You do NOT need them resent. Just complete the audit cleanly.

PRIOR (truncated) AUDIT — for continuity:
═══════════════════════════════════════════════
{prior}
═══════════════════════════════════════════════
"""
    print(f"Continuation payload: {len(user_msg):,} chars")

    import anthropic
    from landtek_core import get
    from llm_billing import anthropic_call
    api_key = get("ANTHROPIC_API_KEY") or open("/root/landtek/.env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
    client = anthropic.Anthropic(api_key=api_key)
    from opus_advisor import OPUS_SYSTEM

    msg = anthropic_call(
        client,
        called_from="opus_audit_gate",
        purpose="audit_continuation",
        case_file="MWK-001",
        model="claude-opus-4-7",
        max_tokens=4000,
        system=[{"type":"text", "cache_control":{"type":"ephemeral","ttl":"1h"}, "text": OPUS_SYSTEM}],
        messages=[{"role":"user", "content": user_msg}],
    )
    response = msg.content[0].text.strip()

    # Append to the audit file
    with open(AUDIT_PATH, "a") as f:
        f.write("\n\n---\n\n# AUDIT CONTINUATION (sections E-rest, F, G, H)\n\n")
        f.write(response)
        f.write(f"\n\n_Continuation cost: ${(msg.usage.input_tokens * 15 + msg.usage.output_tokens * 75)/1_000_000:.3f} "
                f"({msg.usage.input_tokens}in / {msg.usage.output_tokens}out — cache hit on system prompt)_\n")

    print("\n" + "═"*80)
    print("OPUS AUDIT CONTINUATION (sections F, G, H)")
    print("═"*80 + "\n")
    print(response)
    print(f"\n→ Appended to {AUDIT_PATH}")
    print(f"  Continuation cost: ${(msg.usage.input_tokens * 15 + msg.usage.output_tokens * 75)/1_000_000:.3f}")


if __name__ == "__main__":
    main()
