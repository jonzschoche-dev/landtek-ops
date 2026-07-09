"""Leo Tools — HTTP endpoints called by n8n langchain tools."""
import os, json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import psycopg2

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
app = Flask(__name__)
try:
    from files_dashboard import bp as _files_bp
    app.register_blueprint(_files_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: files dashboard not registered: {_e}", file=_sys.stderr)

try:
    from unified_search import bp as _search_bp
    app.register_blueprint(_search_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: unified search not registered: {_e}", file=_sys.stderr)

try:
    from file_access import bp as _access_bp
    app.register_blueprint(_access_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: file access not registered: {_e}", file=_sys.stderr)

try:
    from slash_endpoints import bp as _slash_bp
    app.register_blueprint(_slash_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: slash endpoints not registered: {_e}", file=_sys.stderr)

try:
    from files_public import bp as _files_public_bp
    app.register_blueprint(_files_public_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: files_public (/files/c/) blueprint not registered: {_e}", file=_sys.stderr)

try:
    from onboarding_endpoints import bp as _onb_bp
    app.register_blueprint(_onb_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: onboarding endpoints not registered: {_e}", file=_sys.stderr)

try:
    from channel_adapters import bp as _ch_bp
    app.register_blueprint(_ch_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: channel adapters not registered: {_e}", file=_sys.stderr)

try:
    from vault_endpoints import bp as _vault_bp
    app.register_blueprint(_vault_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: vault endpoints not registered: {_e}", file=_sys.stderr)

try:
    from ops_dashboard import bp as _ops_bp
    app.register_blueprint(_ops_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: ops dashboard not registered: {_e}", file=_sys.stderr)

try:
    from client_portal import bp as _portal_bp
    app.register_blueprint(_portal_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: client portal not registered: {_e}", file=_sys.stderr)

try:
    from client_access import bp as _client_access_bp
    app.register_blueprint(_client_access_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: client access (/client/) blueprint not registered: {_e}", file=_sys.stderr)

try:
    from client_pwa import bp as _client_pwa_bp
    app.register_blueprint(_client_pwa_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: client PWA assets (/client/_app/) not registered: {_e}", file=_sys.stderr)

try:
    from mapping import bp as _mapping_bp
    app.register_blueprint(_mapping_bp)
except Exception as _e:
    import sys as _sys
    print(f"WARN: mapping (/ops/map, /client/<t>/map) blueprint not registered: {_e}", file=_sys.stderr)

def db():
    return psycopg2.connect(PG_DSN)

@app.route('/health')
def health():
    return jsonify({"ok": True})

@app.route('/api/missing')
def missing():
    case = request.args.get('case_file','').strip()
    c = db(); cur = c.cursor()
    sql = """SELECT id, smart_filename, case_file,
                    analyst_memo->'synthesis'->'referenced_but_missing'
             FROM documents
             WHERE analyst_memo IS NOT NULL
               AND jsonb_typeof(analyst_memo->'synthesis'->'referenced_but_missing') = 'array'
               AND jsonb_array_length(analyst_memo->'synthesis'->'referenced_but_missing') > 0"""
    args = []
    if case:
        sql += " AND case_file = %s"; args.append(case)
    cur.execute(sql, args)
    items = [{"doc_id":r[0],"file":r[1],"case_file":r[2],"missing":r[3]} for r in cur.fetchall()]
    cur.close(); c.close()
    return jsonify({"count":len(items),"items":items})

@app.route('/api/questions')
def questions():
    case = request.args.get('case_file','').strip()
    c = db(); cur = c.cursor()
    sql = """SELECT id, case_file, question, priority, source_filename, created_at
             FROM pending_questions WHERE status='open'"""
    args = []
    if case:
        sql += " AND case_file = %s"; args.append(case)
    sql += " ORDER BY created_at DESC LIMIT 20"
    cur.execute(sql, args)
    items = [{"id":r[0],"case_file":r[1],"question":r[2],"priority":r[3],
              "source":r[4],"created_at":str(r[5])} for r in cur.fetchall()]
    cur.close(); c.close()
    return jsonify({"count":len(items),"questions":items})

@app.route('/api/deadlines')
def deadlines():
    """Return upcoming case deadlines.
    Primary source: case_deadlines table.
    Params: within_days (default 30, max 365), case_file (optional)."""
    try:
        days = max(1, min(int(request.args.get('within_days', '30')), 365))
    except Exception:
        days = 30
    case = (request.args.get('case_file') or '').strip()

    c = db(); cur = c.cursor()
    try:
        sql = """
            SELECT id, case_file, title, description, due_date, due_time,
                   deadline_type, status, source_doc_id, confidence, notes
            FROM case_deadlines
            WHERE status = 'pending'
              AND due_date <= CURRENT_DATE + INTERVAL '1 day' * %s
              AND due_date >= CURRENT_DATE - INTERVAL '7 days'
        """
        args = [days]
        if case:
            sql += " AND case_file = %s"
            args.append(case)
        sql += " ORDER BY due_date, due_time NULLS FIRST"
        cur.execute(sql, args)
        items = [{
            "id": r[0], "case_file": r[1], "title": r[2], "description": r[3],
            "due_date": str(r[4]), "due_time": str(r[5]) if r[5] else None,
            "type": r[6], "status": r[7], "source_doc_id": r[8],
            "confidence": float(r[9]) if r[9] is not None else None,
            "notes": r[10],
        } for r in cur.fetchall()]
    finally:
        cur.close(); c.close()
    return jsonify({"count": len(items), "within_days": days, "deadlines": items})


@app.route('/api/cross_reference')
def cross_reference():
    ref = request.args.get('reference','').strip()
    if not ref:
        return jsonify({"error":"missing reference parameter"}), 400
    c = db(); cur = c.cursor()
    cur.execute("""SELECT id, case_file, smart_filename, document_title, classification, created_at, drive_link, matter_code
                   FROM documents
                   WHERE extracted_text ILIKE %s OR analyst_memo::text ILIKE %s
                   ORDER BY created_at DESC NULLS LAST LIMIT 30""",
                (f'%{ref}%', f'%{ref}%'))
    items = [{"doc_id":r[0],"case_file":r[1],"file":r[2],"title":r[3],
              "type":r[4],"created_at":str(r[5]),
              "drive_link":r[6],"matter_code":r[7]} for r in cur.fetchall()]
    cur.close(); c.close()
    return jsonify({"reference":ref,"count":len(items),"documents":items})

@app.route('/api/party')
def party():
    name = request.args.get('name','').strip()
    if not name:
        return jsonify({"error":"missing name parameter"}), 400
    c = db(); cur = c.cursor()
    cur.execute("""SELECT id, case_file, smart_filename, document_title, classification, created_at, drive_link, matter_code
                   FROM documents
                   WHERE extracted_text ILIKE %s
                   ORDER BY created_at DESC NULLS LAST LIMIT 30""",
                (f'%{name}%',))
    items = [{"doc_id":r[0],"case_file":r[1],"file":r[2],"title":r[3],
              "type":r[4],"created_at":str(r[5]),
              "drive_link":r[6],"matter_code":r[7]} for r in cur.fetchall()]
    cur.close(); c.close()
    return jsonify({"party":name,"count":len(items),"documents":items})

@app.route('/api/linked_documents')
def linked_documents():
    """For a given doc_id, return all linked docs across cases."""
    doc_id = request.args.get('doc_id','').strip()
    if not doc_id: return jsonify({"error":"missing doc_id"}), 400
    c = db(); cur = c.cursor()
    cur.execute("""SELECT dl.linked_case_file, dl.link_type, dl.link_reason,
                          d2.id, d2.smart_filename, d2.classification
                   FROM document_links dl
                   LEFT JOIN documents d2 ON d2.id = dl.source_doc_id
                   WHERE dl.document_id = %s""", (doc_id,))
    items = [{"case_file":r[0],"link_type":r[1],"reason":r[2],
              "source_doc_id":r[3],"source_file":r[4],"source_type":r[5]}
             for r in cur.fetchall()]
    cur.close(); c.close()
    return jsonify({"doc_id":doc_id,"count":len(items),"links":items})




@app.route('/api/query_documents')
def query_documents():
    _body = request.get_json(silent=True) or {}
    _thread_id = (request.args.get('thread_id') or _body.get('thread_id') or '').strip()
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
               doc_date, document_date, summary, created_at, drive_link, matter_code
        FROM documents{wc}
        ORDER BY COALESCE(doc_date, document_date, TO_CHAR(created_at, 'YYYY-MM-DD')) DESC NULLS LAST
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
        "drive_link": r[9],
        "matter_code": r[10],
    } for r in rows]

    
    # Thread-scope filter (064)
    if _thread_id:
        try:
            _tid = int(_thread_id)
            _conn = db(); _cur = _conn.cursor()
            try:
                _cur.execute("SELECT doc_id FROM case_thread_documents WHERE thread_id = %s", (_tid,))
                _allowed = {r[0] for r in _cur.fetchall()}
            finally:
                _cur.close(); _conn.close()
            # rows is the local result list — filter it
            if 'rows' in dir():
                rows = [r for r in rows if (r[0] if isinstance(r, (list,tuple)) else r.get('id')) in _allowed]
            elif 'results' in dir():
                results = [r for r in results if (r.get('id') if isinstance(r, dict) else r[0]) in _allowed]
        except Exception as _e:
            log.warning('thread_id filter failed: %s', _e)
    return jsonify({
        "filter": {"case_file": case_file, "classification": classification,
                   "year": year, "keyword": keyword, "limit": limit},
        "count": len(items),
        "documents": items,
    })



@app.route('/api/log_interaction', methods=['POST'])
def log_interaction():
    """Insert one Leo interaction row. Called from n8n workflow after Parse Agent1."""
    import json as _json
    try:
        payload = request.get_json(force=True, silent=False) or {}
    except Exception as e:
        return jsonify({"error": f"bad json: {e}"}), 400

    fields = {
        "channel": payload.get("channel", "telegram"),
        "sender_id": payload.get("sender_id"),
        "sender_name": payload.get("sender_name"),
        "question": payload.get("question", ""),
        "case_file": payload.get("case_file"),
        "tool_calls": _json.dumps(payload.get("tool_calls")) if payload.get("tool_calls") is not None else None,
        "response_json": _json.dumps(payload.get("response_json")) if payload.get("response_json") is not None else None,
        "reply_text": payload.get("reply_text"),
        "duration_ms": payload.get("duration_ms"),
        "execution_id": payload.get("execution_id"),
        "eval_question_id": payload.get("eval_question_id"),
        "eval_expected": _json.dumps(payload.get("eval_expected")) if payload.get("eval_expected") is not None else None,
        "eval_pass": payload.get("eval_pass"),
    }
    if not fields["question"]:
        return jsonify({"error": "question is required"}), 400

    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            INSERT INTO leo_interactions
              (channel, sender_id, sender_name, question, case_file,
               tool_calls, response_json, reply_text, duration_ms, execution_id,
               eval_question_id, eval_expected, eval_pass)
            VALUES (%(channel)s, %(sender_id)s, %(sender_name)s, %(question)s, %(case_file)s,
                    %(tool_calls)s::jsonb, %(response_json)s::jsonb, %(reply_text)s,
                    %(duration_ms)s, %(execution_id)s,
                    %(eval_question_id)s, %(eval_expected)s::jsonb, %(eval_pass)s)
            RETURNING id, timestamp
        """, fields)
        row = cur.fetchone()
        c.commit()
    finally:
        cur.close(); c.close()

    return jsonify({"ok": True, "id": row[0], "timestamp": str(row[1])})




@app.route('/api/extract_file_text', methods=['POST'])
def extract_file_text():
    """Extract text from an uploaded file. Used by n8n workflow.

    Accepts EITHER:
      1. JSON body: {base64_data, original_filename, mime_type?}
      2. multipart/form-data with 'file' (or 'data') field + optional 'original_filename'

    Response: {extracted_text, char_count, status, local_path, mime_type}
    """
    import subprocess as _sp, json as _json, base64 as _b64
    payload = {}

    # Path 1: multipart upload (n8n binary)
    if request.files:
        # n8n's binary param is typically 'file' or 'data'
        f = request.files.get('file') or request.files.get('data')
        if f is None:
            # fall back to the first file
            f = list(request.files.values())[0]
        data = f.read()
        original_filename = request.form.get('original_filename') or f.filename or 'uploaded_file'
        mime_type = request.form.get('mime_type') or f.mimetype or ''
        payload = {
            "base64_data": _b64.b64encode(data).decode(),
            "original_filename": original_filename,
            "mime_type": mime_type,
        }
    else:
        # Path 2: JSON body with base64
        try:
            payload = request.get_json(force=True, silent=False) or {}
        except Exception as e:
            return jsonify({"status": "error", "error": f"json parse: {e}"}), 400

    if not payload.get("base64_data"):
        return jsonify({"status": "error", "error": "base64_data required"}), 400

    try:
        result = _sp.run(
            ["python3", "/root/landtek/extract_uploaded_file.py"],
            input=_json.dumps(payload),
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            return jsonify({
                "status": f"extract_error_rc{result.returncode}",
                "stderr": result.stderr[:500],
                "extracted_text": "",
                "char_count": 0,
            }), 200
        data = _json.loads(result.stdout)
        return jsonify(data), 200
    except _sp.TimeoutExpired:
        return jsonify({"status": "timeout", "extracted_text": "", "char_count": 0}), 200
    except Exception as e:
        return jsonify({"status": f"server_error: {type(e).__name__}: {e}", "extracted_text": "", "char_count": 0}), 200



def _drive_service():
    """Build a Drive v3 client with OWNER-QUOTA credentials.

    A Google service account has ZERO storage quota, so files.create into the personal-owned LANDTEK
    folder returns 403 storageQuotaExceeded. We authenticate as the folder owner via the existing
    DRIVE_REFRESH_TOKEN OAuth token (jonzschoche@gmail.com) → uploads are owner-quota. Falls back to
    the SA only if the token is missing, with a loud log (SA uploads WILL 403 on new files).
    Returns (service, auth_mode).
    """
    from googleapiclient.discovery import build as _build
    tok = os.environ.get("DRIVE_REFRESH_TOKEN")
    if not tok:
        try:
            for _l in open("/root/landtek/.env"):
                _s = _l.strip()
                if _s.startswith("DRIVE_REFRESH_TOKEN=") and not _s.startswith("#"):
                    tok = _s.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    if tok:
        try:
            from google.oauth2.credentials import Credentials as _OAuthCreds
            cli = None
            for _f in ("/root/landtek/gmail_oauth_client.json", "/root/landtek/gemini_oauth_client.json"):
                try:
                    _d = json.load(open(_f))
                    _d = _d.get("installed", _d.get("web", _d))
                    if _d.get("client_id"):
                        cli = _d
                        break
                except Exception:
                    pass
            if cli:
                creds = _OAuthCreds(None, refresh_token=tok,
                                    token_uri="https://oauth2.googleapis.com/token",
                                    client_id=cli["client_id"], client_secret=cli["client_secret"])
                return _build('drive', 'v3', credentials=creds), "oauth_owner_quota"
        except Exception as e:
            app.logger.warning("drive OAuth creds failed (%s); falling back to SA (uploads may 403)", e)
    from google.oauth2 import service_account as _sa
    app.logger.warning("upload_to_drive using SERVICE-ACCOUNT creds — new-file uploads will 403 "
                       "(storageQuotaExceeded); set DRIVE_REFRESH_TOKEN for owner-quota uploads")
    creds = _sa.Credentials.from_service_account_file(
        "/root/landtek/landtek-compute-sa.json",
        scopes=["https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive"])
    return _build('drive', 'v3', credentials=creds), "service_account"


@app.route('/api/upload_to_drive', methods=['POST'])
def upload_to_drive():
    """Upload a file to Google Drive using OWNER-QUOTA OAuth creds (the SA has no storage quota).

    Body:
      - multipart/form-data: file=@... + folder_id + (optional) target_filename
      OR
      - JSON: {base64_data, folder_id, target_filename?, mime_type?}

    Response: {ok, drive_file_id, drive_link, name, auth_mode, status}
    """
    import io as _io, base64 as _b64
    try:
        from googleapiclient.http import MediaIoBaseUpload as _MIO
    except Exception as e:
        return jsonify({"ok": False, "status": f"sdk_missing: {e}"}), 500

    # Parse input
    folder_id = ""
    target_filename = "uploaded_file"
    mime_type = "application/octet-stream"
    raw = b""

    if request.files:
        f = request.files.get('file') or list(request.files.values())[0]
        raw = f.read()
        folder_id = request.form.get('folder_id') or ''
        target_filename = request.form.get('target_filename') or f.filename or target_filename
        mime_type = request.form.get('mime_type') or f.mimetype or mime_type
    else:
        try:
            payload = request.get_json(force=True, silent=False) or {}
        except Exception as e:
            return jsonify({"ok": False, "status": f"json_parse: {e}"}), 400
        b64 = payload.get('base64_data') or ''
        if not b64:
            return jsonify({"ok": False, "status": "base64_data or multipart file required"}), 400
        raw = _b64.b64decode(b64)
        folder_id = payload.get('folder_id') or ''
        target_filename = payload.get('target_filename') or target_filename
        mime_type = payload.get('mime_type') or mime_type

    if not folder_id:
        return jsonify({"ok": False, "status": "folder_id required"}), 400

    try:
        service, auth_mode = _drive_service()
        media = _MIO(_io.BytesIO(raw), mimetype=mime_type, resumable=True)
        meta = {"name": target_filename, "parents": [folder_id]}
        result = service.files().create(
            body=meta, media_body=media,
            fields='id, name, webViewLink, parents, mimeType'
        ).execute()
        return jsonify({
            "ok": True,
            "drive_file_id": result.get('id'),
            "drive_link": result.get('webViewLink'),
            "name": result.get('name'),
            "mime_type": result.get('mimeType'),
            "parents": result.get('parents'),
            "auth_mode": auth_mode,
            "status": "ok",
        }), 200
    except Exception as e:
        return jsonify({"ok": False, "status": f"upload_error: {type(e).__name__}: {e}"}), 500


@app.route('/api/recent_interactions')
def recent_interactions():
    """List recent interactions for rating. Default: unrated, last 50."""
    only_unrated = request.args.get('only_unrated', '1') == '1'
    limit = min(int(request.args.get('limit', 50)), 200)
    c = db(); cur = c.cursor()
    try:
        if only_unrated:
            cur.execute("""
                SELECT id, timestamp, channel, sender_name, question, case_file,
                       LEFT(reply_text, 800) AS reply_excerpt, rating
                FROM leo_interactions
                WHERE rating IS NULL AND channel != 'test'
                ORDER BY id DESC LIMIT %s
            """, (limit,))
        else:
            cur.execute("""
                SELECT id, timestamp, channel, sender_name, question, case_file,
                       LEFT(reply_text, 800) AS reply_excerpt, rating
                FROM leo_interactions
                WHERE channel != 'test'
                ORDER BY id DESC LIMIT %s
            """, (limit,))
        items = [{"id": r[0], "timestamp": str(r[1]), "channel": r[2],
                  "sender_name": r[3], "question": r[4], "case_file": r[5],
                  "reply_excerpt": r[6], "rating": r[7]} for r in cur.fetchall()]
    finally:
        cur.close(); c.close()
    return jsonify({"count": len(items), "interactions": items})


@app.route('/api/rate_interaction', methods=['POST'])
def rate_interaction():
    """Rate one interaction. Payload: {id, rating, failure_mode?, feedback_note?}."""
    p = request.get_json(force=True, silent=True) or {}
    iid = p.get('id'); rating = p.get('rating')
    if iid is None or rating is None:
        return jsonify({"error": "id and rating required"}), 400
    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return jsonify({"error": "rating must be 1-5"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "rating must be integer"}), 400

    fm = p.get('failure_mode')
    if fm not in (None, 'wrong_answer', 'missing_answer', 'hallucination',
                  'wrong_tool', 'wrong_format', 'other'):
        return jsonify({"error": f"invalid failure_mode: {fm}"}), 400

    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            UPDATE leo_interactions
            SET rating=%s, failure_mode=%s, feedback_note=%s
            WHERE id=%s
            RETURNING id
        """, (rating, fm, p.get('feedback_note'), iid))
        row = cur.fetchone()
        c.commit()
    finally:
        cur.close(); c.close()
    if not row:
        return jsonify({"error": f"no row id={iid}"}), 404
    return jsonify({"ok": True, "id": row[0]})


@app.route('/rate')
def rate_dashboard():
    """Minimal HTML dashboard for rating recent Leo interactions."""
    return r"""
<!DOCTYPE html>
<html><head><title>Leo Rate</title>
<style>
body{font:14px/1.5 -apple-system,sans-serif;max-width:1100px;margin:1em auto;padding:0 1em;background:#fafafa}
.card{background:white;border:1px solid #ddd;border-radius:8px;padding:1em;margin:1em 0}
.meta{color:#666;font-size:12px;margin-bottom:.5em}
.q{font-weight:600;margin:.3em 0}
.r{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:12px;background:#f5f5f5;padding:.6em;border-radius:4px;max-height:200px;overflow:auto}
.btns{margin-top:.7em}
button{padding:.4em 1em;margin-right:.4em;border:1px solid #ccc;border-radius:4px;background:white;cursor:pointer;font-size:13px}
button.good{background:#e6f4ea;border-color:#46a35e}
button.bad{background:#fce8e6;border-color:#d93025}
.rated{opacity:.5}
.fm-row{display:none;margin-top:.5em}
.fm-row.show{display:block}
select,textarea{font:13px/1.4 -apple-system,sans-serif;padding:.3em;border:1px solid #ccc;border-radius:4px;width:100%;max-width:400px}
h1{margin:0 0 .5em}
.empty{text-align:center;color:#999;padding:2em}
</style>
</head><body>
<h1>Leo — Rate Recent Interactions</h1>
<p><a href="/rate?all=1">[show all]</a> <a href="/rate">[unrated only]</a> <button onclick="load()">Refresh</button></p>
<div id="list"></div>
<script>
const showAll = location.search.includes('all=1');
async function load(){
  const r = await fetch('/api/recent_interactions?only_unrated=' + (showAll?'0':'1') + '&limit=50');
  const j = await r.json();
  const el = document.getElementById('list');
  if (!j.interactions.length){ el.innerHTML = '<div class=empty>No interactions to rate.</div>'; return; }
  el.innerHTML = j.interactions.map(x => `
    <div class="card${x.rating?' rated':''}" id="c${x.id}">
      <div class=meta>#${x.id} · ${x.timestamp.slice(0,19)} · ${x.channel} · ${x.sender_name||'?'} · ${x.case_file||'?'} ${x.rating?'· rated '+x.rating+'/5':''}</div>
      <div class=q>Q: ${escapeHtml(x.question)}</div>
      <div class=r>${escapeHtml(x.reply_excerpt||'(empty)')}</div>
      <div class=btns>
        <button class=good onclick="rate(${x.id},5)">Good</button>
        <button class=bad onclick="showBad(${x.id})">Bad</button>
      </div>
      <div class=fm-row id="fm${x.id}">
        <select id="fms${x.id}">
          <option value=wrong_answer>Wrong answer</option>
          <option value=missing_answer>Missing answer (was there but not found)</option>
          <option value=hallucination>Hallucinated facts</option>
          <option value=wrong_tool>Used wrong tool</option>
          <option value=wrong_format>Wrong format</option>
          <option value=other>Other</option>
        </select>
        <textarea id="fmn${x.id}" placeholder="optional note"></textarea>
        <button class=bad onclick="rate(${x.id},1)">Submit Bad</button>
      </div>
    </div>`).join('');
}
function escapeHtml(s){return (s||'').replace(/[&<>"]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function showBad(id){ document.getElementById('fm'+id).classList.add('show'); }
async function rate(id, rating){
  const body = {id, rating};
  if (rating === 1){
    body.failure_mode = document.getElementById('fms'+id).value;
    body.feedback_note = document.getElementById('fmn'+id).value || null;
  }
  const r = await fetch('/api/rate_interaction', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r.ok){ document.getElementById('c'+id).style.opacity = '.4'; }
  else alert(await r.text());
}
load();
setInterval(load, 30000);
</script>
</body></html>
"""



@app.route('/api/eval_question', methods=['POST'])
def eval_question():
    """Run an eval question through Anthropic with Leo's actual prompt + tools.
    Payload: {question, eval_question_id?, case_file_hint?, expected?}
    Returns: full response with tool calls log."""
    import json as _json
    import time as _time
    import requests as _req
    import os as _os

    p = request.get_json(force=True, silent=True) or {}
    question = (p.get('question') or '').strip()
    if not question:
        return jsonify({"error": "question required"}), 400

    budget_err = _check_daily_budget("eval")
    if budget_err: return jsonify(budget_err), 429

    ANT_KEY = _os.environ.get('ANTHROPIC_API_KEY')
    if not ANT_KEY:
        # Try loading from .env
        try:
            with open('/root/landtek/.env') as f:
                for line in f:
                    if line.startswith('ANTHROPIC_API_KEY='):
                        ANT_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
                        break
        except Exception: pass
    if not ANT_KEY:
        return jsonify({"error": "ANTHROPIC_API_KEY not set in env or /root/landtek/.env"}), 500

    # Pull current system prompt from the published workflow
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT node->'parameters'->'options'->>'systemMessage'
            FROM workflow_history,
              jsonb_array_elements(nodes::jsonb) AS node
            WHERE "versionId" = '4ebc5fa8-cbc8-4c48-a887-6627d77f456e'
              AND node->>'type' = '@n8n/n8n-nodes-langchain.agent'
            LIMIT 1
        """)
        row = cur.fetchone()
        system_prompt = row[0] if row else ""
    finally:
        cur.close(); c.close()

    if not system_prompt:
        return jsonify({"error": "could not load system prompt from workflow"}), 500

    # Define tools matching n8n's set (compact descriptions)
    BASE = "http://127.0.0.1:8765"
    TOOLS = [
        {"name": "query_documents", "description": "Structured filter on case_file, classification, year, keyword. PRIMARY tool for list/every/all/latest questions.",
         "input_schema": {"type": "object", "properties": {
             "case_file": {"type": "string", "enum": ["Paracale-001", "MWK-001", "Owner"]},
             "classification": {"type": "string"},
             "year": {"type": "string"},
             "keyword": {"type": "string"},
             "limit": {"type": "integer"}
         }}},
        {"name": "cross_reference", "description": "Free-text search on a reference string (TCT, CTN, docket).",
         "input_schema": {"type": "object", "properties": {"reference": {"type": "string"}}, "required": ["reference"]}},
        {"name": "get_party_history", "description": "Documents mentioning a specific person/entity.",
         "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
        {"name": "get_deadlines", "description": "Procedural dates within N days.",
         "input_schema": {"type": "object", "properties": {"within_days": {"type": "integer"}, "case_file": {"type": "string"}}}},
        {"name": "get_pending_questions", "description": "Open questions awaiting Jonathan's input.",
         "input_schema": {"type": "object", "properties": {"case_file": {"type": "string"}}}},
        {"name": "get_referenced_but_missing", "description": "Documents cited in our archive but absent from the index.",
         "input_schema": {"type": "object", "properties": {"case_file": {"type": "string"}}}},
    ]

    TOOL_URL_MAP = {
        "query_documents": f"{BASE}/api/query_documents",
        "cross_reference": f"{BASE}/api/cross_reference",
        "get_party_history": f"{BASE}/api/party",
        "get_deadlines": f"{BASE}/api/deadlines",
        "get_pending_questions": f"{BASE}/api/questions",
        "get_referenced_but_missing": f"{BASE}/api/missing",
    }

    def call_tool(name, args):
        url = TOOL_URL_MAP.get(name)
        if not url: return {"error": f"unknown tool {name}"}
        try:
            r = _req.get(url, params=args, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    started = _time.time()
    messages = [{"role": "user", "content": question}]
    tool_calls_log = []
    final_text = ""
    tokens_in_total = 0
    tokens_out_total = 0

    for _ in range(10):  # max 10 agent turns
        resp = _req.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANT_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-5",
                "max_tokens": 4096,
                "system": system_prompt,
                "tools": TOOLS,
                "messages": messages,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"anthropic api {resp.status_code}: {resp.text[:500]}"}), 500
        data = resp.json()
        usage = data.get("usage", {})
        tokens_in_total += usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
        tokens_out_total += usage.get("output_tokens", 0)
        stop_reason = data.get("stop_reason")
        content = data.get("content", [])

        # Collect any tool_use blocks
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        text_blocks = [b for b in content if b.get("type") == "text"]

        if not tool_uses:
            final_text = "\n".join(b.get("text", "") for b in text_blocks)
            break

        # Execute each tool and append to messages
        messages.append({"role": "assistant", "content": content})
        tool_results = []
        for tu in tool_uses:
            t_started = _time.time()
            result = call_tool(tu["name"], tu.get("input", {}))
            tool_calls_log.append({
                "tool": tu["name"],
                "params": tu.get("input", {}),
                "result_count": result.get("count") if isinstance(result, dict) else None,
                "duration_ms": int((_time.time() - t_started) * 1000),
                "error": result.get("error") if isinstance(result, dict) else None,
            })
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": _json.dumps(result)[:8000],
            })
        messages.append({"role": "user", "content": tool_results})

        if stop_reason == "end_turn":
            final_text = "\n".join(b.get("text", "") for b in text_blocks)
            break

    duration_ms = int((_time.time() - started) * 1000)

    # Try to extract JSON from final_text (Leo's prompt requires JSON output)
    parsed = None
    start = final_text.find("{"); end = final_text.rfind("}")
    if start != -1 and end > start:
        try: parsed = _json.loads(final_text[start:end+1])
        except Exception: pass

    reply_text = (parsed or {}).get("telegram_reply_to_client", final_text[:1000])
    case_file = (parsed or {}).get("case_file", p.get("case_file_hint"))

    # Log to leo_interactions
    c = db(); cur = c.cursor()
    try:
        est_cost = _estimate_cost_cents("claude-sonnet-4-5", tokens_in_total, tokens_out_total)
        cur.execute("""
            INSERT INTO leo_interactions
              (channel, sender_id, sender_name, question, case_file,
               tool_calls, response_json, reply_text, duration_ms,
               eval_question_id, eval_expected,
               tokens_in, tokens_out, model, est_cost_cents)
            VALUES ('eval', 'eval-runner', 'Eval Runner', %s, %s,
                    %s::jsonb, %s::jsonb, %s, %s,
                    %s, %s::jsonb,
                    %s, %s, %s, %s)
            RETURNING id
        """, (
            question, case_file,
            _json.dumps(tool_calls_log),
            _json.dumps(parsed) if parsed else None,
            reply_text, duration_ms,
            p.get('eval_question_id'),
            _json.dumps(p.get('expected')) if p.get('expected') else None,
            tokens_in_total, tokens_out_total, "claude-sonnet-4-5", est_cost,
        ))
        interaction_id = cur.fetchone()[0]
        c.commit()
    finally:
        cur.close(); c.close()

    return jsonify({
        "interaction_id": interaction_id,
        "question": question,
        "duration_ms": duration_ms,
        "tool_calls": tool_calls_log,
        "final_text": final_text,
        "parsed_json": parsed,
        "reply_text": reply_text,
        "case_file": case_file,
        "tokens_in": tokens_in_total,
        "tokens_out": tokens_out_total,
        "est_cost_cents": est_cost,
    })



@app.route('/api/usage_summary')
def usage_summary():
    """Aggregated token usage and cost. Query params: ?days=1 | 7 | 30."""
    try:
        days = max(1, min(int(request.args.get('days', 1)), 90))
    except (TypeError, ValueError):
        days = 1
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT
              COALESCE(model, '(none)') AS model,
              channel,
              COUNT(*) AS calls,
              COALESCE(SUM(tokens_in), 0) AS tokens_in,
              COALESCE(SUM(tokens_out), 0) AS tokens_out,
              COALESCE(SUM(est_cost_cents), 0) AS est_cost_cents
            FROM leo_interactions
            WHERE timestamp > NOW() - INTERVAL '1 day' * %s
            GROUP BY model, channel
            ORDER BY est_cost_cents DESC NULLS LAST, calls DESC
        """, (days,))
        rows = cur.fetchall()
        cur.execute("""
            SELECT
              COALESCE(SUM(tokens_in + tokens_out), 0) AS total_tokens,
              COALESCE(SUM(est_cost_cents), 0) AS total_cents
            FROM leo_interactions
            WHERE timestamp > NOW() - INTERVAL '1 day' * %s
        """, (days,))
        totals = cur.fetchone()
    finally:
        cur.close(); c.close()
    return jsonify({
        "days": days,
        "by_model_channel": [
            {"model": r[0], "channel": r[1], "calls": r[2],
             "tokens_in": r[3], "tokens_out": r[4], "est_cost_cents": r[5]}
            for r in rows
        ],
        "totals": {"tokens": totals[0], "cost_cents": totals[1], "cost_usd": round(totals[1]/100, 2)},
    })


def _check_daily_budget(channel: str):
    """Return None if OK, else dict to return as 429 response."""
    import os as _os
    limit = int(_os.environ.get('LEO_DAILY_TOKEN_LIMIT', '100000'))
    if limit <= 0:
        return None
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT COALESCE(SUM(tokens_in + tokens_out), 0)
            FROM leo_interactions
            WHERE channel = %s
              AND timestamp > date_trunc('day', NOW() AT TIME ZONE 'UTC')
        """, (channel,))
        used = cur.fetchone()[0] or 0
    finally:
        cur.close(); c.close()
    if used >= limit:
        return {"error": f"daily {channel} token budget {limit} exhausted (used {used})",
                "tokens_used_today": used, "limit": limit}
    return None


# Model pricing in cents per 1K tokens. Refresh as prices change.
_PRICING = {
    "claude-sonnet-4-5":    {"in": 0.300, "out": 1.500},
    "claude-haiku-4-5-20251001": {"in": 0.100, "out": 0.500},
    "claude-opus-4-6":      {"in": 1.500, "out": 7.500},
    "llama-3.3-70b-versatile": {"in": 0.000, "out": 0.000},  # Groq free
    "gemini-2.0-flash":     {"in": 0.000, "out": 0.000},     # free tier
    "text-embedding-3-small": {"in": 0.002, "out": 0.000},
    "gpt-4o-mini":          {"in": 0.015, "out": 0.060},
}

def _estimate_cost_cents(model: str, t_in: int, t_out: int) -> int:
    p = _PRICING.get(model, {"in": 0.0, "out": 0.0})
    return int(round((t_in/1000) * p["in"] + (t_out/1000) * p["out"]))



@app.route('/api/eval_question_groq', methods=['POST'])
def eval_question_groq():
    """Run an eval question through Groq Llama 3.3 70B (FREE).
    Same shape as /api/eval_question but uses Groq's OpenAI-compatible API.
    Logs to leo_interactions with channel='eval' and model='llama-3.3-70b-versatile'."""
    import json as _json
    import time as _time
    import requests as _req
    import os as _os

    p = request.get_json(force=True, silent=True) or {}
    question = (p.get('question') or '').strip()
    if not question:
        return jsonify({"error": "question required"}), 400

    budget_err = _check_daily_budget("eval")
    if budget_err: return jsonify(budget_err), 429

    GROQ_KEY = _os.environ.get('GROQ_API_KEY')
    if not GROQ_KEY:
        try:
            with open('/root/landtek/.env') as f:
                for line in f:
                    if line.startswith('GROQ_API_KEY='):
                        GROQ_KEY = line.split('=', 1)[1].strip().strip('"').strip("'")
                        break
        except Exception: pass
    if not GROQ_KEY:
        return jsonify({"error": "GROQ_API_KEY not set"}), 500

    # Pull current system prompt from published workflow
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT node->'parameters'->'options'->>'systemMessage'
            FROM workflow_history,
              jsonb_array_elements(nodes::jsonb) AS node
            WHERE "versionId" = '4ebc5fa8-cbc8-4c48-a887-6627d77f456e'
              AND node->>'type' = '@n8n/n8n-nodes-langchain.agent'
            LIMIT 1
        """)
        row = cur.fetchone()
        system_prompt = row[0] if row else ""
    finally:
        cur.close(); c.close()

    if not system_prompt:
        return jsonify({"error": "could not load system prompt"}), 500

    BASE = "http://127.0.0.1:8765"
    TOOL_URL_MAP = {
        "query_documents": f"{BASE}/api/query_documents",
        "cross_reference": f"{BASE}/api/cross_reference",
        "get_party_history": f"{BASE}/api/party",
        "get_deadlines": f"{BASE}/api/deadlines",
        "get_pending_questions": f"{BASE}/api/questions",
        "get_referenced_but_missing": f"{BASE}/api/missing",
    }

    # OpenAI-style tool definitions with PERMISSIVE schemas (additionalProperties: true)
    # and rich descriptions with explicit example calls.
    TOOLS = [
        {"type": "function", "function": {
            "name": "query_documents",
            "description": (
                "Filter documents in the corpus by case_file, classification, year, or keyword. "
                "PRIMARY tool for 'list every X', 'every', 'all', 'latest', 'show me' questions. "
                "Example: to find all Titles in MWK-001 use {case_file: 'MWK-001', classification: 'Title'}. "
                "PARAMETER NAMES (use exactly these, no others): case_file, classification, year, keyword, limit. "
                "Do NOT use 'documenttype', 'document_type', or 'type' — the correct name is 'classification'. "
                "case_file must be one of: 'Paracale-001', 'MWK-001', 'Owner'. "
                "classification is a free-text substring match (ILIKE), e.g. 'Title' matches 'Title (TCT/OCT)'."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "case_file": {"type": "string"},
                    "classification": {"type": "string"},
                    "year": {"type": "string"},
                    "keyword": {"type": "string"},
                    "limit": {"type": "integer"}
                }
            }
        }},
        {"type": "function", "function": {
            "name": "cross_reference",
            "description": (
                "Find documents mentioning a specific reference string. Use for specific reference numbers "
                "(TCT-4501, CTN SL-2026-XXXX, MPSA-NNN, docket numbers, document IDs like '388'). "
                "Pass the reference string verbatim. Example: {reference: 'TCT-4501'} or {reference: '388'}."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"reference": {"type": "string"}}
            }
        }},
        {"type": "function", "function": {
            "name": "get_party_history",
            "description": (
                "Find documents mentioning a person or entity. Example: {name: 'Allan Inocalla'} or {name: 'Cabezudo'}. "
                "Pass just the name, no other params."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"name": {"type": "string"}}
            }
        }},
        {"type": "function", "function": {
            "name": "get_deadlines",
            "description": (
                "Get procedural dates (filings, hearings, statutory windows) within N days. "
                "Example: {within_days: 30} for upcoming month, or {within_days: 30, case_file: 'MWK-001'} to filter."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "within_days": {"type": "integer"},
                    "case_file": {"type": "string"}
                }
            }
        }},
        {"type": "function", "function": {
            "name": "get_pending_questions",
            "description": "Open questions awaiting Jonathan's input. Example: {} or {case_file: 'MWK-001'}.",
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"case_file": {"type": "string"}}
            }
        }},
        {"type": "function", "function": {
            "name": "get_referenced_but_missing",
            "description": "Documents cited in our archive but absent from the index. Example: {} or {case_file: 'MWK-001'}.",
            "parameters": {
                "type": "object",
                "additionalProperties": True,
                "properties": {"case_file": {"type": "string"}}
            }
        }},
    ]

    def call_tool(name, args):
        url = TOOL_URL_MAP.get(name)
        if not url: return {"error": f"unknown tool {name}"}
        try:
            r = _req.get(url, params=args, timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    started = _time.time()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    tool_calls_log = []
    final_text = ""
    tokens_in_total = 0
    tokens_out_total = 0
    MODEL = "llama-3.1-8b-instant"

    for _ in range(10):
        resp = _req.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
                "max_tokens": 4096,
            },
            timeout=60,
        )
        if resp.status_code != 200:
            # Retry once if it's a tool-call validation error (Groq is strict; Llama sometimes generates bad params)
            err_text = resp.text
            if resp.status_code == 400 and ("tool call validation" in err_text or "Failed to call a function" in err_text):
                # Append a clarifying message and retry
                messages.append({
                    "role": "user",
                    "content": "Your previous tool call had an invalid parameter shape. Use ONLY the parameter names listed in each tool's description. For query_documents the parameter is 'classification' (not 'documenttype' or 'type'). Do not include any parameters not listed in the tool definition. Try again."
                })
                retry = _req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                    json={"model": MODEL, "messages": messages, "tools": TOOLS,
                          "tool_choice": "auto", "max_tokens": 4096},
                    timeout=60,
                )
                if retry.status_code == 200:
                    data = retry.json()
                    usage = data.get("usage", {})
                    tokens_in_total += usage.get("prompt_tokens", 0)
                    tokens_out_total += usage.get("completion_tokens", 0)
                    choice = data["choices"][0]
                    msg = choice["message"]
                    tool_calls = msg.get("tool_calls") or []
                    if not tool_calls:
                        final_text = msg.get("content", "") or ""
                        break
                    messages.append({"role": "assistant", "content": msg.get("content"), "tool_calls": tool_calls})
                    for tc in tool_calls:
                        try: fn_args = _json.loads(tc["function"]["arguments"] or "{}")
                        except Exception: fn_args = {}
                        result = call_tool(tc["function"]["name"], fn_args)
                        tool_calls_log.append({"tool": tc["function"]["name"], "params": fn_args,
                            "result_count": result.get("count") if isinstance(result, dict) else None,
                            "error": result.get("error") if isinstance(result, dict) else None, "retry": True})
                        messages.append({"role": "tool", "tool_call_id": tc["id"], "content": _json.dumps(result)[:6000]})
                    continue
            return jsonify({"error": f"groq api {resp.status_code}: {resp.text[:500]}"}), 500
        data = resp.json()
        usage = data.get("usage", {})
        tokens_in_total += usage.get("prompt_tokens", 0)
        tokens_out_total += usage.get("completion_tokens", 0)

        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            final_text = msg.get("content", "") or ""
            break

        # Echo assistant message back into messages
        messages.append({
            "role": "assistant",
            "content": msg.get("content"),
            "tool_calls": tool_calls,
        })
        # Execute each tool
        for tc in tool_calls:
            t_started = _time.time()
            fn_name = tc["function"]["name"]
            try:
                fn_args = _json.loads(tc["function"]["arguments"] or "{}")
            except Exception:
                fn_args = {}
            result = call_tool(fn_name, fn_args)
            tool_calls_log.append({
                "tool": fn_name,
                "params": fn_args,
                "result_count": result.get("count") if isinstance(result, dict) else None,
                "duration_ms": int((_time.time() - t_started) * 1000),
                "error": result.get("error") if isinstance(result, dict) else None,
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": _json.dumps(result)[:6000],
            })

        if choice.get("finish_reason") == "stop":
            final_text = msg.get("content", "") or ""
            break

    duration_ms = int((_time.time() - started) * 1000)

    parsed = None
    start = final_text.find("{"); end = final_text.rfind("}")
    if start != -1 and end > start:
        try: parsed = _json.loads(final_text[start:end+1])
        except Exception: pass

    reply_text = (parsed or {}).get("telegram_reply_to_client", final_text[:1500])
    case_file = (parsed or {}).get("case_file", p.get("case_file_hint"))

    est_cost = _estimate_cost_cents(MODEL, tokens_in_total, tokens_out_total)

    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            INSERT INTO leo_interactions
              (channel, sender_id, sender_name, question, case_file,
               tool_calls, response_json, reply_text, duration_ms,
               eval_question_id, eval_expected,
               tokens_in, tokens_out, model, est_cost_cents)
            VALUES ('eval', 'eval-runner', 'Eval Runner (Groq)', %s, %s,
                    %s::jsonb, %s::jsonb, %s, %s,
                    %s, %s::jsonb,
                    %s, %s, %s, %s)
            RETURNING id
        """, (
            question, case_file,
            _json.dumps(tool_calls_log),
            _json.dumps(parsed) if parsed else None,
            reply_text, duration_ms,
            p.get('eval_question_id'),
            _json.dumps(p.get('expected')) if p.get('expected') else None,
            tokens_in_total, tokens_out_total, MODEL, est_cost,
        ))
        interaction_id = cur.fetchone()[0]
        c.commit()
    finally:
        cur.close(); c.close()

    return jsonify({
        "interaction_id": interaction_id,
        "question": question,
        "duration_ms": duration_ms,
        "tool_calls": tool_calls_log,
        "final_text": final_text,
        "parsed_json": parsed,
        "reply_text": reply_text,
        "case_file": case_file,
        "tokens_in": tokens_in_total,
        "tokens_out": tokens_out_total,
        "est_cost_cents": est_cost,
        "model": MODEL,
    })



@app.route('/api/get_entity', methods=['GET','POST'])
def get_entity():
    """Look up an entity by canonical name OR alias. Returns full profile + all docs + all threads."""
    body = request.get_json(silent=True) or {}
    name = (request.args.get('name') or body.get('name') or '').strip()
    if not name: return jsonify({"error": "name required"}), 400
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT id, type, canonical_name, aliases, metadata, mentions_count, confidence, notes
            FROM entities
            WHERE canonical_name ILIKE %s OR %s = ANY(aliases)
            ORDER BY mentions_count DESC LIMIT 5
        """, (f"%{name}%", name))
        ents = cur.fetchall()
        if not ents:
            return jsonify({"name": name, "count": 0, "entities": []})
        result = []
        for e in ents:
            cur.execute("""
                SELECT de.doc_id, d.case_file, d.classification, d.smart_filename,
                       de.role, de.context_excerpt
                FROM doc_entities de JOIN documents d ON d.id = de.doc_id
                WHERE de.entity_id = %s ORDER BY de.confidence DESC LIMIT 50
            """, (e[0],))
            docs = [{"doc_id": r[0], "case_file": r[1], "type": r[2], "file": r[3],
                     "role": r[4], "context": r[5]} for r in cur.fetchall()]
            result.append({
                "id": e[0], "type": e[1], "canonical_name": e[2],
                "aliases": e[3], "metadata": e[4],
                "mentions": e[5], "confidence": e[6], "notes": e[7],
                "documents": docs,
            })
    finally:
        cur.close(); c.close()
    return jsonify({"name": name, "count": len(result), "entities": result})



