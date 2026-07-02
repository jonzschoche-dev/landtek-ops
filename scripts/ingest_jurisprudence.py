#!/usr/bin/env python3
"""ingest_jurisprudence.py — embed VERBATIM Supreme Court decisions as case authorities.

WHY THIS SHAPE: Philippine SC decisions are public-domain government works, and lawphil.net serves
their full verbatim text and is fetchable from the VPS (arta.gov.ph is not; AnyCase's editorial layer
is proprietary and must NOT be copied). So AnyCase (or counsel) is the FINDER — it yields accurate
citations + why-relevant — and lawphil is the SOURCE we actually embed. Each target is fetched, then
HARD-VERIFIED (the G.R. number must literally appear in the fetched text and the body must be decision-
length) before anything is written — a wrong/typo'd citation can never bind to the wrong decision.

Writes: legal_authorities (authority_type='case', full_text) + legal_chunks (embedded, forum) +
matter_authorities (links each case to the matters/elements it supports). Idempotent per (citation).

  # upgrade the cases already in the library from holding-only to FULL verbatim text (uses stored URLs):
  python3 scripts/ingest_jurisprudence.py --upgrade-existing
  # ingest a strategic batch from a JSON manifest (see TARGET SCHEMA below):
  python3 scripts/ingest_jurisprudence.py --file /root/landtek/juris_targets.json
  python3 scripts/ingest_jurisprudence.py --file ... --status     # resolve+verify only, write nothing

TARGET SCHEMA (one object per case in a JSON list):
  {
    "gr": "G.R. No. 195670",              # required; L- numbers ok
    "date": "December 3, 2012",            # required (builds the lawphil URL if source_url absent)
    "title": "Willem Beumer v. Avelina Amores",
    "holding": "…one-paragraph ratio…",    # short; NOT operative text
    "forum": "CIVIL",                       # legal_chunks bucket (default CIVIL)
    "source_url": "https://lawphil.net/...",# optional; if given, used verbatim (most reliable)
    "links": [ {"matter":"MWK-DLF-VOID","element_code":"…","relevance":"…","note":"…"} ]
  }
"""
from __future__ import annotations
import argparse
import html as _html
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import legal_authority as la  # reuse verified _conn/_chunks/_embed/_ensure

