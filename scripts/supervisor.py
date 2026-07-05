#!/usr/bin/env python3
"""supervisor.py — Supervisor v1 (Phase 1): work-order state machine + fail-closed governance.

The stack's ~50 agents fire on independent timers with no shared notion of "a piece of work in
flight." This is the missing coordination layer: a unit of work is ROUTED to a plan, TRACKED across
steps with persistent state (survives restarts), and each step is only allowed if it is a GOVERNED
path — a T3/outward step is structurally blocked from autonomous execution and held for a human.

NOT a framework (no LangGraph): a Postgres table (`work_orders`) + this loop. Same primitives as the
rest of the stack (timers + Postgres + gate). Additive; existing agents/timers untouched.

v1 scope: routing + persistent multi-step state + fail-closed governance + the handoff CLI contract.
NO auto-executable steps yet (Phase 3 — needs a real enqueue-and-poll adapter; existing agents are
queue-draining daemons, not callable functions). A step whose mode is 'auto' is fail-closed in v1.

CLI:
  supervisor.py enqueue --kind evidence_gap --matter MWK-001 [--title "..."] [--by jonathan]
  supervisor.py list [--awaiting]          # all orders, or only those awaiting handoff
  supervisor.py status [<id>]              # detail: steps, current step, status, audit
  supervisor.py complete <id> --result "..."   # write a handoff result → advance the order
  supervisor.py tick [--dry]               # process queued orders one cycle (Phase 2 runs via timer)
"""
from __future__ import annotations
import os
import sys
import json
import argparse
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# ── Kind registry — routing is DATA, not code. Add a work-kind = add an entry. ──────────────
# mode: 'handoff' (a Claude session / human does it, then `complete`) | 'auto' (Phase 3 only)
# tier: T0..T3 per GOVERNED_ACTIONS.md. T3/outward/untagged → fail-closed governance block.
KINDS = {
    "evidence_gap": {
        "title": "Evidence gap closure",
        "steps": [
            # ground FIRST: is what this gap seeks already in the corpus? (the check missing when
            # #4/#5 were created). If a strong candidate exists → held for human, don't spend a gather.
            {"name": "ground", "agent": "corpus_check",           "mode": "ground",  "tier": "T1"},
            {"name": "gather", "agent": "case-26360-strategist",  "mode": "handoff", "tier": "T2"},
            {"name": "hold",   "agent": "human",                  "mode": "handoff", "tier": "T3"},
        ],
    },
}

# Words to ignore when grounding a gap title against the corpus (verbs/filler, not discriminators).
GROUND_STOPWORDS = {
    "gap", "obtain", "confirm", "pull", "check", "from", "that", "this", "with", "into",
    "need", "already", "exist", "exists", "corpus", "before", "proof", "which", "does",
    "have", "held", "there", "their", "must", "should", "reframed", "prong", "reanalyze",
}

# Verbs that mean an outward/irreversible action — fail-closed even if mis-tagged (GOVERNED_ACTIONS §0).
OUTWARD_VERBS = ("send", "file", "submit", "email", "post", "notify",
                 "contact", "publish", "expose", "mark_filed", "dispatch")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = False
    return c


def _now():
    return datetime.now(timezone.utc).isoformat()


def governance_block(step: dict) -> bool:
    """Fail-CLOSED: block a step from autonomous execution if it's T3, untagged, or looks outward."""
    tier = (step.get("tier") or "").upper()
    hay = f"{step.get('agent','')} {step.get('name','')}".lower()
    if tier == "T3":
        return True
    if tier not in ("T0", "T1", "T2"):          # untagged / unknown → default-deny
        return True
    if any(v in hay for v in OUTWARD_VERBS):     # outward verb regardless of tag
        return True
    return False


