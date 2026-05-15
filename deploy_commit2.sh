#!/usr/bin/env bash
# Leo v6 — Commit 2: add query_documents structured-query tool
set -euo pipefail

BACKUP=/root/landtek/backups/$(date +%Y-%m-%d-leo-v6)
mkdir -p "$BACKUP"

echo "=== STEP 1: Backup ==="
cp /root/landtek/leo_tools/server.py "$BACKUP/server.py.commit2-before"
docker exec n8n-postgres-1 psql -U n8n -d n8n -tA -c \
  "SELECT row_to_json(w.*) FROM workflow_entity w WHERE id = 'vSDQv1vfn6627bnA';" \
  > "$BACKUP/workflow.commit2-before.json"
echo "  ✓ backups in $BACKUP"

echo ""
echo "=== STEP 2: Append endpoint to server.py (if absent) ==="
if grep -q "def query_documents" /root/landtek/leo_tools/server.py; then
  echo "  endpoint already present — skipping"
else
  cat >> /root/landtek/leo_tools/server.py <<'PYEOF'


@app.route('/api/query_documents')
def query_documents():
    """Structured query over documents table."""
    case_file = request.args.get('case_file', '').strip()
    classification = request.args.get('classification', '').strip()
    year = request.args.get('year', '').strip()
    keyword = request.args.get('keyword', '').strip()
    try:
        limit = min(int(request.args.get('limit', 30)), 100)
    except (TypeError, ValueError):
        limit = 30

    where, params = [], []
    if case_file:
        where.append("case_file = %s"); params.append(case_file)
    if classification:
        where.append("classification ILIKE %s"); params.append(f"%{classification}%")
    if year:
        where.append("(EXTRACT(YEAR FROM doc_date)::text = %s OR smart_filename ILIKE %s OR document_title ILIKE %s)")
        params.extend([year, f"%{year}%", f"%{year}%"])
    if keyword:
        where.append("(extracted_text ILIKE %s OR smart_filename ILIKE %s OR document_title ILIKE %s OR summary ILIKE %s)")
        params.extend([f"%{keyword}%"] * 4)

    wc = (" WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT id, case_file, classification, smart_filename, document_title,
               doc_date, document_date, summary, created_at
        FROM documents{wc}
        ORDER BY COALESCE(doc_date, document_date, created_at) DESC NULLS LAST
        LIMIT %s
    """
    params.append(limit)

    c = db(); cur = c.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close(); c.close()

    items = [{
        "doc_id": r[0], "case_file": r[1], "type": r[2],
        "file": r[3], "title": r[4],
        "date": str(r[5] or r[6] or ''),
        "summary": (r[7] or '')[:400],
        "indexed": str(r[8]),
    } for r in rows]

    return jsonify({
        "filter": {"case_file": case_file, "classification": classification,
                   "year": year, "keyword": keyword, "limit": limit},
        "count": len(items),
        "documents": items,
    })
PYEOF
  echo "  ✓ endpoint appended"
fi

echo ""
echo "=== STEP 3: Python syntax check ==="
python3 -c "import py_compile; py_compile.compile('/root/landtek/leo_tools/server.py', doraise=True)"
echo "  ✓ compiles clean"

echo ""
echo "=== STEP 4: Restart leo-tools service ==="
systemctl restart leo-tools
sleep 3
systemctl is-active leo-tools >/dev/null && echo "  ✓ service active"

echo ""
echo "=== STEP 5: Smoke-test endpoint ==="
RESULT=$(curl -s "http://172.18.0.1:8765/api/query_documents?case_file=MWK-001&classification=Title&limit=5")
COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))")
if [ "$COUNT" -lt 5 ]; then
  echo "  ✗ FAILED — count=$COUNT, expected ≥5"
  echo "  Rolling back server.py..."
  cp "$BACKUP/server.py.commit2-before" /root/landtek/leo_tools/server.py
  systemctl restart leo-tools
  exit 1
fi
echo "  ✓ returns $COUNT Title docs in MWK-001"

echo ""
echo "=== STEP 6: Insert tool node into n8n workflow ==="
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'SQL'
DO $X$
DECLARE has_tool BOOLEAN;
BEGIN
  SELECT EXISTS (
    SELECT 1 FROM workflow_entity, jsonb_array_elements(nodes::jsonb) AS node
    WHERE id = 'vSDQv1vfn6627bnA' AND node->>'name' = 'query_documents'
  ) INTO has_tool;

  IF has_tool THEN
    RAISE NOTICE 'query_documents tool node already exists — skipping';
  ELSE
    UPDATE workflow_entity
    SET nodes = (nodes::jsonb || '[{
      "id": "tool-query_documents",
      "name": "query_documents",
      "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
      "position": [300, -560],
      "typeVersion": 1.1,
      "parameters": {
        "url": "http://172.18.0.1:8765/api/query_documents",
        "method": "GET",
        "sendQuery": true,
        "specifyQuery": "keypair",
        "parametersQuery": {"values": [
          {"name": "case_file", "valueProvider": "modelOptional"},
          {"name": "classification", "valueProvider": "modelOptional"},
          {"name": "year", "valueProvider": "modelOptional"},
          {"name": "keyword", "valueProvider": "modelOptional"},
          {"name": "limit", "valueProvider": "modelOptional"}
        ]},
        "toolDescription": "PRIMARY structured-query tool. Filter documents by case_file (Paracale-001|MWK-001|Owner), classification (Title (TCT/OCT)|Tax Document|Court Filing|Letter|Correspondence|Deed|Receipt|Contract|Email|Demand Letter|Power of Attorney|Notice|Affidavit|Government Submission|Special Power of Attorney|Complaint|Legal Memorandum|Other), year, or keyword. Returns documents ordered most recent first. Use for ANY list / every / all / latest / show me X in case Y question. PREFER this over cross_reference unless the user mentions a specific reference number.",
        "optimizeResponse": false
      }
    }]'::jsonb)::json
    WHERE id = 'vSDQv1vfn6627bnA';
    RAISE NOTICE 'query_documents tool node inserted';
  END IF;
END $X$;
SQL

echo "  ✓ tool node step complete"

echo ""
echo "=== STEP 7: Wire ai_tool connection → AI Agent ==="
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'SQL'
UPDATE workflow_entity
SET connections = jsonb_set(
  COALESCE(connections::jsonb, '{}'::jsonb),
  '{query_documents}',
  '{"ai_tool": [[{"node": "AI Agent", "type": "ai_tool", "index": 0}]]}'::jsonb
)::json
WHERE id = 'vSDQv1vfn6627bnA';
SQL
echo "  ✓ connection added"

echo ""
echo "=== STEP 8: Restart n8n ==="
docker restart n8n-n8n-1
sleep 10
docker ps --filter "name=n8n-n8n" --format "table {{.Names}}\t{{.Status}}"

echo ""
echo "=== STEP 9: Final verification ==="
echo "Tool present in workflow:"
docker exec n8n-postgres-1 psql -U n8n -d n8n -tA -c "
  SELECT EXISTS (
    SELECT 1 FROM workflow_entity, jsonb_array_elements(nodes::jsonb) AS node
    WHERE id = 'vSDQv1vfn6627bnA' AND node->>'name' = 'query_documents'
  );"
echo "Connection present:"
docker exec n8n-postgres-1 psql -U n8n -d n8n -tA -c "
  SELECT (connections::jsonb)->'query_documents' IS NOT NULL
  FROM workflow_entity WHERE id = 'vSDQv1vfn6627bnA';"

echo ""
echo "=========================================="
echo "COMMIT 2 DEPLOY COMPLETE"
echo "=========================================="
echo ""
echo "Now test Leo via Telegram with these 3 questions:"
echo "  1. 'List every TCT in MWK-001'"
echo "  2. 'Latest demand letter in MWK-001'"
echo "  3. 'What is CTN SL-2026-0423-1891 about?'"
echo ""
echo "Pass criteria:"
echo "  Q1 → ~88 docs returned in a clean list with doc_ids"
echo "  Q2 → 1 doc (the 2025-08-18 demand letter), cited with doc_id"
echo "  Q3 → cross_reference called; if 0 results, Leo says so honestly (no Balane invention)"
echo ""
echo "Rollback if needed:"
echo "  cp $BACKUP/server.py.commit2-before /root/landtek/leo_tools/server.py"
echo "  systemctl restart leo-tools"
echo "  # Then restore workflow JSON from $BACKUP/workflow.commit2-before.json"
