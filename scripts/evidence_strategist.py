#!/usr/bin/env python3
"""evidence_strategist.py — AGENTIC, Opus-powered forensic evidence discovery.

Unlike evidence_trail_proposer (single blind pass over filenames/summaries), this
gives the strongest model real TOOLS and lets it INVESTIGATE the corpus:

  - traverse the title chain (parent/derivative titles + provenance)
  - pull instrument-level executor / authority / NOTARY detail per title
  - find the SAME executor or SAME notary reappearing across instruments
    (the deeper-connection signal a keyword search never surfaces)
  - follow entity co-occurrence across documents
  - semantic + keyword search the full corpus
  - check each claim's required_to_prove for GAPS not yet evidenced

It proposes additional evidence (and the deeper links it found) into
evidence_trail_proposals — SUGGESTIONS Jonathan confirms. It never writes the
canonical evidence_trail directly. Discipline: every finding cites a doc_id and
a basis; vectors propose, humans decide.

Usage:
  python3 evidence_strategist.py --claim 2        # investigate one claim
  python3 evidence_strategist.py --case MWK-001   # all open claims for a case
"""
from __future__ import annotations
import argparse, json, os, re, sys, urllib.request
import psycopg2, psycopg2.extras

DSN        = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
OPUS_MODEL = "claude-opus-4-5-20251101"
OPUS_URL   = "https://api.anthropic.com/v1/messages"
OPUS_VER   = "2023-06-01"
MAX_ROUNDS = 22
REL_OK     = ("proves", "corroborates", "impeaches", "contextualizes")
WT_OK      = ("primary", "strong", "moderate", "weak")
CONN_OK    = ("direct_support", "corroboration", "impeachment", "gap_filler", "deeper_link")


