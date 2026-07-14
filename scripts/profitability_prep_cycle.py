#!/usr/bin/env python3
"""profitability_prep_cycle.py — CONTINUOUS preparation of every property for profitability.

Doctrine:
  Preparing a property means securing understanding on SIX axes (always, unprompted):

    1. documents    — secure the papers (CTC, deeds, SPA, tax, court, CLOA…)
    2. status       — understand operative property status
    3. occupants    — who occupies / possesses
    4. ownership    — owners, claimants, authority to act
    5. title_issues — defects, clouds, cancellations, CARP, contest
    6. mapping      — boundary geometry, plot, area

  Matter is OPTIONAL context when the schedule calls for it — never required to prep.
  Cycle runs on a timer whether or not anyone prompts.

Each cycle:
  1. RECOMPUTE asset_preconditions ledger (development_engine)
  2. SCORE each property on the six axes → property_readiness
  3. UPSERT axis-keyed prep moves → profitability_prep_moves
  4. CLOSE moves that are resolved
  5. LOG the cycle

  python3 profitability_prep_cycle.py
  python3 profitability_prep_cycle.py --report
  python3 profitability_prep_cycle.py --no-recompute
  python3 profitability_prep_cycle.py --asset PA-GOLDEN-SAND
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from development_engine import recompute as de_recompute  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

AXES = ("documents", "status", "occupants", "ownership", "title_issues", "mapping")
SCORE = {"solid": 1.0, "partial": 0.55, "thin": 0.25, "unknown": 0.0}
TIER_BOOST = {"earn_now": 0, "develop": 10, "recover_then": 20}


def _conn(autocommit=True):
    c = psycopg2.connect(DSN)
    c.autocommit = autocommit
    return c


def _ensure(cur):
    """Minimal ensure if migrations 914/915 not applied."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profitability_prep_moves (
          id bigserial PRIMARY KEY,
          client_code text,
          asset_code text NOT NULL,
          matter_code text,
          mode text,
          precond_code text,
          action text NOT NULL,
          why text,
          recheck_condition text,
          evidence_ref text,
          priority int NOT NULL DEFAULT 100,
          status text NOT NULL DEFAULT 'open',
          origin text NOT NULL DEFAULT 'prep_cycle',
          move_key text NOT NULL UNIQUE,
          axis text,
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          closed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )""")
    cur.execute("ALTER TABLE profitability_prep_moves ADD COLUMN IF NOT EXISTS axis text")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profitability_prep_cycles (
          id bigserial PRIMARY KEY,
          started_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz,
          assets_seen int,
          moves_open int,
          moves_upserted int,
          moves_closed int,
          note text
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS property_readiness (
          asset_code text PRIMARY KEY,
          client_code text,
          documents text NOT NULL DEFAULT 'unknown',
          status_axis text NOT NULL DEFAULT 'unknown',
          occupants text NOT NULL DEFAULT 'unknown',
          ownership text NOT NULL DEFAULT 'unknown',
          title_issues text NOT NULL DEFAULT 'unknown',
          mapping text NOT NULL DEFAULT 'unknown',
          documents_note text,
          status_note text,
          occupants_note text,
          ownership_note text,
          title_issues_note text,
          mapping_note text,
          readiness_score numeric(5,4),
          weakest_axis text,
          next_prep_action text,
          assessed_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )""")


# ── axis assessment (signals from live tables; honest unknowns) ─────────────────────────────────

def _docs_for_title(cur, title_ref, case_file):
    """Count documents that look related to this title / case_file."""
    if not title_ref and not case_file:
        return 0, 0
    # related docs: filename/title/text mention of title_no, or same case_file
    cur.execute("""
        SELECT count(*) AS n,
               count(*) FILTER (WHERE coalesce(extracted_text,'') <> '') AS with_text
          FROM documents d
         WHERE (%s::text IS NOT NULL AND (
                 coalesce(d.original_filename,'') ILIKE '%%' || %s || '%%'
              OR coalesce(d.document_title,'') ILIKE '%%' || %s || '%%'
              OR coalesce(d.canonical_filename,'') ILIKE '%%' || %s || '%%'
              OR coalesce(d.extracted_text,'') ILIKE '%%' || %s || '%%'
               ))
            OR (%s::text IS NOT NULL AND d.case_file = %s)
        """, (title_ref, title_ref, title_ref, title_ref, title_ref, case_file, case_file))
    r = cur.fetchone()
    return int(r["n"] or 0), int(r["with_text"] or 0)


