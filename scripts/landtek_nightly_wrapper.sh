#!/usr/bin/env bash
# landtek_nightly_wrapper.sh — nightly truth_tests + n8n health check.
# Replaces landtek-truth-tests-wrapper.sh (deploy_246) with a runner that
# also catches silent n8n execution failures (deploy_265 lesson).
#
# Writes any failure to notifications/pending.txt so the session-start hook
# surfaces it next time Jonathan opens a session.
#
# A62 policy (deploy_917/919):
#   - encrypted-cloud OFFSITE tier is report-only inside test_survivable_record until operational
#   - required off-box Mac receipt stays a HARD gate (suite fails if stale) — fix the puller, don't skip
#   - LANDTEK_SKIP_TRUTH_FILES mechanism remains in run_all.py for deliberate ops use; nightly does NOT
#     default-skip A62 (deploy_918 over-carve-out reverted in 919)

set -u
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cd /root/landtek
mkdir -p /root/landtek/notifications /var/log/landtek

echo ""
echo "=== landtek nightly run $TS ==="

OVERALL_RC=0

# 1. truth_tests — full suite; A62 optional cloud is report-only in-test; required legs fail the unit
echo "[$TS] running truth_tests/run_all.py"
if python3 truth_tests/run_all.py >>/var/log/landtek/truth_tests.log 2>&1; then
    echo "[$TS] truth_tests PASSED" >> /var/log/landtek/truth_tests.log
else
    rc=$?
    echo "[$TS] truth_tests FAILED rc=$rc" >> /var/log/landtek/truth_tests.log
    {
        echo "[$TS] nightly: truth_tests FAILED — tail /var/log/landtek/truth_tests.log"
    } >> /root/landtek/notifications/pending.txt
    OVERALL_RC=$rc
fi

# 1.5 incorporation status — governed visibility (Phase 3): daily snapshot + trend log.
#     (A41 consistency of the view is asserted by step 1 above: test_incorporation_view_consistency.)
echo "[$TS] incorporation status:"
python3 scripts/incorporation_status.py --log 2>&1 | sed 's/^/  /' \
    | tee -a /var/log/landtek/incorporation.log || true
# 1.6 rollout guard (Phase 5): alert if connected count fell below the high-water mark (a signal un-set).
if ! python3 scripts/incorporation_status.py --check-regression >>/var/log/landtek/incorporation.log 2>&1; then
    echo "[$TS] nightly: incorporation REGRESSION — connected count fell below high-water; see /var/log/landtek/incorporation.log" \
        >> /root/landtek/notifications/pending.txt
    OVERALL_RC=1
fi

# 1.7 offline-sovereignty regression (A53): a NEW hard external dependency, or the local reasoning
#      substrate (embedded law / local doc text) eroded. Transient Ollama is operational, not gated.
if ! python3 scripts/offline_audit.py --check >>/var/log/landtek/offline_audit.log 2>&1; then
    echo "[$TS] nightly: OFFLINE-CAPABILITY REGRESSION (A53) — the stack may no longer reason unplugged; see /var/log/landtek/offline_audit.log" \
        >> /root/landtek/notifications/pending.txt
    OVERALL_RC=1
fi

# 2. n8n execution health
echo "[$TS] running scripts/monitor_n8n_executions.py"
if python3 scripts/monitor_n8n_executions.py >>/var/log/landtek/n8n_health.log 2>&1; then
    echo "[$TS] n8n_health OK" >> /var/log/landtek/n8n_health.log
else
    rc=$?
    echo "[$TS] n8n_health ALERT rc=$rc" >> /var/log/landtek/n8n_health.log
    # monitor_n8n_executions.py already wrote to notifications/pending.txt
    OVERALL_RC=$rc
fi

# 3. supervision (A59/A61): keep the enumerable fleet roster current, then surface any stalled work
#    order past its review horizon (A59 "finishes-or-surfaces"). Both idempotent + fail-soft.
echo "[$TS] running scripts/fleet_registry.py --sync"
python3 scripts/fleet_registry.py --sync >>/var/log/landtek/supervision.log 2>&1 || true
echo "[$TS] running scripts/supervisor_sentinel.py"
python3 scripts/supervisor_sentinel.py >>/var/log/landtek/supervision.log 2>&1 || true

exit $OVERALL_RC