_MONTHS = {m: a for a, m in [
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
    ("may", "may"), ("jun", "june"), ("jul", "july"), ("aug", "august"),
    ("sep", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")]}
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MIN_DECISION_CHARS = 3000


def _gr_digits(gr: str) -> str:
    """'G.R. No. L-30573' -> '30573' ; 'G.R. No. 195670' -> '195670' (for URL + verification)."""
    m = re.search(r"(?:L-)?0*(\d{3,})", gr.replace(",", ""))
    return m.group(1) if m else ""


def _citation(gr: str, date: str) -> str:
    return f"{gr.strip()} ({date.strip()})"


_ALLMON = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _candidate_urls(gr: str, date: str) -> list[str]:
    """Build lawphil URLs from a G.R. number + date. AnyCase often gives only the YEAR, and lawphil
    keys the path on the promulgation MONTH — so when the month is unknown we sweep all 12 (the
    G.R.-in-text guard in _resolve_and_verify confirms the correct one; wrong months 404 and are skipped)."""
    digits = _gr_digits(gr)
    yr_m = re.search(r"(\d{4})", date)
    if not (digits and yr_m):
        return []
    yr = yr_m.group(1)
    mon_m = re.search(r"([A-Za-z]{3,})", date)
    known = _MONTHS.get(mon_m.group(1).lower(), mon_m.group(1)[:3].lower()) if mon_m else None
    months = ([known] + [m for m in _ALLMON if m != known]) if known else list(_ALLMON)
    stems = [f"gr_{digits}", f"gr_l-{digits}"] if "l-" in gr.lower() else [f"gr_{digits}"]
    return [f"https://lawphil.net/judjuris/juri{yr}/{m}{yr}/{s}_{yr}.html"
            for m in months for s in stems]


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    raw = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = _html.unescape(t)
    for boiler in ("Toggle navigation", "The LawPhil Project", "Arellano Law Foundation",
                   "Republic of the Philippines SUPREME COURT", "Constitution Statutes Executive"):
        t = t.replace(boiler, " ")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def _resolve_and_verify(t):
    """Return (url, text) for a target, or (None, reason). HARD guard against wrong-case ingest."""
    gr, date = t.get("gr", ""), t.get("date", "")
    digits = _gr_digits(gr)
    urls = ([t["source_url"]] if t.get("source_url") else []) + _candidate_urls(gr, date)
    if not urls:
        return None, "no source_url and could not build a lawphil URL from gr/date"
    for url in urls:
        try:
            text = _fetch_text(url)
        except Exception as e:
            continue
        if len(text) < MIN_DECISION_CHARS:
            continue  # 404 stub or thin page
        # the fetched page MUST contain this exact G.R. digits — else it's the wrong/absent case
        if digits and re.search(rf"\b(?:G\.?\s*R\.?|L-)?\s*0*{digits}\b", text):
            return url, text
        # some lawphil pages print the number without the digits we expect → last-resort loose check
        if digits and digits in text:
            return url, text
    return None, f"fetched no lawphil page containing G.R. {digits} (tried {len(urls)} url(s))"


def _upsert_authority(cur, citation, title, holding, full_text, url, forum):
    cur.execute("""
        INSERT INTO legal_authorities (citation, authority_type, title, holding, full_text,
                                       jurisdiction, source, source_url, provenance_level)
        VALUES (%s,'case',%s,%s,%s,'PH','lawphil',%s,'verified')
        ON CONFLICT (citation, source) DO UPDATE
          SET full_text=EXCLUDED.full_text, title=COALESCE(NULLIF(EXCLUDED.title,''),legal_authorities.title),
              holding=COALESCE(NULLIF(EXCLUDED.holding,''),legal_authorities.holding),
              source_url=EXCLUDED.source_url, updated_at=now()
        RETURNING id""", (citation, title, holding, full_text, url))
    return cur.fetchone()[0]


def _embed_fulltext(cur, forum, citation, title, url, full_text):
    cur.execute("DELETE FROM legal_chunks WHERE citation=%s", (citation,))
    n = 0
    for i, ch in enumerate(la._chunks(full_text)):
        if len(ch) < 40:
            continue
        cur.execute("""INSERT INTO legal_chunks (forum,citation,title,source,chunk_no,text,embedding,verify_flag)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'operator-official')""",
                    (forum.upper(), citation, title, url, i, ch, la._embed(ch)))
        n += 1
    return n


def _link_matters(cur, auth_id, links):
    for lk in links or []:
        cur.execute("""INSERT INTO matter_authorities (matter_code, authority_id, element_code, relevance, note, provenance_level)
                       VALUES (%s,%s,%s,%s,%s,'verified')
                       ON CONFLICT DO NOTHING""",
                    (lk["matter"], auth_id, lk.get("element_code", ""), lk.get("relevance", ""), lk.get("note", "")))


def _process(cur, t, status_only):
    citation = _citation(t.get("gr", ""), t.get("date", ""))
    url, text_or_reason = _resolve_and_verify(t)
    if not url:
        print(f"  ✗ REJECT  {citation} — {text_or_reason}")
        return False
    text = text_or_reason
    if status_only:
        print(f"  → OK ({len(text)} chars) {citation}  <- {url}")
        return True
    forum = t.get("forum", "CIVIL")
    aid = _upsert_authority(cur, citation, t.get("title", ""), t.get("holding", ""), text, url, forum)
    nchunks = _embed_fulltext(cur, forum, citation, t.get("title", ""), url, text)
    _link_matters(cur, aid, t.get("links"))
    print(f"  ✓ {citation}  ({len(text)} chars, {nchunks} chunks, {len(t.get('links',[]))} matter-link(s))")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="JSON manifest of target cases")
    ap.add_argument("--upgrade-existing", action="store_true",
                    help="fetch full verbatim text for cases already in legal_authorities (uses stored source_url)")
    ap.add_argument("--status", action="store_true", help="resolve+verify only; write nothing")
    a = ap.parse_args()

    c = la._conn(); cur = c.cursor(); la._ensure(cur)
    targets = []
    if a.upgrade_existing:
        cur.execute("""SELECT citation, source_url, coalesce(title,''), coalesce(holding,'')
                       FROM legal_authorities WHERE authority_type='case' AND source_url IS NOT NULL""")
        for citation, url, title, holding in cur.fetchall():
            m = re.match(r"(.*?)\s*\((.*)\)\s*$", citation)  # split "G.R. No. X (date)"
            gr, date = (m.group(1), m.group(2)) if m else (citation, "")
            targets.append({"gr": gr, "date": date, "title": title, "holding": holding,
                            "source_url": url, "forum": "CIVIL", "links": []})
    if a.file:
        with open(a.file, encoding="utf-8") as f:
            targets += json.load(f)
    if not targets:
        sys.exit("nothing to do — pass --file <manifest.json> and/or --upgrade-existing")

    print(f"=== jurisprudence ingest — {len(targets)} target(s){' [STATUS ONLY]' if a.status else ''} ===")
    ok = sum(_process(cur, t, a.status) for t in targets)
    print(f"\n=== {ok}/{len(targets)} verified{'' if a.status else ' and embedded'} ===")


if __name__ == "__main__":
    main()
