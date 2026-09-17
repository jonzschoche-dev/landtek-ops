#!/usr/bin/env python3
"""activate_map_portfolio.py — make existing map/tax/survey stack LIVE for a client.

Uses ONLY existing tables/engines (no new design):
  titles              → seed map_parcels (status=awaiting_plot)
  property_assets     → asset_code on map row
  document_fields     → title_tax_links (co-occurrence)
  parcels / courses   → stated_area, geometry_priority, title_brief flags
  materialize_title_brief → has_map_geometry etc.

  python3 scripts/activate_map_portfolio.py --client MWK-001
  python3 scripts/activate_map_portfolio.py --client MWK-001 --go
  python3 scripts/activate_map_portfolio.py --client MWK-001 --go --geometry-drip
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
_SKIP = ("invalid", "alias", "out_of_scope", "cancelled")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _as_dicts(cur, rows=None):
    rows = list(rows if rows is not None else (cur.fetchall() or []))
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, r)) for r in rows]


def _parcel_code(client: str, tct: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (tct or "").strip().upper()).strip("-")
    base = f"{client.split('-')[0]}-{slug}"[:80]
    return base


def seed_map_parcels(cur, client: str, go: bool) -> dict:
    cur.execute(
        """
        SELECT t.tct_number, t.status, t.area_sqm, t.case_file,
               t.registrant_name_raw, t.lifecycle_status
          FROM titles t
         WHERE (t.case_file = %s OR t.case_file LIKE %s)
           AND t.case_file NOT ILIKE 'Paracale%%'
           AND coalesce(t.status,'') NOT IN %s
           AND coalesce(t.status,'') NOT ILIKE '%%cancel%%'
         ORDER BY t.tct_number
        """,
        (client, client + "%", _SKIP),
    )
    titles = _as_dicts(cur)
    # asset lookup
    cur.execute(
        """
        SELECT title_ref, asset_code FROM property_assets
         WHERE client_code = %s OR case_file = %s
        """,
        (client, client),
    )
    assets = {}
    for r in _as_dicts(cur):
        if r.get("title_ref"):
            assets[re.sub(r"\s+", "", r["title_ref"].upper())] = r["asset_code"]

    n_ins = n_upd = 0
    for t in titles:
        tct = t["tct_number"]
        pc = _parcel_code(client, tct)
        key = re.sub(r"\s+", "", (tct or "").upper())
        asset = assets.get(key)
        label = f"{tct} — {t.get('status') or '?'}"
        if t.get("registrant_name_raw"):
            label = f"{tct} — {(t['registrant_name_raw'] or '')[:40]}"
        stated = t.get("area_sqm")
        note = (
            f"seeded from titles SoR status={t.get('status')} "
            f"lifecycle={t.get('lifecycle_status')} activate_map_portfolio"
        )
        if not go:
            n_ins += 1
            continue
        cur.execute(
            """
            INSERT INTO map_parcels (
                parcel_code, client_code, matter_code, title_no, label,
                stated_area_sqm, status, source_note, asset_code, accuracy_tier
            ) VALUES (%s,%s,%s,%s,%s,%s,'awaiting_plot',%s,%s,NULL)
            ON CONFLICT (parcel_code) DO UPDATE SET
                title_no = EXCLUDED.title_no,
                label = COALESCE(EXCLUDED.label, map_parcels.label),
                stated_area_sqm = COALESCE(EXCLUDED.stated_area_sqm, map_parcels.stated_area_sqm),
                asset_code = COALESCE(EXCLUDED.asset_code, map_parcels.asset_code),
                source_note = CASE
                    WHEN map_parcels.source_note ILIKE '%%activate_map_portfolio%%'
                    THEN map_parcels.source_note
                    ELSE coalesce(map_parcels.source_note,'') || ' | ' || EXCLUDED.source_note
                END,
                updated_at = now()
            RETURNING (xmax = 0) AS inserted
            """,
            (pc, client, client, tct, label, stated, note, asset),
        )
        row = cur.fetchone()
        # xmax=0 means insert in PostgreSQL system columns for INSERT...RETURNING
        # Simpler: count
        n_ins += 1
    # Keep legacy MWK-BALANE if present
    return {"titles": len(titles), "map_rows_touched": n_ins}


def promote_tax_links(cur, client: str, go: bool) -> int:
    """Co-occurrence of tct + tax_dec on same MWK doc → title_tax_links."""
    cur.execute(
        """
        SELECT tct.value_norm AS title_no,
               tax.value_norm AS arp_no,
               tct.doc_id AS source_doc_id,
               count(*)::int AS n
          FROM document_fields tct
          JOIN document_fields tax
            ON tax.doc_id = tct.doc_id AND tax.field_kind = 'tax_dec'
          JOIN documents d ON d.id = tct.doc_id
         WHERE tct.field_kind = 'tct'
           AND (d.case_file = %s OR d.case_file LIKE %s OR d.matter_code LIKE %s)
           AND length(tax.value_norm) >= 6
           AND (tct.value_norm ~ '^T-' OR tct.value_norm ~ '^[0-9]{3}-')
         GROUP BY 1, 2, 3
         HAVING count(*) >= 1
        """,
        (client, client + "%", client.split("-")[0] + "%"),
    )
    pairs = _as_dicts(cur)
    n = 0
    for p in pairs:
        title = (p["title_no"] or "").strip()
        arp = (p["arp_no"] or "").strip()
        if not title or not arp:
            continue
        if not go:
            n += 1
            continue
        try:
            cur.execute(
                """
                INSERT INTO title_tax_links
                    (title_no, arp_no, link_source, source_doc_id, confidence, notes)
                VALUES (%s,%s,'activate_map_portfolio_cooccur',%s,0.75,%s)
                ON CONFLICT (title_no, arp_no) DO NOTHING
                """,
                (
                    title, arp, p["source_doc_id"],
                    f"TCT {title} + tax {arp} co-occur in doc {p['source_doc_id']}",
                ),
            )
            n += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        except Exception:
            pass
    # recount would-be
    if not go:
        return len(pairs)
    cur.execute("SELECT count(*) AS n FROM title_tax_links")
    return int((_as_dicts(cur) or [{"n": n}])[0].get("n") or n)


def seed_geometry_priority(cur, client: str, go: bool) -> int:
    """Priority docs: source CTC/plan docs for living titles (for geometry drip)."""
    cur.execute(
        """
        SELECT DISTINCT d.id AS doc_id, t.tct_number AS title_no, t.case_file AS matter_code
          FROM titles t
          JOIN documents d ON d.id = t.source_doc_id
         WHERE (t.case_file = %s OR t.case_file LIKE %s)
           AND t.case_file NOT ILIKE 'Paracale%%'
           AND coalesce(t.status,'') NOT IN %s
           AND t.source_doc_id IS NOT NULL
        UNION
        SELECT DISTINCT d.id, tb.title_key, %s
          FROM title_brief tb
          JOIN LATERAL unnest(COALESCE(tb.source_doc_ids, ARRAY[]::int[])) AS x(doc_id) ON true
          JOIN documents d ON d.id = x.doc_id
         WHERE (tb.client_code = %s OR tb.case_file = %s OR tb.title_key LIKE 'T-%%')
           AND tb.n_source_docs > 0
         LIMIT 200
        """,
        (client, client + "%", _SKIP, client, client, client),
    )
    # Simpler reliable query if lateral fails
    try:
        rows = _as_dicts(cur)
    except Exception:
        cur.execute(
            """
            SELECT DISTINCT d.id AS doc_id, t.tct_number AS title_no,
                   coalesce(t.case_file, %s) AS matter_code
              FROM titles t
              JOIN documents d ON d.id = t.source_doc_id
             WHERE t.case_file = %s
               AND coalesce(t.status,'') NOT IN %s
               AND t.source_doc_id IS NOT NULL
            """,
            (client, client, _SKIP),
        )
        rows = _as_dicts(cur)

    # Also docs that mention surveys + tct for living titles
    cur.execute(
        """
        SELECT DISTINCT df.doc_id, df.value_norm AS title_no, %s AS matter_code
          FROM document_fields df
          JOIN documents d ON d.id = df.doc_id
         WHERE df.field_kind = 'tct'
           AND (d.case_file = %s OR d.matter_code LIKE %s)
           AND EXISTS (
               SELECT 1 FROM document_fields s
                WHERE s.doc_id = df.doc_id AND s.field_kind = 'survey'
           )
         LIMIT 80
        """,
        (client, client, client.split("-")[0] + "%"),
    )
    rows2 = _as_dicts(cur)
    seen = set()
    all_rows = []
    for r in rows + rows2:
        did = r.get("doc_id")
        if did in seen:
            continue
        seen.add(did)
        all_rows.append(r)

    n = 0
    rank = 10
    for r in all_rows:
        if not go:
            n += 1
            continue
        try:
            cur.execute(
                """
                INSERT INTO geometry_priority (doc_id, title_no, matter_code, rank, note)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    title_no = COALESCE(EXCLUDED.title_no, geometry_priority.title_no),
                    rank = LEAST(geometry_priority.rank, EXCLUDED.rank),
                    note = coalesce(geometry_priority.note,'') || ' | activate_map_portfolio'
                """,
                (
                    r["doc_id"], r.get("title_no"), r.get("matter_code") or client,
                    rank, "activate_map_portfolio living title / survey co-occur",
                ),
            )
            n += 1
            rank = min(rank + 1, 500)
        except Exception as e:
            print(f"  geometry_priority skip doc {r.get('doc_id')}: {e}")
    return n


def sync_brief_map_flags(cur, client: str, go: bool) -> int:
    """Set has_map_geometry true when parcels or map_parcels has geom for title."""
    if not go:
        return 0
    cur.execute(
        """
        UPDATE title_brief tb
           SET has_map_geometry = true,
               computed_at = now()
         WHERE EXISTS (
               SELECT 1 FROM parcels p
                WHERE upper(regexp_replace(p.title_no, '\\s+', '', 'g'))
                    = upper(regexp_replace(tb.title_key, '\\s+', '', 'g'))
                  AND p.geom_wkt IS NOT NULL
           )
            OR EXISTS (
               SELECT 1 FROM map_parcels m
                WHERE m.title_no = tb.title_key
                  AND m.geom_geojson IS NOT NULL
                  AND m.client_code = %s
           )
        """,
        (client,),
    )
    return cur.rowcount or 0


def link_asset_map(cur, client: str, go: bool) -> int:
    """Fill asset_map_parcels from map_parcels.asset_code when both exist."""
    if not go:
        return 0
    # Discover schema
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'asset_map_parcels' ORDER BY 1
        """
    )
    cols = {r["column_name"] for r in _as_dicts(cur)}
    if not cols:
        return 0
    # Minimal insert if table has asset_code + parcel_code/map id
    try:
        cur.execute(
            """
            INSERT INTO asset_map_parcels (asset_code, client_code, parcel_code)
            SELECT m.asset_code, m.client_code, m.parcel_code
              FROM map_parcels m
             WHERE m.client_code = %s
               AND m.asset_code IS NOT NULL
            ON CONFLICT DO NOTHING
            """,
            (client,),
        )
        return cur.rowcount or 0
    except Exception as e:
        # schema variants
        try:
            cur.execute(
                """
                INSERT INTO asset_map_parcels (asset_code, client_code, parcel_code, link_role, linked_by)
                SELECT m.asset_code, m.client_code, m.parcel_code, 'site', 'activate_map_portfolio'
                  FROM map_parcels m
                 WHERE m.client_code = %s AND m.asset_code IS NOT NULL
                ON CONFLICT DO NOTHING
                """,
                (client,),
            )
            return cur.rowcount or 0
        except Exception as e2:
            print(f"[map] asset_map_parcels link skip: {e2}")
            return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client", default="MWK-001")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--geometry-drip", action="store_true",
                    help="run one geometry_pipeline drip after seed")
    ap.add_argument("--strip-only", action="store_true",
                    help="re-parse clean texts to parcels without re-OCR")
    ap.add_argument("--briefs", action="store_true", help="rematerialize title briefs")
    a = ap.parse_args()

    c = _conn()
    cur = _cur(c)
    print(f"[activate_map] client={a.client} go={a.go}")

    # Ensure client_code exists for FK
    cur.execute("SELECT client_code FROM clients WHERE client_code=%s", (a.client,))
    if not cur.fetchone():
        # try insert minimal client if allowed
        try:
            if a.go:
                cur.execute(
                    """
                    INSERT INTO clients (name, case_file, client_code, role, status, source)
                    VALUES (%s,%s,%s,'client','Active','activate_map_portfolio')
                    ON CONFLICT DO NOTHING
                    """,
                    (a.client, a.client, a.client),
                )
        except Exception as e:
            print(f"[activate_map] clients ensure: {e}")

    m = seed_map_parcels(cur, a.client, a.go)
    print(f"[activate_map] map_parcels living titles={m['titles']} rows_touched={m['map_rows_touched']}")

    tax_n = promote_tax_links(cur, a.client, a.go)
    print(f"[activate_map] title_tax_links pairs_processed={tax_n}")

    gp = seed_geometry_priority(cur, a.client, a.go)
    print(f"[activate_map] geometry_priority docs={gp}")

    am = link_asset_map(cur, a.client, a.go)
    print(f"[activate_map] asset_map links={am}")

    bf = sync_brief_map_flags(cur, a.client, a.go)
    print(f"[activate_map] title_brief has_map updates={bf}")

    if a.go:
        cur.execute(
            """
            SELECT count(*) AS n,
                   count(*) FILTER (WHERE geom_geojson IS NOT NULL) AS with_geom,
                   count(*) FILTER (WHERE status='awaiting_plot') AS awaiting
              FROM map_parcels WHERE client_code=%s
            """,
            (a.client,),
        )
        r = cur.fetchone()
        print(f"[activate_map] map_parcels total={r['n']} geom={r['with_geom']} awaiting_plot={r['awaiting']}")
        cur.execute("SELECT count(*) AS n FROM title_tax_links")
        print(f"[activate_map] title_tax_links total={cur.fetchone()['n']}")
        cur.execute("SELECT count(*) AS n FROM geometry_priority")
        print(f"[activate_map] geometry_priority total={cur.fetchone()['n']}")
        cur.execute(
            "SELECT count(*) AS n FROM parcels WHERE client_code=%s OR matter_code LIKE %s",
            (a.client, a.client.split("-")[0] + "%"),
        )
        print(f"[activate_map] parcels (survey shapes)={cur.fetchone()['n']}")

    if a.go and a.briefs:
        print("[activate_map] materialize_title_brief…")
        subprocess.run(
            [sys.executable, "/root/landtek/scripts/materialize_title_brief.py",
             "--client", a.client, "--go"],
            check=False,
        )

    if a.go and (a.geometry_drip or a.strip_only):
        print("[activate_map] geometry_pipeline…")
        cmd = [sys.executable, "/root/landtek/scripts/geometry_pipeline.py",
               "--matter", a.client, "--max", "8"]
        if a.strip_only:
            cmd.append("--strip-only")
        subprocess.run(cmd, check=False)

    if a.go:
        # mapping agent audit (may be empty geom)
        print("[activate_map] mapping_agent audit…")
        subprocess.run(
            [sys.executable, "/root/landtek/scripts/mapping_agent.py", "audit",
             "--client", a.client],
            check=False,
        )

    print("[activate_map] LIVE surfaces (existing):")
    print("  Ops list:   https://leo.hayuma.org/ops/map  (or /ops/map via leo-tools)")
    print("  Consensus:  /ops/map/consensus")
    print("  GeoJSON:    /ops/map/parcels.geojson?client=" + a.client)
    print("  Draw:       /ops/map/draw?parcel=<parcel_code>")
    cur.close()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
