#!/usr/bin/env python3
"""refresh_all.py — ONE orchestrator for the cockpit/objective refreshers.

Replaces 8 separate cron spawns (each a cold `python3` start every 5–10 min) with two tiered, in-process
runs. Every member is import-safe (guarded `main()`, no LLM), so this imports each module and calls its
`main()` in a single process — sharing the interpreter and the already-loaded `.env`. A failure in one
member is isolated and logged; it never aborts the rest. $0 (no model calls).

  scripts/refresh_all.py --tier hot     # ~every 5 min  — realtime flow + objectives
  scripts/refresh_all.py --tier warm    # ~every 15 min — evidence facts, client history, mwk pending/priorities, evidence-trail proposals
  scripts/refresh_all.py --tier daily   # once daily    — title facts (stable; no need to re-run often)
  scripts/refresh_all.py --tier all     # run everything once (manual)

Cron (replaces the 8 old refresh_* lines):
  */5  * * * * cd /root/landtek && set -a; . .env; set +a; /usr/bin/python3 scripts/refresh_all.py --tier hot   2>&1
  */15 * * * * cd /root/landtek && set -a; . .env; set +a; /usr/bin/python3 scripts/refresh_all.py --tier warm  2>&1
  0 6  * * * * cd /root/landtek && set -a; . .env; set +a; /usr/bin/python3 scripts/refresh_all.py --tier daily 2>&1
"""
import argparse
import importlib
import os
import sys
import time

TIERS = {
    "hot":   ["refresh_realtime_flow", "refresh_objectives"],
    "warm":  ["refresh_evidence_facts", "refresh_client_history",
              "refresh_mwk_pending_matters", "refresh_mwk_priorities", "apply_evidence_trail_proposals"],
    "daily": ["refresh_title_facts"],
}


def run_member(mod_name):
    t0 = time.time()
    try:
        mod = importlib.import_module(mod_name)
        mod.main()
        return (mod_name, "ok", time.time() - t0, "")
    except SystemExit as e:                       # a member calling sys.exit() must not abort the batch
        code = e.code if e.code is not None else 0
        return (mod_name, "ok" if code == 0 else "ERR", time.time() - t0, f"exit {code}")
    except BaseException as e:                    # isolate everything else (incl. KeyboardInterrupt safety)
        return (mod_name, "ERR", time.time() - t0, f"{type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["hot", "warm", "daily", "all"], default="all")
    a = ap.parse_args()
    members = (TIERS["hot"] + TIERS["warm"] + TIERS["daily"]) if a.tier == "all" else TIERS[a.tier]
    # members live in scripts/ alongside this file
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    results = [run_member(m) for m in members]
    ok = sum(1 for r in results if r[1] == "ok")
    print(f"refresh_all --tier {a.tier}: {ok}/{len(results)} ok")
    for name, status, dt, err in results:
        print(f"  [{status:>3}] {name:32s} {dt:5.1f}s  {err}")
    if any(r[1] == "ERR" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
