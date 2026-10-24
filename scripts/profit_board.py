#!/usr/bin/env python3
"""profit_board.py — the magnate engine's MONEY board (deploy_1264/1265/1266).

Ranks fronts by EXPECTED NEAR-TERM CASH (~24 mo) and shows the GATES (dated milestones that
unblock the cash) and the now-money lanes still pending valuation. Reads v_profit_frontboard
(property_assets via the readiness engine UNION money_fronts). Uses only DB figures — fabricates
nothing; unquantified lanes show as pending, never as a number.

  near_term_cash = annual_income*2 + one_time_cash   (one_time = est_value*readiness*tier, cash-event only)

  python3 profit_board.py                 # Keesey estate (MWK-001) by default
  python3 profit_board.py --client MWK-001
  python3 profit_board.py --all
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
    show_all = "--all" in args
    client = val("--client") or (None if show_all else "MWK-001")
    limit = int(val("--limit") or 20)

    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cond, params = [], []
    if client:
        cond.append("client_code = %s"); params.append(client)
    W = ("WHERE " + " AND ".join(cond)) if cond else ""
    AND = "AND" if W else "WHERE"

    scope = client or "all clients"
    print("=" * 98)
    print(f"MONEY BOARD — near-term cash, gates & lanes    scope: {scope}")
    print("=" * 98)

    # A) ranked near-term cash
    cur.execute(f"SELECT * FROM v_profit_frontboard {W} {AND} near_term_cash>0 "
                f"ORDER BY near_term_cash DESC LIMIT %s", (*params, limit))
    cash = cur.fetchall()
    print("\n[1] NEAR-TERM CASH (ranked)  = 2×annual income + one-time (judgment/sale × readiness × tier)")
    print("  " + "-" * 94)
    for i, r in enumerate(cash, 1):
        gate = f"  ⛔ gated: {r['gate']} — {r['gate_date']}" if r.get("gate_date") else ""
        print(f"  {i:>2}  {_peso(r['near_term_cash']):>13}  {(r['tier'] or '-'):<10} rdy={r['readiness']}  "
              f"{r['front_code']}{gate}")
        print(f"      └ {(r['label'] or '')[:66]}")
        if r.get("next_step"):
            print(f"        next: {r['next_step'][:82]}")
    if not cash:
        print("  (none with quantified near-term cash yet)")

    # B) gates / timeline
    cur.execute(f"SELECT * FROM v_profit_frontboard {W} {AND} front_type='gate' "
                f"ORDER BY gate_date NULLS LAST", params)
    gates = cur.fetchall()
    if gates:
        print("\n[2] GATES / TIMELINE (dated milestones that unblock the cash)")
        print("  " + "-" * 94)
        for g in gates:
            print(f"  📅 {str(g['gate_date'] or 'TBD'):<12} {g['front_code']}  (rdy={g['readiness']})")
            print(f"      └ {(g['label'] or '')[:72]}")
            if g.get("next_step"):
                print(f"        next: {g['next_step'][:82]}")
            if g.get("unblocks"):
                print(f"        unblocks: {g['unblocks'][:78]}")

    # C) now-money lanes pending valuation (curated money_fronts, no number yet)
    cur.execute(f"SELECT * FROM v_profit_frontboard {W} {AND} source='money_front' "
                f"AND front_type<>'gate' AND near_term_cash IS NULL ORDER BY readiness DESC", params)
    lanes = cur.fetchall()
    if lanes:
        print("\n[3] NOW-MONEY LANES — pending valuation (visible, not fabricated)")
        print("  " + "-" * 94)
        for r in lanes:
            flag = "no guardianship gate" if not r.get("gate_date") else f"gated {r['gate_date']}"
            print(f"  ○ {r['front_code']}  rdy={r['readiness']}  [{flag}]")
            print(f"      └ {(r['label'] or '')[:72]}")
            if r.get("next_step"):
                print(f"        next: {r['next_step'][:82]}")

    # D) long-run held value
    cur.execute(f"SELECT * FROM v_profit_frontboard {W} {AND} COALESCE(near_term_cash,0)=0 "
                f"AND front_type<>'gate' AND est_value>0 ORDER BY est_value DESC LIMIT 8", params)
    hold = cur.fetchall()
    if hold:
        print("\n[4] LONG-RUN VALUE (held/recover — real value, no near-term cash until recovered/sold)")
        print("  " + "-" * 94)
        for r in hold:
            print(f"  {_peso(r['est_value']):>13}  {(r['tier'] or '-'):<12} {r['front_code']:<18} "
                  f"{(r['label'] or '')[:38]}")

    # E) value unknown property
    cur.execute(f"SELECT count(*) n, count(*) FILTER (WHERE needs_valuation) needs "
                f"FROM v_profit_frontboard {W} {AND} source='property' AND near_term_cash IS NULL", params)
    u = cur.fetchone()
    print(f"\n[5] VALUE UNKNOWN: {u['n']} property fronts carry no value ({u['needs']} need valuation).")
    print("=" * 98)
    cur.close(); c.close()


if __name__ == "__main__":
    main()
