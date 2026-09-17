#!/usr/bin/env python3
"""loop_liveness.py — the reconciler that watches the watchers ($0, deterministic).

The failure this exists to prevent: on 2026-07-20 `meta_pulse` — a loop MASTER_PLAN
called "daily 03:30 LIVE" — was found to have NEVER run on the VPS for 8 days. Its
script + units were untracked/Mac-local and never pushed; `systemctl list-timers`
showed the timer `not-found`. Nothing noticed, because `agents.py --health` only
checks the handful of timers in its on-demand TOOL catalog and does NOT cover the
self-improving loops, and it checks last-`Result` but never RECENCY (a timer that
never fires looks fine).

This loop closes that hole. It holds a DECLARED registry of the critical loops that
MUST be alive (below), reads the LIVE host state (`systemctl`), and for each loop
asserts: the timer unit EXISTS, is enabled, is active, its last run did not FAIL, and
it fired within cadence×STALE_FACTOR. Any loop that fails an assertion becomes an open
`holes_findings` row — which `meta_pulse` then promotes into the system-evolution
decision queue and AUTO-CLOSES once this reconciler marks it healthy again. A dead loop
needs a human to reinstall/enable it (it will NOT self-heal), so these are DECIDE gaps
(no `recheck_condition` → meta_pulse leaves them auto_resolvable=false).

It calls NO model. It is the [[feedback-simulator-anti-trap-doctrine]] shape: measure
live state mechanically, surface drift, decide nothing.

  python3 scripts/loop_liveness.py          # scan live host, write/close findings (run on VPS)
  python3 scripts/loop_liveness.py --dry     # report only, write nothing
  python3 scripts/loop_liveness.py --report  # alias for --dry

Registry note (honest smell): this is a SECOND registry alongside `agents.py` AGENTS.
They serve different concerns (liveness-contract-with-parseable-cadence vs on-demand
tool catalog) and agents.py's free-text cadence isn't machine-parseable — but keep them
from drifting. The UNREGISTERED-timer report below is the drift tripwire.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ROUTINE = "loop_liveness"
ROUTINE_VERSION = "v1"
NOTIF_PATH = "/var/log/landtek_loop_liveness.log"

# A loop is STALE when it hasn't fired for cadence_hours * STALE_FACTOR.
STALE_FACTOR = 3.0

# ── The liveness contract: the critical loops that MUST be alive on the VPS. ──────
# key, timer unit, cadence_hours, one-line purpose.  Add a loop here the moment you
# wire its timer — an entry with no live unit is exactly the meta_pulse failure class.
CRITICAL_LOOPS = [
    # ── self-improving / self-auditing loops ────────────────────────────────────
    ("awareness",        "landtek-awareness.timer",              1.0,  "accretes grounded facts + knowledge_coverage meter"),
    ("meta_agent",       "meta-agent.timer",                     1.0,  "~20 SQL invariants → gap inquiry queue"),
    ("meta_pulse",       "landtek-meta-pulse.timer",            24.0,  "$0 delta gap ledger + self-heal auto-close"),
    ("improvement_agent","improvement-agent.timer",             24.0,  "code/system audit → top leverage moves"),
    ("agent_stack_sim",  "landtek-agent-sim.timer",              6.0,  "grounded agent-stack probe/drain + mechanical grade"),
    # ── truth / knowledge hardening loops ───────────────────────────────────────
    ("verify_loop",      "landtek-verify.timer",                24.0,  "nightly scout: enqueue+rank+measure verifiable corpus"),
    ("verify_worker",    "landtek-verify-worker.timer",          0.25, "continuous grounded read → verified cited facts"),
    ("ontology_check",   "landtek-ontology-check.timer",        24.0,  "whole-corpus ontology/isolation sentinel"),
    ("cross_client",     "landtek-cross-client.timer",          24.0,  "cross-client anti-conflation self-heal"),
    ("corpus_steward",   "landtek-corpus-steward.timer",         6.0,  "keep every matter's case file complete/current"),
    ("supervisor",       "landtek-supervisor.timer",             0.5,  "advance work_orders one fail-closed step"),
    ("jurisprudence",    "landtek-jurisprudence-steward.timer",168.0,  "keep the shared case-law library current"),
    # ── the watcher itself (so its own death is a finding, surfaced by the digest) ─
    ("loop_liveness",    "landtek-loop-liveness.timer",          1.0,  "this reconciler — watches the watchers"),
]
DECLARED_UNITS = {u for _, u, _, _ in CRITICAL_LOOPS}


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _hash(key):
    return hashlib.sha256(f"dead-loop-{key}".encode()).hexdigest()[:32]


def _notify(msg):
    try:
        os.makedirs(os.path.dirname(NOTIF_PATH), exist_ok=True)
        with open(NOTIF_PATH, "a") as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {ROUTINE}: {msg}\n")
    except Exception:
        pass  # surfacing must never crash the sentinel


def _last_trigger_age_hours(unit):
    """Hours since the timer last fired, or None if it has never fired / is unknown.
    LastTriggerUSec is 0 (rendered 'n/a'/empty) for a freshly-installed timer that
    hasn't reached its first OnCalendar yet — we do NOT flag that as stale."""
    usec = _sh(f"systemctl show {unit} -p LastTriggerUSecMonotonic --value 2>/dev/null")
    # Monotonic 0 means never triggered this boot; fall back to the realtime stamp.
    stamp = _sh(f"systemctl show {unit} -p LastTriggerUSec --value 2>/dev/null")
    if not stamp or usec == "0":
        return None
    # stamp like "Mon 2026-07-21 03:30:00 UTC"; parse leniently.
    m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", stamp)
    if not m:
        return None
    try:
        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0


