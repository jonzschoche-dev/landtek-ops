#!/usr/bin/env python3
"""corpus_ingest.py — bulk-ingest FULL statutory texts into the law library for offline self-sufficiency.

Fetches each act's complete text from lawphil, strips HTML/boilerplate, and embeds it via legal_authority
so the system holds the whole governing law in-house (no external legal research needed). Skips an act if
the fetch is too short (a stub) so partial pages are not embedded as if complete. Runs ON THE VPS.

  python3 corpus_ingest.py            # ingest all in CORPUS not already substantially embedded
  python3 corpus_ingest.py --force    # re-ingest even if present
"""
import html as _html
import os
import re
import subprocess
import sys
import urllib.request

# (url, citation, title, forum) — the major governing laws, full text
CORPUS = [
    ("https://lawphil.net/statutes/repacts/ra1991/ra_7160_1991.html", "RA 7160 (Local Government Code, full)", "Local Government Code of 1991 — full text", "DILG"),
    ("https://lawphil.net/consti/cons1987.html", "1987 Constitution (full)", "1987 Constitution of the Philippines — full text", "CIVIL"),
    ("https://lawphil.net/statutes/repacts/ra2003/ra_9184_2003.html", "RA 9184 (Govt Procurement Reform Act, full)", "Government Procurement Reform Act — full text", "OMBUDSMAN"),
    ("https://www.dpwh.gov.ph/DPWH/files/nbc/PD.pdf", "PD 1096 (National Building Code, full)", "National Building Code (PD 1096) — full decree text (DPWH official PDF)", "ARTA"),
    ("https://lawphil.net/executive/execord/eo1987/eo_292_1987.html", "EO 292 (Administrative Code of 1987, full)", "Administrative Code of 1987 — full text", "DILG"),
    ("https://lawphil.net/statutes/repacts/ra1997/ra_8424_1997.html", "RA 8424 (NIRC / Tax Code, full)", "National Internal Revenue Code (Tax Code) — full text", "CIVIL"),
    ("https://lawphil.net/courts/rules/rc_1-71_civil.html", "Rules of Court (Rules 1-71, Civil Procedure, full)", "Rules of Court — Rules 1-71 (civil procedure incl. Rule 70 ejectment) — full text", "CIVIL"),
    ("https://lawphil.net/courts/rules/rc_110-127_2000.html", "Rules of Court (Rules 110-127, Criminal Procedure 2000, full)", "Rules of Court — Rules 110-127 (2000 Revised Rules of Criminal Procedure) — full text", "CIVIL"),
    ("https://lawphil.net/courts/rules/rc_128-134_evidence.html", "Rules of Court (Rules 128-134, Evidence, full)", "Rules of Court — Rules 128-134 (Evidence) — full text", "CIVIL"),
    ("https://lawphil.net/courts/rules/rc_72-109_proceedings.html", "Rules of Court (Rules 72-109, Special Proceedings, full)", "Rules of Court — Rules 72-109 (special proceedings incl. settlement of estate) — full text", "CIVIL"),
    ("https://lawphil.net/statutes/acts/act1930/act_3815_1930.html", "Act 3815 (Revised Penal Code, full)", "Revised Penal Code (Act No. 3815) — full text", "OMBUDSMAN"),
]
SSH_PSQL = "docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    # NOTE: TLS verification stays ON. Some PH govt sites (e.g. dpwh.gov.ph) ship a broken cert chain
    # that a given host's trust store can't verify; do NOT disable verification — ingest those sources
    # out-of-band (fetch where the cert validates, then legal_authority.py --ingest the extracted text).
    data = urllib.request.urlopen(req, timeout=120).read()
    # PDF sources (many PH laws are PDF-only — e.g. the DPWH copy of PD 1096): extract text via PyMuPDF
    if url.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        import fitz  # PyMuPDF (already on the VPS, used by pdf_compress)
        open("/tmp/_corpus_dl.pdf", "wb").write(data)
        doc = fitz.open("/tmp/_corpus_dl.pdf")
        t = "\n".join(p.get_text() for p in doc); doc.close()
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n\n", t)
        return t.strip()
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


def already(citation_like):
    import psycopg2
    c = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"); cur = c.cursor()
    cur.execute("SELECT count(*) FROM legal_chunks WHERE citation ILIKE %s", (f"%{citation_like}%",))
    n = cur.fetchone()[0]; cur.close(); c.close()
    return n


def main():
    force = "--force" in sys.argv
    for url, cite, title, forum in CORPUS:
        # de-dup on the FULL citation, not a broad key — multi-part codes (the Rules of Court books) all
        # share "Rules of Court", so a broad key falsely skips later volumes once the first one is in.
        n_have = already(cite)
        if not force and n_have >= 30:
            print(f"  skip (already substantial): {cite}  [{n_have} chunks]"); continue
        try:
            txt = fetch(url)
        except Exception as e:
            print(f"  FETCH FAILED: {cite} — {e}"); continue
        if len(txt) < 4000:
            print(f"  SKIP (stub, {len(txt)} chars — find another source): {cite}"); continue
        open("/tmp/_corpus.txt", "w").write(txt)
        r = subprocess.run(["python3", "scripts/legal_authority.py", "--ingest", "--forum", forum,
                            "--citation", cite, "--title", title, "--source", url, "--file", "/tmp/_corpus.txt"],
                           cwd="/root/landtek", capture_output=True, text=True)
        print(f"  {('OK' if r.returncode==0 else 'ERR')}: {cite} ({len(txt):,} chars) — {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:80]}")


if __name__ == "__main__":
    main()
