#!/usr/bin/env python3
"""revenue_engine.py — the monetization brain (second north-star: make money from the portfolio).

deploy_913: CONVERGED onto the asset_preconditions ledger (deploy_911 spine).

  * ONE epistemology: board / --asset / plan_for READ the ledger only.
  * Writing/recompute is development_engine (sole writer of asset-owned cache rows).
  * --sync  →  development_engine.recompute() for the full portfolio, then board.

Still owns inventory mutations: --seed, --enroll-titles (property_assets rows). After enroll,
call --sync so the ledger reflects new stubs.

Design: docs/PROPERTY_DEVELOPMENT_SPINE.md. Respects A81–A84, V12 shadow.

  python3 revenue_engine.py --seed --go
  python3 revenue_engine.py --enroll-titles --go
  python3 revenue_engine.py --sync              # recompute ledger for all 83 assets, then board
  python3 revenue_engine.py --board             # path-to-cash from ledger (call --sync if stale)
  python3 revenue_engine.py --asset PA-MANILA-APT
"""
import os
import sys

import psycopg2
import psycopg2.extras

# same package as development_engine when run from repo root / scripts/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from development_engine import CATALOG, NEXT_MOVE, recompute as de_recompute  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Inferred inventory (provenance: corpus mentions + SPAs). Operator confirms/edits the commercial state.
ASSETS = [
    {"asset_code": "PA-MANILA-APT", "label": "4-storey, 10-unit apartment building (2531 G. Del Pilar, Manila)",
     "case_file": "Paracale-001", "asset_type": "residential_building", "location": "2531 G. Del Pilar St, Singalong, Malate, Manila",
     "est_value": 40000000, "est_income_monthly": 200000, "title_status": "clean", "possession": "yes",
     "has_authority": True, "controlling_matter": None, "modes": ["lease", "sale"], "tier": "earn_now",
     "note": "Inocalla family asset under the Omnibus SPA to Allan; 10 units = recurring rental cash."},
    {"asset_code": "PA-RICEFIELD-CSUR", "label": "13-ha ricefield (Milaor / San Fernando, Camarines Sur)",
     "case_file": "Paracale-001", "asset_type": "agri_land", "location": "Milaor / San Fernando, Camarines Sur",
     "est_value": 13000000, "est_income_monthly": 50000, "title_status": "clean", "possession": "yes",
     "has_authority": True, "controlling_matter": None, "modes": ["lease", "develop"], "tier": "earn_now",
     "note": "Agricultural lease / harvest-share income; in the Omnibus SPA."},
    {"asset_code": "PA-LABO-RES", "label": "534 sqm residential lot (Burgos St, Brgy Gumamela, Labo)",
     "case_file": "Paracale-001", "asset_type": "residential", "location": "Burgos St, Labo, Camarines Norte",
     "est_value": 2500000, "est_income_monthly": 15000, "title_status": "clean", "possession": "yes",
     "has_authority": True, "controlling_matter": None, "modes": ["lease", "sale"], "tier": "earn_now",
     "note": "Small residential — rent or sell."},
    {"asset_code": "PA-GOLDEN-SAND", "label": "Golden Sand Beach Resort", "case_file": "Paracale-001",
     "asset_type": "resort", "location": "Paracale, Camarines Norte", "est_value": 60000000, "est_income_monthly": 0,
     "title_status": "clean", "possession": "yes", "has_authority": True, "controlling_matter": "PAR-GOLDEN-SAND",
     "modes": ["develop", "sale"], "tier": "develop", "note": "Resort development / JV — capital + permits gated."},
    {"asset_code": "PA-P1617-23HA", "label": "23.4-ha lot P-1617 (Jesus Inocalla) + mineral rights",
     "case_file": "Paracale-001", "asset_type": "mineral_agri", "location": "Paracale, Camarines Norte",
     "est_value": 25000000, "est_income_monthly": 0, "title_status": "clean", "possession": "contested",
     "has_authority": True, "controlling_matter": "PAR-CASE-88750", "modes": ["mineral", "develop", "sale"],
     "tier": "develop", "note": "MGB-certified mineral lot; income gated on the mineral-rights dispute (PAR-CASE-88750)."},
    {"asset_code": "PA-T4497-ESTATE", "label": "Keesey T-4497 derivative parcels (Mercedes / Camarines Norte)",
     "case_file": "MWK-001", "asset_type": "parcels", "location": "Mercedes, Camarines Norte",
     "est_value": 50000000, "est_income_monthly": 0, "title_status": "clouded", "possession": "contested",
     "has_authority": True, "controlling_matter": "MWK-CV26360", "modes": ["sale", "lease"], "tier": "recover_then",
     "note": "Held by Balane + 20 transferees; monetizable only after recovery — gated on the CV26360 keystone."},
]


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS property_assets (
        asset_code text PRIMARY KEY, label text, case_file text, asset_type text, location text,
        est_value numeric, est_income_monthly numeric, title_status text, possession text,
        has_authority boolean DEFAULT false, controlling_matter text, modes text[] DEFAULT '{}',
        tier text, note text, updated_at timestamptz DEFAULT now())""")
    for col, ddl in [("area_sqm", "numeric"), ("title_ref", "text"), ("origin", "text DEFAULT 'seed'"),
                     ("needs_valuation", "boolean DEFAULT false"), ("monetization_plan", "text"),
                     ("client_code", "text")]:
        cur.execute(f"ALTER TABLE property_assets ADD COLUMN IF NOT EXISTS {col} {ddl}")


def seed(go=False):
    c = _conn(); cur = c.cursor()
    _ensure(cur)
    for a in ASSETS:
        if go:
            cur.execute("""INSERT INTO property_assets
                (asset_code,label,case_file,asset_type,location,est_value,est_income_monthly,title_status,
                 possession,has_authority,controlling_matter,modes,tier,note,origin,updated_at)
                VALUES (%(asset_code)s,%(label)s,%(case_file)s,%(asset_type)s,%(location)s,%(est_value)s,
                 %(est_income_monthly)s,%(title_status)s,%(possession)s,%(has_authority)s,%(controlling_matter)s,
                 %(modes)s,%(tier)s,%(note)s,'seed', now())
                ON CONFLICT (asset_code) DO UPDATE SET label=EXCLUDED.label, est_value=EXCLUDED.est_value,
                 est_income_monthly=EXCLUDED.est_income_monthly, title_status=EXCLUDED.title_status,
                 possession=EXCLUDED.possession, controlling_matter=EXCLUDED.controlling_matter,
                 modes=EXCLUDED.modes, tier=EXCLUDED.tier, note=EXCLUDED.note, updated_at=now()""", a)
    print(f"[revenue] {'WROTE' if go else 'DRY'} assets={len(ASSETS)}")
    if go:
        cur.execute("""UPDATE property_assets SET client_code = COALESCE(
            client_code, _client_of(controlling_matter), _client_of(case_file))
            WHERE client_code IS NULL""")
        print("[revenue] client_code backfill attempted via _client_of")
    cur.close(); c.close()


def enroll_titles(go=False):
    """Standing rule: every title in the corpus becomes a title-stub asset (origin='title')."""
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    cur.execute("""SELECT tct_number, case_file, registrant_canonical, location, area_sqm, status, lifecycle_status, notes
                   FROM titles WHERE coalesce(tct_number,'') <> ''""")
    rows = cur.fetchall(); n = 0
    for t in rows:
        tct = t["tct_number"]; cf = t["case_file"] or ""
        area = float(t["area_sqm"]) if t["area_sqm"] else None
        ls = (t["lifecycle_status"] or t["status"] or "").lower()
        if "cancel" in ls or "supersed" in ls or "disput" in ls:
            tstatus = "clouded"
        elif cf == "MWK-001":
            tstatus = "clouded"
        elif cf == "Paracale-001":
            tstatus = "clean"
        else:
            tstatus = "unverified"
        possession = "contested" if cf == "MWK-001" else ("yes" if cf == "Paracale-001" else "unknown")
        ctrl = "MWK-CV26360" if cf == "MWK-001" else None
        modes = ["sale", "lease"] + (["develop"] if (area and area > 5000) else [])
        tier = "recover_then" if tstatus == "clouded" else ("develop" if (area and area > 20000) else "earn_now")
        label = f"{tct} — {t['location'] or 'location TBD'}" + (f" ({area/10000:.2f} ha)" if area else "")
        if go:
            cur.execute("""INSERT INTO property_assets
                (asset_code,label,case_file,asset_type,location,est_value,est_income_monthly,title_status,possession,
                 has_authority,controlling_matter,modes,tier,note,area_sqm,title_ref,origin,needs_valuation,updated_at)
                VALUES (%s,%s,%s,'parcel',%s,NULL,0,%s,%s,true,%s,%s,%s,%s,%s,%s,'title',true, now())
                ON CONFLICT (asset_code) DO UPDATE SET label=EXCLUDED.label, location=EXCLUDED.location,
                 title_status=EXCLUDED.title_status, possession=EXCLUDED.possession, controlling_matter=EXCLUDED.controlling_matter,
                 modes=EXCLUDED.modes, tier=EXCLUDED.tier, area_sqm=EXCLUDED.area_sqm,
                 origin='title', updated_at=now()""",
                ("PA-" + tct, label, cf or None, t["location"], tstatus, possession, ctrl, modes, tier,
                 (t["notes"] or "")[:200], area, tct))
        n += 1
    if go:
        cur.execute("""UPDATE property_assets SET client_code = COALESCE(
            client_code, _client_of(controlling_matter), _client_of(case_file))
            WHERE client_code IS NULL""")
    print(f"[revenue] {'WROTE' if go else 'DRY'} titles_enrolled={n} (title stubs; run --sync to light the ledger)")
    cur.close(); c.close()


# ── ledger read path (single epistemology) ───────────────────────────────────────────────────────

def _load_ledger_chain(cur, asset_code, mode, project_code=None):
    """Build ordered chain from asset_preconditions for one mode.

    Asset-owned codes: always from ledger (missing → unknown until --sync).
    Project-owned codes: from the named project, else first active project for asset+mode,
    else display-only unknown (no write — V12 requires a real project row).
    """
    catalog = CATALOG.get(mode) or []
    if not catalog:
        return [], None

    # Resolve project for this asset+mode if any
    if project_code is None:
        cur.execute("""SELECT project_code FROM development_projects
                       WHERE asset_code=%s AND mode=%s AND status='active'
                       ORDER BY is_primary DESC, project_code LIMIT 1""", (asset_code, mode))
        row = cur.fetchone()
        project_code = row["project_code"] if row else None

    # Pull all relevant precond rows in one query
    cur.execute("""SELECT owner_kind, owner_code, code, label, status, reason, sort_order, next_move
                   FROM asset_preconditions
                   WHERE mode=%s AND (
                     (owner_kind='asset' AND owner_code=%s)
                     OR (owner_kind='project' AND owner_code=%s)
                   )""", (mode, asset_code, project_code or ""))
    by_key = {(r["owner_kind"], r["code"]): r for r in cur.fetchall()}

    chain = []
    gating = None
    for code, label, owner_kind, sort_order, kind in catalog:
        if owner_kind == "asset":
            r = by_key.get(("asset", code))
        else:
            r = by_key.get(("project", code)) if project_code else None
        if r:
            st, reason = r["status"], (r["reason"] or "")
            lbl = r["label"] or label
        else:
            # Missing row: not yet synced, or project-owned without a project
            if owner_kind == "project" and not project_code:
                st, reason = "unknown", "no deal/project opened — open a project to track this"
            else:
                st, reason = "unknown", "ledger gap — run revenue_engine --sync"
            lbl = label
        chain.append((code, lbl, st, reason))
        if gating is None and st != "ok":
            gating = (code, lbl, st, reason)
    return chain, gating


def plan_for(a, cur=None):
    """Pick the mode closest to cash from the LEDGER. Returns (best_mode, gating, plan_text, ok_ratio).

    If cur is None, opens a short-lived connection (callers with a cursor should pass it).
    """
    own = cur is None
    if own:
        c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    best = None
    asset_code = a["asset_code"] if isinstance(a, dict) and "asset_code" in a else None
    modes = a.get("modes") or []
    if not asset_code:
        # ad-hoc dict without asset_code (legacy enroll dry-run) — cannot read ledger
        if own:
            cur.close(); c.close()
        return (None, None, "no asset_code — cannot read ledger", 0.0)

    for mode in modes:
        if mode not in CATALOG:
            continue
        chain, gating = _load_ledger_chain(cur, asset_code, mode)
        if not chain:
            continue
        ratio = sum(1 for _, _, st, _ in chain if st == "ok") / len(chain)
        cand = (ratio, mode, gating, chain)
        if best is None or ratio > best[0]:
            best = cand
    if own:
        cur.close(); c.close()
    if not best:
        return (None, None, "no monetization mode set / no ledger rows — run --sync", 0.0)
    ratio, mode, gating, _chain = best
    if gating is None:
        return (mode, None, f"READY to {mode}", ratio)
    code, label, st, reason = gating
    return (mode, gating, f"{mode}: blocked at {label} ({reason}) → {NEXT_MOVE.get(code, '')}", ratio)


def _opportunity(a, mode, cur=None):
    """Ledger-backed chain for one mode. Signature preserved for callers."""
    own = cur is None
    if own:
        c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    chain, gating = _load_ledger_chain(cur, a["asset_code"], mode)
    if own:
        cur.close(); c.close()
    return chain, gating


def board(cap=10, sync_first=False):
    if sync_first:
        print("[revenue] syncing ledger via development_engine.recompute() …")
        de_recompute()
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM property_assets WHERE client_code IS NOT NULL")
    assets = cur.fetchall()
    rows = []
    for a in assets:
        mode, gating, plan, ratio = plan_for(a, cur=cur)
        # refresh monetization_plan denorm (best-effort; non-fatal)
        try:
            cur.execute("UPDATE property_assets SET monetization_plan=%s, updated_at=now() WHERE asset_code=%s",
                        (plan[:500] if plan else None, a["asset_code"]))
        except Exception:
            pass
        rows.append({"a": a, "mode": mode, "gating": gating, "plan": plan, "ratio": ratio,
                     "tier_rank": {"earn_now": 0, "develop": 1, "recover_then": 2}.get(a["tier"] or "", 3)})
    rows.sort(key=lambda r: (r["tier_rank"], -r["ratio"], -float(r["a"]["est_income_monthly"] or 0),
                             -float(r["a"]["est_value"] or 0), -float(r["a"]["area_sqm"] or 0)))
    print("\n" + "=" * 82)
    print(f"PATH TO CASH (ledger) — {len(rows)} assets, fastest money first")
    print("=" * 82)
    cur_tier = None; shown = 0
    for r in rows:
        a = r["a"]
        if a["tier"] != cur_tier:
            cur_tier = a["tier"]; shown = 0
            cnt = sum(1 for x in rows if x["a"]["tier"] == cur_tier)
            print(f"\n── {(cur_tier or 'UNSET').upper().replace('_', '-')} ({cnt}) ──")
        shown += 1
        if shown > cap:
            continue
        size = (f"₱{float(a['est_value'])/1e6:.0f}M" if a["est_value"] else
                (f"{float(a['area_sqm'])/10000:.1f}ha" if a["area_sqm"] else "—"))
        inc = f"·₱{float(a['est_income_monthly'])/1e3:.0f}k/mo" if a["est_income_monthly"] else ""
        ready = "▶" if r["gating"] is None else " "
        origin = (a.get("origin") or "?")[0]
        print(f" {ready}{a['asset_code']:<18}[{origin}]{(r['mode'] or '-'):<8}{size:>7}{inc:<10} "
              f"{r['ratio']:.0%}  {r['plan']}")
    # summary
    with_ok = sum(1 for r in rows if r["ratio"] > 0)
    blocked = sum(1 for r in rows if r["gating"] and r["gating"][2] == "blocked")
    print(f"\n  summary: {len(rows)} assets · {with_ok} with ≥1 ok link · {blocked} gated blocked · "
          f"source=asset_preconditions")
    cur.close(); c.close()


def asset(code):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM property_assets WHERE asset_code=%s", (code,))
    a = cur.fetchone()
    if not a:
        print(f"no asset {code}"); cur.close(); c.close(); return
    print(f"\n{a['asset_code']} — {a['label']}")
    print(f"  origin={a.get('origin')} client={a.get('client_code')} title:{a['title_status']} "
          f"possession:{a['possession']}")
    if a.get("note"):
        print(f"  {a['note']}")
    print(f"  value ₱{float(a['est_value'] or 0)/1e6:.0f}M  income ₱{float(a['est_income_monthly'] or 0)/1e3:.0f}k/mo")
    for mode in (a["modes"] or []):
        if mode not in CATALOG:
            continue
        chain, gating = _load_ledger_chain(cur, a["asset_code"], mode)
        print(f"\n  MODE: {mode}" + ("  [from ledger]" if chain else "  [empty — run --sync]"))
        for code_, label, st, reason in chain:
            mark = {"ok": "✓", "blocked": "⛔", "todo": "○", "unknown": "?"}.get(st, " ")
            print(f"    {mark} {label} — {reason}")
    cur.close(); c.close()


def sync():
    """Full portfolio ledger refresh, then board."""
    print("[revenue] --sync: development_engine.recompute() for all assets with client_code")
    de_recompute()
    board(cap=15, sync_first=False)


if __name__ == "__main__":
    a = sys.argv
    if "--seed" in a:
        seed(go="--go" in a)
    elif "--enroll-titles" in a:
        enroll_titles(go="--go" in a)
    elif "--sync" in a:
        sync()
    elif "--board" in a:
        board(sync_first=("--sync" in a or "--refresh" in a))
    elif "--asset" in a:
        asset(a[a.index("--asset") + 1])
    else:
        print(__doc__)