def assess_axes(cur, asset):
    """Return {axis: (grade, note, prep_action|None)} for the six axes."""
    ac = asset["asset_code"]
    title_ref = asset.get("title_ref")
    case_file = asset.get("case_file")
    ts = (asset.get("title_status") or "").lower()
    pos = (asset.get("possession") or "").lower()
    has_auth = bool(asset.get("has_authority"))
    out = {}

    # ── 1. DOCUMENTS ──
    n_docs, n_text = _docs_for_title(cur, title_ref, case_file)
    # also count title row presence as a doc signal
    has_title_row = False
    if title_ref:
        cur.execute("SELECT 1 FROM titles WHERE tct_number=%s LIMIT 1", (title_ref,))
        has_title_row = bool(cur.fetchone())
    if n_text >= 3 or (n_docs >= 2 and n_text >= 1):
        out["documents"] = ("partial" if n_text < 5 else "solid",
                            f"{n_docs} related docs, {n_text} with text"
                            + ("; titles row present" if has_title_row else ""),
                            None if n_text >= 5 else
                            "PREP documents: secure CTC/owner's duplicate + remaining instruments (deeds/SPA/tax)")
    elif n_docs >= 1 or has_title_row:
        out["documents"] = ("thin",
                            f"{n_docs} related docs ({n_text} with text); need secure pack",
                            "PREP documents: pull CTC from RD; secure deeds, SPA, tax decs, court papers for this title")
    else:
        out["documents"] = ("unknown",
                            "no related documents found in corpus for this title/case_file",
                            "PREP documents: identify and secure source docs (RD CTC, Drive, email attachments)")

    # ── 2. STATUS ──
    if ts in ("clean", "active"):
        out["status"] = ("solid" if ts == "clean" else "partial",
                         f"title_status={ts or 'unset'}",
                         None if ts == "clean" else
                         "PREP status: confirm active vs cancelled at RD (status not clean)")
    elif ts in ("clouded", "cancelled", "unverified", "untitled"):
        out["status"] = ("thin" if ts == "unverified" else "partial",
                         f"title_status={ts} — status understood as problem state; keep monitoring",
                         f"PREP status: reconfirm {ts} at RD + note any new annotations this cycle")
    else:
        out["status"] = ("unknown",
                         "title_status missing — property status not understood",
                         "PREP status: establish operative title status (clean/clouded/cancelled) from RD")

    # ── 3. OCCUPANTS ──
    if pos == "yes":
        out["occupants"] = ("partial",
                            "possession=yes on asset — occupant identity may still be thin",
                            "PREP occupants: name who occupies, since when, contact, any lease/tax evidence")
    elif pos == "contested":
        out["occupants"] = ("thin",
                            "possession contested — occupant map is load-bearing",
                            "PREP occupants: map who is on the land, adverse claim history, photos/affidavits")
    elif pos in ("no", "vacant"):
        out["occupants"] = ("partial",
                            f"possession={pos}",
                            "PREP occupants: confirm vacant/no occupant with site check or neighbor statement")
    else:
        out["occupants"] = ("unknown",
                            "possession unknown — occupants not understood",
                            "PREP occupants: determine who occupies (if anyone) and on what basis")

    # ── 4. OWNERSHIP ──
    owner_bits = []
    if title_ref:
        cur.execute("""SELECT registrant_canonical FROM titles WHERE tct_number=%s LIMIT 1""", (title_ref,))
        tr = cur.fetchone()
        if tr and tr.get("registrant_canonical"):
            owner_bits.append(f"registrant={tr['registrant_canonical'][:80]}")
    if has_auth:
        owner_bits.append("has_authority=true on asset")
    cur.execute("""SELECT count(*) AS n FROM asset_titles WHERE asset_code=%s""", (ac,))
    n_links = cur.fetchone()["n"]
    if n_links:
        owner_bits.append(f"{n_links} title links")

    if owner_bits and has_auth and ts == "clean":
        out["ownership"] = ("partial",
                            "; ".join(owner_bits),
                            "PREP ownership: verify heirs/SPA still valid; list all claimants")
    elif owner_bits:
        out["ownership"] = ("thin",
                            "; ".join(owner_bits) or "partial signals",
                            "PREP ownership: complete owner/claimant map + authority (SPA/heirs) docs")
    else:
        out["ownership"] = ("unknown",
                            "no registrant/authority signals on file",
                            "PREP ownership: identify registered owner + claimants + who may act")

    # ── 5. TITLE ISSUES ──
    issues = []
    if ts in ("clouded", "cancelled"):
        issues.append(ts)
    if pos == "contested":
        issues.append("possession_contested")
    ctrl = asset.get("controlling_matter")
    if ctrl:
        issues.append(f"context:{ctrl}")
    # CARP / CLOA hint in title number
    tr_u = (title_ref or "").upper()
    if "CLOA" in tr_u or "EP-" in tr_u:
        issues.append("agrarian/CLOA form")

    if not issues and ts == "clean":
        out["title_issues"] = ("solid",
                               "no cloud/cancel/contest signals on asset row",
                               None)
    elif issues:
        grade = "partial" if ts in ("clouded", "cancelled") else "thin"
        out["title_issues"] = (grade,
                               "issues: " + ", ".join(issues),
                               "PREP title issues: list defects/annotations; assemble recovery or curative pack")
    else:
        out["title_issues"] = ("unknown",
                               "title issues not yet assessed",
                               "PREP title issues: scan RD annotations + corpus for defects/encumbrances")

    # ── 6. MAPPING ──
    cur.execute("""
        SELECT count(*) AS links,
               count(*) FILTER (WHERE mp.geom_geojson IS NOT NULL) AS plotted,
               count(*) FILTER (WHERE mp.accuracy_tier IN ('survey','ortho')) AS survey_grade
          FROM asset_map_parcels amp
          LEFT JOIN map_parcels mp ON mp.parcel_code = amp.parcel_code
         WHERE amp.asset_code=%s""", (ac,))
    g = cur.fetchone()
    cur.execute("""SELECT count(*) AS n FROM asset_survey_parcels WHERE asset_code=%s""", (ac,))
    survey_n = cur.fetchone()["n"]

    if g["survey_grade"] and g["survey_grade"] > 0:
        out["mapping"] = ("solid",
                          f"{g['links']} map links, {g['survey_grade']} survey/ortho",
                          None)
    elif g["plotted"] and g["plotted"] > 0:
        out["mapping"] = ("partial",
                          f"{g['links']} links, plotted but not survey-grade",
                          "PREP mapping: upgrade plot to survey/ortho; confirm area vs title")
    elif g["links"] and g["links"] > 0:
        out["mapping"] = ("thin",
                          f"{g['links']} map links but unplotted",
                          "PREP mapping: plot the linked parcel on satellite / survey")
    elif survey_n:
        out["mapping"] = ("thin",
                          f"{survey_n} survey shapes (relative) — not georeferenced",
                          "PREP mapping: georeference survey shape → map_parcels")
    else:
        out["mapping"] = ("unknown",
                          "no map or survey geometry linked",
                          "PREP mapping: attach boundary (map_parcel or survey courses) for this property")

    return out