def _ground_check(cur, order: dict):
    """Corpus-existence check: does what this gap seeks already exist? Returns [(id,title,score)].
    Deterministic keyword scoring over `documents` — the check that was missing when work orders
    #4/#5 were created against docs (233/415) and a verified fact (390) that already existed.
    Soft gate: any strong candidate → held for human review, never a hard block."""
    import re
    text = (order.get("title") or "")
    terms = sorted({w for w in re.findall(r"[a-z0-9]{4,}", text.lower()) if w not in GROUND_STOPWORDS})
    if len(terms) < 2:
        return []
    like = " + ".join(["(CASE WHEN _hay LIKE %s THEN 1 ELSE 0 END)"] * len(terms))
    sql = f"""SELECT id, coalesce(document_title,original_filename,file_name,'?') AS t, score FROM (
                SELECT id, document_title, original_filename, file_name,
                       ({like}) AS score
                FROM (SELECT id, document_title, original_filename, file_name,
                             lower(coalesce(document_title,'')||' '||coalesce(original_filename,'')||' '||coalesce(file_name,'')) AS _hay
                      FROM documents) d
              ) s WHERE score >= %s ORDER BY score DESC LIMIT 5"""
    thresh = max(2, len(terms) // 2)
    cur.execute(sql, tuple(f"%{t}%" for t in terms) + (thresh,))
    return [(r["id"], r["t"], r["score"]) for r in cur.fetchall()]


def _audit(order: dict, frm: str, to: str, note: str) -> list:
    log = order.get("audit") or []
    log.append({"ts": _now(), "from": frm, "to": to, "note": note})
    return log


# ── Commands ────────────────────────────────────────────────────────────────────────────────

def cmd_enqueue(cur, kind, matter, title, by):
    spec = KINDS.get(kind)
    if not spec:
        print(f"unknown kind '{kind}'. known: {', '.join(KINDS)}")
        return 2
    steps = [dict(s, status="pending", result=None) for s in spec["steps"]]
    cur.execute(
        """INSERT INTO work_orders (kind, matter_code, title, status, steps, current_step,
             created_by, audit)
           VALUES (%s,%s,%s,'queued',%s,0,%s,%s) RETURNING id""",
        (kind, matter, title or spec["title"], json.dumps(steps), by,
         json.dumps([{"ts": _now(), "from": None, "to": "queued", "note": f"enqueued kind={kind}"}])))
    oid = cur.fetchone()["id"]  # RealDictCursor → dict, not tuple
    print(f"enqueued work_order #{oid} ({kind}, matter={matter}) — status=queued, {len(steps)} steps")
    return 0


def cmd_list(cur, awaiting):
    q = "SELECT id, kind, matter_code, status, current_step, title FROM work_orders"
    if awaiting:
        q += " WHERE status='awaiting_handoff'"
    q += " ORDER BY updated_at DESC LIMIT 50"
    cur.execute(q)
    rows = cur.fetchall()
    if not rows:
        print("(no matching work orders)")
        return 0
    for r in rows:
        stale = ""  # staleness surfaced in status/tick; list stays terse
        print(f"  #{r['id']:>4} [{r['status']:<18}] {r['kind']:<14} {r['matter_code'] or '-':<12} "
              f"step {r['current_step']}  {r['title'] or ''}{stale}")
    return 0


def cmd_status(cur, oid):
    if oid:
        cur.execute("SELECT * FROM work_orders WHERE id=%s", (oid,))
        r = cur.fetchone()
        if not r:
            print(f"no work_order #{oid}"); return 2
        print(f"#{r['id']} [{r['status']}] {r['kind']} matter={r['matter_code']} — {r['title']}")
        print(f"  created {r['created_at']} by {r['created_by']}; updated {r['updated_at']}")
        for i, s in enumerate(r["steps"]):
            mark = "→" if i == r["current_step"] else " "
            gov = " ⛔T3-hold" if governance_block(s) else ""
            print(f"  {mark} [{i}] {s['name']:<10} {s['mode']:<8} {s.get('tier','?'):<3} "
                  f"{s.get('status','?')}{gov}  {(s.get('result') or '')[:60]}")
        print("  audit:")
        for a in r["audit"][-8:]:
            print(f"    {a['ts'][:19]}  {a['from']} → {a['to']}  {a['note']}")
    else:
        cur.execute("""SELECT status, count(*) n FROM work_orders GROUP BY status ORDER BY 2 DESC""")
        rows = cur.fetchall()
        print("work_orders by status:" if rows else "(no work orders)")
        for r in rows:
            print(f"  {r['status']:<18} {r['n']}")
        cur.execute("""SELECT id, kind, matter_code FROM work_orders
                       WHERE status IN ('awaiting_handoff','blocked_governance') ORDER BY updated_at""")
        held = cur.fetchall()
        if held:
            print("needs a human:")
            for r in held:
                print(f"  #{r['id']} {r['kind']} {r['matter_code'] or ''}")
    return 0


def cmd_complete(cur, oid, result):
    cur.execute("SELECT * FROM work_orders WHERE id=%s FOR UPDATE", (oid,))
    r = cur.fetchone()
    if not r:
        print(f"no work_order #{oid}"); return 2
    if r["status"] != "awaiting_handoff":
        print(f"#{oid} is '{r['status']}', not awaiting_handoff — nothing to complete"); return 2
    steps = r["steps"]; cs = r["current_step"]
    steps[cs]["status"] = "done"
    steps[cs]["result"] = result
    nxt = cs + 1
    new_status = "done" if nxt >= len(steps) else "queued"
    audit = _audit(r, "awaiting_handoff", new_status, f"handoff '{steps[cs]['name']}' completed")
    cur.execute("""UPDATE work_orders SET steps=%s, current_step=%s, status=%s,
                     updated_at=now(), audit=%s WHERE id=%s""",
                (json.dumps(steps), nxt, new_status, json.dumps(audit), oid))
    print(f"#{oid}: step '{steps[cs]['name']}' done → status={new_status}"
          + ("" if new_status == "done" else f" (next: '{steps[nxt]['name']}')"))
    return 0


def cmd_resolve(cur, oid, note):
    """Human clears a held order (blocked_governance / awaiting_handoff) → done, with a note.
    This is the ONLY path out of a T3 governance hold — a human decision, by design."""
    cur.execute("SELECT * FROM work_orders WHERE id=%s FOR UPDATE", (oid,))
    r = cur.fetchone()
    if not r:
        print(f"no work_order #{oid}"); return 2
    if r["status"] not in ("blocked_governance", "awaiting_handoff", "queued", "in_progress"):
        print(f"#{oid} is '{r['status']}' — nothing to resolve"); return 2
    steps, cs = r["steps"], r["current_step"]
    if cs < len(steps):
        steps[cs]["status"] = "resolved"
        steps[cs]["result"] = note
    audit = _audit(r, r["status"], "done", f"HUMAN-RESOLVED: {note}")
    cur.execute("UPDATE work_orders SET steps=%s, status='done', updated_at=now(), audit=%s WHERE id=%s",
                (json.dumps(steps), json.dumps(audit), oid))
    print(f"#{oid}: resolved by human → status=done — {note}")
    return 0


def cmd_cancel(cur, oid, reason):
    """Cancel a work order created on a false premise (e.g., the doc it seeks already exists).
    'cancelled' ≠ done (nothing was accomplished) and ≠ failed (it didn't fail — it was invalid)."""
    cur.execute("SELECT * FROM work_orders WHERE id=%s FOR UPDATE", (oid,))
    r = cur.fetchone()
    if not r:
        print(f"no work_order #{oid}"); return 2
    if r["status"] in ("done", "cancelled"):
        print(f"#{oid} already {r['status']}"); return 2
    audit = _audit(r, r["status"], "cancelled", f"CANCELLED: {reason}")
    cur.execute("UPDATE work_orders SET status='cancelled', updated_at=now(), audit=%s WHERE id=%s",
                (json.dumps(audit), oid))
    print(f"#{oid}: cancelled — {reason}")
    return 0


def cmd_tick(cur, dry):
    """One processing cycle. Claims queued/in_progress orders (SKIP LOCKED), advances one step each.
    Governance is checked FIRST on every step. Handoff → awaiting_handoff. Auto → fail-closed (v1)."""
    cur.execute("""SELECT * FROM work_orders WHERE status IN ('queued','in_progress')
                   ORDER BY id FOR UPDATE SKIP LOCKED""")
    orders = cur.fetchall()
    if not orders:
        print("tick: nothing queued"); return 0
    for r in orders:
        steps, cs = r["steps"], r["current_step"]
        if cs >= len(steps):
            _set(cur, r, "done", "all steps complete", dry); continue
        step = steps[cs]
        # (a) governance gate FIRST — fail-closed
        if governance_block(step):
            _set(cur, r, "blocked_governance",
                 f"step '{step['name']}' (tier {step.get('tier')}) held for human — no autonomous outward action", dry)
            continue
        # (b) execute by mode
        if step["mode"] == "ground":
            cands = _ground_check(cur, r)
            if cands:
                note = ("GROUNDING HOLD — may already exist in corpus: "
                        + "; ".join(f"doc {c[0]} ({c[1][:32]}, match={c[2]})" for c in cands)
                        + ". Verify this is a REAL gap before spending a gather.")
                _set(cur, r, "blocked_governance", note, dry)
            else:
                print(f"  #{r['id']}: ground passed (no corpus match) → advancing to '{steps[cs+1]['name']}'")
                if not dry:
                    steps[cs]["status"] = "done"; steps[cs]["result"] = "grounding: no existing corpus match"
                    audit = _audit(r, "queued", "queued", "ground: confirmed real gap, advancing")
                    cur.execute("""UPDATE work_orders SET steps=%s, current_step=%s, status='queued',
                                     updated_at=now(), audit=%s WHERE id=%s""",
                                (json.dumps(steps), cs + 1, json.dumps(audit), r["id"]))
        elif step["mode"] == "handoff":
            _set(cur, r, "awaiting_handoff",
                 f"awaiting handoff: '{step['name']}' → {step['agent']} (run it, then: supervisor.py complete {r['id']} --result ...)", dry)
        elif step["mode"] == "auto":
            _set(cur, r, "blocked_governance",
                 f"auto step '{step['name']}' not supported in v1 (Phase 3 adapter) — fail-closed", dry)
        else:
            _set(cur, r, "failed", f"unknown mode '{step['mode']}'", dry)
    return 0


def _set(cur, order, to, note, dry):
    frm = order["status"]
    print(f"  #{order['id']}: {frm} → {to}  ({note})")
    if dry:
        return
    audit = _audit(order, frm, to, note)
    cur.execute("UPDATE work_orders SET status=%s, updated_at=now(), audit=%s WHERE id=%s",
                (to, json.dumps(audit), order["id"]))


def main():
    ap = argparse.ArgumentParser(description="Supervisor v1 — work-order state machine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enqueue"); e.add_argument("--kind", required=True); e.add_argument("--matter")
    e.add_argument("--title"); e.add_argument("--by", default="operator")
    l = sub.add_parser("list"); l.add_argument("--awaiting", action="store_true")
    s = sub.add_parser("status"); s.add_argument("id", nargs="?", type=int)
    c = sub.add_parser("complete"); c.add_argument("id", type=int); c.add_argument("--result", required=True)
    rs = sub.add_parser("resolve"); rs.add_argument("id", type=int); rs.add_argument("--note", required=True)
    cn = sub.add_parser("cancel"); cn.add_argument("id", type=int); cn.add_argument("--reason", required=True)
    t = sub.add_parser("tick"); t.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if a.cmd == "enqueue":
            rc = cmd_enqueue(cur, a.kind, a.matter, a.title, a.by)
        elif a.cmd == "list":
            rc = cmd_list(cur, a.awaiting)
        elif a.cmd == "status":
            rc = cmd_status(cur, a.id)
        elif a.cmd == "complete":
            rc = cmd_complete(cur, a.id, a.result)
        elif a.cmd == "resolve":
            rc = cmd_resolve(cur, a.id, a.note)
        elif a.cmd == "cancel":
            rc = cmd_cancel(cur, a.id, a.reason)
        elif a.cmd == "tick":
            rc = cmd_tick(cur, a.dry)
        else:
            rc = 2
        conn.commit()
    except Exception as ex:
        conn.rollback()
        print(f"error: {ex}")
        rc = 1
    finally:
        conn.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
