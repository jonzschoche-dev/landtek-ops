#!/usr/bin/env python3
"""test_leo_instant_convergence.py — the convergence safety floor (Step 3).

The equilibrium-aligned orchestrator (comm_agent_max.handle_chat_event) runs in SHADOW alongside the live
path (leo_service.process); comm_agent_convergence_diff records both. Before any cutover we must prove:
  (a) the orchestrator is NEVER less strict than the live path — it would SEND only where the live path
      also sends (no leak more than the current classify allows);
  (b) the orchestrator actually PARTICIPATES — it generates + propagates (not a spectator).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import run, TruthFailure


def orchestrator_never_less_strict(cur):
    cur.execute("SELECT count(*) AS n FROM comm_agent_convergence_diff WHERE orch_at_least_as_strict IS FALSE")
    n = cur.fetchone()["n"]
    if n:
        cur.execute("""SELECT inbound_msg_id, live_action, orch_next_action FROM comm_agent_convergence_diff
                        WHERE orch_at_least_as_strict IS FALSE ORDER BY id DESC LIMIT 3""")
        ex = cur.fetchall()
        raise TruthFailure(f"{n} convergence rows where the orchestrator would SEND but the live path did "
                           f"NOT — the orchestrator must never be less strict. e.g. {ex}")


def orchestrator_participates(cur):
    """It must run the engine + generate — not spectate. (Vacuous-safe if no shadow rows yet.)"""
    cur.execute("""SELECT count(*) AS total,
                          count(*) FILTER (WHERE (payload->>'generated')::boolean) AS generated,
                          count(*) FILTER (WHERE payload ? 'internal_contradictions') AS propagated
                     FROM channel_audit WHERE event_type='comm_agent_shadow'
                      AND created_at > now() - interval '7 days'""")
    r = cur.fetchone()
    if r["total"] and r["generated"] == 0 and r["propagated"] == 0:
        raise TruthFailure("comm_agent_shadow rows exist but none show generated/propagated — the "
                           "orchestrator is not participating (still a spectator).")


TESTS = [
    ("convergence.orchestrator_never_less_strict", orchestrator_never_less_strict),
    ("convergence.orchestrator_participates", orchestrator_participates),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
