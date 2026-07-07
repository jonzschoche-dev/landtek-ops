#!/usr/bin/env bash
# landtek_nightly_wrapper.sh — nightly truth_tests + n8n health check.
# Replaces landtek-truth-tests-wrapper.sh (deploy_246) with a runner that
# also catches silent n8n execution failures (deploy_265 lesson).
#
# Writes any failure to notifications/pending.txt so the session-start hook
# surfaces it next time Jonathan opens a session.

set -u
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
cd /root/landtek
mkdir -p /root/landtek/notifications /var/log/landtek

echo ""
echo "=== landtek nightly run $TS ==="

OVERALL_RC=0

# 1. truth_tests
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

exit $OVERALL_RC
