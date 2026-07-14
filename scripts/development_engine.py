#!/usr/bin/env python3
"""development_engine.py — the Property Development + Revenue precondition brain (deploy_911).

Graduates revenue_engine's read-time _assess() into a DURABLE, EVIDENCED, all-mode ledger
(`asset_preconditions`). One epistemology: the board reads the ledger, not a second guess.

Design of record: docs/PROPERTY_DEVELOPMENT_SPINE.md. Two contracts it enforces in code:

  1. ASSET-OWNED codes (tenure/geometry/possession/...) are an ENGINE-DERIVED CACHE of asset facts.
     The engine is their sole writer; recompute is atomic per asset; they are never hand-set. The
     source of truth stays property_assets.title_status / linked geometry — the rows materialize it.

  2. The engine NEVER self-assigns provenance_level IN ('operator','verified'). Deterministic 'ok'
     writes always carry a derived evidence_ref (satisfying the A82 DB CHECK honestly, as inference,
     not as operator attestation). 'operator' is reserved for operator-authenticated writes; SOURCING
     codes (capital_partner/feasibility/buyer_price/tenant/operator) are INSERTed once as 'unknown'
     and then left alone — the engine respects an operator edit and never clobbers it.

  python3 development_engine.py --recompute [--asset PA-... | --project DEV-...]
      # default: ALL assets with client_code (stubs + curated) × their modes — lights the money board
  python3 development_engine.py --seed-project DEV-PAR-GOLDEN-SAND --asset PA-GOLDEN-SAND --mode develop \
                                --label "Golden Sand Beach Resort" --target-use resort
  python3 development_engine.py --board [--curated | --stubs | --all]
  python3 development_engine.py --catalog          # print the mode precondition catalog
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Mode precondition catalog. kind: 'deterministic' (engine recomputes every run) |
# 'sourcing' (operator-owned; engine INSERTs unknown once, then never updates). owner_kind per §1.3.
# code labels align with revenue_engine.PRECONDS/NEXT_MOVE; survey_geometry is the one new code.
D, S = "deterministic", "sourcing"
CATALOG = {
    "develop": [
        ("secure_tenure",   "marketable title or secure tenure",  "asset",   10, D),
        ("survey_geometry", "closed, placed boundary",            "asset",   20, D),
        ("permits",         "zoning + DENR/LGU permits",          "project", 30, D),
        ("capital_partner", "capital or a JV partner",            "project", 40, S),
        ("feasibility",     "a return/feasibility case",          "project", 50, S),
    ],
    "sale": [
        ("marketable_title", "clean, registrable title",          "asset",   10, D),
        ("seller_authority", "authority to sell (heirs/SPA)",     "asset",   20, D),
        ("buyer_price",      "a buyer + agreed price",            "project", 30, S),
        ("tax_clearance",    "CGT/DST/CAR + RPT clearance",       "asset",   40, D),
        ("registrable",      "RD will register the transfer",     "asset",   50, D),
    ],
    "lease": [
        ("possession",       "actual possession/control",         "asset",   10, D),
        ("usable",           "usable/habitable condition",        "asset",   20, D),
        ("tenant",           "a tenant/lessee",                   "project", 30, S),
        ("lease_instrument", "a lease contract",                  "project", 40, D),
        ("collection",       "a collection mechanism",            "project", 50, D),
    ],
    "mineral": [
        ("mineral_rights",   "mineral rights resolved/owned",     "asset",   10, D),
        ("permit",           "MGB permit / mineral agreement",    "project", 20, D),
        ("operator",         "an operator/lessee",                "project", 30, S),
    ],
}
NEXT_MOVE = {
    "secure_tenure": "secure marketable title or tenure for development",
    "survey_geometry": "plot/upgrade the boundary to survey or ortho grade",
    "permits": "obtain zoning/locational + DENR/LGU permits",
    "capital_partner": "raise capital or sign a JV partner",
    "feasibility": "build the feasibility/return case",
    "marketable_title": "PREP title file (CTC/annotations); quiet-title pack — matter only when schedule requires",
    "seller_authority": "confirm heirs' consent or a valid, unrevoked SPA",
    "buyer_price": "source a buyer + set a price",
    "tax_clearance": "compute + secure CGT/DST/CAR + RPT clearance",
    "registrable": "clear blocking annotations so the RD can register",
    "possession": "establish/confirm actual possession + control",
    "usable": "make the unit usable (repairs/turnover)",
    "tenant": "find a tenant/lessee",
    "lease_instrument": "execute a lease contract",
    "collection": "set up rent collection + records",
    "mineral_rights": "resolve the mineral-rights dispute",
    "permit": "secure the MGB permit / mineral agreement",
    "operator": "engage an operator/lessee",
}
PROCESS_TODO = {"tax_clearance", "registrable", "usable", "lease_instrument", "collection"}


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = False  # recompute per owner is a transaction (atomic cache refresh)
    return c


# ── assessment (mirrors revenue_engine._assess but returns evidence + writes rows) ───────────────
def _worst_tenure(asset, cur):
    """Worst-of linked asset_titles.title_status, else property_assets.title_status."""
    cur.execute("SELECT title_status FROM asset_titles WHERE asset_code=%s AND title_status IS NOT NULL",
                (asset["asset_code"],))
    statuses = [r[0] for r in cur.fetchall()] or []
    if asset.get("title_status"):
        statuses.append(asset["title_status"])
    order = {"clouded": 0, "cancelled": 0, "untitled": 1, "unverified": 2, "clean": 3}
    if not statuses:
        return None, None
    worst = min(statuses, key=lambda s: order.get((s or "").lower(), 2))
    basis = "asset_titles worst-of" if len(statuses) > 1 else "property_assets.title_status"
    return worst, basis


def assess_asset(asset, code, cur):
    """Return dict(status, reason, evidence_kind, evidence_ref, provenance, recheck) for an asset-owned code.
    NEVER returns provenance 'operator'/'verified' — engine derives from asset facts as inference."""
    ctrl = asset.get("controlling_matter")
    if code in ("secure_tenure", "marketable_title"):
        ts, basis = _worst_tenure(asset, cur)
        if ts is None:
            return dict(status="unknown", reason="no title status on record", evidence_kind=None,
                        evidence_ref=None, provenance="inferred_weak", recheck="title status recorded")
        tsl = ts.lower()
        if tsl in ("clouded", "cancelled"):
            # Matter is optional context — never the only story. Prep continues either way.
            ctx = f" (context matter {ctrl})" if ctrl else ""
            return dict(status="blocked", reason=f"title {tsl} — prep CTC/annotations/quiet-title pack{ctx}",
                        evidence_kind="title_status", evidence_ref=f"{basis}={ts}",
                        provenance="inferred_strong",
                        recheck="title status improves OR prep pack complete enough for next legal step")
        if tsl == "untitled":
            return dict(status="todo", reason="needs titling", evidence_kind="title_status",
                        evidence_ref=f"{basis}=untitled", provenance="inferred_strong",
                        recheck="title issued")
        if tsl == "clean":
            return dict(status="ok", reason="title clean", evidence_kind="title_status",
                        evidence_ref=f"{basis}=clean", provenance="inferred_strong",
                        recheck="title status changes")
        return dict(status="unknown", reason=f"title {tsl} — verify", evidence_kind="title_status",
                    evidence_ref=f"{basis}={ts}", provenance="inferred_weak", recheck="title verified")
    if code == "survey_geometry":
        cur.execute("""SELECT bool_or(mp.geom_geojson IS NOT NULL AND mp.accuracy_tier IN ('survey','ortho')) AS survey_grade,
                              bool_or(mp.geom_geojson IS NOT NULL) AS any_geom,
                              count(*) AS links, string_agg(mp.parcel_code, ',') AS parcels
                       FROM asset_map_parcels amp JOIN map_parcels mp ON mp.parcel_code=amp.parcel_code
                       WHERE amp.asset_code=%s""", (asset["asset_code"],))
        g = cur.fetchone()
        if not g or g["links"] == 0:
            return dict(status="unknown", reason="no map parcel linked", evidence_kind=None,
                        evidence_ref=None, provenance="inferred_weak", recheck="a map_parcel linked")
        if g["survey_grade"]:
            return dict(status="ok", reason="placed survey-grade (or better) boundary",
                        evidence_kind="geometry", evidence_ref=f"map_parcels[{g['parcels']}] survey/ortho",
                        provenance="inferred_strong", recheck="geometry accuracy_tier changes")
        if g["any_geom"]:
            return dict(status="todo", reason="only rough plot — upgrade to survey/ortho",
                        evidence_kind="geometry", evidence_ref=f"map_parcels[{g['parcels']}] rough",
                        provenance="inferred_strong", recheck="geometry upgraded to survey/ortho")
        return dict(status="todo", reason="linked but not plotted — plot boundary", evidence_kind="geometry",
                    evidence_ref=f"map_parcels[{g['parcels']}] unplotted", provenance="inferred_weak",
                    recheck="boundary plotted")
    if code == "possession":
        pos = (asset.get("possession") or "").lower()
        if pos == "yes":
            return dict(status="ok", reason="in possession", evidence_kind=None,
                        evidence_ref="property_assets.possession=yes", provenance="inferred_strong",
                        recheck="possession changes")
        if pos == "contested":
            return dict(status="blocked", reason="possession contested", evidence_kind="matter",
                        evidence_ref=f"gated on {ctrl or 'dispute'}", provenance="inferred_strong",
                        recheck="possession dispute resolves")
        return dict(status="unknown", reason="possession unknown", evidence_kind=None, evidence_ref=None,
                    provenance="inferred_weak", recheck="possession confirmed")
    if code == "seller_authority":
        if asset.get("has_authority"):
            return dict(status="ok", reason="SPA/authority in place", evidence_kind=None,
                        evidence_ref="property_assets.has_authority=true", provenance="inferred_strong",
                        recheck="authority revoked/expires")
        return dict(status="unknown", reason="confirm authority", evidence_kind=None, evidence_ref=None,
                    provenance="inferred_weak", recheck="authority confirmed")
    if code == "mineral_rights":
        if ctrl:
            return dict(status="blocked", reason=f"mineral-rights dispute open ({ctrl})", evidence_kind="matter",
                        evidence_ref=ctrl, provenance="inferred_strong", recheck=f"{ctrl} resolves")
        return dict(status="ok", reason="rights clear", evidence_kind=None, evidence_ref="no controlling_matter",
                    provenance="inferred_weak", recheck="a mineral dispute is filed")
    if code in PROCESS_TODO:
        return dict(status="todo", reason="process step", evidence_kind=None, evidence_ref=None,
                    provenance="inferred_weak", recheck="the process step is completed")
    return dict(status="unknown", reason="?", evidence_kind=None, evidence_ref=None,
                provenance="inferred_weak", recheck=None)


def assess_project_permits(project_code, cur):
    """Aggregate development_permits for a project's permit-bundle precondition."""
    cur.execute("SELECT status FROM development_permits WHERE project_code=%s", (project_code,))
    sts = [r[0] for r in cur.fetchall()]
    if not sts:
        return dict(status="unknown", reason="no permits defined", evidence_kind=None, evidence_ref=None,
                    provenance="inferred_weak", recheck="a permit row is added")
    done = {"granted", "not_required", "waived"}
    if any(s == "denied" for s in sts):
        return dict(status="blocked", reason="a required permit was denied", evidence_kind="permit",
                    evidence_ref=f"{len(sts)} permits; >=1 denied", provenance="inferred_strong",
                    recheck="the denied permit is refiled/appealed")
    if all(s in done for s in sts):
        return dict(status="ok", reason="all permits granted/waived/not-required", evidence_kind="permit",
                    evidence_ref=f"{len(sts)} permits all cleared", provenance="inferred_strong",
                    recheck="a permit lapses or a new one is required")
    return dict(status="todo", reason="permits in flight", evidence_kind="permit",
                evidence_ref=f"{len(sts)} permits, some pending", provenance="inferred_strong",
                recheck="pending permits decided")


