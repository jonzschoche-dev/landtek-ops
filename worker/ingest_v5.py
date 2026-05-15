"""Phase 3 — disciplined ingestion pipeline.

Pipeline per PDF:
  1. SHA-256 the file bytes -> dedupe via documents.content_hash
  2. PyMuPDF extract -> Document AI OCR fallback
  3. GPT-4o classify (case_file + confidence + reasoning + entities + smart_filename)
  4. CONFIDENCE GATE: < 0.75 OR case mismatch -> file goes to Unclassified, NOT a client folder
  5. Internal consistency check: case_file must be supported by entity match
  6. Document-type -> subfolder via explicit rules (Legal/Finance/Evidence/Conversations/Projects)
  7. Filename collision detection (size match = skip, different = append _v2/_v3)
  8. Smart filename format enforcement (YYYY-MM-DD_name.pdf)
  9. Pre-flight verification of target folder writability
 10. Drive upload + audit_log entry
 11. Chunk + gemini-embedding-001 (768) -> Qdrant landtek_documents
 12. Postgres documents row + content_hash dedup

NO file is moved into a client case folder unless ALL gates pass. Misfiled docs
are worse than unfiled ones; everything ambiguous goes to Unclassified.
"""
from __future__ import annotations
import os, sys, json, time, re, hashlib, base64, argparse
from datetime import datetime
from pathlib import Path
from collections import Counter
import requests
import fitz

DRY_RUN = False  # set in main() from --dry-run flag

sys.path.insert(0, str(Path(__file__).parent))
from config import (
    OPENAI_API_KEY, GEMINI_API_KEY, GOOGLE_CREDS, DOCAI_URL,
    QDRANT_URL, QDRANT_KEY,
    PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD,
)

FOLDERS_FILE = Path("/root/landtek/folders.json")
INBOX_DIR = Path("/root/landtek/inbox")
QDRANT_COLL = "landtek_documents"
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

CONFIDENCE_THRESHOLD = 0.75

# --- Document type -> subfolder rules (explicit, no ambiguity) ---
SUBFOLDER_RULES = [
    ("Legal", {"court filing", "complaint", "motion", "demand letter", "demand", "deed",
               "title", "tct", "oct", "contract", "lease", "permit", "mpsa",
               "license", "notice", "subpoena", "government submission",
               "regulatory", "legal", "filing"}),
    ("Finance", {"receipt", "invoice", "tax", "payment", "bank statement",
                 "financial statement", "billing", "finance"}),
    ("Evidence", {"evidence", "exhibit", "photo", "screenshot", "transcript", "recording"}),
    ("Conversations", {"email", "letter", "memo", "correspondence", "communication"}),
    ("Projects", {"plan", "draft", "schedule", "roadmap", "working draft", "project"}),
]

# Case-specific entity hints for the consistency check
CASE_ENTITY_HINTS = {
    "Paracale-001": {"inocalla", "allan", "paracale", "pgc", "paracale gold",
                     "mpsa", "denr", "mining", "mineral"},
    "MWK-001": {"keesey", "worrick", "mary worrick", "patricia keesey", "mercedes",
                "pajarillo", "arta", "cart", "balane", "zschoche", "anti red tape",
                "civil service", "csc", "estate", "heirs"},
}


def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}", flush=True)


# ---------- folders + targeting -----------------------------------------------
def load_folders():
    return json.loads(FOLDERS_FILE.read_text())


def determine_subfolder(document_type: str) -> str:
    dt = (document_type or "").lower()
    for sub, keywords in SUBFOLDER_RULES:
        if any(k in dt for k in keywords):
            return sub
    return "default"


def target_folder_id(folders, case_file: str, document_type: str):
    case_map = folders.get(case_file)
    if not case_map:
        return None, "case_not_in_folders_json"
    sub = determine_subfolder(document_type)
    fid = case_map.get(sub) or case_map.get("default") or case_map.get("root")
    return fid, sub


# ---------- google auth -------------------------------------------------------
def get_drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def get_docai_token():
    from google.oauth2 import service_account
    import google.auth.transport.requests as gtr
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(gtr.Request())
    return creds.token


