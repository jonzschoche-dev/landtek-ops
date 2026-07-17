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
    # "history of 52540" / "52540 where did it come from" — bare title number
    m = re.search(
        r"\b(?:history|chain|origin|of|from|title|tct)\s+(?:of\s+)?(?:TCT|T[\s\-]*)?(\d{3,7})\b",
        t, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{5,7})\b", t)
    if m:
        return m.group(1)
    return None


HISTORY_PHRASES = (
    "history", "historical", "title chain", "chain of title", "mother title",
    "parent title", "where did", "originally", "origin of", "came from",
    "derived from", "cancelled by", "source title", "prior title",
    "originally come", "come from", "ancestry", "derivation",
)


def wants_title_history(text: str) -> bool:
    """Title chain / origin questions — must NOT fall through to free LLM."""
    t = (text or "").lower()
    if not any(p in t for p in HISTORY_PHRASES):
        return False
    return bool(title_token_from_message(text))


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
    """Filename actually carries the title number (not body-text coincidence)."""
    n = (name or "").lower().replace("–", "-")
    t = (token or "").lower()
    if not t or t not in n:
        return False
    return True


def _doc_precision_score(name: str, token: str, matter_code: str | None = None) -> int:
    """Higher = better primary for a narrow title fetch. Prefer CTC/TCT over dual surveys."""
    n = (name or "").lower().replace("–", "-").replace("_", " ")
    t = (token or "").lower()
    if not t or t not in n:
        return -100
    score = 10
    # Strong title identity
    if f"t-{t}" in n or f"t {t}" in n or f"tct t-{t}" in n or f"tct_{t}" in n.replace(" ", "_"):
        score += 40
    if f"tct {t}" in n or f"tct-{t}" in n or f"tct_{t}" in n:
        score += 35
    # Certified true copy of THIS title
    if "certified" in n or " ctc" in n or n.startswith("ctc"):
        score += 50
    if "true copy" in n:
        score += 40
    # Explicit TCT instrument vs survey/receipt of multiple titles
    if re.search(rf"\btct\b.*\b{re.escape(t)}\b", n) or re.search(rf"\b{re.escape(t)}\b.*\btct\b", n):
        score += 15
    if "survey" in n:
        score -= 25
    if "receipt" in n and "tct" not in n:
        score -= 10
    # Dual-title surveys (e.g. 32911 and 4497) are secondary when asking one number
    other_tcts = re.findall(r"\b(?:tct|t)[\s\-]*([0-9]{3,7})\b", n)
    distinct = {x for x in other_tcts if x != t}
    if len(distinct) >= 1 and "survey" in n:
        score -= 30
    # Matter spine link
    mc = (matter_code or "").upper()
    if mc and t in mc.replace("-", ""):
        score += 20
    if mc and "TCT" in mc and t in mc:
        score += 15
    return score


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
             ORDER BY
               CASE WHEN a.title_ref ILIKE %s OR a.title_ref ILIKE %s THEN 0 ELSE 1 END,
               CASE WHEN coalesce(a.origin,'') = 'title' THEN 0 ELSE 1 END,
               coalesce(r.readiness_score, 0) DESC
             LIMIT 1
        """, (client_code, fam, client_code, like, like, like,
              f"T-{token}", f"%T-{token}%"))
        assets = cur.fetchall()
        # Fallback without client filter only if exact title_ref match in family already empty
        if not assets:
            cur.execute("""
                SELECT a.asset_code, a.title_ref, a.label, a.title_status, a.client_code,
                       r.readiness_score, r.documents, r.documents_note, r.next_prep_action
                  FROM property_assets a
                  LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
                 WHERE a.title_ref ILIKE %s OR a.asset_code ILIKE %s
                 ORDER BY CASE WHEN a.title_ref ILIKE %s THEN 0 ELSE 1 END,
                          coalesce(r.readiness_score, 0) DESC
                 LIMIT 1
            """, (like, like, f"%T-{token}%"))
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
        # NOTE: rank 0 is valid (best hit). Never use `x or 2` — 0 is falsy in Python.
        if isinstance(d, dict):
            v = d.get("rank")
            return int(v) if v is not None else 2
        return 2

    # Prefer downloadable rows whose FILENAME carries the token (dose + precision)
    def _dl(d) -> bool:
        v = _g(d, "downloadable", 4)
        return bool(v) is True or v == 1 or str(v).lower() in ("t", "true", "1")

    token_named = [
        d for d in ranked
        if _rank(d) <= 1 and _dl(d)
        and _name_has_token(str(_g(d, "name", 1) or ""), token)
    ]
    # Precision sort: CTC / T-#### first; dual surveys last
    token_named.sort(
        key=lambda d: -_doc_precision_score(
            str(_g(d, "name", 1) or ""), token, str(_g(d, "matter_code", 2) or "")),
    )
    other_named = [
        d for d in ranked
        if _rank(d) <= 1 and _dl(d)
        and d not in token_named
    ]
    # Body/rank-2 never auto-released on narrow request
    pool = token_named or other_named
    total_related = len(pool)
    chosen = pool[:cap]
    withheld = max(0, total_related - len(chosen))

    # Short BY CONSTRUCTION (≤280). Ranking is intimate; emission is one link.
    if assets:
        a = assets[0]
        sc = _g(a, "readiness_score", 5)
        try:
            scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
        except Exception:
            scs = "?"
        status = _g(a, "title_status", 3) or "—"
        ref = _g(a, "title_ref", 1) or f"T-{token}"
        head = f"{ref}: {status}, readiness {scs}."
    else:
        head = f"T-{token}: no asset row."

    if not chosen:
        return f"{head} No downloadable CTC/TCT in scope.", None

    d = chosen[0]
    did = _g(d, "id", 0)
    name = (_g(d, "name", 1) or "Document")
    # Prefer short name if long
    if len(name) > 45:
        name = name[:42] + "…"
    more = f" +{withheld} more (say: more TCT {token})." if (withheld and not wide) else ""
    if wide and len(chosen) > 1:
        links = " ".join(f"{PUBLIC_FILE}/{_g(x, 'id', 0)}" for x in chosen[:3])
        text = f"{head} {links}{more}"
    else:
        text = f"{head} {name} {PUBLIC_FILE}/{did}{more}"
    if len(text) > 280:
        text = f"{ref if assets else 'T-'+token}: {PUBLIC_FILE}/{did}{more}"
    return text.strip(), None


def fetch_title_history(
    cur, client_code: Optional[str], text: str,
) -> tuple[Optional[str], Optional[str]]:
    """Table-backed title chain/origin. Never invent mother titles or OCT numbers.

    Reads title_brief + titles + verified matter_facts + source docs.
    Free LLM must not answer these — PA-asset codes are not title numbers.
    """
    token = title_token_from_message(text)
    if not token:
        return (
            "Which title? Send the TCT number (e.g. history of TCT 52540).",
            None,
        )
    if not client_code:
        return (
            "I can only pull title history for an approved client scope.",
            None,
        )

    key = f"T-{token}"
    like = f"%{token}%"
    fam = client_code.split("-")[0] + "%"

    brief = None
    reg = None
    try:
        cur.execute(
            """
            SELECT title_key, display_no, title_kind, status, lifecycle_status,
                   parent_titles, child_titles, n_source_docs, n_facts_verified,
                   clarity_status, registrant_name, card
              FROM title_brief
             WHERE title_key ILIKE %s OR display_no ILIKE %s
                OR title_key = %s OR display_no = %s
             ORDER BY n_facts_verified DESC NULLS LAST
             LIMIT 1
            """,
            (like, like, key, key),
        )
        brief = cur.fetchone()
    except Exception as e:
        return None, f"title_history_brief:{type(e).__name__}:{e}"

    try:
        cur.execute(
            """
            SELECT tct_number, status, lifecycle_status, parent_title,
                   cancelled_by_title, registrant_name_raw, issued_date,
                   source_doc_id, notes
              FROM titles
             WHERE tct_number ILIKE %s OR tct_number = %s
             LIMIT 1
            """,
            (like, key),
        )
        reg = cur.fetchone()
    except Exception:
        reg = None

    if not brief and not reg:
        return (
            f"No title card or registry row for {key} in scope. "
            f"I will not invent a mother title. Say fetch TCT {token} to search docs.",
            None,
        )

    def _g2(row, k, i=None):
        if row is None:
            return None
        if isinstance(row, dict):
            return row.get(k)
        return row[i] if i is not None else None

    display = _g2(brief, "display_no") or _g2(reg, "tct_number") or key
    kind = _g2(brief, "title_kind") or "tct"
    status = _g2(brief, "status") or _g2(reg, "status") or "—"
    life = _g2(brief, "lifecycle_status") or _g2(reg, "lifecycle_status") or "—"
    parents = _g2(brief, "parent_titles") or []
    children = _g2(brief, "child_titles") or []
    if isinstance(parents, str):
        parents = [parents]
    if isinstance(children, str):
        children = [children]
    parents = [str(p) for p in (parents or []) if p]
    children = [str(c) for c in (children or []) if c]
    # Registry single parent / cancel chain
    p_reg = _g2(reg, "parent_title")
    if p_reg and str(p_reg) not in parents:
        parents = [str(p_reg)] + parents
    cancelled_by = _g2(reg, "cancelled_by_title")
    if cancelled_by and str(cancelled_by) not in children:
        children = [str(cancelled_by)] + list(children)

    # Verified facts that actually mention this title (not free invent)
    facts = []
    try:
        cur.execute(
            """
            SELECT left(statement, 180) AS statement, source_id
              FROM matter_facts
             WHERE provenance_level IN ('verified', 'operator')
               AND (statement ILIKE %s OR excerpt ILIKE %s)
               AND (
                    matter_code LIKE %s OR matter_code IS NULL
                    OR source_id IN (
                        SELECT d.id FROM documents d
                         WHERE d.case_file = %s OR d.case_file LIKE %s
                            OR d.matter_code LIKE %s
                    )
               )
             ORDER BY
               CASE WHEN statement ILIKE '%%mother%%' OR statement ILIKE '%%parent%%'
                          OR statement ILIKE '%%transferred from%%'
                          OR statement ILIKE '%%acquired%%'
                          OR statement ILIKE '%%cancelled%%'
                          OR statement ILIKE '%%intestate%%'
                          OR statement ILIKE '%%original%%' THEN 0 ELSE 1 END,
               id DESC
             LIMIT 5
            """,
            (like, like, fam, client_code, fam, fam),
        )
        facts = list(cur.fetchall() or [])
    except Exception:
        try:
            cur.execute(
                """
                SELECT left(statement, 180) AS statement, source_id
                  FROM matter_facts
                 WHERE provenance_level IN ('verified', 'operator')
                   AND (statement ILIKE %s OR excerpt ILIKE %s)
                 ORDER BY id DESC
                 LIMIT 5
                """,
                (like, like),
            )
            facts = list(cur.fetchall() or [])
        except Exception:
            facts = []

    # Primary cancelled-fraud / CTC doc if any
    primary_doc = _g2(reg, "source_doc_id")
    primary_name = None
    if primary_doc:
        try:
            cur.execute(
                """
                SELECT id, COALESCE(NULLIF(smart_filename,''), original_filename,
                                    file_name, 'Document') AS name
                  FROM documents WHERE id = %s
                """,
                (int(primary_doc),),
            )
            dr = cur.fetchone()
            if dr:
                primary_doc = _g2(dr, "id", 0)
                primary_name = _g2(dr, "name", 1)
        except Exception:
            pass

    n_docs = _g2(brief, "n_source_docs") or 0
    n_ver = _g2(brief, "n_facts_verified") or 0
    registrant = _g2(brief, "registrant_name") or _g2(reg, "registrant_name_raw")

    # ── Refined clear card (prose, not field dump) ──
    status_bit = f"{status}"
    if life and life not in (status, "—", None):
        status_bit += f" / {life}"
    if registrant and str(registrant).lower() not in ("—", "none", "null"):
        status_bit += f" ({registrant})"

    lines = [f"{display} is a {kind.upper()} — {status_bit}."]

    if parents:
        lines.append("Came from: " + ", ".join(parents[:5]) + ".")
    else:
        lines.append(
            "Mother/parent title is not recorded on the title card or registry "
            "(I will not invent an OCT)."
        )

    if children or cancelled_by:
        succ = []
        if cancelled_by:
            succ.append(str(cancelled_by))
        for c in children:
            if str(c) not in succ:
                succ.append(str(c))
        lines.append("Succeeded by / cancelled toward: " + ", ".join(succ[:5]) + ".")

    # One distilled verified fact (not a dump of three near-duplicates)
    best = None
    for f in facts:
        st = (_g2(f, "statement", 0) or "").strip()
        if not st:
            continue
        low = st.lower()
        score = 0
        for kw, pts in (
            ("cancelled", 40), ("transferred from", 35), ("mother", 30),
            ("acquired", 25), ("intestate", 25), ("fraud", 20), ("heir", 15),
        ):
            if kw in low:
                score += pts
        if best is None or score > best[0]:
            best = (score, st, _g2(f, "source_id", 1))
    if best and best[0] >= 15:
        sid = best[2]
        lines.append(
            f"On record: {best[1]}"
            + (f" (doc {sid})" if sid else "")
            + "."
        )

    if primary_doc:
        nm = (primary_name or "source document")[:48]
        lines.append(f"Primary file: {nm}\n{PUBLIC_FILE}/{primary_doc}")

    if n_docs or n_ver:
        lines.append(
            f"({n_docs or 0} source docs · {n_ver or 0} verified facts on the title card)"
        )

    text = "\n".join(lines)
    if len(text) > 700:
        text = "\n".join(lines[:4])
        if primary_doc:
            text += f"\n{PUBLIC_FILE}/{primary_doc}"
    return text.strip(), None
