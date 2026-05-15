#!/bin/bash
# LANDTEK Run Script — sets env vars and launches the pipeline
# Edit API keys below or source from a .env file

export OPENAI_API_KEY="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"
export GEMINI_API_KEY="AIzaSyCAYfXQrsrAolaGhSzAcFat7g6NzBIMQbQ"
export GOOGLE_APPLICATION_CREDENTIALS="/root/landtek/google-creds.json"
export DATABASE_URL="postgresql://postgres:postgres@localhost/landtek"
export QDRANT_HOST="localhost"
export QDRANT_PORT="6333"
export INBOX_DIR="/root/landtek/inbox"

# Optional — only needed for scanned/image PDFs
# export DOCAI_PROJECT="your-gcp-project-id"
# export DOCAI_LOCATION="us"
# export DOCAI_PROCESSOR="your-processor-id"

# Optional — only needed if service account uses domain-wide delegation
# export GOOGLE_IMPERSONATE_USER="jonathan@hayuma.org"

echo "Starting LANDTEK ingestion pipeline …"
python3 /root/landtek/ingest.py "$@"
