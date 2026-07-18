#!/usr/bin/env python3
"""agent_stack_sim.py — grounded simulator that populates the agents' tables.

Drives the REAL deploy_938 pipeline end to end:

    seed probes FROM the DB → run_inquiry(go=True) → writeback atoms
    → agent_work_queue → drain each agent's compelled hook
    → measure what each agent's owned tables actually gained

Anti-trap doctrine (P0 — memory: simulator anti-trap):
  * NO synthetic facts. Every probe is seeded from rows already in the DB;
    its expected answer IS those rows' values. If the stack can't surface a
    value the DB provably holds, that's a findability gap — real signal.
  * Measure, don't model. Grading is mechanical: expected-substring present,
    forbidden-substring absent (cross-client leak tripwire), held vs answered.
    No LLM judge anywhere. $0 per cycle.
  * Sim safety (mirrors Leo sim rules): channel='sim', sender in the 999000
    range, and the operator-notify path (_enqueue_human_review → Telegram to
    Jonathan) is neutralized for sim inquiries — swallowed pings are counted,
    never sent. S14 stays intact.

Usage (on the VPS):
    python3 scripts/agent_stack_sim.py --once --probes 12       # one cycle
    python3 scripts/agent_stack_sim.py --once --dry             # probes only, no writeback/drain
    python3 scripts/agent_stack_sim.py --once --no-drain        # writeback but skip agent drains
    python3 scripts/agent_stack_sim.py --report                 # recent cycles + worst probes
    python3 scripts/agent_stack_sim.py --loop --interval 21600  # daemon mode
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inquiry_stack as IQ  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

SIM_CHANNEL = "sim"
SIM_USER_ID = "999000101"          # inquiry-stack sim sender (999000* = sim range)
SIM_CLIENT = "MWK-001"

# Cross-client leak tripwires — an MWK answer must never surface these
FORBIDDEN_DEFAULT = ["Paracale", "LTC-001", "NIBDC", "Inocalla"]

# Matters whose tails inquiry_stack._matter_hints recognizes (deterministic scoping)
ARTA_HINTED = (
    "MWK-ARTA-0747", "MWK-ARTA-0690", "MWK-ARTA-0792",
    "MWK-ARTA-1321", "MWK-ARTA-1210",
)

# Full-pass hooks: one drain per cycle is a complete run; more is redundant
DRAIN_LIMITS = {"doc_populate": 1, "contradiction": 1}
DRAIN_DEFAULT_LIMIT = 4
DRAIN_SKIP = {"inquiry_stack"}     # no self-reentry


# ── Sim safety: swallow operator notifications ───────────────────────────────

_suppressed = {"n": 0}


def _sim_enqueue_human_review(cur, inquiry_id, message, ans):
    """Sim replacement for IQ._enqueue_human_review — record, never ping.

    Held inquiries still land in agent_work_queue tagged sim_human_pass so the
    signal survives, but no Telegram to Jonathan and no work_orders spam.
    """
    _suppressed["n"] += 1
    try:
        cur.execute(
            """
            INSERT INTO agent_work_queue (agent_key, event_type, payload, inquiry_id, status)
            VALUES ('sim_observer', 'sim_human_pass', %s::jsonb, %s, 'done')
            """,
            (json.dumps({
                "message": (message or "")[:300],
                "score": (ans.get("human_pass") or {}).get("score"),
                "suppressed_operator_notify": True,
            }), inquiry_id),
        )
    except Exception:
        pass
    return 0


IQ._enqueue_human_review = _sim_enqueue_human_review


# ── DB helpers ───────────────────────────────────────────────────────────────

def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def owned_tables(cur) -> list[str]:
    cur.execute("SELECT owns_tables FROM agent_mandates WHERE active")
    seen: list[str] = []
    for r in cur.fetchall():
        for t in (r["owns_tables"] or []):
            if t not in seen:
                seen.append(t)
    out = []
    for t in seen:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS ok", (t,))
        if cur.fetchone()["ok"]:
            out.append(t)
    return out


def table_counts(cur, tables: list[str]) -> dict[str, int]:
    counts = {}
    for t in tables:
        cur.execute(f"SELECT count(*)::bigint AS n FROM {t}")  # names from agent_mandates only
        counts[t] = int(cur.fetchone()["n"])
    return counts


# ── Probe builders (every probe seeded from live rows) ───────────────────────

def _probe(kind, message, expected=None, forbidden=None, seed=None):
    return {
        "probe_kind": kind,
        "message": message,
        "client_code": SIM_CLIENT,
        "expected": expected or [],
        "forbidden": (forbidden if forbidden is not None else list(FORBIDDEN_DEFAULT)),
        "seed": seed or {},
    }


def probe_arta_ctn(cur):
    cur.execute(
        """
        SELECT matter_code, ctns FROM matter_brief
        WHERE matter_code = ANY(%s) AND coalesce(array_length(ctns, 1), 0) > 0
        ORDER BY random() LIMIT 1
        """,
        (list(ARTA_HINTED),),
    )
    r = cur.fetchone()
    if not r:
        return None
    tail = r["matter_code"].rsplit("-", 1)[-1]
    # ctns[] aggregates every CTN mentioned in the matter's docs — the
    # grounded expectation is the full-form CTN whose tail IS this case.
    own = [
        str(v) for v in (r["ctns"] or [])
        if re.fullmatch(r"20\d{2}-\d{4}-\d{3,4}", str(v)) and str(v).endswith(tail)
    ]
    if not own:
        return None
    return _probe(
        "arta_ctn",
        f"What is the CTN for ARTA case {tail}?",
        expected=[own[0]],
        seed={"matter": r["matter_code"], "from": "matter_brief.ctns"},
    )


def probe_op_docket(cur):
    cur.execute(
        """
        SELECT df.value_norm, df.doc_id
        FROM document_fields df
        JOIN document_matter_links l ON l.doc_id = df.doc_id
        WHERE df.field_kind = 'mro_ref' AND l.matter_code = 'MWK-OP-PETITION'
        ORDER BY (df.value_norm LIKE '050526%%') DESC, random()
        LIMIT 1
        """
    )
    r = cur.fetchone()
    if not r:
        return None
    return _probe(
        "op_docket",
        "What is the docket reference for the OP petition?",
        expected=[r["value_norm"]],
        seed={"doc_id": r["doc_id"], "from": "document_fields.mro_ref"},
    )


def probe_title_status(cur):
    cur.execute(
        r"""
        SELECT tct_number FROM titles
        WHERE case_file LIKE 'MWK%%'
          AND tct_number ~ '^T-\d{4,7}$'
          AND coalesce(status, '') NOT IN
              ('invalid','alias','duplicate','not_a_title','form_serial','out_of_scope')
        ORDER BY random() LIMIT 1
        """
    )
    r = cur.fetchone()
    if not r:
        return None
    tct = r["tct_number"]
    return _probe(
        "title_status",
        f"What is the status of title {tct}?",
        expected=[tct],
        seed={"from": "titles"},
    )


def probe_title_inventory(cur):
    try:
        inv = IQ._fetch_title_inventory(cur, SIM_CLIENT, status_filter="living")
    except Exception:
        return None
    # The dose-aware render names the ACTIVE slice in the primary emission —
    # expect those (other slices are follow-up words, probed separately).
    active = [
        r["tct_number"] for r in (inv.get("rows") or [])
        if (r.get("status") or "").lower() == "active" and r.get("tct_number")
    ]
    if not active:
        return None
    expected = random.sample(active, min(2, len(active)))
    return _probe(
        "title_inventory",
        "List the titles for MWK",
        expected=expected,
        seed={"living_count": inv.get("count"), "from": "titles registry (living)"},
    ) | {"max_len": 340}


def probe_list_followup(cur):
    cur.execute(
        r"""
        SELECT tct_number FROM titles
        WHERE case_file LIKE 'MWK%%' AND coalesce(status,'') ILIKE 'active'
          AND tct_number ~ '^T-\d{3,7}$'
        ORDER BY random() LIMIT 1
        """
    )
    r = cur.fetchone()
    if not r:
        return None
    return _probe(
        "list_followup",
        "Where is the list?",
        expected=[r["tct_number"]],
        forbidden=FORBIDDEN_DEFAULT + ["MRO", "Malacañang"],
        seed={"from": "titles (active); guards the 2026-07-17 follow-up failure"},
    ) | {"max_len": 340}


def probe_tagalog_update(cur):
    # Grounded expectation: matter_brief headlines exist → answer must come
    # from them (or hold honestly) — NEVER the Malacañang-ref spam this ask
    # produced on 2026-07-17.
    return _probe(
        "tagalog_update",
        "Ano po ang pinakabagong update sa titulo natin?",
        expected=[],
        forbidden=FORBIDDEN_DEFAULT + ["MRO", "Malacañang"],
        seed={"from": "invariant: no ref-dump on unmatched phrasing"},
    )


def probe_who_is(cur):
    cur.execute(
        r"""
        SELECT party_name FROM matter_parties
        WHERE matter_code LIKE 'MWK%%'
          AND party_name ~ '^[A-Z][a-z''\-]+(\.? [A-Z][A-Za-z''\-]+){1,3}\.?$'
          AND length(party_name) BETWEEN 6 AND 60
        ORDER BY random() LIMIT 1
        """
    )
    r = cur.fetchone()
    if not r:
        return None
    name = " ".join((r["party_name"] or "").split())
    surname = name.split()[-1]
    return _probe(
        "who_is",
        f"Who is {name}?",
        expected=[surname],
        seed={"party": name, "from": "matter_parties"},
    )


def probe_separation_guard(cur):
    return _probe(
        "separation_guard",
        "Give me a summary of the titles on record",
        expected=[],
        seed={"from": "invariant: client separation"},
    )


BUILDERS = (
    probe_arta_ctn,
    probe_op_docket,
    probe_title_status,
    probe_title_inventory,
    probe_who_is,
    probe_separation_guard,
    probe_list_followup,
    probe_tagalog_update,
)


def seed_probes(cur, n: int) -> list[dict]:
    probes, i, misses = [], 0, 0
    while len(probes) < n and misses < len(BUILDERS) * 2:
        p = BUILDERS[i % len(BUILDERS)](cur)
        i += 1
        if p is None:
            misses += 1
            continue
        probes.append(p)
    return probes


# ── Grading (mechanical only) ────────────────────────────────────────────────

def grade_probe(cur, probe: dict, res: dict) -> dict:
    text = (res.get("text") or "")
    low = text.lower()
    via = (res.get("via") or "").split(":")[-1]
    leaked = [f for f in probe["forbidden"] if f.lower() in low]
    missing = [e for e in probe["expected"] if e.lower() not in low]
    if leaked:
        grade = "leak"
    elif via in ("held_unclear", "pass_to_human") or res.get("pass_to_human"):
        grade = "held_miss" if probe["expected"] else "held_ok"
    elif missing:
        # Distinguish "stack found it but the distilled emission dropped it"
        # (emission_miss) from a true findability failure (answered_miss).
        grade = "answered_miss"
        if res.get("inquiry_id"):
            try:
                cur.execute(
                    "SELECT source_refs::text AS s FROM inquiry_runs WHERE id = %s",
                    (res["inquiry_id"],),
                )
                row = cur.fetchone()
                blob = (row["s"] or "").lower() if row else ""
                if blob and all(m.lower() in blob for m in missing):
                    grade = "emission_miss"
            except Exception:
                pass
    else:
        grade = "hit"
    # Dose check: an answer that exceeds the channel cap gets truncated on the
    # phone — the user never sees the tail. Correct-but-oversized is a miss.
    max_len = probe.get("max_len")
    if grade == "hit" and max_len and len(text) > max_len:
        grade = "answered_miss"
        missing = missing + [f"dose<={max_len} (got {len(text)})"]
    return {"grade": grade, "missing": missing, "leaked": leaked, "via": via}


# ── Retention sweep (sim footprint only) ─────────────────────────────────────

def retention_sweep(cur, inq_days: int = 14, log_days: int = 90) -> dict:
    """Prune the sim's own footprint so quiet cycles don't grow forever.

    NEVER touches real-channel inquiries or the grounded writebacks the sim
    produced (document_fields / matter_facts rows are the point of the sim).
    Sim rows are double-keyed (channel='sim' AND 999000* sender) so a real
    inquiry can never match. inquiry_scrutiny / inquiry_answer_atoms cascade
    from inquiry_runs; agent_sim_probes cascade from agent_sim_cycles.
    """
    out = {}
    # Queue rows tied to old sim inquiries — the FK is ON DELETE SET NULL, so
    # delete them first while the join still resolves.
    cur.execute(
        """
        DELETE FROM agent_work_queue q
        USING inquiry_runs r
        WHERE q.inquiry_id = r.id
          AND r.channel = 'sim' AND r.channel_user_id LIKE '999000%%'
          AND r.created_at < now() - make_interval(days => %s)
        """,
        (inq_days,),
    )
    out["agent_work_queue"] = cur.rowcount
    # sim_observer rows are sim-only by construction (suppressed-notify audit)
    cur.execute(
        """
        DELETE FROM agent_work_queue
        WHERE agent_key = 'sim_observer'
          AND created_at < now() - make_interval(days => %s)
        """,
        (inq_days,),
    )
    out["agent_work_queue"] += cur.rowcount
    cur.execute(
        """
        DELETE FROM inquiry_runs
        WHERE channel = 'sim' AND channel_user_id LIKE '999000%%'
          AND created_at < now() - make_interval(days => %s)
        """,
        (inq_days,),
    )
    out["inquiry_runs"] = cur.rowcount
    cur.execute(
        "DELETE FROM agent_sim_cycles WHERE started_at < now() - make_interval(days => %s)",
        (log_days,),
    )
    out["agent_sim_cycles"] = cur.rowcount
    return out


# ── Cycle ────────────────────────────────────────────────────────────────────

def run_cycle(n_probes: int, drain: bool, dry: bool,
              retain_days: int = 14, log_retain_days: int = 90) -> dict:
    c = _conn()
    cur = _cur(c)
    _suppressed["n"] = 0

    tables = owned_tables(cur)
    before = table_counts(cur, tables)

    cur.execute(
        "INSERT INTO agent_sim_cycles (n_probes, notes) VALUES (%s, %s) RETURNING id",
        (0, "dry" if dry else None),
    )
    cycle_id = cur.fetchone()["id"]

    probes = seed_probes(cur, n_probes)
    tally = {"hit": 0, "answered_miss": 0, "emission_miss": 0,
             "held_ok": 0, "held_miss": 0, "leak": 0, "error": 0}

    for p in probes:
        t0 = time.time()
        try:
            res = IQ.run_inquiry(
                message=p["message"],
                client_code=p["client_code"],
                channel=SIM_CHANNEL,
                channel_user_id=SIM_USER_ID,
                go=not dry,
                drain=False,
            )
            g = grade_probe(cur, p, res)
            inquiry_id = res.get("inquiry_id")
        except Exception as e:
            res = {"text": f"{type(e).__name__}: {e}", "via": "error"}
            g = {"grade": "error", "missing": p["expected"], "leaked": [], "via": "error"}
            inquiry_id = None
        ms = int((time.time() - t0) * 1000)
        tally[g["grade"]] = tally.get(g["grade"], 0) + 1
        cur.execute(
            """
            INSERT INTO agent_sim_probes
                (cycle_id, probe_kind, message, client_code, expected, forbidden,
                 seed, inquiry_id, answer_via, grade, missing, leaked, duration_ms)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
            """,
            (
                cycle_id, p["probe_kind"], p["message"], p["client_code"],
                p["expected"], p["forbidden"], json.dumps(p["seed"]),
                inquiry_id, g["via"], g["grade"], g["missing"], g["leaked"], ms,
            ),
        )
        print(f"  [{g['grade']:>13}] {p['probe_kind']:<17} {p['message'][:70]}", flush=True)

    # Drain every active agent's queue — THIS is what populates their tables
    drain_notes = []
    if drain and not dry:
        cur.execute("SELECT agent_key FROM agent_mandates WHERE active ORDER BY agent_key")
        for r in cur.fetchall():
            key = r["agent_key"]
            if key in DRAIN_SKIP:
                continue
            limit = DRAIN_LIMITS.get(key, DRAIN_DEFAULT_LIMIT)
            try:
                notes = IQ.drain_agent(cur, key, limit=limit, go=True)
            except Exception as e:
                notes = [{"agent": key, "note": f"drain_error:{type(e).__name__}:{e}"}]
            drain_notes.extend(notes)
            for n in notes:
                print(f"  [drain] {key}: {str(n.get('note'))[:90]}", flush=True)

    after = table_counts(cur, tables)
    deltas = {
        t: {"before": before[t], "after": after[t], "delta": after[t] - before[t]}
        for t in tables
    }

    # Self-pruning: sweep AFTER the delta counts so growth numbers stay honest
    sweep = {}
    if not dry:
        sweep = retention_sweep(cur, retain_days, log_retain_days)

    cur.execute(
        """
        UPDATE agent_sim_cycles SET
            finished_at = now(),
            n_probes = %s, n_hit = %s, n_answered_miss = %s,
            n_held = %s, n_leak = %s, n_error = %s,
            suppressed_notifies = %s,
            table_deltas = %s::jsonb, drain_notes = %s::jsonb,
            notes = %s
        WHERE id = %s
        """,
        (
            len(probes), tally["hit"], tally["answered_miss"] + tally["emission_miss"],
            tally["held_ok"] + tally["held_miss"], tally["leak"], tally["error"],
            _suppressed["n"],
            json.dumps(deltas), json.dumps(drain_notes, default=str),
            ("sweep: " + json.dumps(sweep)) if sweep else None,
            cycle_id,
        ),
    )

    if sweep and any(sweep.values()):
        print(f"  [sweep] pruned sim footprint: {sweep}")
    grew = {t: d["delta"] for t, d in deltas.items() if d["delta"]}
    print(f"\ncycle {cycle_id}: {len(probes)} probes — "
          f"{tally['hit']} hit, {tally['answered_miss']} answered-miss, "
          f"{tally['emission_miss']} emission-miss, "
          f"{tally['held_miss']} held-miss, {tally['held_ok']} held-ok, "
          f"{tally['leak']} LEAK, {tally['error']} error; "
          f"operator pings suppressed: {_suppressed['n']}")
    print(f"tables populated: {grew if grew else '(no growth this cycle)'}")

    cur.close()
    c.close()
    return {"cycle_id": cycle_id, "tally": tally, "deltas": deltas}


def report():
    c = _conn()
    cur = _cur(c)
    cur.execute("SELECT * FROM agent_sim_recent")
    rows = cur.fetchall()
    if not rows:
        print("no sim cycles yet")
        return
    print("recent cycles:")
    for r in rows:
        print(f"  #{r['id']} {r['started_at']:%Y-%m-%d %H:%M} — "
              f"{r['n_probes']} probes, {r['hit_pct'] or 0}% hit, "
              f"{r['n_held']} held, {r['n_leak']} leak, "
              f"+{r['rows_populated'] or 0} rows, took {r['took']}")
    cur.execute(
        """
        SELECT probe_kind, grade, message, missing, leaked
        FROM agent_sim_probes
        WHERE cycle_id = (SELECT max(id) FROM agent_sim_cycles)
          AND grade NOT IN ('hit', 'held_ok')
        ORDER BY id
        """
    )
    bad = cur.fetchall()
    if bad:
        print("\nlast cycle — non-hit probes:")
        for b in bad:
            detail = f" missing={b['missing']}" if b["missing"] else ""
            detail += f" LEAKED={b['leaked']}" if b["leaked"] else ""
            print(f"  [{b['grade']}] {b['probe_kind']}: {b['message'][:70]}{detail}")
    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="run one cycle (default)")
    ap.add_argument("--loop", action="store_true", help="run forever")
    ap.add_argument("--interval", type=int, default=21600, help="loop sleep seconds")
    ap.add_argument("--probes", type=int, default=12)
    ap.add_argument("--no-drain", action="store_true", help="skip agent drains")
    ap.add_argument("--dry", action="store_true", help="no writeback, no drain")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--retain-days", type=int, default=14,
                    help="sim inquiries older than this are pruned each cycle")
    ap.add_argument("--log-retain-days", type=int, default=90,
                    help="agent_sim_cycles/probes retention horizon")
    ap.add_argument("--sweep", action="store_true",
                    help="run only the retention sweep, no probes")
    a = ap.parse_args()

    if a.report:
        report()
        return
    if a.sweep:
        c = _conn()
        cur = _cur(c)
        print("sweep:", retention_sweep(cur, a.retain_days, a.log_retain_days))
        cur.close()
        c.close()
        return
    if a.loop:
        while True:
            run_cycle(a.probes, drain=not a.no_drain, dry=a.dry,
                      retain_days=a.retain_days, log_retain_days=a.log_retain_days)
            time.sleep(max(a.interval, 300))
    else:
        run_cycle(a.probes, drain=not a.no_drain, dry=a.dry,
                  retain_days=a.retain_days, log_retain_days=a.log_retain_days)


if __name__ == "__main__":
    main()