# ---------- text extraction ---------------------------------------------------
def extract_pymupdf(pdf_path):
    doc = fitz.open(str(pdf_path))
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def is_readable(text):
    if len(text) < 200: return False
    alpha = sum(1 for c in text if c.isalpha())
    return alpha / max(len(text), 1) >= 0.4


def extract_docai(pdf_path):
    log("  Document AI OCR...")
    with open(pdf_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    token = get_docai_token()
    r = requests.post(DOCAI_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"rawDocument": {"content": content, "mimeType": "application/pdf"}},
        timeout=300)
    r.raise_for_status()
    return r.json().get("document", {}).get("text", "")


def extract_text(pdf_path):
    text = extract_pymupdf(pdf_path)
    log(f"  PyMuPDF: {len(text)} chars")
    if not is_readable(text):
        text = extract_docai(pdf_path)
        log(f"  DocAI: {len(text)} chars")
    return text


# ---------- classification (GPT-4o) -------------------------------------------
def classify_with_gpt4o(text, filename, known_cases):
    cases_str = " | ".join(known_cases + ["Unknown"])
    prompt = f"""Analyze this Philippine legal/property document for the LandTek case management system.

Active case_files: {cases_str}

Filename: {filename}
Document text (first 6000 chars):
{text[:6000]}

Return STRICT JSON only:
{{
  "case_file": "<one of: {cases_str}>",
  "case_file_confidence": 0.0-1.0,
  "case_file_reasoning": "1 sentence on the cues that drove the choice (cite parties/refs/locations)",
  "document_type": "Legal | Court Filing | Contract | Government Submission | Permit | Demand Letter | Complaint | Title | Deed | Notice | Finance | Receipt | Invoice | Tax | Evidence | Email | Correspondence | Letter | Memo | Project | Other",
  "document_date": "YYYY-MM-DD or null",
  "parties": ["all people and entities mentioned"],
  "reference_numbers": ["all case numbers, CTNs, MPSA numbers, TCT/OCT numbers"],
  "summary": "2-3 sentence factual summary",
  "smart_filename": "YYYY-MM-DD_descriptive_name.pdf",
  "strategic_relevance": "1-2 sentences on why this matters to the case"
}}

Case backgrounds:
- Paracale-001 = Allan Inocalla, gold mining in Paracale Camarines Norte (MPSA, DENR/MGB, possibly PGC, mining)
- MWK-001 = Heirs of Mary Worrick Keesey estate, Mercedes Camarines Norte (Patricia Keesey Zschoche as attorney-in-fact, ARTA filings, CART proceedings, Mayor Pajarillo, Atty. Balane, possibly DILG/CSC/civil service)

Confidence guidance:
- 0.9+: parties or case-specific references explicitly tie to one case
- 0.6-0.9: probable but not conclusive
- <0.6: insufficient cues — return "Unknown"
"""
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
        json={"model": "gpt-4o", "max_tokens": 1500,
              "messages": [{"role": "user", "content": prompt}],
              "response_format": {"type": "json_object"}},
        timeout=120)
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])


# ---------- consistency + filename rules --------------------------------------
def consistency_check(case_file, parties, reference_numbers, text_excerpt) -> bool:
    """case_file must be supported by at least one entity matching the case hints."""
    hints = CASE_ENTITY_HINTS.get(case_file, set())
    if not hints:
        return True
    haystack = " ".join(parties or [] + reference_numbers or []).lower()
    haystack += " " + (text_excerpt or "")[:3000].lower()
    return any(h in haystack for h in hints)


_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_[\w\-\.]+\.pdf$", re.IGNORECASE)


def enforce_filename(smart_name: str, doc_date: str | None, summary: str | None,
                     fallback_filename: str) -> str:
    if smart_name and _FILENAME_RE.match(smart_name):
        return smart_name
    # Build a clean fallback
    date_part = (doc_date or datetime.now().strftime("%Y-%m-%d"))[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_part):
        date_part = datetime.now().strftime("%Y-%m-%d")
    desc_src = (summary or fallback_filename or "doc").strip()
    desc = re.sub(r"[^\w\-]+", "_", desc_src)[:60].strip("_") or "doc"
    return f"{date_part}_{desc}.pdf"


