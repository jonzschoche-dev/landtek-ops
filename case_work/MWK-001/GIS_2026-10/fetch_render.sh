#!/bin/bash
# fetch_render.sh <drive_file_id> <name>  — downloads a Drive scan on the VPS (service account),
# renders every page at 170 dpi, and copies the PNGs to $OUT (default: ./scans/<name>/) on this Mac.
set -e
ID=$1; NAME=$2; OUT=${OUT:-$(dirname "$0")/scans/$NAME}; mkdir -p "$OUT"
ssh landtek "mkdir -p /tmp/x2/$NAME && cd /tmp/x2/$NAME && python3 - <<PY
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import fitz
c=service_account.Credentials.from_service_account_file('/root/landtek/google-creds.json',scopes=['https://www.googleapis.com/auth/drive.readonly'])
s=build('drive','v3',credentials=c,cache_discovery=False)
r=s.files().get_media(fileId='$ID',supportsAllDrives=True); f=open('src','wb'); d=MediaIoBaseDownload(f,r); done=False
while not done: _,done=d.next_chunk()
f.close()
try:
    doc=fitz.open('src')
    for i,p in enumerate(doc): p.get_pixmap(dpi=170).save(f'p{i+1}.png')
except Exception:
    import shutil; shutil.copy('src','p1.png')
print('pages ok')
PY"
scp -q "landtek:/tmp/x2/$NAME/p*.png" "$OUT/"
ls "$OUT"
