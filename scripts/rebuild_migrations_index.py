#!/usr/bin/env python3
"""Rebuild migrations/MIGRATIONS_INDEX.md from deploy_*.sql on disk.

DEPLOY_LOG.md is the cowork/workflow event log — not the SQL deploy census.
This index is the living list of schema/script deploys in the tree.
"""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"


def main() -> None:
    rows = []
    for p in sorted(MIG.glob("deploy_*.sql")):
        text = p.read_text(errors="replace")
        first = next((ln.strip() for ln in text.splitlines() if ln.strip().startswith("--")), "")
        first = re.sub(r"^--\s*", "", first)[:140]
        m = re.match(r"deploy_(\d+)", p.name)
        num = m.group(1) if m else "—"
        rows.append((num, p.name, first or "(no header comment)"))
    appliers = sorted(MIG.glob("apply_deploy_*.py"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M PhST")
    numbered = sum(1 for n, _, __ in rows if n != "—")
    high = max((n for n, _, __ in rows if n.isdigit()), default="?")
    out = [
        "# Migrations / Deploy SQL Index",
        "",
        f"*Rebuilt {now} by `scripts/rebuild_migrations_index.py` from `migrations/deploy_*.sql`.*",
        "",
        "This is the **authoritative file census** of SQL deploys in the tree.",
        "`DEPLOY_LOG.md` / `DEPLOY_LOG.csv` are the older cowork/workflow event log (May 2026 era) and",
        "**do not** list schema deploys past the low 100s — do not treat them as the SQL inventory.",
        "",
        f"**Count:** {len(rows)} `deploy_*.sql` files · numbered: {numbered} · unnumbered: {len(rows) - numbered}",
        "",
        "| # | File | Header (first comment) |",
        "|---|---|---|",
    ]
    for num, name, header in rows:
        out.append(f"| {num} | `{name}` | {header.replace('|', '\\|')} |")
    out += ["", "## Companion Python appliers (`apply_deploy_*.py`)", ""]
    if appliers:
        out += ["| File |", "|---|"]
        out += [f"| `{p.name}` |" for p in appliers]
    else:
        out.append("_None._")
    out += [
        "",
        "## Gaps / notes",
        "- Numbered series is **not contiguous** (legacy skips are normal).",
        f"- Highest numbered SQL in tree: **{high}**.",
        "- Apply on VPS via the usual psql/docker path; Mac may lack PG reachability.",
        "- After adding a `deploy_NNNN_*.sql`, re-run: `python3 scripts/rebuild_migrations_index.py`",
        "",
    ]
    path = MIG / "MIGRATIONS_INDEX.md"
    path.write_text("\n".join(out) + "\n")
    print(f"wrote {path} ({len(rows)} deploy_*.sql)")


if __name__ == "__main__":
    main()
