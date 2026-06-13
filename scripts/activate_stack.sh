#!/usr/bin/env bash
# activate_stack.sh — turn the LeoLandTek stack back ON, in the SAFE order, once
# Anthropic credits are topped up. Everything was built cold (deploy_427..429);
# this script is the ONLY thing that consumes tokens, and only when run with --go.
#
# WHY THE ORDER MATTERS:
#   The cost-metering bridge (scripts/anthropic_spend_bridge.py) must be live FIRST,
#   or the synthetic loops burn invisibly again — the exact failure that drained the
#   balance and took Leo/Telegram down. Bridge first → loops second → verify the cap
#   actually sees the burn.
#
# USAGE (run on the VPS, from /root/landtek):
#   ./scripts/activate_stack.sh            # DRY RUN — prints the plan, changes nothing
#   ./scripts/activate_stack.sh --go       # execute (bridge + truth-loop + fullstack-loop)
#   ./scripts/activate_stack.sh --go --with-sim   # ALSO re-enable leo-simulator (the big burner)
#
# The simulator is OPT-IN: it cost ~$47/day (the outage) and earned ~1 verified
# improvement per 1,744 probes. Decide (MASTER_PLAN §7) before adding --with-sim;
# consider widening its cycle / lowering LANDTEK_DAILY_LLM_CAP first.
set -uo pipefail
REPO=/root/landtek
GO=0; WITH_SIM=0
for a in "$@"; do
  [ "$a" = "--go" ] && GO=1
  [ "$a" = "--with-sim" ] && WITH_SIM=1
done
hdr() { echo; echo "━━━ $* ━━━"; }
run() { echo "  \$ $*"; if [ "$GO" = "1" ]; then eval "$*" || echo "  ! command returned non-zero (continuing)"; fi; }
[ "$GO" = "1" ] || echo "### DRY RUN — no changes made. Re-run with --go to execute. ###"

set -a; . "$REPO/.env" 2>/dev/null || true; set +a

hdr "0. Preflight — Anthropic balance must NOT be depleted"
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "  ✗ ANTHROPIC_API_KEY not set in $REPO/.env — set it before activating."; exit 1
fi
if [ "$GO" = "1" ]; then
  resp=$(curl -s https://api.anthropic.com/v1/messages \
    -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" \
    -H "content-type: application/json" \
    -d '{"model":"claude-sonnet-4-5-20250929","max_tokens":1,"messages":[{"role":"user","content":"ok"}]}' 2>/dev/null || true)
  if echo "$resp" | grep -q "credit balance is too low"; then
    echo "  ✗ Anthropic balance is STILL depleted — top up at console.anthropic.com (Plans & Billing) first. Aborting."
    exit 1
  fi
  echo "  ✓ Anthropic balance OK"
else
  echo "  (would probe the API with a 1-token call; abort if the balance is still too low)"
fi

hdr "1. Cost-metering bridge FIRST (so loops cannot burn invisibly)"
run "cp $REPO/systemd/landtek-spend-bridge.service $REPO/systemd/landtek-spend-bridge.timer /etc/systemd/system/"
run "systemctl daemon-reload"
run "systemctl enable --now landtek-spend-bridge.timer"
run "python3 $REPO/scripts/anthropic_spend_bridge.py"   # seed cursor + first sweep

hdr "2. Re-enable the metered loops (smaller burners; cap now sees them)"
for u in landtek-truth-loop landtek-fullstack-loop; do
  run "systemctl enable --now $u"
done

hdr "2b. Simulator (the big burner) — opt-in only"
if [ "$WITH_SIM" = "1" ]; then
  echo "  --with-sim set: re-enabling leo-simulator. The cap (LANDTEK_DAILY_LLM_CAP=\${LANDTEK_DAILY_LLM_CAP:-8}) will now STOP it once reached."
  run "systemctl enable --now leo-simulator"
else
  echo "  leo-simulator LEFT OFF (no --with-sim). This is deliberate — review its ROI/cadence first (MASTER_PLAN §7)."
fi

hdr "3. Verify"
echo "  Service states:"
run "systemctl is-active landtek-spend-bridge.timer landtek-truth-loop landtek-fullstack-loop leo-simulator 2>/dev/null"
echo "  Recorded spend by source (should show n8n once the bridge has swept):"
run "python3 -c \"import sys; sys.path.insert(0,'$REPO/scripts'); import cost_governor as cg; print(cg.today_spend_by_source(), 'cap=\$'+str(cg.DAILY_CAP))\""
echo
echo "  Then, within ~15-30 min, confirm on the cockpit that n8n spend is recorded and the cap is enforcing:"
echo "     https://leo.hayuma.org/ops/spend"
echo "  And that real Leo replies (message @LeoLandTekBot)."
echo
if [ "$GO" = "1" ]; then echo "✓ Activation steps executed — watch /ops/spend."; else echo "### END DRY RUN — nothing was changed. ###"; fi
