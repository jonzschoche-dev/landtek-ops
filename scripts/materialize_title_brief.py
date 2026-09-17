#!/usr/bin/env python3
"""materialize_title_brief.py — one UI-ready row per title (DERIVED, rebuildable).

Aggregates SoR + projections for property classification UI (later: maps + full card):
  titles · title_chain · instruments_on_title · document_titles · fact_fields
  property_assets · property_readiness · map_parcels · parcels · title_tax_links
  title_matter_links

  python3 scripts/materialize_title_brief.py --go
  python3 scripts/materialize_title_brief.py --title T-4497 --go
  python3 scripts/materialize_title_brief.py --client MWK-001 --go
"""
from __future__ import annotations

import argparse
import json
import os
import re

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _norm_key(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").upper())


def _variants(title_key: str) -> list[str]:
    """Match forms used across tables for the same title."""
    k = _norm_key(title_key)
    vs = {k, k.lstrip("TCT").lstrip("-"), k}
    if k.startswith("T-"):
        vs.add(k[2:])
        vs.add("TCT" + k)
        vs.add("TCT-" + k[2:])
        vs.add("TCT No. " + k[2:])
    if k.startswith("OCT-"):
        vs.add(k[4:])
        vs.add("OCT " + k[4:])
        vs.add("OCT No. " + k[4:])
    if re.match(r"^\d{3}-\d{10,}$", k):
        vs.add(k)
        vs.add("T-" + k)
    # fact_fields norms
    if k.startswith("T-"):
        vs.add(k)
    return [v for v in vs if v]


def _like_any(cur, sql_template: str, variants: list[str], extra=()):
    """Run OR of equality on variants — safer than bare ILIKE % for short keys."""
    if not variants:
        return []
    conds = " OR ".join(["%s = ANY(%s)" % ("x", "%s")] )  # placeholder - rewrite per call
    return []


def materialize_one(cur, title_key: str, seed: dict | None = None) -> dict:
    key = _norm_key(title_key)
    variants = _variants(key)
    kind = (seed or {}).get("title_kind") or "unknown"
    if kind == "unknown":
        if key.startswith("OCT"):
            kind = "oct"
        elif re.match(r"^\d{3}-\d{10,}$", key):
            kind = "e_title"
        elif key.startswith("T-") or key[0:1].isdigit():
            kind = "tct"

    display = (seed or {}).get("display_no") or key

    # ── titles SoR ──
    cur.execute(
        """
        SELECT * FROM titles
        WHERE upper(regexp_replace(tct_number, '\\s+', '', 'g')) = ANY(%s)
           OR tct_number = ANY(%s)
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """,
        (variants, variants),
    )
    trow = cur.fetchone()
    registrant = None
    area = None
    location = None
    status = None
    lifecycle = None
    case_file = (seed or {}).get("case_file")
    source_docs: list[int] = []
    if trow:
        display = trow.get("tct_number") or display
        registrant = trow.get("registrant_canonical") or trow.get("registrant_name_raw")
        area = trow.get("area_sqm")
        location = trow.get("location")
        status = trow.get("status")
        lifecycle = trow.get("lifecycle_status")
        case_file = case_file or trow.get("case_file")
        if trow.get("source_doc_id"):
            try:
                source_docs.append(int(trow["source_doc_id"]))
            except (TypeError, ValueError):
                pass

    # ── chain ──
    cur.execute(
        """
        SELECT parent_title FROM title_chain
        WHERE upper(regexp_replace(child_title, '\\s+', '', 'g')) = ANY(%s)
           OR child_title = ANY(%s)
        """,
        (variants, variants),
    )
    parents = sorted({r["parent_title"] for r in cur.fetchall() if r["parent_title"]})
    cur.execute(
        """
        SELECT child_title FROM title_chain
        WHERE upper(regexp_replace(parent_title, '\\s+', '', 'g')) = ANY(%s)
           OR parent_title = ANY(%s)
        """,
        (variants, variants),
    )
    children = sorted({r["child_title"] for r in cur.fetchall() if r["child_title"]})

    # ── matters ──
    matters = set()
    cur.execute(
        """
        SELECT matter_code FROM title_matter_links
        WHERE upper(regexp_replace(title_no, '\\s+', '', 'g')) = ANY(%s)
           OR title_no = ANY(%s)
        """,
        (variants, variants),
    )
    matters.update(r["matter_code"] for r in cur.fetchall() if r["matter_code"])

    # ── fact_fields mentions ──
    cur.execute(
        """
        SELECT fact_id, matter_code, field_kind, value_norm, provenance_level
        FROM fact_fields
        WHERE field_kind IN ('tct','oct','e_title')
          AND (
            upper(regexp_replace(value_norm, '\\s+', '', 'g')) = ANY(%s)
            OR value_norm = ANY(%s)
          )
        """,
        (variants, variants),
    )
    frows = cur.fetchall()
    n_facts = len({r["fact_id"] for r in frows})
    n_v = len({r["fact_id"] for r in frows if r["provenance_level"] == "verified"})
    matters.update(r["matter_code"] for r in frows if r["matter_code"])
    top_fact_ids = sorted({r["fact_id"] for r in frows})[:20]
    if frows and kind == "unknown":
        kind = frows[0]["field_kind"]

    # co-mentioned tax_dec / survey on same facts
    tax_decs: list[str] = []
    surveys: list[str] = []
    if top_fact_ids:
        cur.execute(
            """
            SELECT DISTINCT field_kind, value_norm FROM fact_fields
            WHERE fact_id = ANY(%s) AND field_kind IN ('tax_dec','survey')
            """,
            (top_fact_ids,),
        )
        for r in cur.fetchall():
            if r["field_kind"] == "tax_dec":
                tax_decs.append(r["value_norm"])
            else:
                surveys.append(r["value_norm"])

    cur.execute(
        """
        SELECT arp_no FROM title_tax_links
        WHERE upper(regexp_replace(title_no, '\\s+', '', 'g')) = ANY(%s)
           OR title_no = ANY(%s)
        """,
        (variants, variants),
    )
    tax_decs.extend(r["arp_no"] for r in cur.fetchall() if r["arp_no"])
    tax_decs = sorted(set(tax_decs))
    surveys = sorted(set(surveys))

    # ── documents ──
    cur.execute(
        """
        SELECT DISTINCT doc_id FROM document_titles
        WHERE upper(regexp_replace(tct_number, '\\s+', '', 'g')) = ANY(%s)
           OR tct_number = ANY(%s)
        """,
        (variants, variants),
    )
    for r in cur.fetchall():
        if r["doc_id"]:
            source_docs.append(int(r["doc_id"]))

    # ── instruments ──
    cur.execute(
        """
        SELECT count(*) AS n,
               array_agg(DISTINCT instrument_type) FILTER (WHERE instrument_type IS NOT NULL) AS types
        FROM instruments_on_title
        WHERE parent_tct_number IS NOT NULL
          AND (
            upper(regexp_replace(parent_tct_number, '\\s+', '', 'g')) = ANY(%s)
            OR parent_tct_number = ANY(%s)
          )
        """,
        (variants, variants),
    )
    inst = cur.fetchone() or {}
    n_instruments = int(inst.get("n") or 0)
    inst_types = [x for x in (inst.get("types") or []) if x][:12]

    # also instruments that only appear in quote with this title — skip for now

    # ── property assets + readiness ──
    cur.execute(
        """
        SELECT asset_code, client_code, title_status, possession, area_sqm, location, label, title_ref
        FROM property_assets
        WHERE title_ref IS NOT NULL
          AND (
            upper(regexp_replace(title_ref, '\\s+', '', 'g')) = ANY(%s)
            OR title_ref = ANY(%s)
          )
        """,
        (variants, variants),
    )
    assets = cur.fetchall()
    asset_codes = [a["asset_code"] for a in assets]
    title_status_asset = None
    possession = None
    client_code = None
    for a in assets:
        client_code = client_code or a.get("client_code")
        title_status_asset = title_status_asset or a.get("title_status")
        possession = possession or a.get("possession")
        if area is None and a.get("area_sqm") is not None:
            area = a["area_sqm"]
        if not location and a.get("location"):
            location = a["location"]

    readiness_score = None
    if asset_codes:
        cur.execute(
            """
            SELECT readiness_score, weakest_axis, next_prep_action
            FROM property_readiness
            WHERE asset_code = ANY(%s)
            ORDER BY readiness_score ASC NULLS LAST
            LIMIT 1
            """,
            (asset_codes,),
        )
        rr = cur.fetchone()
        if rr:
            readiness_score = rr.get("readiness_score")

    # ── maps / parcels ──
    cur.execute(
        """
        SELECT id, has_geom FROM (
          SELECT id,
                 (geom_geojson IS NOT NULL OR centroid_lat IS NOT NULL) AS has_geom
          FROM map_parcels
          WHERE title_no IS NOT NULL
            AND (
              upper(regexp_replace(title_no, '\\s+', '', 'g')) = ANY(%s)
              OR title_no = ANY(%s)
            )
        ) x
        """,
        (variants, variants),
    )
    maps = cur.fetchall()
    map_ids = [int(r["id"]) for r in maps]
    has_map = any(r["has_geom"] for r in maps)

    cur.execute(
        """
        SELECT id, area_sqm FROM parcels
        WHERE title_no IS NOT NULL
          AND (
            upper(regexp_replace(title_no, '\\s+', '', 'g')) = ANY(%s)
            OR title_no = ANY(%s)
          )
        LIMIT 5
        """,
        (variants, variants),
    )
    parcel_rows = cur.fetchall()
    if area is None and parcel_rows:
        area = parcel_rows[0].get("area_sqm")

    # map case_file → client if MWK-001 style
    if not client_code and case_file:
        client_code = case_file if "-" in str(case_file) else case_file

    source_docs = sorted(set(source_docs))[:40]
    matters_l = sorted(matters)

    # ── Clarity: be explicit when data is thin — never look finished when it isn't ──
    # Core axes for "title table intake" (maps/tax/chain are enrichment, not core)
    core_checks = {
        "registrant": bool(registrant and str(registrant).strip() not in ("", "—")),
        "area": area is not None,
        "status": bool(title_status_asset or status or lifecycle),
        "source_doc": len(source_docs) > 0,
        "matter_link": len(matters_l) > 0,
        "identity": bool(key and len(key) >= 3),
    }
    missing = sorted(k for k, ok in core_checks.items() if not ok)
    filled = sum(1 for ok in core_checks.values() if ok)
    clarity_score = round(filled / max(len(core_checks), 1), 3)
    if clarity_score >= 0.80:
        clarity_status = "clear"
    elif clarity_score >= 0.50:
        clarity_status = "partial"
    else:
        clarity_status = "unclear"

    # Human oversight: unclear always; partial with zero docs; identity-only stubs
    needs_human = clarity_status == "unclear" or (
        clarity_status == "partial" and "source_doc" in missing
    )
    oversight_reason = None
    if needs_human:
        oversight_reason = (
            f"clarity={clarity_status} ({clarity_score:.0%}); missing: {', '.join(missing) or '—'}. "
            "Do not treat this title card as complete; pull CTC/tax/registrant from source."
        )

    # headline — deterministic; UNCLEAR prefix when human must look
    reg = registrant or "—"
    st = title_status_asset or status or lifecycle or "—"
    ar = f"{float(area):,.0f} sqm" if area not in (None, "") else "area UNCLEAR"
    loc = (location or "—")[:60]
    prefix = "⚠ UNCLEAR · " if clarity_status == "unclear" else (
        "◐ PARTIAL · " if clarity_status == "partial" else ""
    )
    headline = f"{prefix}{display} · {kind} · {st} · {reg} · {ar} · {loc}"

    card = {
        "title_key": key,
        "title_kind": kind,
        "display_no": display,
        "registrant": registrant,
        "area_sqm": float(area) if area is not None else None,
        "location": location,
        "status": status,
        "lifecycle_status": lifecycle,
        "title_status": title_status_asset,
        "possession": possession,
        "parents": parents,
        "children": children,
        "matters": matters_l,
        "tax_decs": tax_decs,
        "surveys": surveys,
        "instruments": {"count": n_instruments, "types": inst_types},
        "docs": source_docs,
        "assets": asset_codes,
        "map": {"parcel_ids": map_ids, "has_geometry": has_map},
        "readiness_score": float(readiness_score) if readiness_score is not None else None,
        "facts": {"mentions": n_facts, "verified": n_v},
        "clarity": {
            "score": clarity_score,
            "status": clarity_status,
            "missing": missing,
            "needs_human_review": needs_human,
            "oversight_reason": oversight_reason,
        },
        "ui_ready": {
            "list_label": display,
            "subtitle": f"{clarity_status} · {kind} · {st}",
            "has_map": has_map,
            "has_tax": bool(tax_decs),
            "has_chain": bool(parents or children),
            "n_docs": len(source_docs),
            "badge": clarity_status,  # UI: clear / partial / unclear
        },
    }

    fp = f"{key}|d{len(source_docs)}|f{n_facts}|i{n_instruments}|m{int(has_map)}|t{len(tax_decs)}|c{clarity_score}"

    return {
        "title_key": key,
        "title_kind": kind,
        "display_no": display,
        "case_file": case_file,
        "client_code": client_code,
        "registrant_name": registrant,
        "area_sqm": area,
        "location": location,
        "status": status,
        "lifecycle_status": lifecycle,
        "parent_titles": parents,
        "child_titles": children,
        "related_matters": matters_l,
        "tax_decs": tax_decs,
        "survey_refs": surveys,
        "asset_codes": asset_codes,
        "n_instruments": n_instruments,
        "n_source_docs": len(source_docs),
        "n_facts_mentioning": n_facts,
        "n_facts_verified": n_v,
        "source_doc_ids": source_docs,
        "top_fact_ids": top_fact_ids[:20],
        "map_parcel_ids": map_ids,
        "has_map_geometry": has_map,
        "readiness_score": readiness_score,
        "title_status_asset": title_status_asset,
        "possession": possession,
        "headline": headline[:500],
        "card": json.dumps(card),
        "source_fingerprint": fp,
        "clarity_score": clarity_score,
        "clarity_status": clarity_status,
        "missing_fields": missing,
        "needs_human_review": needs_human,
        "oversight_reason": oversight_reason,
    }


def _flag_oversight(cur, row: dict):
    """Visible human-oversight queue via holes_findings (idempotent open row)."""
    if not row.get("needs_human_review"):
        return
    key = f"title_clarity|{row['title_key']}"
    try:
        cur.execute(
            """
            INSERT INTO holes_findings (
                routine_name, routine_version, finding_id_hash, severity, hole_type,
                case_file, matter_code, description, suggested_fix, metadata, status
            )
            SELECT
                'title_brief_clarity', 'v1', md5(%s), 'medium', 'title_unclear',
                %s, %s, %s,
                'Pull CTC / tax dec / registrant from RD or source docs; re-run materialize_title_brief.',
                jsonb_build_object(
                    'title_key', %s,
                    'clarity_status', %s,
                    'clarity_score', %s,
                    'missing', %s::jsonb
                ),
                'open'
            WHERE NOT EXISTS (
                SELECT 1 FROM holes_findings
                WHERE finding_id_hash = md5(%s) AND status = 'open'
            )
            """,
            (
                key,
                row.get("case_file") or row.get("client_code"),
                (row.get("related_matters") or [None])[0],
                (row.get("oversight_reason") or "Title card incomplete")[:900],
                row["title_key"],
                row.get("clarity_status"),
                float(row.get("clarity_score") or 0),
                json.dumps(row.get("missing_fields") or []),
                key,
            ),
        )
    except Exception:
        pass  # oversight log must never break materialize


def upsert(cur, row: dict, go: bool):
    if not row:
        return
    if not go:
        print(f"  [dry] {row['headline'][:100]}")
        return
    cur.execute(
        """
        INSERT INTO title_brief (
            title_key, title_kind, display_no, case_file, client_code,
            registrant_name, area_sqm, location, status, lifecycle_status,
            parent_titles, child_titles, related_matters, tax_decs, survey_refs,
            asset_codes, n_instruments, n_source_docs, n_facts_mentioning, n_facts_verified,
            source_doc_ids, top_fact_ids, map_parcel_ids, has_map_geometry,
            readiness_score, title_status_asset, possession,
            headline, card, source_fingerprint, computed_at,
            clarity_score, clarity_status, missing_fields, needs_human_review, oversight_reason
        ) VALUES (
            %(title_key)s, %(title_kind)s, %(display_no)s, %(case_file)s, %(client_code)s,
            %(registrant_name)s, %(area_sqm)s, %(location)s, %(status)s, %(lifecycle_status)s,
            %(parent_titles)s, %(child_titles)s, %(related_matters)s, %(tax_decs)s, %(survey_refs)s,
            %(asset_codes)s, %(n_instruments)s, %(n_source_docs)s, %(n_facts_mentioning)s, %(n_facts_verified)s,
            %(source_doc_ids)s, %(top_fact_ids)s, %(map_parcel_ids)s, %(has_map_geometry)s,
            %(readiness_score)s, %(title_status_asset)s, %(possession)s,
            %(headline)s, %(card)s::jsonb, %(source_fingerprint)s, now(),
            %(clarity_score)s, %(clarity_status)s, %(missing_fields)s, %(needs_human_review)s, %(oversight_reason)s
        )
        ON CONFLICT (title_key) DO UPDATE SET
            title_kind = EXCLUDED.title_kind,
            display_no = EXCLUDED.display_no,
            case_file = EXCLUDED.case_file,
            client_code = EXCLUDED.client_code,
            registrant_name = EXCLUDED.registrant_name,
            area_sqm = EXCLUDED.area_sqm,
            location = EXCLUDED.location,
            status = EXCLUDED.status,
            lifecycle_status = EXCLUDED.lifecycle_status,
            parent_titles = EXCLUDED.parent_titles,
            child_titles = EXCLUDED.child_titles,
            related_matters = EXCLUDED.related_matters,
            tax_decs = EXCLUDED.tax_decs,
            survey_refs = EXCLUDED.survey_refs,
            asset_codes = EXCLUDED.asset_codes,
            n_instruments = EXCLUDED.n_instruments,
            n_source_docs = EXCLUDED.n_source_docs,
            n_facts_mentioning = EXCLUDED.n_facts_mentioning,
            n_facts_verified = EXCLUDED.n_facts_verified,
            source_doc_ids = EXCLUDED.source_doc_ids,
            top_fact_ids = EXCLUDED.top_fact_ids,
            map_parcel_ids = EXCLUDED.map_parcel_ids,
            has_map_geometry = EXCLUDED.has_map_geometry,
            readiness_score = EXCLUDED.readiness_score,
            title_status_asset = EXCLUDED.title_status_asset,
            possession = EXCLUDED.possession,
            headline = EXCLUDED.headline,
            card = EXCLUDED.card,
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
    _flag_oversight(cur, row)


def run(title: str | None, client: str | None, go: bool, limit: int | None):
    c = psycopg2.connect(DSN)
    c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if title:
        seeds = [{"title_key": _norm_key(title), "title_kind": "unknown", "display_no": title, "case_file": None, "source": "cli"}]
    else:
        # Prefer grounded sources for the 90% intake set — not every OCR fragment in fact_fields.
        # Grounded = titles SoR OR document_titles OR property_assets OR verified fact_fields.
        cur.execute(
            """
            SELECT DISTINCT ON (title_key) title_key, title_kind, display_no, case_file, source
            FROM (
                SELECT upper(regexp_replace(tct_number, '\\s+', '', 'g')) AS title_key,
                       CASE WHEN tct_number ~* '^OCT' THEN 'oct'
                            WHEN tct_number ~ '^\\d{3}-\\d{10,}' THEN 'e_title' ELSE 'tct' END AS title_kind,
                       tct_number AS display_no, case_file, 'titles'::text AS source, 1 AS pri
                FROM titles WHERE coalesce(tct_number,'') <> ''
                UNION ALL
                SELECT upper(regexp_replace(tct_number, '\\s+', '', 'g')), 'tct', tct_number, NULL, 'document_titles', 2
                FROM document_titles WHERE coalesce(tct_number,'') <> ''
                UNION ALL
                SELECT upper(regexp_replace(title_ref, '\\s+', '', 'g')),
                       CASE WHEN title_ref ~ '^\\d{3}-\\d{10,}' THEN 'e_title' ELSE 'tct' END,
                       title_ref, client_code, 'property_assets', 2
                FROM property_assets WHERE coalesce(title_ref,'') <> ''
                UNION ALL
                SELECT upper(regexp_replace(value_norm, '\\s+', '', 'g')), field_kind, value_norm, NULL, 'fact_fields_verified', 3
                FROM fact_fields
                WHERE field_kind IN ('tct','oct','e_title')
                  AND provenance_level = 'verified'
                  AND coalesce(value_norm,'') <> ''
            ) u
            ORDER BY title_key, pri
            """
        )
        seeds = cur.fetchall()
        if client:
            seeds = [s for s in seeds if not s.get("case_file") or client in str(s.get("case_file"))]
        if limit:
            seeds = seeds[:limit]

    # dedupe by key + quality gates (no phantom OCT-04 / T-1 stubs)
    seen = set()
    unique = []
    for s in seeds:
        k = _norm_key(s["title_key"] if "title_key" in s else s.get("display_no", ""))
        if not k or k in seen:
            continue
        if len(k) < 4 or k in ("T-", "OCT-", "TCT", "OCT"):
            continue
        if re.fullmatch(r"T-\d{1,2}", k) or re.fullmatch(r"OCT-?\d{1,2}", k):
            continue
        # OCT-T-106 style from bad OCR: require at least 3 digit body for OCT
        if k.startswith("OCT") and len(re.sub(r"\D", "", k)) < 3:
            continue
        seen.add(k)
        unique.append({**dict(s), "title_key": k})

    print(f"[title_brief] materializing {len(unique)} title(s) ({'GO' if go else 'DRY'})")
    n_ok = 0
    for s in unique:
        try:
            row = materialize_one(cur, s["title_key"], s)
            upsert(cur, row, go)
            n_ok += 1
            if go and n_ok <= 8:
                print(f"  {row['headline'][:110]}")
        except Exception as e:
            print(f"  ! {s['title_key']}: {type(e).__name__}: {e}")
            c.rollback()
            c.autocommit = True

    if go:
        cur.execute(
            """
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE has_map_geometry) AS maps,
                   count(*) FILTER (WHERE clarity_status = 'clear') AS clear,
                   count(*) FILTER (WHERE clarity_status = 'partial') AS partial,
                   count(*) FILTER (WHERE clarity_status = 'unclear') AS unclear,
                   count(*) FILTER (WHERE needs_human_review) AS review
            FROM title_brief
            """
        )
        r = cur.fetchone()
        usable = int(r["clear"] or 0) + int(r["partial"] or 0)
        pct = (100.0 * usable / r["n"]) if r["n"] else 0
        print(
            f"[title_brief] rows={r['n']} clear={r['clear']} partial={r['partial']} "
            f"unclear={r['unclear']} need_review={r['review']} "
            f"usable_intake={pct:.1f}% (target ≥90%) with_map={r['maps']}"
        )
        cur.execute(
            """
            SELECT title_kind, count(*) n FROM title_brief GROUP BY 1 ORDER BY n DESC
            """
        )
        for row in cur.fetchall():
            print(f"  {row['title_kind']:<10} {row['n']}")

    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default=None)
    ap.add_argument("--client", default=None)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.title, a.client, a.go, a.limit)


if __name__ == "__main__":
    main()