@app.route('/api/fuzzy_find_entity', methods=['GET','POST'])
def fuzzy_find_entity():
    """Find entities by fuzzy match using trigram similarity + phonetic key.
       Use this when the user might have misspelled or abbreviated a name.
       Returns top-10 candidates with confidence scores."""
    body = request.get_json(silent=True) or {}
    name = (request.args.get('name') or body.get('name') or '').strip()
    min_sim = float(request.args.get('min_sim') or body.get('min_sim') or 0.30)
    etype = (request.args.get('type') or body.get('type') or '').strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    c = db(); cur = c.cursor()
    try:
        sql = """
            SELECT e.id, e.type, e.canonical_name, e.aliases, e.mentions_count,
                   GREATEST(
                       similarity(e.canonical_name, %s),
                       COALESCE((SELECT MAX(similarity(a, %s)) FROM unnest(e.aliases) a), 0)
                   ) AS sim,
                   (e.phonetic_key = SOUNDEX(%s)) AS phonetic_match
              FROM entities e
             WHERE (e.canonical_name %% %s
                    OR EXISTS (SELECT 1 FROM unnest(e.aliases) a WHERE a %% %s)
                    OR e.phonetic_key = SOUNDEX(%s))
        """
        args = [name, name, name, name, name, name]
        if etype:
            sql += " AND e.type = %s"
            args.append(etype)
        sql += " ORDER BY sim DESC, mentions_count DESC LIMIT 10"
        cur.execute(sql, args)
        rows = cur.fetchall()
        results = [{
            "id": r[0], "type": r[1], "canonical_name": r[2],
            "aliases": r[3], "mentions": r[4],
            "similarity": float(r[5]) if r[5] is not None else None,
            "phonetic_match": bool(r[6]),
        } for r in rows if (r[5] or 0) >= min_sim or r[6]]
    finally:
        cur.close(); c.close()
    return jsonify({"query": name, "count": len(results), "matches": results})


