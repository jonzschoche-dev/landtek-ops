#!/usr/bin/env python3
"""title_fetch.py — deterministic corpus title pack (A85: one ability, shared).

Used by Telegram llm handler and Messenger/headless leo_service. Ollama cannot
call tools; when a human asks to fetch a title we answer from documents +
property_assets with real https://leo.hayuma.org/files/c/<id> links — never a
promise without delivery.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import psycopg2.extras

PUBLIC_FILE = "https://leo.hayuma.org/files/c"


def title_token_from_message(text: str) -> Optional[str]:
    t = text or ""
    m = re.search(
        r"\b(?:TCT|T)[\s\-–#]*([0-9]{3,7}(?:[\-/][0-9]{1,7})?)\b",
        t, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"\btitle\s+(?:no\.?|number|#)?\s*([0-9]{3,7})\b", t, re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def wants_title_fetch(text: str) -> bool:
    t = (text or "").lower()
    if not any(k in t for k in (
        "fetch", "send me", "get me", "give me", "download", "link to",
        "pull the", "pull me", "hanapin", "ibigay", "padala",
    )):
        return False
    return bool(
        "title" in t or "tct" in t or "titulo" in t
        or title_token_from_message(text)
    )


def fetch_title_pack(cur, client_code: Optional[str], text: str) -> tuple[Optional[str], Optional[str]]:
    """Build a plain-text title pack. cur is a RealDictCursor (or compatible).

    Returns (pack_text, error). pack_text is None only on hard failure.
    """
    token = title_token_from_message(text)
    if not token:
        return (
            "Which title? Send the TCT number (e.g. fetch me title TCT 32911).",
            None,
        )
    if not client_code:
        return (
            "I can only pull titles for an approved client scope. "
            "Your channel identity is not bound to a client yet.",
            None,
        )

    like = f"%{token}%"
    fam = client_code.split("-")[0] + "%"
    tct_like = f"%TCT%{token}%"
    t_dash = f"%T-{token}%"

    try:
        cur.execute("""
            SELECT a.asset_code, a.title_ref, a.label, a.title_status, a.client_code,
                   r.readiness_score, r.documents, r.documents_note, r.next_prep_action
              FROM property_assets a
              LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
             WHERE a.title_ref ILIKE %s OR a.asset_code ILIKE %s OR a.label ILIKE %s
             ORDER BY a.asset_code LIMIT 3
        """, (like, like, like))
        assets = cur.fetchall()

        cur.execute("""
            SELECT d.id,
                   COALESCE(NULLIF(d.smart_filename,''), d.original_filename, 'Document') AS name,
                   d.matter_code, d.case_file,
                   (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL) AS downloadable,
                   CASE
                     WHEN COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s THEN 0
                     WHEN COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s
                       OR COALESCE(d.smart_filename,'') ILIKE %s
                       OR COALESCE(d.original_filename,'') ILIKE %s THEN 1
                     ELSE 2
                   END AS rank
              FROM documents d
             WHERE (
                    d.case_file = %s
                 OR d.case_file LIKE %s
                 OR d.matter_code LIKE %s
                 OR (d.case_file IN ('MWK-001', 'Owner') AND %s LIKE 'MWK%%')
             )
               AND (
                    COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.extracted_text,'') ILIKE %s
                 OR COALESCE(d.extracted_text,'') ILIKE %s
               )
             ORDER BY rank ASC, downloadable DESC, d.id DESC
             LIMIT 12
        """, (
            like, like, tct_like, tct_like, t_dash, t_dash,
            client_code, fam, fam, client_code,
            like, like, tct_like, tct_like, t_dash, t_dash,
            tct_like, t_dash,
        ))
        ranked = list(cur.fetchall() or [])

        def _rank(d: Any) -> int:
            if isinstance(d, dict):
                return int(d.get("rank") or 2)
            return 2

        strong = [d for d in ranked if _rank(d) <= 1]
        docs = strong if strong else ranked[:5]
    except Exception as e:
        return None, f"title_fetch_db:{type(e).__name__}:{e}"

    def _g(row, key, idx=None):
        if isinstance(row, dict):
            return row.get(key)
        return row[idx] if idx is not None else None

    lines = [f"Title pack for TCT / T-{token}:"]
    if assets:
        for a in assets:
            sc = _g(a, "readiness_score", 5)
            try:
                scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
            except Exception:
                scs = "?"
            lines.append(
                f"• {_g(a, 'title_ref', 1) or _g(a, 'asset_code', 0)} "
                f"({_g(a, 'client_code', 4) or '—'}) status={_g(a, 'title_status', 3) or '—'} "
                f"readiness={scs} docs={_g(a, 'documents', 6) or '?'}"
            )
            note = (_g(a, "documents_note", 7) or "")[:120]
            if note:
                lines.append(f"  note: {note}")
            nxt = (_g(a, "next_prep_action", 8) or "")[:140]
            if nxt:
                lines.append(f"  next: {nxt}")
    else:
        lines.append(
            f"• No property_assets row matched T-{token} yet "
            "(title may still be in documents only)."
        )

    dl_docs = [d for d in docs if _g(d, "downloadable", 4)]
    other = [d for d in docs if not _g(d, "downloadable", 4)]
    if dl_docs:
        lines.append("Downloadable from the corpus:")
        for d in dl_docs[:8]:
            name = (_g(d, "name", 1) or "Document")[:90]
            did = _g(d, "id", 0)
            lines.append(f"• {name}")
            lines.append(f"  {PUBLIC_FILE}/{did}")
    if other and not dl_docs:
        lines.append("Named in the record but no file bytes on disk/Drive yet:")
        for d in other[:5]:
            lines.append(f"• {(_g(d, 'name', 1) or 'Document')[:90]} (doc {_g(d, 'id', 0)})")
    if not docs:
        lines.append(
            "No document filename hit for that number in your scope. "
            "We may still need a CTC from the Registry of Deeds."
        )
    lines.append(
        "I am not inventing a file — only linking what is already in the LandTek corpus."
    )
    return "\n".join(lines), None
