#!/usr/bin/env python3
"""title_fetch.py — deterministic corpus title pack (A85: one ability, shared).

Used by Telegram llm handler and Messenger/headless leo_service. Ollama cannot
call tools; when a human asks to fetch a title we answer from documents +
property_assets with real https://leo.hayuma.org/files/c/<id> links — never a
promise without delivery.

Equilibrium (A71 dose): a NARROW request returns ONE primary document + status,
not a dump. Say "all" / "pack" / "related" for a small related set (cap 3).

Security (honest):
  * A25: requires resolved client_code (no cross-client invent).
  * Query scoped to that client family (A5 wall at SELECT).
  * A21: delivery still goes through leo_service send gate (internal auto /
    outward HOLD).
  * /files/c/<id> is intentionally unauthenticated (operator phone stream) —
    releasing a link IS disclosure. Prefer dose-1; never bulk-leak for "fetch one".
"""
from __future__ import annotations

import re
from typing import Any, Optional

PUBLIC_FILE = "https://leo.hayuma.org/files/c"

# A71: narrow request → one file. Explicit wideners → small pack.
WIDEN_PHRASES = (
    "all", "pack", "related", "everything", "full set", "lahat", "mga docs",
    "all docs", "all documents", "title pack",
)
PRIMARY_CAP = 1
WIDE_CAP = 3


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


def _wants_wide(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in WIDEN_PHRASES)


def _g(row, key, idx=None):
    if isinstance(row, dict):
        return row.get(key)
    return row[idx] if idx is not None else None


def _name_has_token(name: str, token: str) -> bool:
    n = (name or "").lower()
    t = token.lower()
    return t in n and (
        f"tct" in n or f"t-{t}" in n or f"t {t}" in n
        or f"tct-{t}" in n or f"tct {t}" in n
        or f"_{t}" in n or f"-{t}" in n or n.startswith(t)
    )


def fetch_title_pack(cur, client_code: Optional[str], text: str) -> tuple[Optional[str], Optional[str]]:
    """Build a dose-aware plain-text title reply. cur is a RealDictCursor (or compatible)."""
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

    wide = _wants_wide(text)
    cap = WIDE_CAP if wide else PRIMARY_CAP
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
             WHERE (a.client_code = %s OR a.client_code LIKE %s OR a.case_file = %s)
               AND (a.title_ref ILIKE %s OR a.asset_code ILIKE %s OR a.label ILIKE %s)
             ORDER BY a.asset_code LIMIT 1
        """, (client_code, fam, client_code, like, like, like))
        assets = cur.fetchall()
        # Fallback without client filter only if exact title_ref match in family already empty
        if not assets:
            cur.execute("""
                SELECT a.asset_code, a.title_ref, a.label, a.title_status, a.client_code,
                       r.readiness_score, r.documents, r.documents_note, r.next_prep_action
                  FROM property_assets a
                  LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
                 WHERE a.title_ref ILIKE %s OR a.asset_code ILIKE %s
                 ORDER BY a.asset_code LIMIT 1
            """, (like, like))
            assets = cur.fetchall()
            # A5: refuse foreign client assets
            assets = [
                a for a in assets
                if str(_g(a, "client_code", 4) or "").startswith(client_code.split("-")[0])
            ]

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
             )
               AND (
                    COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
                 OR COALESCE(d.smart_filename,'') ILIKE %s
                 OR COALESCE(d.original_filename,'') ILIKE %s
               )
             ORDER BY rank ASC, downloadable DESC, d.id DESC
             LIMIT 20
        """, (
            like, like, tct_like, tct_like, t_dash, t_dash,
            client_code, fam, fam,
            like, like, tct_like, tct_like, t_dash, t_dash,
        ))
        ranked = list(cur.fetchall() or [])
    except Exception as e:
        return None, f"title_fetch_db:{type(e).__name__}:{e}"

    def _rank(d: Any) -> int:
        if isinstance(d, dict):
            return int(d.get("rank") or 2)
        return 2

    # Prefer filename that actually carries the title number (not mere "TCT" noise)
    primary_pool = [
        d for d in ranked
        if _rank(d) <= 1 and _g(d, "downloadable", 4)
        and _name_has_token(str(_g(d, "name", 1) or ""), token)
    ]
    secondary_pool = [
        d for d in ranked
        if _rank(d) <= 1 and _g(d, "downloadable", 4) and d not in primary_pool
    ]
    # Body-only (rank 2) never auto-released on narrow request
    pool = primary_pool or secondary_pool
    total_related = len(pool)
    chosen = pool[:cap]
    withheld = max(0, total_related - len(chosen))

    lines = []
    # Status — one line (equilibrium: not a dashboard dump)
    if assets:
        a = assets[0]
        sc = _g(a, "readiness_score", 5)
        try:
            scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
        except Exception:
            scs = "?"
        lines.append(
            f"T-{token} ({_g(a, 'client_code', 4) or client_code}): "
            f"status={_g(a, 'title_status', 3) or '—'} · readiness={scs} · "
            f"docs={_g(a, 'documents', 6) or '?'}"
        )
    else:
        lines.append(f"T-{token}: no property_assets row yet (documents only).")

    if chosen:
        if wide:
            lines.append(f"Related corpus files ({len(chosen)} of {total_related}):")
        else:
            lines.append("Primary file (narrow fetch — one document):")
        for d in chosen:
            name = (_g(d, "name", 1) or "Document")[:90]
            did = _g(d, "id", 0)
            lines.append(f"• {name}")
            lines.append(f"  {PUBLIC_FILE}/{did}")
        if withheld and not wide:
            lines.append(
                f"+ {withheld} more related in corpus. "
                f"Reply: more TCT {token}   (or: full pack TCT {token})"
            )
    else:
        lines.append(
            "No downloadable file whose name matches that title number in your scope. "
            "We may still need a CTC from the Registry of Deeds."
        )

    # Honest security footer (short — operator visibility, not a lecture)
    lines.append(
        "Scope: client-bound query only. "
        "Link is a live corpus stream (/files/c) — treat as confidential."
    )
    return "\n".join(lines), None
