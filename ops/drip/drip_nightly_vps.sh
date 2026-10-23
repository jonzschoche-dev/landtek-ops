#!/bin/bash
# Nightly drip routine — runs ON THE VPS at 00:00 Manila (16:00 UTC) via landtek-drip-nightly.timer.
# Never sends, never prints. Works whether or not the Mac is on.
#   1. pull jonzschoche@gmail.com office mail (the inbox every MWK drip goes out from) into gmail_messages
#   2. ingest_email_bodies.py: office e-mails become corpus documents (an office's reply = proof of receipt)
#   3. drip_log.py reconcile: office replies and our sends nobody logged are logged; proofs start clocks
#   4. drip_board.py: one board of every ladder across all matters + ranked next targets
#   5. truth_tests/test_drip_core.py: the drip is fed and not blind (result in the log; never blocks the board)
#   6. ingest the per-client boards into the corpus (client-separated; the all-clients board stays local)
# A dead token (invalid_grant) must not stop the board: step 1 logs and the board still runs on what is in the DB.
cd /root/landtek || exit 1
set -a; . /root/.landtek_db.env; set +a   # secret lives in a 600 file, not here (Phase 0, 23 Oct 2026)
export PG_DSN="postgresql://${PGUSER}:${PGPASSWORD}@172.18.0.3:5432/n8n"
echo "=== $(date -u '+%F %T') UTC nightly drip ==="
/usr/bin/python3 gmail_watcher.py --account backup --query "(ARTA OR PENRO OR assessor OR ombudsman OR manifestation OR resolution OR docket OR Balane OR Keesey OR Zschoche OR Inocalla OR Paracale OR Barandon OR sanggunian OR DILG OR CTN OR Hoppe OR Worrick OR from:gov.ph OR from:judiciary.gov.ph OR from:lams.region5@gmail.com OR from:dilg5records2019@gmail.com OR from:ablagemma@yahoo.com OR from:omixamjr_anagam@yahoo.com OR from:barandon_lawoffice@yahoo.com OR from:penro.camnorte@yahoo.com) -category:promotions" --max 300 \
  || echo "jonzschoche pull FAILED (token? re-mint on the Mac: scripts/mint_gmail_backup_token.py) — board runs on existing data"
/usr/bin/python3 ingest_email_bodies.py --since "$(date -u -d '4 days ago' +%F)" | tail -4 || echo "email bodies FAILED"
/usr/bin/python3 scripts/drip_log.py reconcile --since "$(date -u -d '10 days ago' +%F)" || echo "reconcile FAILED"
/usr/bin/python3 scripts/drip_board.py || echo "board FAILED"
/usr/bin/python3 truth_tests/test_drip_core.py | grep -E '✓|✗|FAIL' || echo "drip core check FAILED"
for b in case_work/DRIP_BOARDS/DRIP_BOARD_MWK-001.md case_work/DRIP_BOARDS/DRIP_BOARD_Paracale-001.md; do
  [ -f "$b" ] && { /usr/bin/python3 scripts/ingest_strategy_docs.py --apply --only "$b" || echo "board ingest FAILED: $b"; }
done
exit 0
