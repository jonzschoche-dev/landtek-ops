#!/usr/bin/env bash
# deploy_137_report_pipeline.sh — wire the report-generation path into Leos Workflow.
#
# Adds two nodes after Parse Agent1:
#   1. "Generate Report" — Execute Command node that runs generate_report.py
#      when Parse Agent1 emits response_type IN ('report','summary_with_report').
#   2. "Telegram Send Document" — sends the generated file to Jonathan's chat.
#
# Idempotent: skips injection if nodes already exist.

set -euo pipefail
DEPLOY="137"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

PG_CRED=$(docker exec -i n8n-postgres-1 psql -U n8n -d n8n -tAc "
  SELECT id::text FROM credentials_entity
   WHERE type = 'postgres'
   ORDER BY \"updatedAt\" DESC LIMIT 1;" | tr -d '[:space:]')
echo "Using Postgres credential id: $PG_CRED"

TG_CRED=$(docker exec -i n8n-postgres-1 psql -U n8n -d n8n -tAc "
  SELECT id::text FROM credentials_entity
   WHERE type = 'telegramApi'
   ORDER BY \"updatedAt\" DESC LIMIT 1;" | tr -d '[:space:]')
echo "Using Telegram credential id: $TG_CRED"

python3 - <<PYEOF
import json, sys, uuid, psycopg2
PG_CRED_ID = "${PG_CRED}"
TG_CRED_ID = "${TG_CRED}"

conn = psycopg2.connect(dbname="n8n", user="n8n", password="n8npassword", host="172.18.0.3")
cur = conn.cursor()
cur.execute('SELECT id, nodes, connections FROM workflow_entity WHERE name=%s', ("Leos Workflow",))
row = cur.fetchone()
if not row: sys.exit("workflow not found")
wf_id, nodes, conns = row
nodes = nodes if isinstance(nodes, list) else json.loads(nodes)
conns = conns if isinstance(conns, dict) else json.loads(conns)

EXISTING = {n.get("name") for n in nodes}
if "Generate Report" in EXISTING and "Telegram Send Report" in EXISTING:
    print("Both nodes already present — skipping.")
    sys.exit(0)

parse_pos = next((n.get("position", [800,400]) for n in nodes if n.get("name") == "Parse Agent1"), [800,400])
gen_id   = str(uuid.uuid4())
send_id  = str(uuid.uuid4())

generate_node = {
    "id": gen_id,
    "name": "Generate Report",
    "type": "n8n-nodes-base.executeCommand",
    "typeVersion": 1,
    "position": [parse_pos[0] + 240, parse_pos[1] + 380],
    "parameters": {
        "command": "export DATABASE_URL=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n && python3 /root/landtek/generate_report.py {{ \$json.report_query.split(':')[0] }} {{ \$json.report_query.split(':')[1] }}"
    }
}

send_node = {
    "id": send_id,
    "name": "Telegram Send Report",
    "type": "n8n-nodes-base.telegram",
    "typeVersion": 1.2,
    "position": [parse_pos[0] + 460, parse_pos[1] + 380],
    "parameters": {
        "resource": "message",
        "operation": "sendDocument",
        "chatId": "={{ \$('Telegram Trigger').first().json.message.chat.id }}",
        "binaryData": False,
        "additionalFields": {
            "caption": "={{ \$('Parse Agent1').first().json.reply_text }}"
        },
        "file": "={{ JSON.parse(\$('Generate Report').first().json.stdout).filepath }}"
    },
    "credentials": {"telegramApi": {"id": TG_CRED_ID, "name": "Telegram (Leo)"}}
}

new_nodes = []
if "Generate Report" not in EXISTING: new_nodes.append(generate_node)
if "Telegram Send Report" not in EXISTING: new_nodes.append(send_node)
nodes.extend(new_nodes)

# Wire: Parse Agent1.main[0] → Generate Report → Telegram Send Report
# (Parse Agent1 already has multiple downstream nodes — we ADD, don't replace.)
conns.setdefault("Parse Agent1", {}).setdefault("main", [[]])
if not conns["Parse Agent1"]["main"]:
    conns["Parse Agent1"]["main"].append([])
conns["Parse Agent1"]["main"][0].append({"node": "Generate Report", "type": "main", "index": 0})

conns.setdefault("Generate Report", {"main": [[]]})
if not conns["Generate Report"]["main"]:
    conns["Generate Report"]["main"] = [[]]
conns["Generate Report"]["main"][0].append({"node": "Telegram Send Report", "type": "main", "index": 0})

cur.execute("""UPDATE workflow_entity SET nodes=%s::jsonb, connections=%s::jsonb,
                  "updatedAt"=now() WHERE id=%s""",
            (json.dumps(nodes), json.dumps(conns), wf_id))
conn.commit()
print(f"OK: appended {len(new_nodes)} nodes; report pipeline wired.")
print("NOTE: Generate Report node uses a NAIVE 'report:identifier' split.")
print("      Leo must produce report_query like 'title:T-4497' or 'matter:MWK-CV26360'.")
print("      n8n will only route to this branch when Leo sets response_type IN (report, summary_with_report).")
print("      Add an IF node between Parse Agent1 and Generate Report to gate on response_type !== 'message'.")
PYEOF

docker restart n8n-n8n-1
echo "Waiting 10s for n8n to come back up..."
sleep 10
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'n8n|postgres'

echo
echo "=== deploy_${DEPLOY} complete ==="
echo "Manual steps remaining in n8n UI:"
echo "  1. Add an IF node between Parse Agent1 and Generate Report:"
echo "       condition: {{ \$json.response_type !== 'message' && \$json.report_query }}"
echo "  2. Paste the prompt addition from /root/landtek/drafts/leo_prompt_addition_report_routing.md"
echo "     into Agent1's System Message"
echo "  3. Publish the workflow"
