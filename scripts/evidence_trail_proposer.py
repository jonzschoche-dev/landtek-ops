#!/usr/bin/env python3
"""evidence_trail_proposer.py — Opus proposes doc → claim mappings.

Reads the 6 (or current N) open claims + a sample of categorized docs.
For each claim, asks Opus: "Which of these documents support this claim,
and how strongly?" Inserts proposals into evidence_trail_proposals for
Jonathan to review (Telegram digest) and accept.

Conservative — only proposes high-confidence matches. Jonathan's
acceptance via leo_proposal_apply.py-style command moves them into
the canonical evidence_trail table.

Run on-demand or as cron (daily). Doesn't write to evidence_trail directly.
"""
from __future__ import annotations
import json, os, re, sys, urllib.request
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from report_publisher import push_strict

DSN          = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN     = "6513067717"
OPUS_MODEL   = "claude-opus-4-5-20251101"
OPUS_URL     = "https://api.anthropic.com/v1/messages"
OPUS_VER     = "2023-06-01"
OPUS_MAX_OUT = 8000
DOC_SAMPLE   = 80   # how many candidate docs to feed Opus per claim


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS evidence_trail_proposals (
            id              SERIAL PRIMARY KEY,
            proposed_at     timestamptz NOT NULL DEFAULT now(),
            status          text NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','approved','rejected','applied')),
            claim_id        integer NOT NULL REFERENCES claims(id),
            supporting_doc_id integer NOT NULL REFERENCES documents(id),
            relation_kind   text NOT NULL,
            weight          text NOT NULL,
            narrative       text NOT NULL,
            confidence      numeric(3,2),
            rationale       text,
            reviewed_by     text,
            reviewed_at     timestamptz,
            applied_at      timestamptz,
            UNIQUE (claim_id, supporting_doc_id)
        )
    """)


def fetch_claims(cur):
    cur.execute("""
        SELECT id, short_label, claim_text, claim_kind
          FROM claims
         WHERE status = 'open'
         ORDER BY priority DESC, id
    """)
    return cur.fetchall()


def fetch_doc_sample(cur, limit: int):
    # Sample categorized docs likely to relate to the case
    cur.execute("""
        SELECT id, lt_number, original_filename, COALESCE(summary, '') AS summary,
               doc_role, doc_date
          FROM documents
         WHERE case_file = 'MWK-001'
           AND lt_number IS NOT NULL
           AND doc_role IN ('prime_evidence','title_instrument','transfer_instrument',
                            'chain_proof','tax_declaration','order_resolution',
                            'pleading','correspondence')
         ORDER BY
           CASE doc_role
             WHEN 'prime_evidence' THEN 1
             WHEN 'title_instrument' THEN 2
             WHEN 'transfer_instrument' THEN 3
             WHEN 'order_resolution' THEN 4
             WHEN 'pleading' THEN 5
             WHEN 'tax_declaration' THEN 6
             WHEN 'chain_proof' THEN 7
             ELSE 99 END,
           id DESC
         LIMIT %s
    """, (limit,))
    return cur.fetchall()


def call_opus(system_text: str, user_text: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = json.dumps({
        "model": OPUS_MODEL,
        "max_tokens": OPUS_MAX_OUT,
        "system": system_text,
        "messages": [{"role": "user", "content": user_text}],
    }).encode("utf-8")
    req = urllib.request.Request(OPUS_URL, data=body,
        headers={"x-api-key": api_key, "anthropic-version": OPUS_VER,
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    chunks = [c["text"] for c in payload.get("content", []) if c.get("type") == "text"]
    text = "\n".join(chunks).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def build_prompt(claim, docs):
    docs_block = "\n".join(
        f"  [{d['lt_number']}] doc_id={d['id']} role={d['doc_role']} date={d['doc_date']} "
        f"\"{(d['original_filename'] or '')[:90]}\"  summary: {d['summary'][:140]}"
        for d in docs
    )
    return f"""You are evaluating which documents from LandTek's index support
a specific legal claim in Civil Case 26-360.

== CLAIM ==
  claim_id:   {claim['id']}
  label:      {claim['short_label']}
  kind:       {claim['claim_kind']}
  text:       {claim['claim_text']}

== CANDIDATE DOCS (filename + summary excerpt) ==
{docs_block}

== YOUR TASK ==
Identify documents that SUPPORT this claim. Be conservative — only propose
documents whose filename/summary clearly indicate they are relevant.

Return STRICT JSON: a list of proposals, each:
  {{
    "supporting_doc_id": <int>,        // from the candidates above
    "lt_number": "<LT-NNNN>",
    "relation_kind":     "proves" | "corroborates" | "impeaches" | "contextualizes",
    "weight":            "primary" | "strong" | "moderate" | "weak",
    "narrative":         "<one sentence: HOW this doc supports this claim>",
    "confidence":        <0.50-1.00>   // your confidence in this match
  }}

