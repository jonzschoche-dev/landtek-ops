#!/usr/bin/env python3
"""opus_doc_role_classifier.py — batch-classify not_yet_assessed docs via Opus.

The filename-heuristic classifier (auto_assign_doc_role.py) handled 240/977
docs. The remaining 737 didn't match any pattern — these are docs whose
filenames are non-obvious (PDF scan numbers, vague titles, etc.).

This script reads their filename + summary excerpt, batches 20 at a time
to Opus, and proposes a doc_role for each. Conservative — uses the same
enum as deploy_317 (prime_evidence, title_instrument, etc.) plus a
not_yet_assessed default for genuinely ambiguous cases.

Runs once. Output: ~50 batches × $0.05 = ~$2 total cost.
Inserts proposals into doc_role_proposals; cron applies confidence ≥ 0.85
automatically (hourly). Lower confidence sits for Jonathan review.

Idempotent — re-running skips docs that already have a proposal.
"""
from __future__ import annotations
import json, os, re, sys, urllib.request, time
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OPUS_MODEL   = "claude-opus-4-5-20251101"
OPUS_URL     = "https://api.anthropic.com/v1/messages"
OPUS_VER     = "2023-06-01"
OPUS_MAX_OUT = 4000
BATCH_SIZE   = 20
ROLES = ['prime_evidence','title_instrument','tax_declaration','transfer_instrument',
         'chain_proof','pleading','order_resolution','correspondence','background',
         'not_yet_assessed']


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS doc_role_proposals (
            id              SERIAL PRIMARY KEY,
            proposed_at     timestamptz NOT NULL DEFAULT now(),
            status          text NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','applied','rejected')),
            doc_id          integer NOT NULL UNIQUE REFERENCES documents(id),
            proposed_role   text NOT NULL,
            confidence      numeric(3,2) NOT NULL,
            rationale       text,
            applied_at      timestamptz
        )
    """)


def fetch_unclassified(cur, limit=None):
    sql = """
        SELECT d.id, d.lt_number, d.original_filename, COALESCE(d.summary,'') AS summary
          FROM documents d
          LEFT JOIN doc_role_proposals p ON p.doc_id = d.id
         WHERE (d.doc_role IS NULL OR d.doc_role = 'not_yet_assessed')
           AND p.id IS NULL
         ORDER BY d.id
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    return cur.fetchall()


