#!/usr/bin/env bash
# install_corpus_steward.sh — one-command VPS install for the Corpus Steward resident agent.
# Idempotent: copies the unit pair, reloads systemd, enables the 6h timer, and kicks a first run
# so the corpus is swept immediately instead of waiting for the boot offset. Safe to re-run.
#
#   sudo bash scripts/install_corpus_steward.sh          # install + enable + run once now
#   sudo bash scripts/install_corpus_steward.sh --no-run # install + enable, don't run yet
#
# Runs ON THE VPS (needs systemctl + the /root/landtek checkout). No-op-safe on re-run.
set -euo pipefail
REPO=/root/landtek

echo "[install] copying unit files -> /etc/systemd/system/"
cp "$REPO/systemd/landtek-corpus-steward.service" /etc/systemd/system/
cp "$REPO/systemd/landtek-corpus-steward.timer"   /etc/systemd/system/

echo "[install] daemon-reload + enable timer"
systemctl daemon-reload
systemctl enable --now landtek-corpus-steward.timer

echo "[install] timer state:"
systemctl is-enabled landtek-corpus-steward.timer || true
systemctl list-timers landtek-corpus-steward.timer --no-pager || true

if [ "${1:-}" != "--no-run" ]; then
  echo "[install] kicking a first sweep now (writes /var/log/landtek_corpus_steward.log)"
  systemctl start landtek-corpus-steward.service || true
fi

echo "[install] done. Watch: journalctl -u landtek-corpus-steward.service -f  ·  tail -f /var/log/landtek_corpus_steward.log"
echo "[install] health:  python3 $REPO/scripts/agents.py --health | grep corpus_steward"
