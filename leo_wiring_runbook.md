# LEO WIRING RUNBOOK — apply the discernment architecture into live Leo

Apply when the VPS is reachable again. All steps are **snapshot-first** and reversible. The
architecture itself (Constitution, protocol, gate, remediate) is already built + committed
(deploys 490–493); this runbook only connects it to the live n8n workflow + leo-tools.

**Token profile of the wired result:** ~400 fixed tokens (the protocol) on calls that actually
happen, + small on-demand retrieval; gate + remediate are **$0** (deterministic). No Constitution
dump. Nothing here re-enables the simulator (the real money pit — keep it dead).

---

## STEP 0 — snapshot first (rollback insurance)

The sim safety gates (S1–S4, S14, the chatId sim-guard) live in this same workflow and MUST NOT
be disturbed. Snapshot before any edit:

```bash
python3 /root/landtek/scripts/leo_snapshot.py            # or the existing snapshot path →
# writes nodes JSON to leo_workflow_snapshots (see CLAUDE.md). Note the snapshot id for rollback.
```

Rollback if anything regresses: `python3 scripts/leo_proposal_apply.py --rollback <snap_id>`.

---

## STEP 1 — systemMessage prepend (the retrieve-before discipline) · LOWEST RISK

In the AI-Agent node's `systemMessage`, **prepend** the block from `leo_discernment_protocol.md`
(the ``` fenced section). Single text field; no topology change. Do **not** paste the Constitution
body — that's the 5K-token-per-call anti-pattern. Grounding comes on demand (Step 2/3).

Verify after: the four sim rules (S1–S4) and S14 text are still present in the systemMessage.

---

## STEP 2 — leo-tools gate endpoint ✅ BUILT + VERIFIED (deploy_617)

**Done.** `/api/answer_gate` is live in `leo_tools/server.py` (uses the local `db()` helper). Verified on
the box: `{"text":"Balane paid 5M [doc:99999]."}` → `verdict:fail` + `final_text:"I don't have a verified
record to answer that."`; a clean line passes through unchanged. Steps 1 & 3 (the live n8n edits) remain
operator-applied. Original build note below:

### (original — so n8n can call the $0 gate over HTTP)

n8n Code nodes are JS; the gate is Python — so expose it as an endpoint and call it. Add to
`leo_tools/server.py` (follows the existing `/api/*` pattern):

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import leo_answer_gate as _gate
import psycopg2

@app.route("/api/answer_gate", methods=["POST"])
def answer_gate():
    data = request.get_json(force=True) or {}
    text = data.get("text", "")
    conn = psycopg2.connect(_gate.DSN)
    try:
        cur = conn.cursor()
        res = _gate.gate(cur, text)
        # deterministic, $0 fail-path: ship grounded-only rewrite, never an LLM regen
        res["final_text"] = text if res["verdict"] == "pass" else _gate.remediate(cur, text, res)
        return jsonify(res)
    finally:
        conn.close()
```

Then restart leo-tools: `systemctl restart leo-tools` (or the service name on the box). Test:
```bash
curl -s localhost:8765/api/answer_gate -H 'Content-Type: application/json' \
  -d '{"text":"Balane paid 5M [doc:99999]."}' | python3 -m json.tool
# expect verdict=fail + final_text = grounded-only rewrite
```

## STEP 3 — n8n: gate node between the AI-Agent and the Telegram-send · TOPOLOGY CHANGE

Insert an **HTTP Request** node after the AI-Agent output, before the Telegram-send node:
- POST `http://127.0.0.1:8765/api/answer_gate`, body `{ "text": "{{ $json.output }}" }`
- Map the Telegram-send `text` to `{{ $json.final_text }}` (the gate's grounded-only result).
- Keep the existing **chatId sim-guard** wrap on the send node intact (rewrites chatId→'0' for
  999000* senders). Do not remove it.

Net effect: every reply passes the $0 gate; a fabricated cite or ungrounded cascade is stripped
deterministically before send — no LLM regeneration, no extra tokens.

---

## Order / risk

- **Step 1 alone** = ~80% of the value, near-zero risk (one field). Do it first; verify sim rules intact.
- **Steps 2–3** = the enforcement teeth. Step 3 is the only topology change — do it with the snapshot taken.
- Leo stays inert until `ANTHROPIC_API_KEY` has balance, so each step can be applied + verified with
  no live traffic and no token spend.
