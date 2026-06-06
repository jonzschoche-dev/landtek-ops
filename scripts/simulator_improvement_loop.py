#!/usr/bin/env python3
"""simulator_improvement_loop.py — closed loop: fail → fix → re-verify.

A simulator that does not improve the system is waste. This script:
  1. DETECT  — load failed probes from a session (or run a burst first)
  2. REFRESH — run $0 context refresh scripts mapped to each failure
  3. VERIFY  — re-fire only the failed probes against live Leo
  4. REPORT  — before/after pass count; marks holes_findings remediated if improved

Usage:
  python3 scripts/simulator_improvement_loop.py --session 1 --full
  python3 scripts/simulator_improvement_loop.py --probe arch.arta_0747_op_deadline --full
  python3 scripts/simulator_improvement_loop.py --run-burst --full   # burst then loop
  python3 scripts/simulator_improvement_loop.py --detect-only --session 1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from simulator_core import connect, fetch_pack_probes, pick_probe, run_one_probe  # noqa: E402

# $0 safe refreshes — stale context is the most common fixable sim failure.
PROBE_REFRESH_MAP: dict[str, list[str]] = {
    "arch.email_legal_event_policy": ["scripts/refresh_client_history.py"],
    "arch.promo_not_on_spine": ["scripts/refresh_client_history.py"],
    "arch.arta_0747_op_deadline": [
        "scripts/refresh_mwk_pending_matters.py",
        "scripts/refresh_mwk_priorities.py",
    ],
    "arch.pending_matters_arta_op": [
        "scripts/refresh_mwk_pending_matters.py",
        "scripts/refresh_mwk_priorities.py",
    ],
    "arch.del_rosario_1210_may": ["scripts/refresh_mwk_pending_matters.py"],
    "arch.dual_arta_manifestations": ["scripts/refresh_mwk_pending_matters.py"],
    "arch.arta_1210_op_window": ["scripts/refresh_mwk_pending_matters.py"],
    "arch.arta_0747_not_cv26360": ["scripts/refresh_mwk_pending_matters.py"],
    "arch.dilg_not_cv26360": ["scripts/refresh_mwk_pending_matters.py"],
    "arch.gmail_38220_citation": [
        "scripts/refresh_mwk_pending_matters.py",
        "client_history_scan.py",
    ],
    "arch.mediation_impasse_cv26360": ["scripts/refresh_mwk_hard_facts.py"],
    "arch.no_barandon_blocker_0747": ["scripts/refresh_mwk_priorities.py"],
}

DEFAULT_REFRESH = [
    "scripts/refresh_client_history.py",
    "scripts/refresh_mwk_pending_matters.py",
    "scripts/refresh_mwk_hard_facts.py",
    "scripts/refresh_mwk_priorities.py",
    "scripts/refresh_objectives.py",
    "client_history_scan.py",
]


def _run_script(rel_path: str) -> dict:
    path = os.path.join(ROOT, rel_path)
    if not os.path.isfile(path):
        return {"script": rel_path, "ok": False, "error": "missing"}
    t0 = time.time()
    r = subprocess.run(
        [sys.executable, path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "script": rel_path,
        "ok": r.returncode == 0,
        "seconds": round(time.time() - t0, 1),
        "tail": (r.stdout or r.stderr or "")[-200:],
    }


def load_session_failures(cur, session_id: int) -> list[dict]:
    cur.execute(
        """
        SELECT probe_name, fail_reason, passed
          FROM simulator_session_results
         WHERE session_id = %s AND passed = false
         ORDER BY probe_name
        """,
        (session_id,),
    )
    return cur.fetchall()


def latest_session_id(cur) -> int | None:
    cur.execute("""
        SELECT id FROM simulator_sessions
         WHERE status = 'done'
         ORDER BY started_at DESC LIMIT 1
    """)
    r = cur.fetchone()
    return r["id"] if r else None


def refresh_for_probes(probe_names: list[str]) -> list[dict]:
    scripts: list[str] = []
    for name in probe_names:
        scripts.extend(PROBE_REFRESH_MAP.get(name, []))
    if not scripts:
        scripts = DEFAULT_REFRESH
    seen: set[str] = set()
    ordered: list[str] = []
    for s in scripts:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    return [_run_script(s) for s in ordered]


def verify_probes(cur, probe_names: list[str]) -> list[dict]:
    results = []
    for name in probe_names:
        probe = pick_probe(cur, name=name)
        if not probe:
            results.append({"probe": name, "passed": False, "fail_reason": "probe not found"})
            continue
        try:
            results.append(run_one_probe(cur, probe))
        except Exception as e:
            results.append({"probe": name, "passed": False, "fail_reason": str(e)})
        time.sleep(3)
    return results


def mark_remediated(cur, probe_names: list[str], improved: list[str]):
    for name in improved:
        cur.execute(
            """
            UPDATE holes_findings
               SET status = 'remediated',
                   remediated_at = now(),
                   remediated_via = 'simulator_improvement_loop',
                   remediated_by = 'auto_refresh_verify'
             WHERE status = 'open'
               AND metadata->>'probe_name' = %s
            """,
            (name,),
        )


def run_burst(cur, pack: str, burst: int) -> int:
    from rapid_fire_simulator import start_session, finish_session  # noqa: E402

    probes = fetch_pack_probes(cur, pack, limit=burst)
    session_id = start_session(cur, pack, len(probes))
    results = []
    passed = failed = 0
    for probe in probes:
        try:
            r = run_one_probe(cur, probe, session_id=session_id)
        except Exception as e:
            r = {"probe": probe["name"], "passed": False, "fail_reason": str(e)}
        results.append(r)
        if r["passed"]:
            passed += 1
        else:
            failed += 1
        time.sleep(3)
    finish_session(cur, session_id, passed, failed, results)
    return session_id


def main():
    ap = argparse.ArgumentParser(description="Simulator improvement closed loop")
    ap.add_argument("--session", type=int, help="simulator_sessions.id to process")
    ap.add_argument("--probe", action="append", dest="probes", help="specific probe(s)")
    ap.add_argument("--full", action="store_true", help="detect → refresh → verify")
    ap.add_argument("--detect-only", action="store_true")
    ap.add_argument("--refresh-only", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--run-burst", action="store_true", help="run architecture burst first")
    ap.add_argument("--pack", default="architecture")
    ap.add_argument("--burst", type=int, default=12)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    conn, cur = connect()
    try:
        session_id = args.session
        if args.run_burst:
            session_id = run_burst(cur, args.pack, args.burst)
            print(f"# burst session {session_id}")

        fails: list[dict] = []
        if args.probes:
            failed_names = args.probes
        elif session_id:
            fails = load_session_failures(cur, session_id)
            failed_names = [f["probe_name"] for f in fails]
        else:
            session_id = latest_session_id(cur)
            if not session_id:
                print("No completed simulator session found")
                sys.exit(1)
            fails = load_session_failures(cur, session_id)
            failed_names = [f["probe_name"] for f in fails]

        if not failed_names:
            out = {"message": "no failures to improve", "session_id": session_id}
            print(json.dumps(out, indent=2) if args.json else "No failed probes — nothing to improve.")
            return

        report = {
            "session_id": session_id,
            "failed_probes": failed_names,
            "refresh": [],
            "verify_before": fails if session_id and not args.probes else None,
            "verify_after": [],
            "improved": [],
            "still_failing": [],
        }

        if args.detect_only:
            if args.json:
                print(json.dumps(report, indent=2, default=str))
            else:
                print(f"Failed probes ({len(failed_names)}):")
                for n in failed_names:
                    print(f"  - {n}")
            return

        if args.full or args.refresh_only:
            report["refresh"] = refresh_for_probes(failed_names)
            if not args.json:
                print("# refresh ($0 context scripts)")
                for r in report["refresh"]:
                    mark = "ok" if r["ok"] else "FAIL"
                    print(f"  [{mark}] {r['script']} ({r.get('seconds', '?')}s)")

        if args.full or args.verify_only:
            if not args.json:
                print(f"# re-verify {len(failed_names)} probe(s)")
            after = verify_probes(cur, failed_names)
            report["verify_after"] = after
            for r in after:
                if r.get("passed"):
                    report["improved"].append(r["probe"])
                else:
                    report["still_failing"].append(r["probe"])

            if report["improved"]:
                mark_remediated(cur, failed_names, report["improved"])

            try:
                sys.path.insert(0, os.path.join(ROOT, "holes"))
                from holes.c3_simulator_regression import C3_SimulatorRegression

                C3_SimulatorRegression().run()
            except Exception as e:
                report["c3_error"] = str(e)

        if args.json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(
                f"\n# improvement loop: "
                f"improved={len(report['improved'])} "
                f"still_failing={len(report['still_failing'])}"
            )
            if report["still_failing"]:
                print("  Still failing (needs manual context/code fix):")
                for n in report["still_failing"]:
                    print(f"    - {n}")
            if report["improved"]:
                print("  Fixed by refresh+re-verify:")
                for n in report["improved"]:
                    print(f"    + {n}")

        sys.exit(0 if not report.get("still_failing") else 1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()