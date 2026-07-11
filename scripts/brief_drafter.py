#!/usr/bin/env python3
"""brief_drafter.py — resident agent: draft work-product grounded in the VERIFIED corpus. Local-LLM ($0).

Drafts a demand letter / case summary / position section for a matter using ONLY its verified facts.
Anything needed but not in the verified record is marked '[PENDING VERIFICATION]' rather than invented
— the same discipline as Leo's answer gate, applied to drafting. Output is a DRAFT (stored in
matter_drafts, clearly labeled), for the operator/counsel to finalize — never filed automatically.
Runs on the in-house Ollama tier (sovereign, unlimited, $0).

  python3 scripts/brief_drafter.py --matter MWK-CV26360 --type summary [--go]
      --type: summary | demand | position
"""
import json
import os
import sys
import urllib.request
import urllib.error

import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
OLLAMA_MODEL = os.environ.get("DRAFTER_OLLAMA_MODEL", os.environ.get("VERIFY_WORKER_OLLAMA_MODEL", "qwen2.5:7b-instruct"))

KINDS = {
    "summary": "a concise CASE SUMMARY (parties, the dispute, the key chain of facts, current posture)",
    "demand": "a DEMAND LETTER (state the right, the wrong, the demand, and a deadline)",
    "position": "a POSITION STATEMENT arguing the matter on the verified facts",
}
PROMPT = """You are drafting {kind} for a Philippine property matter, for review by counsel (NOT for
filing). Use ONLY the VERIFIED FACTS below (each tagged [id]). State a fact only if a listed fact
supports it, and reference the [id]. Where something is legally needed but NOT in the verified record,
write '[PENDING VERIFICATION: ...]' instead of inventing it. Be precise and professional.

VERIFIED FACTS:
"""


def _ollama(prompt):
    body = {"model": OLLAMA_MODEL, "stream": False, "options": {"temperature": 0.3}, "prompt": prompt}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read()).get("response", "").strip()
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None


def _projected_facts(cur, mc):
    """A75: pull this matter's verified fact work-slice through the brief-drafter RecipientProfile
    (WHO=A5 wall in-query · MACHINE handles intact · PULL_COMPLETE) — no raw un-projected fact read."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "leo_tools"))
    from recipient_projection import project_fact_slice
    return [(f["fact_id"], f["statement"])
            for f in project_fact_slice(cur, "brief-drafter", mc)
            if f["provenance_level"] == "verified"]


def main():
    a = sys.argv
    if "--matter" not in a:
        print(__doc__); return
    mc = a[a.index("--matter") + 1]
    kind = a[a.index("--type") + 1] if "--type" in a else "summary"
    if kind not in KINDS:
        print(f"--type must be one of {list(KINDS)}"); return
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    # A70 incorporation gate (fail-closed): never draft on a thin / gap-blind base. The verdict is
    # recorded (incorporation_verdicts) so the truth-floor can assert no emitter ships un-gated.
    from incorporation_gate import require_incorporation
    v = require_incorporation(cur, mc, stakeholder="counsel", purpose=f"brief:{kind}")
    if v["verdict"] != "READY":
        print(f"[drafter] {mc}: incorporation gate → {v['verdict']} "
              f"(verified={v.get('verified_count')}) — NOT drafting on a base that can't ground it. "
              f"reasons: {v.get('reasons')}"); return
    facts = _projected_facts(cur, mc)   # A75: verified slice through the brief-drafter profile
    if not facts:
        print(f"[drafter] {mc}: no verified facts — nothing to draft from."); return
    corpus = "\n".join(f"[{i}] {s}" for i, s in facts)
    print(f"[drafter] {mc}: drafting {kind} from {len(facts)} verified facts via {OLLAMA_MODEL}…", flush=True)
    out = _ollama(PROMPT.replace("{kind}", KINDS[kind]) + corpus[:24000])
    if not out:
        print("[drafter] local model unavailable (Ollama down)"); return
    print("\n" + "=" * 72 + f"\nDRAFT {kind.upper()} — {mc}  (grounded in verified facts; DRAFT for counsel, not for filing)\n" + "=" * 72)
    print(out)
    if "--go" in a:
        cur.execute("""CREATE TABLE IF NOT EXISTS matter_drafts (
            id serial PRIMARY KEY, matter_code text, kind text, draft text, n_facts int, model text,
            created_at timestamptz DEFAULT now())""")
        cur.execute("INSERT INTO matter_drafts (matter_code,kind,draft,n_facts,model) VALUES (%s,%s,%s,%s,%s)",
                    (mc, kind, out, len(facts), OLLAMA_MODEL))
        print(f"\n[drafter] ✓ written to matter_drafts")


if __name__ == "__main__":
    main()
