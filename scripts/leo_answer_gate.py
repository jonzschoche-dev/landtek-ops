#!/usr/bin/env python3
"""leo_answer_gate.py — deterministic discernment gate on Leo's replies. $0, no LLM.

WHY (operator, 2026-06-16): "an architecture that makes LEO THINK and not INFER; with facts he
must be discerning; anything less is a waste." Prompting Leo to be careful is not enough — the
model will still infer. This gate makes discernment ENFORCEABLE: it runs on a candidate reply
BEFORE it ships and refuses claims that aren't grounded. A confident ungrounded answer is worse
than "I don't know" — so the gate blocks it.

Deterministic checks (no LLM, runs in milliseconds):
  1. CITATION RESOLUTION — every doc:N the reply cites must resolve to a real `documents` row.
     A cite to a non-existent doc = FABRICATED CITATION → FAIL. A real doc with no verified
     `matter_facts` fact behind it = WARN (cited a doc we haven't verified into the fact base).
  2. CASCADE GROUNDING — if the reply asserts a cascade (X void → Y void, "all 20 transferees",
     "cascades to"), a supporting `keystones` row must exist. An asserted cascade with no
     keystone = UNGROUNDED CASCADE → FAIL (this is the exact class that hallucinates legal theory).
  3. UNGROUNDED-ASSERTION HEURISTIC — a sentence carrying fact-signals (title nos, dates, "void",
     "revoked", "registered to", money) but NO citation = WARN. Soft, because NL can't be parsed
     perfectly — but it surfaces the model stating facts it didn't cite.

Verdict: {"verdict": "pass"|"fail", "fails": [...], "warns": [...]}.
In the n8n flow: verdict=fail → block the send / regenerate with the issues fed back; warns → annotate.

  python3 scripts/leo_answer_gate.py --text "<reply>" [--json]
  echo "<reply>" | python3 scripts/leo_answer_gate.py
Importable: gate(cur, text) -> dict.
"""
import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# doc citation forms Leo / the corpus use: doc:246, doc#246, doc 246, [doc:246], document 246
CITE_RE = re.compile(r"\bdoc(?:ument)?\s*[:#]?\s*(\d{1,6})\b", re.I)
# phrases that assert a cross-matter cascade / sweeping legal consequence
CASCADE_RE = re.compile(
    r"\b(cascad\w+|all\s+\d*\s*transferees?|every\s+(?:deed|title|instrument)|"
    r"void\s+ab\s+initio|the\s+(?:whole|entire)\s+chain|knocks?\s+out|falls?\s+with)\b", re.I)
# fact-signal patterns: if a sentence has one of these it is making a factual claim
FACT_SIGNAL_RE = re.compile(
    r"(\bT-\d{3,}\b|\b0?79-\d{6,}\b|\bP\.?E\.?\s*\d+|\b(19|20)\d{2}\b|"
    r"\bvoid\b|\brevok\w+|\bregistered to\b|\bnotari[sz]ed\b|\bPhp?\s?[\d,]+|"
    r"\bSPA\b|\bdeed\b|\bTCT\b)", re.I)
# hedges / non-assertions that should NOT be flagged even if they contain a fact signal
HEDGE_RE = re.compile(
    r"\b(unknown|not in the record|i don't know|cannot confirm|unverified|pending|"
    r"need to (?:check|verify)|no (?:verified )?record|\[unknown\]|\[inferred\])\b", re.I)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _split_sentences(text):
    # keep it simple + deterministic: split on sentence enders + newlines/bullets
    parts = re.split(r"(?<=[.!?])\s+|\n+|(?:^|\s)[-•]\s+", text.strip())
    return [p.strip() for p in parts if p and p.strip()]


def gate(cur, text):
    fails, warns = [], []

    # ── 1. citation resolution ──
    cited = sorted({int(m) for m in CITE_RE.findall(text)})
    if cited:
        cur.execute("SELECT id FROM documents WHERE id = ANY(%s)", (cited,))
        real = {r[0] for r in cur.fetchall()}
        cur.execute("""SELECT DISTINCT source_id FROM matter_facts
                       WHERE provenance_level='verified' AND source_kind='doc'
                         AND source_id = ANY(%s)""", ([str(x) for x in cited],))
        verified = {int(r[0]) for r in cur.fetchall() if (r[0] or "").isdigit()}
        for d in cited:
            if d not in real:
                fails.append(f"FABRICATED CITATION: doc:{d} does not exist in the corpus")
            elif d not in verified:
                warns.append(f"doc:{d} exists but has no verified fact behind it — cite is weak")

    # ── 2. cascade grounding ──
    if CASCADE_RE.search(text):
        cur.execute("SELECT count(*) FROM keystones WHERE lower(status) IN ('open','verified')")
        n_keystones = cur.fetchone()[0]
        if n_keystones == 0:
            fails.append("UNGROUNDED CASCADE: reply asserts a cascade but no verified keystone exists")
        elif not cited:
            # asserting sweeping legal consequence with zero citations is the top hallucination
            # class — block it. A grounded cascade claim must cite the keystone's basis docs.
            fails.append("UNGROUNDED CASCADE: reply asserts a cascade/sweeping consequence with NO citation")
        else:
            warns.append("reply asserts a cascade — confirm it matches a specific keystone row, "
                         "not just that some keystone exists")

    # ── 3. ungrounded-assertion heuristic ──
    for s in _split_sentences(text):
        if HEDGE_RE.search(s):
            continue
        if FACT_SIGNAL_RE.search(s) and not CITE_RE.search(s):
            warns.append(f"uncited factual claim: \"{s[:90]}\"")

    verdict = "fail" if fails else "pass"
    return {"verdict": verdict, "fails": fails, "warns": warns,
            "cited_docs": cited, "n_warns": len(warns)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    text = a.text if a.text is not None else sys.stdin.read()
    c = _conn()
    cur = c.cursor()
    res = gate(cur, text)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"VERDICT: {res['verdict'].upper()}")
        for f in res["fails"]:
            print(f"  ✗ FAIL  {f}")
        for w in res["warns"]:
            print(f"  ⚠ warn  {w}")
        if res["verdict"] == "pass" and not res["warns"]:
            print("  ✓ all factual claims grounded")
    sys.exit(1 if res["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