def _priority(tier, grade, axis):
    # weaker axis = higher priority (lower number)
    weak = {"unknown": 0, "thin": 10, "partial": 25, "solid": 90}
    axis_w = {"documents": 0, "title_issues": 2, "ownership": 4, "occupants": 6,
              "status": 8, "mapping": 10, "deal": 40}
    return TIER_BOOST.get(tier or "", 30) + weak.get(grade, 15) + axis_w.get(axis, 20)


def _move_key(asset_code, axis, action):
    return f"{asset_code}|{axis}|{action[:180]}"


def upsert_move(cur, m):
    cur.execute("""
        INSERT INTO profitability_prep_moves
          (client_code, asset_code, matter_code, mode, precond_code, action, why,
           recheck_condition, evidence_ref, priority, status, origin, move_key, axis,
           last_seen_at, updated_at)
        VALUES (%(client_code)s,%(asset_code)s,%(matter_code)s,%(mode)s,%(precond_code)s,%(action)s,%(why)s,
                %(recheck_condition)s,%(evidence_ref)s,%(priority)s,'open','prep_cycle',%(move_key)s,%(axis)s,
                now(),now())
        ON CONFLICT (move_key) DO UPDATE SET
          client_code=EXCLUDED.client_code,
          matter_code=EXCLUDED.matter_code,
          why=EXCLUDED.why,
          recheck_condition=EXCLUDED.recheck_condition,
          evidence_ref=EXCLUDED.evidence_ref,
          priority=EXCLUDED.priority,
          axis=EXCLUDED.axis,
          status='open',
          closed_at=NULL,
          last_seen_at=now(),
          updated_at=now()
        """, m)


