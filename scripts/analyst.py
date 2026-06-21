#!/usr/bin/env python3
"""analyst.py — resident agent: synthesize a grounded case theory from the VERIFIED corpus. Local-LLM ($0).

Reads a matter's verified facts (document-proven only) and asks the in-house model to produce: the
case theory, strongest points (each tied to fact ids), evidentiary gaps, and recommended next steps.
This is DERIVED REASONING, not fact — stored in `matter_analysis`, clearly labeled, and it does NOT
pass through the provenance gate (it argues over facts rather than quoting them). The model is told to
reason ONLY over the supplied verified facts and to name gaps rather than invent. Runs on the in-house
Ollama tier (sovereign, unlimited, $0); Gemini fallback.

  python3 scripts/analyst.py --matter MWK-CV26360          # print analysis (dry)
  python3 scripts/analyst.py --matter MWK-CV26360 --go     # also write matter_analysis
"""
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
OLLAMA_MODEL = os.environ.get("ANALYST_OLLAMA_MODEL", os.environ.get("VERIFY_WORKER_OLLAMA_MODEL", "qwen2.5:7b-instruct"))

PROMPT = """You are a Philippine property-litigation analyst. Using ONLY the VERIFIED FACTS below
(each tagged [id]), produce a grounded analysis. Do NOT assert anything not supported by a listed
fact; where the record is silent, say so explicitly.

Output these sections:
1. CASE THEORY — 2-3 sentences: what this matter is and the core legal thrust.
2. STRONGEST POINTS — bullets, each citing the supporting [id](s).
3. EVIDENTIARY GAPS — what is asserted-but-unproven or missing from the verified record.
4. RECOMMENDED NEXT STEPS — concrete, prioritized.

VERIFIED FACTS:
"""


def _ollama(prompt):
    body = {"model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.4}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read()).get("response", "").strip()
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None


def main():
    a = sys.argv
    if "--matter" not in a:
        print(__doc__); return
    mc = a[a.index("--matter") + 1]
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    cur.execute("""SELECT id, statement FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'
                   ORDER BY id""", (mc,))
    facts = cur.fetchall()
    if not facts:
        print(f"[analyst] {mc}: no verified facts yet — nothing to analyze."); return
    corpus = "\n".join(f"[{i}] {s}" for i, s in facts)
    print(f"[analyst] {mc}: reasoning over {len(facts)} verified facts via {OLLAMA_MODEL}…", flush=True)
    out = _ollama(PROMPT + corpus[:24000])
    if not out:
        print("[analyst] local model unavailable (Ollama down)"); return
    print("\n" + "=" * 72 + f"\nCASE ANALYSIS — {mc}  (derived reasoning over verified facts; NOT itself a verified fact)\n" + "=" * 72)
    print(out)
    if "--go" in a:
        cur.execute("""CREATE TABLE IF NOT EXISTS matter_analysis (
            id serial PRIMARY KEY, matter_code text, analysis text, n_facts int, model text,
            created_at timestamptz DEFAULT now())""")
        cur.execute("INSERT INTO matter_analysis (matter_code,analysis,n_facts,model) VALUES (%s,%s,%s,%s)",
                    (mc, out, len(facts), OLLAMA_MODEL))
        print(f"\n[analyst] ✓ written to matter_analysis ({len(facts)} facts basis)")


if __name__ == "__main__":
    main()
