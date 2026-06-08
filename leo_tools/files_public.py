"""files_public - unauthenticated /files/c/<doc_id> blueprint.

Streams docs to Jonathan's phone from Telegram replies without depending on
Drive's preview UI, in-app browser auth state, or Google session cookies.

Nginx is already configured to proxy /files/c/ to this port without
basic-auth (vs /files/ which DOES require it).

Strategy per doc:
  1. If documents.file_path exists locally -> stream from disk
  2. Else if drive_file_id is set -> stream from Drive via service account
  3. Else 404

Service-account creds at /root/landtek/google-creds.json; the LANDTEK Drive
folder is shared with leolandtek-docai@landtek.iam.gserviceaccount.com.
"""
from __future__ import annotations

import io
import os
from flask import Blueprint, Response, abort, send_file

import psycopg2

bp = Blueprint("files_public", __name__, url_prefix="/files/c")

GOOGLE_CREDS_PATH = "/root/landtek/google-creds.json"


def _db():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "172.18.0.3"),
        dbname=os.environ.get("PGDATABASE", "n8n"),
        user=os.environ.get("PGUSER", "n8n"),
        password=os.environ.get("PGPASSWORD", "n8npassword"),
    )


_drive_client = None
def _drive():
    """Lazy-init the Drive service-account client. Cached for the process."""
    global _drive_client
    if _drive_client is not None:
        return _drive_client
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    _drive_client = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_client


def _stream_drive(drive_file_id, filename, mime):
    """Fetch the file bytes from Drive and return as a Flask Response."""
    from googleapiclient.http import MediaIoBaseDownload
    svc = _drive()
    buf = io.BytesIO()
    req = svc.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    safe_name = (filename or f"{drive_file_id}.pdf").replace('"', "_")
    return Response(
        buf.read(),
        mimetype=mime or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "private, max-age=3600",
            "X-Source": "drive-proxy",
        },
    )


@bp.route("/<int:doc_id>")
def serve(doc_id):
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, file_path, drive_file_id, mime_type, original_filename, smart_filename
             FROM documents WHERE id = %s""",
        (doc_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404, "doc not found")
    _id, file_path, drive_id, mime, orig_name, smart_name = row
    name = smart_name or orig_name or f"doc-{doc_id}.pdf"

    # 1. Local file path (fastest)
    if file_path and os.path.exists(file_path):
        return send_file(
            file_path,
            as_attachment=False,
            download_name=name,
            mimetype=mime or "application/pdf",
        )

    # 2. Drive fallback
    if drive_id:
        try:
            return _stream_drive(drive_id, name, mime)
        except Exception as e:
            return Response(
                f"failed to stream from Drive: {type(e).__name__}: {e}",
                status=502,
                mimetype="text/plain",
            )

    return Response(
        f"doc {doc_id} has no file_path and no drive_file_id",
        status=404,
        mimetype="text/plain",
    )


@bp.route("/vault")
def vault_table():
    """Live HTML table: every physical vault entry <-> its digital corpus copy
    and a download link. Public (same as the file proxy), mobile-friendly, and
    always current. Leo links here when anyone asks for "the vault table" or the
    physical<->digital correlation, instead of trying to paste a table into chat.
    """
    import html
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.vault_section, d.vault_number, d.smart_filename,
               d.digital_scan_id, s.smart_filename, s.doc_date,
               (s.file_path IS NOT NULL OR s.drive_file_id IS NOT NULL) AS dl
          FROM documents d
          LEFT JOIN documents s ON s.id = d.digital_scan_id
         WHERE d.master_form = 'physical' AND d.vault_section IS NOT NULL
         ORDER BY d.vault_section, d.vault_number
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    body = []
    linked = 0
    for sec, num, pname, scan_id, dname, ddate, dl in rows:
        locator = f"{sec}-{num:03d}"
        # physical_name usually starts with the locator — strip it for clarity
        desc = (pname or "").strip()
        if desc.upper().startswith(locator):
            desc = desc[len(locator):].strip()
        desc = html.escape(desc[:90])
        dname_e = html.escape((dname or "")[:60])
        ddate_e = html.escape(str(ddate) if ddate else "")
        if scan_id and dl:
            link = (f'<a href="/files/c/{scan_id}">open / download</a>'
                    f' <span class="muted">(doc#{scan_id})</span>')
            linked += 1
        elif scan_id:
            link = f'<span class="warn">linked but no scan uploaded (doc#{scan_id})</span>'
        else:
            link = '<span class="warn">no digital copy yet</span>'
        body.append(
            f"<tr><td class='loc'>{locator}</td><td>{desc}</td>"
            f"<td>{dname_e}<br><span class='muted'>{ddate_e}</span></td>"
            f"<td>{link}</td></tr>"
        )

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LandTek Vault &harr; Digital Corpus</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;color:#1a1a1a;background:#fafafa}}
 h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}}
 th{{background:#f4f4f6;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#555}}
 td.loc{{font-weight:600;white-space:nowrap}} a{{color:#0a58ca;text-decoration:none}} a:hover{{text-decoration:underline}}
 .muted{{color:#999;font-size:11px}} .warn{{color:#b54708;font-size:12px}}
</style></head><body>
<h1>LandTek Physical Vault &harr; Digital Corpus</h1>
<div class="sub">{len(rows)} vault entries &middot; {linked} with a downloadable digital copy &middot; live view</div>
<table><thead><tr><th>Vault</th><th>Document</th><th>Digital copy</th><th>Link</th></tr></thead>
<tbody>{''.join(body)}</tbody></table>
</body></html>"""
    return Response(page, mimetype="text/html")


