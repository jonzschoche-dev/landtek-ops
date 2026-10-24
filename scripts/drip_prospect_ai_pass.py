#!/usr/bin/env python3
"""drip_prospect_ai_pass.py — read every MWK document with the LOCAL model and add what it finds as prospects.

Jonathan, 23 Oct 2026: "run the AI pass over all MWK documents with the local model (no outside service), adding what
it finds as prospects". Runs on the MAC (Ollama, qwen2.5 14B). It calls Ollama directly — never model_router.py,
whose fallback tiers are outside services. If Ollama is down, the pass stops; it never falls back.

Hallucination guard: every finding must carry a verbatim quote from the document; a finding whose quote is not found
in the text (whitespace/case-normalized) is dropped. Lanes are assigned by rule, not by the model, so the drip only
ever receives follow-ups (records asks, replies owed); positions go to the legal desk, litigation items to counsel.
Resumable: drip_prospect_scan records each document done.

  python3 scripts/drip_prospect_ai_pass.py [--limit N] [--doc ID] [--model qwen2.5:14b-instruct] [--dry-run]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import psycopg2
import psycopg2.extras
import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from drip_board import load_priorities  # noqa: E402

from _pgdsn import dsn as _pgdsn  # noqa: E402
DSN = _pgdsn("127.0.0.1:15432")
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
CHUNK = 6000
MAX_CHUNKS = 2
KINDS = {"records_request": ("drip", 55), "reply_owed_by_office": ("drip", 60), "office_asks_us": ("drip", 65),
         "office_duty_unperformed": ("legal_desk", 45), "money_owed": ("legal_desk", 55), "deadline": ("legal_desk", 60),
         "occupant_or_encroachment": ("hold", 30), "contradiction": ("legal_desk", 40), "litigation_step": ("counsel", 45)}
NOT_MWK = re.compile(r"(?i)paracale|inocalla|capacuan|nibdc|gracesen")

PROMPT = """You read one document from the case file of the Heirs of Mary Worrick Keesey (estate land in Mercedes and
Daet, Camarines Norte, Philippines; TCT T-4497 and derivative titles; client acts through Jonathan Paul Zschoche,
attorney-in-fact of co-owner Patricia Keesey Zschoche).

List ACTIONABLE PROSPECTS this document reveals: things the estate could still do or obtain. Only these kinds:
- records_request: a specific record a named government office holds that the estate does not yet have
- reply_owed_by_office: an office received our request and has not answered or acted
- office_asks_us: an office asks the estate to pay, submit, comply or acknowledge something
- office_duty_unperformed: an official duty (registration, assessment, permit, release) not done
- money_owed: money owed to the estate (compensation, rent, refund) with its basis
- deadline: a dated deadline or period that still matters
- occupant_or_encroachment: someone occupying or building on estate land
- contradiction: two records that disagree on a fact that matters
- litigation_step: a step in a court case (subpoena, filing, testimony)

Rules: only what THIS document shows; no guessing; nothing already completed. Each item MUST include "quote": an exact
sentence or phrase copied word for word from the document that supports it. If there is nothing actionable, return
{"items": []}. Return JSON only:
{"items":[{"kind":"...","title":"<= 20 words, specific","office":"office or person, or null","quote":"exact words"}]}

