#!/usr/bin/env python3
"""Roll up active tax declarations per case (deploy 118-C).

Identifies the LATEST tax dec per (case, lot/PIN) and computes:
  - Active tax dec count per case
  - Total assessed + market value
  - Annual RPT obligation estimate (assessed × 2% rate, typical for residential)
  - Per-tax-dec payment history (matched transactions)
  - Delinquency status

Writes:
  - asset_valuations.is_active_tax_dec column update
  - Telegram digest of MWK-001 active tax decs
"""
import argparse
from datetime import date
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # For each (case, tax_dec_no), keep the row with LATEST snapshot_date
    # (or asset_title-anchored row if tax_dec_no is NULL)
    cur.execute("""
        WITH latest AS (
          SELECT DISTINCT ON (COALESCE(tax_dec_no, asset_title))
                 id, asset_title, tax_dec_no, area_sqm,
                 assessed_value, market_price_value, current_use,
                 source_docs, snapshot_date
            FROM asset_valuations
           WHERE case_file=%s AND (assessed_value > 0 OR market_price_value > 0)
           ORDER BY COALESCE(tax_dec_no, asset_title), snapshot_date DESC
        )
        SELECT * FROM latest ORDER BY assessed_value DESC NULLS LAST
    """, (args.case,))
    active = cur.fetchall()

    # PH RPT rate: typically 1-2% of assessed value annually (varies by LGU)
    # Mercedes/Camarines Norte: ~2% basic + ~1% SEF = 3% effective
    RPT_RATE = 0.03

    total_assessed = sum(float(r["assessed_value"] or 0) for r in active)
    total_market = sum(float(r["market_price_value"] or 0) for r in active)
    annual_rpt_est = total_assessed * RPT_RATE

    # Match payment transactions to tax decs (per asset)
    cur.execute("""
        SELECT source_tx_ref, tx_date, amount, source_doc_id, description
          FROM transactions
         WHERE case_file=%s AND category IN ('rpt')
         ORDER BY tx_date DESC
    """, (args.case,))
    payments = cur.fetchall()
    total_paid = sum(float(p["amount"] or 0) for p in payments)

    # Print summary
    print(f"\n  Case: {args.case}")
    print(f"  Active tax declarations: {len(active)}  ⚠️ PROVISIONAL — overcounts (target ~20 for MWK)")
    print(f"  → True canonical MWK count is ~20 (T-4497 + T-32916 + T-32917 + T-31298 + 17 sub-derivs).")
    print(f"  → Distortion: tax decs of conveyed-away lots (Iligan, Santiago, Pascual et al.) + adjacent")
    print(f"    parcels still tagged MWK-001. Fix requires title_chain linkage (Phase 2).")
    print(f"  Total assessed value (PROVISIONAL): ₱{total_assessed:,.0f}")
    print(f"  Total market value (PROVISIONAL):   ₱{total_market:,.0f}")
    print(f"  Annual RPT estimate (PROVISIONAL):  ₱{annual_rpt_est:,.0f} (assessed × {RPT_RATE*100:.0f}%)")
    print(f"  Payments recorded:       {len(payments)} totaling ₱{total_paid:,.0f}")
    print(f"\n  Active tax decs (top 25):")
    for a in active[:25]:
        td = a.get("tax_dec_no") or a.get("asset_title")
        print(f"    {td:30s}  area={a.get('area_sqm') or 0:>7,.0f} sqm  "
              f"assessed=₱{float(a.get('assessed_value') or 0):>12,.0f}  "
              f"market=₱{float(a.get('market_price_value') or 0):>14,.0f}  "
              f"({a.get('current_use') or '—'})")

    # Mark as active in DB
    cur.execute("ALTER TABLE asset_valuations ADD COLUMN IF NOT EXISTS is_active_tax_dec boolean DEFAULT false")
    cur.execute("UPDATE asset_valuations SET is_active_tax_dec = false WHERE case_file = %s", (args.case,))
    for a in active:
        cur.execute("UPDATE asset_valuations SET is_active_tax_dec = true WHERE id = %s", (a["id"],))
    print(f"\n  ✓ flagged {len(active)} rows as is_active_tax_dec=true")

    # Add to monthly_overhead as recurring obligation (replace old estimate)
    monthly_est = annual_rpt_est / 12.0
    cur.execute("""
        DELETE FROM monthly_overhead WHERE case_file=%s AND category='rpt' AND description LIKE 'Estimated annual%%'
    """, (args.case,))
    cur.execute("""
        INSERT INTO monthly_overhead (owner, case_file, category, description, monthly_amount, start_date)
        VALUES (%s, %s, 'rpt',
                %s,
                %s, %s)
        ON CONFLICT DO NOTHING
    """, (args.case, args.case,
          f"[PROVISIONAL — overcounts] Annual RPT across {len(active)} tagged tax decs (target ~20 for MWK); fix requires Phase 2 title_chain linkage. assessed×3%÷12. Provisional annual: ₱{annual_rpt_est:,.0f}",
          monthly_est, date.today().replace(day=1)))
    print(f"  ✓ updated monthly_overhead.rpt = ₱{monthly_est:,.0f}/mo (₱{annual_rpt_est:,.0f}/yr)")

    if args.send_tg:
        import requests, os
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
        lines = [
            f"📋 <b>{args.case} — Active Tax Declarations (Mercedes assessor)</b>",
            "",
            f"<b>{len(active)} active tax decs</b>",
            f"Total assessed: <b>₱{total_assessed:,.0f}</b>",
            f"Total market:   <b>₱{total_market:,.0f}</b>",
            f"Annual RPT est: <b>₱{annual_rpt_est:,.0f}</b> (assessed × 3%)",
            f"Recorded payments to date: <b>{len(payments)} = ₱{total_paid:,.0f}</b>",
            "",
            "<b>Top 15 active tax decs by assessed value:</b>",
        ]
        for a in active[:15]:
            td = a.get("tax_dec_no") or a.get("asset_title")
            assessed = float(a.get("assessed_value") or 0)
            market = float(a.get("market_price_value") or 0)
            area = float(a.get("area_sqm") or 0)
            lines.append(f"  • <code>{td[:30]}</code>  {area:>5,.0f}sqm  ₱{assessed:>10,.0f}"
                         + (f" (mkt ₱{market:>10,.0f})" if market else ""))
        text = "\n".join(lines)
        r = requests.post(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                          json={"chat_id": "6513067717", "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True})
        print(f"\n  TG digest: {r.status_code}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
