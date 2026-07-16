#!/usr/bin/env python3
"""corpus_answer.py — purpose-aware, deterministic answers from the SoR.

Companion to title_fetch.py. The headless LLM only sees a tiny fact window
(12 latest verified rows) — so questions like "how many ARTA cases went to the
OP?" answer "none" even when matters/MWK-OP-PETITION exist. This module
classifies the ask and answers from the right tables BEFORE Ollama invents
ignorance.

A85: one ability shared by Messenger + Telegram (called from leo_service).
A5: client-scoped. A71: dosed lists (not full dumps).
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

# (purpose, keywords) — first match wins
_PURPOSES = (
    ("arta_op_referrals", (
        "arta", "op ", " op?", "office of the president", "executive secretary",
        "referred to the op", "referr", "bagong pilipinas",
    )),
    ("matter_inventory", (
        "how many case", "how many matter", "list my case", "list cases",
        "what cases", "which cases", "active matter", "our cases",
    )),
    ("matter_status", (
        "status of", "what's the status", "what is the status", "where is",
        "update on",
    )),
)


def classify_purpose(message: str) -> Optional[str]:
    t = (message or "").lower()
    # ARTA→OP needs both families of signal when counting referrals
    if ("arta" in t or "ctn" in t) and any(
        k in t for k in (
            "op", "office of the president", "executive secretary",
            "referr", "bagong pilipinas", "supervisory",
        )
    ):
        return "arta_op_referrals"
    if any(k in t for k in ("how many", "count", "list")) and any(
        k in t for k in ("arta", "case", "matter", "complaint")
    ):
        if "arta" in t:
            return "arta_inventory"
        return "matter_inventory"
    for purpose, keys in _PURPOSES:
        if purpose == "arta_op_referrals":
            continue
        if any(k in t for k in keys):
            return purpose
    return None


def _g(row, key):
    return row.get(key) if isinstance(row, dict) else None


def answer_arta_op_referrals(cur, client_code: str) -> str:
    """Grounded inventory: ARTA matters that touch OP / ES / supervisory path."""
    fam = (client_code or "").split("-")[0] + "%"
    cur.execute("""
        SELECT matter_code, title, status, current_stage, forum, court_or_agency
          FROM matters
         WHERE (client_code = %s OR client_code LIKE %s OR matter_code LIKE %s)
           AND matter_code NOT LIKE 'AUTO-%%'
           AND (
                matter_code ILIKE '%%OP%%'
             OR matter_code ILIKE '%%ARTA%%'
             OR coalesce(forum,'') ILIKE '%%President%%'
             OR coalesce(forum,'') ILIKE '%% OP%%'
             OR coalesce(court_or_agency,'') ILIKE '%%President%%'
             OR coalesce(court_or_agency,'') ILIKE '%%Executive Secretary%%'
             OR coalesce(title,'') ILIKE '%%Office of the President%%'
             OR coalesce(title,'') ILIKE '%%supervisory%%'
             OR coalesce(current_stage,'') ILIKE '%%op_%%'
             OR coalesce(current_stage,'') ILIKE '%%op %%'
           )
         ORDER BY matter_code
    """, (client_code, fam, fam))
    rows = cur.fetchall() or []

    # Split: clear OP path vs ARTA-only
    op_path, arta_only = [], []
    for r in rows:
        blob = " ".join(str(_g(r, k) or "") for k in (
            "matter_code", "title", "forum", "court_or_agency", "current_stage",
        )).lower()
        if any(x in blob for x in (
            "office of the president", "executive secretary", "op petition",
            "op_", " op", "bagong pilipinas", "supervisory review",
        )) or str(_g(r, "matter_code") or "").upper().startswith("MWK-OP"):
            op_path.append(r)
        elif "arta" in blob:
            arta_only.append(r)

    lines = [
        f"ARTA / OP path — grounded from matters table (client {client_code}):",
        f"Matters on an OP / Executive Secretary / supervisory path: {len(op_path)}",
    ]
    for r in op_path[:12]:
        lines.append(
            f"• {_g(r, 'matter_code')}: {_g(r, 'status') or '—'} · "
            f"{(_g(r, 'current_stage') or '—')[:50]}"
        )
        title = (_g(r, "title") or "")[:90]
        if title:
            lines.append(f"  {title}")
        venue = (_g(r, "court_or_agency") or _g(r, "forum") or "")[:80]
        if venue:
            lines.append(f"  venue: {venue}")

    if arta_only:
        lines.append(f"Other active/closed ARTA matters (not clearly OP-bound): {len(arta_only)}")
        for r in arta_only[:8]:
            lines.append(
                f"• {_g(r, 'matter_code')}: {_g(r, 'status') or '—'} · "
                f"{(_g(r, 'current_stage') or '—')[:40]}"
            )

    if not op_path and not arta_only:
        lines.append(
            "No ARTA/OP matter rows matched in this client scope. "
            "That is a record gap — not a confident 'zero referrals'."
        )
    else:
        lines.append(
            "Source: matters (not chat memory). "
            "If you need filings/docs for one code, ask: fetch docs for MWK-ARTA-…"
        )
    return "\n".join(lines)


def answer_arta_inventory(cur, client_code: str) -> str:
    fam = (client_code or "").split("-")[0] + "%"
    cur.execute("""
        SELECT matter_code, status, current_stage, title
          FROM matters
         WHERE (client_code = %s OR matter_code LIKE %s)
           AND matter_code ILIKE '%%ARTA%%'
           AND matter_code NOT LIKE 'AUTO-%%'
         ORDER BY matter_code
    """, (client_code, fam))
    rows = cur.fetchall() or []
    active = [r for r in rows if str(_g(r, "status") or "").lower() == "active"]
    lines = [
        f"ARTA matters in scope ({client_code}): {len(rows)} total, {len(active)} active.",
    ]
    for r in (active or rows)[:15]:
        lines.append(
            f"• {_g(r, 'matter_code')}: {_g(r, 'status')} · "
            f"{(_g(r, 'current_stage') or '—')[:45]}"
        )
    if len(rows) > 15:
        lines.append(f"… +{len(rows)-15} more")
    return "\n".join(lines)


def answer_matter_inventory(cur, client_code: str) -> str:
    fam = (client_code or "").split("-")[0] + "%"
    cur.execute("""
        SELECT status, count(*) n FROM matters
         WHERE (client_code = %s OR matter_code LIKE %s)
           AND matter_code NOT LIKE 'AUTO-%%'
         GROUP BY 1 ORDER BY 2 DESC
    """, (client_code, fam))
    by = cur.fetchall() or []
    cur.execute("""
        SELECT matter_code, status, current_stage FROM matters
         WHERE (client_code = %s OR matter_code LIKE %s)
           AND matter_code NOT LIKE 'AUTO-%%'
           AND coalesce(status,'') = 'active'
         ORDER BY matter_code LIMIT 20
    """, (client_code, fam))
    active = cur.fetchall() or []
    lines = [f"Matters for {client_code} (from matters table):"]
    for r in by:
        lines.append(f"• {_g(r, 'status') or 'NULL'}: {_g(r, 'n')}")
    if active:
        lines.append("Active:")
        for r in active:
            lines.append(f"  {_g(r, 'matter_code')} · {(_g(r, 'current_stage') or '—')[:40]}")
    return "\n".join(lines)


def try_corpus_answer(cur, client_code: Optional[str], message: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (answer, purpose) if a deterministic corpus path applies; else (None, None)."""
    if not client_code:
        return None, None
    purpose = classify_purpose(message or "")
    if not purpose:
        return None, None
    try:
        if purpose == "arta_op_referrals":
            return answer_arta_op_referrals(cur, client_code), purpose
        if purpose == "arta_inventory":
            return answer_arta_inventory(cur, client_code), purpose
        if purpose == "matter_inventory":
            return answer_matter_inventory(cur, client_code), purpose
        # matter_status: leave to LLM for now once RC retrieves better facts
        return None, purpose
    except Exception as e:
        return None, f"error:{type(e).__name__}:{e}"