def _guard_provenance(prov):
    assert prov not in ("operator", "verified"), \
        f"engine must never self-assign provenance '{prov}' (design refinement 1)"
    return prov


def _upsert(cur, client_code, owner_kind, owner_code, mode, code, label, sort_order, kind, r):
    """Deterministic codes: upsert (recompute). Sourcing codes: insert-if-absent, never clobber operator."""
    _guard_provenance(r["provenance"])
    if kind == S:
        cur.execute("""INSERT INTO asset_preconditions
            (client_code,owner_kind,owner_code,mode,code,label,sort_order,status,reason,next_move,provenance_level,recheck_condition)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'unknown',%s,%s,'inferred_weak',%s)
            ON CONFLICT (owner_kind,owner_code,mode,code) DO NOTHING""",
            (client_code, owner_kind, owner_code, mode, code, label, sort_order,
             "operator-sourced — needs your input", NEXT_MOVE.get(code), "operator sets this"))
        return
    nm = NEXT_MOVE.get(code) if r["status"] != "ok" else None
    cur.execute("""INSERT INTO asset_preconditions
        (client_code,owner_kind,owner_code,mode,code,label,sort_order,status,reason,next_move,
         evidence_kind,evidence_ref,provenance_level,recheck_condition,last_assessed_at,updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
        ON CONFLICT (owner_kind,owner_code,mode,code) DO UPDATE SET
          status=EXCLUDED.status, reason=EXCLUDED.reason, next_move=EXCLUDED.next_move,
          evidence_kind=EXCLUDED.evidence_kind, evidence_ref=EXCLUDED.evidence_ref,
          provenance_level=EXCLUDED.provenance_level, recheck_condition=EXCLUDED.recheck_condition,
          label=EXCLUDED.label, sort_order=EXCLUDED.sort_order, last_assessed_at=now(), updated_at=now()""",
        (client_code, owner_kind, owner_code, mode, code, label, sort_order, r["status"], r["reason"], nm,
         r["evidence_kind"], r["evidence_ref"], r["provenance"], r["recheck"]))


