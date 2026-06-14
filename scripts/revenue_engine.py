#!/usr/bin/env python3
"""revenue_engine.py — the monetization brain (second north-star: make money from the portfolio).

Same pattern as the litigation engine, pointed at cash: every revenue opportunity decomposes
into the first-principles chain of conditions that MUST be true for money to flow (a sale needs
marketable title + authority + buyer + taxes + registrability; a lease needs possession + a usable
unit + a tenant + a contract + collection). The agent assesses each link against reality, finds the
BROKEN one, and names the move to clear it — so you see *why* each deal happens or stalls, and pursue
every opportunity without hesitation. Creditless to architect; deals are yours to execute.

Cross-links to litigation: a clouded-title asset's "marketable_title" link is BLOCKED by the matter
that must resolve it — so the board shows e.g. "can't sell the Keesey parcels until CV26360 wins."

  python3 revenue_engine.py --seed --go        # load the asset inventory
  python3 revenue_engine.py --board            # the path-to-cash board (fastest money first)
  python3 revenue_engine.py --asset PA-MANILA-APT
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# first-principles preconditions per monetization mode (ordered — gating = first not-ok link)
PRECONDS = {
    "sale": [("marketable_title", "clean, registrable title"), ("seller_authority", "authority to sell (heirs' consent / valid SPA)"),
             ("buyer_price", "a buyer + agreed price"), ("tax_clearance", "CGT/DST/CAR + RPT clearance"),
             ("registrable", "RD will register the transfer")],
    "lease": [("possession", "actual possession/control"), ("usable", "usable/habitable condition"),
              ("tenant", "a tenant/lessee"), ("lease_instrument", "a lease contract"), ("collection", "a collection mechanism")],
    "develop": [("secure_tenure", "marketable title or secure tenure"), ("permits", "zoning + DENR/LGU permits"),
                ("capital_partner", "capital or a JV partner"), ("feasibility", "a return/feasibility case")],
    "mineral": [("mineral_rights", "mineral rights resolved/owned"), ("permit", "MGB permit / mineral agreement"),
                ("operator", "an operator/lessee")],
}
NEXT_MOVE = {
    "marketable_title": "clear/quiet the title (often gated on the controlling litigation)",
    "seller_authority": "confirm heirs' consent or a valid, unrevoked SPA",
    "buyer_price": "source a buyer + set a price (list it / work brokers)",
    "tax_clearance": "compute + secure CGT/DST/CAR + RPT clearance",
    "registrable": "clear blocking annotations so the RD can register",
    "possession": "establish/confirm actual possession + control",
    "usable": "make the unit usable (repairs/turnover)",
    "tenant": "find a tenant/lessee",
    "lease_instrument": "execute a lease contract",
    "collection": "set up rent collection + records",
    "secure_tenure": "secure marketable title or tenure for development",
    "permits": "obtain zoning/locational + DENR/LGU permits",
    "capital_partner": "raise capital or sign a JV partner",
    "feasibility": "build the feasibility/return case",
    "mineral_rights": "resolve the mineral-rights dispute",
    "permit": "secure the MGB permit / mineral agreement",
    "operator": "engage an operator/lessee",
}

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


def seed(go=False):
    c = _conn(); cur = c.cursor()
    _ensure(cur)
    for a in ASSETS:
        if go:
            cur.execute("""INSERT INTO property_assets
                (asset_code,label,case_file,asset_type,location,est_value,est_income_monthly,title_status,
                 possession,has_authority,controlling_matter,modes,tier,note,updated_at)
                VALUES (%(asset_code)s,%(label)s,%(case_file)s,%(asset_type)s,%(location)s,%(est_value)s,
                 %(est_income_monthly)s,%(title_status)s,%(possession)s,%(has_authority)s,%(controlling_matter)s,
                 %(modes)s,%(tier)s,%(note)s, now())
                ON CONFLICT (asset_code) DO UPDATE SET label=EXCLUDED.label, est_value=EXCLUDED.est_value,
                 est_income_monthly=EXCLUDED.est_income_monthly, title_status=EXCLUDED.title_status,
                 possession=EXCLUDED.possession, controlling_matter=EXCLUDED.controlling_matter,
                 modes=EXCLUDED.modes, tier=EXCLUDED.tier, note=EXCLUDED.note, updated_at=now()""", a)
    print(f"[revenue] {'WROTE' if go else 'DRY'} assets={len(ASSETS)}")
    cur.close(); c.close()


def _assess(a, code):
    """Return (status, reason). status: ok | blocked | todo | unknown."""
    ts, pos, ctrl = a["title_status"], a["possession"], a["controlling_matter"]
    if code in ("marketable_title", "secure_tenure"):
        if ts == "clouded":
            return "blocked", f"title clouded — gated on {ctrl or 'recovery'}"
        if ts == "untitled":
            return "todo", "needs titling"
        return "ok", "title clean"
    if code == "mineral_rights":
        return ("blocked", f"mineral-rights dispute open ({ctrl})") if ctrl else ("ok", "rights clear")
    if code == "possession":
        return {"yes": ("ok", "in possession"), "contested": ("blocked", "possession contested"),
                "no": ("unknown", "possession unknown")}.get(pos, ("unknown", "?"))
    if code == "seller_authority":
        return ("ok", "SPA/authority in place") if a["has_authority"] else ("unknown", "confirm authority")
    if code in ("buyer_price", "tenant", "capital_partner", "operator"):
        return "unknown", "needs sourcing (your input)"
    if code in ("tax_clearance", "registrable", "permits", "lease_instrument", "collection", "usable", "feasibility", "permit"):
        return "todo", "process step"
    return "unknown", "?"


def _opportunity(a, mode):
    chain = []
    gating = None
    for code, label in PRECONDS[mode]:
        st, reason = _assess(a, code)
        chain.append((code, label, st, reason))
        if gating is None and st != "ok":
            gating = (code, label, st, reason)
    return chain, gating


def board():
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM property_assets")
    assets = cur.fetchall()
    rows = []
    for a in assets:
        for mode in (a["modes"] or []):
            chain, gating = _opportunity(a, mode)
            ok_links = sum(1 for _, _, st, _ in chain if st == "ok")
            tier_rank = {"earn_now": 0, "develop": 1, "recover_then": 2}.get(a["tier"], 3)
            rows.append({"asset": a, "mode": mode, "gating": gating, "ok": ok_links, "n": len(chain),
                         "tier_rank": tier_rank})
    # fastest money first: tier, then most links already satisfied, then income/value
    rows.sort(key=lambda r: (r["tier_rank"], -(r["ok"] / r["n"]),
                             -float(r["asset"]["est_income_monthly"] or 0), -float(r["asset"]["est_value"] or 0)))
    print("\n" + "=" * 80)
    print("PATH TO CASH — every opportunity, fastest money first, with the broken link")
    print("=" * 80)
    cur_tier = None
    for r in rows:
        a = r["asset"]
        if a["tier"] != cur_tier:
            cur_tier = a["tier"]
            print(f"\n── {cur_tier.upper().replace('_', '-')} ──")
        val = f"₱{float(a['est_value'] or 0)/1e6:.0f}M"
        inc = f" · ₱{float(a['est_income_monthly'])/1e3:.0f}k/mo" if a["est_income_monthly"] else ""
        if r["gating"] is None:
            status = "▶ READY TO TRANSACT"
        else:
            code, label, st, reason = r["gating"]
            tag = {"blocked": "⛔", "todo": "○", "unknown": "?"}.get(st, "")
            status = f"{tag} blocked at: {label} — {reason}  →  {NEXT_MOVE.get(code, '')}"
        print(f" [{r['ok']}/{r['n']}] {a['asset_code']:<16} {r['mode']:<8} {val}{inc}")
        print(f"        {status}")
    cur.close(); c.close()


def asset(code):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM property_assets WHERE asset_code=%s", (code,))
    a = cur.fetchone()
    if not a:
        print(f"no asset {code}"); cur.close(); c.close(); return
    print(f"\n{a['asset_code']} — {a['label']}\n  {a['note']}\n  value ₱{float(a['est_value'] or 0)/1e6:.0f}M  income ₱{float(a['est_income_monthly'] or 0)/1e3:.0f}k/mo  title:{a['title_status']} possession:{a['possession']}")
    for mode in (a["modes"] or []):
        chain, gating = _opportunity(a, mode)
        print(f"\n  MODE: {mode}")
        for code, label, st, reason in chain:
            mark = {"ok": "✓", "blocked": "⛔", "todo": "○", "unknown": "?"}.get(st, " ")
            print(f"    {mark} {label} — {reason}")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--seed" in a:
        seed(go="--go" in a)
    elif "--board" in a:
        board()
    elif "--asset" in a:
        asset(a[a.index("--asset") + 1])
    else:
        print(__doc__)
