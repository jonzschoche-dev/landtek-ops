#!/usr/bin/env python3
"""find_missing_record.py — recover referenced-but-unheld records from the LIVE sources.

"Not in our corpus" != "doesn't exist". The corpus is a SELECTIVE ingest: inbound agency
email only started ~Mar 2026 (the relevance gate dropped earlier agency mail), and scanned
attachments were never OCR'd. This closes the corpus against the LIVE mailbox, reusing
blend_emails for the heavy lifting (dedup / fetch-with-fresh-id / separation guard / links):

  live Gmail search  -> upsert envelope (matter from the DOCKET number, separation-safe)
   -> blend_emails.blend_email() fetch + ingest attachments
   -> Tesseract OCR the scanned attachments (local, quota-free; Gemini free-tier 429s)
   -> anything still unfound is logged in record_gaps (to request externally).

  find_missing_record.py --backfill            # all case-relevant agency mail (DRY-RUN)
  find_missing_record.py --backfill --apply    # write
  find_missing_record.py --query '<gmail q>' --apply
  find_missing_record.py --ocr --apply         # OCR-fill hollow scanned docs only
"""
from __future__ import annotations
import argparse, glob, os, re, subprocess, sys, tempfile
import datetime as dt
from email.utils import parsedate_to_datetime
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
from gmail_watcher import gmail_client
import blend_emails as B

# docket -> matter: all MWK-side ARTA dockets (separation-safe — never crosses the client line)
DOCKET_MAP = {
    "SL-2026-0209-1319": "MWK-ARTA-1319", "SL-2026-0209-1321": "MWK-ARTA-1321",
    "SL-2026-0128-1210": "MWK-ARTA-1210", "SL-2026-0128-1212": "MWK-ARTA-1212",
    "SL-2026-0218-1378": "MWK-ARTA-1378",
}
DOCKET_RE = re.compile(r"SL-20\d\d-\d{4}-\d{3,4}")
# MWK-SPECIFIC land identifiers only (never 'penro.camnorte' alone — PENRO also handles NIBDC mining;
# these tie a doc to the Keesey/MWK boundary matter without crossing the client line)
MWK_SIGNAL = re.compile(r"lot 2-a|psd-221861|psd-229480|t-32911|t-4497|special patent.{0,30}mercedes|boundary history|mercedes police", re.I)
AGENCY_QUERIES = [
    "from:penro.camnorte@yahoo.com OR to:penro.camnorte@yahoo.com",
    "from:(arta.gov.ph) OR from:(denr.gov.ph) OR from:(dilg.gov.ph)",
    '"PENRO Camarines Norte" OR Fortuno OR Remoto',
    "CTN SL-2026",
    "Psd-229480 OR Psd-221861",
]


def _hdr(p, n):
    return next((h["value"] for h in p.get("headers", []) if h["name"].lower() == n.lower()), None)


def _atts(payload):
    out = []
    def w(p):
        b = p.get("body") or {}
        if p.get("filename") and b.get("attachmentId"):
            out.append({"mime": p.get("mimeType") or "application/octet-stream",
                        "size": b.get("size") or 0, "filename": p["filename"],
                        "attachmentId": b["attachmentId"]})
        for c in p.get("parts", []) or []:
            w(c)
    w(payload)
    return out


def _envelope(svc, mid):
    d = svc.users().messages().get(userId="me", id=mid, format="full").execute()
    p = d["payload"]; subj = _hdr(p, "Subject") or ""
    atts = _atts(p)
    blob = " ".join(filter(None, [subj, d.get("snippet"), " ".join(a["filename"] for a in atts)]))
    matters = sorted({DOCKET_MAP[k] for k in DOCKET_RE.findall(blob) if k in DOCKET_MAP})
    if not matters and MWK_SIGNAL.search(blob):     # pre-docket MWK boundary/PENRO correspondence
        matters = ["MWK-001"]
    try:
        sent = parsedate_to_datetime(_hdr(p, "Date")).replace(tzinfo=None)
    except Exception:
        sent = None
    try:
        recv = dt.datetime.utcfromtimestamp(int(d["internalDate"]) / 1000)
    except Exception:
        recv = None
    return {"message_id": mid, "thread_id": d.get("threadId"), "subject": subj,
            "from_addr": _hdr(p, "From"), "from_name": _hdr(p, "From"), "to_addrs": _hdr(p, "To"),
            "sent_at": sent, "received_at": recv, "attachment_refs": atts,
            "matter_codes": matters, "case_file": None, "document_id": None}


def _upsert(cur, g):
    cur.execute("""INSERT INTO gmail_messages
          (message_id, thread_id, from_addr, to_addrs, subject, sent_at, received_at,
           has_attachments, attachment_refs, matter_codes, relevance_score, relevance_status,
           provenance_level, ingested_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1.0,'agency_backfill','inferred_strong',now())
        ON CONFLICT (message_id) DO UPDATE SET
          attachment_refs = COALESCE(gmail_messages.attachment_refs, EXCLUDED.attachment_refs),
          matter_codes = CASE WHEN COALESCE(array_length(gmail_messages.matter_codes,1),0) > 0
                              THEN gmail_messages.matter_codes ELSE EXCLUDED.matter_codes END""",
        (g["message_id"], g["thread_id"], g["from_addr"],
         ([g["to_addrs"]] if g["to_addrs"] else None), g["subject"],
         g["sent_at"], g["received_at"], bool(g["attachment_refs"]),
         psycopg2.extras.Json(g["attachment_refs"]), g["matter_codes"]))


