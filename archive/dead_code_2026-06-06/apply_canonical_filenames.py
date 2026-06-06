#!/usr/bin/env python3
"""Compute canonical filenames for all documents (deploy 118-B).

Pattern: {CASE}_{YYYY-MM-DD}_{TYPE}_{detail-slug}_{leo-id}.{ext}

Sources used (in priority):
  1. documents.doc_date (or extract from extracted_text/smart_filename)
  2. documents.classification + execution_status → TYPE code
  3. extracted_text scanned for TCT/ARP/docket → detail-slug
  4. Fallback: 'unknown-date', 'OTHER', 'no-detail'
"""
import argparse
import json
import re
from datetime import date
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

CASE_MAP = {
    "MWK-001":     "MWK",
    "Paracale-001": "PCL",
    "Owner":       "LT",
    None:          "UNK",
    "":            "UNK",
    "unknown":     "UNK",
    "Unknown":     "UNK",
}

# Classification → TYPE mapping (most specific first)
TYPE_MAP = [
    (r"judicial\s+affidavit",        "JAFF"),
    (r"affidavit",                   "AFF"),
    (r"verified\s+complaint|^complaint", "COMPL"),
    (r"complaint",                   "COMPL"),
    (r"answer",                      "ANSW"),
    (r"^reply$|^reply\b",            "REPLY"),
    (r"motion",                      "MOT"),
    (r"comment|opposition",          "OPPOS"),
    (r"order",                       "ORDER"),
    (r"decision",                    "DECISION"),
    (r"resolution",                  "RESOL"),
    (r"notice",                      "NOTICE"),
    (r"memorandum|memo|legal\s+memo|position\s+paper", "MEMO"),
    (r"verification",                "VERIF"),
    (r"compliance",                  "COMPLI"),
    (r"petition",                    "PETITION"),
    (r"brief",                       "BRIEF"),
    (r"court\s+filing",              "COURTFILING"),
    (r"deed",                        "DEED"),
    (r"special\s+power\s+of\s+attorney|^spa", "SPA"),
    (r"power\s+of\s+attorney",       "SPA"),
    (r"revocation",                  "SPA-REVOKE"),
    (r"title\s*\(tct/oct\)|^title$|^title\s*\(tct\)", "TCT"),
    (r"tax\s+document",              "TAXDEC"),  # default for tax docs
    (r"receipt",                     "OR"),
    (r"demand\s+letter",             "DEMAND"),
    (r"letter|correspondence",       "LETTER"),
    (r"email",                       "EMAIL"),
    (r"government\s+submission",     "GOVT"),
    (r"contract",                    "CONTRACT"),
    (r"financial\s+statement",       "FINSTMT"),
    (r"summary",                     "MEMO"),
    (r"transcript",                  "TRANSCRIPT"),
    (r"appraisal",                   "APPRAISAL"),
    (r"map|plan|survey",             "MAP"),
    (r"exhibit",                     "EXHIBIT"),
    (r"arta",                        "ARTA"),
]


def case_code(case_file):
    return CASE_MAP.get(case_file, "UNK")


def doc_type(classification, smart_filename, extracted_text):
    """Pick best TYPE code."""
    # Filename hints first
    sfn = (smart_filename or "").lower()
    if "exhibit" in sfn and not any(k in sfn for k in ("complaint", "answer", "reply")):
        return "EXHIBIT"
    if "tct" in sfn or "oct" in sfn:
        return "TCT"
    if "tax" in sfn and "dec" in sfn:
        return "TAXDEC"
    if "judicial" in sfn and "affidavit" in sfn:
        return "JAFF"
    if "complaint" in sfn:
        return "COMPL"
    if "answer" in sfn:
        return "ANSW"
    if "deed" in sfn:
        return "DEED"
    if "spa" in sfn or "power of attorney" in sfn:
        return "SPA"
    if "notice" in sfn and "trial" in sfn:
        return "NOTICE"
    if "memorandum" in sfn or "memo" in sfn:
        return "MEMO"
    if "petition" in sfn:
        return "PETITION"

    cls = (classification or "").lower()
    for pattern, code in TYPE_MAP:
        if re.search(pattern, cls, re.IGNORECASE):
            return code

    # Heuristics from extracted_text
    if extracted_text:
        t = extracted_text[:5000]
        if re.search(r"NOTICE\s+OF\s+PRE[\-\s]?TRIAL", t, re.IGNORECASE): return "NOTICE"
        if re.search(r"JUDICIAL\s+AFFIDAVIT", t, re.IGNORECASE): return "JAFF"
        if re.search(r"AFFIDAVIT\b", t, re.IGNORECASE): return "AFF"
        if re.search(r"COMPLAINT\s+FOR|VERIFIED\s+COMPLAINT", t, re.IGNORECASE): return "COMPL"
        if re.search(r"DEED\s+OF\s+(?:ABSOLUTE\s+)?(?:SALE|DONATION|CONFIRMATION)", t, re.IGNORECASE): return "DEED"
        if re.search(r"SPECIAL\s+POWER\s+OF\s+ATTORNEY", t, re.IGNORECASE): return "SPA"
        if re.search(r"ANSWER\s+WITH", t, re.IGNORECASE): return "ANSW"
        if re.search(r"DECLARATION\s+OF\s+REAL\s+PROPERTY", t, re.IGNORECASE): return "TAXDEC"
        if re.search(r"STATEMENT\s+OF\s+ACCOUNT", t, re.IGNORECASE): return "SOA"
        if re.search(r"OFFICIAL\s+RECEIPT", t, re.IGNORECASE): return "OR"
        if re.search(r"TRANSFER\s+CERTIFICATE\s+OF\s+TITLE", t, re.IGNORECASE): return "TCT"
    return "OTHER"


