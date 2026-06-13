#!/usr/bin/env python3
"""anthropic_spend_bridge.py — make n8n's Anthropic spend VISIBLE to cost_governor.

WHY THIS EXISTS (the outage it prevents):
  The Leo simulator (and any n8n workflow) calls Anthropic on the SHARED key
  THROUGH n8n. cost_governor never saw those tokens (`llm_spend` read $0), so the
  daily cap was blind — which is exactly how the sim silently drained the balance
  and took real Leo/Telegram down. This poller reads n8n's own execution store,
  extracts the REAL tokenUsage from each finished execution, and records it into
  the SAME `llm_spend` table cost_governor already sums. After that, can_afford()
  finally gates on TOTAL burn (Python pipeline + n8n), so the sim physically can
  no longer re-drain the balance once the cap is reached.

HOW n8n STORES IT (validated 2026-06-13 against workflow vSDQv1vfn6627bnA):
  execution_data.data is a FLATTENED reference array (JSON). A dict element holding
  {"tokenUsage": "<idx>"} dereferences to {promptTokens, completionTokens, totalTokens}
  at arr[<idx>]. One execution may contain several tokenUsage holders (one per LLM
  round in a tool-use loop) — each is a separate billable call.

RUN:
  python3 anthropic_spend_bridge.py --dry    # parse recent execs + PRINT, record NOTHING
  python3 anthropic_spend_bridge.py          # process new execs since cursor, record to llm_spend

Idempotent: a cursor (max processed execution id) in `spend_bridge_state` means each
run only handles new executions; first-ever run starts at the current max so it accounts
spend going FORWARD (it does not backfill old executions as today's spend).
"""
import os
import sys
import json

import psycopg2

sys.path.insert(0, "/root/landtek/scripts")
import cost_governor as cg  # reuse price() + record() + the llm_spend schema

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
BATCH = int(os.environ.get("SPEND_BRIDGE_BATCH", "1000"))
SOURCE = "n8n"            # n8n-side spend (predominantly the simulator)
DEFAULT_MODEL = "claude-sonnet-4-6"   # what the n8n Leo workflow uses


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure_state(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS spend_bridge_state (
        id int PRIMARY KEY DEFAULT 1,
        last_exec_id bigint DEFAULT 0,
        updated_at timestamptz DEFAULT now())""")
    cur.execute("SELECT coalesce(max(id), 0) FROM execution_entity WHERE finished = true")
    cur_max = cur.fetchone()[0]
    # First-ever run only: anchor the cursor at the current max so we account spend
    # going forward, not backfill history into "today".
    cur.execute("""INSERT INTO spend_bridge_state (id, last_exec_id)
                   VALUES (1, %s) ON CONFLICT (id) DO NOTHING""", (cur_max,))


def _get_cursor(cur):
    cur.execute("SELECT last_exec_id FROM spend_bridge_state WHERE id = 1")
    r = cur.fetchone()
    return r[0] if r else 0


def _set_cursor(cur, v):
    cur.execute("UPDATE spend_bridge_state SET last_exec_id = %s, updated_at = now() WHERE id = 1", (v,))


def extract_calls(data):
    """Yield (model, usage_dict) for every LLM call (tokenUsage holder) in one
    execution's flattened data array. usage_dict uses Anthropic-native keys so it
    drops straight into cost_governor.record()."""
    try:
        arr = json.loads(data)
    except Exception:
        return
    if not isinstance(arr, list):
        return

    def deref(v):
        if isinstance(v, str) and v.isdigit() and int(v) < len(arr):
            return arr[int(v)]
        return v

    # model: first thing that looks like a bare model id (avoid prompt prose)
    model = DEFAULT_MODEL
    for el in arr:
        if isinstance(el, str) and el.startswith("claude-") and " " not in el and len(el) < 40:
            model = el
            break

    for el in arr:
        if isinstance(el, dict) and "tokenUsage" in el:
            tu = deref(el["tokenUsage"])
            if not isinstance(tu, dict):
                continue
            pt = deref(tu.get("promptTokens", 0))
            ct = deref(tu.get("completionTokens", 0))
            try:
                pt, ct = int(pt), int(ct)
            except (TypeError, ValueError):
                continue
            if pt or ct:
                yield model, {"input_tokens": pt, "output_tokens": ct}


def run(dry=False):
    c = _conn(); cur = c.cursor()
    if dry:
        cur.execute("""SELECT ee.id, ee."startedAt", ed.data
                         FROM execution_data ed JOIN execution_entity ee ON ee.id = ed."executionId"
                        WHERE ee.finished = true AND ed.data LIKE %s
                        ORDER BY ee.id DESC LIMIT 25""", ("%tokenUsage%",))
    else:
        _ensure_state(cur)
        cursor = _get_cursor(cur)
        cur.execute("""SELECT ee.id, ee."startedAt", ed.data
                         FROM execution_data ed JOIN execution_entity ee ON ee.id = ed."executionId"
                        WHERE ee.finished = true AND ee.id > %s AND ed.data LIKE %s
                        ORDER BY ee.id ASC LIMIT %s""", (cursor, "%tokenUsage%", BATCH))
    rows = cur.fetchall()

    n_exec = n_calls = 0
    total = 0.0
    maxid = 0
    for exid, started, data in rows:
        n_exec += 1
        maxid = max(maxid, exid)
        for model, usage in extract_calls(data):
            cost = cg.price(model, usage)
            total += cost
            n_calls += 1
            if dry:
                print(f"  exec {exid}  {started:%Y-%m-%d %H:%M}  {model}  "
                      f"in={usage['input_tokens']} out={usage['output_tokens']}  -> ${cost:.4f}")
            else:
                cg.record(model, usage, source=SOURCE, ts=started)

    if not dry and rows:
        _set_cursor(cur, maxid)

    tag = "DRY (nothing recorded)" if dry else "recorded to llm_spend"
    print(f"[spend_bridge] execs={n_exec} llm_calls={n_calls} total=${total:.4f} [{tag}]"
          + ("" if dry else f" cursor->{maxid}"))
    cur.close(); c.close()


if __name__ == "__main__":
    run(dry=("--dry" in sys.argv))
