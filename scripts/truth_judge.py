#!/usr/bin/env python3
"""truth_judge.py — LAWYER-GRADE grading. Instead of substring matching, an Opus
"senior litigation partner" reviews each answer against the verified record and
grades it the way a hostile reviewer would: factual accuracy, CITATION SOUNDNESS
(does the cited doc actually support the point?), no-inference-as-fact discipline,
completeness (did it state the strongest point?), and defensibility vs opposing
counsel. Returns a letter grade + specific defects.
"""
import json, os, re, urllib.request
import psycopg2, psycopg2.extras

OPUS_MODEL = "claude-opus-4-5-20251101"
OPUS_URL = "https://api.anthropic.com/v1/messages"


def _envk(name):
    v = os.environ.get(name)
    if v:
        return v
    for line in open("/root/landtek/.env"):
        line = line.strip()
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


JUDGE_SYS = """You are a skeptical, exacting senior litigation partner at a Philippine
property-law firm, reviewing a junior associate's answer BEFORE it reaches the client
or the court. You care about one question: would this answer survive a hostile judge
and opposing counsel? Grade RUTHLESSLY against the VERIFIED RECORD provided:

  ACCURACY      — every factual assertion must match the verified record. Any wrong
                  name, date, title number, or case is a serious defect.
  CITATIONS     — documents cited must actually support the point made; an uncited
                  factual assertion, or a citation to the wrong document, is a defect.
  DISCIPLINE    — never present inference, a draft, or email content as established
                  fact; keep SEPARATE matters and SEPARATE clients separate.
  COMPLETENESS  — the answer should state the strongest available point; omitting a
                  decisive fact is a defect.
  DEFENSIBILITY — nothing opposing counsel could exploit: no overclaim, no
                  hallucination, no conflated cases.

Output STRICT JSON only, no prose:
{"grade":"A|B|C|D|F","pass":<bool>,"accuracy":"<short>","citations":"<short>",
 "discipline":"<short>","completeness":"<short>","defensibility":"<short>",
 "defects":["..."],"one_line":"<verdict>"}
pass=true ONLY if grade is A or B (court/client-ready). C or below is not yet defensible."""


def _verified_record(cur):
    cur.execute("""SELECT c.short_label, c.claim_text, v.verdict, v.citation_tag
                     FROM claims c LEFT JOIN claim_truth_verdicts v ON v.claim_id=c.id
                    WHERE c.case_file='MWK-001' ORDER BY c.priority DESC NULLS LAST, c.id""")
    claims = "\n".join(
        f"  - [{(r['verdict'] or '?').upper()}] {r['claim_text']} (cites {r['citation_tag'] or '—'})"
        for r in cur.fetchall())
    invariants = (
        "INVARIANTS (ground truth):\n"
        "  - TCT T-4497 is the mother title = Heirs of Mary Worrick Keesey.\n"
        "  - Gloria Balane's TCT T-079-2021002127 is VOID: derives from cancelled T-52540 via a 2016 "
        "Deed of Sale executed by Cesar de la Fuente under an SPA revoked in 2005.\n"
        "  - Civil Case 26-360 = accion reinvindicatoria vs Balane over T-4497. Civil Case 6839 = CARP "
        "just-compensation (a SEPARATE case).\n"
        "  - TCT T-30683 (Manguisoc) and TCT T-4494 (Cabanbanan) are SEPARATE matters — NOT derivatives "
        "of T-4497 and NOT part of Civil Case 26-360.\n"
        "  - MMK is NOT MWK. Allan Inocalla / Paracale (Paracale-001) is a SEPARATE CLIENT from the "
        "Keesey estate (MWK-001).")
    return invariants + "\n\nVERIFIED CLAIMS (with truth-negotiator verdict):\n" + claims


def judge(question, answer, conn=None):
    """Grade one Q/answer pair. Returns a dict (grade/pass/defects/...)."""
    own = conn is None
    if own:
        conn = psycopg2.connect(os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"))
        conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    record = _verified_record(cur)
    cur.close()
    if own:
        conn.close()
    user = (f"QUESTION:\n{question}\n\nJUNIOR ASSOCIATE'S ANSWER:\n{answer}\n\n"
            f"THE VERIFIED RECORD (the answer MUST be consistent with this):\n{record}")
    body = json.dumps({"model": OPUS_MODEL, "max_tokens": 900, "system": JUDGE_SYS,
                       "messages": [{"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(OPUS_URL, data=body, method="POST",
        headers={"x-api-key": _envk("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            payload = json.loads(r.read())
        txt = "\n".join(c["text"] for c in payload.get("content", []) if c.get("type") == "text")
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {"grade": "?", "pass": False, "defects": ["judge parse fail"], "one_line": txt[:120]}
    except Exception as e:
        return {"grade": "?", "pass": False, "defects": [f"judge error: {type(e).__name__}"], "one_line": str(e)[:120]}


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "When was Cesar de la Fuente's SPA revoked?"
    a = sys.argv[2] if len(sys.argv) > 2 else "His SPA was revoked in 2005 (doc#91)."
    print(json.dumps(judge(q, a), indent=2))
