#!/usr/bin/env python3
"""process_case_attachments.py — extract + classify the 55 Civil Case 26-360
attachment PDFs that were marked status='not_applicable' in heightened_ocr_queue.

These are court filings (Reply, Motion, Affidavit, Complaint exhibits, Pretrial
Notice) — NOT TCTs — so the heightened tct_v3_canonical contract is wrong for
them. This script uses the general pipeline:

  1. PyMuPDF text extraction
  2. Document AI OCR fallback (if PyMuPDF yields <200 chars — scanned doc)
  3. case_keywords.determine_case_file() — deterministic pre-classification
  4. GPT-4o for fine-grained metadata (classification, date, parties, summary)
  5. UPDATE documents row with extracted_text, classification, doc_date, etc.

Skips: chunking and Qdrant embedding (Gemini embedding key is cooled — can run
those steps later as a separate pass).
"""

import os, sys, json, time, psycopg2
from pathlib import Path
import fitz  # PyMuPDF
import openai
from psycopg2.extras import Json
from google.oauth2 import service_account

sys.path.insert(0, '/root/landtek/autonomous')
import case_keywords

OPENAI_API_KEY      = os.environ["OPENAI_API_KEY"]
SA_KEY              = '/root/landtek/google-creds.json'
DOCAI_PROJECT       = 'landtek'
DOCAI_LOCATION      = 'us'
DOCAI_PROCESSOR     = '29ccddeea977ef1f'
DB_DSN              = "host=172.18.0.3 dbname=n8n user=n8n password=n8npassword"

oai = openai.OpenAI(api_key=OPENAI_API_KEY)

# Document AI client (lazy-init)
_docai_client = None
def docai():
    global _docai_client
    if _docai_client is None:
        from google.cloud import documentai_v1 as documentai
        creds = service_account.Credentials.from_service_account_file(
            SA_KEY, scopes=['https://www.googleapis.com/auth/cloud-platform'])
        _docai_client = documentai.DocumentProcessorServiceClient(credentials=creds)
    return _docai_client


def extract_text(pdf_path: Path) -> tuple[str, str]:
    """Return (text, method)."""
    try:
        doc = fitz.open(pdf_path)
        txt = "".join(p.get_text() for p in doc)
        if len(txt.strip()) >= 200:
            return txt, "pymupdf"
    except Exception as e:
        print(f"   pymupdf error: {e}", file=sys.stderr)

    # Fallback to Document AI
    try:
        from google.cloud import documentai_v1 as documentai
        client = docai()
        name = client.processor_path(DOCAI_PROJECT, DOCAI_LOCATION, DOCAI_PROCESSOR)
        raw = pdf_path.read_bytes()
        # Document AI sync API caps at ~20MB / 15 pages. Big PDFs need batch — skip if huge
        if len(raw) > 20 * 1024 * 1024:
            return "", "skipped_oversize"
        doc_input = documentai.RawDocument(content=raw, mime_type="application/pdf")
        req = documentai.ProcessRequest(name=name, raw_document=doc_input)
        result = client.process_document(request=req)
        return result.document.text.strip(), "documentai"
    except Exception as e:
        print(f"   docai error: {e}", file=sys.stderr)
        return "", "failed"


CLASSIFY_PROMPT = """You are a legal document classifier for a Philippine property litigation firm.

Return STRICTLY valid JSON with these fields:
  case_file: "MWK-001" | "Paracale-001" | "Owner" | "Unknown"
  classification: one of "Court Filing", "Affidavit", "Motion", "Complaint",
    "Notice", "Order", "Demand Letter", "Correspondence", "Title", "Tax Document",
    "Power of Attorney", "Special Power of Attorney", "Deed", "Memorandum",
    "Receipt", "Email", "Government Submission", "Other"
  year: "YYYY" (4-digit) or ""
  primary_party: shortest accurate name of the principal party (e.g. "Patricia Keesee Zschoche")
  secondary_party: opposing party or other named (e.g. "Gloria Balane et al.")
  reference_no: case-number / pleading-number if any (e.g. "Civil Case No. 26-360")
  summary_one_line: 1-sentence description of what this document is
  parties_named: array of distinct named persons (max 10)
  strategic_relevance: 1-sentence on why this matters for Civil Case 26-360

Filename: {filename}
Text (first 4000 chars):
{text}
"""


