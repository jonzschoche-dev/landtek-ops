#!/usr/bin/env python3
"""classify_document_type.py — classify untyped docs' document_type via the OWNED local model (qwen, $0).

WHY. `document_type` is one of the 5 ConnectivityGate signals (A41). The deterministic map
(deploy_710: classification→type) can only type docs that already carry a `classification`; the residue
(e.g. 71 Paracale docs with NULL/`Other`/unmapped classification) stays untyped and can never reach
"connected" until typed. This types them from the doc TEXT using the local Ollama model via `model_router`
(Tier-1, logged to inference_audit; no Gemini, no credits) — the quota-free half of Paracale connectivity.

SAFETY / A41. Setting `document_type` is A41-SAFE: it never sets `model_used`, so a typed-but-unstamped doc
is still NOT fully connected — `test_connected_document_count.py` (prov ⇒ all-5) stays green. Shadow-first:
proposals land in `document_type_proposals` for review; `--commit` writes `documents.document_type` ONLY
where currently NULL (never overwrites), and it's reversible (re-type / clear the column).

  python3 scripts/classify_document_type.py --shadow --matter Paracale-001         # classify → proposals (no write)
  python3 scripts/classify_document_type.py --review [--matter Paracale-001]        # bulk-review proposals
  python3 scripts/classify_document_type.py --commit --min-confidence 0.6           # write approved (NULL only)
"""
import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Controlled vocabulary — existing types + the real categories this mining/civil-registry corpus needs.
# WIDE ON PURPOSE (v2): a too-narrow list force-fits the model into confidently-wrong picks (v1 mislabeled
# birth certs / business clearances / permits as "Certificate of Death" at 0.9+). 'Other Document' is the
# honest escape hatch — the prompt forbids force-fitting.
VOCAB = [
    "TCT", "Deed", "SPA", "Affidavit", "Court Order", "Court Filing", "Tax Document", "Correspondence",
    "Receipt", "Contract", "Government Submission", "Newspaper", "Chat Screenshot", "Working Draft",
    "Certificate of Birth", "Certificate of Death", "Marriage Certificate", "Business Permit",
    "Sanitary Permit", "Mining Permit", "Environmental Document", "License", "Permit", "Application",
    "Technical Report", "Clearance", "Certification", "Map or Plan", "Photograph",
    "Document (photographed)", "Other Document",
]
_VOCAB_LC = {v.lower(): v for v in VOCAB}

# Synonyms → canonical vocab (the model often spells out or varies a type that IS on the list).
SYN = {
    "transfer certificate of title": "TCT", "tct": "TCT",
    "special power of attorney": "SPA", "spa": "SPA",
    "complaint": "Court Filing", "pleading": "Court Filing", "motion": "Court Filing", "petition": "Court Filing",
    "letter": "Correspondence", "letter/email": "Correspondence", "email": "Correspondence", "memo": "Correspondence",
    "certificate of business name": "Certification", "certificate of business name registration": "Certification",
    "business name certificate": "Certification", "certificate": "Certification",
}

SYS = ("You are a precise document classifier for a Philippine land/mining/civil-registry case corpus. You "
       "classify a document into EXACTLY ONE type from a controlled list and reply ONLY with a single JSON "
       "object. Accuracy matters more than specificity: a wrong specific label is a corruption.")

