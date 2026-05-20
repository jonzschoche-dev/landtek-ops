#!/usr/bin/env python3
"""build_title_tree — clean ASCII lineage trees from title_chain + titles.

Per Jonathan 2026-05-17: pollution in title_refs has phantom entries like
T-2023 (tax year), T-025-07 (tax PIN), T-001-00030. Plus title_chain has
OCR-typo parents like 1-106 (=OCT T-106), 7-32917 (=T-32917), -32917, etc.

This script:
  1. Filters phantom titles (year patterns, tax-PIN patterns)
  2. Normalizes well-known OCR-typo title-IDs to canonical form
  3. Builds a parent→children graph from title_chain + titles.parent_title
  4. Renders ASCII trees for TRACK A (T-4497 chain) and TRACK B (CV-6839 CARP)
  5. Lists orphan derivatives (have no clean parent)

Output: stdout + /root/landtek/drafts/title_tree_<date>.md
"""
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# ── Canonical title-ID patterns ─────────────────────────────────────────
# Real titles look like:
#   OCT T-NNN          (1934 onwards, original certificates)
#   T-NNNN to T-NNNNNN (transfer certificates)
#   T-NNN-NNNNNNNNNN+ (Balane-style long-format 2021-era titles)
RE_OCT          = re.compile(r'^OCT\s*T-\d{1,5}$', re.IGNORECASE)
RE_TCT_STD      = re.compile(r'^T-(\d{1,6})$')
RE_TCT_LONG     = re.compile(r'^T-\d{2,3}-\d{7,}$')  # T-079-2021002126

# Noise patterns (REJECT):
#   T-(year):  T-1989..T-2030  → tax year
#   T-NNN-NN(N): tax PIN segments  → assessor parcel
RE_TAX_PIN      = re.compile(r'^T-\d{3}-\d{1,4}(-\d+)?$')  # T-025-07, T-001-00030


def is_real_title(t):
    """Strict check: must match a known canonical pattern."""
    if not t:
        return False
    t = t.strip()
    if RE_OCT.match(t):
        return True
    if RE_TCT_LONG.match(t):
        return True
    m = RE_TCT_STD.match(t)
    if m:
        n = int(m.group(1))
        if 1900 <= n <= 2030:
            return False  # year-pattern → phantom
        return True
    return False


def is_tax_pin(t):
    return bool(RE_TAX_PIN.match((t or "").strip()))


# Explicit alias normalizations — per Jonathan: early-era titles were
# written in composite form (volume-folio or with non-T prefixes) and ARE
# the same titles as their modern T- equivalents. Composites merge to
# canonical form. Anything not here AND not is_real_title() is dropped.
NORMALIZATIONS = {
    # OCT T-106 aliases (the foundational 1934 original certificate)
    "1-106":          "OCT T-106",
    "F-106":          "OCT T-106",
    "7-106":          "OCT T-106",
    "T-106":          "OCT T-106",
    # T-32917 aliases (OCR typos of the same title)
    "7-32917":        "T-32917",
    "-32917":         "T-32917",
    # Volume/folio composites — same convention pre-modern
    "No.1-33365":     "T-33365",
    "1-184":          "T-184",
    "1-24":           "T-24",
    "1-25":           "T-25",
    # TCT 45616 with periods (T.C.T. punctuation variant)
    "T.C.T.45616":    "T-45616",
    # Range notation (handled separately — keep as descriptive)
    "T-32912-14":     "T-32912",       # primary of range; sibs T-32913, T-32914 already in graph
    # Patent (different title type but still a real title — keep as-is)
    "P-2218":         "P-2218",
    # Composite "T-7-136" likely Vol 7 / Folio 136 — keep but flag
    "T-7-136":        "T-136",
    # Garbage (truncated long-format Balane-era, etc.) — drop
    "210-23":         None,
    "2010000663":     None,
    "079-2010000694": None,
    "4770981":        None,
    "T-1130650":      None,           # 7-digit, no dash — likely OCR garbage
}


def normalize(t):
    """Return canonical title or None if it should be dropped."""
    if not t:
        return None
    t = t.strip()
    if t in NORMALIZATIONS:
        return NORMALIZATIONS[t]
    return t if is_real_title(t) else None


