"""Per-client file access tokens — deploy_086.

GET  /files/c/<token>        — token-gated client view of the dashboard
POST /api/issue_files_token  — generate a fresh token for a telegram_id
GET  /api/clients_directory  — list of clients and their doc counts (Jonathan only)

Tokens are random 32-char hex. Default TTL 1 hour. Each token is scoped
to ONE telegram_id + case_file pair. Renderer filters documents by
case_file and only shows files in that scope.

Per "information is gold" — every token issue is logged in
file_access_tokens, used_count is incremented on every page render.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, render_template_string, jsonify, abort
import psycopg2
from psycopg2.extras import RealDictCursor

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN_TG_ID = "6513067717"
PUBLIC_BASE = os.getenv("LEO_PUBLIC_BASE_URL", "https://leo.hayuma.org")

bp = Blueprint("file_access", __name__)


def _db():
    return psycopg2.connect(PG_DSN)


def _new_token():
    return secrets.token_hex(16)


@bp.route("/api/issue_files_token", methods=["POST"])
def issue_token():
    """Issue a fresh access token for a Telegram-authenticated client.

    Body JSON: { telegram_id: "<numeric>", ttl_hours: <optional, default 1>, issued_by: "<optional>" }

    Returns: { token, url, case_file, expires_at }
    """
    data = request.get_json(silent=True) or {}
    tg = str(data.get("telegram_id", "")).strip()
    if not tg or not tg.isdigit():
        return jsonify({"error": "telegram_id required (numeric)"}), 400
    ttl_hours = int(data.get("ttl_hours", 1))
    ttl_hours = max(1, min(ttl_hours, 24 * 7))
    issued_by = str(data.get("issued_by", "")).strip() or None

    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT case_file, name FROM clients WHERE telegram_id = %s LIMIT 1", (tg,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return jsonify({"error": f"no client found for telegram_id {tg}"}), 404

    token = _new_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    cur.execute("""
        INSERT INTO file_access_tokens (token, telegram_id, case_file, client_name, expires_at, issued_by)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (token, tg, row["case_file"], row["name"], expires, issued_by))
    conn.commit()
    cur.close(); conn.close()

    return jsonify({
        "token": token,
        "url": f"{PUBLIC_BASE}/files/c/{token}",
        "case_file": row["case_file"],
        "client_name": row["name"],
        "expires_at": expires.isoformat(),
        "ttl_hours": ttl_hours,
    })


def _validate_token(token):
    """Returns (telegram_id, case_file, client_name) or None if invalid/expired."""
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT telegram_id, case_file, client_name, expires_at
          FROM file_access_tokens
         WHERE token = %s
         LIMIT 1
    """, (token,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return None
    if row["expires_at"] < datetime.now(timezone.utc):
        cur.close(); conn.close()
        return None
    cur.execute("""
        UPDATE file_access_tokens
           SET used_count = used_count + 1, last_used_at = now()
         WHERE token = %s
    """, (token,))
    conn.commit()
    cur.close(); conn.close()
    return row["telegram_id"], row["case_file"], row["client_name"]


CLIENT_DASHBOARD_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<title>LandTek — {{ client_name }} files</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 1100px; margin: 1em auto; padding: 0 1em; color: #222; }
  h1 { margin: 0.2em 0; }
  .subtitle { color: #666; margin-bottom: 1em; }
  .controls { margin: 1em 0; }
  input[type=search] { padding: 0.4em; width: 60%; font-size: 1em; }
  table { width: 100%; border-collapse: collapse; margin-top: 0.8em; }
  th, td { padding: 0.4em 0.6em; border-bottom: 1px solid #eee; vertical-align: top; }
  th { text-align: left; background: #f9f9f9; }
  tr:hover { background: #fafafa; }
  a { color: #1856a5; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .meta { color: #888; font-size: 0.9em; }
  .pill { display: inline-block; padding: 0.1em 0.5em; border-radius: 0.6em; background: #eef; font-size: 0.8em; }
</style>
</head><body>
  <h1>{{ client_name }}</h1>
  <div class="subtitle">
    Case: <span class="pill">{{ case_file }}</span> · Files visible: {{ total }}
  </div>

  <form class="controls" method="get">
    <input type="hidden" name="" />
    <input type="search" name="q" value="{{ q }}" placeholder="Search filenames + content…" autofocus />
    <button type="submit">Search</button>
  </form>

  <table>
    <thead><tr><th>#</th><th>Filename</th><th>Type</th><th>Date</th><th>Actions</th></tr></thead>
    <tbody>
      {% for d in docs %}
      <tr>
        <td>{{ d.id }}</td>
        <td>{{ d.original_filename or d.smart_filename or '—' }}
            {% if d.summary %}<div class="meta">{{ d.summary[:160] }}</div>{% endif %}</td>
        <td>{{ d.mime_type or '' }}</td>
        <td>{{ d.timestamp.strftime('%Y-%m-%d') if d.timestamp else '' }}</td>
        <td>
          <a href="/files/{{ d.id }}/download">download</a>
          {% if d.drive_link %} · <a href="{{ d.drive_link }}" target="_blank">Drive</a>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <p class="meta">This link is unique to you and expires in 1 hour from issue. No basic-auth password is needed.</p>
</body></html>"""


@bp.route("/files/c/<token>")
def client_dashboard(token):
    info = _validate_token(token)
    if not info:
        return "Token invalid or expired. Ask Leo for a new link.", 401
    tg, case_file, client_name = info

    q = request.args.get("q", "").strip()
    like = "%" + q + "%" if q else None

    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    if q:
        cur.execute("""
            SELECT id, original_filename, smart_filename, mime_type, timestamp,
                   drive_link, LEFT(coalesce(extracted_text,''), 200) AS summary
              FROM documents
             WHERE case_file = %s
               AND (
                 coalesce(original_filename,'') ILIKE %s
                 OR coalesce(smart_filename,'') ILIKE %s
                 OR coalesce(extracted_text,'') ILIKE %s
               )
             ORDER BY id DESC LIMIT 200
        """, (case_file, like, like, like))
    else:
        cur.execute("""
            SELECT id, original_filename, smart_filename, mime_type, timestamp,
                   drive_link, LEFT(coalesce(extracted_text,''), 200) AS summary
              FROM documents
             WHERE case_file = %s
             ORDER BY id DESC LIMIT 200
        """, (case_file,))
    docs = cur.fetchall()
    cur.execute("SELECT count(*) AS total FROM documents WHERE case_file = %s", (case_file,))
    total = cur.fetchone()["total"]
    cur.close(); conn.close()

    return render_template_string(
        CLIENT_DASHBOARD_HTML,
        client_name=client_name, case_file=case_file,
        docs=docs, total=total, q=q,
    )


@bp.route("/api/clients_directory")
def clients_directory():
    """Operator view: list all clients with their doc counts.

    Requires X-Operator header = Jonathan's telegram_id (basic auth shim).
    """
    op = request.headers.get("X-Operator", "").strip()
    if op != JONATHAN_TG_ID:
        return jsonify({"error": "operator only"}), 403
    conn = _db(); cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT c.id, c.name, c.telegram_id, c.case_file, c.email,
               (SELECT count(*) FROM documents d WHERE d.case_file = c.case_file) AS doc_count
          FROM clients c ORDER BY c.id;
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify({"clients": [dict(r) for r in rows]})