PROMPT_TMPL = (
    "Classify the document below into EXACTLY ONE of these types:\n{vocab}\n\n"
    "Rules: pick the single best fit from the list. Distinguish carefully — a 'Certificate of Birth' is NOT a "
    "'Certificate of Death'; a 'Business Permit'/'Clearance'/'Sanitary Permit' is NOT a civil-registry "
    "certificate. Use 'Chat Screenshot' for messenger/social captures; 'Correspondence' for letters/emails/"
    "notices; 'Court Filing' for pleadings/motions/complaints; 'Court Order' for orders/resolutions/decisions. "
    "**If NO type on the list clearly fits, answer 'Other Document' with confidence <= 0.5 — do NOT force-fit "
    "a specific type you are unsure of. Prefer 'Other Document' over a wrong specific guess.** "
    "Reply with ONLY this JSON, no prose:\n"
    '{{"document_type": "<one exactly from the list>", "confidence": <0.0-1.0>, "reason": "<=12 words"}}\n\n'
    "DOCUMENT TEXT (may be OCR-noisy):\n{body}"
)


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS document_type_proposals (
        doc_id int PRIMARY KEY, case_file text, proposed_type text, confidence real, reason text,
        model text, raw text, status text DEFAULT 'proposed', created_at timestamptz DEFAULT now())""")


def _parse(txt):
    """Extract the JSON object from a possibly-chatty model reply; normalize the type to the vocab."""
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None, 0.0, "no-json", "parse_error"
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None, 0.0, "bad-json", "parse_error"
    raw = str(d.get("document_type", "")).strip()
    key = raw.lower()
    typ = _VOCAB_LC.get(key) or SYN.get(key) or SYN.get(re.sub(r"[^a-z ]", "", key).strip())
    if not typ:  # genuinely off-list → keep raw but flag low so review catches it
        return raw or None, float(d.get("confidence", 0) or 0) * 0.5, (d.get("reason") or "off-vocab")[:120], "off_vocab"
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0) or 0)))
    except Exception:
        conf = 0.0
    return typ, conf, (d.get("reason") or "")[:120], "ok"


def shadow(cur, matter, limit):
    from model_router import pick, call_model
    _ensure(cur)
    q = """SELECT id, case_file, coalesce(extracted_text,'') AS t FROM documents
           WHERE document_type IS NULL AND coalesce(text_length,length(extracted_text),0) >= 50 {mf}
           ORDER BY id"""
    mf = "AND case_file=%s" if matter else ""
    cur.execute(q.format(mf=mf), ((matter,) if matter else ()))
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
    print(f"[classify] shadow pass over {len(rows)} untyped doc(s){' in '+matter if matter else ''} via local model")
    cfg = pick("classify")
    if not cfg.get("provider"):
        print(f"[classify] ABORT — no local model tier available: {cfg.get('error')}"); return
    done = err = 0
    for r in rows:
        body = r["t"][:3000]
        try:
            res = call_model(cfg, PROMPT_TMPL.format(vocab=", ".join(VOCAB), body=body),
                             task_type="classify", system_prompt=SYS, doc_id=str(r["id"]))
        except Exception as e:
            res = {"error": str(e)[:80], "text": ""}
        if res.get("error") and not res.get("text"):
            err += 1
            cur.execute("""INSERT INTO document_type_proposals (doc_id,case_file,proposed_type,confidence,reason,model,raw,status)
                VALUES (%s,%s,NULL,0,%s,%s,%s,'error') ON CONFLICT (doc_id) DO UPDATE SET
                reason=EXCLUDED.reason, status='error', created_at=now()""",
                (r["id"], r["case_file"], f"model error: {res['error']}"[:120], cfg.get("model_name") or "ollama", ""))
            continue
        typ, conf, reason, st = _parse(res.get("text", ""))
        cur.execute("""INSERT INTO document_type_proposals (doc_id,case_file,proposed_type,confidence,reason,model,raw,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (doc_id) DO UPDATE SET
            proposed_type=EXCLUDED.proposed_type, confidence=EXCLUDED.confidence, reason=EXCLUDED.reason,
            model=EXCLUDED.model, raw=EXCLUDED.raw, status=EXCLUDED.status, created_at=now()""",
            (r["id"], r["case_file"], typ, conf, reason, cfg.get("model_name") or "ollama_local",
             (res.get("text") or "")[:400], st))
        done += 1
    print(f"[classify] done: {done} classified, {err} model-errors → document_type_proposals (review with --review)")


def review(cur, matter):
    _ensure(cur)
    mf = "AND case_file=%s" if matter else ""
    cur.execute(f"""SELECT status, count(*) FROM document_type_proposals WHERE 1=1 {mf} GROUP BY 1 ORDER BY 2 DESC""",
                ((matter,) if matter else ()))
    print("[classify] proposal status:", ", ".join(f"{r['status']}={r['count']}" for r in cur.fetchall()))
    cur.execute(f"""SELECT proposed_type, count(*), round(avg(confidence)::numeric,2) avg_conf
                    FROM document_type_proposals WHERE status IN ('ok','off_vocab') {mf}
                    GROUP BY 1 ORDER BY 2 DESC""", ((matter,) if matter else ()))
    print("  proposed_type distribution (avg confidence):")
    for r in cur.fetchall():
        print(f"    {str(r['proposed_type']):<26} {r['count']:>3}  conf~{r['avg_conf']}")
    cur.execute(f"""SELECT doc_id, proposed_type, confidence, reason FROM document_type_proposals
                    WHERE status IN ('ok','off_vocab','error') {mf} AND coalesce(confidence,0) < 0.6
                    ORDER BY confidence ASC LIMIT 40""", ((matter,) if matter else ()))
    low = cur.fetchall()
    if low:
        print(f"  ⚠ {len(low)} LOW-confidence (<0.6) — eyeball before commit:")
        for r in low:
            print(f"    doc {r['doc_id']}: {r['proposed_type']} ({r['confidence']}) — {r['reason']}")


def commit(cur, matter, min_conf):
    _ensure(cur)
    mf = "AND p.case_file=%s" if matter else ""
    cur.execute(f"""UPDATE documents d SET document_type = p.proposed_type
        FROM document_type_proposals p
        WHERE p.doc_id=d.id AND d.document_type IS NULL          -- never overwrite (A41-safe, reversible)
          AND p.status='ok' AND p.proposed_type IS NOT NULL AND p.confidence >= %s {mf}
        RETURNING d.id, p.proposed_type, p.confidence""",
        ((min_conf,) + ((matter,) if matter else ())))
    wrote = cur.fetchall()
    print(f"[classify] COMMIT: wrote document_type on {len(wrote)} doc(s) at confidence >= {min_conf} "
          f"(NULL-only, no provenance stamped — A41 stays green). Reversible.")
    for r in wrote[:15]:
        print(f"    doc {r['id']} → {r['proposed_type']} ({r['confidence']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shadow", action="store_true"); ap.add_argument("--review", action="store_true")
    ap.add_argument("--commit", action="store_true"); ap.add_argument("--matter")
    ap.add_argument("--limit", type=int); ap.add_argument("--min-confidence", type=float, default=0.6, dest="min_conf")
    a = ap.parse_args()
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if a.commit:   commit(cur, a.matter, a.min_conf)
        elif a.review: review(cur, a.matter)
        else:          shadow(cur, a.matter, a.limit)
    finally:
        cur.close(); c.close()


if __name__ == "__main__":
    main()