DOCUMENT #{doc_id} — {title}
---
{text}
---"""


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).lower().encode()).hexdigest()[:24]


def ask(model, prompt):
    r = requests.post(f"{OLLAMA}/api/generate", json={"model": model, "prompt": prompt, "format": "json", "stream": False,
                                                      "options": {"temperature": 0.1, "num_ctx": 8192}}, timeout=600)
    r.raise_for_status()
    return json.loads(r.json().get("response") or "{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--doc", type=int)
    ap.add_argument("--model", default="qwen2.5:14b-instruct")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    requests.get(f"{OLLAMA}/api/tags", timeout=5).raise_for_status()   # local model must be up; no fallback
    c = psycopg2.connect(DSN)
    c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""CREATE TABLE IF NOT EXISTS drip_prospect_scan (doc_id integer PRIMARY KEY, model text, scanned_at timestamptz
                   DEFAULT now(), found integer, kept integer, error text)""")
    weights = {k: v.get("weight", 5) for k, v in load_priorities().get("matters", {}).items()}
    where = ["(d.case_file LIKE 'MWK%%' OR d.matter_code LIKE 'MWK%%')", "length(coalesce(d.extracted_text,'')) >= 200",
             "coalesce(d.ingest_source,'') <> 'strategy_desk'",
             # court papers and our own drafts: their "asks" are ours or counsel's (triage R2b, 23 Oct 2026)
             # our own papers: our letters signed as attorney-in-fact, playbooks, dossiers (triage R2c)
             "coalesce(d.document_title, d.original_filename, '') !~* '^(zschoche_|mwk[-_]|master_|complete_)|playbook|dossier|tracker|steering|work.?product|briefing|red.?team|directive|binder|hearing.?card|strategy'",
             "NOT (coalesce(d.document_title,'') !~* '^email' AND coalesce(d.extracted_text,'') ~* 'attorney-in-fact (for|of) patricia keesey zschoche' AND coalesce(d.extracted_text,'') !~* 'dear (mr\\.?|sir|mister) (jonathan |paul )*zschoche')",
             "coalesce(d.doc_role,'') NOT IN ('pleading','order_resolution','prime_evidence')",
             "coalesce(d.document_title, d.original_filename, '') !~* '(draft|complaint|exhibit|affidavit|petition|motion|manifestation|rejoinder|pleading)'",
             # our own outgoing e-mails: the model would read our asks as the office's demands
             "NOT (coalesce(d.document_title,'') ILIKE 'EMAIL%%' AND left(d.extracted_text, 400) ~* 'From: [^\\n]*(zschoche|hayuma)')",
             "NOT EXISTS (SELECT 1 FROM drip_prospect_scan s WHERE s.doc_id = d.id AND s.error IS NULL)"]
    args = []
    if a.doc:
        where = ["d.id = %s"]; args = [a.doc]
    cur.execute(f"""SELECT d.id, coalesce(d.document_title, d.smart_filename, d.original_filename, '') AS title,
                           coalesce(d.matter_code, d.case_file) AS matter, d.extracted_text AS text
                      FROM documents d WHERE {' AND '.join(where)} ORDER BY d.id DESC {'LIMIT %s' if a.limit else ''}""",
                args + ([a.limit] if a.limit else []))
    docs = cur.fetchall()
    print(f"{len(docs)} document(s) to read with {a.model}", flush=True)
    tot_kept = 0
    for n, d in enumerate(docs, 1):
        t0 = time.time()
        text = d["text"] or ""
        chunks = [text[i:i + CHUNK] for i in range(0, min(len(text), CHUNK * MAX_CHUNKS), CHUNK)]
        found = kept = 0
        err = None
        try:
            for ch in chunks:
                out = ask(a.model, PROMPT.replace("{doc_id}", str(d["id"])).replace("{title}", d["title"][:150]).replace("{text}", ch))
                items = out.get("items") if isinstance(out, dict) else None
                for it in items or []:
                    found += 1
                    kind = it.get("kind")
                    q = norm(it.get("quote"))
                    title = (it.get("title") or "").strip()
                    if kind not in KINDS or len(q) < 12 or q not in norm(ch) or not title or NOT_MWK.search(title + q):
                        continue   # unsupported kind, or the quote is not in the document: dropped
                    lane, base = KINDS[kind]
                    matter = d["matter"] or "MWK-001"
                    if matter.startswith("MWK-CV26360"):
                        lane = "counsel"   # everything in the trial file goes through Barandon (Charter §5, X17)
                    w = weights.get(matter, weights.get("MWK-001", 5))
                    kept += 1
                    if a.dry_run:
                        print(f"   + [{lane}] {kind}: {title[:100]}  «{it.get('quote','')[:80]}»")
                        continue
                    cur.execute("""INSERT INTO drip_prospect (client_code, matter_code, kind, title, detail, office, lane, score,
                                          source_kind, source_ref, excerpt, evidence_doc_ids, dedupe_key)
                                   VALUES ('MWK-001',%s,%s,%s,%s,%s,%s,%s,'doc',%s,%s,%s,%s)
                                   ON CONFLICT (dedupe_key) DO UPDATE SET last_seen=now()""",
                                (matter, f"ai:{kind}", title[:200], f"{title}\nQuote: {it.get('quote')}"[:1500], it.get("office"),
                                 lane, round(base * w / 10, 1), f"documents:{d['id']}", (it.get("quote") or "")[:500], [d["id"]],
                                 key("ai", d["id"], norm(title)[:120])))
        except Exception as e:  # one bad document never stops the pass
            err = str(e)[:300]
        if not a.dry_run:
            cur.execute("""INSERT INTO drip_prospect_scan (doc_id, model, found, kept, error) VALUES (%s,%s,%s,%s,%s)
                           ON CONFLICT (doc_id) DO UPDATE SET model=EXCLUDED.model, scanned_at=now(), found=EXCLUDED.found,
                                  kept=EXCLUDED.kept, error=EXCLUDED.error""", (d["id"], a.model, found, kept, err))
        tot_kept += kept
        print(f"[{n}/{len(docs)}] doc {d['id']} {d['title'][:60]!r}: {found} found, {kept} kept"
              + (f" ERROR {err}" if err else "") + f" ({time.time() - t0:.0f}s)", flush=True)
    print(f"done: {tot_kept} prospect(s) kept from {len(docs)} document(s)")
    if not a.dry_run:   # route what we just added (already handled / counsel / our own papers)
        import subprocess
        subprocess.run([sys.executable, os.path.join(REPO, "scripts", "drip_prospect_triage.py")])


if __name__ == "__main__":
    main()