@app.route('/api/get_thread_documents', methods=['GET','POST'])
def get_thread_documents():
    """Return all documents belonging to a case thread, ordered chronologically.
       Use this when answering anything tied to a thread (e.g. 'audit the RD title-history')
       — it guarantees scope discipline so off-topic docs from other matters in the same
       case_file are not included."""
    body = request.get_json(silent=True) or {}
    tid = request.args.get('thread_id') or body.get('thread_id') or request.args.get('id') or body.get('id')
    if not tid:
        return jsonify({"error": "thread_id required"}), 400
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return jsonify({"error": "thread_id must be an integer"}), 400
    c = db(); cur = c.cursor()
    try:
        cur.execute("""SELECT id, thread_name, parent_case_file, status, summary,
                              thread_scope_notes, last_relink_at
                         FROM case_threads WHERE id = %s""", (tid,))
        t = cur.fetchone()
        if not t:
            return jsonify({"error": "thread not found"}), 404
        cur.execute("""
            SELECT d.id, d.doc_date, d.classification, d.smart_filename, d.case_file,
                   ctd.role, ctd.linked_at
              FROM case_thread_documents ctd
              JOIN documents d ON d.id = ctd.doc_id
             WHERE ctd.thread_id = %s
             ORDER BY (CASE WHEN d.doc_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                            THEN d.doc_date::date END) DESC NULLS LAST, d.id DESC
        """, (tid,))
        docs = [{"doc_id": r[0], "date": r[1], "classification": r[2],
                 "filename": r[3], "case_file": r[4], "thread_role": r[5],
                 "linked_at": str(r[6]) if r[6] else None}
                for r in cur.fetchall()]
    finally:
        cur.close(); c.close()
    return jsonify({
        "thread": {"id": t[0], "name": t[1], "case_file": t[2], "status": t[3],
                   "summary": t[4], "scope_notes": t[5],
                   "last_relinked": str(t[6]) if t[6] else None},
        "count": len(docs), "documents": docs
    })

