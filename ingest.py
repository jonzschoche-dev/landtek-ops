#!/usr/bin/env python3
"""
LANDTEK Document Ingestion Pipeline v1.0
=========================================
Workflow:
  1. Download pending PDFs from Google Drive inbox staging folder
  2. Extract text via PyMuPDF; fall back to Document AI OCR if < 200 chars
  3. Classify document with GPT-4o (case, type, parties, refs, summary, etc.)
  4. Move file in Google Drive to correct case subfolder
  5. Chunk text (400-word windows, 50-word overlap)
  6. Embed each chunk with gemini-embedding-001 @ 768 dims
  7. Upsert to Qdrant collection landtek_documents
  8. Log to Postgres documents table

Usage:
  python ingest.py                  # full run (download + process)
  python ingest.py --no-download    # process local /root/landtek/inbox/ only
  python ingest.py --backtest       # run semantic search backtests only
"""

import os, sys, json, hashlib, io, re, uuid, logging, argparse, time
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ── deps ──────────────────────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
    import openai
    import google.generativeai as genai
    import psycopg2
    from psycopg2.extras import Json as PgJson
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.oauth2 import service_account
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance, VectorParams, PointStruct,
        Filter, FieldCondition, MatchValue
    )
except ImportError as e:
    sys.exit(f"Missing dependency: {e}\nRun: pip install pymupdf openai google-auth google-api-python-client google-generativeai psycopg2-binary qdrant-client --break-system-packages")

# ── config ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY          = os.environ["OPENAI_API_KEY"]
GEMINI_API_KEY          = os.environ["GEMINI_API_KEY"]
GOOGLE_CREDS            = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "/root/landtek/google-creds.json")
GOOGLE_IMPERSONATE_USER = os.environ.get("GOOGLE_IMPERSONATE_USER", "")   # leave blank if SA has direct Drive access
DATABASE_URL            = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/landtek")
QDRANT_HOST             = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT             = int(os.environ.get("QDRANT_PORT", "6333"))
QDRANT_API_KEY          = os.environ.get("QDRANT_API_KEY", "")
DOCAI_PROJECT           = os.environ.get("DOCAI_PROJECT", "")
DOCAI_LOCATION          = os.environ.get("DOCAI_LOCATION", "us")
DOCAI_PROCESSOR_ID      = os.environ.get("DOCAI_PROCESSOR", "")

INBOX_DIR        = Path(os.environ.get("INBOX_DIR", "/root/landtek/inbox"))
FOLDERS_JSON     = Path("/root/landtek/folders.json")
COLLECTION_NAME  = "landtek_documents"

CHUNK_WORDS      = 400
OVERLAP_WORDS    = 50
EMBED_DIM        = 768
OCR_THRESHOLD    = 200   # chars — below this, trigger OCR

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/root/landtek/ingest.log", mode="a"),
    ],
)
log = logging.getLogger("landtek")

# ── helpers ───────────────────────────────────────────────────────────────────

def load_folders() -> dict:
    return json.loads(FOLDERS_JSON.read_text())


def build_drive_service():
    scopes = ["https://www.googleapis.com/auth/drive"]
    if GOOGLE_IMPERSONATE_USER:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDS, scopes=scopes,
            subject=GOOGLE_IMPERSONATE_USER,
        )
    else:
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_CREDS, scopes=scopes,
        )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def download_drive_inbox(service, local_inbox: Path) -> list[dict]:
    """Download files from Drive inbox/staging to local_inbox. Returns list of {path, drive_id, parent_id}."""
    local_inbox.mkdir(parents=True, exist_ok=True)
    folders = load_folders()
    staging_id = folders.get("inbox_staging", "142QmpKv2DvWjJ46nhOq_C8HhN6xD4Zjy")

    results = service.files().list(
        q=f"'{staging_id}' in parents and mimeType='application/pdf' and trashed=false",
        fields="files(id,name,size)",
        pageSize=50,
    ).execute()

    downloaded = []
    for f in results.get("files", []):
        local_path = local_inbox / f["name"]
        if local_path.exists():
            log.info(f"  Already local: {f['name']} — skipping download")
            downloaded.append({"path": local_path, "drive_id": f["id"], "parent_id": staging_id})
            continue
        log.info(f"  Downloading {f['name']} ({int(f.get('size', 0))//1024} KB) …")
        request = service.files().get_media(fileId=f["id"])
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        local_path.write_bytes(buf.getvalue())
        downloaded.append({"path": local_path, "drive_id": f["id"], "parent_id": staging_id})
    return downloaded


