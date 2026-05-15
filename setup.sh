#!/bin/bash
# LANDTEK VPS Setup Script
# Run once on root@104.248.156.34 to prepare the environment
# Usage: bash /root/landtek/setup.sh
set -e

echo "======================================================"
echo "  LANDTEK Pipeline Setup"
echo "======================================================"

# ── 1. Create directories ─────────────────────────────────────────────────────
echo "[1/6] Creating directories …"
mkdir -p /root/landtek/inbox
mkdir -p /root/landtek/logs
echo "  ✓ /root/landtek/{inbox,logs}"

# ── 2. Install Python dependencies ────────────────────────────────────────────
echo "[2/6] Installing Python packages …"
pip install \
  pymupdf \
  openai \
  google-auth \
  google-auth-httplib2 \
  google-api-python-client \
  google-generativeai \
  google-cloud-documentai \
  psycopg2-binary \
  qdrant-client \
  requests \
  --break-system-packages -q
echo "  ✓ Packages installed"

# ── 3. Check Qdrant ───────────────────────────────────────────────────────────
echo "[3/6] Checking Qdrant …"
if ! curl -s http://localhost:6333/healthz | grep -q "ok"; then
  echo "  Qdrant not running — starting via Docker …"
  if command -v docker &>/dev/null; then
    docker run -d --name qdrant --restart unless-stopped \
      -p 6333:6333 -p 6334:6334 \
      -v /root/qdrant_storage:/qdrant/storage \
      qdrant/qdrant
    sleep 5
    echo "  ✓ Qdrant started"
  else
    echo "  ⚠ Docker not found — install Docker or run Qdrant manually"
    echo "    curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-musl.tar.gz | tar xz"
    echo "    ./qdrant &"
  fi
else
  echo "  ✓ Qdrant already running"
fi

# ── 4. Set up PostgreSQL database and table ───────────────────────────────────
echo "[4/6] Setting up PostgreSQL …"
DB_NAME="landtek"
DB_USER="postgres"

# Create database if it doesn't exist
psql -U "$DB_USER" -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 || \
  psql -U "$DB_USER" -c "CREATE DATABASE $DB_NAME;"

psql -U "$DB_USER" -d "$DB_NAME" -c "
CREATE TABLE IF NOT EXISTS documents (
    id                  SERIAL PRIMARY KEY,
    filename            TEXT NOT NULL,
    smart_filename      TEXT,
    case_file           TEXT,
    document_type       TEXT,
    doc_date            TEXT,
    parties             JSONB,
    reference_numbers   JSONB,
    summary             TEXT,
    strategic_relevance TEXT,
    drive_file_id       TEXT UNIQUE,
    drive_folder_id     TEXT,
    text_length         INTEGER,
    chunk_count         INTEGER,
    ocr_used            BOOLEAN DEFAULT FALSE,
    processed_at        TIMESTAMPTZ DEFAULT NOW(),
    error               TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_case_file ON documents(case_file);
CREATE INDEX IF NOT EXISTS idx_docs_doc_type  ON documents(document_type);
"
echo "  ✓ Database '$DB_NAME' and table 'documents' ready"

# ── 5. Verify google-creds.json exists ────────────────────────────────────────
echo "[5/6] Checking Google credentials …"
if [ -f /root/landtek/google-creds.json ]; then
  echo "  ✓ google-creds.json found"
  python3 -c "
import json
c = json.load(open('/root/landtek/google-creds.json'))
print(f'  SA email: {c.get(\"client_email\",\"unknown\")}')
print(f'  Project:  {c.get(\"project_id\",\"unknown\")}')
"
else
  echo "  ⚠ /root/landtek/google-creds.json NOT FOUND"
  echo "    Upload your service account JSON to that path before running ingest.py"
fi

# ── 6. Verify folders.json ────────────────────────────────────────────────────
echo "[6/6] Checking folders.json …"
if [ -f /root/landtek/folders.json ]; then
  echo "  ✓ folders.json found"
  python3 -c "import json; d=json.load(open('/root/landtek/folders.json')); print(f'  Cases: {list(d.keys())}')"
else
  echo "  ⚠ /root/landtek/folders.json NOT FOUND — copy it from your workspace"
fi

echo ""
echo "======================================================"
echo "  SETUP COMPLETE"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  1. Upload google-creds.json if not present"
echo "  2. Set environment variables (see run.sh or export manually):"
echo "     export OPENAI_API_KEY=sk-..."
echo "     export GEMINI_API_KEY=AIza..."
echo "     export GOOGLE_APPLICATION_CREDENTIALS=/root/landtek/google-creds.json"
echo "     export DATABASE_URL=postgresql://postgres:postgres@localhost/landtek"
echo "     # Optional: export GOOGLE_IMPERSONATE_USER=jonathan@hayuma.org"
echo "     # Optional: export DOCAI_PROJECT=your-gcp-project"
echo "     # Optional: export DOCAI_PROCESSOR=your-processor-id"
echo "  3. Run: python3 /root/landtek/ingest.py"
echo "  4. Backtest only: python3 /root/landtek/ingest.py --backtest"
echo ""
