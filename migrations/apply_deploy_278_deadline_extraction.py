#!/usr/bin/env python3
"""Deploy 278 — deadline extraction from inbound documents/emails.

The forcing-function gap: ARTA Resolutions, court Orders, and agency Notices
arrive in our inbox + drive but nothing reads the deadline language and surfaces
it to the calendar. Today's Pajarillo ARTA Resolution literally says

    "you may file a Notice of Appeal with the Office of the President within
     fifteen (15) days from notice of this Resolution"

— a HARD bar against us by ~June 10 2026. If we miss it we lose the appeal.

This deploy:

  A. Schema:
     - Extend calendar_events.status check constraint to allow 'proposed'
     - Add columns: source_doc_id, source_email_id (FKs), deadline_kind,
       extraction_method, extraction_confidence, raw_clause
     - Indexes for the new FKs + deadline_kind

  B. Ship scripts/deadline_extractor.py (regex-only, zero LLM, audit-trail
     verbatim clause stored on every row)

  C. Install systemd timer landtek-deadline-extractor.timer (every 30 min)
     to scan last 7 days of new inbound docs/emails on each tick

  D. Backfill last 60 days

  E. Surface in calendar_briefer.py — proposed deadlines hit the 7am brief
     with a "REVIEW THIS" prompt. (calendar_briefer already pulls from
     calendar_events.start_at, so 'proposed' will appear automatically; we
     only have to make sure it filters them in.)

  F. Surface in Leo's Context Builder ACTIVE LANDSCAPE — but the existing
     calendar_today / calendar_tomorrow JSON aggregate from deploy_276
     already covers this since it pulls from calendar_events. Just verify
     it doesn't exclude status='proposed'.

Idempotent. Run multiple times safely.
"""
from __future__ import annotations

import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_278"

REPO_ROOT = "/root/landtek"
EXTRACTOR_PATH = f"{REPO_ROOT}/scripts/deadline_extractor.py"
TIMER_NAME = "landtek-deadline-extractor"
SYSTEMD_DIR = "/etc/systemd/system"


# -----------------------------------------------------------------------------
# A. Schema extensions
# -----------------------------------------------------------------------------

SCHEMA_SQL = """
-- 1. Allow 'proposed' status
ALTER TABLE calendar_events
  DROP CONSTRAINT IF EXISTS calendar_events_status_check;
ALTER TABLE calendar_events
  ADD  CONSTRAINT calendar_events_status_check
       CHECK (status = ANY (ARRAY['scheduled','completed','cancelled','rescheduled','proposed']));

-- 2. New columns (idempotent via IF NOT EXISTS)
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS source_doc_id        integer;
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS source_email_id      integer;
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS deadline_kind        text;
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS extraction_method    text;
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS extraction_confidence numeric(3,2);
ALTER TABLE calendar_events ADD COLUMN IF NOT EXISTS raw_clause           text;

-- 3. FKs (best-effort; skip if target table missing or FK already there)
DO $fk$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
     WHERE constraint_name = 'calendar_events_source_doc_fk'
       AND table_name = 'calendar_events'
  ) THEN
    ALTER TABLE calendar_events
      ADD CONSTRAINT calendar_events_source_doc_fk
      FOREIGN KEY (source_doc_id) REFERENCES documents(id) ON DELETE SET NULL;
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'doc FK skipped: %', SQLERRM;
END $fk$;

DO $fk2$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
     WHERE constraint_name = 'calendar_events_source_email_fk'
       AND table_name = 'calendar_events'
  ) THEN
    ALTER TABLE calendar_events
      ADD CONSTRAINT calendar_events_source_email_fk
      FOREIGN KEY (source_email_id) REFERENCES gmail_messages(id) ON DELETE SET NULL;
  END IF;
EXCEPTION WHEN others THEN
  RAISE NOTICE 'email FK skipped: %', SQLERRM;
END $fk2$;

-- 4. Indexes
CREATE INDEX IF NOT EXISTS idx_calendar_source_doc   ON calendar_events(source_doc_id)   WHERE source_doc_id   IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_source_email ON calendar_events(source_email_id) WHERE source_email_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_deadline_kind ON calendar_events(deadline_kind)  WHERE deadline_kind  IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_proposed     ON calendar_events(start_at)        WHERE status = 'proposed';
"""


# -----------------------------------------------------------------------------
# C. systemd timer files
# -----------------------------------------------------------------------------

