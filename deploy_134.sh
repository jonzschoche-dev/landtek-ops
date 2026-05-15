#!/usr/bin/env bash
# deploy_134.sh — wire the 'Handle Calendar/Notes' Postgres node into Leos Workflow.
# Idempotent. Skips if already deployed.
#
# Fixed from original-pasted version:
#   - python3+psycopg2 are NOT in the postgres container image (pgvector/pg15) but ARE on the
#     host. Switched to running the script on the host with host=172.18.0.3.
#   - Container name is `n8n-n8n-1` per docker-compose naming, not `n8n`.

set -euo pipefail
DEPLOY="134"
echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ==="

PG_CRED=$(docker exec -i n8n-postgres-1 psql -U n8n -d n8n -tAc "
  SELECT id::text FROM credentials_entity
  WHERE type = 'postgres'
  ORDER BY \"updatedAt\" DESC LIMIT 1;" | tr -d '[:space:]')

if [ -z "$PG_CRED" ]; then
  echo "ERROR: no postgres credential found in credentials_entity. Stop." >&2
  exit 2
fi
echo "Using Postgres credential id: $PG_CRED"

python3 - <<PYEOF
import json, sys, uuid, psycopg2

PG_CRED_ID = "${PG_CRED}"
WORKFLOW_NAME = "Leos Workflow"
NEW_NODE_NAME = "Handle Calendar/Notes"

conn = psycopg2.connect(
    dbname="n8n", user="n8n", password="n8npassword", host="172.18.0.3"
)
cur = conn.cursor()

cur.execute("""
  SELECT id, nodes, connections
  FROM workflow_entity
  WHERE name = %s
""", (WORKFLOW_NAME,))
row = cur.fetchone()
if not row:
    print(f"ERROR: workflow {WORKFLOW_NAME!r} not found", file=sys.stderr)
    sys.exit(3)

wf_id, nodes, connections = row
nodes = nodes if isinstance(nodes, list) else json.loads(nodes)
connections = connections if isinstance(connections, dict) else json.loads(connections)

if any(n.get("name") == NEW_NODE_NAME for n in nodes):
    print(f"{NEW_NODE_NAME} already present — skipping.")
    sys.exit(0)

parse_pos = [800, 400]
for n in nodes:
    if n.get("name") == "Parse Agent1":
        parse_pos = list(n.get("position", parse_pos))
        break

new_node = {
    "id": str(uuid.uuid4()),
    "name": NEW_NODE_NAME,
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [parse_pos[0] + 240, parse_pos[1] + 200],
    "parameters": {
        "operation": "executeQuery",
        "query": "SELECT leo_handle_output(\$1::jsonb) AS leo_handle_result;",
        "options": {
            "queryReplacement": "={{ JSON.stringify(\$json) }}"
        }
    },
    "credentials": {
        "postgres": {
            "id": PG_CRED_ID,
            "name": "Postgres (Leos)"
        }
    }
}

nodes.append(new_node)

if "Parse Agent1" not in connections:
    connections["Parse Agent1"] = {"main": [[]]}
if "main" not in connections["Parse Agent1"]:
    connections["Parse Agent1"]["main"] = [[]]
if not connections["Parse Agent1"]["main"]:
    connections["Parse Agent1"]["main"].append([])

connections["Parse Agent1"]["main"][0].append({
    "node": NEW_NODE_NAME,
    "type": "main",
    "index": 0
})

cur.execute("""
  UPDATE workflow_entity
  SET nodes = %s::jsonb, connections = %s::jsonb, "updatedAt" = now()
  WHERE id = %s
""", (json.dumps(nodes), json.dumps(connections), wf_id))
conn.commit()
print(f"OK: appended {NEW_NODE_NAME} (id={new_node['id']}) and Parse Agent1 connection.")
PYEOF

docker restart n8n-n8n-1
echo "Waiting 10s for n8n to come back up..."
sleep 10
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'n8n|postgres'

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: append Handle Calendar/Notes Postgres node to Leos Workflow + Parse Agent1 wiring" || true

echo
echo "=== deploy_${DEPLOY} complete ==="
echo
echo "Final manual step: open Leos Workflow in n8n UI, click 'Publish' to promote the draft to live."
echo "Then send a Telegram test message:"
echo "  'Save: court hearing June 30 at 9am Naga RTC' — expect 'Logged: ... [event:pending]'"
echo "  'What's on my calendar?' — expect bulleted list of upcoming events"
