"""holes.a1_tn_regression — Truth-Negotiator daily regression.

Runs every active back_test_suite case through truth_negotiator.negotiate(),
mirrors systems_analyzer's pass logic, emits one finding per FAILING test plus
a P0 if pass rate drops below baseline (4 of 5).

This sits ALONGSIDE systems_analyzer.run_backtests() which runs hourly and writes
to `back_test_runs`. The difference: this routine writes to `holes_findings` with
verbose per-test detail, so the daily Holes Report carries calibration signal
without you having to dig through back_test_runs manually.

Baseline pass rate (Phase 1.1 target): ≥4 of 5.
"""
import sys

from holes.base import Routine, run_cli, LANDTEK_ROOT

# Baseline target — drop below this is a P0 regression
PASS_RATE_BASELINE = 4


class A1_TNRegression(Routine):
    name = "A1_tn_regression"
    version = "v1"
    hole_type = "truth_gap"
    cadence = "daily"
    severity_default = "P1"
    description = "Truth-Negotiator daily regression: runs back_test_suite, emits per-failure + regression P0."

    def find_holes(self, cur):
        # Make sure ANTHROPIC_API_KEY is loaded for challenger calls
        sys.path.insert(0, LANDTEK_ROOT)
        from truth_negotiator import negotiate

        cur.execute("SELECT * FROM back_test_suite WHERE active ORDER BY id")
        tests = cur.fetchall()
        if not tests:
            self.emit(
                severity="P1",
                description="back_test_suite has no active tests — regression detector is blind.",
                suggested_fix="Re-run migrations/apply_deploy_120_analyzer_schema.py to reseed.",
            )
            return

        passes = 0
        failures = []
        for t in tests:
            try:
                r = negotiate(t["claim"], case_file=t["case_file"], asked_by="A1_regression")
            except Exception as e:
                failures.append((t, f"negotiate() raised: {e}", None))
                continue

            actual = r["verdict"]
            expected = t["expected_verdict"]
            fact_backers = list(r.get("fact_backers") or [])
            top10 = fact_backers[:10]
            verdict_match = actual == expected
            doc_match = True
            if verdict_match and t.get("expected_doc_ids"):
                if not set(t["expected_doc_ids"]) & set(top10):
                    doc_match = False
            passed = verdict_match and doc_match

            if passed:
                passes += 1
            else:
                if not verdict_match:
                    reason = f"expected verdict={expected} but got {actual}"
                else:
                    missing = [d for d in t["expected_doc_ids"] if d not in top10]
                    reason = f"verdict OK but expected docs {missing} missing from top-10 (ranking issue)"
                failures.append((t, reason, r))

        # Per-test failure findings
        for t, reason, r in failures:
            severity = "P1"
            challenger_reason = (r.get("challenger_reason") or "")[:300] if r else ""
            top10_summary = ",".join(str(d) for d in (r.get("fact_backers") if r else [])[:10]) or "(none)"
            self.emit(
                severity=severity,
                description=f"Back-test '{t['test_name']}' FAILED: {reason}",
                case_file=t.get("case_file"),
                suggested_fix=(
                    "Run `python3 back_test_diagnostic.py --test " + t["test_name"] +
                    "` for full evidence trace + ranking detail."
                ),
                metadata={
                    "test_id": t["id"],
                    "test_name": t["test_name"],
                    "claim": t["claim"],
                    "expected_verdict": t.get("expected_verdict"),
                    "actual_verdict": r["verdict"] if r else None,
                    "challenger_reason": challenger_reason,
                    "top10_fact_backers": top10_summary,
                    "expected_doc_ids": list(t.get("expected_doc_ids") or []),
                },
                hash_parts={"test_name": t["test_name"]},  # one open finding per test
            )

        # Regression P0 if below baseline
        if passes < PASS_RATE_BASELINE:
            self.emit(
                severity="P0",
                description=(
                    f"TN regression: only {passes}/{len(tests)} back-tests passing "
                    f"(baseline ≥{PASS_RATE_BASELINE}). Intelligence quality gate is open."
                ),
                suggested_fix=(
                    "Review per-test findings above. Calibrate challenger prompt or ranking. "
                    "See Phase 1.1 in LEO_MASTER_PLAN.md."
                ),
                metadata={"pass_count": passes, "total": len(tests), "baseline": PASS_RATE_BASELINE},
                hash_parts={"regression_below_baseline": True, "pass_count": passes},
            )


if __name__ == "__main__":
    run_cli(A1_TNRegression)
