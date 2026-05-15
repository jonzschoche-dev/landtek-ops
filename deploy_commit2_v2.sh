#!/usr/bin/env bash
set -euo pipefail
BACKUP=/root/landtek/backups/2026-05-10-leo-v6

echo "=== STEP 1: Revert server.py to pre-commit-2 state ==="
cp "$BACKUP/server.py.commit2-before" /root/landtek/leo_tools/server.py
echo "  ✓ reverted"

echo ""
echo "=== STEP 2: Confirm app.run line ==="
RUN_LINE=$(grep -n "app\.run(" /root/landtek/leo_tools/server.py | head -1 | cut -d: -f1)
if [ -z "$RUN_LINE" ]; then
  echo "  ✗ no app.run() found — server.py uses different startup pattern. STOP and report."
  exit 1
fi
echo "  ✓ app.run() found at line $RUN_LINE"

echo ""
echo "=== STEP 3: Write endpoint to staging file ==="
cat > /tmp/qd_endpoint.py <<'PYEOF'

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
echo "  ✓ endpoint written to /tmp/qd_endpoint.py"

echo ""
echo "=== STEP 4: Insert endpoint BEFORE app.run() ==="
python3 <<PYEOF
src_path = "/root/landtek/leo_tools/server.py"
endpoint_path = "/tmp/qd_endpoint.py"
with open(src_path) as f:
    src = f.read()
with open(endpoint_path) as f:
    endpoint = f.read()
# find the app.run line and insert before it
import re
match = re.search(r'^(\s*)(app\.run\()', src, re.MULTILINE)
if not match:
    raise SystemExit("no app.run found")
insert_at = match.start()
new_src = src[:insert_at] + endpoint + "\n" + src[insert_at:]
# safety: no double-insert
if new_src.count("def query_documents") != 1:
    raise SystemExit(f"insert produced {new_src.count('def query_documents')} copies — abort")
with open(src_path, "w") as f:
    f.write(new_src)
print("  ✓ endpoint inserted")
PYEOF

echo ""
echo "=== STEP 5: Python syntax check ==="
python3 -c "import py_compile; py_compile.compile('/root/landtek/leo_tools/server.py', doraise=True)"
echo "  ✓ compiles"

echo ""
echo "=== STEP 6: Restart leo-tools ==="
systemctl restart leo-tools
sleep 3
systemctl is-active leo-tools >/dev/null && echo "  ✓ active"

echo ""
echo "=== STEP 7: Smoke test (localhost) ==="
R1=$(curl -s "http://127.0.0.1:8765/api/query_documents?case_file=MWK-001&classification=Title&limit=5")
echo "  Response head: ${R1:0:200}"
C1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null || echo "-1")
echo "  count=$C1"
if [ "$C1" -lt 5 ]; then
  echo "  ✗ localhost test FAILED. Service logs:"
  journalctl -u leo-tools -n 30 --no-pager
  exit 1
fi

echo ""
echo "=== STEP 8: Smoke test (from n8n container) ==="
R2=$(docker exec n8n-n8n-1 wget -qO- "http://172.18.0.1:8765/api/query_documents?case_file=MWK-001&classification=Title&limit=5")
C2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null || echo "-1")
echo "  count=$C2"
if [ "$C2" -lt 5 ]; then
  echo "  ✗ n8n container can't reach endpoint. Stop."
  exit 1
fi

echo ""
echo "=========================================="
echo "ENDPOINT VERIFIED FROM BOTH HOST AND CONTAINER"
echo "=========================================="
echo "Endpoint is live. Next: add tool node + connection in workflow."
echo "Re-run the original deploy script from STEP 6 onward, OR I'll send a step-6+ continuation."
