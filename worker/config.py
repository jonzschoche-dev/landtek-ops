"""LeoLandTek v4 worker configuration.

Loads /root/landtek/.env into the process environment, exposes typed
constants for the rest of the worker package.
"""
import os
from pathlib import Path

ENV_FILE = Path("/root/landtek/.env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GOOGLE_CREDS      = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/root/landtek/google-creds.json")
TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY", "")
QDRANT_URL        = os.getenv("QDRANT_URL", "")
QDRANT_KEY        = os.getenv("QDRANT_KEY", "")
GOOGLE_DRIVE_API_KEY = os.getenv("GOOGLE_DRIVE_API_KEY", "")

DOCAI_PROJECT_ID   = os.getenv("DOCAI_PROJECT_ID", "287898704764")
DOCAI_PROCESSOR_ID = os.getenv("DOCAI_PROCESSOR_ID", "29ccddeea977ef1f")
DOCAI_LOCATION     = os.getenv("DOCAI_LOCATION", "us")
DOCAI_URL = (
    f"https://{DOCAI_LOCATION}-documentai.googleapis.com/v1/"
    f"projects/{DOCAI_PROJECT_ID}/locations/{DOCAI_LOCATION}/"
    f"processors/{DOCAI_PROCESSOR_ID}:process"
)

PG_HOST     = os.getenv("PGHOST", "localhost")
PG_PORT     = int(os.getenv("PGPORT", "5432"))
PG_DATABASE = os.getenv("PGDATABASE", "n8n")
PG_USER     = os.getenv("PGUSER", "n8n")
PG_PASSWORD = os.getenv("PGPASSWORD", "")

# Model strings per system info
ANTHROPIC_MODEL_HEAVY  = os.getenv("ANTHROPIC_MODEL_HEAVY",  "claude-opus-4-6")
ANTHROPIC_MODEL_MEDIUM = os.getenv("ANTHROPIC_MODEL_MEDIUM", "claude-sonnet-4-6")
ANTHROPIC_MODEL_LIGHT  = os.getenv("ANTHROPIC_MODEL_LIGHT",  "claude-haiku-4-5-20251001")

OPENAI_MODEL_FALLBACK = os.getenv("OPENAI_MODEL_FALLBACK", "gpt-4o")

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_DIM   = int(os.getenv("EMBEDDING_DIM", "3072"))

# Pass 1 thresholds
OCR_MIN_TEXT_LEN     = 200
OCR_MIN_ALPHA_RATIO  = 0.40
OCR_MIN_CONFIDENCE   = 0.70
OCR_HIGH_CONFIDENCE  = 0.90

# Pass 4 self-consistency
CLASSIFICATION_RUNS = 3
CLASSIFICATION_AGREEMENT_THRESHOLD = 2  # need 2/3 to commit