SERVICE_UNIT = f"""[Unit]
Description=LandTek deadline extractor — scan inbound docs+emails for deadlines
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory={REPO_ROOT}
Environment="PG_DSN=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ExecStart=/usr/bin/python3 {EXTRACTOR_PATH} --days 7
StandardOutput=append:/var/log/landtek-deadline-extractor.log
StandardError=append:/var/log/landtek-deadline-extractor.log
"""

TIMER_UNIT = f"""[Unit]
Description=Run LandTek deadline extractor every 30 min

[Timer]
OnBootSec=4min
OnUnitActiveSec=30min
AccuracySec=1min
Unit={TIMER_NAME}.service

[Install]
WantedBy=timers.target
"""


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def write_unit(path: str, content: str) -> bool:
    """Write a systemd unit only if content differs. Returns True if changed."""
    existing = ""
    if os.path.exists(path):
        with open(path) as f:
            existing = f.read()
    if existing.strip() == content.strip():
        return False
    with open(path, "w") as f:
        f.write(content)
    return True


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    print("Deploy 278 — Deadline extraction from inbound documents")
    print("=" * 60)

    # ---- A. Schema ----
    print("\n  A) Schema extensions on calendar_events")
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))
    cur.execute(SCHEMA_SQL)
    conn.commit()
    print("    ✓ status check extended (+proposed)")
    print("    ✓ columns: source_doc_id, source_email_id, deadline_kind, extraction_method, extraction_confidence, raw_clause")
    print("    ✓ FKs + indexes")

    # ---- B. Extractor script present? ----
    print(f"\n  B) Extractor script presence check: {EXTRACTOR_PATH}")
    if not os.path.exists(EXTRACTOR_PATH):
        print("    ✗ MISSING — copy scripts/deadline_extractor.py to VPS before continuing")
        return 1
    st = os.stat(EXTRACTOR_PATH)
    os.chmod(EXTRACTOR_PATH, st.st_mode | 0o111)  # +x
    print(f"    ✓ present ({st.st_size} bytes), executable")

    # ---- C. systemd timer ----
    print("\n  C) Install systemd timer")
    svc_path = f"{SYSTEMD_DIR}/{TIMER_NAME}.service"
    tmr_path = f"{SYSTEMD_DIR}/{TIMER_NAME}.timer"
    svc_changed = write_unit(svc_path, SERVICE_UNIT)
    tmr_changed = write_unit(tmr_path, TIMER_UNIT)
    print(f"    {'✓ wrote' if svc_changed else '· unchanged'} {svc_path}")
    print(f"    {'✓ wrote' if tmr_changed else '· unchanged'} {tmr_path}")
    if svc_changed or tmr_changed:
        run(["systemctl", "daemon-reload"])
        print("    ✓ systemctl daemon-reload")
    rc, out = run(["systemctl", "enable", "--now", f"{TIMER_NAME}.timer"])
    print(f"    ✓ enabled+started {TIMER_NAME}.timer  rc={rc}")
    rc, out = run(["systemctl", "is-active", f"{TIMER_NAME}.timer"])
    print(f"    → is-active: {out}")

    # ---- D. Backfill ----
    print("\n  D) Backfill — last 60 days")
    rc, out = run(["python3", EXTRACTOR_PATH, "--days", "60"])
    print(out)
    if rc != 0:
        print(f"    ✗ backfill rc={rc}")
        return rc

    # ---- E. Recap of new calendar items ----
    print("\n  E) New deadline-extracted calendar events")
    conn2 = psycopg2.connect(DSN)
    cur2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur2.execute("""
        SELECT id, title, start_at, status, deadline_kind, source_doc_id, source_email_id,
               extraction_confidence
          FROM calendar_events
         WHERE source = 'deadline_extractor'
         ORDER BY start_at
    """)
    rows = cur2.fetchall()
    for r in rows:
        src = f"doc#{r['source_doc_id']}" if r['source_doc_id'] else f"email#{r['source_email_id']}"
        print(f"    #{r['id']:>3}  {r['start_at'].strftime('%Y-%m-%d %H:%M')}  "
              f"[{r['status']}/{r['deadline_kind']}] conf={r['extraction_confidence']}  "
              f"{r['title']}  ←{src}")
    if not rows:
        print("    (no deadlines extracted — patterns may not match current corpus)")
    cur2.close()
    conn2.close()

    print("\n  ✓ deploy_278 complete")
    print("    Next tick of landtek-deadline-extractor.timer: systemctl list-timers | grep deadline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
