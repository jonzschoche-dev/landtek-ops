#!/usr/bin/env python3
"""tool_routes.py — the spine's TOOL surface (agent_specs/004 §what-moves-where, deploy_966).

One brain for every communication tool: the capabilities that lived only in the retired per-channel
Anthropic loop (vault queries · document lookup/search) become deterministic, governed PURPOSE ROUTES
of the ONE spine — so Telegram, Messenger, and every future channel answer them identically, $0,
preformed, ≤280, honest.

READ-ONLY by design: vault WRITES (register/bind) stay with the explicit deterministic vault command
handler — a write is never inferred from conversation. semantic_search is deliberately NOT ported as
a primary route (measured ~9% recall — feedback-retrieval-bottleneck-is-upstream); typed/deterministic
lookups only.

  try_tool_route(cur, client_code, message) -> {text, via, preformed, purpose} | None
"""
import json
import os
import re
import urllib.parse
import urllib.request

LEO_TOOLS_BASE = os.environ.get("LEO_TOOLS_BASE", "http://127.0.0.1:8765")
DOCBASE = "https://leo.hayuma.org"
_SECT_NUM_RE = re.compile(r"\b(AFF|TCT|SPA|DEED|TAX|PSA|ID|CRT|RES|CONT|CORR|MISC)[\s\-]?(\d{1,3})\b", re.I)