# ---------- drive ops ---------------------------------------------------------
def folder_writable(service, folder_id) -> bool:
    """Check that we can stat the folder and have write permission."""
    try:
        meta = service.files().get(
            fileId=folder_id,
            fields="id, name, capabilities(canAddChildren)",
            supportsAllDrives=True,
        ).execute()
        return bool(meta.get("capabilities", {}).get("canAddChildren"))
    except Exception:
        return False


def find_existing_in_folder(service, folder_id, name):
    safe_name = name.replace("'", "\\'")
    resp = service.files().list(
        q=f"'{folder_id}' in parents and name='{safe_name}' and trashed=false",
        fields="files(id,name,size,md5Checksum)",
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    return resp.get("files", [])


def upload_with_collision(service, local_path, folder_id, target_name):
    from googleapiclient.http import MediaFileUpload
    local_size = local_path.stat().st_size

    existing = find_existing_in_folder(service, folder_id, target_name)
    for e in existing:
        if int(e.get("size", 0) or 0) == local_size:
            return {"ok": True, "skipped_already_exists": True,
                    "id": e["id"], "name": e["name"]}
    # Append _v2/_v3 if name taken with different size
    final_name = target_name
    if existing:
        stem, dot, ext = target_name.rpartition(".")
        i = 2
        while True:
            candidate = f"{stem}_v{i}.{ext}" if dot else f"{target_name}_v{i}"
            if not find_existing_in_folder(service, folder_id, candidate):
                final_name = candidate; break
            i += 1
    media = MediaFileUpload(str(local_path), mimetype="application/pdf", resumable=False)
    f = service.files().create(
        body={"name": final_name, "parents": [folder_id]},
        media_body=media, fields="id, name, parents, webViewLink",
        supportsAllDrives=True,
    ).execute()
    return {"ok": True, "id": f["id"], "name": f["name"],
            "webViewLink": f.get("webViewLink"), "renamed": final_name != target_name}


# ---------- embeddings + qdrant ----------------------------------------------
def embed_text(text):
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}",
        json={"model": f"models/{EMBED_MODEL}",
              "content": {"parts": [{"text": text[:8000]}]},
              "outputDimensionality": EMBED_DIM},
        timeout=30)
    r.raise_for_status()
    return r.json()["embedding"]["values"]


def ensure_qdrant_collection():
    h = {"api-key": QDRANT_KEY, "Content-Type": "application/json"}
    r = requests.get(f"{QDRANT_URL}/collections/{QDRANT_COLL}", headers=h)
    if r.status_code == 404:
        requests.put(f"{QDRANT_URL}/collections/{QDRANT_COLL}", headers=h,
            json={"vectors": {"size": EMBED_DIM, "distance": "Cosine"},
                  "on_disk_payload": True}).raise_for_status()
        log(f"  Created Qdrant collection {QDRANT_COLL}")


def qdrant_upsert(point_id, vector, payload):
    requests.put(f"{QDRANT_URL}/collections/{QDRANT_COLL}/points",
        headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
        json={"points": [{"id": point_id, "vector": vector, "payload": payload}]},
        timeout=30).raise_for_status()


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + size]))
        i += size - overlap
    return [c for c in out if len(c.strip()) > 50]


# ---------- postgres ----------------------------------------------------------
def pg_conn():
    import psycopg2
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DATABASE,
                            user=PG_USER, password=PG_PASSWORD)


def existing_doc_by_hash(content_hash):
    conn = pg_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, case_file, smart_filename FROM documents WHERE content_hash=%s",
                    (content_hash,))
        return cur.fetchone()
    finally:
        cur.close(); conn.close()


