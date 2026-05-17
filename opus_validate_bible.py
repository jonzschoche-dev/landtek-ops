#!/usr/bin/env python3
"""opus_validate_bible — pre-delivery Opus audit (deploy_160).

Per Jonathan 2026-05-17 directive: "use opus to validate before the final output."
Sanctioned use case #1 from [[feedback_opus_as_advisor]] — strategic synthesis
at a major milestone (June 2 mediation prep).

Scope: audit 2025 + 2026 narratives + forward projection + spot-check
cross-reference index. Strict mandate: FLAG WHAT YOU'D CHANGE, do not rewrite.

Expected cost: $0.10-0.20.
"""
import re
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

BIBLE_PATH = "/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md"


def extract_section(md, start_pattern, end_pattern):
    """Return text between (inclusive) start_pattern and (exclusive) end_pattern."""
    start = re.search(start_pattern, md, re.MULTILINE)
    if not start:
        print(f"  ⚠ pattern not found: {start_pattern!r}")
        return ""
    rest = md[start.start():]
    end = re.search(end_pattern, rest, re.MULTILINE)
    if end:
        return rest[:end.start()]
    return rest[:8000]


def build_audit_payload():
    md = Path(BIBLE_PATH).read_text()
    # 2025 narrative + first 10 events
    s2025 = extract_section(md, r'^### 2025 — Annual Narrative Summary', r'^### 2026 — Annual Narrative Summary')
    s2026 = extract_section(md, r'^### 2026 — Annual Narrative Summary', r'^# 4\. MISSING')
    # Forward projection block
    s_proj = extract_section(md, r'^## Next Projected Events', r'^## Critical Open Deadlines')
    # Critical open deadlines
    s_dl = extract_section(md, r'^## Critical Open Deadlines', r'^## Coverage Audit Warnings')
    # First two cross-ref entries (T-4497, T-32917)
    s_xref = extract_section(md, r'^### T-4497', r'^### T-32916')
    return s2025, s2026, s_proj, s_dl, s_xref


def main():
    s2025, s2026, s_proj, s_dl, s_xref = build_audit_payload()

    user_msg = f"""# AUDIT REQUEST — Master Case Bible pre-delivery

I am preparing to deliver the Heirs of MWK Omnibus Master Case Bible to
Atty. Bonifacio Jr. Barandon and Patricia Keesee Zschoche ahead of the
June 2 2026 mediation in Civil Case 26-360. Before I ship the PDF, audit
the four sections below.

CRITICAL CONSTRAINTS:
  - FLAG what you would change. DO NOT rewrite or regenerate any section.
  - Lead with the highest-leverage issues (anything that would embarrass us
    in front of Barandon, or that misstates the void-SPA evidentiary stack).
  - Lower-priority style issues at the end.
  - Be concise — bullet points, not paragraphs.

RESPOND WITH EXACTLY THESE 5 SECTIONS:

  1. CITATION RISKS — claims in the narratives that ASSERT facts without a
     citation OR with weak citation. Each finding: line reference + the fix.
  2. EVIDENTIARY-CHAIN GAPS — places where the void-SPA → void-deed → void-T-079
     argument has missing primary instruments not flagged in the bible.
  3. TACTICAL PRIORITIES — among the 10 Forward Projected Events + Critical
     Open Deadlines, are these the highest-leverage moves for the T-16d
     mediation window? What's missing or out of order?
  4. CROSS-REFERENCE ACCURACY — given the T-4497 cross-reference spot-check,
     do the dates/events listed actually correspond to what you'd expect
     for the T-4497 chain? Any anomalies?
  5. SHIP-OR-HOLD VERDICT — one line: "SHIP" or "HOLD — fix N before shipping."

═══════════════════════════════════════════════════════════════════
SECTION A — 2025 NARRATIVE + DETAILED EVENT LOG (first 20 events)
═══════════════════════════════════════════════════════════════════
{s2025[:8000]}

═══════════════════════════════════════════════════════════════════
SECTION B — 2026 NARRATIVE + DETAILED EVENT LOG (first 20 events)
═══════════════════════════════════════════════════════════════════
{s2026[:8000]}

═══════════════════════════════════════════════════════════════════
SECTION C — FORWARD PROJECTED EVENTS (Layer E)
═══════════════════════════════════════════════════════════════════
{s_proj[:3000]}

═══════════════════════════════════════════════════════════════════
SECTION D — CRITICAL OPEN DEADLINES
═══════════════════════════════════════════════════════════════════
{s_dl[:1500]}

═══════════════════════════════════════════════════════════════════
SECTION E — CROSS-REFERENCE INDEX SPOT-CHECK (T-4497, 57 touches)
═══════════════════════════════════════════════════════════════════
{s_xref[:4000]}
"""
    print(f"Audit payload: {len(user_msg):,} chars")
    import anthropic
    from landtek_core import get
    from llm_billing import anthropic_call
    api_key = get("ANTHROPIC_API_KEY") or open("/root/landtek/.env").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip()
    client = anthropic.Anthropic(api_key=api_key)

    # Reuse the opus_advisor system prompt (1h-cached) for cost discipline
    from opus_advisor import OPUS_SYSTEM
    msg = anthropic_call(
        client,
        called_from="opus_validate_bible",
        purpose="pre_delivery_audit",
        case_file="MWK-001",
        model="claude-opus-4-7",
        max_tokens=2500,
        system=[{
            "type": "text",
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
            "text": OPUS_SYSTEM,
        }],
        messages=[{"role": "user", "content": user_msg}],
    )
    response = msg.content[0].text.strip()
    print("\n" + "═" * 70)
    print("OPUS PRE-DELIVERY AUDIT")
    print("═" * 70 + "\n")
    print(response)
    # Save to drafts
    audit_path = Path("/root/landtek/drafts/opus_bible_audit_2026-05-17.md")
    audit_path.write_text(f"# Opus Pre-Delivery Audit — Bible v3\n\n## Source\n\n"
                           f"{BIBLE_PATH}\n\n## Audit\n\n{response}\n")
    print(f"\n→ Saved to {audit_path}")
    print(f"\nTokens: {msg.usage.input_tokens}in / {msg.usage.output_tokens}out")
    print(f"Estimated cost: ${(msg.usage.input_tokens * 15 + msg.usage.output_tokens * 75) / 1_000_000:.3f}")


if __name__ == "__main__":
    main()
