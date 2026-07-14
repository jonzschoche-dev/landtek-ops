#!/usr/bin/env python3
"""profitability_prep_cycle.py — CONTINUOUS preparation of every property for profitability.

Doctrine (operator 2026-07-15):
  * Prep runs whether or not anyone prompts.
  * Prep does NOT require a controlling_matter. Matter attaches only when the schedule/obligation
    calls for it — never as the default gate on the whole portfolio.
  * Goal: maximum momentum — always a clear next prep move per property, across all tracks
    (earn-now, develop, agrarian, recovery) in parallel.

Each cycle:
  1. RECOMPUTE the asset_preconditions ledger for all assets with client_code
     (development_engine — sole writer of asset-owned cache).
  2. DERIVE prep moves from non-ok preconditions + structural gaps (no map, no deal shell, …).
  3. UPSERT open moves; CLOSE moves whose precond is now ok.
  4. LOG the cycle (heartbeat).

  python3 profitability_prep_cycle.py              # full cycle
  python3 profitability_prep_cycle.py --report     # momentum board only (no writes)
  python3 profitability_prep_cycle.py --no-recompute  # derive from current ledger only
  python3 profitability_prep_cycle.py --limit 20   # print top N

Timer: landtek-profitability-prep.timer (deploy_914)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from development_engine import CATALOG, NEXT_MOVE, recompute as de_recompute  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Prep-oriented actions (momentum). Prefer DOING over WAITING on a matter.
PREP_ACTIONS = {
    "marketable_title": "PREP title file: CTC + RD annotations + liens; assemble quiet-title / recovery pack",
    "secure_tenure":    "PREP tenure file: CTC + chain status + who holds possession papers",
    "survey_geometry":  "PREP geometry: link/plot map_parcel; upgrade rough→survey when possible",
    "seller_authority": "PREP authority: confirm SPA/heirs consent docs on file and unrevoked",
    "tax_clearance":    "PREP tax pack: RPT receipts + compute CGT/DST path for a future transfer",
    "registrable":      "PREP registrability: list blocking annotations; draft lift/cancel requests",
    "possession":       "PREP possession: who occupies, since when, paper trail, photos if any",
    "usable":           "PREP unit readiness: inspect/repairs checklist for lease or sale",
    "buyer_price":      "PREP sale readiness: pricing memo + broker list (open a deal when ready)",
    "tenant":           "PREP lease readiness: unit sheet + rent comps (open a lease deal when ready)",
    "lease_instrument": "PREP lease form: draft terms from unit sheet (no outbound without gate)",
    "collection":       "PREP collection: account path + receipt template for when leased",
    "permits":          "PREP permits: list required LGU/DENR items; seed permit skeleton rows",
    "capital_partner":  "PREP capital: one-pager for JV/partner (operator decides outreach)",
    "feasibility":      "PREP feasibility: area/value/income sheet from title + map facts",
    "mineral_rights":   "PREP mineral file: MGB papers + dispute chronology (no matter wait)",
    "permit":           "PREP mineral permit: MGB checklist + gaps",
    "operator":         "PREP operator shortlist for mineral/lease ops",
}

# Priority: lower = sooner. Earn-now + blocked title prep still high (prep, not freeze).
TIER_BOOST = {"earn_now": 0, "develop": 10, "recover_then": 20}
STATUS_BOOST = {"blocked": 0, "todo": 15, "unknown": 25}


def _conn(autocommit=True):
    c = psycopg2.connect(DSN)
    c.autocommit = autocommit
    return c


def _ensure(cur):
    """Idempotent minimal ensure if migration not applied yet."""
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
          move_key text NOT NULL,
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          closed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (move_key)
        )""")
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
        CREATE OR REPLACE VIEW v_profitability_momentum AS
        SELECT m.priority, m.client_code, m.asset_code, a.label AS asset_label, a.origin, a.tier,
               a.title_status, m.mode, m.precond_code, m.action, m.why, m.recheck_condition,
               m.matter_code, m.last_seen_at
          FROM profitability_prep_moves m
          JOIN property_assets a ON a.asset_code = m.asset_code
         WHERE m.status = 'open'
         ORDER BY m.priority ASC, m.last_seen_at DESC""")


def _priority(tier, status, sort_order):
    return TIER_BOOST.get(tier or "", 30) + STATUS_BOOST.get(status or "unknown", 25) + int(sort_order or 50)


def _action_for(code, status, reason):
    base = PREP_ACTIONS.get(code) or NEXT_MOVE.get(code) or f"PREP: resolve {code}"
    # Never phrase as "wait for controlling matter only"
    if status == "blocked" and reason and "gated on" in reason.lower():
        return base  # prep pack, not wait
    return base


def _optional_matter(asset):
    """Matter is optional context only — never required for the move to exist."""
    return asset.get("controlling_matter") or None


def derive_moves(cur, asset):
    """Yield dicts of prep moves for one asset from the ledger + structural gaps."""
    ac = asset["asset_code"]
    client = asset.get("client_code")
    tier = asset.get("tier")
    matter = _optional_matter(asset)
    modes = list(asset.get("modes") or []) or ["sale"]

    # All non-ok ledger rows for this asset (asset-owned + any project-owned for its projects)
    cur.execute("""
        SELECT ap.mode, ap.code, ap.label, ap.status, ap.reason, ap.next_move,
               ap.evidence_ref, ap.recheck_condition, ap.sort_order, ap.owner_kind
          FROM asset_preconditions ap
         WHERE (ap.owner_kind='asset' AND ap.owner_code=%s)
            OR (ap.owner_kind='project' AND ap.owner_code IN (
                  SELECT project_code FROM development_projects
                   WHERE asset_code=%s AND status='active'))
           AND ap.status <> 'ok'
         ORDER BY ap.mode, ap.sort_order""", (ac, ac))
    rows = cur.fetchall()
    seen = set()
    for r in rows:
        key = (r["mode"], r["code"])
        if key in seen:
            continue
        seen.add(key)
        action = _action_for(r["code"], r["status"], r["reason"])
        why = f"{r['status']}: {r['reason'] or r['label'] or r['code']}"
        yield dict(
            client_code=client, asset_code=ac, matter_code=matter,
            mode=r["mode"], precond_code=r["code"], action=action, why=why,
            recheck_condition=r["recheck_condition"] or f"{r['code']} becomes ok",
            evidence_ref=r["evidence_ref"],
            priority=_priority(tier, r["status"], r["sort_order"]),
        )

    # Structural gap: no map link at all (geometry prep even before a precond row)
    cur.execute("SELECT 1 FROM asset_map_parcels WHERE asset_code=%s LIMIT 1", (ac,))
    if not cur.fetchone():
        yield dict(
            client_code=client, asset_code=ac, matter_code=matter,
            mode=None, precond_code="survey_geometry",
            action=PREP_ACTIONS["survey_geometry"],
            why="no map_parcel linked — geometry prep unblocks develop + area checks",
            recheck_condition="asset_map_parcels row exists with geom",
            evidence_ref=None,
            priority=_priority(tier, "unknown", 20),
        )

    # Structural gap: modes include sale/lease but no active deal project — still prep, don't freeze
    for mode in modes:
        if mode not in ("sale", "lease", "develop", "mineral"):
            continue
        cur.execute("""SELECT 1 FROM development_projects
                        WHERE asset_code=%s AND mode=%s AND status='active' LIMIT 1""", (ac, mode))
        if cur.fetchone():
            continue
        # only if asset-owned core for that mode is mostly ok → deal shell is the next momentum
        cat = CATALOG.get(mode) or []
        asset_codes = [c for c, _, ok, _, _ in cat if ok == "asset"]
        if not asset_codes:
            continue
        cur.execute("""SELECT count(*) FILTER (WHERE status='ok') AS ok, count(*) AS n
                         FROM asset_preconditions
                        WHERE owner_kind='asset' AND owner_code=%s AND mode=%s
                          AND code = ANY(%s)""", (ac, mode, asset_codes))
        st = cur.fetchone()
        if st and st["n"] and st["ok"] >= max(1, st["n"] - 1):
            yield dict(
                client_code=client, asset_code=ac, matter_code=matter,
                mode=mode, precond_code="_deal_shell",
                action=f"PREP open a {mode} deal project when ready (ledger nearly clear for asset facts)",
                why=f"asset-owned {mode} facts {st['ok']}/{st['n']} ok — deal shell is optional momentum",
                recheck_condition=f"development_projects row for {mode} or operator defers",
                evidence_ref=None,
                priority=_priority(tier, "todo", 80),
            )


def _move_key(m):
    return "|".join([
        m["asset_code"],
        m.get("mode") or "",
        m.get("precond_code") or "",
        m["action"][:200],
    ])


def upsert_move(cur, m):
    m = dict(m)
    m["move_key"] = _move_key(m)
    cur.execute("""
        INSERT INTO profitability_prep_moves
          (client_code, asset_code, matter_code, mode, precond_code, action, why,
           recheck_condition, evidence_ref, priority, status, origin, move_key, last_seen_at, updated_at)
        VALUES (%(client_code)s,%(asset_code)s,%(matter_code)s,%(mode)s,%(precond_code)s,%(action)s,%(why)s,
                %(recheck_condition)s,%(evidence_ref)s,%(priority)s,'open','prep_cycle',%(move_key)s,now(),now())
        ON CONFLICT (move_key)
        DO UPDATE SET
          client_code=EXCLUDED.client_code,
          matter_code=EXCLUDED.matter_code,
          why=EXCLUDED.why,
          recheck_condition=EXCLUDED.recheck_condition,
          evidence_ref=EXCLUDED.evidence_ref,
          priority=EXCLUDED.priority,
          status='open',
          closed_at=NULL,
          last_seen_at=now(),
          updated_at=now()
        """, m)


def close_resolved(cur, seen_keys):
    """Mark open moves not seen this cycle as done when their precond is now ok; else leave open
    (staleness: if not in seen_keys and precond ok → done; if precond still non-ok, keep open)."""
    cur.execute("""SELECT id, asset_code, mode, precond_code, action FROM profitability_prep_moves
                   WHERE status='open'""")
    closed = 0
    for row in cur.fetchall():
        key = "|".join([row["asset_code"], row["mode"] or "", row["precond_code"] or "",
                        (row["action"] or "")[:200]])
        if key in seen_keys:
            continue
        # Structural codes without ledger row
        if row["precond_code"] in (None, "", "_deal_shell", "survey_geometry"):
            if row["precond_code"] == "survey_geometry":
                cur.execute("SELECT 1 FROM asset_map_parcels WHERE asset_code=%s LIMIT 1",
                            (row["asset_code"],))
                if cur.fetchone():
                    cur.execute("""UPDATE profitability_prep_moves SET status='done', closed_at=now(),
                                   updated_at=now() WHERE id=%s""", (row["id"],))
                    closed += 1
            continue
        cur.execute("""SELECT status FROM asset_preconditions
                        WHERE owner_kind='asset' AND owner_code=%s AND mode IS NOT DISTINCT FROM %s
                          AND code=%s
                       UNION ALL
                       SELECT ap.status FROM asset_preconditions ap
                        JOIN development_projects dp ON dp.project_code=ap.owner_code
                        WHERE ap.owner_kind='project' AND dp.asset_code=%s
                          AND ap.mode IS NOT DISTINCT FROM %s AND ap.code=%s
                       LIMIT 1""",
                    (row["asset_code"], row["mode"], row["precond_code"],
                     row["asset_code"], row["mode"], row["precond_code"]))
        st = cur.fetchone()
        if st and st["status"] == "ok":
            cur.execute("""UPDATE profitability_prep_moves SET status='done', closed_at=now(),
                           updated_at=now() WHERE id=%s""", (row["id"],))
            closed += 1
    return closed


def run_cycle(do_recompute=True, report_limit=25):
    started = datetime.now(timezone.utc)
    if do_recompute:
        print("[prep] recompute ledger (all assets) …")
        de_recompute()

    c = _conn(autocommit=False)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)

    cur.execute("""INSERT INTO profitability_prep_cycles (started_at) VALUES (%s) RETURNING id""",
                (started,))
    cycle_id = cur.fetchone()["id"]

    cur.execute("SELECT * FROM property_assets WHERE client_code IS NOT NULL ORDER BY asset_code")
    assets = cur.fetchall()
    seen_keys = set()
    upserted = 0
    for a in assets:
        for m in derive_moves(cur, a):
            upsert_move(cur, m)
            upserted += 1
            seen_keys.add(_move_key(m))
    closed = close_resolved(cur, seen_keys)
    cur.execute("SELECT count(*) AS n FROM profitability_prep_moves WHERE status='open'")
    open_n = cur.fetchone()["n"]
    note = (f"continuous prep — matter optional; assets={len(assets)} "
            f"upserted={upserted} closed={closed} open={open_n}")
    cur.execute("""UPDATE profitability_prep_cycles SET finished_at=now(), assets_seen=%s,
                   moves_open=%s, moves_upserted=%s, moves_closed=%s, note=%s WHERE id=%s""",
                (len(assets), open_n, upserted, closed, note, cycle_id))
    c.commit()
    print(f"[prep] cycle #{cycle_id}: {note}")
    report(cur, limit=report_limit)
    cur.close(); c.close()
    return open_n


def report(cur=None, limit=25):
    own = cur is None
    if own:
        c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        _ensure(cur)
    if _view_exists(cur):
        cur.execute("""SELECT priority, client_code, asset_code, mode, precond_code, action, why, tier
                         FROM v_profitability_momentum LIMIT %s""", (limit,))
    else:
        cur.execute("""SELECT m.priority, m.client_code, m.asset_code, m.mode, m.precond_code,
                              m.action, m.why, a.tier
                         FROM profitability_prep_moves m
                         JOIN property_assets a ON a.asset_code=m.asset_code
                        WHERE m.status='open'
                        ORDER BY m.priority, m.last_seen_at DESC LIMIT %s""", (limit,))
    rows = cur.fetchall()
    print("\n" + "=" * 88)
    print(f"PROFITABILITY MOMENTUM — top {len(rows)} prep moves (continuous; not matter-gated)")
    print("=" * 88)
    for r in rows:
        mode = r["mode"] or "-"
        print(f"  p{r['priority']:<3} {(r['client_code'] or '?'):<12} {r['asset_code']:<18} "
              f"{mode:<8} {r['precond_code'] or '-':<18}")
        print(f"       → {r['action']}")
        if r.get("why"):
            print(f"         ({r['why'][:100]})")
    if own:
        cur.execute("SELECT id, finished_at, assets_seen, moves_open, note FROM profitability_prep_cycles "
                    "ORDER BY id DESC LIMIT 1")
        last = cur.fetchone()
        if last:
            print(f"\n  last cycle: #{last['id']} open={last['moves_open']} "
                  f"assets={last['assets_seen']} @ {last['finished_at']}")
        cur.close(); c.close()


def _view_exists(cur):
    cur.execute("SELECT 1 FROM pg_views WHERE viewname='v_profitability_momentum'")
    return bool(cur.fetchone())


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--report" in args:
        report(limit=int(args[args.index("--limit") + 1]) if "--limit" in args else 25)
    else:
        lim = int(args[args.index("--limit") + 1]) if "--limit" in args else 25
        run_cycle(do_recompute=("--no-recompute" not in args), report_limit=lim)
