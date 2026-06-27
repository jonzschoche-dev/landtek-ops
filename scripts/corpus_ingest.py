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
    ("https://lawphil.net/statutes/presdecs/pd1977/pd_1096_1977.html", "PD 1096 (National Building Code, full)", "National Building Code — full text", "ARTA"),
    ("https://lawphil.net/executive/execord/eo1987/eo_292_1987.html", "EO 292 (Administrative Code of 1987, full)", "Administrative Code of 1987 — full text", "DILG"),
]
SSH_PSQL = "docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "ignore")
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
        key = re.search(r"(RA|PD|EO|Act)\s*\d+|Constitution", cite).group(0)
        if not force and already(key) >= 30:
            print(f"  skip (already substantial): {cite}  [{already(key)} chunks]"); continue
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
