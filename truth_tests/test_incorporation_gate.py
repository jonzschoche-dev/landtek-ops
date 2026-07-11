#!/usr/bin/env python3
"""test_incorporation_gate.py — the A70 truth-floor (incorporation precedes decision).

Three count-independent assertions (honest as matters improve — deliberately NOT "matter X must HOLD",
which would punish grounding progress; 1891 went 0→91 verified while this was being built):
  1. **No READY was ever recorded on a thin base** — every `incorporation_verdicts` row with
     verdict='READY' carries verified_count ≥ 5. A READY-on-thin row means the gate lied or was bypassed.
  2. **Fail-closed behavior, exercised live** — the gate called on a nonexistent matter returns
     HOLD:gap-blind (never READY, never an exception escaping). Run with record=False (read-only).
  3. **The wiring floor** — `scripts/ombudsman_hunter.py::cmd_playbook` actually calls
     `require_incorporation` (the A36-style grep-floor: the gate can't be silently unwired).
Plus a report line: verdicts recorded so far by outcome. Negative-tested (rolled-back READY-on-thin
insert makes #1 bite).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def no_ready_on_thin(cur):
    """A70: a recorded READY verdict on a base under the 5-verified floor is a gate lie/bypass."""
    cur.execute("SELECT to_regclass('incorporation_verdicts')")
    if cur.fetchone()["to_regclass"] is None:
        print("      [incorporation] verdict ledger not created yet (no gate run) — nothing to assert")
        return
    cur.execute("""SELECT matter_code, stakeholder, verified_count, created_at::date AS d
                   FROM incorporation_verdicts
                   WHERE verdict='READY' AND coalesce(verified_count, 0) < 5
                   ORDER BY created_at DESC LIMIT 10""")
    bad = [f"{r['matter_code']}→{r['stakeholder']} ({r['verified_count']} verified, {r['d']})"
           for r in cur.fetchall()]
    if bad:
        raise TruthFailure(
            f"{len(bad)} READY verdict(s) recorded on a THIN base (<5 verified) — the A70 gate lied or "
            f"was bypassed: {bad}. A decision emitted over an un-incorporated base is the violation "
            f"A70 exists to prevent.")


def gate_fails_closed(cur):
    """A70: an unknown matter must yield HOLD:gap-blind — never READY, never an escaping exception."""
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    from incorporation_gate import require_incorporation
    v = require_incorporation(cur, "ZZ-NONEXISTENT-000", "truth-test", record=False)
    if v["verdict"] != "HOLD:gap-blind":
        raise TruthFailure(
            f"gate returned {v['verdict']!r} for a NONEXISTENT matter — must be HOLD:gap-blind "
            f"(fail-closed, A70c). A gate that passes the unknown passes anything.")


# (file, function) for every GRADUATED deliverable emitter — its body must call require_incorporation
# so no governed emitter ships without a recorded verdict. Add a row when an emitter graduates
# (universalize_report.py --strict enumerates the not-yet-gated remainder).
GATED_EMITTERS = [
    ("scripts/ombudsman_hunter.py", "cmd_playbook"),
    ("scripts/brief_drafter.py", "main"),   # A70 graduation, deploy_858
    ("scripts/case_memo.py", "main"),       # A70 graduation, deploy_870
]


def gate_is_wired(cur):
    """A70 wiring floor: every graduated emitter calls the gate (it cannot be silently unwired)."""
    for relpath, fn in GATED_EMITTERS:
        src = open(os.path.join(REPO, relpath), errors="ignore").read()
        body = re.search(rf"def {re.escape(fn)}\b.*?(?=\ndef |\nclass |\Z)", src, re.S)
        if not body or "require_incorporation" not in body.group(0):
            raise TruthFailure(
                f"{relpath}::{fn} no longer calls require_incorporation — the A70 gate has been "
                f"unwired from a governed deliverable emitter. Re-wire before any draft emits.")
    print(f"      [incorporation] {len(GATED_EMITTERS)} emitter(s) hold the A70 gate floor")


def verdicts_reported(cur):
    """Visibility: recorded incorporation verdicts by outcome (threshold-free)."""
    cur.execute("SELECT to_regclass('incorporation_verdicts')")
    if cur.fetchone()["to_regclass"] is None:
        return
    cur.execute("SELECT verdict, count(*) AS n FROM incorporation_verdicts GROUP BY verdict ORDER BY n DESC")
    parts = [f"{r['verdict']}={r['n']}" for r in cur.fetchall()]
    print(f"      [incorporation] verdicts recorded: {', '.join(parts) if parts else 'none yet'} (A70)")


TESTS = [
    ("incorporation.no_ready_on_thin", no_ready_on_thin),
    ("incorporation.gate_fails_closed", gate_fails_closed),
    ("incorporation.gate_is_wired", gate_is_wired),
    ("incorporation.verdicts_reported", verdicts_reported),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
