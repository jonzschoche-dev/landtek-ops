#!/usr/bin/env python3
"""test_drip_core.py — the drip runs on five FED tables (Jonathan, 23 Oct 2026: "take ownership … five-table
consolidation and the single logging step, then work down the design list with a test for each").

What went wrong before this test existed: the drip was worked from chat and markdown; step_plan went stale,
office_obligation held no running clock, events carried no ladder, and the jonzschoche mail feed was dead for a
month — and nothing turned red. These assertions make each of those failures visible on every deploy and night.

Cutover: rows logged before 2026-10-23 are history and are not judged (drip_event is append-only).
Deterministic, read-only, creditless.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure

CUTOVER = "2026-10-23"


def core_objects_exist(cur):
    """The single logging step's schema is present: ladder-tagged event view, ladder status view, clock ladder column."""
    cur.execute("SELECT to_regclass('drip_event_v') v, to_regclass('drip_ladder_status') s")
    r = cur.fetchone()
    if not (r["v"] and r["s"]):
        raise TruthFailure("drip_event_v / drip_ladder_status views are missing (migrations/drip_core_2026-10-23.sql)")
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name='office_obligation' AND column_name='ladder'")
    if not cur.fetchone():
        raise TruthFailure("office_obligation.ladder is missing — clocks cannot be joined to their ladder")
    print("      [drip core] views + clock ladder column present")


def every_new_event_names_its_ladder(cur):
    """Since cutover, every send/draft/receipt/reply/field event names its ladder — the board, clocks and UI join on it."""
    cur.execute("""SELECT id, kind FROM drip_event_v WHERE created_at >= %s
                    AND kind IN ('sent','drafted','receipt','reply','field','dispatched') AND ladder IS NULL""", (CUTOVER,))
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"{len(bad)} drip event(s) with no ladder since {CUTOVER}: "
                           + ", ".join(f"#{r['id']} {r['kind']}" for r in bad[:10])
                           + ". Log through scripts/drip_log.py, never a bare INSERT.")
    print("      [drip core] every event since cutover names its ladder")


def every_proven_receipt_runs_a_clock(cur):
    """A receipt with a corpus proof document must have started a clock on its ladder (served_at + due_at)."""
    cur.execute("""SELECT v.id, v.ladder FROM drip_event_v v
                    WHERE v.created_at >= %s AND v.kind = 'receipt' AND v.detail ? 'proof_doc_id'
                      AND NOT EXISTS (SELECT 1 FROM office_obligation o WHERE o.ladder = v.ladder
                                       AND o.served_at IS NOT NULL AND o.due_at IS NOT NULL)""", (CUTOVER,))
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"{len(bad)} proven receipt(s) with no running clock: "
                           + ", ".join(f"#{r['id']} {r['ladder']}" for r in bad[:10]))
    print("      [drip core] every proven receipt has a running clock")


def clocks_are_sane(cur):
    """A clock's due date is after its service date, and a running clock always carries corpus proof."""
    cur.execute("""SELECT id, ladder FROM office_obligation
                    WHERE (due_at IS NOT NULL AND served_at IS NOT NULL AND due_at <= served_at)
                       OR (state = 'served_running' AND service_proof_doc_id IS NULL)""")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(f"{len(bad)} malformed clock(s): " + ", ".join(f"#{r['id']} {r['ladder']}" for r in bad))
    print("      [drip core] clocks sane (due after service; proof on every running clock)")


def drip_is_not_blind(cur):
    """The drip can see work: at least one clock is running or answered. Zero means the tables are not being fed."""
    cur.execute("""SELECT count(*) n FROM office_obligation
                    WHERE state IN ('served_running','replied_not_performed','partial','lapsed','consequence_staged')""")
    if cur.fetchone()["n"] == 0:
        raise TruthFailure("no live clock in office_obligation — the drip is blind (log receipts via scripts/drip_log.py)")
    print("      [drip core] live clocks present")


def both_mail_feeds_alive(cur):
    """Both Gmail tokens (hayuma + jonzschoche) check OK. The jonzschoche token died silently ~22 Sep 2026."""
    cur.execute("""SELECT DISTINCT ON (token_key) token_key, status, checked_at FROM token_health
                    WHERE token_key IN ('GMAIL_REFRESH_TOKEN','GMAIL_REFRESH_TOKEN_BACKUP')
                    ORDER BY token_key, checked_at DESC""")
    rows = {r["token_key"]: r for r in cur.fetchall()}
    missing = [k for k in ("GMAIL_REFRESH_TOKEN", "GMAIL_REFRESH_TOKEN_BACKUP") if k not in rows]
    if missing:
        raise TruthFailure(f"token_health has never checked {missing} — the sentinel is not watching the mail feed")
    bad = [f"{k}={r['status']}" for k, r in rows.items() if r["status"] != "ok"]
    if bad:
        raise TruthFailure("mail feed token not OK: " + ", ".join(bad)
                           + " (jonzschoche: on the Mac run scripts/mint_gmail_backup_token.py)")
    print("      [drip core] both Gmail tokens OK")


def board_rebuilt_nightly(cur):
    """The per-client drip board in the corpus was rebuilt within the last ~26 hours (landtek-drip-nightly.timer)."""
    cur.execute("""SELECT max(updated_at) m FROM documents
                    WHERE file_path = 'case_work/DRIP_BOARDS/DRIP_BOARD_MWK-001.md'""")
    m = cur.fetchone()["m"]
    if not m:
        raise TruthFailure("MWK drip board is not in the corpus")
    if m.tzinfo is None:
        m = m.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - m > timedelta(hours=26):
        raise TruthFailure(f"MWK drip board last rebuilt {m:%Y-%m-%d %H:%M} UTC — the nightly drip did not run")
    print("      [drip core] board rebuilt within 26 h")


def interface_never_sends(cur):
    """The Drip UI and the Gmail staging helper only CREATE DRAFTS: no messages.send / drafts.send / SMTP anywhere."""
    import re as _re
    root = "/root/landtek" if os.path.isdir("/root/landtek") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    bad = []
    for rel in ("drip_ui/app.py", "scripts/drip_stage_gmail.py"):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        src = open(path).read()
        if _re.search(r"messages\(\)\.send|drafts\(\)\.send|smtplib|\.sendmail\(", src):
            bad.append(rel)
    if bad:
        raise TruthFailure(f"send path found in {bad}: the interface may only stage drafts (Charter §11.1 never sends)")
    print("      [drip core] interface and Gmail staging carry no send path")


TESTS = [
    ("drip_core.objects_exist", core_objects_exist),
    ("drip_core.every_new_event_names_its_ladder", every_new_event_names_its_ladder),
    ("drip_core.every_proven_receipt_runs_a_clock", every_proven_receipt_runs_a_clock),
    ("drip_core.clocks_are_sane", clocks_are_sane),
    ("drip_core.drip_is_not_blind", drip_is_not_blind),
    ("drip_core.both_mail_feeds_alive", both_mail_feeds_alive),
    ("drip_core.board_rebuilt_nightly", board_rebuilt_nightly),
    ("drip_core.interface_never_sends", interface_never_sends),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
