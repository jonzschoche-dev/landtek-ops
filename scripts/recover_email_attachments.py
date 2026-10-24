#!/usr/bin/env python3
"""Recover email attachments the PDF-only extractor (extract_email_attachments.py v1) never ingested:
non-PDF attachments (photos, scans, screenshots, .docx) and attachments on emails with case_file NULL.
Downloads to /root/landtek/uploads/_RECOVERED_<date>/<bucket>/, dedups by sha256 against documents.sha256/content_hash
and within the run, writes manifest.csv. Writes NOTHING to the DB (ingestion is a separate, matter-aware step).

  python3 scripts/recover_email_attachments.py [--dry-run] [--min-kb 30]
"""
import os, sys, csv, hashlib, argparse, re, datetime, psycopg2
sys.path.insert(0, "/root/landtek")
from extract_email_attachments import fetch_attachment_bytes
from gmail_watcher import gmail_client, ACCOUNT_ADDR

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
ap = argparse.ArgumentParser(); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--min-kb", type=int, default=30)
args = ap.parse_args()
OUT = f"/root/landtek/uploads/_RECOVERED_{datetime.date.today().isoformat()}"
SKIP_NAME = re.compile(r"^(outlook-|image0\d\d|att0000|logo|signature)", re.I)

def bucket(m):
    s = " ".join(str(x or "") for x in (m["case_file"], m["matter_codes"], m["from_addr"], m["subject"])).lower()
    if "inocalla" in s or "paracale" in s or "shiraction" in s or "nibdc" in s: return "Paracale-Inocalla"
    if m["case_file"] or m["matter_codes"] or any(k in s for k in ("keesey", "worrick", "mercedes", "balane", "ablaw", "avaslaw", "dilg", "arta", "psa")): return "MWK"
    return "unassigned"

con = psycopg2.connect(DSN); cur = con.cursor()
cur.execute("select coalesce(sha256,$$$$), coalesce(content_hash,$$$$) from documents")
known = set(h for r in cur.fetchall() for h in r if h)
cur.execute("""select id, message_id, account, received_at, from_addr, subject, case_file, matter_codes, attachment_refs, document_id
               from gmail_messages where has_attachments and attachment_refs is not null and jsonb_typeof(attachment_refs::jsonb)=$$array$$ order by received_at""")
cols = [d[0] for d in cur.description]; msgs = [dict(zip(cols, r)) for r in cur.fetchall()]
addr2acct = {v: k for k, v in ACCOUNT_ADDR.items()}; clients = {}
def client_for(a):
    k = addr2acct.get(a, "primary")
    if k not in clients: clients[k] = gmail_client(k)
    return clients[k]
seen = set(); rows = []; stats = {"candidates": 0, "saved": 0, "dup_in_corpus": 0, "dup_in_run": 0, "gone": 0}
for m in msgs:
    for a in m["attachment_refs"]:
        fn = a.get("filename") or ""; size = a.get("size") or 0
        is_pdf = fn.lower().endswith(".pdf") or (a.get("mime") or "") == "application/pdf"
        if size < args.min_kb * 1024 or SKIP_NAME.match(fn): continue
        if is_pdf and m["case_file"] and m["document_id"]: continue   # the extractor already handled these
        stats["candidates"] += 1
        b = bucket(m)
        if args.dry_run:
            rows.append([m["id"], m["received_at"], m["account"], b, fn, size, "dry-run", ""]); continue
        data, acct, note = fetch_attachment_bytes(client_for, list(ACCOUNT_ADDR.values()), m, a)
        if data is None:
            stats["gone"] += 1; rows.append([m["id"], m["received_at"], m["account"], b, fn, size, "GONE", note]); continue
        h = hashlib.sha256(data).hexdigest()
        if h in known: stats["dup_in_corpus"] += 1; rows.append([m["id"], m["received_at"], m["account"], b, fn, size, "already-in-corpus", h]); continue
        if h in seen: stats["dup_in_run"] += 1; continue
        seen.add(h)
        d = os.path.join(OUT, b); os.makedirs(d, exist_ok=True)
        name = "%s_em%s_%s" % (m["received_at"].strftime("%Y-%m-%d"), m["id"], os.path.basename(fn).replace("/", "_")[:90] or "unnamed")
        open(os.path.join(d, name), "wb").write(data); stats["saved"] += 1
        rows.append([m["id"], m["received_at"], m["account"], b, fn, size, "saved", os.path.join(b, name)])
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, "manifest.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["gmail_row", "received_at", "account", "bucket", "filename", "size", "status", "detail"]); w.writerows(rows)
print(stats, "->", OUT)