def extract_text_pymupdf(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text.strip()


def ocr_with_document_ai(pdf_path: Path) -> str:
    """Google Document AI OCR. Requires DOCAI_PROJECT, DOCAI_LOCATION, DOCAI_PROCESSOR env vars."""
    if not all([DOCAI_PROJECT, DOCAI_PROCESSOR_ID]):
        log.warning("  Document AI not configured — skipping OCR, using empty text")
        return ""
    try:
        from google.cloud import documentai
        client = documentai.DocumentProcessorServiceClient()
        name = client.processor_path(DOCAI_PROJECT, DOCAI_LOCATION, DOCAI_PROCESSOR_ID)
        raw = pdf_path.read_bytes()
        doc_input = documentai.RawDocument(content=raw, mime_type="application/pdf")
        request = documentai.ProcessRequest(name=name, raw_document=doc_input)
        result = client.process_document(request=request)
        return result.document.text.strip()
    except Exception as e:
        log.error(f"  Document AI error: {e}")
        return ""


def classify_with_gpt4o(filename: str, text: str) -> dict:
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"""You are a legal document classifier for a Philippine property management and litigation firm.

Analyze the following document and return a JSON object with these fields:
- case_file: one of ["Paracale-001", "MWK-001", "unknown"]
  * Paracale-001 = Allan Inocalla mining/land case in Paracale, Camarines Norte
  * MWK-001 = Heirs of Mary Worrick Keesey estate, land transfer fraud (Gloria Balane), TCT 4497, Mercedes/Camarines Norte LGU
- classification: one of ["Legal", "Finance", "Evidence", "Conversations", "Projects", "other"]
  * Legal = pleadings, motions, orders, complaints, affidavits, titles, deeds, ARTA filings
  * Finance = tax declarations, ORs, RPT, accounting, payments, DAR/Landbank
  * Evidence = photographs, survey maps, NBI inquiries, sworn statements, transfer docs
  * Conversations = correspondence letters, emails, meeting notes, DILG comms
  * Projects = project plans, road donation docs, barangay matters, non-case admin
- date: best-guess date as "YYYY-MM-DD" or "YYYY-MM" or "YYYY" or null
- parties: list of named individuals and offices mentioned (max 10)
- reference_numbers: list of TCT/OCT numbers, case numbers, ARTA refs, OR numbers found
- summary: 2-3 sentence summary of what this document is and why it matters
- smart_filename: a clean filename slug (no extension) e.g. "2025-11-24_balane-complaint-affidavit"
- strategic_relevance: one sentence on why this is strategically important (or "routine")

Filename: {filename}
Text (first 3000 chars):
{text[:3000]}

Return ONLY valid JSON. No markdown, no commentary."""

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return json.loads(raw)
        except Exception as e:
            log.warning(f"  GPT-4o attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)
    log.error("  GPT-4o classification failed after 3 attempts")
    return {
        "case_file": "unknown",
        "classification": "other",
        "date": None,
        "parties": [],
        "reference_numbers": [],
        "summary": filename,
        "smart_filename": Path(filename).stem,
        "strategic_relevance": "unclassified",
    }


def move_drive_file(service, file_id: str, new_parent_id: str, old_parent_id: str):
    try:
        service.files().update(
            fileId=file_id,
            addParents=new_parent_id,
            removeParents=old_parent_id,
            fields="id,parents",
        ).execute()
        log.info(f"  Moved {file_id} → folder {new_parent_id}")
    except Exception as e:
        log.error(f"  Drive move failed for {file_id}: {e}")


def chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap_words: int = OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks = []
    step = chunk_words - overlap_words
    for i in range(0, len(words), step):
        chunk = words[i: i + chunk_words]
        chunks.append(" ".join(chunk))
        if i + chunk_words >= len(words):
            break
    return [c for c in chunks if c.strip()]


def embed_text(text: str) -> list[float]:
    genai.configure(api_key=GEMINI_API_KEY)
    for attempt in range(3):
        try:
            result = genai.embed_content(
                model="models/gemini-embedding-001",
                content=text,
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=EMBED_DIM,
            )
            return result["embedding"]
        except Exception as e:
            log.warning(f"  Gemini embed attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("Gemini embedding failed after 3 attempts")


def ensure_qdrant_collection(qc: QdrantClient):
    cols = [c.name for c in qc.get_collections().collections]
    if COLLECTION_NAME not in cols:
        qc.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        log.info(f"Created Qdrant collection: {COLLECTION_NAME}")


def upsert_to_qdrant(qc: QdrantClient, chunks: list[str], metadata: dict, drive_file_id: str, doc_db_id: int):
    points = []
    for i, chunk in enumerate(chunks):
        vec = embed_text(chunk)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{drive_file_id}::{i}"))
        payload = {
            **metadata,
            "text": chunk,
            "chunk_index": i,
            "chunk_text": chunk[:1000],   # store first 1000 chars for retrieval
            "drive_file_id": drive_file_id,
            "doc_db_id": doc_db_id,
        }
        points.append(PointStruct(id=point_id, vector=vec, payload=payload))
        log.info(f"  Embedded chunk {i+1}/{len(chunks)}")

    qc.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)


def ensure_postgres_schema(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id               SERIAL PRIMARY KEY,
                filename         TEXT NOT NULL,
                smart_filename   TEXT,
                case_file        TEXT,
                classification    TEXT,
                doc_date         TEXT,
                parties          JSONB,
                reference_numbers JSONB,
                summary          TEXT,
                strategic_relevance TEXT,
                drive_file_id    TEXT UNIQUE,
                drive_folder_id  TEXT,
                text_length      INTEGER,
                chunk_count      INTEGER,
                ocr_used         BOOLEAN DEFAULT FALSE,
                processed_at     TIMESTAMPTZ DEFAULT NOW(),
                error            TEXT
            );
        """)
        conn.commit()


def log_to_postgres(conn, rec: dict) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents
                (original_filename, smart_filename, case_file, classification, doc_date,
                 parties, reference_numbers, summary, strategic_relevance,
                 drive_file_id, drive_folder_id, text_length, chunk_count,
                 ocr_used, processed_at, error)
            VALUES
                (%(filename)s, %(smart_filename)s, %(case_file)s, %(classification)s, %(doc_date)s,
                 %(parties)s, %(reference_numbers)s, %(summary)s, %(strategic_relevance)s,
                 %(drive_file_id)s, %(drive_folder_id)s, %(text_length)s, %(chunk_count)s,
                 %(ocr_used)s, NOW(), %(error)s)
            ON CONFLICT (drive_file_id) DO UPDATE SET
                processed_at = NOW(),
                chunk_count  = EXCLUDED.chunk_count,
                error        = EXCLUDED.error
            RETURNING id;
        """, {
            **rec,
            "parties": PgJson(rec.get("parties", [])),
            "reference_numbers": PgJson(rec.get("reference_numbers", [])),
        })
        row = cur.fetchone()
        conn.commit()
        return row[0]


# ── backtest ──────────────────────────────────────────────────────────────────

def run_backtests(qc: QdrantClient):
    queries = [
        {"label": "MWK-001: ARTA referral DILG estate obstruction Balane",
         "q": "ARTA referral DILG estate administration obstruction Balane",
         "filter_case": "MWK-001"},
        {"label": "MWK-001: accion reinvindicatoria Balane pretrial May 13",
         "q": "accion reinvindicatoria Gloria Balane pretrial May 13",
         "filter_case": "MWK-001"},
        {"label": "Paracale-001: ARTA mining concession Inocalla",
         "q": "ARTA filing mining concession submission Allan Inocalla",
         "filter_case": "Paracale-001"},
    ]

    genai.configure(api_key=GEMINI_API_KEY)
    print("\n" + "="*70)
    print("BACKTEST RESULTS")
    print("="*70)

    for q in queries:
        print(f"\n── {q['label']}")
        try:
            vec = embed_text(q["q"])
            results = qc.search(
                collection_name=COLLECTION_NAME,
                query_vector=vec,
                limit=3,
                query_filter=Filter(
                    must=[FieldCondition(key="case_file", match=MatchValue(value=q["filter_case"]))]
                ) if q.get("filter_case") else None,
                with_payload=True,
            )
            if not results:
                print("  (no results)")
                continue
            for i, r in enumerate(results, 1):
                snippet = r.payload.get("chunk_text", "")[:200].replace("\n", " ")
                print(f"  #{i}  score={r.score:.4f}")
                print(f"       file={r.payload.get('filename','?')} | type={r.payload.get('classification','?')}")
                print(f"       snippet: {snippet}…")
        except Exception as e:
            print(f"  ERROR: {e}")
    print("="*70 + "\n")


# ── main pipeline ─────────────────────────────────────────────────────────────

def process_pdf(
    pdf_path: Path,
    drive_info: Optional[dict],   # {drive_id, parent_id} or None
    drive_service,
    qc: QdrantClient,
    pg_conn,
    folders: dict,
) -> dict:
    """Process a single PDF. Returns result summary dict."""
    filename = pdf_path.name
    log.info(f"\n{'─'*60}\nProcessing: {filename}")
    result = {"filename": filename, "status": "ok", "chunks": 0, "ocr": False}

    # 1. Extract text
    text = extract_text_pymupdf(pdf_path)
    log.info(f"  PyMuPDF extracted {len(text)} chars")
    ocr_used = False
    if len(text) < OCR_THRESHOLD:
        log.info(f"  < {OCR_THRESHOLD} chars — triggering Document AI OCR")
        text = ocr_with_document_ai(pdf_path)
        ocr_used = True
        log.info(f"  OCR returned {len(text)} chars")

    # 2. Classify
    classification = classify_with_gpt4o(filename, text)
    case_file     = classification.get("case_file", "unknown")
    doc_type      = classification.get("classification", "other")
    log.info(f"  Classified: case={case_file}, type={doc_type}")

    # 3. Determine target Drive folder
    target_folder_id = None
    if drive_info and case_file in folders:
        case_folders = folders[case_file]
        target_folder_id = case_folders.get(doc_type) or case_folders.get("default")
        if target_folder_id and target_folder_id != drive_info.get("parent_id"):
            move_drive_file(drive_service, drive_info["drive_id"], target_folder_id, drive_info["parent_id"])

    # 4. Postgres log
    pg_rec = {
        "filename":            filename,
        "smart_filename":      classification.get("smart_filename"),
        "case_file":           case_file,
        "classification":       doc_type,
        "doc_date":            classification.get("date"),
        "parties":             classification.get("parties", []),
        "reference_numbers":   classification.get("reference_numbers", []),
        "summary":             classification.get("summary"),
        "strategic_relevance": classification.get("strategic_relevance"),
        "drive_file_id":       drive_info["drive_id"] if drive_info else hashlib.md5(str(pdf_path).encode()).hexdigest(),
        "drive_folder_id":     target_folder_id,
        "text_length":         len(text),
        "chunk_count":         0,
        "ocr_used":            ocr_used,
        "error":               None,
    }
    doc_db_id = log_to_postgres(pg_conn, pg_rec)

    # 5. Chunk → embed → upsert
    chunks = chunk_text(text)
    log.info(f"  {len(chunks)} chunks to embed")

    if chunks:
        meta = {
            "filename":            filename,
            "smart_filename":      classification.get("smart_filename"),
            "case_file":           case_file,
            "classification":       doc_type,
            "doc_date":            classification.get("date"),
            "parties":             classification.get("parties", []),
            "reference_numbers":   classification.get("reference_numbers", []),
            "summary":             classification.get("summary"),
            "strategic_relevance": classification.get("strategic_relevance"),
            "ocr_used":            ocr_used,
        }
        n_upserted = upsert_to_qdrant(qc, chunks, meta, pg_rec["drive_file_id"], doc_db_id)
        result["chunks"] = n_upserted

        # update chunk_count in postgres
        with pg_conn.cursor() as cur:
            cur.execute("UPDATE documents SET chunk_count=%s WHERE id=%s", (n_upserted, doc_db_id))
        pg_conn.commit()

    result["case_file"] = case_file
    result["doc_type"]  = doc_type
    result["ocr"]       = ocr_used
    log.info(f"  ✓ Done: {n_upserted if chunks else 0} points upserted")
    return result


def main():
    parser = argparse.ArgumentParser(description="LANDTEK Ingestion Pipeline")
    parser.add_argument("--no-download", action="store_true", help="Skip Drive download, process local inbox only")
    parser.add_argument("--backtest",    action="store_true", help="Run semantic search backtests only")
    args = parser.parse_args()

    # ── init clients ──────────────────────────────────────────────────────────
    log.info("Initialising clients …")
    drive_service = build_drive_service()
    qc = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, api_key=QDRANT_API_KEY, https=True)
    ensure_qdrant_collection(qc)
    pg_conn = psycopg2.connect(DATABASE_URL)
    ensure_postgres_schema(pg_conn)
    folders = load_folders()

    if args.backtest:
        run_backtests(qc)
        return

    # ── download from Drive inbox ──────────────────────────────────────────────
    drive_map: dict[str, dict] = {}   # filename → {drive_id, parent_id}
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    if not args.no_download:
        log.info("Downloading from Drive inbox …")
        downloaded = download_drive_inbox(drive_service, INBOX_DIR)
        for item in downloaded:
            drive_map[item["path"].name] = {"drive_id": item["drive_id"], "parent_id": item["parent_id"]}
        log.info(f"  {len(downloaded)} file(s) ready in {INBOX_DIR}")

    # ── process local inbox ───────────────────────────────────────────────────
    pdfs = sorted(INBOX_DIR.glob("*.pdf"))
    if not pdfs:
        log.info(f"No PDFs found in {INBOX_DIR}")
        return

    log.info(f"Processing {len(pdfs)} PDF(s) …")
    summary_rows = []
    failed = []

    for pdf_path in pdfs:
        drive_info = drive_map.get(pdf_path.name)
        try:
            res = process_pdf(pdf_path, drive_info, drive_service, qc, pg_conn, folders)
            summary_rows.append(res)
        except Exception as e:
            log.error(f"FAILED {pdf_path.name}: {e}", exc_info=True)
            failed.append({"filename": pdf_path.name, "error": str(e)})

    # ── final report ──────────────────────────────────────────────────────────
    total_points = qc.get_collection(COLLECTION_NAME).points_count
    print("\n" + "="*70)
    print("INGESTION COMPLETE")
    print("="*70)
    print(f"  PDFs processed : {len(summary_rows)}")
    print(f"  Failed         : {len(failed)}")
    print(f"  Qdrant points  : {total_points}")
    print()
    for r in summary_rows:
        ocr_tag = "[OCR]" if r.get("ocr") else ""
        print(f"  ✓ {r['filename']:<40} {r.get('case_file','?'):<15} {r.get('doc_type','?'):<15} {r.get('chunks',0)} chunks {ocr_tag}")
    for f in failed:
        print(f"  ✗ {f['filename']:<40} ERROR: {f['error']}")

    # run backtests automatically after ingestion
    if summary_rows:
        run_backtests(qc)

    pg_conn.close()


if __name__ == "__main__":
    main()
