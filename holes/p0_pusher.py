"""holes/p0_pusher.py — immediate Telegram push for new P0 holes.

Run every 5 minutes from a systemd timer. Scans holes_findings for P0 findings
that haven't been pushed yet (metadata->>'pushed_at' IS NULL), sends one Telegram
per finding via comms_send, marks them pushed.

P0 means: legal output hallucination, comms blackout, schema-breaking change,
client-facing leak, regression alert. Anything where waiting for the 06:00 PHT
digest would be too late.

Usage:
  python3 -m holes.p0_pusher          # push any unpushed P0s, mark pushed
  python3 -m holes.p0_pusher --dry-run # print what would be pushed
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from holes.base import DSN, LANDTEK_ROOT, load_env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, routine_name, hole_type, case_file, matter_code, doc_id,
               description, suggested_fix, metadata, created_at
          FROM holes_findings
         WHERE status='open' AND severity='P0'
           AND COALESCE(metadata->>'pushed_at', '') = ''
         ORDER BY created_at ASC
    """)
    pending = cur.fetchall()
    if not pending:
        print("  (no unpushed P0s)")
        return

    if args.dry_run:
        for f in pending:
            print(f"WOULD PUSH #{f['id']} [{f['routine_name']}] {f['description'][:120]}")
        return

    sys.path.insert(0, LANDTEK_ROOT)
    from comms import comms_send

    pushed = 0
    for f in pending:
        tag = f.get("case_file") or f.get("matter_code") or ""
        tag_s = f" · <code>{tag}</code>" if tag else ""
        fix_s = f"\n\n<b>Suggested fix:</b> {f['suggested_fix']}" if f.get("suggested_fix") else ""
        html = (
            f"🚨 <b>P0 hole #{f['id']}</b>{tag_s}\n"
            f"<i>routine: {f['routine_name']} · type: {f['hole_type']}</i>\n\n"
            f"{f['description']}"
            f"{fix_s}"
        )
        try:
            comms_send(html, audience="ops", parse_mode="HTML",
                       kind="holes_p0",
                       case_file=f.get("case_file") or "MWK-001")
            # Mark pushed
            cur.execute("""
                UPDATE holes_findings
                   SET metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object('pushed_at', %s)
                 WHERE id = %s
            """, (datetime.now(timezone.utc).isoformat(), f["id"]))
            pushed += 1
        except Exception as e:
            print(f"  ✗ failed to push #{f['id']}: {e}", file=sys.stderr)

    cur.close(); conn.close()
    print(f"  ✓ pushed {pushed}/{len(pending)} P0(s)")


if __name__ == "__main__":
    main()