def upsert_readiness(cur, asset, axes, next_action):
    grades = {ax: axes[ax][0] for ax in AXES}
    notes = {ax: axes[ax][1] for ax in AXES}
    score = sum(SCORE[grades[ax]] for ax in AXES) / len(AXES)
    weakest = min(AXES, key=lambda ax: (SCORE[grades[ax]], ax))
    cur.execute("""
        INSERT INTO property_readiness
          (asset_code, client_code,
           documents, status_axis, occupants, ownership, title_issues, mapping,
           documents_note, status_note, occupants_note, ownership_note, title_issues_note, mapping_note,
           readiness_score, weakest_axis, next_prep_action, assessed_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
        ON CONFLICT (asset_code) DO UPDATE SET
          client_code=EXCLUDED.client_code,
          documents=EXCLUDED.documents, status_axis=EXCLUDED.status_axis,
          occupants=EXCLUDED.occupants, ownership=EXCLUDED.ownership,
          title_issues=EXCLUDED.title_issues, mapping=EXCLUDED.mapping,
          documents_note=EXCLUDED.documents_note, status_note=EXCLUDED.status_note,
          occupants_note=EXCLUDED.occupants_note, ownership_note=EXCLUDED.ownership_note,
          title_issues_note=EXCLUDED.title_issues_note, mapping_note=EXCLUDED.mapping_note,
          readiness_score=EXCLUDED.readiness_score, weakest_axis=EXCLUDED.weakest_axis,
          next_prep_action=EXCLUDED.next_prep_action, assessed_at=now(), updated_at=now()
        """, (
        asset["asset_code"], asset.get("client_code"),
        grades["documents"], grades["status"], grades["occupants"],
        grades["ownership"], grades["title_issues"], grades["mapping"],
        notes["documents"], notes["status"], notes["occupants"],
        notes["ownership"], notes["title_issues"], notes["mapping"],
        round(score, 4), weakest, next_action,
    ))


def process_asset(cur, asset):
    """Assess axes, write readiness + prep moves. Returns (moves_list, next_action)."""
    axes = assess_axes(cur, asset)
    moves = []
    for axis in AXES:
        grade, note, action = axes[axis]
        if not action:
            continue
        m = dict(
            client_code=asset.get("client_code"),
            asset_code=asset["asset_code"],
            matter_code=asset.get("controlling_matter"),  # optional context only
            mode=None,
            precond_code=axis,
            action=action,
            why=f"{axis}={grade}: {note}",
            recheck_condition=f"{axis} reaches solid or prep pack complete",
            evidence_ref=note[:200] if note else None,
            priority=_priority(asset.get("tier"), grade, axis),
            axis=axis,
        )
        m["move_key"] = _move_key(asset["asset_code"], axis, action)
        moves.append(m)
    # next action = lowest priority number among moves
    next_action = None
    if moves:
        moves_sorted = sorted(moves, key=lambda x: x["priority"])
        next_action = moves_sorted[0]["action"]
    upsert_readiness(cur, asset, axes, next_action)
    for m in moves:
        upsert_move(cur, m)
    return moves, next_action


def close_resolved(cur, seen_keys):
    cur.execute("SELECT id, move_key, asset_code, axis FROM profitability_prep_moves WHERE status='open'")
    closed = 0
    for row in cur.fetchall():
        if row["move_key"] in seen_keys:
            continue
        # if readiness axis is solid, close
        axis = row["axis"]
        if axis and axis in AXES:
            col = "status_axis" if axis == "status" else axis
            cur.execute(f"SELECT {col} AS g FROM property_readiness WHERE asset_code=%s",
                        (row["asset_code"],))
            r = cur.fetchone()
            if r and r["g"] == "solid":
                cur.execute("""UPDATE profitability_prep_moves SET status='done', closed_at=now(),
                               updated_at=now() WHERE id=%s""", (row["id"],))
                closed += 1
                continue
        # not seen and not solid — supersede stale axis moves from older action text
        if row["axis"]:
            cur.execute("""UPDATE profitability_prep_moves SET status='superseded', closed_at=now(),
                           updated_at=now() WHERE id=%s""", (row["id"],))
            closed += 1
    return closed