def assess(unit, cadence_h):
    """Return (verdict, severity, detail_bits) for one declared loop from live host state.
    verdict ∈ {'ok','missing','disabled','inactive','failed','stale'}."""
    enabled = _sh(f"systemctl is-enabled {unit} 2>/dev/null")   # enabled|disabled|static|not-found|''
    active = _sh(f"systemctl is-active {unit} 2>/dev/null")     # active|inactive|failed|''
    svc = unit.replace(".timer", ".service")
    result = _sh(f"systemctl show {svc} -p Result --value 2>/dev/null") or "-"
    age = _last_trigger_age_hours(unit)
    bits = {"enabled": enabled or "?", "active": active or "?", "last_result": result,
            "age_hours": round(age, 2) if age is not None else None,
            "cadence_hours": cadence_h}

    # MISSING is the meta_pulse class: the unit does not exist on the host at all.
    if enabled in ("", "not-found"):
        return "missing", "high", bits
    if enabled == "disabled":
        return "disabled", "high", bits
    if active not in ("active", "activating", "waiting", "listening") and active:
        # a healthy .timer sits 'active (waiting)'; 'inactive'/'failed' means not armed
        return "inactive", "high", bits
    if result not in ("success", "-"):
        return "failed", "high", bits
    if age is not None and age > cadence_h * STALE_FACTOR:
        sev = "high" if age > cadence_h * 6 else "warn"
        return "stale", sev, bits
    return "ok", "info", bits


REMEDY = {
    "missing":  "unit absent — install /etc/systemd/system/{u} then: systemctl daemon-reload && systemctl enable --now {u}",
    "disabled": "systemctl enable --now {u}",
    "inactive": "systemctl start {u}  (and check: systemctl status {u})",
    "failed":   "journalctl -u {svc} -n 50  — fix the cause, then: systemctl start {u}",
    "stale":    "timer armed but overdue — check OnCalendar + last run: systemctl status {svc}; journalctl -u {svc} -n 50",
}


