#!/usr/bin/env python3
"""narrative_postprocess — deterministic corrections to bible narratives (deploy_163).

Per Opus re-audit findings, the Haiku narrator is being faithful to source-document
OCR (which contains 'MTC Mercedes' draft captions, etc.), so prompt hardening alone
isn't enough. This post-processor does targeted regex replacements on the narrative
paragraphs only (between '### YYYY — Annual Narrative Summary' and '**Detailed Event Log:**').

The corrections are documented + reviewable. Runs idempotently.
"""
import re
from pathlib import Path

BIBLE_PATH = "/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md"

# (pattern, replacement, flags, why)
CORRECTIONS = [
    # Venue: MTC Mercedes → RTC Camarines Norte Br 64 (Daet)
    (r"\bMunicipal Trial Court of Mercedes\b",
     "RTC Camarines Norte Branch 64 (the draft caption read 'MTC Mercedes' but the operative filing is at the RTC)",
     re.IGNORECASE,
     "Opus re-audit: CV-26360 venue is RTC Br 64 Daet, not MTC Mercedes"),

    (r"\bBranch 64,?\s*Mercedes\b",
     "Branch 64, Daet, Camarines Norte",
     re.IGNORECASE,
     "Opus re-audit: Branch 64 sits in Daet, not Mercedes"),

    (r"\bRTC Branch 64,\s*Mercedes\b",
     "RTC Branch 64, Daet, Camarines Norte",
     re.IGNORECASE,
     "Opus re-audit: Branch 64 sits in Daet"),

    # Spelling: Keesey → Keesee for the caption-name pattern
    # Specifically "Patricia Keesey Zschoche" (the plaintiff caption)
    (r"\bPatricia\s+Keesey\s+Zschoche\b",
     "Patricia Keesee Zschoche",
     0,
     "Opus re-audit: caption spelling is KEESEE, not KEESEY"),

    # Editorial-conclusion strip: the "no causal linkage..." sentence in 2026
    (r"No causal linkage between the ARTA filings and CV-26360 discovery phases is evident from the record;\s*both tracks advanced in parallel\.",
     "ARTA filings and CV-26360 advanced as separate tracks during this period.",
     re.IGNORECASE,
     "Opus re-audit: bibles narrate, not opine; strip causal-linkage editorial"),

    # Strip the inline "(draft caption read MTC Mercedes ...)" parenthetical
    # Opus final check: internal editorial doesn't belong in client-facing prose.
    (r"\s*\(the draft caption read 'MTC Mercedes' but the operative filing is at the RTC\)",
     "",
     0,
     "Opus final check: strip inline editorial about draft caption"),

    # Fix "#" markdown header artifact leaked into italicized narrative body.
    # Haiku emits "# YYYY Year Summary..." as the first line of its output, but
    # the narrative is wrapped in asterisks for italics so a literal # at the
    # start renders as plain text. Strip the markdown-header prefix.
    (r"^# (\d{4}[^\n]*)",
     r"**\1**",
     re.MULTILINE,
     "Opus final check: convert leaked # markdown-header to bold span inside italicized narrative"),
]


def apply_corrections(text):
    """Apply each correction. Return (new_text, list of applied corrections + counts)."""
    applied = []
    for pattern, replacement, flags, why in CORRECTIONS:
        new_text, n = re.subn(pattern, replacement, text, flags=flags)
        if n > 0:
            applied.append({"pattern": pattern, "n": n, "why": why})
            text = new_text
    return text, applied


def patch_narrative_blocks(md):
    """Apply corrections only to narrative paragraphs (between
    '### YYYY — Annual Narrative Summary' and '**Detailed Event Log:**')."""
    # Find all narrative blocks
    pattern = re.compile(
        r"(### \d{4} — Annual Narrative Summary\n+\*)([^*]+?)(\*\n+\*\*Detailed Event Log:\*\*)",
        re.MULTILINE
    )
    all_applied = []
    def replacer(m):
        prefix, narrative, suffix = m.group(1), m.group(2), m.group(3)
        new_narrative, applied = apply_corrections(narrative)
        all_applied.extend(applied)
        return prefix + new_narrative + suffix
    new_md = pattern.sub(replacer, md)
    return new_md, all_applied


def main():
    md = Path(BIBLE_PATH).read_text()
    new_md, applied = patch_narrative_blocks(md)
    Path(BIBLE_PATH).write_text(new_md)
    print(f"Wrote {BIBLE_PATH} ({len(new_md):,} chars)")
    print(f"\nCorrections applied ({len(applied)} total hits across narratives):")
    # Group by pattern for cleaner output
    from collections import defaultdict
    grouped = defaultdict(lambda: {"n": 0, "why": ""})
    for a in applied:
        grouped[a["pattern"]]["n"] += a["n"]
        grouped[a["pattern"]]["why"] = a["why"]
    for pat, info in grouped.items():
        print(f"  ({info['n']}x) {info['why']}")
        print(f"        pattern: {pat[:80]}")


if __name__ == "__main__":
    main()
