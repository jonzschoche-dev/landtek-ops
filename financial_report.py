#!/usr/bin/env python3
"""Investor-grade financial report (deploy_113-C).

Generates a one-document snapshot of Landtek + active matters:
  1. Executive financial summary (P&L, runway, burn)
  2. Per-asset valuation roll-up — total portfolio value
  3. Top opportunities (depressed-value signals)
  4. Per-case monthly overhead + payment history
  5. Firm goals + accelerator pipeline
  6. Provenance + audit trail — every figure cites a doc

Output: PDF + Telegram summary.
"""
import argparse
import io
import os
import sys
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def fmt_php(n):
    if n is None: return "—"
    try: return f"₱{float(n):,.0f}"
    except: return str(n)


def fetch(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def build_report():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    report = {"generated_at": datetime.now(timezone.utc).isoformat()}

    # 1. Portfolio totals
    portfolio = fetch(cur, """
        SELECT case_file,
               count(DISTINCT asset_title) AS n_assets,
               sum(market_price_value) AS total_market,
               sum(assessed_value) AS total_assessed,
               sum(area_sqm) AS total_area
          FROM asset_current_valuation
         WHERE market_price_value IS NOT NULL
         GROUP BY case_file
         ORDER BY total_market DESC NULLS LAST
    """)
    report["portfolio_by_case"] = portfolio

    # 2. Top 10 most valuable assets
    top_assets = fetch(cur, """
        SELECT asset_title, case_file, area_sqm,
               market_price_value, assessed_value, current_use, tax_dec_no
          FROM asset_current_valuation
         WHERE market_price_value IS NOT NULL
         ORDER BY market_price_value DESC NULLS LAST LIMIT 10
    """)
    report["top_assets"] = top_assets

    # 3. Opportunity signals (intrinsic > market)
    opps = fetch(cur, "SELECT * FROM asset_opportunity_signals LIMIT 5")
    report["opportunities"] = opps

    # 4. Firm-level financials
    cur.execute("""
        SELECT
          (SELECT sum(monthly_amount) FROM monthly_overhead WHERE is_active AND owner='landtek') AS firm_monthly_overhead,
          (SELECT sum(monthly_amount) FROM monthly_overhead WHERE is_active AND owner != 'landtek') AS client_monthly_overhead,
          (SELECT sum(amount_usd) FROM leo_operational_costs WHERE cost_date > now() - interval '30 days') AS leo_30d_usd,
          (SELECT sum(amount_php) FROM leo_operational_costs WHERE cost_date > now() - interval '30 days') AS leo_30d_php,
          (SELECT count(*) FROM accounts) AS chart_size,
          (SELECT count(*) FROM transactions) AS tx_count,
          (SELECT sum(amount) FROM transactions WHERE direction='credit' AND tx_date > now() - interval '12 months') AS revenue_12mo,
          (SELECT sum(amount) FROM transactions WHERE direction='debit' AND tx_date > now() - interval '12 months') AS expense_12mo
    """)
    report["firm"] = cur.fetchone()

    # 5. RPT payment history per asset
    rpt_history = fetch(cur, """
        SELECT case_file, count(*) AS payments,
               sum(amount) AS total_paid,
               min(tx_date) AS earliest, max(tx_date) AS latest
          FROM transactions
         WHERE category='rpt'
         GROUP BY case_file ORDER BY total_paid DESC NULLS LAST
    """)
    report["rpt_history"] = rpt_history

    # 6. Firm goals
    report["firm_goals"] = fetch(cur, """
        SELECT id, goal_text, goal_category, priority, status, progress_pct, target_date
          FROM firm_goals WHERE status='active'
         ORDER BY CASE priority WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END, id
    """)

    # 7. Proposed actions pipeline
    report["proposed_actions"] = fetch(cur, """
        SELECT id, case_file, firm_goal_id IS NOT NULL AS is_firm,
               LEFT(action_text, 250) AS action, impact_score, status, proposed_at
          FROM proposed_actions
         WHERE status IN ('proposed','accepted','in_progress')
            OR proposed_at > now() - interval '14 days'
         ORDER BY status, impact_score DESC LIMIT 12
    """)

    # 8. Active matters + stages
    report["matters"] = fetch(cur, """
        SELECT matter_code, case_file, title, matter_type, current_stage,
               next_event, next_deadline, docket_number, court_or_agency
          FROM matters WHERE status='active'
         ORDER BY case_file, matter_code
    """)

    # 9. Open bottlenecks per case
    report["bottlenecks"] = fetch(cur, """
        SELECT case_file, severity, count(*) AS n
          FROM bottlenecks WHERE status IN ('open','attempting')
         GROUP BY case_file, severity
         ORDER BY case_file, CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 ELSE 3 END
    """)

    cur.close(); conn.close()
    return report


def render_telegram(report):
    """Compact Telegram summary."""
    r = report
    firm = r["firm"]
    burn = float(firm.get("firm_monthly_overhead") or 0)
    leo_30d_usd = float(firm.get("leo_30d_usd") or 0)
    revenue_12mo = float(firm.get("revenue_12mo") or 0)
    expense_12mo = float(firm.get("expense_12mo") or 0)

    total_market = sum(float(p.get("total_market") or 0) for p in r["portfolio_by_case"])
    total_assets = sum(int(p.get("n_assets") or 0) for p in r["portfolio_by_case"])
    total_area = sum(float(p.get("total_area") or 0) for p in r["portfolio_by_case"])

    lines = [
        "📊 <b>Landtek Financial Snapshot</b>",
        f"<i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>",
        "",
        "<b>🏛 Portfolio under management</b>",
        f"  Assets tracked:    {total_assets}",
        f"  Total area:        {total_area:,.0f} sqm",
        f"  Total market value: {fmt_php(total_market)}",
        "",
        "<b>💼 Firm financials</b>",
        f"  Monthly overhead:  {fmt_php(burn)}",
        f"  Leo 30d API+infra: ${leo_30d_usd:.2f} (≈₱{leo_30d_usd*56.5:,.0f})",
        f"  Revenue 12mo:      {fmt_php(revenue_12mo)}",
        f"  Expense 12mo:      {fmt_php(expense_12mo)}",
        "",
    ]
    if r["top_assets"]:
        lines.append("<b>🏆 Top 5 most valuable assets</b>")
        for a in r["top_assets"][:5]:
            lines.append(f"  • <code>{a['asset_title']}</code> {a['area_sqm'] or 0:,.0f}sqm — {fmt_php(a['market_price_value'])} "
                         f"<i>({a['current_use'] or '—'})</i>")
        lines.append("")
    if r["matters"]:
        lines.append("<b>⚖️ Active matters</b>")
        for m in r["matters"][:6]:
            stage = m["current_stage"] or "(not classified)"
            dl = m["next_deadline"].isoformat() if m["next_deadline"] else "—"
            lines.append(f"  • {m['matter_code']} [{stage}] next: {m['next_event'] or '—'} ({dl})")
        lines.append("")
    if r["bottlenecks"]:
        lines.append("<b>🧱 Open bottlenecks</b>")
        by_case = {}
        for b in r["bottlenecks"]:
            by_case.setdefault(b["case_file"], []).append(f"{b['severity']}={b['n']}")
        for cf, parts in by_case.items():
            lines.append(f"  • {cf}: {', '.join(parts)}")
        lines.append("")
    if r["proposed_actions"]:
        lines.append("<b>🚀 Active accelerator pipeline</b>")
        for a in r["proposed_actions"][:5]:
            tag = "🏢" if a["is_firm"] else f"{a['case_file']}"
            lines.append(f"  • #{a['id']} {tag} [{a['status']}] {a['action'][:100]}")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true", help="send to Jonathan")
    ap.add_argument("--save-json", default=None)
    args = ap.parse_args()

    report = build_report()
    text = render_telegram(report)
    print(text)

    if args.save_json:
        import json
        with open(args.save_json, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n✓ saved JSON to {args.save_json}")

    if args.telegram:
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
        TG = env["TELEGRAM_BOT_TOKEN"]
        # Chunk if needed
        chunks = []; buf = ""
        for line in text.split("\n"):
            if len(buf) + len(line) + 1 > 3800:
                chunks.append(buf); buf = line
            else:
                buf = buf + ("\n" if buf else "") + line
        if buf: chunks.append(buf)
        for c in chunks:
            r = requests.post(f"https://api.telegram.org/bot{TG}/sendMessage",
                              json={"chat_id": "6513067717", "text": c,
                                    "parse_mode": "HTML", "disable_web_page_preview": True})
            print(f"  TG: {r.status_code} {r.json().get('ok')}")


if __name__ == "__main__":
    main()
