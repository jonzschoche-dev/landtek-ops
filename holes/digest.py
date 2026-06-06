"""holes/digest.py — daily 'Holes Report' consolidator.

Run at 06:00 PHT. Reads `holes_findings` WHERE status='open' AND severity in (P0..P3),
groups by severity then hole_type, formats as a single Telegram message via comms_send,
and writes a markdown copy to /root/landtek/drafts/holes_report_YYYY-MM-DD.md.

P0s are also pushed immediately by `holes/p0_pusher.py` when emitted, so the daily
digest is the wrap-up + reminder of what's still open.

Usage:
  python3 -m holes.digest                # full digest, ops audience
  python3 -m holes.digest --no-tg        # print to stdout only
  python3 -m holes.digest --since 24h    # only findings created in last 24h (default: all open)
"""
import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import psycopg2
import psycopg2.extras

from holes.base import DSN, LANDTEK_ROOT, load_env

SEVERITY_ORDER = ["P0", "P1", "P2", "P3", "info"]
SEVERITY_EMOJI = {"P0": "🚨", "P1": "🔴", "P2": "🟠", "P3": "🟡", "info": "•"}
HOLE_TYPE_LABEL = {
    "truth_gap":          "Truth gaps",
    "evidence_gap":       "Evidence gaps",
    "coverage_gap":       "Coverage gaps",
    "discipline_drift":   "Discipline drift",
    "schema_drift":       "Schema drift",
    "capacity_gap":       "Capacity gaps",
    "coordination_gap":   "Coordination gaps",
    "memory_drift":       "Memory drift",
}


def _parse_since(s: str) -> timedelta:
    m = re.match(r"^(\d+)\s*([hdw])$", s.strip().lower())
    if not m:
        raise ValueError(f"--since must be like '24h', '7d', '2w'; got {s!r}")
    n, unit = int(m.group(1)), m.group(2)
    return {"h": timedelta(hours=n), "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]


def fetch_findings(cur, since: timedelta = None):
    where = "status='open'"
    params = []
    if since is not None:
        where += " AND created_at >= now() - %s::interval"
        params.append(f"{int(since.total_seconds())} seconds")
    cur.execute(f"""
        SELECT id, routine_name, severity, hole_type, case_file, matter_code, doc_id,
               description, suggested_fix, auto_remediable, metadata, created_at
          FROM holes_findings
         WHERE {where}
         ORDER BY array_position(ARRAY['P0','P1','P2','P3','info']::text[], severity),
                  created_at DESC
    """, params)
    return cur.fetchall()


def render_html(findings, since: timedelta = None) -> str:
    """Telegram HTML."""
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scope = f"last {int(since.total_seconds()//3600)}h" if since else "all open"
    if not findings:
        return f"🟢 <b>Holes Report — {when}</b>\n\nNo open holes ({scope}). Leo is clean."

    by_sev_then_type = defaultdict(lambda: defaultdict(list))
    for f in findings:
        by_sev_then_type[f["severity"]][f["hole_type"]].append(f)

    counts = {sev: sum(len(v) for v in by_sev_then_type.get(sev, {}).values()) for sev in SEVERITY_ORDER}
    header_count = " · ".join(f"{SEVERITY_EMOJI[s]}{counts[s]}" for s in SEVERITY_ORDER if counts[s])

    out = [f"🛰️ <b>Holes Report — {when}</b>",
           f"<i>Scope: {scope} · {header_count}</i>",
           ""]
    for sev in SEVERITY_ORDER:
        if sev not in by_sev_then_type:
            continue
        out.append(f"{SEVERITY_EMOJI[sev]} <b>{sev}</b> "
                   f"({sum(len(v) for v in by_sev_then_type[sev].values())})")
        for hole_type, items in by_sev_then_type[sev].items():
            out.append(f"  <u>{HOLE_TYPE_LABEL.get(hole_type, hole_type)}</u>")
            for f in items[:10]:  # cap per group to keep message under TG limit
                tag = f.get("case_file") or f.get("matter_code") or ""
                tag = f" [{tag}]" if tag else ""
                fix = f.get("suggested_fix") or ""
                fix_short = f" → <i>{fix[:80]}</i>" if fix else ""
                out.append(f"  • #{f['id']}{tag} {f['description'][:200]}{fix_short}")
            if len(items) > 10:
                out.append(f"  • <i>+ {len(items)-10} more in {hole_type}</i>")
        out.append("")
    out.append(f"<i>{len(findings)} open holes total. Routines: holes_runs.</i>")
    return "\n".join(out)


def render_markdown(findings, since: timedelta = None) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scope = f"last {int(since.total_seconds()//3600)}h" if since else "all open"
    lines = [f"# Holes Report — {when}", "", f"_Scope: {scope}_", ""]
    if not findings:
        lines.append("**No open holes. Leo is clean.**")
        return "\n".join(lines)

    by_sev_then_type = defaultdict(lambda: defaultdict(list))
    for f in findings:
        by_sev_then_type[f["severity"]][f["hole_type"]].append(f)

    counts = {sev: sum(len(v) for v in by_sev_then_type.get(sev, {}).values()) for sev in SEVERITY_ORDER}
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---|")
    for sev in SEVERITY_ORDER:
        if counts.get(sev):
            lines.append(f"| {SEVERITY_EMOJI[sev]} {sev} | {counts[sev]} |")
    lines.append("")

    for sev in SEVERITY_ORDER:
        if sev not in by_sev_then_type:
            continue
        lines.append(f"## {SEVERITY_EMOJI[sev]} {sev}")
        for hole_type, items in by_sev_then_type[sev].items():
            lines.append("")
            lines.append(f"### {HOLE_TYPE_LABEL.get(hole_type, hole_type)} ({len(items)})")
            lines.append("")
            lines.append("| # | Routine | Case | Description | Suggested fix |")
            lines.append("|---|---|---|---|---|")
            for f in items:
                tag = f.get("case_file") or f.get("matter_code") or "—"
                desc = (f["description"] or "").replace("|", "\\|")
                fix = (f.get("suggested_fix") or "").replace("|", "\\|")
                lines.append(f"| {f['id']} | `{f['routine_name']}` | {tag} | "
                             f"{desc[:200]} | {fix[:200]} |")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="window (e.g. '24h'). Default: all open findings.")
    ap.add_argument("--no-tg", action="store_true", help="don't send to Telegram")
    ap.add_argument("--no-file", action="store_true", help="don't write markdown file")
    args = ap.parse_args()
    load_env()

    since_td = _parse_since(args.since) if args.since else None

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    findings = fetch_findings(cur, since=since_td)
    cur.close(); conn.close()

    html = render_html(findings, since=since_td)
    md = render_markdown(findings, since=since_td)

    if not args.no_file:
        drafts = Path(LANDTEK_ROOT) / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        out_path = drafts / f"holes_report_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}.md"
        out_path.write_text(md)
        print(f"  ✓ wrote {out_path}")

    if not args.no_tg:
        try:
            sys.path.insert(0, LANDTEK_ROOT)
            from comms import comms_send
            comms_send(html, audience="ops", parse_mode="HTML",
                       kind="holes_digest")
            print(f"  ✓ TG digest sent ({len(findings)} findings)")
        except Exception as e:
            print(f"  ✗ TG send failed: {e}", file=sys.stderr)
    else:
        print(html)


if __name__ == "__main__":
    main()
