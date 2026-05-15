#!/usr/bin/env python3
"""
FINAL Leo 1.0 Native Telegram File Upload
All bugs fixed - native file saved + record in documents table.
"""

import sys
import json
import requests
import mimetypes
import os
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import psycopg2

load_dotenv("/root/landtek/.env")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDS_PATH = "/root/landtek/landtek-compute-sa.json"

SLUG_TO_CASE_FILE = {
    "mwk": "MWK-001",
    "owner": "Owner"
}

def get_drive_service():
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH,
        scopes=['https://www.googleapis.com/auth/drive.file']
    )
    return build('drive', 'v3', credentials=creds)

def upload_native_file(file_id, client_slug, original_filename):
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    # Get file path
    file_info = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}").json()
    file_path = file_info['result']['file_path']

    # Download raw file
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
    response = requests.get(download_url)
    response.raise_for_status()
    file_bytes = response.content

    # Upload to Drive
    service = get_drive_service()
    folder_id = "1roy5YlHJIHKbV8hYsxYu6ptonlM7Lmj2" if client_slug == "mwk" else "1eDLECG_Lu9dXh-FLeCTvjI3fJclMid2b"

    file_metadata = {'name': original_filename, 'parents': [folder_id]}
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mimetypes.guess_type(original_filename)[0] or 'application/octet-stream')

    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    # Insert into documents table (final correct columns)
    case_file = SLUG_TO_CASE_FILE.get(client_slug, client_slug)
    conn = psycopg2.connect(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO documents (case_file, original_filename, drive_file_id, mime_type)
        VALUES (%s, %s, %s, %s)
    """, (case_file, original_filename, file.get('id'), mimetypes.guess_type(original_filename)[0]))
    conn.commit()
    cur.close()
    conn.close()

    return {
        "status": "success",
        "drive_file_id": file.get('id'),
        "client": client_slug,
        "case_file": case_file,
        "original_filename": original_filename
    }

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        data = json.loads(raw)
        result = upload_native_file(
            data.get("file_id"),
            data.get("client", "mwk"),
            data.get("original_filename", "unknown_file")
        )
        print(json.dumps(result))
    else:
        print("telegram_file_to_drive ready")