def _tesseract(path):
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "p")
        subprocess.run(["pdftoppm", "-png", "-r", "200", path, base], capture_output=True, timeout=600)
        out = []
        for img in sorted(glob.glob(base + "*.png")):
            r = subprocess.run(["tesseract", img, "stdout"], capture_output=True, text=True, timeout=180)
            out.append(r.stdout)
    return re.sub(r"[ \t]+", " ", "\n".join(out)).strip()


def ocr_fill(cur, apply, only_ids=None, limit=300):
    where = ("coalesce(extracted_text,'')='' AND file_path IS NOT NULL "
             "AND lower(coalesce(mime_type,'')) LIKE '%%pdf%%'")
    if only_ids:
        where += " AND id IN (" + ",".join(str(int(i)) for i in only_ids) + ")"
    cur.execute("SELECT id, file_path, original_filename FROM documents WHERE "
                + where + " ORDER BY id LIMIT %s", (limit,))
    rows = cur.fetchall(); n = 0
    for d in rows:
        if not os.path.exists(d["file_path"]):
            continue
        try:
            txt = _tesseract(d["file_path"])
        except Exception as e:
            print(f"    ! OCR fail doc#{d['id']}: {e}"); continue
        if not txt:
            continue
        bdate = B.borne_date(txt)
        print(f"    ⊕ OCR doc#{d['id']} {(d['original_filename'] or '?')[:42]} -> {len(txt)}c"
              + (f" borne={bdate}" if bdate else ""))
        if apply:
            cur.execute("""UPDATE documents SET extracted_text=%s, ingest_status='ocr_tesseract',
                  doc_date=COALESCE(doc_date,%s) WHERE id=%s""",
                (txt, (str(bdate) if bdate else None), d["id"]))
        n += 1
    return n


def _collect(svc, queries, limit):
    seen = []
    for q in queries:
        tok = None
        while True:
            r = svc.users().messages().list(userId="me", q=q, maxResults=100, pageToken=tok).execute()
            for m in r.get("messages", []):
                if m["id"] not in seen:
                    seen.append(m["id"])
            tok = r.get("nextPageToken")
            if not tok or (limit and len(seen) >= limit):
                break
    return seen[:limit] if limit else seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--matter")
    ap.add_argument("--query")
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    conn = psycopg2.connect(B.DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    B.ensure_schema(cur)
    cur.execute("""CREATE TABLE IF NOT EXISTS record_gaps (
        id serial PRIMARY KEY, reference text NOT NULL, matter_code text, source_hint text,
        status text DEFAULT 'open', found_message_id text, found_doc_id int, note text,
        created_at timestamptz DEFAULT now(), resolved_at timestamptz,
        UNIQUE (reference, matter_code))""")
    mode = "APPLY" if a.apply else "DRY-RUN"
    svc = gmail_client()

    if a.ocr and not (a.backfill or a.query):
        print(f"[find] OCR-fill hollow scanned docs ({mode})")
        print(f"[find] OCR-filled {ocr_fill(cur, a.apply)}")
        return

    if a.matter:                                    # recover one matter's records (Stage 0 of case_dossier)
        rev = {v: k for k, v in DOCKET_MAP.items()}
        queries = []
        if rev.get(a.matter):
            queries.append(f'"{rev[a.matter]}" OR "CTN {rev[a.matter]}"')
        if a.matter.startswith("MWK"):
            queries.append('Psd-229480 OR Psd-221861 OR "Lot 2-A" OR "boundary history" OR "LETTER DATED NOVEMBER 26"')
        queries = queries or AGENCY_QUERIES
    elif a.query:
        queries = [a.query]
    else:
        queries = AGENCY_QUERIES
    ids = _collect(svc, queries, a.limit)
    print(f"[find] {len(ids)} unique live-mailbox messages match ({mode})")
    if not ids and a.query and a.apply:
        cur.execute("""INSERT INTO record_gaps (reference, status, note)
            VALUES (%s,'external_request',%s) ON CONFLICT DO NOTHING""",
            (a.query, "no live-mailbox hit — request from agency/operator"))
        print("[find] logged as record_gap (external request)")

    made_t = link_t = 0; touched = []
    for mid in ids:
        g = _envelope(svc, mid)
        tag = ",".join(g["matter_codes"]) or "—"
        if not a.apply:
            print(f"  · {mid[:16]} [{tag}] atts={len(g['attachment_refs'])} | {(g['subject'] or '')[:46]}")
            continue
        _upsert(cur, g)
        made, linked, _ = B.blend_email(cur, svc, g)
        made_t += len(made); link_t += len(linked); touched += [did for _, did, _ in made]
        if made or linked:
            print(f"  • [{tag}] {(g['subject'] or '')[:44]}")
            for fn, did, note in made:
                print(f"      + doc#{did} {fn[:40]} ({note})")
            for fn, did, how in linked:
                print(f"      = doc#{did} {fn[:40]} (dedup)")
    print(f"[find] {made_t} new docs · {link_t} linked")
    if a.apply and touched:
        print("[find] OCR pass on new scanned docs…")
        ocr_fill(cur, True, only_ids=touched)


if __name__ == "__main__":
    main()