def insert_document(doc, filename, text, content_hash, drive_file_id=None):
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO documents
        (case_file, original_filename, smart_filename, mime_type,
         extracted_text, classification, strategic_relevance,
         document_title, content_hash, confidence, first_seen_at, last_seen_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
        ON CONFLICT (content_hash) DO UPDATE SET
          last_seen_at = NOW(), duplicate_count = documents.duplicate_count + 1
        RETURNING id""",
        (doc.get("case_file", "Unknown"), filename,
         doc.get("smart_filename", filename), "application/pdf",
         text[:50000], doc.get("document_type", "Other"),
         doc.get("strategic_relevance", ""),
         doc.get("smart_filename", filename),
         content_hash,
         float(doc.get("case_file_confidence", 0.0))))
    doc_id = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return doc_id


def write_audit(actor, action, target_type, target_id, after_state):
    try:
        conn = pg_conn(); cur = conn.cursor()
        cur.execute("""INSERT INTO audit_log
            (actor, actor_type, action, target_type, target_id, after_state)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
            (actor, "worker", action, target_type, str(target_id),
             json.dumps(after_state, default=str)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log(f"  audit_log warning: {e}")


def queue_question(case_file, question, source_doc_id):
    try:
        conn = pg_conn(); cur = conn.cursor()
        cur.execute("""INSERT INTO pending_questions
            (case_file, source_doc_id, question, priority)
            VALUES (%s, %s, %s, %s)""",
            (case_file, source_doc_id, question, "normal"))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log(f"  pending_questions warning: {e}")


# ---------- per-file pipeline -------------------------------------------------
def process_file(pdf_path, drive_service, folders, known_cases, summary):
    filename = pdf_path.name
    log(f"\n{'='*70}\nProcessing: {filename}")
    summary["attempted"] += 1

    # Step 1: hash + dedup (skip dedup check in dry-run)
    file_bytes = pdf_path.read_bytes()
    content_hash = hashlib.sha256(file_bytes).hexdigest()
    if not DRY_RUN:
        existing = existing_doc_by_hash(content_hash)
        if existing:
            eid, ecase, ename = existing
            log(f"  DUPLICATE: hash already in documents (id={eid}, case={ecase}, {ename})")
            summary["duplicates"].append((filename, eid)); return

    # Step 2: extract text
    try:
        text = extract_text(pdf_path)
    except Exception as e:
        log(f"  EXTRACT FAILED: {e}")
        summary["failed_extract"].append((filename, str(e))); return
    if not text or len(text) < 50:
        log("  No usable text — skipping"); summary["failed_extract"].append((filename, "no_text"))
        return

    # Step 3: classify
    try:
        cls = classify_with_gpt4o(text, filename, known_cases)
    except Exception as e:
        log(f"  CLASSIFY FAILED: {e}")
        summary["failed_classify"].append((filename, str(e))); return

    case_file = cls.get("case_file", "Unknown")
    conf = float(cls.get("case_file_confidence", 0.0))
    doc_type = cls.get("document_type", "Other")
    log(f"  Classifier said: case={case_file} conf={conf:.2f} type={doc_type}")
    log(f"  Reasoning: {(cls.get('case_file_reasoning') or '')[:200]}")

    # Step 4: confidence + consistency gates
    quarantine_reason = None
    if case_file == "Unknown" or case_file not in known_cases:
        quarantine_reason = f"case_file_not_known:{case_file}"
    elif conf < CONFIDENCE_THRESHOLD:
        quarantine_reason = f"confidence_below_threshold:{conf:.2f}"
    elif not consistency_check(case_file, cls.get("parties", []),
                               cls.get("reference_numbers", []), text):
        quarantine_reason = f"entity_consistency_check_failed_for_{case_file}"

    if quarantine_reason:
        log(f"  ⚠ QUARANTINE → Unclassified ({quarantine_reason})")
        cls["case_file"] = "Unclassified"
        target_id = folders.get("unclassified")
        target_sub = "Unclassified"
    else:
        target_id, target_sub = target_folder_id(folders, case_file, doc_type)

    # Step 5: enforce filename format
    smart_name = enforce_filename(cls.get("smart_filename"), cls.get("document_date"),
                                  cls.get("summary"), filename)
    cls["smart_filename"] = smart_name
    log(f"  Target: {case_file} / {target_sub} ({target_id})")
    log(f"  Filename: {smart_name}")

    # DRY-RUN: stop here, just print the classification + would-be target
    if DRY_RUN:
        log(f"  [DRY-RUN] would file to folder {target_id} ({target_sub})")
        log(f"  [DRY-RUN] classifier raw: case={case_file} type={doc_type} conf={conf:.2f}")
        log(f"  [DRY-RUN] entities: parties={cls.get('parties',[])[:5]} refs={cls.get('reference_numbers',[])[:5]}")
        log(f"  [DRY-RUN] summary: {(cls.get('summary') or '')[:300]}")
        log(f"  [DRY-RUN] No Postgres / Qdrant / Drive writes performed.")
        summary["completed"].append(filename)
        return

    # Step 6: pre-flight folder writability
    drive_result = None
    if not drive_service:
        log("  ✗ No Drive service — skipping upload"); summary["drive_failed"].append((filename, "no_drive_service"))
    elif not target_id:
        log("  ✗ No target folder ID resolved — skipping upload")
        summary["drive_failed"].append((filename, "no_target_folder_id"))
    elif not folder_writable(drive_service, target_id):
        log(f"  ✗ Target folder NOT writable by SA — skipping upload (verify Editor share)")
        summary["drive_failed"].append((filename, "target_folder_not_writable"))
    else:
        try:
            drive_result = upload_with_collision(drive_service, pdf_path, target_id, smart_name)
            if drive_result.get("skipped_already_exists"):
                log(f"  ✓ Drive: identical file already in folder (id={drive_result['id']}); no upload")
                summary["drive_already_present"] += 1
            else:
                renamed = " (renamed for collision)" if drive_result.get("renamed") else ""
                log(f"  ✓ Drive uploaded: {drive_result['name']}{renamed}")
                log(f"      {drive_result.get('webViewLink')}")
                summary["drive_uploaded"] += 1
        except Exception as e:
            log(f"  ✗ Drive upload error: {type(e).__name__}: {str(e)[:200]}")
            summary["drive_failed"].append((filename, str(e)))

    # Step 7: Postgres insert + audit
    try:
        doc_id = insert_document(cls, filename, text, content_hash,
                                 drive_file_id=drive_result.get("id") if drive_result else None)
        log(f"  ✓ Postgres documents.id = {doc_id}")
    except Exception as e:
        log(f"  ✗ Postgres insert: {e}")
        doc_id = None

    if drive_result and drive_result.get("ok") and not drive_result.get("skipped_already_exists"):
        write_audit("worker", "drive_upload", "drive_file", drive_result.get("id"),
                    {"folder_id": target_id, "subfolder": target_sub,
                     "case_file": cls.get("case_file"), "original_filename": filename,
                     "smart_filename": drive_result.get("name"),
                     "document_type": doc_type, "confidence": conf,
                     "doc_id": doc_id, "quarantine_reason": quarantine_reason})

    if quarantine_reason and doc_id:
        queue_question(case_file if case_file in known_cases else "Unknown",
                       f"Doc {doc_id} ({filename}) was quarantined: {quarantine_reason}. "
                       f"Classifier suggested {case_file} (conf {conf:.2f}). "
                       f"Confirm correct case_file or leave in Unclassified.",
                       doc_id)

    # Step 8: chunk + embed + Qdrant
    chunks = chunk_text(text)
    log(f"  Chunks: {len(chunks)}")
    fhash = hashlib.md5(filename.encode()).hexdigest()[:8]
    for i, ch in enumerate(chunks):
        try:
            v = embed_text(ch)
            pid = int(hashlib.md5(f"{fhash}_{i}".encode()).hexdigest()[:8], 16)
            qdrant_upsert(pid, v, {
                "case_file": cls.get("case_file"),
                "document_type": doc_type,
                "filename": filename, "smart_filename": smart_name,
                "chunk_index": i, "total_chunks": len(chunks),
                "document_date": cls.get("document_date"),
                "parties": cls.get("parties", []),
                "reference_numbers": cls.get("reference_numbers", []),
                "summary": cls.get("summary", ""),
                "strategic_relevance": cls.get("strategic_relevance", ""),
                "text": ch,
                "doc_id_postgres": doc_id,
                "drive_file_id": drive_result.get("id") if drive_result else None,
                "ingested_at": datetime.now().isoformat()
            })
            time.sleep(0.25)
        except Exception as e:
            log(f"  chunk {i+1} failed: {e}")
            summary["failed_chunks"].append((filename, i, str(e)))
    summary["chunks_total"] += len(chunks)
    summary["completed"].append(filename)
    log(f"  COMPLETE: {filename}")


def main():
    global DRY_RUN
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Classify and print, no DB / Drive / Qdrant writes")
    args = parser.parse_args()
    DRY_RUN = args.dry_run

    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY missing"); sys.exit(1)
    if not FOLDERS_FILE.exists():
        print(f"ERROR: {FOLDERS_FILE} missing"); sys.exit(1)

    folders = load_folders()
    known_cases = [k for k in folders.keys() if k not in ("inbox", "unclassified")]
    log(f"Known cases: {known_cases}")
    log(f"Confidence threshold: {CONFIDENCE_THRESHOLD}")
    if DRY_RUN:
        log(">>> DRY-RUN MODE — no writes to Postgres / Qdrant / Drive <<<")
    else:
        ensure_qdrant_collection()

    try:
        drive_service = get_drive_service()
        log("Drive service authed (Editor scope)")
    except Exception as e:
        log(f"Drive auth failed: {e} — uploads will be skipped")
        drive_service = None

    pdfs = sorted(list(INBOX_DIR.glob("*.pdf")) + list(INBOX_DIR.glob("*.PDF")))
    log(f"Found {len(pdfs)} PDF(s) in {INBOX_DIR}")

    summary = {"attempted": 0, "completed": [], "duplicates": [],
               "drive_uploaded": 0, "drive_already_present": 0, "drive_failed": [],
               "failed_extract": [], "failed_classify": [],
               "failed_chunks": [], "chunks_total": 0}

    for pdf in pdfs:
        try:
            process_file(pdf, drive_service, folders, known_cases, summary)
        except Exception as e:
            log(f"FAILED on {pdf.name}: {e}")
            import traceback; traceback.print_exc()

    # Final Qdrant + Postgres counts
    try:
        r = requests.get(f"{QDRANT_URL}/collections/{QDRANT_COLL}",
                         headers={"api-key": QDRANT_KEY})
        pc = r.json().get("result", {}).get("points_count", "?")
    except Exception:
        pc = "?"

    print("\n" + "="*72)
    print("INGESTION SUMMARY")
    print("="*72)
    print(f"Attempted: {summary['attempted']}")
    print(f"Completed: {len(summary['completed'])} → {summary['completed']}")
    print(f"Duplicates skipped: {len(summary['duplicates'])}")
    for f, eid in summary['duplicates']:
        print(f"  - {f} (existing id={eid})")
    print(f"Drive uploaded fresh: {summary['drive_uploaded']}")
    print(f"Drive already present (no-op): {summary['drive_already_present']}")
    print(f"Drive failures: {len(summary['drive_failed'])}")
    for f, err in summary['drive_failed']:
        print(f"  - {f}: {err}")
    print(f"Extract failures: {len(summary['failed_extract'])}")
    for f, err in summary['failed_extract']:
        print(f"  - {f}: {err}")
    print(f"Classify failures: {len(summary['failed_classify'])}")
    for f, err in summary['failed_classify']:
        print(f"  - {f}: {err}")
    print(f"Chunk failures: {len(summary['failed_chunks'])}")
    print(f"Total chunks indexed: {summary['chunks_total']}")
    print(f"Final Qdrant points_count in {QDRANT_COLL}: {pc}")


if __name__ == "__main__":
    main()
