#!/usr/bin/env python3
"""test_survivable_record.py — corpus-wide assertion for A62 (the record survives the machine).

**What A62 requires.** Every invariant assumes the System of Record exists — A50 rebuilds projections
"from the SoR", A53 reasons from local Postgres. A62 governs the assumption itself: the SoR must survive
the droplet. The mechanism exists (nightly 02:00 `pg_dump` → `/root/backups/` + `rclone` off-box to Drive,
14-day retention) but was UNGOVERNED — a silently-dead cron or failing rclone would alarm nothing (the
installed-wrapper-drift failure class). This makes it mechanical:
  (a) FRESH   — a local dump newer than 26h and above a sanity size floor (a 0-byte gz "succeeds" silently);
  (b) CLEAN   — the backup log's recent window shows completion and no errors (rclone failures land here,
                so the OFF-BOX copy is covered without making the deploy gate depend on Drive connectivity —
                an A53-clean design: the gate never needs the internet to verify);
  (c) DRILLED — report-only: days since the last RECORDED restore drill (an unrestored backup is a hope,
                not a backup). Threshold-free until the first drill is recorded, then it ratchets.

Env overrides (for negative-testing): LANDTEK_BACKUP_DIR, LANDTEK_BACKUP_LOG.
Grounded 2026-07-10: dump 1.3 GB at 02:08 today, log clean, drill NEVER RECORDED (the honest gap).
"""
import glob
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

BACKUP_DIR = os.environ.get("LANDTEK_BACKUP_DIR", "/root/backups")
BACKUP_LOG = os.environ.get("LANDTEK_BACKUP_LOG", os.path.join(BACKUP_DIR, "backup.log"))
DRILL_MARKER = os.path.join(BACKUP_DIR, "RESTORE_DRILL.log")   # operator appends one line per drill
MAX_AGE_H = 26          # nightly at 02:00 → 26h tolerates clock/queue slop, catches a missed night
MIN_BYTES = 100 * 1024 * 1024   # DB ≈3 GB → dump ≈1.3 GB gz; 100 MB floor catches a truncated/empty dump


def _newest_dump():
    dumps = glob.glob(os.path.join(BACKUP_DIR, "landtek_backup_*.sql.gz"))
    if not dumps:
        return None
    return max(dumps, key=os.path.getmtime)


def backup_fresh(cur):
    """A62(a): a local SoR dump exists, is <26h old, and is above the sanity size floor."""
    d = _newest_dump()
    if d is None:
        raise TruthFailure(
            f"NO SoR dump found in {BACKUP_DIR} (landtek_backup_*.sql.gz) — the record does not survive "
            f"the machine (A62). Check the 02:00 cron `/root/backup_postgres.sh`.")
    age_h = (time.time() - os.path.getmtime(d)) / 3600
    size = os.path.getsize(d)
    if age_h > MAX_AGE_H:
        raise TruthFailure(
            f"SoR backup is STALE — newest dump {os.path.basename(d)} is {age_h:.0f}h old (>{MAX_AGE_H}h). "
            f"The nightly backup cron died silently (A62). Check `crontab -l` + {BACKUP_LOG}.")
    if size < MIN_BYTES:
        raise TruthFailure(
            f"SoR backup is SUSPICIOUSLY SMALL — {os.path.basename(d)} is {size/1e6:.0f} MB "
            f"(floor {MIN_BYTES/1e6:.0f} MB; a healthy dump is ~1.3 GB). A truncated/empty dump 'succeeds' "
            f"silently — treat as NO backup (A62).")


def backup_log_clean(cur):
    """A62(b): the LAST RUN's log block completed without errors — covers the rclone OFF-BOX copy (its
    failures print to this log) without the gate ever touching the network (A53-clean). Judged on the most
    recent run's block only (each run ends with 'Backup complete'), so a repaired pipeline goes green on its
    next clean run instead of dragging weeks-old error lines."""
    try:
        with open(BACKUP_LOG, errors="ignore") as f:
            text = f.read()
    except FileNotFoundError:
        raise TruthFailure(f"backup log {BACKUP_LOG} missing — cannot verify the off-box copy ran (A62).")
    marker = "Backup complete"
    if marker not in text:
        raise TruthFailure(f"backup log has no '{marker}' — the script has never finished (A62); tail {BACKUP_LOG}.")
    def _errs(seg):
        return [ln.strip()[:110] for ln in seg.splitlines()
                if any(w in ln.lower() for w in ("error", "failed", "fatal", "critical", "permission denied", "no space"))]
    runs = text.split(marker)
    after_last = _errs(runs[-1])           # a run that started but never reached 'complete'
    if after_last:
        raise TruthFailure(
            f"backup log shows {len(after_last)} error line(s) AFTER the last completed run — the current "
            f"run is failing before completion (A62): {after_last[:3]}")
    last_run = _errs(runs[-2])             # the block belonging to the most recent COMPLETED run
    if last_run:
        raise TruthFailure(
            f"the LAST backup run logged {len(last_run)} error line(s) — the dump or the rclone off-box "
            f"copy is failing (A62): {last_run[:3]}")


def restore_drill_reported(cur):
    """A62(c) — report-only: an unrestored backup is a hope. Surfaces days-since-drill on every run;
    never RED (the drill is an operator act to schedule, not a pipeline defect to alarm on nightly)."""
    if not os.path.exists(DRILL_MARKER):
        print(f"      [survivable] restore drill: NEVER RECORDED — run one (restore latest dump into a "
              f"scratch DB, count rows on 3 key tables) and append a dated line to {DRILL_MARKER}")
        return
    days = (time.time() - os.path.getmtime(DRILL_MARKER)) / 86400
    with open(DRILL_MARKER, errors="ignore") as f:
        last = ([ln.strip() for ln in f if ln.strip()] or ["(empty)"])[-1]
    print(f"      [survivable] restore drill: {days:.0f}d ago — “{last[:80]}” (A62; suggest quarterly)")


TESTS = [
    ("survivable.backup_fresh", backup_fresh),
    ("survivable.backup_log_clean", backup_log_clean),
    ("survivable.restore_drill_reported", restore_drill_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
