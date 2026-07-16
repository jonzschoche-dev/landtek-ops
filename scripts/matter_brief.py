#!/usr/bin/env python3
"""matter_brief.py — MPRB v1: Matter Pre-Response Brief (internal plane).

Assembles a client-walled, purpose-selected multi-angle view of matter(s)
BEFORE Leo speaks. Deterministic, $0. Provenance split: verified vs provisional.

Angles declare status: data | empty | not_instrumented (never silent absence).
answer_structured may assert ONLY from verified facts / matters spine.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Cap load into qwen — selection quality > angle count
MAX_VERIFIED_LINES = 6
MAX_PROVISIONAL_LINES = 3
MAX_DOCS = 3
MAX_PARTIES = 8


def _g(row, key, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return default


def resolve_matters(cur, client_code: str, message: str) -> List[str]:
    """Resolve matter_code(s) from the message. Fail closed → []."""
    if not client_code:
        return []
    fam = client_code.split("-")[0]
    text = message or ""
    codes = []
    # Explicit matter codes
    for m in re.finditer(r"\b([A-Z]{2,8}-(?:ARTA|OP|CV|TCT|GUARDIANSHIP|ESTATE|DILG)?-?[A-Z0-9]{2,20})\b",
                         text, re.I):
        codes.append(m.group(1).upper())
    # CTN / docket fragments → ARTA matters
    for m in re.finditer(r"\b(?:CTN\s*)?(?:SL-?)?(\d{4}-\d{4}-\d{3,4})\b", text, re.I):
        frag = m.group(1)
        cur.execute("""
            SELECT matter_code FROM matters
             WHERE matter_code LIKE %s
               AND (title ILIKE %s OR matter_code ILIKE %s)
             LIMIT 3
        """, (fam + "%", f"%{frag}%", f"%{frag}%"))
        for r in cur.fetchall() or []:
            codes.append(str(_g(r, "matter_code")).upper())
    # Title token → property-linked is not matter; skip
    # Portfolio ARTA→OP: codes from verified OP/ES-bound facts only
    tlow = text.lower()
    if ("arta" in tlow and any(k in tlow for k in (
            "op", "president", "executive secretary", "supervisory"))):
        try:
            import corpus_answer as ca
            fam_like = fam + "%"
            cur.execute("""
                SELECT matter_code, statement FROM matter_facts
                 WHERE matter_code LIKE %s AND provenance_level='verified'
                   AND matter_code ILIKE '%%ARTA%%'
                   AND (
                        statement ILIKE '%%Executive Secretary%%'
                     OR statement ILIKE '%%Ralph G. Recto%%'
                     OR (statement ILIKE '%%Petition for Supervisory Review%%'
                         AND statement ILIKE '%%Corrective Action%%')
                   )
            """, (fam_like,))
            for r in cur.fetchall() or []:
                st = _g(r, "statement") or ""
                if ca._is_op_bound_fact(st):
                    codes.append(str(_g(r, "matter_code")).upper())
            cur.execute("""
                SELECT matter_code FROM matters
                 WHERE matter_code LIKE %s AND matter_code ILIKE '%%OP-PETITION%%'
            """, (fam_like,))
            for r in cur.fetchall() or []:
                codes.append(str(_g(r, "matter_code")).upper())
        except Exception:
            pass

    # Dedupe preserve order
    out, seen = [], set()
    for c in codes:
        if c and c not in seen:
            # verify exists in family
            cur.execute(
                "SELECT 1 FROM matters WHERE matter_code=%s AND "
                "(client_code=%s OR matter_code LIKE %s) LIMIT 1",
                (c, client_code, fam + "%"))
            if cur.fetchone():
                seen.add(c)
                out.append(c)
    return out[:8]


def _angle_spine(cur, matter_code: str) -> Dict[str, Any]:
    cur.execute("""
        SELECT matter_code, title, status, current_stage, forum, court_or_agency, client_code
          FROM matters WHERE matter_code=%s
    """, (matter_code,))
    r = cur.fetchone()
    if not r:
        return {"status": "empty", "data": None}
    return {"status": "data", "data": dict(r) if isinstance(r, dict) else r}


def _angle_facts(cur, matter_code: str) -> Dict[str, Any]:
    cur.execute("""
        SELECT statement, source_id, provenance_level
          FROM matter_facts
         WHERE matter_code=%s AND provenance_level='verified'
           AND coalesce(statement,'')<>''
         ORDER BY updated_at DESC LIMIT %s
    """, (matter_code, MAX_VERIFIED_LINES))
    verified = list(cur.fetchall() or [])
    cur.execute("""
        SELECT statement, source_id, provenance_level
          FROM matter_facts
         WHERE matter_code=%s AND provenance_level='inferred_strong'
           AND coalesce(statement,'')<>''
         ORDER BY updated_at DESC LIMIT %s
    """, (matter_code, MAX_PROVISIONAL_LINES))
    provisional = list(cur.fetchall() or [])
    if not verified and not provisional:
        return {"status": "empty", "verified": [], "provisional": []}
    return {"status": "data", "verified": verified, "provisional": provisional}


def _angle_parties(cur, matter_code: str) -> Dict[str, Any]:
    cur.execute("""
        SELECT party_name, role, side FROM matter_parties
         WHERE matter_code=%s AND coalesce(party_name,'')<>''
         ORDER BY party_name LIMIT %s
    """, (matter_code, MAX_PARTIES))
    rows = list(cur.fetchall() or [])
    if not rows:
        # distinguish empty vs not instrumented: table has global rows?
        cur.execute("SELECT count(*) AS n FROM matter_parties")
        n = _g(cur.fetchone(), "n") or 0
        if int(n) < 50:  # sparse corpus-wide
            return {"status": "not_instrumented", "data": [],
                    "note": "matter_parties sparsely populated corpus-wide"}
        return {"status": "empty", "data": [], "note": "no parties on this matter"}
    return {"status": "data", "data": rows}


def _angle_deadlines(cur, matter_code: str) -> Dict[str, Any]:
    try:
        cur.execute("""
            SELECT due_date, label, bucket, days_out
              FROM surfaced_deadlines
             WHERE matter_code=%s
             ORDER BY as_of DESC, due_date ASC NULLS LAST
             LIMIT 5
        """, (matter_code,))
        rows = list(cur.fetchall() or [])
    except Exception:
        return {"status": "not_instrumented", "data": []}
    if not rows:
        return {"status": "empty", "data": []}
    return {"status": "data", "data": rows}


def _angle_documents(cur, matter_code: str) -> Dict[str, Any]:
    """Deterministic only — matter_code link or filename contains code fragment."""
    frag = matter_code.split("-")[-1] if matter_code else ""
    cur.execute("""
        SELECT id,
               COALESCE(NULLIF(smart_filename,''), original_filename, 'Document') AS name,
               (file_path IS NOT NULL OR drive_file_id IS NOT NULL) AS downloadable
          FROM documents
         WHERE matter_code=%s
            OR (coalesce(smart_filename,'') ILIKE %s OR coalesce(original_filename,'') ILIKE %s)
         ORDER BY downloadable DESC, id DESC
         LIMIT %s
    """, (matter_code, f"%{frag}%", f"%{frag}%", MAX_DOCS))
    rows = list(cur.fetchall() or [])
    if not rows:
        return {"status": "empty", "data": []}
    return {"status": "data", "data": rows}


def _angle_property(cur, client_code: str, message: str) -> Dict[str, Any]:
    m = re.search(r"\b(T-?[0-9][0-9A-Za-z./-]{2,})\b", message or "")
    if not m:
        return {"status": "empty", "data": None, "note": "no title token in ask"}
    token = m.group(1)
    cur.execute("""
        SELECT a.title_ref, a.title_status, r.readiness_score, r.weakest_axis, r.next_prep_action
          FROM property_assets a
          LEFT JOIN property_readiness r ON r.asset_code=a.asset_code
         WHERE a.client_code=%s AND (a.title_ref ILIKE %s OR a.asset_code ILIKE %s)
         LIMIT 2
    """, (client_code, f"%{token}%", f"%{token}%"))
    rows = list(cur.fetchall() or [])
    if not rows:
        return {"status": "empty", "data": []}
    return {"status": "data", "data": rows}


def assemble(cur, *, client_code: str, matter_codes: List[str], message: str = "",
             role: str = "operator") -> Dict[str, Any]:
    """Build MatterBrief dict for matter_codes (client-walled)."""
    angles = {}
    for mc in matter_codes:
        angles[mc] = {
            "spine": _angle_spine(cur, mc),
            "verified_ground": _angle_facts(cur, mc),
            "parties": _angle_parties(cur, mc),
            "deadlines": _angle_deadlines(cur, mc),
            "documents": _angle_documents(cur, mc),
        }
    prop = _angle_property(cur, client_code, message)
    return {
        "client_code": client_code,
        "role": role,
        "matter_codes": matter_codes,
        "angles_by_matter": angles,
        "property": prop,
    }


def assemble_for_message(cur, client_code: str, message: str, role: str = "operator"
                         ) -> Optional[Dict[str, Any]]:
    codes = resolve_matters(cur, client_code, message)
    if not codes:
        return None
    return assemble(cur, client_code=client_code, matter_codes=codes, message=message, role=role)


def render(brief: Dict[str, Any]) -> str:
    """Dosed human-readable internal brief (for LLM or operator)."""
    if not brief:
        return ""
    lines = [f"MPRB client={brief.get('client_code')} matters={','.join(brief.get('matter_codes') or [])}"]
    for mc, ang in (brief.get("angles_by_matter") or {}).items():
        lines.append(f"--- {mc} ---")
        sp = ang.get("spine") or {}
        if sp.get("status") == "data" and sp.get("data"):
            d = sp["data"]
            lines.append(
                f"spine: status={_g(d,'status')} stage={_g(d,'current_stage')} "
                f"venue={(_g(d,'court_or_agency') or _g(d,'forum') or '—')[:60]}"
            )
            title = (_g(d, "title") or "")[:100]
            if title:
                lines.append(f"  title: {title}")
        else:
            lines.append(f"spine: {sp.get('status', 'empty')}")

        vg = ang.get("verified_ground") or {}
        if vg.get("status") == "data":
            lines.append("VERIFIED GROUND (earned — state plainly):")
            for f in (vg.get("verified") or [])[:MAX_VERIFIED_LINES]:
                st = re.sub(r"\s+", " ", str(_g(f, "statement") or ""))[:160]
                lines.append(f"  • (doc:{_g(f,'source_id')}) {st}")
            prov = vg.get("provisional") or []
            if prov:
                lines.append("PROVISIONAL (inferred_strong — NOT verified; mark unconfirmed if used):")
                for f in prov[:MAX_PROVISIONAL_LINES]:
                    st = re.sub(r"\s+", " ", str(_g(f, "statement") or ""))[:120]
                    lines.append(f"  • unconfirmed (doc:{_g(f,'source_id')}) {st}")
        else:
            lines.append(f"verified_ground: {vg.get('status', 'empty')}")

        pt = ang.get("parties") or {}
        if pt.get("status") == "data":
            lines.append("parties:")
            for p in (pt.get("data") or [])[:MAX_PARTIES]:
                lines.append(
                    f"  • {_g(p,'party_name')} | {_g(p,'role') or '?'} | {_g(p,'side') or ''}"
                )
        else:
            note = pt.get("note") or pt.get("status")
            lines.append(f"parties: {note}")

        dl = ang.get("deadlines") or {}
        if dl.get("status") == "data":
            lines.append("deadlines:")
            for d in (dl.get("data") or [])[:5]:
                lines.append(
                    f"  • {_g(d,'due_date')} {_g(d,'label') or ''} [{_g(d,'bucket') or ''}]"
                )
        else:
            lines.append(f"deadlines: {dl.get('status', 'empty')}")

        doc = ang.get("documents") or {}
        if doc.get("status") == "data":
            lines.append("documents (deterministic matter link only):")
            for d in (doc.get("data") or [])[:MAX_DOCS]:
                lines.append(f"  • doc:{_g(d,'id')} {(_g(d,'name') or '')[:70]}")
        else:
            lines.append(f"documents: {doc.get('status', 'empty')}")

    prop = brief.get("property") or {}
    if prop.get("status") == "data":
        lines.append("property:")
        for p in prop.get("data") or []:
            sc = _g(p, "readiness_score")
            scs = f"{float(sc)*100:.0f}%" if sc is not None else "?"
            lines.append(
                f"  • {_g(p,'title_ref')} status={_g(p,'title_status')} ready={scs} "
                f"weak={_g(p,'weakest_axis')}"
            )
    return "\n".join(lines)


def answer_structured(brief: Dict[str, Any], purpose: str = "") -> Optional[str]:
    """SQL-grade conclusions only from verified spine — never provisional untagged."""
    if not brief or not brief.get("matter_codes"):
        return None
    # Single-matter status
    if len(brief["matter_codes"]) == 1 and purpose in ("", "matter_status", "status"):
        mc = brief["matter_codes"][0]
        ang = (brief.get("angles_by_matter") or {}).get(mc) or {}
        sp = (ang.get("spine") or {}).get("data")
        if not sp:
            return None
        lines = [
            f"{mc}",
            f"status: {_g(sp,'status') or '—'}",
            f"stage: {_g(sp,'current_stage') or '—'}",
            f"venue: {(_g(sp,'court_or_agency') or _g(sp,'forum') or '—')[:80]}",
        ]
        title = (_g(sp, "title") or "")[:120]
        if title:
            lines.append(f"title: {title}")
        vg = ang.get("verified_ground") or {}
        verified = vg.get("verified") or []
        if verified:
            lines.append("verified ground (sample):")
            for f in verified[:3]:
                st = re.sub(r"\s+", " ", str(_g(f, "statement") or ""))[:140]
                lines.append(f"  • (doc:{_g(f,'source_id')}) {st}")
        else:
            lines.append("verified ground: empty — do not invent facts for this matter.")
        pt = ang.get("parties") or {}
        if pt.get("status") == "not_instrumented":
            lines.append("parties: not_instrumented (table sparsely populated)")
        elif pt.get("status") == "empty":
            lines.append("parties: empty on this matter")
        lines.append("Basis: matters + matter_facts(verified only). Provisional omitted from asserts.")
        return "\n".join(lines)
    return None


def try_mprb_route(cur, client_code: str, message: str) -> Optional[Dict[str, Any]]:
    """If message is a clear single-matter status ask, return preformed structured answer."""
    t = (message or "").lower()
    # status-style
    if not any(k in t for k in ("status", "where is", "update on", "what's happening", "what is the stage")):
        # explicit matter code alone or "tell me about MWK-..."
        if not re.search(r"\b[A-Z]{2,8}-[A-Z0-9-]{3,}\b", message or "", re.I):
            return None
    codes = resolve_matters(cur, client_code, message)
    if len(codes) != 1:
        return None
    brief = assemble(cur, client_code=client_code, matter_codes=codes, message=message)
    text = answer_structured(brief, "matter_status")
    if not text:
        return None
    return {"text": text, "via": f"mprb:status:{codes[0]}", "preformed": True,
            "purpose": "matter_status", "matter_codes": codes}