@app.route('/api/list_threads')
def list_threads():
    case = (request.args.get('case_file') or '').strip()
    c = db(); cur = c.cursor()
    try:
        sql = """SELECT id, parent_case_file, thread_name, thread_type, primary_reference,
                 status, opened_date, target_resolution_date, summary
                 FROM case_threads"""
        args = []
        if case:
            sql += " WHERE parent_case_file = %s"
            args.append(case)
        sql += " ORDER BY status, opened_date NULLS LAST"
        cur.execute(sql, args)
        rows = cur.fetchall()
    finally:
        cur.close(); c.close()
    return jsonify({"count": len(rows), "threads": [
        {"id": r[0], "parent_case_file": r[1], "thread_name": r[2], "thread_type": r[3],
         "primary_reference": r[4], "status": r[5], "opened_date": str(r[6]) if r[6] else None,
         "target_resolution_date": str(r[7]) if r[7] else None, "summary": r[8]} for r in rows]})


@app.route('/api/get_thread')
def get_thread():
    """Returns thread + linked docs + events + related threads."""
    tid = request.args.get('id') or request.args.get('thread_id')
    ref = (request.args.get('reference') or '').strip()
    name = (request.args.get('name') or '').strip()
    c = db(); cur = c.cursor()
    try:
        if tid:
            cur.execute("SELECT * FROM case_threads WHERE id = %s", (tid,))
        elif ref:
            cur.execute("SELECT * FROM case_threads WHERE primary_reference ILIKE %s LIMIT 1", (f"%{ref}%",))
        elif name:
            cur.execute("SELECT * FROM case_threads WHERE thread_name ILIKE %s LIMIT 1", (f"%{name}%",))
        else:
            return jsonify({"error": "provide id, reference, or name"}), 400
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row: return jsonify({"count": 0, "thread": None})
        thread = dict(zip(cols, row))
        for k in ("opened_date", "target_resolution_date", "last_activity_at", "created_at", "updated_at"):
            if thread.get(k): thread[k] = str(thread[k])
        tid = thread["id"]
        cur.execute("""
            SELECT d.id, d.case_file, d.classification, d.smart_filename,
                   td.role, td.notes
            FROM case_thread_documents td JOIN documents d ON d.id = td.doc_id
            WHERE td.thread_id = %s ORDER BY td.linked_at
        """, (tid,))
        docs = [{"doc_id": r[0], "case_file": r[1], "type": r[2], "file": r[3], "role": r[4], "notes": r[5]}
                for r in cur.fetchall()]
        cur.execute("""
            SELECT event_date, event_type, description, doc_id, participant
            FROM case_thread_events WHERE thread_id = %s ORDER BY event_date
        """, (tid,))
        events = [{"date": str(r[0]), "type": r[1], "description": r[2], "doc_id": r[3], "participant": r[4]}
                  for r in cur.fetchall()]
        cur.execute("""
            SELECT b.id, b.thread_name, b.thread_type, r.relation_type, r.evidence_basis
            FROM thread_relationships r JOIN case_threads b ON b.id = r.thread_b
            WHERE r.thread_a = %s
            UNION ALL
            SELECT a.id, a.thread_name, a.thread_type, r.relation_type, r.evidence_basis
            FROM thread_relationships r JOIN case_threads a ON a.id = r.thread_a
            WHERE r.thread_b = %s
        """, (tid, tid))
        related = [{"id": r[0], "thread_name": r[1], "thread_type": r[2],
                    "relation_type": r[3], "evidence_basis": r[4]} for r in cur.fetchall()]
    finally:
        cur.close(); c.close()
    return jsonify({"thread": thread, "documents": docs, "events": events, "related_threads": related})


