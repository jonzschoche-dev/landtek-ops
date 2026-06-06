#!/usr/bin/env python3
"""rapid_fire_simulator.py — burst synthetic Leo inquiries for architecture regression.

Fires a pack of simulator probes in quick succession, grades replies, and
records a session summary. Use after spine / autolink / context deploys.

Usage:
  python3 scripts/rapid_fire_simulator.py --pack architecture
  python3 scripts/rapid_fire_simulator.py --pack architecture --burst 12 --interval 4
  python3 scripts/rapid_fire_simulator.py --probe arch.arta_0747_not_cv26360
  python3 scripts/rapid_fire_simulator.py --pack architecture --json
  python3 scripts/rapid_fire_simulator.py --list-packs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from simulator_core import (  # noqa: E402
    connect,
    fetch_pack_probes,
    health_ok,
    pick_probe,
    run_one_probe,
)

DEFAULT_PACK = "architecture"
DEFAULT_BURST = 12
DEFAULT_INTERVAL = 4


def start_session(cur, pack: str, burst: int) -> int:
    cur.execute(
        """
        INSERT INTO simulator_sessions (pack, burst_size, status)
        VALUES (%s, %s, 'running')
        RETURNING id
        """,
        (pack, burst),
    )
    return cur.fetchone()["id"]


def finish_session(cur, session_id: int, passed: int, failed: int, results: list[dict]):
    cur.execute(
        """
        UPDATE simulator_sessions
           SET completed_at = now(),
               status = 'done',
               passed = %s,
               failed = %s,
               details = %s::jsonb
         WHERE id = %s
        """,
        (passed, failed, json.dumps(results), session_id),
    )


def main():
    ap = argparse.ArgumentParser(description="Rapid-fire Leo architecture simulator")
    ap.add_argument("--pack", default=DEFAULT_PACK, help="probe pack (architecture, all)")
    ap.add_argument("--burst", type=int, default=DEFAULT_BURST, help="max probes this session")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="seconds between probes")
    ap.add_argument("--probe", help="run one named probe only")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-packs", action="store_true")
    ap.add_argument("--skip-health", action="store_true")
    args = ap.parse_args()

    conn, cur = connect()
    try:
        if args.list_packs:
            cur.execute("""
                SELECT COALESCE(definition->>'pack', 'legacy') AS pack, COUNT(*) AS n
                  FROM leo_qa_probes
                 WHERE rail = 'sim' AND active = true
                 GROUP BY 1 ORDER BY 1
            """)
            rows = cur.fetchall()
            if args.json:
                print(json.dumps(rows, default=str, indent=2))
            else:
                for r in rows:
                    print(f"  {r['pack']}: {r['n']} probes")
            return

        if not args.skip_health and not health_ok(cur):
            print("Leo health check failed (>50% errors in last 15m) — aborting burst")
            sys.exit(2)

        if args.probe:
            probe = pick_probe(cur, name=args.probe)
            if not probe:
                print(f"Probe not found: {args.probe}")
                sys.exit(1)
            session_id = start_session(cur, args.pack, 1)
            result = run_one_probe(cur, probe, session_id=session_id)
            finish_session(cur, session_id, int(result["passed"]), int(not result["passed"]), [result])
            if args.json:
                print(json.dumps({"session_id": session_id, "results": [result]}, indent=2))
            else:
                status = "PASS" if result["passed"] else "FAIL"
                print(f"[{status}] {result['probe']}  {result['fail_reason'] or ''}")
            sys.exit(0 if result["passed"] else 1)

        probes = fetch_pack_probes(cur, args.pack, limit=args.burst)
        if not probes:
            print(f"No probes for pack={args.pack!r}")
            sys.exit(1)

        session_id = start_session(cur, args.pack, len(probes))
        results = []
        passed = failed = 0

        print(f"# rapid-fire session {session_id}  pack={args.pack}  n={len(probes)}")
        for i, probe in enumerate(probes, 1):
            t0 = time.time()
            try:
                result = run_one_probe(cur, probe, session_id=session_id)
            except Exception as e:
                result = {"probe": probe["name"], "passed": False, "fail_reason": str(e), "reply_excerpt": ""}
            results.append(result)
            if result["passed"]:
                passed += 1
                mark = "PASS"
            else:
                failed += 1
                mark = "FAIL"
            if not args.json:
                print(f"  [{i}/{len(probes)}] {mark}  {result['probe']}  {result.get('fail_reason') or ''}")
            elapsed = time.time() - t0
            if i < len(probes):
                sleep_for = max(args.interval - elapsed, 0.5)
                time.sleep(sleep_for)

        finish_session(cur, session_id, passed, failed, results)
        summary = {
            "session_id": session_id,
            "pack": args.pack,
            "total": len(probes),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(probes), 3) if probes else 0,
            "results": results,
        }
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"\n# session {session_id} done: {passed}/{len(probes)} passed")
        sys.exit(0 if failed == 0 else 1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()