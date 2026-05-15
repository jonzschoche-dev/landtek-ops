#!/usr/bin/env bash
# diag.sh — figure out why telegram_file_to_drive.py isn't getting files to Drive.
# Safe to run repeatedly. Prints what's working and what isn't.

set -uo pipefail

hr() { printf '\n=== %s ===\n' "$1"; }

hr "host"
hostname
date -u

hr "python interpreter n8n likely uses"
which python3
python3 --version

hr "python imports the script needs"
python3 - <<'PY' 2>&1
mods = ["dotenv", "psycopg2", "googleapiclient", "google.oauth2", "requests"]
for m in mods:
    try:
        __import__(m)
        print(f"  OK    {m}")
    except Exception as e:
        print(f"  FAIL  {m}: {type(e).__name__}: {e}")
PY

hr "service account file"
SA=/root/landtek/landtek-compute-sa.json
if [ -f "$SA" ]; then
  ls -la "$SA"
  echo "service account email:"
  python3 -c "import json; print('  ' + json.load(open('$SA'))['client_email'])" 2>&1
else
  echo "  MISSING: $SA"
fi

hr ".env keys present (names only, no values)"
if [ -f /root/landtek/.env ]; then
  grep -E '^[A-Z_][A-Z0-9_]*=' /root/landtek/.env | cut -d= -f1 | sed 's/^/  /'
  echo
  echo "TELEGRAM_BOT_TOKEN present and non-empty?"
  if grep -qE '^TELEGRAM_BOT_TOKEN=.+' /root/landtek/.env; then
    echo "  yes"
  else
    echo "  NO — empty or missing"
  fi
else
  echo "  MISSING: /root/landtek/.env"
fi

hr "postgres reachable as user n8n"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "SELECT current_user, current_database(), now();" 2>&1

hr "postgres container internal IP (vs hardcoded 172.18.0.3 in script)"
docker inspect n8n-postgres-1 -f '  IP: {{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>&1

hr "documents table schema"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "\d documents" 2>&1

hr "row count in documents"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "SELECT count(*) FROM documents;" 2>&1

hr "most recent 5 rows in documents"
docker exec n8n-postgres-1 psql -U n8n -d n8n -c "SELECT id, case_file, original_filename, drive_file_id, created_at FROM documents ORDER BY id DESC LIMIT 5;" 2>&1

hr "smoke test: connect with the SAME args the script uses"
python3 - <<'PY' 2>&1
import psycopg2
try:
    conn = psycopg2.connect(host="172.18.0.3", dbname="n8n", user="n8n", password="n8npassword", connect_timeout=5)
    cur = conn.cursor()
    cur.execute("SELECT 1")
    print("  OK — script's hardcoded connection works")
    conn.close()
except Exception as e:
    print(f"  FAIL — {type(e).__name__}: {e}")
    print("  (this is the most likely reason files appear to not save)")
PY

hr "smoke test: same but using container DNS name (recommended fix)"
python3 - <<'PY' 2>&1
import psycopg2
try:
    conn = psycopg2.connect(host="n8n-postgres-1", dbname="n8n", user="n8n", password="n8npassword", connect_timeout=5)
    print("  OK — container-name DNS works (use this instead of 172.18.0.3)")
    conn.close()
except Exception as e:
    print(f"  FAIL — {type(e).__name__}: {e}")
PY

hr "Drive folder access test"
python3 - <<'PY' 2>&1
import os
SA = "/root/landtek/landtek-compute-sa.json"
FOLDERS = {
    "mwk":   "1roy5YlHJIHKbV8hYsxYu6ptonlM7Lmj2",
    "owner": "1eDLECG_Lu9dXh-FLeCTvjI3fJclMid2b",
}
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        SA, scopes=["https://www.googleapis.com/auth/drive"])
    svc = build("drive", "v3", credentials=creds)
    for label, fid in FOLDERS.items():
        try:
            meta = svc.files().get(fileId=fid, fields="id,name,mimeType").execute()
            print(f"  OK    {label:6} {fid}  -> {meta.get('name')}")
        except Exception as e:
            print(f"  FAIL  {label:6} {fid}  -> {type(e).__name__}: {e}")
            print(f"        likely: folder not shared with the service account email above")
except Exception as e:
    print(f"  COULD NOT INITIALIZE DRIVE CLIENT: {type(e).__name__}: {e}")
PY

hr "done"
