#!/usr/bin/env python3
"""materialize_matter_brief.py — rebuild matter_brief from SoR + fact_fields (DERIVED).

Deterministic headline template — same inputs → identical output. No LLM.

  python3 scripts/materialize_matter_brief.py --go
  python3 scripts/materialize_matter_brief.py --matter MWK-OP-PETITION --go
  python3 scripts/materialize_matter_brief.py --stale-only --go
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _arr(cur, matter, kind, prov_verified_only=False):
    sql = """
        SELECT DISTINCT value_norm FROM fact_fields
        WHERE matter_code = %s AND field_kind = %s
    """
    params = [matter, kind]
    if prov_verified_only:
        sql += " AND provenance_level = 'verified'"
    sql += " ORDER BY 1 LIMIT 40"
    cur.execute(sql, params)
    return [r["value_norm"] for r in cur.fetchall()]


def _headline(matter, status, stage, forum, ctns_v, n_v, next_deadline):
    # Deterministic template — not model prose
    ctn_part = f"{len(ctns_v)} CTNs ({', '.join(ctns_v)})" if ctns_v else "0 CTNs"
    st = status or "—"
    sg = stage or "—"
    fo = forum or "—"
    nd = next_deadline.isoformat() if next_deadline else "—"
    return f"{matter} · {st}/{sg} · {fo} · {ctn_part} · {n_v} verified · next: {nd}"


def materialize_one(cur, matter: str) -> dict:
    cur.execute(
        """
        SELECT matter_code, status, current_stage, forum, next_deadline
        FROM matters WHERE matter_code = %s
        """,
        (matter,),
    )
    m = cur.fetchone()
    if not m:
        return {}

    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE provenance_level = 'verified') AS n_v,
          count(*) FILTER (WHERE provenance_level IS DISTINCT FROM 'verified') AS n_p
        FROM matter_facts WHERE matter_code = %s
        """,
        (matter,),
    )
    counts = cur.fetchone()
    n_v = int(counts["n_v"] or 0)
    n_p = int(counts["n_p"] or 0)

    cur.execute(
        """
        SELECT count(*) AS n,
               count(*) FILTER (WHERE provenance_level='verified') AS nv
        FROM fact_fields WHERE matter_code = %s
        """,
        (matter,),
    )
    fc = cur.fetchone()

    # Verified-only lists for cold answers; full lists kept for machine
    # Kinds are delicately separated: ctn ≠ tct ≠ oct ≠ e_title ≠ tax_dec
    ctns_v = _arr(cur, matter, "ctn", prov_verified_only=True)
    ctns_all = _arr(cur, matter, "ctn", prov_verified_only=False)
    tcts = _arr(cur, matter, "tct", prov_verified_only=False)
    octs = _arr(cur, matter, "oct", prov_verified_only=False)
    e_titles = _arr(cur, matter, "e_title", prov_verified_only=False)
    # TCT list also surfaces e-titles that are transfer titles (machine convenience)
    tcts = list(dict.fromkeys(tcts + e_titles))
    tax_decs = _arr(cur, matter, "tax_dec", prov_verified_only=False)
    dockets = _arr(cur, matter, "docket", prov_verified_only=False)
    # stash extras on readiness for inquiry without schema churn
    number_pack = {
        "octs": octs,
        "e_titles": e_titles,
        "tax_decs": tax_decs,
    }

    cur.execute(
        """
        SELECT party_name FROM matter_parties
        WHERE matter_code = %s
        ORDER BY id LIMIT 30
        """,
        (matter,),
    )
    parties = [r["party_name"] for r in cur.fetchall() if r["party_name"]]

    cur.execute(
        """
        SELECT value_norm FROM fact_fields
        WHERE matter_code = %s AND field_kind = 'date'
        ORDER BY value_norm LIMIT 20
        """,
        (matter,),
    )
    key_dates = [{"date": r["value_norm"]} for r in cur.fetchall()]

    cur.execute(
        """
        SELECT value_norm FROM fact_fields
        WHERE matter_code = %s AND field_kind = 'amount'
        ORDER BY value_norm LIMIT 20
        """,
        (matter,),
    )
    amounts = [{"amount": r["value_norm"]} for r in cur.fetchall()]

    cur.execute(
        """
        SELECT source_id::int AS doc_id, count(*) AS n
        FROM matter_facts
        WHERE matter_code = %s AND source_kind = 'doc'
          AND source_id ~ '^[0-9]+$'
          AND provenance_level = 'verified'
        GROUP BY 1 ORDER BY n DESC LIMIT 8
        """,
        (matter,),
    )
    top_docs = [r["doc_id"] for r in cur.fetchall()]

    n_contra = 0
    try:
        cur.execute(
            """
            SELECT count(*) AS n FROM holes_findings
            WHERE status = 'open'
              AND (matter_code = %s OR detail ILIKE %s)
            """,
            (matter, f"%{matter}%"),
        )
        n_contra = int((cur.fetchone() or {}).get("n") or 0)
    except Exception:
        cur.connection.rollback()
        n_contra = 0

    stage = m.get("current_stage")
    status = m.get("status")
    forum = m.get("forum")
    next_deadline = m.get("next_deadline")
    # Prefer verified CTNs in headline; fall back to all if none verified yet
    ctn_for_head = ctns_v or ctns_all[:5]

    core = {
        "status": bool(status),
        "verified_facts": n_v > 0,
        "typed_fields": int(fc["n"] or 0) > 0,
        "parties": bool(parties),
        "numbers": bool(ctns_all or tcts or dockets),
    }
    missing = sorted(k for k, ok in core.items() if not ok)
    filled = sum(1 for ok in core.values() if ok)
    clarity_score = round(filled / max(len(core), 1), 3)
    if clarity_score >= 0.80:
        clarity_status = "clear"
    elif clarity_score >= 0.50:
        clarity_status = "partial"
    else:
        clarity_status = "unclear"
    needs_human = clarity_status == "unclear" or n_v == 0
    oversight_reason = None
    if needs_human:
        oversight_reason = (
            f"matter clarity={clarity_status} ({clarity_score:.0%}); "
            f"verified={n_v}; missing: {', '.join(missing) or '—'}"
        )

    headline = _headline(matter, status, stage, forum, ctn_for_head, n_v, next_deadline)
    if clarity_status == "unclear":
        headline = "⚠ UNCLEAR · " + headline
    elif needs_human and n_v == 0:
        headline = "◐ NO VERIFIED · " + headline

    angle_status = {
        "facts": "data" if n_v else "empty",
        "fields": "data" if int(fc["n"] or 0) else "empty",
        "parties": "data" if parties else "empty",
        "deadlines": "data" if next_deadline else "empty",
        "ctns": "data" if (ctns_v or ctns_all) else "empty",
        "clarity": clarity_status,
        "needs_human_review": needs_human,
    }

    # fingerprint: counts + sorted verified ctn list
    fp = f"v{n_v}|p{n_p}|f{fc['n']}|ctn={','.join(ctn_for_head)}|c{clarity_score}"

    return {
        "matter_code": matter,
        "status": status,
        "stage": stage,
        "forum": forum,
        "n_facts_verified": n_v,
        "n_facts_provisional": n_p,
        "n_fields_total": int(fc["n"] or 0),
        "n_fields_verified": int(fc["nv"] or 0),
        "ctns": ctns_all,
        "tcts": tcts,
        "dockets": dockets,
        "parties": parties,
        "key_dates": json.dumps(key_dates),
        "amounts": json.dumps(amounts),
        "next_deadline": next_deadline,
        "n_open_contradictions": n_contra,
        "top_doc_ids": top_docs,
        "readiness": json.dumps({
            "verified_facts": n_v,
            "provisional_facts": n_p,
            "octs": octs,
            "e_titles": e_titles,
            "tax_decs": tax_decs,
            "numbers": number_pack,
            "clarity": clarity_status,
            "missing": missing,
        }),
        "headline": headline,
        "angle_status": json.dumps(angle_status),
        "source_fingerprint": fp,
        "clarity_score": clarity_score,
        "clarity_status": clarity_status,
        "missing_fields": missing,
        "needs_human_review": needs_human,
        "oversight_reason": oversight_reason,
    }


