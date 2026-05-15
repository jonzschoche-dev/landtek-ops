#!/usr/bin/env bash
# deploy_135_scannerpro_ingest.sh — pull all PDFs from ScannerPro Drive folder,
# dedupe by sha256, classify via Gemini fallback key, INSERT into documents,
# and move each file to its canonical case folder via Service Account.
#
# Idempotent: re-runs skip files already in documents.drive_file_id.
# Uses fallback Gemini key so the running TCT sweep is unaffected.

set -euo pipefail
DEPLOY="135"
SCANNERPRO_FOLDER_ID="1TAksYrG-BzoOfc3UEIEZgJ6lBzu3IzmY"
SA_KEY="/root/landtek/google-creds.json"   # adjust if SA key lives elsewhere
LOG="/var/log/scannerpro_ingest_$(date +%F).log"

echo "=== deploy_${DEPLOY} starting at $(date -u +%FT%TZ) ===" | tee -a "$LOG"

# ──────────────────────────────────────────────────────────────────────
# 1. Ensure schema is ready
# ──────────────────────────────────────────────────────────────────────
docker exec -i n8n-postgres-1 psql -U n8n -d n8n <<'SQL' 2>&1 | tee -a "$LOG"
-- columns the ingest needs; idempotent ADDs
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='documents' AND column_name='sha256') THEN
    ALTER TABLE documents ADD COLUMN sha256 TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='documents' AND column_name='ingest_source') THEN
    ALTER TABLE documents ADD COLUMN ingest_source TEXT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='documents' AND column_name='ingest_status') THEN
    ALTER TABLE documents ADD COLUMN ingest_status TEXT DEFAULT 'pending_classification';
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_drive_file_id_unique
  ON documents(drive_file_id) WHERE drive_file_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_documents_ingest_status ON documents(ingest_status);
SQL

# ──────────────────────────────────────────────────────────────────────
# 2. Python: list folder → dedupe → download → hash → INSERT → classify → move
# ──────────────────────────────────────────────────────────────────────
cat > /root/landtek/autonomous/scannerpro_ingest.py <<'PYEOF'
#!/usr/bin/env python3
"""ScannerPro folder ingest with dedup + Gemini classify + Drive move."""
import hashlib
import io
import json
import os
import sys
import time
import psycopg2
from psycopg2.extras import Json
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import google.generativeai as genai

FOLDER_ID  = os.environ["SCANNERPRO_FOLDER_ID"]
SA_KEY     = os.environ["SA_KEY"]
GEMINI_KEY = os.environ.get("GEMINI_API_KEY_FALLBACK") or os.environ["GEMINI_API_KEY"]
DB_DSN     = os.environ.get("LANDTEK_DSN",
                "host=172.18.0.3 dbname=n8n user=n8n password=n8npassword")
DOWNLOAD_DIR = Path("/root/landtek/uploads/scannerpro")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Canonical case folder targets — adjust IDs to your actual folders.
# Fallback: keep file in ScannerPro folder until manual classification.
CASE_FOLDERS = {
    "MWK-001":     os.environ.get("FOLDER_MWK",   ""),
    "Paracale-001":os.environ.get("FOLDER_PARA",  ""),
    "Owner":       os.environ.get("FOLDER_OWNER", ""),
}

