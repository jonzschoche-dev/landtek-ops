#!/usr/bin/env python3
"""ingest_arta_circulars.py — embed operator-supplied ARTA circular PDFs as VERBATIM law.

WHY THIS IS OPERATOR-FED, not auto-fetched: arta.gov.ph sits behind a Cloudflare bot-check that
403s every automated fetch (curl / WebFetch / headless browser). A human browser passes it trivially,
so the operator downloads the official PDFs; this script embeds their VERBATIM text into legal_chunks
(the same store the rest of the law library uses), replacing the "[TEXT PENDING]" placeholders. No
paraphrase is ever embedded — only the extracted PDF text. Extraction is local (PyMuPDF), embedding is
in-house Ollama ($0). Idempotent: re-running replaces a circular's chunks rather than duplicating.

  # 1) operator downloads the PDFs (browser passes Cloudflare) into a folder, named with the MC number
  # 2) run on the VPS (needs Ollama + Postgres):
  python3 scripts/ingest_arta_circulars.py --dir /root/landtek/arta_inbox            # ingest all matched
  python3 scripts/ingest_arta_circulars.py --dir /root/landtek/arta_inbox --status   # what's matched/missing
  python3 scripts/ingest_arta_circulars.py --dir /root/landtek/arta_inbox --force     # re-ingest even if present

Filename matching is by the circular NUMBER anywhere in the filename, e.g. "MC-2020-07.pdf",
"Memorandum-Circular-2020-07-Guidelines-on-CART.pdf", "arta_advisory_2024-20.pdf" all match.
"""
from __future__ import annotations
import argparse
import os
import re
import sys

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legal_authority as la  # reuse the verified ingest/embed path — no reimplementation

# The 13 ARTA issuances referenced across the LANDTEK corpus (see the legal_chunks "[TEXT PENDING]"
# rows). `key` = canonical circular number used for filename matching. `title` is best-known; the
# supplied PDF is the authority — a "[confirm]" title is a label only, never operative text.
MANIFEST = [
    # key(number)   forum   citation                                   title
    ("2018-01",  "ARTA", "ARTA MC No. 2018-01 (PCOO-DILG-ARTA Joint MC)", "Freedom of Information — People's FOI Manual / joint implementing MC"),
    ("2019-001", "ARTA", "ARTA MC No. 2019-001",                          "Early ARTA implementing circular [confirm title from PDF]"),
    ("2019-002", "ARTA", "ARTA MC No. 2019-002",                          "Guidelines on Citizen's Charter Implementation under RA 11032"),
    ("2020-07",  "ARTA", "ARTA MC No. 2020-07",                           "Guidelines on the Designation of a Committee on Anti-Red Tape (CART)"),
    ("2021-08",  "ARTA", "ARTA MC No. 2021-08",                           "Pilot Implementation — Referral & Handling of Complaints under RA 9485 s.21(a)-(g)"),
    ("2021-11",  "ARTA", "ARTA MC No. 2021-11",                           "Nationwide Implementation — Referral & Handling of Complaints (ss.12(f),21(a)-(g)) to CART"),
    ("2022-05",  "ARTA", "ARTA MC No. 2022-05",                           "Harmonized Client Satisfaction Measurement (CSM) [confirm title from PDF]"),
    ("2023-02",  "ARTA", "ARTA MC No. 2023-02",                           "2023 ARTA Revised Rules of Procedure"),
    ("2023-08",  "ARTA", "ARTA MC No. 2023-08",                           "Amendment on Certain Provisions of ARTA MC No. 2020-07 (CART Guidelines)"),
    ("2010-13",  "ARTA", "ARTA MC No. 2010-13",                           "Legacy issuance [confirm title/issuing body from PDF]"),
    ("2024-20",  "ARTA", "ARTA Advisory No. 2024-20",                     "Citizen's Charter / compliance-deadline advisory [confirm title from PDF]"),
    ("2025-005", "ARTA", "ARTA Advisory No. 2025-005",                    "ARTA advisory [confirm title from PDF]"),
    ("2026-007", "ARTA", "ARTA Advisory No. 2026-007",                    "ARTA advisory [confirm title from PDF]"),
]


def _num(s: str) -> str:
    """Normalize a circular number for matching: '2019-1' -> '2019-001' won't collide, keep as-is but
    compare on the (year, tail-as-int) so '2019-001' == '2019-1'."""
    m = re.search(r"(20\d\d)[-_ ]0*(\d+)", s)
    return f"{m.group(1)}-{int(m.group(2))}" if m else ""


def _extract(path: str) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        t = "\n".join(p.get_text() for p in doc); doc.close()
    except Exception:
        # fallback to pdftotext if PyMuPDF chokes
        import subprocess
        t = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _existing_real_chunks(cur, citation: str) -> int:
    cur.execute("SELECT count(*) FROM legal_chunks WHERE citation=%s AND text NOT ILIKE '%%TEXT PENDING%%'",
                (citation,))
    return cur.fetchone()[0]


def _purge(cur, key: str, citation: str):
    """Remove this circular's placeholder rows and any prior real chunks for a clean replace."""
    # exact citation match
    cur.execute("DELETE FROM legal_chunks WHERE citation=%s", (citation,))
    # the shared placeholder index/pending rows that name this number
    cur.execute("DELETE FROM legal_chunks WHERE text ILIKE '%%TEXT PENDING%%' AND text ILIKE %s",
                (f"%{key}%",))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/root/landtek/arta_inbox", help="folder of operator-supplied PDFs")
    ap.add_argument("--status", action="store_true", help="show matched/missing without ingesting")
    ap.add_argument("--force", action="store_true", help="re-ingest even if real chunks already present")
    a = ap.parse_args()

    pdfs = {}
    if os.path.isdir(a.dir):
        for fn in os.listdir(a.dir):
            if fn.lower().endswith(".pdf"):
                n = _num(fn)
                if n:
                    pdfs.setdefault(n, os.path.join(a.dir, fn))

    c = la._conn(); cur = c.cursor(); la._ensure(cur)
    print(f"=== ARTA circular ingest — source dir: {a.dir} ({len(pdfs)} numbered PDF(s) found) ===\n")
    ingested = missing = skipped = 0
    for key, forum, citation, title in MANIFEST:
        norm = _num(key)
        path = pdfs.get(norm)
        have_real = _existing_real_chunks(cur, citation)
        tag = "  "
        if have_real and not a.force:
            print(f"{tag}✓ already embedded   {citation}  ({have_real} chunks)")
            skipped += 1
            continue
        if not path:
            print(f"{tag}✗ NEED PDF           {citation} — {title}")
            missing += 1
            continue
        if a.status:
            print(f"{tag}→ ready to ingest    {citation}  <- {os.path.basename(path)}")
            continue
        text = _extract(path)
        if len(text) < 200:
            print(f"{tag}! extract too short  {citation} ({len(text)} chars) — is the PDF a scan? OCR needed. SKIPPED")
            missing += 1
            continue
        _purge(cur, key, citation)
        # verify=False => verify_flag 'operator-official' (operator downloaded the official copy)
        la.ingest(forum, citation, title, f"operator-supplied official PDF ({os.path.basename(path)}); arta.gov.ph",
                  text, verify=False)
        ingested += 1

    print(f"\n=== summary: {ingested} ingested · {skipped} already present · {missing} still need a PDF ===")
    if missing and not a.status:
        print("Download the missing circulars from arta.gov.ph/documents/ (a human browser passes the")
        print("Cloudflare check), drop them in the inbox folder named with the MC number, and re-run.")


if __name__ == "__main__":
    main()
