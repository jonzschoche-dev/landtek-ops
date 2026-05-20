#!/usr/bin/env python3
"""run_all.py — Run every truth_tests/test_*.py and aggregate results.

Wired into landtek_git_routine.sh deploy and nightly cron.
Exit code 0 only if ALL assertions pass.
"""
import importlib
import os
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, "/root/landtek")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    test_files = sorted(p.stem for p in TESTS_DIR.glob("test_*.py"))
    print("=" * 60)
    print(f"truth_tests suite — {len(test_files)} test files")
    print("=" * 60)

    total_passed = 0
    total_failed = 0
    failed_details = []

    for tf in test_files:
        print(f"\n[{tf}]")
        try:
            mod = importlib.import_module(tf)
        except Exception as e:
            print(f"  ✗ IMPORT FAILED: {type(e).__name__}: {e}")
            total_failed += 1
            failed_details.append((tf, "import-failed", str(e)))
            continue

        if not hasattr(mod, "TESTS"):
            print(f"  ⚠ no TESTS list in {tf}.py — skipping")
            continue

        from _harness import run as run_tests
        passed, failed = run_tests(mod.TESTS)
        total_passed += len(passed)
        total_failed += len(failed)
        for label, err in failed:
            failed_details.append((tf, label, err))

    print()
    print("=" * 60)
    if total_failed:
        print(f"✗ truth_tests FAILED: {total_passed} passed, {total_failed} failed")
        print()
        print("Failures:")
        for tf, label, err in failed_details:
            print(f"  - [{tf}] {label}: {err}")
        sys.exit(1)
    else:
        print(f"✓ truth_tests: {total_passed} assertions passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