def upsert(cur, row: dict, go: bool):
    if not row:
        return
    if not go:
        print(f"  [dry] {row['headline']}")
        return
    cur.execute(
        """
        INSERT INTO matter_brief (
            matter_code, status, stage, forum,
            n_facts_verified, n_facts_provisional, n_fields_total, n_fields_verified,
            ctns, tcts, dockets, parties, key_dates, amounts,
            next_deadline, n_open_contradictions, top_doc_ids, readiness,
            headline, angle_status, source_fingerprint, computed_at,
            clarity_score, clarity_status, missing_fields, needs_human_review, oversight_reason
        ) VALUES (
            %(matter_code)s, %(status)s, %(stage)s, %(forum)s,
            %(n_facts_verified)s, %(n_facts_provisional)s, %(n_fields_total)s, %(n_fields_verified)s,
            %(ctns)s, %(tcts)s, %(dockets)s, %(parties)s, %(key_dates)s::jsonb, %(amounts)s::jsonb,
            %(next_deadline)s, %(n_open_contradictions)s, %(top_doc_ids)s, %(readiness)s::jsonb,
            %(headline)s, %(angle_status)s::jsonb, %(source_fingerprint)s, now(),
            %(clarity_score)s, %(clarity_status)s, %(missing_fields)s, %(needs_human_review)s, %(oversight_reason)s
        )
        ON CONFLICT (matter_code) DO UPDATE SET
            status = EXCLUDED.status,
            stage = EXCLUDED.stage,
            forum = EXCLUDED.forum,
            n_facts_verified = EXCLUDED.n_facts_verified,
            n_facts_provisional = EXCLUDED.n_facts_provisional,
            n_fields_total = EXCLUDED.n_fields_total,
            n_fields_verified = EXCLUDED.n_fields_verified,
            ctns = EXCLUDED.ctns,
            tcts = EXCLUDED.tcts,
            dockets = EXCLUDED.dockets,
            parties = EXCLUDED.parties,
            key_dates = EXCLUDED.key_dates,
            amounts = EXCLUDED.amounts,
            next_deadline = EXCLUDED.next_deadline,
            n_open_contradictions = EXCLUDED.n_open_contradictions,
            top_doc_ids = EXCLUDED.top_doc_ids,
            readiness = EXCLUDED.readiness,
            headline = EXCLUDED.headline,
            angle_status = EXCLUDED.angle_status,
            source_fingerprint = EXCLUDED.source_fingerprint,
            computed_at = now(),
            clarity_score = EXCLUDED.clarity_score,
            clarity_status = EXCLUDED.clarity_status,
            missing_fields = EXCLUDED.missing_fields,
            needs_human_review = EXCLUDED.needs_human_review,
            oversight_reason = EXCLUDED.oversight_reason
        """,
        row,
    )
    print(f"  {row['headline']}")


