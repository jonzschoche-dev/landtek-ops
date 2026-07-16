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


def _is_op_bound_fact(statement: str) -> bool:
    """True only if the verified statement evidences a filing/address to OP/ES.

    Rejects soft advocacy ('properly before OP', 'without prejudice… simultaneously
    filed') and other-agency referrals. Accepts petition addressed to ES/OP or an
    explicit Petition for Supervisory Review and Corrective Action filing.
    """
    s = (statement or "").lower()
    if not s:
        return False
    # Soft / non-filing language — do not promote to "sent to OP"
    if "without prejudice" in s:
        return False
    if "properly before the office of the president" in s and "filed" not in s:
        return False
    if "ombudsman" in s and "executive secretary" not in s and "office of the president" not in s:
        return False
    if re.search(r"\bdilg\b", s) and "executive secretary" not in s:
        return False
    if re.search(r"\bcsc\b", s) and "executive secretary" not in s:
        return False
    if "referred to mayor" in s or (
        "mayor pajarillo" in s and "president" not in s and "executive secretary" not in s
    ):
        return False

    # Hard OP/ES address
    if "executive secretary" in s or "ralph g. recto" in s:
        return True
    if "office of the president" in s and any(
        x in s for x in ("addressed", "filed with", "filed 0", "filed on", "copy furnished")
    ):
        return True
    # Operative petition filing (May 2026 supervisory review package)
    if (
        "petition for supervisory review" in s
        and "corrective action" in s
        and any(x in s for x in ("filed", "files the petition", "petitioner files"))
    ):
        return True
    return False


def answer_arta_op_referrals(cur, client_code: str) -> str:
    """Cold professional brief: only matters with *verified* OP/ES-bound evidence.

    Counts distinct ARTA CTN-style matter_codes that the verified record ties to
    an Office of the President / Executive Secretary supervisory filing — not
    every row that merely mentions 'OP' in a stage string or program label.
    """
    fam = (client_code or "").split("-")[0] + "%"

    # 1) Verified facts that are truly OP/ES-bound (evidence, not labels)
    cur.execute("""
        SELECT matter_code, statement, source_id, updated_at
          FROM matter_facts
         WHERE matter_code LIKE %s
           AND provenance_level = 'verified'
           AND coalesce(statement, '') <> ''
           AND (
                statement ILIKE '%%Office of the President%%'
             OR statement ILIKE '%%Executive Secretary%%'
             OR statement ILIKE '%%Petition for Supervisory Review%%'
             OR statement ILIKE '%%properly before the Office of the President%%'
           )
         ORDER BY matter_code, updated_at DESC
    """, (fam,))
    fact_rows = cur.fetchall() or []

    # matter_code → best supporting fact (first = newest per matter due to sort)
    evidence: dict[str, dict] = {}
    for r in fact_rows:
        mc = str(_g(r, "matter_code") or "")
        if not mc or mc.startswith("AUTO-"):
            continue
        # Skip pure civil/estate noise unless it is the OP petition vehicle
        st = str(_g(r, "statement") or "")
        if not _is_op_bound_fact(st):
            continue
        # Prefer ARTA / OP petition codes for the count of "matters sent to OP"
        if mc not in evidence:
            evidence[mc] = {
                "matter_code": mc,
                "statement": st,
                "source_id": _g(r, "source_id"),
            }

    # 2) Restrict "sent to OP" count to ARTA CTNs + OP-PETITION with hard evidence
    #    (0690, 0747, 0792 are the three CTNs on the May 2026 supervisory petition;
    #     MWK-OP-PETITION is the docket vehicle — reported separately, not double-counted
    #     as a fourth "referral" if the question is "how many matters".)
    arta_sent = sorted(
        mc for mc in evidence
        if mc.upper().startswith(client_code.split("-")[0].upper() + "-ARTA")
        or re.match(r"^[A-Z]+-ARTA-", mc, re.I)
    )
    # Also accept bare family-ARTA pattern
    if not arta_sent:
        arta_sent = sorted(mc for mc in evidence if "ARTA" in mc.upper())

    op_vehicle = sorted(mc for mc in evidence if re.search(r"-OP-", mc, re.I) or mc.upper().endswith("-OP-PETITION") or "OP-PETITION" in mc.upper())

    # 3) Matter row status only for evidenced codes (no speculative stage scrape)
    codes = list(dict.fromkeys(arta_sent + op_vehicle))
    matter_meta: dict[str, dict] = {}
    if codes:
        cur.execute("""
            SELECT matter_code, title, status, current_stage, forum, court_or_agency
              FROM matters
             WHERE matter_code = ANY(%s)
        """, (codes,))
        for r in cur.fetchall() or []:
            matter_meta[str(_g(r, "matter_code"))] = dict(r)

    # Professional brief — no greeting, no fluff
    n = len(arta_sent)
    lines = [
        "ARTA → Office of the President — verified ground only",
        "",
        f"Count of ARTA matters with verified OP/ES-bound record: {n}.",
    ]

    if n:
        lines.append("")
        lines.append("Matters:")
        for mc in arta_sent:
            meta = matter_meta.get(mc) or {}
            ev = evidence.get(mc) or {}
            stage = (meta.get("current_stage") or "—")[:48]
            status = meta.get("status") or "—"
            sid = ev.get("source_id") or "?"
            # One tight evidence line (not the whole statement dump)
            snippet = re.sub(r"\s+", " ", str(ev.get("statement") or ""))[:140]
            lines.append(f"{mc}  [{status} · {stage}]")
            lines.append(f"  Evidence (doc:{sid}): {snippet}")

    if op_vehicle:
        lines.append("")
        lines.append("Tracking docket (petition vehicle, not an extra ARTA CTN):")
        for mc in op_vehicle:
            if mc in arta_sent:
                continue
            meta = matter_meta.get(mc) or {}
            lines.append(
                f"{mc}  [{meta.get('status') or '—'} · "
                f"{(meta.get('current_stage') or '—')[:48]}]"
            )
            title = (meta.get("title") or "")[:100]
            if title:
                lines.append(f"  {title}")

    # Explicit non-counts so we never "spew" soft labels as truth
    lines.append("")
    lines.append("Not counted as OP referral without verified OP/ES-bound fact:")
    lines.append(
        "• Program labels only (e.g. 'OP Bagong Pilipinas' on an ARTA Southern Luzon filing)"
    )
    lines.append("• Referrals to CSC, DILG, CART, Mayor, or Ombudsman")
    lines.append("• Stage strings that merely contain 'op_' without a verified OP filing fact")

    if n == 0:
        lines.append("")
        lines.append(
            "No verified OP/ES-bound fact found in this client family. "
            "That is a gap in the verified record — not a conversational guess of zero."
        )
    else:
        lines.append("")
        lines.append(
            "Basis: matter_facts.provenance_level=verified with OP/ES or "
            "Petition for Supervisory Review language. Not chat memory."
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
