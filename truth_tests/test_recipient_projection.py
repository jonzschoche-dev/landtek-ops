#!/usr/bin/env python3
"""test_recipient_projection.py — the A75 truth-floor (one truth, N recipient-shaped projections).

Extends the A70 grep-floor pattern (test_incorporation_gate.py) to the projection layer:
  1. **Wiring floors, one per graduated path** — each WIRED consuming path still pulls/pushes through
     `leo_tools/recipient_projection.py` (it cannot be silently unwired):
       · ombudsman_hunter.py::_fetch_facts  → project_fact_slice   (deploy_844, first proof)
       · verify_worker.py                   → project_doc_slice    (rollout T1)
       · calendar_orchestrator.py::enqueue_deliverable → project_pulse_payload (rollout T2)
  2. **Profile totality** — every PROFILES entry declares ALL six axes (kind/who/purpose/form/dose/
     channel), with a coherent dose (PULL_COMPLETE, or a push ceiling with a window). A profile with a
     missing axis is an unshaped recipient — the defect A75 exists to prevent. (Module-level render
     functions like render_human_reply are not profiles; only the PROFILES dict is checked.)
  3. **Fail-closed registry** — an unknown profile key must refuse (KeyError), never default-open.
  4. **A5 in the SQL** — the WHO wall is a bound parameter in the projection queries (LIKE %s in
     project_fact_slice and verify_loop.doc_worklist), never a post-filter.
Plus a REPORT-ONLY line: agent paths still reading governed tables raw (the un-wired inventory —
visibility, not a red; the list shrinks as paths graduate).

Negative-tested state-free: `python3 truth_tests/test_recipient_projection.py --negative` strips an
axis from an in-memory profile copy and feeds the wiring floors doctored source — both must bite.
No DB writes, nothing persisted.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "leo_tools"))

AXES = ("kind", "who", "purpose", "form", "dose", "channel")

# (floor label, file, function whose body must contain the call, required projection call)
WIRED_PATHS = [
    ("ombudsman_hunter._fetch_facts", os.path.join("scripts", "ombudsman_hunter.py"),
     "_fetch_facts", "project_fact_slice"),
    ("verify_worker._projected_worklist", os.path.join("scripts", "verify_worker.py"),
     "_projected_worklist", "project_doc_slice"),
    ("calendar_orchestrator.enqueue_deliverable", os.path.join("scripts", "calendar_orchestrator.py"),
     "enqueue_deliverable", "project_pulse_payload"),
    ("brief_drafter._projected_facts", os.path.join("scripts", "brief_drafter.py"),
     "_projected_facts", "project_fact_slice"),
    ("case_memo._projected_facts", os.path.join("scripts", "case_memo.py"),
     "_projected_facts", "project_fact_slice"),
]


def _fn_body(relpath, fn_name, src=None):
    """The source body of `def fn_name` in repo file relpath (or doctored src for the negative test)."""
    if src is None:
        src = open(os.path.join(REPO, relpath), errors="ignore").read()
    m = re.search(rf"def {re.escape(fn_name)}\b.*?(?=\ndef |\nclass |\Z)", src, re.S)
    return m.group(0) if m else ""


def _assert_wired(label, relpath, fn_name, call, src=None):
    body = _fn_body(relpath, fn_name, src=src)
    if not body:
        raise TruthFailure(f"{relpath} no longer defines {fn_name}() — the {label} projection path "
                           f"has been removed/renamed. Re-wire the A75 floor before this path runs.")
    if call not in body:
        raise TruthFailure(f"{relpath}::{fn_name} no longer calls {call} — the {label} path has been "
                           f"UNWIRED from recipient_projection (A75: no recipient reads raw "
                           f"un-projected data). Re-wire before it runs.")


def wired_paths(cur):
    """A75 wiring floors: every graduated consuming path still goes through the projection module."""
    for label, relpath, fn, call in WIRED_PATHS:
        _assert_wired(label, relpath, fn, call)
    print(f"      [projection] {len(WIRED_PATHS)} wired path(s) hold their floor: "
          + ", ".join(lbl for lbl, *_ in WIRED_PATHS))


def profiles_total(cur, profiles=None):
    """A75 totality: every RecipientProfile fixes ALL four design axes (six schema fields)."""
    import recipient_projection as rp
    profiles = profiles if profiles is not None else rp.PROFILES
    bad = []
    for key, p in profiles.items():
        missing = [a for a in AXES if a not in p or p[a] in (None, "", {})]
        if missing:
            bad.append(f"{key}: missing {missing}")
            continue
        if p["kind"] not in ("human", "agent"):
            bad.append(f"{key}: kind={p['kind']!r} not human|agent")
        if p["form"] not in ("HUMAN", "MACHINE"):
            bad.append(f"{key}: form={p['form']!r} not HUMAN|MACHINE")
        d = p["dose"]
        if d != rp.PULL_COMPLETE and not (isinstance(d, dict) and "push_max_per_window" in d and "window" in d):
            bad.append(f"{key}: dose={d!r} is neither PULL_COMPLETE nor a push ceiling with a window")
        if not isinstance(p["who"], dict):
            bad.append(f"{key}: who axis is not a resolved dict (the A5 wall must be explicit)")
    if bad:
        raise TruthFailure(f"{len(bad)} RecipientProfile(s) are NOT total — an unshaped recipient is the "
                           f"defect A75 exists to prevent: {bad}")
    print(f"      [projection] {len(profiles)} profile(s) total across axes {'/'.join(AXES)}")


def unknown_profile_refuses(cur):
    """A75 fail-closed: an unregistered profile key refuses — never a default-open projection."""
    import recipient_projection as rp
    try:
        rp.profile("zz-nonexistent-recipient")
    except KeyError:
        return
    raise TruthFailure("recipient_projection.profile() returned something for an UNREGISTERED key — "
                       "the registry must fail closed (no recipient reads raw un-projected data, A75)")


def scope_in_query(cur):
    """A5 floor: the WHO wall is a bound SQL parameter inside the projection queries, not a post-filter."""
    checks = [
        (os.path.join("leo_tools", "recipient_projection.py"), "project_fact_slice", "LIKE %s"),
        (os.path.join("scripts", "verify_loop.py"), "doc_worklist", "LIKE %s"),
    ]
    for relpath, fn, needle in checks:
        if needle not in _fn_body(relpath, fn):
            raise TruthFailure(f"{relpath}::{fn} no longer binds the matter scope in its SQL ({needle!r} "
                               f"gone) — A5 scope must live IN THE QUERY, never a post-filter.")


def scope_isolation_runtime(cur):
    """A5 RUNTIME floor (not just a grep): project_fact_slice under a PAR scope returns ZERO MWK
    rows and vice-versa — the WHO wall actually isolates at query time. Negative-tested: if the
    LIKE binding regressed to a no-op, a foreign-client row would leak and this bites."""
    import psycopg2
    import recipient_projection as rp
    from _harness import DSN
    c = psycopg2.connect(DSN)          # plain tuple cursor: project_fact_slice indexes r[0]
    pc = c.cursor()
    try:
        for scope, foreign in (("PAR-%", "MWK"), ("MWK-%", "PAR")):
            rows = rp.project_fact_slice(pc, "brief-drafter", scope)
            leak = [r for r in rows if (r["matter_code"] or "").startswith(foreign)]
            if leak:
                raise TruthFailure(
                    f"project_fact_slice(scope={scope!r}) leaked {len(leak)} {foreign} row(s) — the A5 "
                    f"WHO wall failed to isolate (e.g. {leak[0]['matter_code']}). A projection must "
                    f"NEVER cross the client boundary.")
    finally:
        c.close()
    print("      [projection] runtime scope isolation holds (PAR↮MWK: 0 cross-scope rows)")


def unwired_inventory(cur):
    """REPORT-ONLY visibility: repo agent scripts still touching matter_facts raw (candidates for the
    next A75 graduations; wired files may appear too when they retain residual internal raw reads —
    the ombudsman precedent). Never a red; the list shrinks as paths graduate."""
    raw = []
    sdir = os.path.join(REPO, "scripts")
    for name in sorted(os.listdir(sdir)):
        if not name.endswith(".py"):
            continue
        try:
            src = open(os.path.join(sdir, name), errors="ignore").read()
        except OSError:
            continue
        if re.search(r"FROM\s+matter_facts", src, re.I):
            wired = any(c in src for c in ("project_fact_slice", "project_doc_slice", "project_pulse_payload"))
            raw.append(name + ("*" if wired else ""))
    print(f"      [projection] un-wired inventory (report-only): {len(raw)} script(s) read matter_facts "
          f"directly; * = already projection-wired with residual internal reads")
    print("        " + ", ".join(raw[:14]) + (" …" if len(raw) > 14 else ""))


TESTS = [
    ("projection.wired_paths", wired_paths),
    ("projection.profiles_total", profiles_total),
    ("projection.unknown_profile_refuses", unknown_profile_refuses),
    ("projection.scope_in_query", scope_in_query),
    ("projection.scope_isolation_runtime", scope_isolation_runtime),
    ("projection.unwired_inventory", unwired_inventory),
]


def _negative():
    """State-free negative proof: a stripped axis and an unwired path must BITE. No DB, no writes."""
    import recipient_projection as rp
    ok = 0
    # 1) axis-strip: an in-memory profile copy missing its dose axis must fail totality.
    doctored = {k: dict(v) for k, v in rp.PROFILES.items()}
    doctored["verify-worker"].pop("dose")
    try:
        profiles_total(None, profiles=doctored)
        print("  ✗ NEGATIVE FAILED: stripped dose axis did NOT bite")
    except TruthFailure as e:
        ok += 1
        print(f"  ✓ negative (axis-strip) bit as required: {e}")
    # 2) unwired path: doctored verify_worker source with the projection call removed must fail the floor.
    real = open(os.path.join(REPO, "scripts", "verify_worker.py"), errors="ignore").read()
    stripped = real.replace("project_doc_slice", "doc_worklist_raw")
    try:
        _assert_wired("verify_worker._projected_worklist", os.path.join("scripts", "verify_worker.py"),
                      "_projected_worklist", "project_doc_slice", src=stripped)
        print("  ✗ NEGATIVE FAILED: unwired path did NOT bite")
    except TruthFailure as e:
        ok += 1
        print(f"  ✓ negative (unwired-path) bit as required: {e}")
    return ok == 2


if __name__ == "__main__":
    if "--negative" in sys.argv:
        sys.exit(0 if _negative() else 1)
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