@bp.route("/m/<matter_code>")
def matter_table(matter_code):
    """Live HTML table of every document linked to a matter, with download
    links. Public, mobile-friendly. Leo links here when asked for "all the
    documents / links for ARTA-NNNN" instead of pasting URLs into chat."""
    import html
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, COALESCE(NULLIF(d.smart_filename,''), d.original_filename),
               d.doc_date, d.classification,
               (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL) AS dl
          FROM documents d
          JOIN document_matter_links l ON l.doc_id = d.id
         WHERE l.matter_code = %s
         ORDER BY d.doc_date NULLS LAST, d.id
        """,
        (matter_code,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    body = []
    avail = 0
    for did, fname, ddate, cls, dl in rows:
        nm = html.escape((fname or f"doc {did}")[:78])
        dt = html.escape(str(ddate) if ddate else "")
        cl = html.escape((cls or "")[:24])
        if dl:
            link = f'<a href="/files/c/{did}">download</a>'
            avail += 1
        else:
            link = '<span class="warn">no scan yet</span>'
        body.append(
            f"<tr><td>{dt}</td><td>{nm}<br><span class='muted'>{cl} · doc#{did}</span></td>"
            f"<td>{link}</td></tr>"
        )
    title = html.escape(matter_code)
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — documents</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;background:#fafafa;color:#1a1a1a}}
 h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}}
 th{{background:#f4f4f6;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#555}}
 a{{color:#0a58ca;text-decoration:none}} a:hover{{text-decoration:underline}}
 .muted{{color:#999;font-size:11px}} .warn{{color:#b54708;font-size:12px}}
</style></head><body>
<h1>{title} — documents</h1>
<div class="sub">{len(rows)} documents · {avail} downloadable · live view</div>
<table><thead><tr><th>Date</th><th>Document</th><th>File</th></tr></thead>
<tbody>{''.join(body) or '<tr><td colspan=3>No documents linked to this matter.</td></tr>'}</tbody></table>
</body></html>"""
    return Response(page, mimetype="text/html")


@bp.route("/<int:doc_id>/info")
def info(doc_id):
    """Metadata JSON so Leo or n8n can confirm what the URL serves."""
    from flask import jsonify
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, case_file, matter_code, smart_filename, original_filename,
                  mime_type, drive_file_id, file_path, document_title, summary
             FROM documents WHERE id = %s""",
        (doc_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404)
    keys = ["id", "case_file", "matter_code", "smart_filename", "original_filename",
            "mime_type", "drive_file_id", "file_path", "document_title", "summary"]
    return jsonify(dict(zip(keys, row)))
