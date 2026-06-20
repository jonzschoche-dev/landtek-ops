#!/usr/bin/env python3
"""verify_worker.py — the autonomous reader that continuously grows the verifiable corpus. $0 (Gemini).

verify_loop POINTS (ranks the next legible source docs to read); this worker READS them. For each
doc it sends the OCR text to Gemini (free-tier key×model ladder = creditless re: Anthropic), asks for
atomic factual claims each with a VERBATIM contiguous quote, and writes them through the HARDENED
provenance gate. A claim becomes 'verified' ONLY if its quote is a real substring of the cited
document (excerpt_grounded). The gate is the guarantee: even a hallucinating model cannot land an
ungrounded verified fact. Claims it surfaces but cannot ground go to `proposed_facts` for human
review — never auto-verified.

Attempt-tracked (verify_worker_log, 14-day cooldown) so a doc that yields nothing isn't re-read
forever; rate-limited to free-tier. Run a few docs per tick from a timer (= continuous) or --loop.

  python3 scripts/verify_worker.py --limit 2 --dry     # show what it WOULD write (no DB writes)
  python3 scripts/verify_worker.py --limit 5 --go      # read 5 docs, write grounded facts
  python3 scripts/verify_worker.py --loop --go         # continuous, paced
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_loop import doc_worklist

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
GEMINI_KEYS = [k for k in (os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_API_KEY_FALLBACK", "")) if k]
# flash-lite first: it carries a SEPARATE free-tier quota from flash/2.0-flash (which are often the
# first exhausted by the OCR/embed jobs sharing this key). Ladder falls through on 429.
MODELS = [m.strip() for m in os.environ.get(
    "VERIFY_WORKER_MODELS", "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-2.0-flash").split(",") if m.strip()]
MIN_CONF = float(os.environ.get("VERIFY_WORKER_MIN_CONF", "0.55"))
COOLDOWN_DAYS = 14

PROMPT = """You are reading the OCR text of a legal document in matter {matter} (a Philippine
property/land case). Extract up to 6 ATOMIC factual claims this document PROVES — parties and their
roles, dates, amounts, case identity/caption, rulings/dispositions, obligations, admissions.

For EACH claim return an object with:
- "statement": one self-contained sentence stating the fact (a faithful paraphrase).
- "excerpt": a CONTIGUOUS quote copied CHARACTER-FOR-CHARACTER from the text below (at least ~8 words),
  that proves the statement. Do NOT alter, summarize, translate, or join pieces with "...". It MUST
  appear verbatim in the text.
- "confidence": 0.0-1.0.

Only include a claim if you can supply a verbatim excerpt that is actually present in the text.
Return ONLY JSON: {"facts":[ ... ]}."""


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS verify_worker_log (
        doc_id int, attempted_at timestamptz DEFAULT now(), n_verified int, n_proposed int, status text)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS proposed_facts (
        id serial PRIMARY KEY, matter_code text, statement text, excerpt text, source_doc_id int,
        confidence numeric, created_by text DEFAULT 'verify_worker', created_at timestamptz DEFAULT now(),
        status text DEFAULT 'pending', UNIQUE(matter_code, statement))""")


def _gemini(text, matter):
    body = {"contents": [{"parts": [{"text": PROMPT.replace("{matter}", matter) + "\n\nTEXT:\n" + text[:16000]}]}],
            "generationConfig": {"temperature": 0, "response_mime_type": "application/json"}}
    for key in GEMINI_KEYS:
        for model in MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={"content-type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    out = json.loads(r.read())
                raw = "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"])
                return json.loads(raw).get("facts", [])
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(1); continue
                raise
            except (json.JSONDecodeError, KeyError, IndexError):
                return []
    return None  # all combos 429 → quota exhausted


