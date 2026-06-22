#!/usr/bin/env python3
"""relevance_triage.py — FAST keep/drop relevance decision over linked docs. $0 (local model).

The text is ALREADY in the corpus, so deciding whether a linked doc is even relevant to its matter is
one quick local-LLM call — far cheaper than the full fact-extraction grind. This triages the AMBIGUOUS
linked docs (no verified facts for the matter AND no docket-token match — the "NOSIG" bucket) into
RELEVANT (→ leave linked, queue for source-read) or NOT (→ unlink candidate), writing the verdict to
`doc_relevance_triage`. The deep fact-read then runs only on the keepers; the noise is surfaced for the
operator-authorized unlink. Clear cases (already have facts, or carry the docket) are skipped — they're
known-relevant.

  python3 scripts/relevance_triage.py MWK-ARTA-1319            # preview one matter's ambiguous links
  python3 scripts/relevance_triage.py MWK-ARTA-1319 --apply    # write verdicts
  python3 scripts/relevance_triage.py --all --apply            # triage every matter
"""
import json
import os
import re
import sys
import urllib.request

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matter_readiness import _tokens

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("VERIFY_WORKER_OLLAMA_MODEL", "qwen2.5:7b-instruct")
IMG = re.compile(r"\.(png|jpe?g|gif|bmp|tiff?|webp)$", re.I)
_SCHEMA = {"type": "object",
           "properties": {"relevant": {"type": "boolean"}, "reason": {"type": "string"}},
           "required": ["relevant", "reason"]}


def _llm(prompt):
    body = {"model": MODEL, "stream": False, "options": {"temperature": 0.1}, "format": _SCHEMA, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        try:
            return json.loads(json.loads(r.read())["response"])
        except Exception:
            return None


def _toks(docket, title, mc):
    t = list(_tokens(docket, title))
    m = re.search(r"-(\d{3,5})$", mc)
    if m:
        t.append(m.group(1))
    return t or ["~nomatch~"]


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS doc_relevance_triage (
        doc_id int, matter_code text, relevant bool, reason text, model text,
        decided_at timestamptz DEFAULT now(), UNIQUE(doc_id, matter_code))""")


def _profile(cur, mc):
    cur.execute("SELECT title, coalesce(forum,court_or_agency,''), coalesce(docket_number,'') FROM matters WHERE matter_code=%s", (mc,))
    row = cur.fetchone()
    if not row:
        return None
    title, forum, docket = row
    cur.execute("""SELECT statement FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY id LIMIT 5""", (mc,))
    facts = " | ".join(r[0][:160] for r in cur.fetchall())
    prof = f"MATTER {mc}: {title} (forum: {forum}; docket: {docket}). What it is about: {facts or '(no facts yet)'}"
    return prof, _toks(docket, title, mc)


def candidates(cur, mc, toks):
    """Ambiguous linked docs: no facts for THIS matter, no docket-token, legible, not an image."""
    cur.execute("""SELECT d.id, coalesce(d.original_filename,d.smart_filename,'?') fn, left(coalesce(d.extracted_text,''),1600) txt
        FROM documents d
        WHERE (d.matter_code=%s OR d.id IN (SELECT doc_id FROM document_matter_links WHERE matter_code=%s))
          AND length(coalesce(d.extracted_text,'')) >= 400
          AND NOT EXISTS (SELECT 1 FROM matter_facts f WHERE f.provenance_level='verified' AND f.source_kind='doc'
                          AND f.source_id=d.id::text AND f.matter_code=%s)
          AND NOT EXISTS (SELECT 1 FROM doc_relevance_triage t WHERE t.doc_id=d.id AND t.matter_code=%s)
        """, (mc, mc, mc, mc))
    out = []
    for did, fn, txt in cur.fetchall():
        if IMG.search(fn or ""):
            continue
        blob = (txt + " " + fn).lower()
        if any(t.lower() in blob for t in toks):   # carries the docket → known-relevant, skip triage
            continue
        out.append((did, fn, txt))
    return out


def triage(cur, mc, apply=False):
    pr = _profile(cur, mc)
    if not pr:
        return None
    prof, toks = pr
    cand = candidates(cur, mc, toks)
    rel = irr = 0
    for did, fn, txt in cand:
        v = _llm(f"You are triaging whether a document is relevant to a specific legal matter. {prof}\n\n"
                 f"DOCUMENT (id {did}, '{fn}'):\n{txt}\n\n"
                 f"Is this document relevant to THIS matter — does it concern the same complaint, parties, "
                 f"acts, or relief? Answer strictly about THIS matter (not the broader estate). "
                 f"JSON: {{\"relevant\": true/false, \"reason\": \"one short clause\"}}")
        if v is None:
            continue
        ok = bool(v.get("relevant"))
        rel += ok; irr += (not ok)
        mark = "KEEP" if ok else "DROP"
        print(f"  {mark}  doc:{did:>5}  {fn[:46]:46}  — {str(v.get('reason',''))[:60]}")
        if apply:
            cur.execute("""INSERT INTO doc_relevance_triage (doc_id, matter_code, relevant, reason, model)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (doc_id,matter_code)
                DO UPDATE SET relevant=excluded.relevant, reason=excluded.reason, decided_at=now()""",
                (did, mc, ok, str(v.get("reason", ""))[:300], MODEL))
    return {"mc": mc, "cand": len(cand), "relevant": rel, "irrelevant": irr}


def main():
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    ensure(cur)
    apply = "--apply" in sys.argv
    if "--all" in sys.argv:
        cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE 'MWK-%' ORDER BY matter_code")
        mats = [r[0] for r in cur.fetchall()]
    else:
        arg = next((a for a in sys.argv[1:] if not a.startswith("-")), "MWK-ARTA-1319")
        mats = [arg]
    tot_r = tot_i = 0
    for mc in mats:
        print(f"\n=== {mc} ===")
        r = triage(cur, mc, apply)
        if r:
            print(f"  → {r['relevant']} relevant, {r['irrelevant']} not-relevant of {r['cand']} ambiguous"
                  + ("" if apply else "  (preview — use --apply to record)"))
            tot_r += r["relevant"]; tot_i += r["irrelevant"]
    if len(mats) > 1:
        print(f"\nTOTAL: {tot_r} keep · {tot_i} unlink-candidates across {len(mats)} matters")


if __name__ == "__main__":
    main()
