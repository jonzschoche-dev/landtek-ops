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
    # Word-ish OP signal (avoid matching inside "of"/"open" alone: require op as token)
    op_signal = bool(re.search(
        r"(?:\bop\b|office of the president|executive secretary|malacañ?ang|"
        r"\brecto\b|supervisory|op appeal|op petition|petition to the op)",
        t,
    ))
    docket_signal = any(k in t for k in (
        "docket", "case no", "case number", "mro", "transmittal",
        "op case", "reference no", "ref no", "receiving ref", "filing ref",
    ))
    # "second manifestation" of OP package is a docket/ref ask even without the word docket
    if ("manifestation" in t and op_signal) or (docket_signal and op_signal):
        return "op_docket"
    if "docket" in t and any(k in t for k in ("appeal", "petition to the op", "op petition", "op appeal")):
        return "op_docket"
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


def _g(row, key, default=None):
    """Safe field get for RealDictRow, dict, or tuple rows (by name if mapping)."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]  # psycopg2 RealDict-like / named
    except (KeyError, TypeError, IndexError):
        return default


def _as_dicts(cur, rows=None):
    """Normalize fetchall() to list[dict] for plain or RealDict cursors."""
    rows = list(rows if rows is not None else (cur.fetchall() or []))
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, r)) for r in rows]


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

    # Short BY CONSTRUCTION (≤280 = S14 / EMISSION_CAP). No post-hoc chop.
    n = len(arta_sent)
    if n == 0:
        return (
            "No ARTA matter has a verified OP/ES filing on record for this client."
        )

    # Prefer short codes in the list (0690 not full MWK-ARTA-0690 if clear)
    short = []
    for mc in arta_sent:
        m = re.search(r"(\d{4})$", mc) or re.search(r"ARTA-(\d+)", mc, re.I)
        short.append(m.group(1) if m else mc)
    codes = ", ".join(short) if len("".join(short)) < 40 else ", ".join(arta_sent)

    src_ids = []
    for mc in arta_sent:
        sid = (evidence.get(mc) or {}).get("source_id")
        if sid and str(sid) not in src_ids:
            src_ids.append(str(sid))
    cite = f" docs {', '.join(src_ids[:3])}." if src_ids else ""

    vehicle = next((m for m in op_vehicle if m not in arta_sent), None)
    vehicle_bit = f" Vehicle {vehicle} awaiting OP action." if vehicle else ""

    # One sentence + optional second
    text = (
        f"{n} ARTA CTNs on the May 2026 OP/ES supervisory petition: {codes}."
        f"{vehicle_bit}{cite}"
    )
    if len(text) > 280:
        text = f"{n} CTNs on OP/ES petition May 2026: {codes}.{cite}"
    return text.strip()


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


def answer_op_docket(cur, client_code: str, message: str = "") -> str:
    """OP petition docket/ref — cold, short by construction (≤280).

    Answer hierarchy (do not conflate):
      1) Malacañang MRO / OP Transmittal Ref (what OP records stamped)
      2) O.P. Case No. — only if typed; else say not on face
      3) Core ARTA CTNs on the May 2026 petition only (0690/0792), not a dump

    If the ask is specifically the *second manifestation*, prefer that filing's MRO
    (060426-… / doc 1189), not a random ARTA respondent manifestation.
    """
    tmsg = (message or "").lower()
    want_second = bool(re.search(
        r"\bsecond\b.*\bmanifest", tmsg
    ) or re.search(r"\bmanifest\w*\b.*\bsecond\b", tmsg))

    mros = []
    # Prefer OP-petition-linked document_fields
    try:
        cur.execute(
            """
            SELECT DISTINCT df.value_norm, df.doc_id
            FROM document_fields df
            JOIN document_matter_links l ON l.doc_id = df.doc_id
            WHERE df.field_kind = 'mro_ref'
              AND l.matter_code = 'MWK-OP-PETITION'
            ORDER BY df.value_norm
            """
        )
        mros = _as_dicts(cur)
    except Exception:
        mros = []
    if not mros:
        try:
            cur.execute(
                """
                SELECT DISTINCT value_norm, NULL::int AS doc_id
                FROM fact_fields
                WHERE matter_code = 'MWK-OP-PETITION' AND field_kind = 'mro_ref'
                """
            )
            mros = _as_dicts(cur)
        except Exception:
            mros = []
    if not mros:
        try:
            cur.execute(
                """
                SELECT DISTINCT
                  (regexp_match(
                      coalesce(statement,'') || ' ' || coalesce(excerpt,''),
                      '(\\d{6}-MRO-\\d{4,8})', 'i'))[1] AS value_norm,
                  NULLIF(source_id, '')::int AS doc_id
                FROM matter_facts
                WHERE matter_code = 'MWK-OP-PETITION'
                  AND (statement ~* '\\d{6}-MRO-\\d+' OR excerpt ~* '\\d{6}-MRO-\\d+')
                """
            )
            mros = [r for r in _as_dicts(cur) if _g(r, "value_norm")]
        except Exception:
            mros = []

    # Also pull MRO from known second-manifestation doc even if not matter-linked
    if want_second:
        try:
            cur.execute(
                """
                SELECT DISTINCT value_norm, doc_id FROM document_fields
                WHERE field_kind = 'mro_ref' AND doc_id = 1189
                """
            )
            for r in _as_dicts(cur):
                mros.append(r)
        except Exception:
            pass

    vals = []
    seen = set()
    for r in mros:
        v = (_g(r, "value_norm") or "").upper().strip()
        if v and v not in seen:
            seen.add(v)
            vals.append(v)

    # Primary petition stamp 050526-… first; second manifestation 060426-… second
    vals.sort(key=lambda x: (0 if x.startswith("050526") else 1 if x.startswith("060426") else 2, x))

    # Core CTNs on the operative petition — short codes only
    core_ctns = []
    try:
        cur.execute(
            """
            SELECT DISTINCT value_norm
            FROM fact_fields
            WHERE matter_code = 'MWK-OP-PETITION'
              AND field_kind = 'ctn'
              AND (
                value_norm LIKE '%%0690'
                OR value_norm LIKE '%%0792'
                OR value_norm LIKE '%%0747'
                OR value_norm ~ '2025-1008-0690|2025-1104-0792|2025-1021-0747'
              )
            ORDER BY 1
            """
        )
        for r in _as_dicts(cur):
            v = _g(r, "value_norm") or ""
            m = re.search(r"(\d{4})$", v)
            core_ctns.append(m.group(1) if m else v)
    except Exception:
        pass
    ctn_short = []
    for c in core_ctns:
        if c not in ctn_short:
            ctn_short.append(c)
    ctn_short = ctn_short[:3]

    if not vals:
        ctn_bit = f" ARTA CTNs on record: {', '.join(ctn_short)}." if ctn_short else ""
        return (
            "No Malacañang receiving ref (MRO) or O.P. Case No. is typed yet "
            f"for the OP petition.{ctn_bit}"
        )

    primary = next((v for v in vals if v.startswith("050526")), vals[0])
    second = next((v for v in vals if v.startswith("060426")), None)

    if want_second:
        if second:
            text = (
                f"OP second manifestation: Malacañang receiving ref {second} "
                f"(ties to petition MRO {primary}). No separate O.P. Case No. on face."
            )
        else:
            text = (
                f"No separate MRO for a second OP manifestation is typed yet. "
                f"Petition MRO is {primary}."
            )
        if len(text) > 280:
            text = f"OP 2nd manifestation MRO {second or '—'}; petition MRO {primary}."
        return text.strip()

    # Default: primary petition
    text = (
        f"OP petition (5 May 2026): Malacañang receiving ref {primary}. "
        f"No separate O.P. Case No. on the petition face."
    )
    if ctn_short:
        text += f" ARTA CTNs {', '.join(ctn_short)}."
    if len(text) > 280:
        text = f"OP petition: MRO {primary}. No O.P. Case No. on face."
        if ctn_short:
            text += f" ARTA {', '.join(ctn_short)}."
    return text.strip()


def try_corpus_answer(cur, client_code: Optional[str], message: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (answer, purpose) if a deterministic corpus path applies; else (None, None)."""
    if not client_code:
        return None, None
    purpose = classify_purpose(message or "")
    if not purpose:
        return None, None
    try:
        if purpose == "op_docket":
            return answer_op_docket(cur, client_code, message or ""), purpose
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