def _next_docs(cur, limit):
    """Breadth-fair: build out EVERY acknowledged matter, not just the flagship. Round-robin one doc
    per matter per round, matters ordered by current verified-fact count ASC (most-neglected first),
    each matter's docs in priority order. So a 0-fact matter gets read before CV-26360's 80th fact."""
    work = doc_worklist(cur)
    cur.execute(f"SELECT DISTINCT doc_id FROM verify_worker_log WHERE attempted_at > now() - interval '{COOLDOWN_DAYS} days'")
    recent = {r["doc_id"] for r in cur.fetchall()}
    work = [w for w in work if w["id"] not in recent]
    if not work:
        return []
    cur.execute("SELECT matter_code, count(*) c FROM matter_facts WHERE provenance_level='verified' GROUP BY matter_code")
    vcount = {r["matter_code"]: r["c"] for r in cur.fetchall()}
    bym = {}
    for w in work:
        bym.setdefault(w["matter_code"], []).append(w)
    matters = sorted(bym, key=lambda m: vcount.get(m, 0))  # most-neglected matter first
    picked = []
    while len(picked) < limit:
        progressed = False
        for m in matters:
            if bym[m] and len(picked) < limit:
                picked.append(bym[m].pop(0)); progressed = True
        if not progressed:
            break
    return picked


def process_doc(cur, w, go):
    cur.execute("SELECT extracted_text FROM documents WHERE id=%s", (w["id"],))
    text = (cur.fetchone() or {}).get("extracted_text") or ""
    if len(text) < 200:
        return {"doc": w["id"], "skip": "too short"}
    facts = _gemini(text, w["matter_code"])
    if facts is None:
        raise RuntimeError("gemini quota exhausted")
    nv = npr = 0; shown = []
    for f in (facts or []):
        stmt = (f.get("statement") or "").strip()
        exc = (f.get("excerpt") or "").strip()
        conf = float(f.get("confidence") or 0)
        if not stmt or not exc:
            continue
        cur.execute("SELECT excerpt_grounded(%s,%s)", (exc, str(w["id"])))
        grounded = cur.fetchone()["excerpt_grounded"]
        verdict = "verified" if (grounded and conf >= MIN_CONF) else ("proposed" if conf >= MIN_CONF else "drop")
        shown.append((verdict, "G" if grounded else "-", round(conf, 2), stmt[:70]))
        if not go or verdict == "drop":
            continue
        if verdict == "verified":
            cur.execute("SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s", (w["matter_code"], stmt))
            if cur.fetchone():
                continue
            try:
                cur.execute("""INSERT INTO matter_facts (matter_code,statement,fact_kind,source_kind,source_id,
                    excerpt,provenance_level,confidence,created_by,created_at)
                    VALUES (%s,%s,'auto_read','doc',%s,%s,'verified',%s,'verify_worker',now())""",
                    (w["matter_code"], stmt, str(w["id"]), exc, conf)); nv += 1
            except psycopg2.Error:
                verdict = "proposed"  # gate refused (not grounded after all) → fall through to review
        if verdict == "proposed":
            cur.execute("""INSERT INTO proposed_facts (matter_code,statement,excerpt,source_doc_id,confidence)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (matter_code,statement) DO NOTHING""",
                (w["matter_code"], stmt, exc, w["id"], conf)); npr += 1
    if go:
        cur.execute("INSERT INTO verify_worker_log (doc_id,n_verified,n_proposed,status) VALUES (%s,%s,%s,%s)",
                    (w["id"], nv, npr, "ok"))
    return {"doc": w["id"], "matter": w["matter_code"], "verified": nv, "proposed": npr, "shown": shown}


def run(limit, go, loop, rpm):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    total_v = total_p = 0
    while True:
        docs = _next_docs(cur, limit)
        if not docs:
            print("[worker] worklist empty (all legible docs read or in cooldown)"); break
        for w in docs:
            try:
                r = process_doc(cur, w, go)
            except RuntimeError:
                print("[worker] Gemini quota exhausted — resume on reset"); loop = False; break
            total_v += r.get("verified", 0); total_p += r.get("proposed", 0)
            tag = f"+{r.get('verified',0)}v/{r.get('proposed',0)}p" if go else "(dry)"
            print(f"  doc:{r['doc']} [{r.get('matter','?')}] {tag}", flush=True)
            for verdict, g, conf, s in r.get("shown", []):
                print(f"      [{verdict:8} {g} c={conf}] {s}", flush=True)
            if rpm > 0:
                time.sleep(60.0 / rpm)
        if not loop:
            break
    print(f"[worker] done — verified+{total_v}, proposed+{total_p}")


if __name__ == "__main__":
    a = sys.argv
    run(limit=int(a[a.index("--limit") + 1]) if "--limit" in a else 5,
        go="--go" in a, loop="--loop" in a,
        rpm=int(a[a.index("--rpm") + 1]) if "--rpm" in a else 6)