def scan(dry=False):
    if not shutil.which("systemctl"):
        print(f"[{ROUTINE}] systemctl not available (not the VPS host) — nothing to assess, exiting clean.")
        return 0

    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    findings, healthy = [], []
    for key, unit, cad, note in CRITICAL_LOOPS:
        verdict, sev, bits = assess(unit, cad)
        if verdict == "ok":
            healthy.append((key, unit, bits))
        else:
            findings.append((key, unit, cad, note, verdict, sev, bits))

    # 1) Auto-close: any open finding whose loop is healthy again (self-healing signal
    #    for meta_pulse, which then closes the promoted system_evolution_log gap).
    closed = 0
    if not dry and healthy:
        for key, unit, _bits in healthy:
            cur.execute(
                "UPDATE holes_findings SET status='remediated', remediated_at=now(), "
                "remediated_via='loop_healthy' "
                "WHERE routine_name=%s AND status='open' AND finding_id_hash=%s",
                (ROUTINE, _hash(key)))
            closed += cur.rowcount

    # 2) Surface each unhealthy loop (dedup: one open finding per loop key).
    surfaced = 0
    for key, unit, cad, note, verdict, sev, bits in findings:
        svc = unit.replace(".timer", ".service")
        detail = (f"CRITICAL LOOP '{key}' ({note}) is {verdict.upper()}: {unit} "
                  f"enabled={bits['enabled']} active={bits['active']} last_result={bits['last_result']} "
                  f"last_fired={bits['age_hours']}h ago (cadence {cad}h).")
        fix = REMEDY.get(verdict, "investigate").format(u=unit, svc=svc)
        if dry:
            print(f"  WOULD SURFACE [{sev}] {detail}\n      fix: {fix}")
            continue
        fid = _hash(key)
        cur.execute("SELECT 1 FROM holes_findings WHERE finding_id_hash=%s AND status='open'", (fid,))
        if cur.fetchone():
            continue  # already open — leave it (stable id → stable meta_pulse gap)
        cur.execute(
            """INSERT INTO holes_findings
                 (routine_name, routine_version, finding_id_hash, severity, hole_type,
                  description, suggested_fix, fix_command, auto_remediable, metadata, status)
               VALUES (%s,%s,%s,%s,'dead_loop',%s,%s,%s,false,%s,'open')""",
            (ROUTINE, ROUTINE_VERSION, fid, sev, detail, fix, fix,
             json.dumps({"loop": key, "unit": unit, "verdict": verdict, **bits})))
        _notify(detail)
        surfaced += 1

    # 3) Drift tripwire (report-only, no findings): enabled landtek/leo timers that are
    #    NOT in the declared contract — a new loop nobody registered, or a rename.
    raw = _sh("systemctl list-timers --all --no-legend 2>/dev/null")
    live_units = {p for l in raw.splitlines() for p in l.split() if p.endswith(".timer")}
    live_landtek = {u for u in live_units if re.search(r"landtek|leo|meta-agent|improvement-agent", u)}
    unregistered = sorted(u for u in live_landtek if u not in DECLARED_UNITS
                          and _sh(f"systemctl is-enabled {u} 2>/dev/null") == "enabled")

    # ── report ──────────────────────────────────────────────────────────────────
    print("=" * 78)
    print(f"LOOP LIVENESS  ({len(CRITICAL_LOOPS)} declared critical loops)")
    print("=" * 78)
    for key, unit, bits in healthy:
        print(f"  ✓ {key:18} {unit:38} last={bits['last_result']} age={bits['age_hours']}h")
    for key, unit, cad, note, verdict, sev, bits in findings:
        print(f"  ✗ {key:18} {unit:38} {verdict.upper()} [{sev}] "
              f"enabled={bits['enabled']} active={bits['active']} last={bits['last_result']}")
    if unregistered:
        print(f"\n  ⚠ {len(unregistered)} enabled timer(s) NOT in the liveness contract "
              f"(register or retire): {', '.join(unregistered)}")
    verb = "would surface" if dry else "surfaced_new"
    print(f"\n[{ROUTINE}] declared={len(CRITICAL_LOOPS)} healthy={len(healthy)} "
          f"unhealthy={len(findings)} {verb}={surfaced} auto_closed={closed} "
          f"unregistered={len(unregistered)}" + (" (dry-run)" if dry else ""))

    cur.close(); conn.close()
    return 1 if findings else 0


if __name__ == "__main__":
    dry = "--dry" in sys.argv or "--report" in sys.argv
    sys.exit(scan(dry=dry))
