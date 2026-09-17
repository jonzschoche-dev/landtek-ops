#!/usr/bin/env bash
#
# activate_downstream.sh — enable the BUILT-BUT-DORMANT LandTek downstream agents,
# in lock-step with MASTER_PLAN + ONTOLOGY (A1-A61), gated on the truth/ontology guards.
#
# WHAT IT DOES
#   Enables the deterministic ($0, no-LLM) + local-Ollama (sovereign, $0) systemd timers
#   on the VPS so the fleet runs WITHOUT a human driving a coding session. Every timer is
#   wrapped in a pre-flight that refuses to enable anything if the guards are red.
#
# WHAT IT DOES NOT DO
#   - Does NOT enable landtek-reocr-sweep (the METERED Gemini OCR path). The $0 local sweep
#     (reocr_local.py) covers OCR. Keeps the stack token-free.
#   - Does NOT wire Leo (n8n) — that is an operator-applied edit (harness-blocked). This only
#     ships the autonomous BACKEND agents.
#   - Does NOT change any DB schema. No upgrade.
#
# USAGE
#   ./activate_downstream.sh --dry-run     # show what WOULD be enabled (default if no flag)
#   ./activate_downstream.sh --go          # run the pre-flight, then enable
#
# SAFE BY DESIGN: default is --dry-run. Nothing is touched unless you pass --go.
#
set -u

REPO="${LANDTEK_REPO:-/root/landtek}"
cd "$REPO" 2>/dev/null || { echo "✗ cannot cd to $REPO (set LANDTEK_REPO or run on the VPS)"; exit 2; }

GO=0
[[ "${1:-}" == "--go" ]] && GO=1

# The downstream agents to activate: deterministic + local-Ollama only.
# Format: "timer_unit|why". landtek-reocr-sweep (Gemini, metered) is DELIBERATELY ABSENT.
ENABLE=(
  "landtek-verify.timer|verify_loop — daily scout/measure (det, $0)"
  "landtek-verify-worker.timer|verify_worker — continuous reader, local Ollama (local, $0)"
  "landtek-cross-client.timer|cross_client_sentinel — entity separation (det, A5/A16)"
  "landtek-ontology-check.timer|ontology_check --sentinel — A1-A61 enforcement (det)"
  "landtek-deadline-refresh.timer|deadlines --write — A57 deadline totality (det)"
  "landtek-corpus-steward.timer|case_corpus_sweep — matter completeness (det)"
  "landtek-reocr-local-sweep.timer|reocr_local — $0 OCR drain, NOT gemini (local)"
  "landtek-geometry-drip.timer|geometry_pipeline — local-vision plot mining (local)"
  "landtek-filing-monitor.timer|filing_monitor — Discovery alerts, never files (det)"
  "landtek-digest.timer|build_digest — daily operator digest (det)"
  "landtek-jurisprudence-steward.timer|jurisprudence_steward — law-library self-audit (det)"
  "landtek-coordinator.timer|platform_coordinator — internal identity resolve (det, A31/A38)"
  "landtek-dependability.timer|client_dependability — ship-gate score (det, A57)"
)

echo "=============================================================="
echo "LandTek downstream-agent activation — gate-first"
echo "Repo: $REPO"
echo "Mode: $([ $GO -eq 1 ] && echo 'ENABLE (--go)' || echo 'DRY-RUN (default)')"
echo "Metered Gemini sweep: EXCLUDED (token-free posture)"
echo "=============================================================="

# ---- PRE-FLIGHT GATE 1: truth_tests suite must be green ----
echo
echo "[GATE 1] truth_tests/run_all.py (deploy-gate + nightly) ..."
if python3 truth_tests/run_all.py >/tmp/tt_$$.log 2>&1; then
  echo "  ✓ truth_tests GREEN"
else
  echo "  ✗ truth_tests RED — refusing to enable. Tail:"
  tail -20 /tmp/tt_$$.log | sed 's/^/    /'
  rm -f /tmp/tt_$$.log
  exit 1
fi
rm -f /tmp/tt_$$.log

# ---- PRE-FLIGHT GATE 2: ontology enforcement reality (no phantom enforcement) ----
echo
echo "[GATE 2] ontology_check.py --enforcement (phantom-enforcement guard) ..."
if python3 scripts/ontology_check.py --enforcement >/tmp/oc_$$.log 2>&1; then
  echo "  ✓ ontology enforcement REAL (no phantom modes)"
else
  echo "  ✗ ontology enforcement found a discrepancy — refusing to enable. Tail:"
  tail -25 /tmp/oc_$$.log | sed 's/^/    /'
  rm -f /tmp/oc_$$.log
  exit 1
fi
rm -f /tmp/oc_$$.log

# ---- GATE 3: confirm the metered sweep is NOT enabled (token-free invariant) ----
echo
echo "[GATE 3] confirm landtek-reocr-sweep (Gemini) is disabled ..."
if systemctl is-enabled landtek-reocr-sweep.timer 2>/dev/null | grep -qx enabled; then
  echo "  ✗ landtek-reocr-sweep is ENABLED (metered). Disable it first to keep token-free:"
  echo "      systemctl disable --now landtek-reocr-sweep.timer"
  exit 1
else
  echo "  ✓ metered Gemini sweep is NOT enabled (token-free invariant held)"
fi

# ---- ENABLE ----
echo
echo "Pre-flight passed. Enabling ${#ENABLE[@]} downstream agents:"
echo "--------------------------------------------------------------"
for entry in "${ENABLE[@]}"; do
  unit="${entry%%|*}"
  why="${entry#*|}"
  if [ $GO -eq 1 ]; then
    if systemctl enable --now "$unit" >/dev/null 2>&1; then
      echo "  ✓ ENABLED  $unit  — $why"
    else
      echo "  ✗ FAILED   $unit  — check 'systemctl status $unit' on VPS"
    fi
  else
    echo "  · would-enable  $unit  — $why"
  fi
done

echo
echo "--------------------------------------------------------------"
if [ $GO -eq 1 ]; then
  echo "Done. Verify with: python3 scripts/agents.py --health"
  echo "Token-free check:  python3 scripts/token_free_check.py"
  echo
  echo "STILL MANUAL (not covered here):"
  echo "  - launchctl load ~/Library/LaunchAgents/com.landtek.ollama-host.plist  (Mac, reboot-safe tier)"
  echo "  - Leo n8n wiring (operator-applied, harness-blocked)"
else
  echo "DRY-RUN only. Re-run with --go to actually enable."
fi
exit 0
