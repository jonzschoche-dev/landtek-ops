"""holes/dispatcher.py — cadence-aware single entry point.

Run me from a single systemd timer (every 15min). I inspect each registered
routine's cadence and the last successful run in holes_runs; if a routine is
due, I run it.

Cadences and minimum gaps:
  every_4h           → 4h
  every_6h           → 6h
  daily              → 24h, prefers 06:00 PHT window
  weekly             → 7d, prefers Mondays
  session_boundary   → triggered separately, NOT by dispatcher
  on_demand          → never by dispatcher

Usage:
  python3 -m holes.dispatcher               # run any routine that's due
  python3 -m holes.dispatcher --routine A2  # force-run one routine
  python3 -m holes.dispatcher --list        # show registry + last-run times
"""
import argparse
import importlib
import json
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import psycopg2
import psycopg2.extras

from holes.base import DSN, VALID_CADENCES

# ─────────────────────────────────────────────────────────────────────────
# Routine registry. Adding a new routine = adding an import + a row here.
# Each entry: (module_path, class_name)
# ─────────────────────────────────────────────────────────────────────────
REGISTRY = [
    ("holes.a1_tn_regression",     "A1_TNRegression"),
    ("holes.a2_self_research",     "A2_SelfResearch"),
    ("holes.a3_hallucination_canary", "A3_HallucinationCanary"),
    ("holes.b1_matter_readiness",  "B1_MatterReadiness"),
    ("holes.b2_expected_evidence", "B2_ExpectedEvidence"),
    ("holes.b3_stage_claim_backtest", "B3_StageClaimBacktest"),
    ("holes.b4_untouched_entities", "B4_UntouchedEntities"),
    ("holes.c1_provenance_drift",  "C1_ProvenanceDrift"),
    ("holes.c2_ops_language_leak", "C2_OpsLanguageLeak"),
    ("holes.c3_simulator_regression", "C3_SimulatorRegression"),
    ("holes.d1_schema_drift",      "D1_SchemaDrift"),
    ("holes.d2_memory_contradiction", "D2_MemoryContradiction"),
    ("holes.d3_dead_script",       "D3_DeadScript"),
    ("holes.e1_capacity_health",   "E1_CapacityHealth"),
    ("holes.e2_state_divergence",  "E2_StateDivergence"),
]

CADENCE_GAP = {
    "every_4h": timedelta(hours=4),
    "every_6h": timedelta(hours=6),
    "daily":    timedelta(hours=20),  # slight slack so 06:00 daily still fires reliably
    "weekly":   timedelta(days=6, hours=12),
}


def _load_routines():
    """Import and instantiate every registered routine. Tolerates missing modules so
    you can ship the dispatcher before every routine is built (just logs which are
    missing — they're treated as 'not registered yet')."""
    routines = []
    missing = []
    for mod_path, cls_name in REGISTRY:
        try:
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            routines.append(cls())
        except (ImportError, AttributeError) as e:
            missing.append((mod_path, cls_name, str(e)))
    return routines, missing


def _last_ok_run(cur, routine_name: str) -> Optional[datetime]:
    cur.execute("""
        SELECT run_at FROM holes_runs
         WHERE routine_name=%s AND status='ok'
         ORDER BY run_at DESC LIMIT 1
    """, (routine_name,))
    row = cur.fetchone()
    return row["run_at"] if row else None


def _is_due(cadence: str, last_ok: Optional[datetime]) -> bool:
    if cadence in ("session_boundary", "on_demand"):
        return False
    if last_ok is None:
        return True
    gap = CADENCE_GAP.get(cadence)
    if not gap:
        return False
    return (datetime.now(timezone.utc) - last_ok) >= gap


def list_registry():
    routines, missing = _load_routines()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    print(f"{'name':<32}{'kind':<12}{'cadence':<14}{'last_ok':<24}{'due?':<6}")
    print("-" * 88)
    for r in routines:
        last = _last_ok_run(cur, r.name)
        last_s = last.strftime("%Y-%m-%d %H:%M UTC") if last else "(never)"
        if r.kind == "cc_session":
            due = "[CC]"
        else:
            due = "YES" if _is_due(r.cadence, last) else "no"
        print(f"{r.name:<32}{r.kind:<12}{r.cadence:<14}{last_s:<24}{due:<6}")
    cur.close(); conn.close()
    if missing:
        print()
        print("Missing (not yet built):")
        for mp, cn, err in missing:
            print(f"  - {mp}::{cn}  [{err[:60]}]")


def dispatch(force_routine: Optional[str] = None, auto_remediate: bool = False) -> dict:
    """Run all due routines. Returns aggregate result."""
    routines, missing = _load_routines()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    run_results = []
    for r in routines:
        if force_routine and r.name != force_routine and not r.name.startswith(force_routine):
            continue
        # CC-session routines have their own systemd timer firing `claude -p < prompt_file`;
        # the Python dispatcher leaves them alone (but lists them in --list for unified view).
        if r.kind == "cc_session":
            continue
        if not force_routine:
            last = _last_ok_run(cur, r.name)
            if not _is_due(r.cadence, last):
                continue
        if getattr(r, "version", "").startswith("v0-stub"):
            continue
        print(f"→ {r.name} ({r.cadence})", flush=True)
        try:
            result = r.run(auto_remediate=auto_remediate)
        except NotImplementedError as e:
            result = {"routine": r.name, "status": "skipped", "error": str(e)[:200]}
        except Exception as e:
            result = {"routine": r.name, "status": "failed", "error": f"{type(e).__name__}: {e}"[:300]}
        run_results.append(result)

    cur.close(); conn.close()
    return {
        "ran": len(run_results),
        "missing_routines": len(missing),
        "results": run_results,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show registry + last-run state")
    ap.add_argument("--routine", help="force-run a specific routine (matches name prefix)")
    ap.add_argument("--auto", action="store_true", help="auto-remediate eligible findings")
    ap.add_argument("--json", action="store_true", help="output result as JSON")
    args = ap.parse_args()
    if args.list:
        list_registry()
        return
    result = dispatch(force_routine=args.routine, auto_remediate=args.auto)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n✓ dispatcher: ran {result['ran']} routine(s)")
        for r in result["results"]:
            print(f"  - {r.get('routine','?')}: {r.get('status','?')} "
                  f"({r.get('findings_persisted',0)} findings, {r.get('p0_count',0)} P0)")


if __name__ == "__main__":
    main()
