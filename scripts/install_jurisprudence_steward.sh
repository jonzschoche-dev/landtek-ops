#!/usr/bin/env bash
# install_jurisprudence_steward.sh — one-command VPS install for the Jurisprudence Steward.
# Idempotent: copies the unit pair, reloads systemd, enables the weekly timer, kicks a first run.
#   sudo bash scripts/install_jurisprudence_steward.sh            # install + enable + run once
#   sudo bash scripts/install_jurisprudence_steward.sh --no-run   # install + enable only
set -euo pipefail
REPO=/root/landtek
echo "[install] copying unit files -> /etc/systemd/system/"
cp "$REPO/systemd/landtek-jurisprudence-steward.service" /etc/systemd/system/
cp "$REPO/systemd/landtek-jurisprudence-steward.timer"   /etc/systemd/system/
echo "[install] daemon-reload + enable weekly timer"
systemctl daemon-reload
systemctl enable --now landtek-jurisprudence-steward.timer
systemctl list-timers landtek-jurisprudence-steward.timer --no-pager || true
if [ "${1:-}" != "--no-run" ]; then
  echo "[install] first run (non-blocking) -> /var/log/landtek_jurisprudence_steward.log"
  systemctl start --no-block landtek-jurisprudence-steward.service || true
fi
echo "[install] done. board: python3 $REPO/scripts/jurisprudence_steward.py --board"