def load_edges(cur):
    """Pull parent→child edges from title_chain + titles.parent_title.
    Returns set of (parent_canonical, child_canonical, relationship, provenance)."""
    edges = set()

    cur.execute("""
        SELECT parent_title, child_title, relationship, provenance_level
          FROM title_chain
         WHERE case_file = 'MWK-001'
    """)
    for r in cur.fetchall():
        p = normalize(r["parent_title"])
        c = normalize(r["child_title"])
        if p and c and p != c:
            edges.add((p, c, r["relationship"] or "derivative", r["provenance_level"] or "?"))

    cur.execute("""
        SELECT parent_title, tct_number, provenance_level
          FROM titles
         WHERE case_file = 'MWK-001' AND parent_title IS NOT NULL
    """)
    for r in cur.fetchall():
        p = normalize(r["parent_title"])
        c = normalize(r["tct_number"])
        if p and c and p != c:
            edges.add((p, c, "derivative", r["provenance_level"] or "?"))

    return edges


def render_tree(root, children_of, contested, depth=0, prefix="", is_last=True, visited=None):
    """ASCII tree renderer. Marks contested titles with [CONTESTED]."""
    if visited is None:
        visited = set()
    if root in visited:
        return [f"{prefix}{'└── ' if is_last else '├── '}{root} _(cycle detected, skipping)_"]
    visited.add(root)

    lines = []
    if depth == 0:
        marker = ""
    else:
        marker = "└── " if is_last else "├── "

    label = root
    if root in contested:
        label = f"{root}  [⚠ {contested[root]}]"

    lines.append(f"{prefix}{marker}{label}")

    kids = sorted(children_of.get(root, []))
    new_prefix = prefix + ("    " if is_last else "│   ") if depth > 0 else "    "
    for i, kid in enumerate(kids):
        kid_is_last = (i == len(kids) - 1)
        lines.extend(render_tree(kid, children_of, contested,
                                  depth + 1, new_prefix, kid_is_last, visited))
    return lines


# Known contested titles for inline-flagging (per the void-SPA case)
CONTESTED = {
    "T-079-2021002127": "Balane title — VOID per CV-26-360 theory (issued from 2016 void deed)",
    "T-52540":          "Cancelled 2021 to issue Balane T-079 — CV-26-360 contesting cancellation",
}

