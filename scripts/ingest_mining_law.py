#!/usr/bin/env python3
"""ingest_mining_law.py — embed the Philippine MINING statutory frame as VERBATIM law (forum=MINING).

WHY THIS SHAPE: the mining frame that governs the PMRB (Provincial/City Mining Regulatory Board) and
the Paracale gold matter splits by SOURCE availability:
  • The STATUTES are public-domain and lawphil serves their full verbatim text, fetchable from the VPS
    → auto-fetched + HARD-VERIFIED (the act number must literally appear in the fetched text) before any
    write, exactly like the jurisprudence path — a wrong URL can never embed the wrong act.
  • The IRRs (DENR Administrative Orders) and PD 1899 live on DENR/MGB / Official Gazette behind
    bot-checks that 403 every automated fetch → OPERATOR-FED: the human downloads the official PDF, drops
    it in the inbox named with the issuance number, and this script embeds its VERBATIM extracted text.

No paraphrase is ever embedded — only fetched/extracted source text. Embedding is in-house Ollama ($0).
Idempotent: an issuance already carrying real chunks is skipped unless --force; re-running is cheap.

  # run on the VPS (needs docker Postgres + Ollama):
  python3 scripts/ingest_mining_law.py --status                       # what's embedded / auto-ready / needs a PDF
  python3 scripts/ingest_mining_law.py                                # fetch+embed the auto ones; embed any matched PDFs
  python3 scripts/ingest_mining_law.py --dir /root/landtek/mining_inbox   # operator PDF folder (default shown)
  python3 scripts/ingest_mining_law.py --force                        # re-embed even if already present

Operator PDFs are matched by the issuance number anywhere in the filename, e.g. "DAO-96-40.pdf",
"DENR_DAO_34_s1992_IRR.pdf", "PD-1899.pdf" all match their manifest entry.
"""
from __future__ import annotations
import argparse
import html as _html
import os
import re
import sys
import urllib.request

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_authority as la  # reuse the verified _conn/_ensure/_chunks/_embed + ingest path — no reimpl

FORUM = "MINING"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MIN_STATUTE_CHARS = 3000  # a real act is long; a 404 stub / thin page is short

# The mining frame. Each entry:
#   key      — the issuance NUMBER, used to verify fetched text + match operator filenames
#   citation — canonical label stored on every chunk
#   title    — best-known descriptive title (the source text is the authority, not this label)
#   url      — lawphil verbatim source (auto-fetch); None => OPERATOR-FED (needs a PDF in --dir)
MANIFEST = [
    # key       citation                       url / None                                                            title
    ("7076",  "RA 7076",  "https://lawphil.net/statutes/repacts/ra1991/ra_7076_1991.html",
     "People's Small-Scale Mining Act of 1991 — CREATES the Provincial/City Mining Regulatory Board (PMRB), Minahang Bayan, small-scale mining permits/contracts"),
    ("7942",  "RA 7942",  "https://lawphil.net/statutes/repacts/ra1995/ra_7942_1995.html",
     "Philippine Mining Act of 1995 — MPSA/EP/FTAA regime, MGB mandate, mineral agreements (the large-scale frame behind the Paracale gold / TSX matter)"),
    ("1899",  "PD 1899",  None,
     "Presidential Decree No. 1899 (1984) — Establishing Small-Scale Mining as a New Dimension in Mineral Development (pre-RA 7076 small-scale decree)"),
    ("34",    "DENR DAO No. 34, s.1992", None,
     "Implementing Rules and Regulations of RA 7076 (how the PMRB actually operates — application, permit, Minahang Bayan procedure)"),
    ("96-40", "DENR DAO No. 96-40",     None,
     "Revised Implementing Rules and Regulations of RA 7942, as amended (the operative mining IRR)"),
]