def recompute_asset(cur, asset, mode):
    """Refresh the asset-owned precondition rows for one (asset, mode). Atomic per asset."""
    for code, label, owner_kind, sort_order, kind in CATALOG[mode]:
        if owner_kind != "asset":
            continue
        r = assess_asset(asset, code, cur)
        _upsert(cur, asset["client_code"], "asset", asset["asset_code"], mode, code, label, sort_order, kind, r)


def recompute_project(cur, proj):
    """Refresh project-owned rows + roll up gating/readiness across asset∪project rows for the mode."""
    mode = proj["mode"]
    for code, label, owner_kind, sort_order, kind in CATALOG[mode]:
        if owner_kind != "project":
            continue
        if code == "permits":
            r = assess_project_permits(proj["project_code"], cur)
        elif code == "permit":  # mineral permit bundle (reuse permit aggregation)
            r = assess_project_permits(proj["project_code"], cur)
        elif kind == D:
            r = dict(status="todo", reason="process step", evidence_kind=None, evidence_ref=None,
                     provenance="inferred_weak", recheck="the process step is completed")
        else:
            r = None  # sourcing handled by insert-if-absent
        if kind == S:
            _upsert(cur, proj["client_code"], "project", proj["project_code"], mode, code, label, sort_order, kind,
                    dict(provenance="inferred_weak"))
        else:
            _upsert(cur, proj["client_code"], "project", proj["project_code"], mode, code, label, sort_order, kind, r)

    # roll up across asset-owned (parent asset, this mode) ∪ project-owned rows
    cur.execute("""SELECT code, status, sort_order, owner_kind FROM asset_preconditions
        WHERE mode=%s AND ((owner_kind='asset' AND owner_code=%s) OR (owner_kind='project' AND owner_code=%s))
        ORDER BY sort_order, owner_kind""", (mode, proj["asset_code"], proj["project_code"]))
    chain = cur.fetchall()
    total = len(chain)
    ok = sum(1 for c in chain if c["status"] == "ok")
    gating = next((c["code"] for c in chain if c["status"] != "ok"), None)
    ratio = round(ok / total, 4) if total else None
    suggested = "ready" if (total and ok == total) else None
    cur.execute("""UPDATE development_projects SET gating_precondition=%s, readiness_ratio=%s, updated_at=now()
                   WHERE project_code=%s""", (gating, ratio, proj["project_code"]))
    return dict(ok=ok, total=total, gating=gating, ratio=ratio, suggested_stage=suggested, current_stage=proj["stage"])


