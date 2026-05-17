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

    # REVERSE direction (deploy_166): the canonical spelling is KEESEY.
    # Earlier "Keesee" was a typo seeded by CLAUDE.md and propagated through
    # Opus/Haiku. Corpus evidence: 307 KEESEY occurrences vs 0 KEESEE; Patricia's
    # birth certificate, RTC Order caption (CV 26-360), and ARTA filings all
    # spell KEESEY. Reverse any prior Keesee→Keesey to fix the error.
    (r"\bPatricia\s+Keesee\s+Zschoche\b",
     "Patricia Keesey Zschoche",
     0,
     "deploy_166: revert prior Keesee enforcement — corpus has KEESEY 307x, KEESEE 0x"),
    (r"\bKEESEE\b",
     "KEESEY",
     0,
     "deploy_166: revert prior Keesee enforcement (all-caps)"),

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
    """Apply corrections to narrative paragraphs (between
    '### YYYY — Annual Narrative Summary' and '**Detailed Event Log:**')
    AND apply CANONICAL-NAME corrections globally to the whole document
    (deploy_166 fix — earlier the post-processor only touched narrative blocks,
    but the wrong-spelling errors propagated into the cross-ref index and
    event log too).
    """
    # Step 1: narrative-only corrections (venue, editorial strip, etc.)
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

    # Step 2: GLOBAL canonical-name fixes (apply to whole doc, including cross-ref).
    # Corpus evidence: Keesey appears 307× (Mary), 108× (Geraldine), 109× (Marcia),
    # Patricia birth-cert KEESEY, RTC Order KEESEY, ARTA caption KEESEY. Keesee = 0.
    GLOBAL_NAME_FIXES = [
        (r"\bKeesee\b",           "Keesey",       0,
         "deploy_166: KEESEE → KEESEY (canonical family name; 0 corpus occurrences of KEESEE)"),
        (r"\bKEESEE\b",           "KEESEY",       0,
         "deploy_166: KEESEE → KEESEY (all-caps)"),
        (r"\bKeeseey\b",          "Keesey",       0,
         "deploy_166: Keeseey (typo) → Keesey"),
        (r"\bKEESEEY\b",          "KEESEY",       0,
         "deploy_166: KEESEEY → KEESEY"),
    ]
    for pat, repl, flags, why in GLOBAL_NAME_FIXES:
        new_md, n = re.subn(pat, repl, new_md, flags=flags)
        if n > 0:
            all_applied.append({"pattern": pat, "n": n, "why": why})
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
