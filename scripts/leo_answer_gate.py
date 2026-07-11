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
# specific legal-authority citations (statute / rule / article / section / G.R.) — LandTek is NOT a law
# firm, so a named provision asserted WITHOUT a grounding doc is the model inventing law → FAIL, not warn.
# (A hedge does NOT excuse it: the model should say "I'll confirm the applicable rules with counsel",
# never name a specific rule number it can't ground.)
LEGAL_CITE_RE = re.compile(
    r"\b("
    r"rules?\s+\d+"                                              # Rule 74, Rules 45
    r"|art(?:icle|\.)?\s+\d+"                                    # Article 1144, Art. 1144
    r"|sec(?:tion|\.)?\s+\d+"                                    # Section 4, Sec. 21
    r"|(?:R\.?A\.?|republic\s+act)\s*(?:no\.?\s*)?\d+"           # R.A. 3019, Republic Act No. 6713
    r"|(?:P\.?D\.?|presidential\s+decree)\s*(?:no\.?\s*)?\d+"    # P.D. 1529
    r"|(?:B\.?P\.?|batas\s+pambansa)\s*(?:blg\.?|no\.?)?\s*\d+"  # B.P. Blg. 129
    r"|(?:C\.?A\.?|commonwealth\s+act)\s*(?:no\.?\s*)?\d+"       # C.A. 141
    r"|G\.?R\.?\s*(?:no\.?\s*)?\d+"                              # G.R. No. 12345
    r")\b", re.I)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


# dotted legal-authority prefixes (R.A. 3019, G.R. No. 45) whose INTERNAL periods must not read as
# sentence enders — else "R.A. 3019" splits and the legal-cite check/remediation misses the fragment.
_ABBREV_DOT = re.compile(r"\b(R\.A|P\.D|B\.P|C\.A|G\.R|E\.O)\.", re.I)


def _split_sentences(text):
    # keep it simple + deterministic: split on sentence enders + newlines/bullets, but first protect
    # the internal periods of dotted legal abbreviations (restored after the split).
    t = _ABBREV_DOT.sub(lambda m: m.group(0).replace(".", "\x00"), text.strip())
    parts = re.split(r"(?<=[.!?])\s+|\n+|(?:^|\s)[-•]\s+", t)
    return [p.replace("\x00", ".").strip() for p in parts if p and p.strip()]


def _c0(row):
    """First selected column — works for BOTH tuple and RealDict cursors (real callers use RealDict,
    so positional r[0] KeyError'd on any cited reply — the exact input the gate exists to check)."""
    if row is None:
        return None
    return row[0] if not hasattr(row, "keys") else next(iter(row.values()))


def gate(cur, text):
    fails, warns = [], []

    # ── 1. citation resolution ──
    cited = sorted({int(m) for m in CITE_RE.findall(text)})
    if cited:
        cur.execute("SELECT id FROM documents WHERE id = ANY(%s)", (cited,))
        real = {_c0(r) for r in cur.fetchall()}
        cur.execute("""SELECT DISTINCT source_id FROM matter_facts
                       WHERE provenance_level='verified' AND source_kind='doc'
                         AND source_id = ANY(%s)""", ([str(x) for x in cited],))
        verified = {int(_c0(r)) for r in cur.fetchall() if (str(_c0(r) or "")).isdigit()}
        for d in cited:
            if d not in real:
                fails.append(f"FABRICATED CITATION: doc:{d} does not exist in the corpus")
            elif d not in verified:
                warns.append(f"doc:{d} exists but has no verified fact behind it — cite is weak")

    # ── 2. cascade grounding ──
    if CASCADE_RE.search(text):
        cur.execute("SELECT count(*) FROM keystones WHERE lower(status) IN ('open','verified')")
        n_keystones = _c0(cur.fetchone())
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

    # ── 4. uncited legal authority ── a named statute/rule/G.R. with no grounding doc → FAIL
    for s in _split_sentences(text):
        if LEGAL_CITE_RE.search(s) and not CITE_RE.search(s):
            fails.append(f"UNCITED LEGAL AUTHORITY: \"{LEGAL_CITE_RE.search(s).group(0)}\" "
                         "asserted with no grounding doc")

    verdict = "fail" if fails else "pass"
    return {"verdict": verdict, "fails": fails, "warns": warns,
            "cited_docs": cited, "n_warns": len(warns)}


def remediate(cur, text, res=None):
    """Deterministically produce a GROUNDED-ONLY version of a reply that failed the gate — $0,
    no LLM. The token-efficient fail-path: instead of regenerating (which doubles cost), keep
    every non-factual sentence and every factual sentence with a RESOLVABLE citation, and drop
    the ungrounded ones (fabricated cite / uncited cascade / uncited factual claim). Guarantees
    nothing ungrounded ships, at zero extra tokens and millisecond speed.

    (The n8n flow MAY instead try one bounded LLM regeneration first for quality, then fall back
    to this — but this is the floor: accurate and free, never a loop.)"""
    res = res or gate(cur, text)
    if res["verdict"] == "pass" and not res["warns"]:
        return text
    real = set()
    if res["cited_docs"]:
        cur.execute("SELECT id FROM documents WHERE id = ANY(%s)", (res["cited_docs"],))
        real = {_c0(r) for r in cur.fetchall()}
    kept, dropped = [], 0
    for s in _split_sentences(text):
        cites = {int(m) for m in CITE_RE.findall(s)}
        if any(c not in real for c in cites):          # cites a fabricated doc
            dropped += 1; continue
        factual = bool(FACT_SIGNAL_RE.search(s)) and not HEDGE_RE.search(s)
        if CASCADE_RE.search(s) and not cites:          # ungrounded cascade
            dropped += 1; continue
        if LEGAL_CITE_RE.search(s) and not cites:       # uncited legal authority (statute/rule/G.R.)
            dropped += 1; continue
        if factual and not cites:                       # uncited factual claim
            dropped += 1; continue
        kept.append(s)
    out = " ".join(kept).strip()
    if dropped:
        out = (out + " I've left out claims I can't ground in the record.").strip() \
            if out else "I don't have a verified record to answer that."
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--text")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--remediate", action="store_true",
                    help="print a grounded-only rewrite of a failing reply ($0, no LLM)")
    a = ap.parse_args()
    text = a.text if a.text is not None else sys.stdin.read()
    c = _conn()
    cur = c.cursor()
    if a.remediate:
        print(remediate(cur, text))
        return
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
