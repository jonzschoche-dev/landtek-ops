#!/usr/bin/env python3
"""profit_board.py — the magnate engine's MONEY board (deploy_1111).

Ranks client property fronts by expected pesos (recurring income + readiness/tier-
discounted capital), not by readiness urgency alone. Reads v_profit_frontboard, which
is layered over the running readiness engine (profitability_prep_cycle.py) and uses only
figures already on property_assets — it fabricates no numbers; assets with no value show
as VALUE UNKNOWN.

  python3 profit_board.py                 # ranked money board + value-unknown + gaps
  python3 profit_board.py --client MWK-001
  python3 profit_board.py --limit 20
"""
from __future__ import annotations
import os, sys
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _peso(n):
    if n is None:
        return "—"
    return f"₱{float(n):,.0f}"


def main():
    args = sys.argv[1:]
    def val(f):
        return args[args.index(f) + 1] if f in args and args.index(f) + 1 < len(args) else None
    client = val("--client")
    limit = int(val("--limit") or 15)

    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = "WHERE money_score IS NOT NULL"
    params = []
    if client:
        where += " AND client_code = %s"
        params.append(client)
    cur.execute(f"""SELECT * FROM v_profit_frontboard {where}
                    ORDER BY money_score DESC NULLS LAST LIMIT %s""", (*params, limit))
    ranked = cur.fetchall()

    print("=" * 96)
    print("MONEY BOARD — fronts ranked by expected pesos  (money_score = annual income + 8%/yr × realizable capital)")
    print("=" * 96)
    print(f"  {'#':>2}  {'money/yr':>13}  {'tier':<12} {'income/mo':>11}  {'est_value':>13}  {'rdy':>4}  asset")
    print("  " + "-" * 92)
    for i, r in enumerate(ranked, 1):
        print(f"  {i:>2}  {_peso(r['money_score']):>13}  {(r['tier'] or '-'):<12} "
              f"{_peso(r['est_income_monthly']):>11}  {_peso(r['est_value']):>13}  "
              f"{(r['readiness'] or 0):>4}  {r['asset_code']}")
        print(f"      └ {(r['label'] or '')[:60]}  [{r['client_code']}]")
        if r.get("next_prep_action"):
            print(f"        gating ({r['weakest_axis']}): {r['next_prep_action'][:72]}")

    # VALUE UNKNOWN — honest separation, not zero-ranked
    uw = "WHERE money_score IS NULL"
    up = []
    if client:
        uw += " AND client_code = %s"; up.append(client)
    cur.execute(f"""SELECT count(*) AS n, count(*) FILTER (WHERE needs_valuation) AS needs
                    FROM v_profit_frontboard {uw}""", up)
    u = cur.fetchone()
    print("\n  " + "-" * 92)
    print(f"  VALUE UNKNOWN: {u['n']} fronts carry no est_value/income "
          f"({u['needs']} flagged needs_valuation) — invisible to the money ranking until valued.")

    # The gap the magnate must see: money-judgment fronts the asset engine can't model
    print("\n" + "=" * 96)
    print("NOT ON THIS BOARD (money the asset engine cannot see — collection/judgment fronts):")
    print("  • CV6839 CARP just-compensation (RTC Br40, Land Bank payor) — the guaranteed near-term cash,")
    print("    modeled as a court matter, not a property_asset → it never enters this ranking.")
    print("  • Expense reimbursement recovery (advances logged) + LGU expenditure claims.")
    print("  Next step: model collection/judgment fronts as first-class, valued fronts so they rank here too.")
    print("=" * 96)

    cur.close(); c.close()


if __name__ == "__main__":
    main()