def _http_get(path, **params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{LEO_TOOLS_BASE}{path}" + (f"?{qs}" if qs else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"http_get_failed: {e}"}


# ── intent classification (deterministic, anchored — mirrors the vault handler's vocabulary) ────────
def _vault_intent(text):
    t = (text or "").lower().strip()
    if not t or "vault" not in t and not re.match(r"^(queue|what'?s?\s+pending|missing|last|find\s+)", t):
        # require the word 'vault' OR a vault-verb opener, so ordinary chat never trips this
        if not re.search(r"\bvault\b", t):
            return None
    if _SECT_NUM_RE.search(text or "") and re.search(r"\b(find|where|what)\b", t):
        return "find"
    if re.search(r"\b(queue|pending)\b", t):
        return "queue"
    if re.search(r"\bmissing\b", t):
        return "missing"
    if re.search(r"\b(last|recent)\b", t):
        return "last"
    if re.search(r"\bvault\b", t) and re.search(r"\b(status|state|how|what)\b", t):
        return "queue"
    return None


_DOC_ID_RE = re.compile(r"(?i)\b(?:doc|document)\s*(?:no\.?|#|id)?\s*(\d{2,5})\b")
_DOC_SEARCH_RE = re.compile(r"(?i)\b(?:find|search|look\s+for|locate)\b.{0,20}\b(?:doc|document|file)s?\b"
                            r"\s*(?:about|for|on|named|called|re)?\s*(.{3,60})")


# ── executors (read-only; A5 wall in the SQL) ───────────────────────────────────────────────────────
def _vault_route(cur, intent, message):
    if intent == "find":
        m = _SECT_NUM_RE.search(message)
        if not m:
            return "Which vault entry? Like: find AFF-1."
        r = _http_get("/api/vault/find", section=m.group(1).upper(), number=int(m.group(2)))
        if r.get("ok"):
            mats = ", ".join(r.get("matter_codes") or []) or "no matter linked"
            scan = "scan attached" if r.get("digital_scan_id") else "no scan yet"
            return (f"{m.group(1).upper()}-{int(m.group(2)):03d}: {r.get('smart_filename')}. "
                    f"Matter: {mats}. {scan}. Cabinet: {r.get('vault_location') or 'no location noted'}.")
        return f"Nothing at {m.group(1).upper()}-{int(m.group(2)):03d} yet."
    if intent == "queue":
        r = _http_get("/api/vault/queue")
        if not r.get("ok", True) and r.get("error"):
            return None                                     # endpoint down → let the spine degrade honestly
        n = (r.get("counts") or {}).get("pending_scans", 0)
        if not n:
            return "Nothing pending right now. Vault is current."
        names = "; ".join(it.get("smart_filename", "?") for it in (r.get("pending_scans") or [])[:3])
        return f"{n} vault {'entry' if n == 1 else 'entries'} waiting for a scan. Top: {names}."
    if intent == "missing":
        return None                                         # needs a matter resolver — the vault handler's ask-back owns this
    if intent == "last":
        m = re.search(r"\b(\d{1,2})\b", message)
        n = max(1, min(int(m.group(1)) if m else 5, 20))
        r = _http_get("/api/vault/last", n=n)
        entries = r.get("entries") or []
        if not entries:
            return "Vault is empty so far." if r.get("ok", True) else None
        lines = "; ".join(f"{e['vault_section']}-{e['vault_number']:03d}" for e in entries[:5])
        return f"Last {min(n, len(entries))} vault entries: {lines}."
    return None


def _doc_lookup(cur, client_code, doc_id):
    """One document by id — A5: only within the asker's client family; honest no-record otherwise."""
    fam = (client_code or "").split("-")[0]
    if not fam:
        return None
    cur.execute("""SELECT id, coalesce(document_title, smart_filename, original_filename, '') AS name,
                          coalesce(case_file, matter_code, '') AS cf, doc_date
                     FROM documents WHERE id=%s""", (doc_id,))
    r = cur.fetchone()
    row = dict(r) if r else None
    if not row:
        return f"No record of doc {doc_id} in the corpus."
    if not (row["cf"] or "").upper().startswith(fam.upper()):
        return f"No record of doc {doc_id} in this client's corpus."     # A5: never confirm other-family docs
    when = f" ({row['doc_date']})" if row.get("doc_date") else ""
    return f"doc:{doc_id} — {row['name'][:120]}{when}. {DOCBASE}/files/c/{doc_id}"


def _doc_search(cur, client_code, terms):
    """Deterministic filename/title search, client-walled, top 3 — NEVER semantic."""
    fam = (client_code or "").split("-")[0]
    terms = (terms or "").strip().rstrip("?.!").strip()
    if not fam or len(terms) < 3:
        return None
    like = f"%{terms}%"
    cur.execute("""SELECT id, coalesce(document_title, smart_filename, original_filename,'') AS name
                     FROM documents
                    WHERE (case_file ILIKE %s OR matter_code ILIKE %s)
                      AND (document_title ILIKE %s OR smart_filename ILIKE %s OR original_filename ILIKE %s)
                    ORDER BY id DESC LIMIT 3""", (fam + "%", fam + "%", like, like, like))
    rows = cur.fetchall()
    rows = [dict(r) for r in rows] if rows else []
    if not rows:
        return f"No documents matching “{terms[:40]}” in this client's corpus."
    lines = "; ".join(f"doc:{r['id']} {r['name'][:45]}" for r in rows)
    return f"{len(rows)} match(es): {lines}."


# ── the one entry point the spine calls ─────────────────────────────────────────────────────────────
def try_tool_route(cur, client_code, message):
    """Deterministic tool routes for every channel — same brain, same answers. Returns None fast when
    no tool intent is present (ordinary conversation is untouched)."""
    if not (message or "").strip():
        return None
    intent = _vault_intent(message)
    if intent:
        text = _vault_route(cur, intent, message)
        if text:
            return {"text": text[:280], "via": f"tool:vault_{intent}", "preformed": True,
                    "purpose": "vault"}
    m = _DOC_ID_RE.search(message)
    if m:
        text = _doc_lookup(cur, client_code, int(m.group(1)))
        if text:
            return {"text": text[:280], "via": "tool:doc_lookup", "preformed": True, "purpose": "doc_lookup"}
    m = _DOC_SEARCH_RE.search(message)
    if m:
        text = _doc_search(cur, client_code, m.group(1))
        if text:
            return {"text": text[:280], "via": "tool:doc_search", "preformed": True, "purpose": "doc_search"}
    return None