def slugify(s, maxlen=40):
    if not s: return ""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen]


def detail_slug(text, smart_filename, doc_id, dtype):
    """Pick the most identifying detail for this doc."""
    text = (text or "")[:8000]
    sfn = smart_filename or ""

    # TCT number anywhere → top priority
    m = re.search(r"\b(T-?\d{4,7}(?:[\-\s]\d{4,7})?)\b", text + " " + sfn)
    if m:
        norm = m.group(1).upper().replace(" ", "-")
        if not norm.startswith("T-"): norm = "T-" + norm[1:]
        return slugify(norm.replace("T-", "T"))

    # ARP / Tax Dec
    m = re.search(r"(GR-\d{4}-[A-Z]{2}-\d{2}-\d{3}-\d{5}|ARP-?\d+)", text + " " + sfn, re.IGNORECASE)
    if m: return slugify("arp-" + m.group(1).replace("GR-", "").replace("ARP-", ""))[:40]

    # Docket
    m = re.search(r"(?:Civil\s+Case\s+No\.?\s*|CV[\-\s]?)([\dA-Z\-]+)", text + " " + sfn, re.IGNORECASE)
    if m: return slugify("case-" + m.group(1))[:40]

    # Exhibit letter
    m = re.search(r"Exhibit\s+([A-Z]+(?:\s*to\s*[A-Z\-0-9]+)?)", sfn, re.IGNORECASE)
    if m: return slugify("exhibit-" + m.group(1).strip())

    # Party name
    for name in ("Balane", "Pajarillo", "Macale", "Buenaventura", "Llamanzares", "De La Fuente",
                 "Inocalla", "Zschoche", "Keesey", "Worrick", "Aguilar"):
        if name.lower() in (text + " " + sfn).lower():
            return slugify(name)

    # If type is RPT/TAXDEC, try year
    if dtype in ("TAXDEC", "RPT", "SOA", "OR"):
        y = re.search(r"\b(19|20)(\d{2})\b", sfn)
        if y: return slugify("y" + y.group(0))

    # Fallback: use first non-prefix word of smart_filename
    if sfn:
        # strip drive prefix
        clean = re.sub(r"^[a-f0-9]+__", "", sfn)
        clean = re.sub(r"^null_|^drive_\d+_file_\d+", "", clean)
        clean = re.sub(r"\.[a-zA-Z]{2,5}$", "", clean)
        clean = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]", "", clean)
        clean = re.sub(r"^YYYY[-_]MM[-_]DD[-_]", "", clean)
        if clean:
            return slugify(clean[:50])
    return "no-detail"


def doc_date_str(doc_date_val, smart_filename, extracted_text):
    if doc_date_val:
        try:
            return doc_date_val.isoformat()
        except: pass
    # From smart_filename
    sfn = smart_filename or ""
    m = re.match(r"(\d{4})[-_](\d{2})[-_](\d{2})", sfn)
    if m and m.group(1) not in ("YYYY", "0000"):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # From extracted_text (first 1000 chars)
    t = (extracted_text or "")[:3000]
    m = re.search(r"(?:dated?|filed)[:\s]+(?:on\s+)?([A-Z][a-z]+ \d{1,2},?\s+\d{4})", t)
    if m:
        try:
            from datetime import datetime
            return datetime.strptime(m.group(1).replace(",",""), "%B %d %Y").date().isoformat()
        except: pass
    return "unknown-date"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", type=int, default=20)
    ap.add_argument("--reapply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    sql = """
        SELECT id, smart_filename, case_file, classification, execution_status,
               doc_date, mime_type,
               LEFT(extracted_text, 8000) AS text
          FROM documents
         WHERE """ + ("" if args.reapply else " (canonical_filename IS NULL OR canonical_filename = '') AND ") + """
               extracted_text IS NOT NULL
         ORDER BY id
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql.replace("WHERE   AND", "WHERE").replace("WHERE  AND", "WHERE"))
    docs = cur.fetchall()
    print(f"  computing canonical for {len(docs)} docs …")

    samples = []
    for d in docs:
        ccode = case_code(d["case_file"])
        dtype = doc_type(d["classification"], d["smart_filename"], d["text"])
        ddate = doc_date_str(d["doc_date"], d["smart_filename"], d["text"])
        slug = detail_slug(d["text"], d["smart_filename"], d["id"], dtype)
        ext = ".pdf"  # default; refine from mime if needed
        mime = (d["mime_type"] or "").lower()
        if "docx" in mime or (d["smart_filename"] or "").lower().endswith(".docx"): ext = ".docx"
        canonical = f"{ccode}_{ddate}_{dtype}_{slug or 'no-detail'}_{d['id']:04d}{ext}"
        # sanity cap length
        canonical = canonical[:200]
        if args.dry_run:
            samples.append((d["id"], d["smart_filename"] or "(empty)", canonical))
            continue
        cur.execute("""
            UPDATE documents
               SET canonical_filename = %s,
                   canonical_filename_at = now()
             WHERE id = %s
        """, (canonical, d["id"]))
        if len(samples) < args.show:
            samples.append((d["id"], d["smart_filename"] or "(empty)", canonical))

    print(f"\n  Sample renames ({len(samples)} of {len(docs)}):")
    for did, old, new in samples[:args.show]:
        print(f"    #{did:4d}  {(old or '(empty)')[:70]:70s}  →  {new}")
    print(f"  ✓ {len(docs)} docs {'previewed' if args.dry_run else 'renamed'}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