def classify(filename: str, text: str, deterministic_hint: dict | None = None) -> dict:
    snippet = text[:4000] if text else ""
    prompt = CLASSIFY_PROMPT.format(filename=filename, text=snippet)
    try:
        resp = oai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"   classify error: {e}", file=sys.stderr)
        return {"case_file": "Unknown", "classification": "Other",
                "year": "", "primary_party": "", "secondary_party": "",
                "reference_no": "", "summary_one_line": "",
                "parties_named": [], "strategic_relevance": ""}


def main():
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()
    cur.execute("""
      SELECT d.id, d.original_filename, d.analyst_memo->>'local_path' AS local_path,
             COALESCE(length(d.extracted_text),0) AS existing_text_len
        FROM documents d
        JOIN heightened_ocr_queue q ON q.doc_id=d.id
       WHERE q.status='not_applicable'
         AND q.case_file='MWK-001'
         AND d.analyst_memo->>'source'='gmail_attachment'
         AND d.mime_type='application/pdf'
       ORDER BY d.id
    """)
    docs = cur.fetchall()
    print(f"Processing {len(docs)} case-attachment PDFs")

    done, skip_have_text, failed = 0, 0, 0
    for doc_id, fname, local_path, existing_len in docs:
        if existing_len >= 200:
            skip_have_text += 1
            continue
        if not local_path or not Path(local_path).exists():
            print(f"  doc {doc_id}: missing local_path={local_path}", file=sys.stderr)
            failed += 1
            continue

        t0 = time.time()
        print(f"\n[doc {doc_id}] {fname[:70]}")
        text, method = extract_text(Path(local_path))
        print(f"  text: {len(text)} chars via {method}")
        if not text or len(text) < 50:
            failed += 1
            cur.execute("UPDATE documents SET error=%s WHERE id=%s",
                        (f"text extraction failed via {method}", doc_id))
            conn.commit()
            continue

        # Deterministic case_file via case_keywords (saves an LLM round-trip
        # when we're confident)
        hint = case_keywords.determine_case_file(text=text, filename=fname)
        cls = classify(fname, text)

        # If case_keywords is highly confident AND GPT-4o disagrees, log it
        if hint["case_file"] != "unknown" and hint["confidence"] >= 0.5:
            if cls.get("case_file") != hint["case_file"]:
                print(f"  override case_file: kw={hint['case_file']!r} (conf {hint['confidence']}) "
                      f"vs gpt={cls.get('case_file')!r}")
                cls["case_file"] = hint["case_file"]

        # Persist
        cur.execute("""
            UPDATE documents SET
              extracted_text       = %s,
              text_length          = %s,
              ocr_used             = %s,
              case_file            = %s,
              classification       = %s,
              classification_json  = %s,
              year                 = %s,
              status               = 'classified',
              updated_at           = NOW()
            WHERE id=%s
        """, (
            text,
            len(text),
            (method == "documentai"),
            cls.get("case_file") or "Unknown",
            cls.get("classification") or "Other",
            Json({**cls, "_classifier_hint": hint, "_extract_method": method}),
            cls.get("year") or None,
            doc_id
        ))
        conn.commit()
        done += 1
        elapsed = time.time() - t0
        print(f"  -> {cls.get('case_file')} / {cls.get('classification')} "
              f"  {len(text)} chars, {elapsed:.1f}s")
        time.sleep(0.3)  # polite throttle to OpenAI

    print(f"\nDONE: extracted={done}  skipped_have_text={skip_have_text}  failed={failed}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
