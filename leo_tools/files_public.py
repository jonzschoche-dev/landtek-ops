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