Rules:
  - Maximum 6 proposals per claim. Quality over quantity.
  - Only propose with confidence ≥ 0.65.
  - If no docs clearly support the claim, return [] (empty list).
  - "primary" = directly proves the claim by itself. Use sparingly.
  - "strong" = significantly contributes to proving the claim.
  - "moderate" = corroborating evidence.
  - "weak" = contextual or supporting.

Output ONLY the JSON list. No commentary.
""".strip()


def parse_proposals(raw: str, valid_doc_ids: set[int]):
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m: return []
        try:
            items = json.loads(m.group(0))
        except Exception:
            return []
    if not isinstance(items, list): return []
    valid = []
    for i in items:
        if not isinstance(i, dict): continue
        try:
            doc_id = int(i.get("supporting_doc_id"))
        except (TypeError, ValueError):
            continue
        if doc_id not in valid_doc_ids: continue
        if i.get("relation_kind") not in ("proves","corroborates","impeaches","contextualizes"): continue
        if i.get("weight") not in ("primary","strong","moderate","weak"): continue
        try:
            conf = float(i.get("confidence") or 0)
        except (TypeError, ValueError):
            continue
        if conf < 0.65: continue
        i["confidence"] = conf
        i["supporting_doc_id"] = doc_id
        valid.append(i)
    return valid


def insert_proposals(cur, claim, proposals):
    n = 0
    for p in proposals:
        cur.execute("""
            INSERT INTO evidence_trail_proposals
              (claim_id, supporting_doc_id, relation_kind, weight, narrative, confidence, rationale)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (claim_id, supporting_doc_id) DO NOTHING
            RETURNING id
        """, (claim["id"], p["supporting_doc_id"], p["relation_kind"], p["weight"],
              p["narrative"], p["confidence"],
              f"Opus proposed; confidence {p['confidence']:.2f}"))
        if cur.fetchone():
            n += 1
    return n


def push_digest(cur):
    cur.execute("""
        SELECT etp.id, c.short_label, c.claim_text,
               d.lt_number, etp.relation_kind, etp.weight, etp.confidence, etp.narrative
          FROM evidence_trail_proposals etp
          JOIN claims c ON c.id = etp.claim_id
          JOIN documents d ON d.id = etp.supporting_doc_id
         WHERE etp.status = 'pending'
         ORDER BY etp.confidence DESC, etp.id DESC
         LIMIT 6
    """)
    rows = cur.fetchall()
    if not rows or tg_send is None:
        return 0
    parts = ["📋 <b>Evidence Trail Proposals</b>", ""]
    for r in rows:
        parts.append(
            f"<b>#{r['id']}</b> [{r['short_label']}]\n"
            f"  → <code>{r['lt_number']}</code> as <i>{r['weight']}</i> ({r['relation_kind']}, conf {r['confidence']:.2f})\n"
            f"  <i>{(r['narrative'] or '')[:200]}</i>"
        )
    parts.append("")
    parts.append("Review: <code>SELECT * FROM evidence_trail_proposals WHERE status='pending'</code>")
    parts.append("Approve: <code>UPDATE evidence_trail_proposals SET status='approved' WHERE id=N</code>")
    try:
        tg_send(JONATHAN, "\n\n".join(parts), source="watchdog",
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception:
        pass
    return len(rows)


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)

    claims = fetch_claims(cur)
    docs = fetch_doc_sample(cur, DOC_SAMPLE)
    if not docs:
        print("[evidence_proposer] no categorized docs available — run auto_assign_doc_role.py first")
        return
    valid_ids = {d["id"] for d in docs}
    print(f"[evidence_proposer] {len(claims)} claims, {len(docs)} candidate docs")

    sys_text = ("You are a precise, conservative evidence-trail analyst for a Philippine "
                "property case. You output ONLY valid JSON, no commentary.")

    total_proposed = 0
    for claim in claims:
        try:
            raw = call_opus(sys_text, build_prompt(claim, docs))
        except Exception as e:
            print(f"[evidence_proposer] Opus error for claim {claim['id']}: {e}")
            continue
        props = parse_proposals(raw, valid_ids)
        n = insert_proposals(cur, claim, props)
        print(f"  claim {claim['id']} ({claim['short_label']}): {n} new proposals (of {len(props)} valid)")
        total_proposed += n

    if total_proposed:
        n_pushed = push_digest(cur)
        print(f"[evidence_proposer] {total_proposed} new proposals; pushed digest of {n_pushed}")
    else:
        print("[evidence_proposer] no new proposals this run")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