def _fetch(url: str) -> str:
    """Fetch lawphil statute text — HTML (strip tags) or PDF-hosted (PyMuPDF), mirroring the juris path."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    data = urllib.request.urlopen(req, timeout=30).read()
    if url.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        import fitz  # PyMuPDF (already on the VPS)
        d = fitz.open(stream=data, filetype="pdf")
        t = "\n".join(p.get_text() for p in d); d.close()
    else:
        raw = data.decode("utf-8", "ignore")
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", " ", t)
        t = _html.unescape(t)
        for boiler in ("Toggle navigation", "The LawPhil Project", "Arellano Law Foundation",
                       "Republic of the Philippines SUPREME COURT", "Constitution Statutes Executive"):
            t = t.replace(boiler, " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _extract_pdf(path: str) -> str:
    try:
        import fitz
        d = fitz.open(path); t = "\n".join(p.get_text() for p in d); d.close()
    except Exception:
        import subprocess
        t = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _num_token(key: str) -> re.Pattern:
    """Verify the issuance number is really in the text/filename. '96-40' -> matches '96-40'; '34' ->
    a bare 34 is too loose for filename matching but fine for text verification of a DAO body."""
    return re.compile(re.escape(key).replace(r"\-", r"[-\s]?"))


def _existing_real(cur, citation: str) -> int:
    cur.execute("SELECT count(*) FROM legal_chunks WHERE citation=%s AND text NOT ILIKE '%%TEXT PENDING%%'",
                (citation,))
    return cur.fetchone()[0]


def _match_pdf(key: str, files: dict) -> str | None:
    """Match an operator PDF by the issuance number appearing in the filename."""
    tok = _num_token(key)
    for norm, path in files.items():
        if tok.search(norm):
            return path
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/root/landtek/mining_inbox", help="operator PDF folder (for the IRRs / PD 1899)")
    ap.add_argument("--status", action="store_true", help="show embedded / auto-ready / needs-a-PDF; write nothing")
    ap.add_argument("--force", action="store_true", help="re-embed even if real chunks already present")
    a = ap.parse_args()

    files = {}
    if os.path.isdir(a.dir):
        for fn in os.listdir(a.dir):
            if fn.lower().endswith(".pdf"):
                files[fn.lower().replace("_", "-").replace(" ", "-")] = os.path.join(a.dir, fn)

    c = la._conn(); cur = c.cursor(); la._ensure(cur)
    print(f"=== MINING law ingest (forum={FORUM}) — operator dir: {a.dir} ({len(files)} PDF(s)) ===\n")
    embedded = present = needpdf = 0
    for key, citation, url, title in MANIFEST:
        have = _existing_real(cur, citation)
        if have and not a.force:
            print(f"  ✓ embedded      {citation:26s} ({have} chunks)")
            present += 1
            continue

        if url:  # AUTO: fetch verbatim from lawphil + hard-verify the act number is in the text
            try:
                text = _fetch(url)
            except Exception as e:
                print(f"  ✗ FETCH FAILED  {citation:26s} — {e}")
                needpdf += 1
                continue
            if len(text) < MIN_STATUTE_CHARS:
                print(f"  ! too short     {citation:26s} ({len(text)} chars) — page changed? SKIPPED")
                needpdf += 1
                continue
            if not _num_token(key).search(text):
                print(f"  ✗ VERIFY FAIL   {citation:26s} — '{key}' not found in fetched text; refusing to embed")
                needpdf += 1
                continue
            if a.status:
                print(f"  → auto-ready    {citation:26s} ({len(text)} chars)  <- {url}")
                continue
            la.ingest(FORUM, citation, title, url, text, verify=False)
            embedded += 1
        else:  # OPERATOR-FED: match a PDF in the inbox by issuance number
            path = _match_pdf(key, files)
            if not path:
                print(f"  ✗ NEED PDF      {citation:26s} — {title}")
                needpdf += 1
                continue
            text = _extract_pdf(path)
            if len(text) < 500:
                print(f"  ! extract short {citation:26s} ({len(text)} chars) — scanned PDF? needs OCR. SKIPPED")
                needpdf += 1
                continue
            if not _num_token(key).search(text):
                print(f"  ⚠ number '{key}' not in {os.path.basename(path)} text — wrong PDF? embedding anyway is unsafe. SKIPPED")
                needpdf += 1
                continue
            if a.status:
                print(f"  → pdf-ready     {citation:26s}  <- {os.path.basename(path)}")
                continue
            cur.execute("DELETE FROM legal_chunks WHERE citation=%s", (citation,))  # clean replace
            la.ingest(FORUM, citation, title, f"operator-supplied official PDF ({os.path.basename(path)})", text, verify=False)
            embedded += 1

    print(f"\n=== summary: {embedded} embedded · {present} already present · {needpdf} auto-failed/need-a-PDF ===")
    if needpdf and not a.status:
        print(f"For the operator-fed issuances (DAO 34 s.1992, DAO 96-40, PD 1899): download the official copy")
        print(f"(mgb.gov.ph / DENR / Official Gazette in a real browser), drop it in {a.dir} named with the")
        print(f"issuance number (e.g. 'DAO-96-40.pdf', 'PD-1899.pdf'), and re-run.")


if __name__ == "__main__":
    main()