def run(matter: str | None, go: bool, stale_only: bool):
    c = psycopg2.connect(DSN)
    c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if matter:
        codes = [matter]
    elif stale_only:
        cur.execute(
            """
            SELECT matter_code FROM v_matter_brief_staleness
            WHERE missing_brief OR is_stale
            ORDER BY matter_code
            """
        )
        codes = [r["matter_code"] for r in cur.fetchall()]
    else:
        cur.execute(
            """
            SELECT matter_code FROM matters
            WHERE coalesce(status,'') NOT IN ('archived')
            ORDER BY matter_code
            """
        )
        codes = [r["matter_code"] for r in cur.fetchall()]

    print(f"[brief] materializing {len(codes)} matter(s) ({'GO' if go else 'DRY'})")
    for mc in codes:
        row = materialize_one(cur, mc)
        upsert(cur, row, go)

    if go:
        cur.execute(
            """
            INSERT INTO equilibrium_coverage_log
                (n_facts, n_facts_verified, n_facts_with_fields, typed_coverage_pct,
                 n_briefs, n_briefs_stale, notes)
            SELECT
                (SELECT count(*) FROM matter_facts),
                (SELECT count(*) FROM matter_facts WHERE provenance_level='verified'),
                (SELECT count(DISTINCT fact_id) FROM fact_fields),
                CASE WHEN (SELECT count(*) FROM matter_facts)=0 THEN 0
                     ELSE round(100.0 * (SELECT count(DISTINCT fact_id) FROM fact_fields)
                                / (SELECT count(*) FROM matter_facts), 2) END,
                (SELECT count(*) FROM matter_brief),
                (SELECT count(*) FROM v_matter_brief_staleness WHERE is_stale OR missing_brief),
                'materialize_matter_brief'
            """
        )
    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", default=None)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--stale-only", action="store_true")
    a = ap.parse_args()
    run(a.matter, a.go, a.stale_only)


if __name__ == "__main__":
    main()
