#!/usr/bin/env python3
"""harvest_facts.py — FREE structured-fact accretion (no LLM, no quota, $0).

A large slice of "awareness" needs no model at all: title/lot numbers, dates, peso amounts, areas,
and known party names are STRUCTURED facts that regex pulls straight from the OCR'd text. This
harvests them per matter into matter_facts (grounded: source doc + verbatim excerpt), which moves
the awareness meter at zero cost and with no quota dependency — the LLM comprehension layer is then
reserved only for judgment (clean vs clouded, valuation, strategy). Idempotent (created_by='harvest').

  python3 harvest_facts.py --all --go
  python3 harvest_facts.py --matter MWK-CV26360 --go
"""
import re
import sys
import os

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

RE_TITLE = re.compile(r"\b(?:TCT|OCT)?[\s-]?(?:T|P|OCT)-\d{3,6}(?:-\d+)*\b", re.I)
RE_DATE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
RE_MONEY = re.compile(r"(?:₱|PHP|Php|P)\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\s*(?:pesos|PHP)\b", re.I)
RE_AREA = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:sq\.?\s?m\.?|square\s+meters?|hectares?|has?\.|sqm)\b", re.I)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("ALTER TABLE matter_facts ADD COLUMN IF NOT EXISTS created_by text")


def _ctx(text, m, pad=45):
    s = max(0, m.start() - pad); e = min(len(text), m.end() + pad)
    return re.sub(r"\s+", " ", text[s:e]).strip()


def _harvest_doc(text):
    """Return list of (fact_kind, statement, excerpt) — capped, deduped, high-value only."""
    out = []
    titles = sorted({m.group(0).upper().replace(" ", "").replace("TCT", "").replace("OCT", "").lstrip("-")
                     for m in RE_TITLE.finditer(text)})
    titles = [t for t in titles if re.search(r"\d{3,}", t)][:12]
    if titles:
        out.append(("reference", f"References title(s): {', '.join(titles)}", ", ".join(titles)))
    for kind, rx, lbl, cap in [("event", RE_DATE, "Dated reference", 3),
                               ("financial", RE_MONEY, "Amount", 2),
                               ("area", RE_AREA, "Area", 2)]:
        seen = set()
        for m in rx.finditer(text):
            v = m.group(0).strip()
            if v in seen:
                continue
            seen.add(v)
            out.append((kind, f"{lbl}: {v}", _ctx(text, m)))
            if len(seen) >= cap:
                break
    return out


def harvest_matter(cur, matter_code, go):
    cur.execute("""SELECT l.doc_id, d.extracted_text FROM document_matter_links l
                   JOIN documents d ON d.id=l.doc_id
                   WHERE l.matter_code=%s AND length(coalesce(d.extracted_text,''))>80""", (matter_code,))
    docs = cur.fetchall()
    n = 0
    if go:
        cur.execute("DELETE FROM matter_facts WHERE matter_code=%s AND created_by='harvest'", (matter_code,))
    for d in docs:
        for kind, stmt, excerpt in _harvest_doc(d["extracted_text"]):
            n += 1
            if go:
                cur.execute("""INSERT INTO matter_facts
                    (matter_code, statement, fact_kind, source_kind, source_id, excerpt, provenance_level, created_by, created_at)
                    VALUES (%s,%s,%s,'doc',%s,%s,'inferred_strong','harvest', now())""",
                    (matter_code, stmt[:500], kind, str(d["doc_id"]), excerpt[:400]))
    return n, len(docs)


def run(matter=None, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    if matter:
        codes = [matter]
    else:
        cur.execute("SELECT matter_code FROM matters ORDER BY matter_code")
        codes = [r["matter_code"] for r in cur.fetchall()]
    tot_f = tot_d = 0
    for mc in codes:
        nf, nd = harvest_matter(cur, mc, go)
        tot_f += nf; tot_d += nd
        if nf:
            print(f"  {mc:<26} {nf} facts from {nd} docs")
    print(f"[harvest] {'WROTE' if go else 'DRY'} matters={len(codes)} facts={tot_f} (FREE — no LLM)")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    run(matter=(a[a.index("--matter") + 1] if "--matter" in a else None), go="--go" in a)