# ── commands ─────────────────────────────────────────────────────────────────────────────────────
def recompute(asset_code=None, project_code=None, curated_only=False):
    """Refresh ledger. Default: ALL assets with client_code (title stubs + curated) so revenue_engine
    has one evidenced board for the full portfolio. Project-owned codes still require a project row
    (V12); stubs get asset-owned codes only until a deal/project is opened."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # 1. asset-owned rows for every in-scope asset × each of its modes
    if project_code:
        cur.execute("SELECT * FROM development_projects WHERE project_code=%s", (project_code,))
        projs = cur.fetchall()
        asset_codes = list({p["asset_code"] for p in projs})
        cur.execute("SELECT * FROM property_assets WHERE asset_code = ANY(%s)", (asset_codes,))
        assets = cur.fetchall()
    else:
        q = "SELECT * FROM property_assets WHERE client_code IS NOT NULL"
        params = []
        if curated_only:
            q += " AND origin IN ('seed','operator')"
        if asset_code:
            q += " AND asset_code=%s"; params.append(asset_code)
        cur.execute(q, params)
        assets = cur.fetchall()
    n_asset = 0
    skipped = 0
    for a in assets:
        if a.get("client_code") is None:
            print(f"[dev] SKIP {a['asset_code']}: no client_code (isolation dark) — backfill first")
            skipped += 1
            continue
        for mode in (a.get("modes") or []):
            if mode in CATALOG:
                recompute_asset(cur, a, mode); n_asset += 1
    c.commit()
    # 2. project rollups (project-owned codes + gating)
    if project_code:
        projs_iter = projs
    else:
        cur.execute("SELECT * FROM development_projects WHERE status='active'"
                    + (" AND asset_code=%s" if asset_code else ""),
                    (asset_code,) if asset_code else ())
        projs_iter = cur.fetchall()
    for p in projs_iter:
        roll = recompute_project(cur, p)
        c.commit()
        sug = f"  ⇒ SUGGEST stage 'ready' (all {roll['total']} ok)" if roll["suggested_stage"] else ""
        print(f"[dev] {p['project_code']}: {roll['ok']}/{roll['total']} ok "
              f"(ratio {roll['ratio']}), gating={roll['gating']}, stage={roll['current_stage']}{sug}")
    print(f"[dev] recomputed asset-mode rows={n_asset}, projects={len(projs_iter)}, "
          f"assets_seen={len(assets)}, skipped_no_client={skipped}")
    cur.close(); c.close()


def seed_project(project_code, asset_code, mode="develop", label=None, target_use=None,
                 objective=None, is_primary=True):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT asset_code, origin, client_code, label FROM property_assets WHERE asset_code=%s", (asset_code,))
    a = cur.fetchone()
    if not a:
        print(f"[dev] ERROR: asset {asset_code} not found"); c.close(); return
    if a["origin"] not in ("seed", "operator"):
        print(f"[dev] REFUSED: {asset_code} origin='{a['origin']}' is a title stub — projects attach to "
              f"curated assets only (design §1.1)."); c.close(); return
    if a["client_code"] is None:
        print(f"[dev] REFUSED: {asset_code} has no client_code."); c.close(); return
    cur.execute("""INSERT INTO development_projects (project_code, client_code, label, asset_code, mode,
                     stage, is_primary, target_use, objective, provenance_level)
                   VALUES (%s,%s,%s,%s,%s,'assessing',%s,%s,%s,'operator')
                   ON CONFLICT (project_code) DO UPDATE SET label=EXCLUDED.label, mode=EXCLUDED.mode,
                     target_use=EXCLUDED.target_use, objective=EXCLUDED.objective, updated_at=now()""",
                (project_code, a["client_code"], label or a["label"], asset_code, mode,
                 is_primary, target_use, objective))
    c.commit()
    print(f"[dev] seeded project {project_code} on {asset_code} (client {a['client_code']}, mode {mode})")
    cur.close(); c.close()
    recompute(project_code=project_code)


def board(scope="curated"):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if scope in ("curated", "all"):
        cur.execute("SELECT * FROM v_development_board ORDER BY readiness_ratio DESC NULLS LAST, project_code")
        rows = cur.fetchall()
        print("\n" + "=" * 84 + f"\nDEVELOPMENT BOARD — {len(rows)} active project(s)\n" + "=" * 84)
        for r in rows:
            ok = (r["project_pre_ok"] or 0) + (r["asset_pre_ok"] or 0)
            tot = (r["project_pre_total"] or 0) + (r["asset_pre_total"] or 0)
            geo = "survey+" if r["has_survey_grade_geom"] else "no-survey-geom"
            date = f" · next {r['next_milestone_date']}" if r["next_milestone_date"] else ""
            print(f"  {r['project_code']:<24}{r['mode']:<8}{r['stage']:<12} {ok}/{tot} ok "
                  f"(ratio {r['readiness_ratio']}) gating={r['gating_precondition']} [{geo}]{date}")
    if scope in ("stubs", "all"):
        cur.execute("""SELECT * FROM v_asset_inventory WHERE origin='title'
                       ORDER BY (tenure_status='ok') DESC NULLS LAST, asset_code LIMIT 20""")
        rows = cur.fetchall()
        print("\n" + "-" * 84 + f"\nTITLE-STUB INVENTORY (fast-cash candidates) — showing {len(rows)}\n" + "-" * 84)
        for r in rows:
            comp = f" component_of={r['component_of_curated']}" if r["component_of_curated"] else ""
            print(f"  {r['asset_code']:<22}{(r['client_code'] or '-'):<14}tenure={r['tenure_status'] or '?'}{comp}")
    cur.close(); c.close()


def print_catalog():
    for mode, codes in CATALOG.items():
        print(f"\n{mode}:")
        for code, label, ok, so, kind in codes:
            print(f"  {so:>3} [{ok:<7} {kind:<13}] {code:<18} {label}")


if __name__ == "__main__":
    a = sys.argv
    def val(flag, default=None):
        return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default
    if "--catalog" in a:
        print_catalog()
    elif "--seed-project" in a:
        seed_project(val("--seed-project"), val("--asset"), mode=val("--mode", "develop"),
                     label=val("--label"), target_use=val("--target-use"), objective=val("--objective"))
    elif "--recompute" in a:
        recompute(asset_code=val("--asset"), project_code=val("--project"),
                  curated_only=("--curated-only" in a))
    elif "--board" in a:
        board(scope=("all" if "--all" in a else "stubs" if "--stubs" in a else "curated"))
    else:
        print(__doc__)
