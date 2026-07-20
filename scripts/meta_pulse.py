#!/usr/bin/env python3
"""meta_pulse.py — the $0, deterministic self-improving loop.

LandTek already RUNS its checks (truth_tests + ontology_check). What it lacked was a
loop that (a) records only what CHANGED since the last run, (b) auto-closes the classes
that self-heal, and (c) routes everything else — and ONLY everything else — to a human.
This is that loop. It calls NO model. Verification is subprocess + DB + regex.

Each cycle, in order:
  1. Run truth_tests/run_all.py            → per-assertion pass/fail.
  2. Run ontology_check.py --invariants
       / --enforcement / --alignment       → the active drift-signal set.
  3. Read holes_findings                    → the open self-recorded-gap id set.
  4. DELTA vs the last run (meta_pulse_state):
       - an assertion that was NOT failing and is now failing  → a NEW gap.
       - an open holes_findings id not seen last run           → a NEW gap.
       - a drift key not present last run                       → a NEW gap.
     Write ONLY new gaps to system_evolution_log. Known gaps are never re-logged.
  5. AUTO-CLOSE: for every still-open evolution row, re-evaluate its machine-checkable
     recheck_condition against the CURRENT signals. If it now passes, close it
     (resolved_via='meta_pulse_recheck') and print the closure. This mirrors the A74
     recheck / reOCR-rearm / V-shadow-soak self-close — the pulse only records it.
  6. Persist the current signal state as the new baseline.

The pulse SENDS nothing and DECIDES nothing. Downstream (or the operator's next
session) reads:  SELECT * FROM system_evolution_log WHERE status='open'
AND auto_resolvable=false  — the only queue that needs a human/Claude decision.

  auto_resolvable = the gap belongs to a class with existing self-healing machinery,
  so it will clear itself and needs no human. Precisely:
    - hole gaps  → TRUE iff the source holes_findings row carries an A74
      metadata.recheck_condition (contradiction/ingest-fidelity holds, doc-owner holds
      — these self-close in their own routines).
    - assertion gaps → FALSE. A red test has a machine-checkable recheck (does it pass
      now?) so the pulse auto-CLOSES it once fixed, but it will NOT self-heal without a
      code fix → a human must see it.
    - drift gaps → FALSE. A broken invariant / phantom-enforcement / dangling ref needs
      a doc-or-code decision; it does not self-clear.
  (So "has a recheck_condition" enables auto-CLOSE for every gap; auto_resolvable is the
  stricter "will self-heal unattended" subset. The two are deliberately separate.)

Usage:
  python3 scripts/meta_pulse.py             # one idempotent cycle (timer entry point)
  python3 scripts/meta_pulse.py --report    # read-only: print the open decision queue, run nothing
  python3 scripts/meta_pulse.py --reseed     # force re-baseline (log nothing this cycle)

Exit code: 0 always on a successful cycle (a NEW gap is data, not a daemon failure —
keep `systemctl --failed` at zero). 2 only on an internal error (DB unreachable, etc.).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import psycopg2
import psycopg2.extras

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
PY = sys.executable or "python3"


# ─── check runners (subprocess — wrap, never re-implement) ────────────────────

def _run(argv):
    """Run a check as a child process from the repo root. Returns (rc, stdout+stderr)."""
    try:
        p = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, timeout=1200)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:                      # a crashed check is itself a signal, not a pulse crash
        return 99, f"<meta_pulse: check failed to run: {type(e).__name__}: {e}>"


def truth_test_signals():
    """Run the truth-test suite; parse per-assertion pass/fail into {testfile::label: 'pass'|'fail'}.

    run_all.py prints a '[testfile]' header per file, then the harness prints '  ✓ label'
    / '  ✗ label: err' per assertion. We key each assertion by its file so labels that
    repeat across files stay distinct."""
    rc, out = _run([PY, "truth_tests/run_all.py"])
    sig = {}
    cur_file = "?"
    for line in out.splitlines():
        m = re.match(r"^\[(test_\w+)\]\s*$", line)
        if m:
            cur_file = m.group(1)
            continue
        # assertion lines are INDENTED ('  ✓ label' / '  ✗ label: err'); the runner's
        # column-0 summary ('✓ truth_tests: …' / '✗ truth_tests FAILED: …') is NOT an
        # assertion — require leading whitespace so the summary is never mis-parsed.
        m = re.match(r"^\s+✓\s+(.+?)\s*$", line)
        if m:
            sig[f"{cur_file}::{m.group(1)}"] = "pass"
            continue
        m = re.match(r"^\s+✗\s+(.+?)(?::\s.*)?$", line)
        if m:
            label = m.group(1).strip()
            # a whole-file import failure -> one synthetic assertion for the file
            if label.startswith("IMPORT FAILED"):
                label = "__import__"
            sig[f"{cur_file}::{label}"] = "fail"
    # If the runner produced no parseable assertions at all, that itself is a drift-ish
    # signal, but we do NOT fabricate assertion keys — an empty dict simply records no
    # assertion state this cycle (handled conservatively by the delta: nothing new).
    return sig, rc


_INV_LINE = re.compile(r"^\s*-\s*(A\d+):\s*missing")
_ENF_LINE = re.compile(r"^\s*-\s*(A\d+)\s*(?:->|→)\s*(V\d+):")
_ALN_LINE = re.compile(r"^\s*(\S+\.md):\s*\[(.+)\]")


def _section_lines(out, header_substr):
    """Yield lines that appear AFTER the given section header (so we only parse the
    failure block, never the ✓ / ⚠-stale lines that share the same '→' shape)."""
    started = False
    for line in out.splitlines():
        if header_substr in line:
            started = True
            continue
        if started:
            yield line


def ontology_drift_signals():
    """Return the set of active drift keys from the three ontology gates. Deterministic:
    each key names the specific broken artifact. A non-zero exit with no parseable
    specifics still yields a generic fallback key so a regression is never fully missed."""
    drift = set()

    # --invariants: 🟢 rows naming an artifact that does not exist
    rc, out = _run([PY, "scripts/ontology_check.py", "--invariants"])
    if rc == 1:
        hit = False
        for line in _section_lines(out, "GREEN invariant"):
            m = _INV_LINE.match(line)
            if m:
                drift.add(f"invariant:{m.group(1)}"); hit = True
        if not hit:
            drift.add("invariant:UNSPECIFIED")

    # --enforcement: §4 rows claiming a validator mode that is not live (phantom)
    rc, out = _run([PY, "scripts/ontology_check.py", "--enforcement"])
    if rc == 1:
        hit = False
        for line in _section_lines(out, "PHANTOM ENFORCEMENT"):
            m = _ENF_LINE.match(line)
            if m:
                drift.add(f"enforcement:{m.group(1)}/{m.group(2)}"); hit = True
        if not hit:
            drift.add("enforcement:UNSPECIFIED")

    # --alignment: an A# cited in the plan/bridge that is not defined in §4
    rc, out = _run([PY, "scripts/ontology_check.py", "--alignment"])
    if rc == 1:
        hit = False
        for line in _section_lines(out, "DANGLING"):
            m = _ALN_LINE.match(line)
            if m:
                fn = m.group(1)
                for a in re.findall(r"A\d+", m.group(2)):
                    drift.add(f"alignment:{fn}:{a}"); hit = True
        if not hit:
            drift.add("alignment:UNSPECIFIED")

    return drift


def open_holes(cur):
    """Every currently-open holes_findings row. Returns {id: {hole_type, self_heal}}.
    self_heal = the row carries an A74 metadata.recheck_condition (it self-closes in its
    own routine) → the evolution gap that mirrors it is auto_resolvable."""
    cur.execute("""SELECT id, hole_type, severity, description,
                          (metadata ? 'recheck_condition') AS self_heal
                   FROM holes_findings WHERE status = 'open'""")
    out = {}
    for r in cur.fetchall():
        out[r["id"]] = {
            "hole_type": r["hole_type"], "severity": r["severity"],
            "description": (r["description"] or "")[:280], "self_heal": bool(r["self_heal"]),
        }
    return out


# ─── state ────────────────────────────────────────────────────────────────────

def load_state(cur):
    cur.execute("SELECT assertions, holes_ids, drift, seeded FROM meta_pulse_state WHERE id = 1")
    r = cur.fetchone()
    if not r:                                    # migration guarantees the row, but be defensive
        cur.execute("INSERT INTO meta_pulse_state (id) VALUES (1) ON CONFLICT DO NOTHING")
        return {}, set(), set(), False
    return dict(r["assertions"] or {}), set(r["holes_ids"] or []), set(r["drift"] or []), bool(r["seeded"])


def save_state(cur, assertions, holes_ids, drift):
    cur.execute("""UPDATE meta_pulse_state
                      SET last_run_at = now(), assertions = %s, holes_ids = %s,
                          drift = %s, seeded = true
                    WHERE id = 1""",
                (json.dumps(assertions), json.dumps(sorted(holes_ids)),
                 json.dumps(sorted(drift))))


# ─── gap recording (delta only) ─────────────────────────────────────────────────

def _record_gap(cur, gap_id, kind, detail, recheck, auto_resolvable, metadata):
    """Insert a NEW gap, or re-open one that had previously resolved. Never duplicates,
    never touches a row already open (that's a known gap — the delta shouldn't even
    reach here for one, but ON CONFLICT makes it safe if it does)."""
    cur.execute("""INSERT INTO system_evolution_log
                     (gap_id, kind, detail, recheck_condition, auto_resolvable, metadata, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'open')
                   ON CONFLICT (gap_id) DO UPDATE
                     SET status = CASE WHEN system_evolution_log.status = 'resolved'
                                       THEN 'open' ELSE system_evolution_log.status END,
                         last_seen = now(),
                         resolved_at = CASE WHEN system_evolution_log.status = 'resolved'
                                            THEN NULL ELSE system_evolution_log.resolved_at END,
                         resolved_via = CASE WHEN system_evolution_log.status = 'resolved'
                                             THEN NULL ELSE system_evolution_log.resolved_via END,
                         detail = EXCLUDED.detail, metadata = EXCLUDED.metadata,
                         recheck_condition = EXCLUDED.recheck_condition,
                         auto_resolvable = EXCLUDED.auto_resolvable
                   RETURNING (xmax = 0) AS inserted, status""",
                (gap_id, kind, detail, recheck, auto_resolvable, json.dumps(metadata)))
    row = cur.fetchone()
    return row  # {inserted: bool, status: 'open'}


def record_new_gaps(cur, cur_assert, last_assert, cur_holes, last_holes, cur_drift, last_drift):
    new = []

    # assertions: was-not-failing -> now-failing
    for akey, st in cur_assert.items():
        if st == "fail" and last_assert.get(akey) != "fail":
            gid = f"assertion:{akey}"
            detail = f"Truth-test assertion regressed to FAILING: {akey}"
            recheck = f"truth-test assertion '{akey}' passes (or the test is removed)"
            r = _record_gap(cur, gid, "assertion", detail, recheck, False, {"assertion": akey})
            new.append((gid, "assertion", False, r))

    # holes: an open holes_findings id not seen last run
    for hid, info in cur_holes.items():
        if hid not in last_holes:
            gid = f"hole:{hid}"
            auto = info["self_heal"]
            detail = (f"New self-recorded gap (holes_findings #{hid}, {info['hole_type']}, "
                      f"{info['severity']}): {info['description']}")
            recheck = f"holes_findings id {hid} is no longer status='open'"
            r = _record_gap(cur, gid, "hole", detail, recheck, auto,
                            {"holes_findings_id": hid, "hole_type": info["hole_type"],
                             "self_heal": auto})
            new.append((gid, "hole", auto, r))

    # drift: a drift key not present last run
    for key in cur_drift:
        if key not in last_drift:
            gid = f"drift:{key}"
            detail = f"New ontology drift signal: {key}"
            recheck = f"ontology drift signal '{key}' no longer reported by ontology_check"
            r = _record_gap(cur, gid, "drift", detail, recheck, False, {"drift_key": key})
            new.append((gid, "drift", False, r))

    return new


# ─── auto-close (recheck; no model) ──────────────────────────────────────────────

def reconcile_closures(cur, cur_assert, cur_holes, cur_drift):
    """For every still-open evolution row, machine-check its recheck_condition against the
    CURRENT signals and close the ones that now pass. Deterministic; no model call."""
    cur.execute("SELECT gap_id, kind, metadata FROM system_evolution_log WHERE status = 'open'")
    rows = cur.fetchall()
    closed = []
    open_hole_ids = set(cur_holes.keys())
    for r in rows:
        gid, kind, md = r["gap_id"], r["kind"], (r["metadata"] or {})
        resolved = False
        if kind == "assertion":
            akey = md.get("assertion")
            # closed iff the assertion is now passing, or no longer present in the suite
            resolved = (cur_assert.get(akey) == "pass") or (akey not in cur_assert and cur_assert)
        elif kind == "hole":
            hid = md.get("holes_findings_id")
            resolved = hid not in open_hole_ids            # the source hole left 'open'
        elif kind == "drift":
            resolved = md.get("drift_key") not in cur_drift
        if resolved:
            cur.execute("""UPDATE system_evolution_log
                             SET status = 'resolved', resolved_at = now(),
                                 resolved_via = 'meta_pulse_recheck', last_seen = now()
                           WHERE gap_id = %s AND status = 'open'""", (gid,))
            if cur.rowcount:
                closed.append(gid)
    return closed


# ─── report ───────────────────────────────────────────────────────────────────

def print_queue(cur):
    cur.execute("""SELECT gap_id, kind, detail, first_seen FROM system_evolution_log
                   WHERE status = 'open' AND auto_resolvable = false
                   ORDER BY first_seen""")
    rows = cur.fetchall()
    print("=" * 72)
    print(f"meta-pulse DECISION QUEUE — open gaps with no automatic resolution ({len(rows)})")
    print("=" * 72)
    if not rows:
        print("  (empty — every open gap is either auto-resolving or already closed)")
    for r in rows:
        print(f"  [{r['kind']:9}] {r['gap_id']}")
        print(f"      {r['detail']}")
        print(f"      first_seen {r['first_seen']:%Y-%m-%d %H:%M}")
    # auto-resolving watch-list (informational; no decision needed)
    cur.execute("""SELECT count(*) AS n FROM system_evolution_log
                   WHERE status = 'open' AND auto_resolvable = true""")
    n_auto = cur.fetchone()["n"]
    if n_auto:
        print(f"\n  ({n_auto} open gap(s) are auto-resolving — self-healing machinery, no action)")


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    report_only = "--report" in sys.argv
    reseed = "--reseed" in sys.argv

    try:
        conn = psycopg2.connect(DSN)
        conn.autocommit = True
    except Exception as e:
        print(f"meta_pulse: DB unreachable: {e}", file=sys.stderr)
        sys.exit(2)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if report_only:
        print_queue(cur)
        conn.close()
        sys.exit(0)

    # 1-3. gather current signals
    cur_assert, tt_rc = truth_test_signals()
    cur_drift = ontology_drift_signals()
    cur_holes = open_holes(cur)

    # 4. delta vs last baseline
    last_assert, last_holes, last_drift, seeded = load_state(cur)

    if reseed or not seeded:
        save_state(cur, cur_assert, set(cur_holes.keys()), cur_drift)
        why = "reseed requested" if reseed else "first run"
        print(f"meta_pulse: baseline established ({why}) — "
              f"{len(cur_assert)} assertions, {len(cur_holes)} open holes, "
              f"{len(cur_drift)} drift signal(s). No gaps logged this cycle (delta-only).")
        conn.close()
        sys.exit(0)

    new = record_new_gaps(cur, cur_assert, last_assert, cur_holes, last_holes,
                          cur_drift, last_drift)

    # 5. auto-close whatever the recheck now satisfies
    closed = reconcile_closures(cur, cur_assert, cur_holes, cur_drift)

    # 6. persist new baseline
    save_state(cur, cur_assert, set(cur_holes.keys()), cur_drift)

    # report (to the log — no send)
    n_manual = sum(1 for _, _, auto, _ in new if not auto)
    n_auto = sum(1 for _, _, auto, _ in new if auto)
    print(f"meta_pulse cycle: {len(new)} new gap(s) "
          f"[{n_manual} need a decision, {n_auto} auto-resolving], "
          f"{len(closed)} auto-closed. "
          f"assertions={len(cur_assert)} holes={len(cur_holes)} drift={len(cur_drift)}.")
    for gid, kind, auto, r in new:
        tag = "AUTO" if auto else "DECIDE"
        print(f"  + [{tag}] {gid}")
    for gid in closed:
        print(f"  - [CLOSED] {gid}")
    if n_manual:
        print(f"  → decision queue: SELECT * FROM system_evolution_log "
              f"WHERE status='open' AND auto_resolvable=false;")

    conn.close()
    sys.exit(0)


if __name__ == "__main__":
    main()
