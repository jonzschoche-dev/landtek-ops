#!/usr/bin/env bash
set -euo pipefail
BACKUP=/root/landtek/backups/2026-05-10-leo-v6

echo "=== STEP 1: Revert server.py to clean state ==="
cp "$BACKUP/server.py.commit2-before" /root/landtek/leo_tools/server.py
echo "  ✓ reverted"

echo ""
echo "=== STEP 2: (Re)generate endpoint staging file ==="
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
echo "  ✓ /tmp/qd_endpoint.py written"

echo ""
echo "=== STEP 3: Insert endpoint BEFORE the 'if __name__' guard ==="
python3 <<'PYEOF'
import re
src_path = "/root/landtek/leo_tools/server.py"
with open(src_path) as f: src = f.read()
with open("/tmp/qd_endpoint.py") as f: endpoint = f.read()

m = re.search(r'^if __name__\s*==', src, re.MULTILINE)
if m:
    insert_at = m.start()
    print(f"  inserting before 'if __name__' at offset {insert_at}")
else:
    m = re.search(r'^app\.run\(', src, re.MULTILINE)
    if not m:
        raise SystemExit("no insertion point found")
    insert_at = m.start()
    print(f"  inserting before top-level app.run at offset {insert_at}")

new_src = src[:insert_at] + endpoint + "\n\n" + src[insert_at:]
if new_src.count("def query_documents") != 1:
    raise SystemExit(f"insertion produced {new_src.count('def query_documents')} copies — abort")
with open(src_path, "w") as f: f.write(new_src)
print("  ✓ endpoint inserted")
PYEOF

echo ""
echo "=== STEP 4: Python syntax check ==="
python3 -c "import py_compile; py_compile.compile('/root/landtek/leo_tools/server.py', doraise=True)"
echo "  ✓ compiles"

echo ""
echo "=== STEP 5: Restart leo-tools ==="
systemctl restart leo-tools
sleep 3
systemctl is-active leo-tools >/dev/null && echo "  ✓ active"

echo ""
echo "=== STEP 6: Smoke test (localhost) ==="
R1=$(curl -s "http://127.0.0.1:8765/api/query_documents?case_file=MWK-001&classification=Title&limit=5")
echo "  Response head: ${R1:0:200}"
C1=$(echo "$R1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null || echo "-1")
echo "  count=$C1"
if [ "$C1" -lt 5 ]; then
  echo "  ✗ localhost FAILED. Logs:"
  journalctl -u leo-tools -n 40 --no-pager
  exit 1
fi

echo ""
echo "=== STEP 7: Smoke test (from n8n container) ==="
R2=$(docker exec n8n-n8n-1 wget -qO- "http://172.18.0.1:8765/api/query_documents?case_file=MWK-001&classification=Title&limit=5")
C2=$(echo "$R2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', -1))" 2>/dev/null || echo "-1")
echo "  count=$C2"
[ "$C2" -ge 5 ] && echo "  ✓ both endpoints verified, ready for n8n workflow patch" || { echo "  ✗ container can't reach endpoint"; exit 1; }
