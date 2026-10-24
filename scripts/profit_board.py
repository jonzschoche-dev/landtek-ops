#!/usr/bin/env python3
"""profit_board.py — the magnate engine's MONEY board (deploy_1264/1265).

Ranks fronts by EXPECTED NEAR-TERM CASH (~next 24 months), not readiness urgency:
  near_term_cash = annual_income*2  +  one_time_cash
  one_time_cash  = est_value * readiness * tier_factor   (ONLY cash-event fronts: judgment/sale)
Held/recover land that isn't being sold contributes 0 near-term cash (honest); its est_value is
shown as the long-run backdrop and used as the tiebreak. Reads v_profit_frontboard, which UNIONs
property_assets (via the readiness engine) with money_fronts (judgment/collection money the property
engine can't model). Uses only figures already in the DB — fabricates nothing.

  python3 profit_board.py                 # Keesey-first money board + value-unknown + backdrop
  python3 profit_board.py --client MWK-001
  python3 profit_board.py --all           # every client
  python3 profit_board.py --limit 20
"""
from __future__ import annotations
import os, sys
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _peso(n):
    return "—" if n is None else f"₱{float(n):,.0f}"


def main():
    args = sys.argv[1:]
    def val(f):
        return args[args.index(f) + 1] if f in args and args.index(f) + 1 < len(args) else None
    client = val("--client")
    show_all = "--all" in args
    limit = int(val("--limit") or 20)

    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cond, params = [], []
    if client:
        cond.append("client_code = %s"); params.append(client)
    where = ("WHERE " + " AND ".join(cond)) if cond else ""

    # 1) ranked by near-term cash
    cur.execute(f"""SELECT * FROM v_profit_frontboard {where}
                    {'AND' if where else 'WHERE'} near_term_cash IS NOT NULL AND near_term_cash > 0
                    ORDER BY near_term_cash DESC LIMIT %s""", (*params, limit))
    cash = cur.fetchall()

    scope = client or ("all clients" if show_all else "all clients")
    print("=" * 98)
    print(f"MONEY BOARD — fronts by EXPECTED NEAR-TERM CASH (~24 mo)   scope: {scope}")
    print("  near_term_cash = 2×annual income + one-time cash (judgment/sale × readiness × tier)")
    print("=" * 98)
    print(f"  {'#':>2}  {'near-term₱':>13}  {'src':<5} {'tier':<12} {'rdy':>4}  {'est_value':>13}  front")
    print("  " + "-" * 94)
    for i, r in enumerate(cash, 1):
        print(f"  {i:>2}  {_peso(r['near_term_cash']):>13}  {r['source'][:5]:<5} {(r['tier'] or '-'):<12} "
              f"{(r['readiness'] or 0):>4}  {_peso(r['est_value']):>13}  {r['front_code']}")
        print(f"      └ {(r['label'] or '')[:62]}  [{r['client_code']}]")
        if r.get("next_step"):
            print(f"        next: {r['next_step'][:80]}")

    # 2) long-run backdrop: value held but no near-term cash (recover/hold)
    cur.execute(f"""SELECT front_code, client_code, tier, est_value, readiness, next_step, label
                    FROM v_profit_frontboard {where}
                    {'AND' if where else 'WHERE'} COALESCE(near_term_cash,0)=0 AND est_value IS NOT NULL AND est_value>0
                    ORDER BY est_value DESC LIMIT 8""", params)
    hold = cur.fetchall()
    if hold:
        print("\n  " + "-" * 94)
        print("  LONG-RUN VALUE (held/recover — real value, no near-term cash until recovered/sold):")
        for r in hold:
            print(f"    {_peso(r['est_value']):>13}  {(r['tier'] or '-'):<12} {r['front_code']:<18} "
                  f"{(r['label'] or '')[:40]}  [{r['client_code']}]")

    # 3) value unknown
    cur.execute(f"""SELECT count(*) AS n, count(*) FILTER (WHERE needs_valuation) AS needs
                    FROM v_profit_frontboard {where}
                    {'AND' if where else 'WHERE'} near_term_cash IS NULL""", params)
    u = cur.fetchone()
    print("\n  VALUE UNKNOWN: "
          f"{u['n']} fronts carry no value/income ({u['needs']} need valuation) — not yet rankable.")
    print("=" * 98)
    cur.close(); c.close()


if __name__ == "__main__":
    main()