# CV-6839 / CARP agrarian title set (per CLAUDE.md + Opus audit)
CARP_TITLES = ["T-14", "T-4494", "T-4501", "T-4502", "T-4503",
                "T-30681", "T-30682", "T-30683"]


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    edges = load_edges(cur)
    children_of = defaultdict(set)
    parents_of = defaultdict(set)
    relationship = {}
    for p, c, rel, prov in edges:
        children_of[p].add(c)
        parents_of[c].add(p)
        relationship[(p, c)] = (rel, prov)

    all_nodes = set(children_of) | set(parents_of)
    derivatives = set(parents_of)              # has at least one parent
    roots = {n for n in all_nodes if n not in derivatives}

    out = []
    out.append("# Title Tree — MWK-001 (clean, phantom-filtered)")
    out.append("")
    out.append(f"_{len(edges)} normalized edges across {len(all_nodes)} unique titles. "
                f"Phantom T-YYYY (years) and T-NNN-NN... (tax PINs) filtered. "
                f"Contested titles flagged inline._")
    out.append("")

    # ── TRACK A: T-4497 chain ──
    out.append("## TRACK A — T-4497 / OCT T-106 Lineage (CV-26-360 theatre)")
    out.append("")
    track_a_root = "OCT T-106"
    if track_a_root in children_of:
        out.append("```")
        out.extend(render_tree(track_a_root, children_of, CONTESTED))
        out.append("```")
    else:
        out.append("_OCT T-106 not present as a parent in current edges — checking T-4497 directly_")
        out.append("")
        if "T-4497" in children_of:
            out.append("```")
            out.extend(render_tree("T-4497", children_of, CONTESTED))
            out.append("```")
        else:
            out.append("_T-4497 also has no children in normalized edges. Data gap._")
    out.append("")

    # ── TRACK B: CARP / CV-6839 ──
    out.append("## TRACK B — CARP / CV-6839 Lineage (Just-compensation track)")
    out.append("")
    out.append("_The 8 CARP titles per CLAUDE.md context. These are typically standalone parcels under DAR/LBP proceedings, not a single lineage — but if any have parent/child structure in the DB, it'll appear here._")
    out.append("")
    for ct in CARP_TITLES:
        if ct in children_of or ct in parents_of:
            out.append(f"### {ct}")
            out.append("```")
            if ct in parents_of:
                parents_str = ", ".join(sorted(parents_of[ct]))
                out.append(f"   (parent(s): {parents_str})")
            if ct in children_of:
                out.extend(render_tree(ct, children_of, CONTESTED))
            else:
                out.append(f"{ct}  _(no derivatives in DB)_")
            out.append("```")
            out.append("")
        else:
            out.append(f"- **{ct}** — no lineage data in DB (no parent, no derivatives)")
    out.append("")

    # ── Orphans: derivatives with no parent in normalized graph ──
    out.append("## ORPHANED TITLES")
    out.append("")
    out.append("_Titles that appear as derivatives (children) elsewhere but have NO parent in the normalized edges. Either the parent was a phantom/typo we filtered, or the data has gaps._")
    out.append("")
    # Find titles mentioned anywhere but missing a parent
    cur.execute("""
        SELECT DISTINCT t FROM (
          SELECT child_title AS t FROM title_chain WHERE case_file='MWK-001'
          UNION
          SELECT tct_number AS t FROM titles WHERE case_file='MWK-001'
          UNION
          SELECT derivative_title AS t FROM title_transfers WHERE case_file='MWK-001'
        ) x
        WHERE t IS NOT NULL
    """)
    seen_anywhere = {normalize(r["t"]) for r in cur.fetchall()}
    seen_anywhere.discard(None)
    orphans = sorted(seen_anywhere - set(children_of) - set(parents_of))
    if orphans:
        for o in orphans:
            out.append(f"- {o}")
    else:
        out.append("_(none — all titles have either a parent or a derivative)_")
    out.append("")

    # ── Coverage summary ──
    out.append("## DATA COVERAGE")
    out.append("")
    cur.execute("""
        WITH all_refs AS (
          SELECT unnest(title_refs) AS t FROM client_history WHERE case_file='MWK-001'
          UNION ALL
          SELECT parent_title AS t FROM title_chain WHERE case_file='MWK-001'
          UNION ALL
          SELECT child_title AS t FROM title_chain WHERE case_file='MWK-001'
        )
        SELECT t, COUNT(*) AS n FROM all_refs WHERE t IS NOT NULL GROUP BY t ORDER BY n DESC
    """)
    raw_refs = cur.fetchall()
    real_count = sum(1 for r in raw_refs if is_real_title(r["t"]) or r["t"] in NORMALIZATIONS)
    phantom_count = len(raw_refs) - real_count
    out.append(f"- **{real_count}** distinct title-IDs pass the real-title filter")
    out.append(f"- **{phantom_count}** distinct phantom/tax-PIN/typo IDs rejected (see top below)")
    out.append("")
    out.append("**Top 10 phantom IDs (rejected):**")
    for r in raw_refs:
        if not (is_real_title(r["t"]) or r["t"] in NORMALIZATIONS):
            out.append(f"  - `{r['t']}` (×{r['n']}) — "
                        + ("tax PIN" if is_tax_pin(r["t"]) else "year-pattern or unrecognized format"))
    # cap to 10 in print
    md_text = "\n".join(out)

    # Cap the phantom list in the actual output file
    phantom_lines_seen = 0
    final_lines = []
    in_phantom_list = False
    for line in out:
        if line.startswith("**Top 10 phantom"):
            in_phantom_list = True
            final_lines.append(line)
            continue
        if in_phantom_list and line.startswith("  - "):
            phantom_lines_seen += 1
            if phantom_lines_seen > 10:
                continue
        final_lines.append(line)
    final_text = "\n".join(final_lines)

    # Write file + print
    out_path = Path(f"/root/landtek/drafts/title_tree_{date.today().isoformat()}.md")
    out_path.write_text(final_text)
    print(final_text)
    print(f"\n→ Saved to {out_path}")


if __name__ == "__main__":
    main()