@app.route('/api/pending_entity_types')
def pending_entity_types():
    c = db(); cur = c.cursor()
    try:
        cur.execute("""
            SELECT name, description, parent_type, added_at, COUNT(e.id) AS uses
            FROM entity_types et LEFT JOIN entities e ON e.type = et.name
            WHERE et.status = 'pending'
            GROUP BY name, description, parent_type, added_at
            ORDER BY added_at DESC
        """)
        rows = cur.fetchall()
    finally:
        cur.close(); c.close()
    return jsonify({"pending": [
        {"name": r[0], "description": r[1], "parent_type": r[2], "added_at": str(r[3]), "uses": r[4]}
        for r in rows]})


# ── Leo answer-gate over HTTP (deploy_617) ──────────────────────────────────────────────────
# Exposes the $0 deterministic discernment gate (scripts/leo_answer_gate.py) so the n8n workflow can
# strip a fabricated cite / ungrounded cascade from EVERY Leo reply before it ships — no LLM
# regeneration, no extra tokens. POST {"text": "..."} → {verdict, fails, warns, final_text}.
import sys as _gsys
_gsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import leo_answer_gate as _answer_gate


@app.route('/api/answer_gate', methods=['POST'])
def answer_gate():
    data = request.get_json(force=True) or {}
    text = data.get('text', '')
    c = db(); cur = c.cursor()
    try:
        res = _answer_gate.gate(cur, text)
        # deterministic $0 fail-path: ship the grounded-only rewrite, never an LLM regen
        res['final_text'] = text if res['verdict'] == 'pass' else _answer_gate.remediate(cur, text, res)
        return jsonify(res)
    finally:
        cur.close(); c.close()