CLASSIFY_PROMPT = """You are classifying a legal/property document for filing.
Read the attached PDF and return STRICTLY this JSON (no markdown, no prose):

{
  "case_file": "MWK-001" | "Paracale-001" | "Owner" | "Unknown",
  "classification": "Title (TCT/OCT)" | "Court Filing" | "Tax Document" | "Demand Letter"
                  | "Correspondence" | "Letter" | "Deed" | "Receipt" | "Contract"
                  | "Email" | "Power of Attorney" | "Notice" | "Affidavit"
                  | "Government Submission" | "Special Power of Attorney"
                  | "Complaint" | "Legal Memorandum" | "Other",
  "year": "YYYY" | "",
  "primary_party":  "",
  "secondary_party": "",
  "reference_no": "",
  "summary_one_line": "",
  "confidence": 0.0
}

Rules:
- If the doc mentions T-4497, TCT in Camarines Norte, MWK, Heirs of MWK, Balane,
  Civil Case 26-360, ARTA, road donation — case_file = MWK-001.
- If it mentions Paracale, MPSA, MGB, mining claims — case_file = Paracale-001.
- If it's personal admin (no client-facing matter) — case_file = Owner.
- If unsure — case_file = Unknown and confidence < 0.5.
"""

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    creds  = service_account.Credentials.from_service_account_file(
        SA_KEY, scopes=["https://www.googleapis.com/auth/drive"]
    )
    drive  = build("drive", "v3", credentials=creds)
    genai.configure(api_key=GEMINI_KEY)
    model  = genai.GenerativeModel("gemini-2.5-flash")

    conn   = psycopg2.connect(DB_DSN)
    cur    = conn.cursor()

    # List PDFs in folder (paginated)
    page_token = None
    files = []
    while True:
        resp = drive.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType,size,modifiedTime,md5Checksum)",
            pageToken=page_token,
            pageSize=200,
        ).execute()
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token: break

    print(f"Found {len(files)} files in ScannerPro folder")
    stats = {"skipped_existing": 0, "ingested": 0, "classified": 0,
             "moved": 0, "errors": 0}

    for i, f in enumerate(files, 1):
        fid, fname = f["id"], f["name"]
        mime = f.get("mimeType", "")
        if not (mime == "application/pdf" or fname.lower().endswith(".pdf")):
            continue
        print(f"[{i}/{len(files)}] {fname}")

        # Already ingested?
        cur.execute("SELECT id, ingest_status FROM documents WHERE drive_file_id=%s", (fid,))
        existing = cur.fetchone()
        if existing and existing[1] not in ("pending_classification", "error"):
            stats["skipped_existing"] += 1
            continue

        # Download
        local = DOWNLOAD_DIR / f"{fid}.pdf"
        if not local.exists():
            req = drive.files().get_media(fileId=fid)
            with open(local, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

        sha = sha256_file(local)

        # Dedup by sha256
        cur.execute("SELECT id FROM documents WHERE sha256=%s AND drive_file_id<>%s",
                    (sha, fid))
        dup = cur.fetchone()
        if dup:
            print(f"  duplicate by sha (matches doc {dup[0]}); recording as dup")
            cur.execute("""INSERT INTO documents
                          (drive_file_id, file_name, sha256, ingest_source, ingest_status)
                          VALUES (%s,%s,%s,'scannerpro','duplicate')
                          ON CONFLICT (drive_file_id) DO NOTHING""",
                        (fid, fname, sha))
            conn.commit()
            stats["skipped_existing"] += 1
            continue

        # INSERT (or update if pending)
        if existing:
            cur.execute("""UPDATE documents
                          SET sha256=%s, ingest_source='scannerpro',
                              ingest_status='pending_classification'
                          WHERE id=%s""", (sha, existing[0]))
            doc_id = existing[0]
        else:
            cur.execute("""INSERT INTO documents
                          (drive_file_id, file_name, sha256, ingest_source, ingest_status,
                           file_path)
                          VALUES (%s,%s,%s,'scannerpro','pending_classification', %s)
                          RETURNING id""",
                        (fid, fname, sha, str(local)))
            doc_id = cur.fetchone()[0]
        conn.commit()
        stats["ingested"] += 1

        # Classify via Gemini fallback
        try:
            uploaded = genai.upload_file(str(local))
            resp = model.generate_content(
                [uploaded, CLASSIFY_PROMPT],
                generation_config={
                    "temperature": 0.0,
                    "max_output_tokens": 1024,
                    "response_mime_type": "application/json"
                },
                safety_settings=[{"category": c, "threshold": "BLOCK_NONE"}
                                for c in ["HARM_CATEGORY_HARASSMENT",
                                          "HARM_CATEGORY_HATE_SPEECH",
                                          "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                                          "HARM_CATEGORY_DANGEROUS_CONTENT"]]
            )
            classify = json.loads(resp.text)
            cur.execute("""UPDATE documents
                          SET case_file=%s, classification=%s, year=%s,
                              classification_json=%s, ingest_status='classified',
                              updated_at=now()
                          WHERE id=%s""",
                        (classify.get("case_file") or "Unknown",
                         classify.get("classification") or "Other",
                         classify.get("year") or None,
                         Json(classify), doc_id))
            conn.commit()
            stats["classified"] += 1
            print(f"  -> {classify.get('case_file')}/{classify.get('classification')} "
                  f"(conf {classify.get('confidence', 0):.2f})")

            # Move to canonical folder (only if confidence high enough)
            target_folder = CASE_FOLDERS.get(classify.get("case_file"), "")
            if target_folder and (classify.get("confidence", 0) >= 0.7):
                old_parents = ",".join(drive.files().get(fileId=fid,
                                       fields="parents").execute().get("parents", []))
                drive.files().update(
                    fileId=fid,
                    addParents=target_folder,
                    removeParents=old_parents,
                    fields="id, parents"
                ).execute()
                cur.execute("UPDATE documents SET ingest_status='filed' WHERE id=%s",
                            (doc_id,))
                conn.commit()
                stats["moved"] += 1
                print(f"  -> moved to {classify.get('case_file')} folder")
        except Exception as e:
            print(f"  ERROR classifying: {e}", file=sys.stderr)
            cur.execute("UPDATE documents SET ingest_status='error' WHERE id=%s",
                        (doc_id,))
            conn.commit()
            stats["errors"] += 1
            time.sleep(2)  # back off on error
            continue

        # Polite spacing to avoid 429
        time.sleep(0.5)

    print("=" * 60)
    print("FINAL STATS:")
    for k, v in stats.items():
        print(f"  {k:20s} : {v}")

if __name__ == '__main__':
    main()
PYEOF

chmod +x /root/landtek/autonomous/scannerpro_ingest.py

# ──────────────────────────────────────────────────────────────────────
# 3. Detect SA key path
# ──────────────────────────────────────────────────────────────────────
if [ ! -f "$SA_KEY" ]; then
  for p in /root/landtek/landtek-creds.json \
           /root/landtek/service-account.json \
           /root/landtek/sa.json; do
    if [ -f "$p" ]; then SA_KEY="$p"; break; fi
  done
fi
if [ ! -f "$SA_KEY" ]; then
  echo "ERROR: cannot find service account JSON. Set SA_KEY env var." >&2
  exit 2
fi
echo "Using SA key: $SA_KEY"

# ──────────────────────────────────────────────────────────────────────
# 4. Canonical case folder IDs (probed via probe_drive_folders.py on 2026-05-13).
#    The clients.legal_folder_path column holds HUMAN-READABLE PATHS, not Drive
#    IDs, so we hardcode the real IDs here. Re-run probe if folders move.
# ──────────────────────────────────────────────────────────────────────
FOLDER_MWK="1y3w8gIS8SG66J2npfKhKQibOUpqwUTUi"
FOLDER_PARA="1TKMNbNxnns0FdtEuvEPMLISnnmmy46jx"
FOLDER_OWNER="1D3RlVRP-WlbvSl_0t_NRxKQtgmi-6ht9"
echo "Case-folder IDs: MWK=$FOLDER_MWK  PARA=$FOLDER_PARA  OWNER=$FOLDER_OWNER"

# ──────────────────────────────────────────────────────────────────────
# 5. Run the ingest
# ──────────────────────────────────────────────────────────────────────
export SCANNERPRO_FOLDER_ID="$SCANNERPRO_FOLDER_ID"
export SA_KEY="$SA_KEY"
export FOLDER_MWK FOLDER_PARA FOLDER_OWNER
export GEMINI_API_KEY_FALLBACK="${GEMINI_API_KEY_FALLBACK:-${GEMINI_API_KEY:-}}"

pip3 install --quiet --break-system-packages \
  google-api-python-client google-auth google-generativeai psycopg2-binary 2>/dev/null || true

python3 /root/landtek/autonomous/scannerpro_ingest.py 2>&1 | tee -a "$LOG"

cd /root/landtek
git add -A
git commit -m "deploy_${DEPLOY}: ScannerPro ingest — dedupe by sha256, classify via Gemini fallback, auto-file to case folders" || true

echo
echo "=== deploy_${DEPLOY} complete ==="
echo "Log: $LOG"
echo "Run again any time — already-ingested files are skipped automatically."
