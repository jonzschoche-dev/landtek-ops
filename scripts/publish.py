#!/usr/bin/env python3
"""publish.py — one-command instrument publisher (VPS-side core).

Collapses the 6-step loop hand-cranked all session — render -> register -> host -> Telegram —
into one call. Distinct from report_publisher.py (which serves TEXT reports to /reports/);
this serves PDF INSTRUMENTS via the documents table + the public /files/c/<id> endpoint.

  markdown  -> PDF (render_memo)
            -> documents row (file_path) + document_matter_links
            -> https://leo.hayuma.org/files/c/<id>
            -> optional Telegram sendDocument

  python3 publish.py /root/landtek/1891_output/foo.md --matter MWK-ARTA-1210 --title "Errata — OP/1210"
  python3 publish.py .../foo.md --matter MWK-OP-PETITION --matter MWK-ARTA-1210 --telegram --caption "..."
  python3 publish.py .../foo.md --dry          # render + show the would-be URL; no DB write, no send
Usually invoked via the Mac wrapper scripts/publish.sh (handles the scp + pulls the PDF back).
"""
from __future__ import annotations
import argparse, os, sys
import datetime as dt
import psycopg2

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
BASE = "https://leo.hayuma.org/files/c"
JONATHAN = "6513067717"


def _render(md_path):
    import render_memo
    pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    render_memo.render(md_path, pdf_path)
    return pdf_path


CLIENT_OF = {"MWK": "MWK-001", "PAR": "Paracale-001", "NIBDC": "NIBDC-001"}


def _client_for(matters):
    """case_file must be the CLIENT (domain-constrained); the matter goes in document_matter_links."""
    m = matters[0] if matters else ""
    return next((c for p, c in CLIENT_OF.items() if m.startswith(p)), "MWK-001")


def _register(cur, path, title, matters, classification, date):
    fn = os.path.basename(path)
    case_file = _client_for(matters)
    cur.execute("""INSERT INTO documents
        (case_file, original_filename, smart_filename, mime_type, classification, doc_date, file_path)
        VALUES (%s,%s,%s,'application/pdf',%s,%s,%s) RETURNING id""",
        (case_file, fn, (title or fn), classification, date, path))
    did = cur.fetchone()[0]
    for mc in matters:
        cur.execute("INSERT INTO document_matter_links (doc_id, matter_code) VALUES (%s,%s) ON CONFLICT DO NOTHING", (did, mc))
    return did


def _telegram(path, caption):
    import requests
    tok = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
    if not tok:
        return "no token in env"
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                          data={"chat_id": JONATHAN, "caption": (caption or "")[:1024]},
                          files={"document": f}, timeout=90)
    j = r.json()
    return f"sent (msg {j.get('result',{}).get('message_id')})" if j.get("ok") else f"FAILED {str(j)[:140]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("--matter", action="append", default=[])
    ap.add_argument("--title")
    ap.add_argument("--classification", default="Work Product — Counsel Deliverable")
    ap.add_argument("--date")
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--caption")
    ap.add_argument("--no-pdf", action="store_true", help="register the file as-is (skip render)")
    ap.add_argument("--dry", action="store_true", help="render only; no DB write, no Telegram")
    a = ap.parse_args()
    if not os.path.exists(a.md):
        sys.exit(f"[publish] not found: {a.md}")
    path = a.md if a.no_pdf else _render(a.md)
    print(f"[publish] rendered -> {path} ({os.path.getsize(path)//1024} KB)")
    if a.dry:
        print(f"[publish] DRY — would register (matters={a.matter or ['MWK-001']}, class='{a.classification}')"
              + (f" + Telegram" if a.telegram else ""))
        return
    conn = psycopg2.connect(DSN); conn.autocommit = True
    did = _register(conn.cursor(), path, a.title, a.matter, a.classification, a.date or dt.date.today().isoformat())
    url = f"{BASE}/{did}"
    print(f"[publish] doc#{did} hosted -> {url}" + (f"  (linked: {', '.join(a.matter)})" if a.matter else ""))
    if a.telegram:
        print(f"[publish] Telegram: {_telegram(path, a.caption)}")
    print(url)


if __name__ == "__main__":
    main()