def call_opus(system, user):
    key = os.environ.get("ANTHROPIC_API_KEY")
    body = json.dumps({
        "model": OPUS_MODEL, "max_tokens": OPUS_MAX_OUT,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(OPUS_URL, data=body,
        headers={"x-api-key": key, "anthropic-version": OPUS_VER,
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        payload = json.loads(r.read())
    txt = "\n".join(c["text"] for c in payload.get("content", []) if c.get("type") == "text")
    txt = re.sub(r"^```(?:json)?\s*", "", txt.strip())
    txt = re.sub(r"\s*```$", "", txt)
    return txt


def build_prompt(batch):
    rows = "\n".join(
        f"  doc_id={d['id']}  LT={d['lt_number']}  filename={(d['original_filename'] or '')[:90]!r}  "
        f"summary={d['summary'][:200]!r}"
        for d in batch
    )
    return f"""Classify each document below into one of these doc_roles:

{', '.join(ROLES)}

Heuristic guide:
- title_instrument: TCT, OCT, certificate of title, title transfer record
- tax_declaration: tax declaration (TD), real property tax assessment
- transfer_instrument: deed of sale/donation/conveyance, SPA, contract to sell
- prime_evidence: birth/marriage/death certs, affidavits, sworn statements,
  primary identity or relationship proof
- pleading: motion, manifestation, petition, complaint, answer, brief, memorandum
- order_resolution: court order, resolution, decision, writ, ruling
- correspondence: letter, email, reply, memo
- chain_proof: documents that ESTABLISH a derivative or transfer relationship
  (NOT the title itself, but evidence of the chain)
- background: receipts, invoices, CARP/DAR/Landbank docs, context-only
- not_yet_assessed: only if genuinely ambiguous after reading

== DOCUMENTS ==
{rows}

Return STRICT JSON: array of objects, one per doc_id above:
  [{{"doc_id": <int>, "doc_role": "<role>", "confidence": <0.50-1.00>}}]

Use confidence 0.90+ only when the role is unambiguous.
Use 0.65-0.89 for likely-but-not-certain.
Use < 0.65 only if you'd default to 'not_yet_assessed'.
Output ONLY the JSON array.
""".strip()


def parse_batch(raw, valid_ids):
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m: return []
        try: items = json.loads(m.group(0))
        except: return []
    out = []
    for i in items:
        if not isinstance(i, dict): continue
        try:
            doc_id = int(i.get("doc_id"))
        except: continue
        if doc_id not in valid_ids: continue
        role = i.get("doc_role")
        if role not in ROLES: continue
        try:
            conf = float(i.get("confidence") or 0)
        except: continue
        if conf < 0.50: continue
        out.append({"doc_id": doc_id, "doc_role": role, "confidence": conf})
    return out


def insert_proposals(cur, batch_results):
    n = 0
    for r in batch_results:
        cur.execute("""
            INSERT INTO doc_role_proposals (doc_id, proposed_role, confidence, rationale)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (doc_id) DO NOTHING
            RETURNING id
        """, (r["doc_id"], r["doc_role"], r["confidence"],
              f"Opus batch classification; confidence {r['confidence']:.2f}"))
        if cur.fetchone():
            n += 1
    return n


def auto_apply_high_confidence(cur):
    """Auto-apply proposals with confidence ≥ 0.90."""
    cur.execute("""
        WITH applied AS (
            SELECT id, doc_id, proposed_role FROM doc_role_proposals
             WHERE status = 'pending' AND confidence >= 0.90
        )
        UPDATE documents d
           SET doc_role = a.proposed_role
          FROM applied a
         WHERE d.id = a.doc_id
        RETURNING d.id
    """)
    n_doc = cur.rowcount
    cur.execute("""
        UPDATE doc_role_proposals
           SET status = 'applied', applied_at = now()
         WHERE status = 'pending' AND confidence >= 0.90
    """)
    return n_doc


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    rows = fetch_unclassified(cur)
    print(f"[opus_doc_role] {len(rows)} docs to classify")
    if not rows:
        print("nothing to do"); return

    sys_text = ("You classify legal documents conservatively. Output ONLY valid JSON.")
    total_proposed = 0
    for batch_start in range(0, len(rows), BATCH_SIZE):
        batch = rows[batch_start:batch_start + BATCH_SIZE]
        valid_ids = {d["id"] for d in batch}
        try:
            raw = call_opus(sys_text, build_prompt(batch))
        except Exception as e:
            print(f"  batch {batch_start//BATCH_SIZE + 1} Opus error: {e}")
            continue
        parsed = parse_batch(raw, valid_ids)
        n = insert_proposals(cur, parsed)
        print(f"  batch {batch_start//BATCH_SIZE + 1:2d} ({batch_start+1}-{batch_start+len(batch)})  "
              f"proposed {n} of {len(parsed)}/{len(batch)}")
        total_proposed += n
        time.sleep(0.5)  # gentle rate-limit

    print(f"\n[opus_doc_role] {total_proposed} proposals inserted")
    applied = auto_apply_high_confidence(cur)
    print(f"[opus_doc_role] {applied} high-confidence (≥0.90) auto-applied to documents")
    cur.execute("SELECT doc_role, COUNT(*) AS n FROM documents WHERE lt_number IS NOT NULL GROUP BY doc_role ORDER BY n DESC NULLS LAST")
    print("\nFinal role distribution:")
    for r in cur.fetchall():
        print(f"  {(r['doc_role'] or 'NULL'):25s} {r['n']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