def envk(name):
    v = os.environ.get(name)
    if v:
        return v
    try:
        for line in open("/root/landtek/.env"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return None


# ───────────────────────── corpus tools (mostly pure SQL) ─────────────────────
def t_keyword_search(cur, query, limit=12):
    cur.execute("""
        SELECT id, COALESCE(NULLIF(smart_filename,''), original_filename) nm,
               substring(extracted_text from greatest(1, position(lower(%s) in lower(extracted_text)) - 60)
                         for 220) snip
          FROM documents
         WHERE master_form='digital' AND extracted_text ILIKE %s
         ORDER BY id LIMIT %s
    """, (query, f"%{query}%", limit))
    return [{"doc_id": r["id"], "name": r["nm"], "snippet": (r["snip"] or "").replace("\n", " ")}
            for r in cur.fetchall()]


def t_docs_for_title(cur, tct):
    cur.execute("""
        SELECT dt.doc_id, dt.mentions,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename) nm, d.doc_date
          FROM document_titles dt JOIN documents d ON d.id=dt.doc_id
         WHERE dt.tct_number=%s ORDER BY dt.mentions DESC LIMIT 40
    """, (tct,))
    return [{"doc_id": r["doc_id"], "name": r["nm"], "date": str(r["doc_date"] or ""),
             "mentions": r["mentions"]} for r in cur.fetchall()]


def t_title_chain(cur, tct):
    cur.execute("""
        SELECT parent_title, child_title, relationship, provenance_level,
               source_doc_id, left(provenance_quote,160) q
          FROM title_chain WHERE parent_title=%s OR child_title=%s
    """, (tct, tct))
    return [{"parent": r["parent_title"], "child": r["child_title"], "rel": r["relationship"],
             "provenance": r["provenance_level"], "source_doc_id": r["source_doc_id"],
             "quote": r["q"]} for r in cur.fetchall()]


def t_instruments_on_title(cur, tct):
    cur.execute("""
        SELECT doc_id, pe_number, instrument_type, executor_full_name, executed_in_capacity,
               authority_basis, authority_instrument_ref, authority_date, notary_name,
               notary_doc_no, notary_book, notary_series_year, consideration_amount,
               provenance_level, left(source_quote_full,200) q
          FROM instruments_on_title WHERE parent_tct_number=%s ORDER BY entry_date NULLS LAST
    """, (tct,))
    return [dict(r) for r in cur.fetchall()]


def t_find_instruments_by_person(cur, name):
    """Same executor OR same notary across instruments — the cross-title pattern."""
    cur.execute("""
        SELECT parent_tct_number, doc_id, pe_number, instrument_type, executor_full_name,
               authority_basis, authority_date, notary_name, notary_book, notary_series_year,
               provenance_level
          FROM instruments_on_title
         WHERE executor_full_name ILIKE %s OR notary_name ILIKE %s
         ORDER BY parent_tct_number LIMIT 40
    """, (f"%{name}%", f"%{name}%"))
    return [dict(r) for r in cur.fetchall()]


def t_entity_docs(cur, name):
    cur.execute("""
        SELECT e.canonical_name, e.type, de.doc_id, de.role, left(de.context_excerpt,140) ctx,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename) nm
          FROM entities e JOIN doc_entities de ON de.entity_id=e.id
          JOIN documents d ON d.id=de.doc_id
         WHERE e.canonical_name ILIKE %s OR e.aliases::text ILIKE %s
         ORDER BY de.doc_id LIMIT 30
    """, (f"%{name}%", f"%{name}%"))
    return [{"entity": r["canonical_name"], "type": r["type"], "doc_id": r["doc_id"],
             "role": r["role"], "name": r["nm"], "context": r["ctx"]} for r in cur.fetchall()]


def t_get_doc(cur, doc_id):
    cur.execute("""
        SELECT id, COALESCE(NULLIF(smart_filename,''), original_filename) nm, doc_date,
               classification, COALESCE(summary,'') summary, left(extracted_text,2600) txt
          FROM documents WHERE id=%s
    """, (doc_id,))
    r = cur.fetchone()
    if not r:
        return {"error": f"doc {doc_id} not found"}
    return {"doc_id": r["id"], "name": r["nm"], "date": str(r["doc_date"] or ""),
            "classification": r["classification"], "summary": r["summary"],
            "text_excerpt": r["txt"]}


def t_current_evidence(cur, claim_id):
    cur.execute("SELECT required_to_prove, claim_text FROM claims WHERE id=%s", (claim_id,))
    c = cur.fetchone()
    cur.execute("""SELECT supporting_doc_id, relation_kind, weight, provenance_level
                     FROM evidence_trail WHERE claim_id=%s""", (claim_id,))
    conf = [dict(r) for r in cur.fetchall()]
    cur.execute("""SELECT supporting_doc_id, relation_kind, weight, confidence
                     FROM evidence_trail_proposals WHERE claim_id=%s AND status='pending'""", (claim_id,))
    prop = [dict(r) for r in cur.fetchall()]
    return {"required_to_prove": c["required_to_prove"] if c else None,
            "confirmed": conf, "already_suggested": prop}


def t_semantic_search(cur, query, k=8):
    try:
        import google.generativeai as genai
        from qdrant_client import QdrantClient
        genai.configure(api_key=envk("GEMINI_API_KEY"))
        emb = genai.embed_content(model="models/gemini-embedding-001", content=query,
                                  task_type="RETRIEVAL_QUERY", output_dimensionality=768)
        vec = emb["embedding"]
        qc = QdrantClient(url=envk("QDRANT_URL"), api_key=envk("QDRANT_KEY"), timeout=20)
        hits = qc.search(collection_name="landtek_documents", query_vector=vec, limit=k * 2)
        seen, out = set(), []
        for h in hits:
            did = (h.payload or {}).get("doc_id_postgres")
            if did is None or did in seen:
                continue
            seen.add(did)
            out.append({"doc_id": did, "score": round(h.score, 3),
                        "snippet": (h.payload or {}).get("text", "")[:160]})
            if len(out) >= k:
                break
        return out or {"note": "no semantic hits; use keyword_search"}
    except Exception as e:
        return {"error": f"semantic unavailable ({type(e).__name__}); use keyword_search instead"}


TOOLS = [
    {"name": "semantic_search", "description": "Search the corpus by MEANING (vector). Use for concepts/themes.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "keyword_search", "description": "Exact substring search over full document text. Use for names, title numbers, PE numbers, dates.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "docs_for_title", "description": "Every document that cites a given TCT number (e.g. T-52540).",
     "input_schema": {"type": "object", "properties": {"tct_number": {"type": "string"}}, "required": ["tct_number"]}},
    {"name": "title_chain", "description": "Parent/derivative title edges touching a TCT, with provenance.",
     "input_schema": {"type": "object", "properties": {"tct_number": {"type": "string"}}, "required": ["tct_number"]}},
    {"name": "instruments_on_title", "description": "Encumbrances on a title: executor, authority basis/date, NOTARY, consideration.",
     "input_schema": {"type": "object", "properties": {"tct_number": {"type": "string"}}, "required": ["tct_number"]}},
    {"name": "find_instruments_by_person", "description": "Find every instrument where a person is the EXECUTOR or the NOTARY — reveals the same actor reappearing across titles (deeper link).",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "entity_docs", "description": "Documents co-mentioning a person/org entity, with role + context.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "get_doc", "description": "Read a document's metadata, summary, and text excerpt to VERIFY relevance before proposing it.",
     "input_schema": {"type": "object", "properties": {"doc_id": {"type": "integer"}}, "required": ["doc_id"]}},
    {"name": "current_evidence", "description": "What is already confirmed/suggested for a claim, plus its required_to_prove elements — use to find GAPS and avoid duplicates.",
     "input_schema": {"type": "object", "properties": {"claim_id": {"type": "integer"}}, "required": ["claim_id"]}},
    {"name": "submit_findings", "description": "FINAL step. Submit the evidence you investigated and verified.",
     "input_schema": {"type": "object", "properties": {"findings": {"type": "array", "items": {"type": "object", "properties": {
        "supporting_doc_id": {"type": "integer"},
        "relation_kind": {"type": "string", "enum": list(REL_OK)},
        "weight": {"type": "string", "enum": list(WT_OK)},
        "connection_type": {"type": "string", "enum": list(CONN_OK)},
        "confidence": {"type": "number"},
        "rationale": {"type": "string", "description": "HOW it bears on the claim + the basis you verified (cite the tool result)."}},
        "required": ["supporting_doc_id", "relation_kind", "weight", "connection_type", "confidence", "rationale"]}}},
        "required": ["findings"]}},
]

DISPATCH = {
    "semantic_search": lambda cur, a: t_semantic_search(cur, a["query"]),
    "keyword_search":  lambda cur, a: t_keyword_search(cur, a["query"]),
    "docs_for_title":  lambda cur, a: t_docs_for_title(cur, a["tct_number"]),
    "title_chain":     lambda cur, a: t_title_chain(cur, a["tct_number"]),
    "instruments_on_title": lambda cur, a: t_instruments_on_title(cur, a["tct_number"]),
    "find_instruments_by_person": lambda cur, a: t_find_instruments_by_person(cur, a["name"]),
    "entity_docs":     lambda cur, a: t_entity_docs(cur, a["name"]),
    "get_doc":         lambda cur, a: t_get_doc(cur, a["doc_id"]),
    "current_evidence": lambda cur, a: t_current_evidence(cur, a["claim_id"]),
}

SYSTEM = """You are a senior forensic evidence strategist for a Philippine property-fraud case.
You build court-grade evidence, and you are NOT lazy: you INVESTIGATE with the tools before you
conclude anything. A guess is worthless; a verified link with a cited basis is gold.

Your job for the given CLAIM:
 1. current_evidence(claim) — see what's already covered and what required_to_prove elements are GAPS.
 2. Investigate the corpus to find ADDITIONAL evidence the drafter may have missed: corroboration,
    impeachment of the other side, and documents that fill the gaps.
 3. Hunt DEEPER CONNECTIONS the structured data exposes but a reader wouldn't notice:
      - the SAME executor or SAME notary appearing on multiple instruments (find_instruments_by_person)
      - a title in the chain with no supporting instrument/transfer (a hole in their chain)
      - an entity recurring across documents (entity_docs)
 4. Before proposing any document, get_doc it and confirm it actually says what you think.

Be thorough. Pull every relevant title, instrument, and person. Then call submit_findings with
ONLY the documents you verified, each with an honest confidence and a rationale that cites what
you found. Mark connection_type='deeper_link' for the non-obvious cross-references. Do not propose
documents already confirmed for this claim. Quality over quantity, but do not stop early — if a
thread is open, pull it."""


def call_opus(messages):
    body = json.dumps({"model": OPUS_MODEL, "max_tokens": 8000, "system": SYSTEM,
                       "tools": TOOLS, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(OPUS_URL, data=body, method="POST",
        headers={"x-api-key": envk("ANTHROPIC_API_KEY"), "anthropic-version": OPUS_VER,
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as resp:
        return json.loads(resp.read())


def investigate(cur, claim):
    msg = [{"role": "user", "content":
            f"CLAIM #{claim['id']} [{claim['short_label']}] kind={claim['claim_kind']}\n"
            f"{claim['claim_text']}\n\nInvestigate and submit findings."}]
    findings, tool_calls = None, []
    for rnd in range(MAX_ROUNDS):
        resp = call_opus(msg)
        content = resp.get("content", [])
        msg.append({"role": "assistant", "content": content})
        tool_uses = [b for b in content if b.get("type") == "tool_use"]
        if not tool_uses:
            break
        results = []
        for tu in tool_uses:
            name, args = tu["name"], tu.get("input", {})
            tool_calls.append(name)
            if name == "submit_findings":
                findings = args.get("findings", [])
                results.append({"type": "tool_result", "tool_use_id": tu["id"],
                                "content": "received"})
            else:
                try:
                    out = DISPATCH[name](cur, args)
                except Exception as e:
                    out = {"error": f"{type(e).__name__}: {e}"}
                results.append({"type": "tool_result", "tool_use_id": tu["id"],
                                "content": json.dumps(out, default=str)[:6000]})
        if findings is not None:
            msg.append({"role": "user", "content": results})
            break
        if rnd >= MAX_ROUNDS - 3:
            results.append({"type": "text", "text":
                "INVESTIGATION BUDGET NEARLY EXHAUSTED. In your next turn call submit_findings "
                "with EVERY document you have already verified — do not call any other tool, do "
                "not start new threads. If you verified nothing worth proposing, submit an empty list."})
        msg.append({"role": "user", "content": results})
    return findings or [], tool_calls


def valid_doc_ids(cur):
    cur.execute("SELECT id FROM documents")
    return {r["id"] for r in cur.fetchall()}


def insert_findings(cur, claim_id, findings, doc_ids):
    n, kept = 0, []
    for f in findings:
        try:
            did = int(f["supporting_doc_id"])
            conf = float(f["confidence"])
        except (KeyError, TypeError, ValueError):
            continue
        if did not in doc_ids or f.get("relation_kind") not in REL_OK or f.get("weight") not in WT_OK:
            continue
        ctype = f.get("connection_type", "direct_support")
        narrative = (f.get("rationale") or "")[:600]
        cur.execute("""
            INSERT INTO evidence_trail_proposals
              (claim_id, supporting_doc_id, relation_kind, weight, narrative, confidence, rationale)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (claim_id, supporting_doc_id) DO NOTHING RETURNING id
        """, (claim_id, did, f["relation_kind"], f["weight"], narrative, round(conf, 2),
              f"strategist[{ctype}]: {narrative[:200]}"))
        if cur.fetchone():
            n += 1
            kept.append((did, ctype, f["weight"], round(conf, 2), narrative[:90]))
    return n, kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--claim", type=int)
    ap.add_argument("--case", default="MWK-001")
    args = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if args.claim:
        cur.execute("SELECT id, short_label, claim_text, claim_kind FROM claims WHERE id=%s", (args.claim,))
    else:
        cur.execute("SELECT id, short_label, claim_text, claim_kind FROM claims WHERE case_file=%s AND status='open' ORDER BY priority DESC, id", (args.case,))
    claims = cur.fetchall()
    if not claims:
        print("no matching claims"); return
    doc_ids = valid_doc_ids(cur)
    total = 0
    for claim in claims:
        print(f"\n=== investigating claim #{claim['id']} [{claim['short_label']}] ===")
        findings, calls = investigate(cur, claim)
        print(f"  tools used: {', '.join(calls) or '(none)'}")
        n, kept = insert_findings(cur, claim["id"], findings, doc_ids)
        total += n
        print(f"  {n} NEW proposals ({len(findings)} returned):")
        for did, ctype, wt, conf, why in kept:
            print(f"    doc#{did}  {ctype}/{wt}  conf={conf}  {why}")
    print(f"\n[strategist] {total} new evidence proposals across {len(claims)} claim(s) -> review queue")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