def run_cycle(do_recompute=True, report_limit=20, only_asset=None):
    started = datetime.now(timezone.utc)
    if do_recompute and not only_asset:
        print("[prep] recompute ledger …")
        de_recompute()
    elif do_recompute and only_asset:
        de_recompute(asset_code=only_asset)

    c = _conn(autocommit=False)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    cur.execute("INSERT INTO profitability_prep_cycles (started_at) VALUES (%s) RETURNING id", (started,))
    cycle_id = cur.fetchone()["id"]

    if only_asset:
        cur.execute("SELECT * FROM property_assets WHERE asset_code=%s AND client_code IS NOT NULL",
                    (only_asset,))
    else:
        cur.execute("SELECT * FROM property_assets WHERE client_code IS NOT NULL ORDER BY asset_code")
    assets = cur.fetchall()

    seen = set()
    upserted = 0
    for a in assets:
        moves, _ = process_asset(cur, a)
        for m in moves:
            seen.add(m["move_key"])
            upserted += 1

    closed = close_resolved(cur, seen) if not only_asset else 0
    cur.execute("SELECT count(*) AS n FROM profitability_prep_moves WHERE status='open'")
    open_n = cur.fetchone()["n"]
    note = (f"6-axis property prep — assets={len(assets)} moves_upserted={upserted} "
            f"closed={closed} open={open_n}")
    cur.execute("""UPDATE profitability_prep_cycles SET finished_at=now(), assets_seen=%s,
                   moves_open=%s, moves_upserted=%s, moves_closed=%s, note=%s WHERE id=%s""",
                (len(assets), open_n, upserted, closed, note, cycle_id))
    c.commit()
    print(f"[prep] cycle #{cycle_id}: {note}")
    report(cur, limit=report_limit, asset=only_asset)
    cur.close(); c.close()


def report(cur=None, limit=20, asset=None):
    own = cur is None
    if own:
        c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        _ensure(cur)

    print("\n" + "=" * 90)
    print("PROPERTY READINESS — six axes (documents · status · occupants · ownership · title · map)")
    print("=" * 90)
    if asset:
        cur.execute("""SELECT * FROM property_readiness WHERE asset_code=%s""", (asset,))
        rows = cur.fetchall()
    else:
        cur.execute("""SELECT * FROM property_readiness ORDER BY readiness_score ASC NULLS FIRST
                       LIMIT %s""", (limit,))
        rows = cur.fetchall()
    if not rows:
        print("  (no readiness rows yet — run a full cycle)")
    for r in rows:
        print(f"\n  {r['asset_code']}  score={r['readiness_score']}  weakest={r['weakest_axis']}")
        print(f"    docs={r['documents']:<8} status={r['status_axis']:<8} occ={r['occupants']:<8} "
              f"own={r['ownership']:<8} title={r['title_issues']:<8} map={r['mapping']:<8}")
        if r.get("next_prep_action"):
            print(f"    → {r['next_prep_action']}")

    print("\n" + "-" * 90)
    print("TOP PREP MOVES (by axis priority)")
    print("-" * 90)
    q = """SELECT priority, axis, client_code, asset_code, action, why
             FROM profitability_prep_moves WHERE status='open'"""
    params = []
    if asset:
        q += " AND asset_code=%s"
        params.append(asset)
    q += " ORDER BY priority ASC, last_seen_at DESC LIMIT %s"
    params.append(limit)
    cur.execute(q, params)
    for r in cur.fetchall():
        print(f"  p{r['priority']:<3} [{(r['axis'] or '-'):<12}] {r['asset_code']:<18} {r['action'][:70]}")

    if own:
        cur.close(); c.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    def val(flag):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None
    if "--report" in args:
        report(limit=int(val("--limit") or 20), asset=val("--asset"))
    else:
        run_cycle(do_recompute=("--no-recompute" not in args),
                  report_limit=int(val("--limit") or 15),
                  only_asset=val("--asset"))
