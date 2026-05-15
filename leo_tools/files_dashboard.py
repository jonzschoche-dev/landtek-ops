"""Files dashboard — Flask blueprint mounted at /files/ on leo_tools server.

Single-page UI to browse, search, and download every file in documents.
Imported and registered in leo_tools/server.py via blueprint pattern.
"""
from __future__ import annotations
from flask import Blueprint, request, abort, send_file, Response, jsonify
from pathlib import Path
import os
import psycopg2
import psycopg2.extras
import html

bp = Blueprint("files", __name__, url_prefix="/files")


def _db():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "172.18.0.3"),
        dbname=os.environ.get("PGDATABASE", "n8n"),
        user=os.environ.get("PGUSER", "n8n"),
        password=os.environ.get("PGPASSWORD", "n8npassword"),
    )


def _esc(s):
    if s is None:
        return ""
    return html.escape(str(s))


def _fmt_size(n):
    if not n:
        return ""
    n = int(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


CSS = """
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       max-width: 1400px; margin: 20px auto; padding: 0 20px; color: #222; }
h1 { font-size: 20px; margin: 0 0 8px; }
.subtitle { color: #666; font-size: 13px; margin-bottom: 20px; }
.filters { background: #f5f5f5; padding: 12px; border-radius: 6px; margin-bottom: 16px; }
.filters input, .filters select {
  padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px;
  margin-right: 8px; font-size: 14px;
}
.filters button { padding: 6px 14px; background: #2c5; color: white; border: none;
                   border-radius: 4px; cursor: pointer; font-size: 14px; }
.filters button:hover { background: #1a4; }
.filters a { font-size: 13px; color: #2563eb; margin-left: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th { background: #f0f0f0; padding: 8px 10px; text-align: left; border-bottom: 2px solid #ddd;
     position: sticky; top: 0; }
td { padding: 6px 10px; border-bottom: 1px solid #eee; vertical-align: top; }
tr:hover { background: #fafafa; }
.id { font-family: monospace; color: #888; }
.filename { max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.casefile { font-family: monospace; font-size: 12px; padding: 2px 6px; background: #e0e7ff;
            border-radius: 3px; color: #1e40af; }
.chars { text-align: right; color: #444; }
.actions a { margin-right: 8px; color: #2563eb; text-decoration: none; font-size: 12px; }
.actions a:hover { text-decoration: underline; }
.empty { color: #999; font-style: italic; }
.detail-panel { background: #fafafa; padding: 16px; border-radius: 6px; margin-top: 16px;
                 font-family: monospace; font-size: 12px; white-space: pre-wrap; }
.pagination { margin-top: 16px; }
.pagination a { padding: 6px 12px; background: #fff; border: 1px solid #ccc;
                 border-radius: 4px; margin-right: 4px; text-decoration: none; color: #333; }
.pagination a:hover { background: #eee; }
.pagination .current { background: #2c5; color: white; border-color: #2c5; }
.meta-table { margin-bottom: 12px; }
.meta-table td { padding: 4px 8px; }
.meta-table td:first-child { color: #666; width: 200px; }
</style>
"""


@bp.route("/")
def index():
    q = request.args.get("q", "").strip()
    case = request.args.get("case", "").strip()
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 50
    offset = (page - 1) * per_page

    where = []
    params = []
    if q:
        where.append("(original_filename ILIKE %s OR extracted_text ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    if case:
        where.append("case_file = %s")
        params.append(case)
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    conn = _db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT count(*) AS n FROM documents{where_sql}", params)
    total = cur.fetchone()["n"]
    cur.execute(f"""
        SELECT id, original_filename, case_file, classification,
               length(coalesce(extracted_text,'')) AS chars,
               file_path, drive_link, mime_type,
               to_char(created_at, 'YYYY-MM-DD HH24:MI') AS at
          FROM documents{where_sql}
         ORDER BY id DESC
         LIMIT %s OFFSET %s
    """, params + [per_page, offset])
    rows = cur.fetchall()
    cur.execute("SELECT DISTINCT case_file FROM documents WHERE case_file IS NOT NULL ORDER BY 1")
    cases = [r["case_file"] for r in cur.fetchall()]
    cur.close(); conn.close()

    total_pages = (total + per_page - 1) // per_page
    rows_html = []
    for r in rows:
        actions = []
        if r["file_path"] and os.path.exists(r["file_path"]):
            actions.append(f'<a href="{r["id"]}/download">download</a>')
        if r["chars"]:
            actions.append(f'<a href="{r["id"]}/text">text</a>')
        actions.append(f'<a href="{r["id"]}">details</a>')
        if r["drive_link"]:
            actions.append(f'<a href="{_esc(r["drive_link"])}" target="_blank">drive ↗</a>')
        rows_html.append(f"""
        <tr>
          <td class="id">{r["id"]}</td>
          <td class="filename" title="{_esc(r["original_filename"])}">{_esc(r["original_filename"]) or '<span class="empty">unnamed</span>'}</td>
          <td>{f'<span class="casefile">{_esc(r["case_file"])}</span>' if r["case_file"] else ''}</td>
          <td>{_esc(r["classification"]) or '<span class="empty">—</span>'}</td>
          <td class="chars">{r["chars"]:,}</td>
          <td>{_esc(r["at"])}</td>
          <td class="actions">{' '.join(actions)}</td>
        </tr>
        """)

    # Pagination
    pag = []
    if total_pages > 1:
        base = f"?q={_esc(q)}&case={_esc(case)}"
        for p in range(max(1, page - 3), min(total_pages, page + 3) + 1):
            cls = ' class="current"' if p == page else ''
            pag.append(f'<a href="{base}&page={p}"{cls}>{p}</a>')

    case_options = '<option value="">all cases</option>' + ''.join(
        f'<option value="{_esc(c)}"{" selected" if c == case else ""}>{_esc(c)}</option>'
        for c in cases
    )

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>LandTek Files</title>{CSS}</head><body>
<h1>LandTek Files</h1>
<div class="subtitle">{total:,} documents indexed · showing {len(rows)} per page</div>
<form class="filters">
  <input name="q" placeholder="search filename + text..." value="{_esc(q)}" size="32">
  <select name="case">{case_options}</select>
  <button type="submit">filter</button>
  <a href="/files/">clear</a>
</form>
<table>
  <tr>
    <th>id</th><th>filename</th><th>case</th><th>classification</th>
    <th style="text-align:right">chars</th><th>uploaded</th><th>actions</th>
  </tr>
  {''.join(rows_html) if rows_html else '<tr><td colspan="7" class="empty">no matches</td></tr>'}
</table>
<div class="pagination">{' '.join(pag)}</div>
</body></html>"""


@bp.route("/<int:doc_id>")
def detail(doc_id):
    conn = _db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, original_filename, case_file, classification, status,
               file_path, drive_link, drive_file_id, mime_type,
               length(coalesce(extracted_text,'')) AS chars,
               to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created,
               to_char(updated_at, 'YYYY-MM-DD HH24:MI:SS') AS updated,
               coalesce(extracted_text,'') AS extracted_text,
               summary, document_title, document_type, document_date,
               conversation_id, smart_filename
          FROM documents WHERE id=%s
    """, (doc_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)

    fields = [
        ("ID", row["id"]),
        ("Filename", row["original_filename"]),
        ("Smart filename", row["smart_filename"]),
        ("Document title", row["document_title"]),
        ("Case file", row["case_file"]),
        ("Classification", row["classification"]),
        ("Document type", row["document_type"]),
        ("Document date", row["document_date"]),
        ("MIME type", row["mime_type"]),
        ("Status", row["status"]),
        ("Local file path", row["file_path"]),
        ("Drive file ID", row["drive_file_id"]),
        ("Drive link", f'<a href="{_esc(row["drive_link"])}" target="_blank">{_esc(row["drive_link"])}</a>' if row["drive_link"] else None),
        ("Char count (extracted)", f"{row['chars']:,}"),
        ("Conversation ID", row["conversation_id"]),
        ("Created", row["created"]),
        ("Updated", row["updated"]),
    ]
    meta_rows = ''.join(
        f'<tr><td>{_esc(k)}</td><td>{v if k == "Drive link" and v else _esc(v) if v is not None else ""}</td></tr>'
        for k, v in fields if v not in (None, "", 0)
    )

    actions = []
    if row["file_path"] and os.path.exists(row["file_path"]):
        actions.append(f'<a href="/files/{doc_id}/download">↓ download</a>')
    if row["chars"]:
        actions.append(f'<a href="/files/{doc_id}/text">view extracted text</a>')

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>doc {doc_id} · LandTek</title>{CSS}</head><body>
<h1><a href="/files/" style="text-decoration:none;color:#666">← files</a> / doc {doc_id}</h1>
<div class="subtitle">{_esc(row['original_filename'])}</div>
<div class="filters" style="margin-bottom:16px;">{' &nbsp; '.join(actions) or '<span class="empty">no local file or text available</span>'}</div>
<table class="meta-table"><tbody>{meta_rows}</tbody></table>
<details><summary>Extracted text (first 5000 chars)</summary>
<div class="detail-panel">{_esc(row['extracted_text'][:5000]) or '<span class="empty">no text extracted</span>'}{('<br><br>...(truncated, ' + str(row['chars']) + ' total chars, use /files/' + str(doc_id) + '/text for full)') if row['chars'] > 5000 else ''}</div>
</details>
</body></html>"""


@bp.route("/<int:doc_id>/download")
def download(doc_id):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT file_path, original_filename, mime_type FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    fp, name, mime = row
    if not fp or not os.path.exists(fp):
        return Response(f"no local file for doc {doc_id} (file_path={fp})", status=404)
    return send_file(fp, as_attachment=True, download_name=name or os.path.basename(fp),
                     mimetype=mime or "application/octet-stream")


@bp.route("/<int:doc_id>/text")
def text(doc_id):
    conn = _db(); cur = conn.cursor()
    cur.execute("SELECT original_filename, coalesce(extracted_text,'') FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        abort(404)
    name, txt = row
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_esc(name)} text</title>{CSS}</head><body>
<h1><a href="/files/{doc_id}" style="text-decoration:none;color:#666">← {_esc(name)}</a> · extracted text</h1>
<div class="subtitle">{len(txt):,} chars</div>
<pre style="white-space:pre-wrap;font-family:monospace;font-size:12px;background:#fafafa;padding:16px;border-radius:6px;">{_esc(txt)}</pre>
</body></html>"""


@bp.route("/api/stats")
def stats():
    conn = _db(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
      SELECT
        count(*) AS total,
        count(*) FILTER (WHERE file_path IS NOT NULL AND file_path<>'') AS local,
        count(*) FILTER (WHERE drive_file_id IS NOT NULL AND drive_file_id<>'') AS drive,
        count(*) FILTER (WHERE length(coalesce(extracted_text,''))>0) AS with_text
      FROM documents
    """)
    s = cur.fetchone()
    cur.close(); conn.close()
    return jsonify(s)