# ── Leo retrieve-before grounding (deploy_618) ──────────────────────────────────────────────
# The "RETRIEVE, then reason" data path the discernment protocol references: Leo pulls a matter's
# VERIFIED (document-proven) facts here BEFORE answering, so dates/facts come from structured rows
# (exact) not the vector store (close-enough). Verified-only by design — the only tier surfaced as
# fact — and matter-scoped (client-separation: no cross-client leakage). Each fact carries its cite.
#   GET  /api/get_verified_facts?matter=MWK-CV26360[&q=balane][&limit=60]
#   POST /api/get_verified_facts  {"matter": "...", "q": "...", "limit": 60}
@app.route('/api/get_verified_facts', methods=['GET', 'POST'])
def get_verified_facts():
    data = (request.get_json(force=True, silent=True) or {}) if request.method == 'POST' else {}
    matter = (data.get('matter') or request.args.get('matter') or '').strip()
    q = (data.get('q') or request.args.get('q') or '').strip()
    try:
        limit = min(int(data.get('limit') or request.args.get('limit') or 60), 500)
    except (TypeError, ValueError):
        limit = 60
    if not matter:
        return jsonify({"error": "matter required (verified facts are matter-scoped)", "facts": []}), 400
    sql = ("SELECT statement, excerpt, source_kind, source_id, fact_kind, as_of, confidence "
           "FROM matter_facts WHERE matter_code = %s AND provenance_level = 'verified'")
    params = [matter]
    if q:
        sql += " AND (statement ILIKE %s OR excerpt ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY id LIMIT %s"
    params.append(limit)
    c = db(); cur = c.cursor()
    try:
        cur.execute(sql, params)
        rows = cur.fetchall()
    finally:
        cur.close(); c.close()
    facts = [{
        "statement": st,
        "cite": (f"doc:{sid}" if sk == 'doc' and sid else (f"{sk}:{sid}" if sid else None)),
        "excerpt": exc,
        "fact_kind": fk,
        "as_of": str(asof) if asof else None,
        "confidence": conf,
    } for st, exc, sk, sid, fk, asof, conf in rows]
    return jsonify({"matter": matter, "count": len(facts), "facts": facts,
                    "note": "verified-only (document-proven); cite each fact as shown"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8765)
