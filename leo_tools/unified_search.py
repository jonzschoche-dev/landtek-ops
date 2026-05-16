"""Unified search endpoint — deploy_085.

GET /api/search?q=<text>&limit=<N>&case=<MWK-001|Paracale-001|Owner|>

Searches across:
  - documents (original_filename, smart_filename, extracted_text)
  - chat_notes (content, summary)
  - conversations (message_caption, leo_response)
  - entities (canonical_name, aliases)

Returns merged ranked results. Per-kind soft cap so one type doesn't
drown the others. Snippets contain the matched query for clarity.

Powered by Postgres ILIKE for simplicity + portability. Full-text +
trigram + Qdrant semantic ranking are next iterations.
"""
import os
import re
from flask import Blueprint, request, jsonify
import psycopg2

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

bp = Blueprint("unified_search", __name__)


def _db():
    return psycopg2.connect(PG_DSN)


def _snippet(text, q, length=160):
    if not text:
        return ""
    text = str(text)
    lower = text.lower()
    qlow = q.lower()
    idx = lower.find(qlow)
    if idx < 0:
        return text[:length] + ("…" if len(text) > length else "")
    start = max(0, idx - 40)
    end = min(len(text), idx + len(q) + length - 40)
    s = text[start:end]
    if start > 0:
        s = "…" + s
    if end < len(text):
        s = s + "…"
    return s


@bp.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"error": "q must be at least 2 chars"}), 400
    limit = min(int(request.args.get("limit", 30)), 100)
    case = request.args.get("case", "").strip() or None

    per_kind_cap = max(5, limit // 4)
    like = "%" + q + "%"
    args_case = [case] if case else []
    case_clause = "AND case_file = %s" if case else ""

    results = []
    conn = _db(); cur = conn.cursor()

    # 1) documents
    cur.execute(f"""
        SELECT id, case_file, original_filename, smart_filename, content_hash,
               file_path, drive_link, drive_file_id,
               LEFT(coalesce(extracted_text,''), 4000) AS body_excerpt
          FROM documents
         WHERE (
           coalesce(original_filename,'') ILIKE %s
           OR coalesce(smart_filename,'') ILIKE %s
           OR coalesce(extracted_text,'') ILIKE %s
         ) {case_clause}
         ORDER BY id DESC
         LIMIT %s;
    """, [like, like, like, *args_case, per_kind_cap])
    for r in cur.fetchall():
        (doc_id, cf, orig, smart, h, fp, dl, dfi, body) = r
        title = orig or smart or f"DOC {doc_id}"
        score = 0
        if orig and q.lower() in orig.lower(): score += 3
        if smart and q.lower() in smart.lower(): score += 2
        if body and q.lower() in body.lower(): score += 1
        results.append({
            "kind": "document",
            "id": doc_id,
            "title": title,
            "snippet": _snippet(orig + " — " + (body or ""), q),
            "case_file": cf,
            "drive_link": dl,
            "dashboard": f"https://leo.hayuma.org/files/{doc_id}",
            "local_path": fp,
            "score": score + (2 if cf == case else 0),
        })

    # 2) chat_notes  (column is related_case not case_file)
    notes_case_clause = "AND related_case = %s" if case else ""
    cur.execute(f"""
        SELECT id, related_case, topic, importance, summary, content, created_at
          FROM chat_notes
         WHERE (coalesce(content,'') ILIKE %s OR coalesce(summary,'') ILIKE %s)
           {notes_case_clause}
         ORDER BY id DESC
         LIMIT %s;
    """, [like, like, *args_case, per_kind_cap])
    for r in cur.fetchall():
        (nid, cf, topic, imp, summary, content, ts) = r
        results.append({
            "kind": "chat_note",
            "id": nid,
            "title": summary or (content[:80] if content else f"Note {nid}"),
            "snippet": _snippet(content, q),
            "case_file": cf,
            "topic": topic,
            "importance": imp,
            "timestamp": str(ts) if ts else None,
            "score": 2,
        })

    # 3) conversations
    cur.execute(f"""
        SELECT id, case_file, client_name, message_caption, leo_response, timestamp
          FROM conversations
         WHERE (coalesce(message_caption,'') ILIKE %s OR coalesce(leo_response,'') ILIKE %s)
           {case_clause}
         ORDER BY id DESC
         LIMIT %s;
    """, [like, like, *args_case, per_kind_cap])
    for r in cur.fetchall():
        (cid, cf, client, msg, leo, ts) = r
        body = (msg or "") + " | " + (leo or "")
        results.append({
            "kind": "conversation",
            "id": cid,
            "title": f"{client or 'unknown'}: {(msg or '')[:60]}",
            "snippet": _snippet(body, q),
            "case_file": cf,
            "timestamp": str(ts) if ts else None,
            "score": 1,
        })

    # 4) entities
    cur.execute("""
        SELECT id, type, canonical_name, aliases, mentions_count, notes
          FROM entities
         WHERE coalesce(canonical_name,'') ILIKE %s
            OR EXISTS (SELECT 1 FROM unnest(coalesce(aliases, ARRAY[]::text[])) a WHERE a ILIKE %s)
            OR coalesce(notes,'') ILIKE %s
         ORDER BY mentions_count DESC NULLS LAST, id DESC
         LIMIT %s;
    """, [like, like, like, per_kind_cap])
    for r in cur.fetchall():
        (eid, etype, name, aliases, mentions, notes) = r
        results.append({
            "kind": "entity",
            "id": eid,
            "title": f"{etype}: {name}",
            "snippet": (notes or f"aliases: {', '.join(aliases or [])}")[:200],
            "type": etype,
            "mentions_count": mentions or 0,
            "aliases": aliases or [],
            "score": 1 + min(3, (mentions or 0) // 5),
        })

    cur.close(); conn.close()

    # Sort by score then per-kind slot
    results.sort(key=lambda r: (-r["score"], r["kind"], -r["id"]))
    results = results[:limit]

    return jsonify({
        "query": q,
        "case_filter": case,
        "count": len(results),
        "results": results,
    })
