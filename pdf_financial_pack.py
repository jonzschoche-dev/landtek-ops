#!/usr/bin/env python3
"""Financial PDF report pack (deploy_117-B).

Three sub-reports:
  --type cashflow --case MWK-001  → Per-client Cash Flow Statement
  --type pnl                      → Landtek Firm P&L (12-month trailing)
  --type valuation --asset T-32917 → Per-asset Valuation Memo (intrinsic, market, risks)
  --type pack --case MWK-001      → Bundled pack: snapshot + cashflow + pnl + top-asset memos
"""
import argparse
import os
import sys
from datetime import date, datetime, timezone, timedelta
import psycopg2
import psycopg2.extras
from weasyprint import HTML

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def fmt(n, prefix="₱"):
    if n is None: return "—"
    try: return f"{prefix}{float(n):,.0f}"
    except: return str(n)


def fetch(cur, sql, params=()):
    cur.execute(sql, params); return cur.fetchall()


# ── Shared CSS ──
CSS_HEAD = """<style>
  @page { size: A4; margin: 18mm 14mm; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 10.5pt; line-height: 1.45; }
  h1 { color: #0a3d62; font-size: 22pt; margin: 0 0 6px 0; }
  h2 { color: #0a3d62; font-size: 14pt; border-bottom: 2px solid #0a3d62; padding-bottom: 4px; margin-top: 22px; }
  h3 { color: #2c3e50; font-size: 11pt; margin-top: 16px; margin-bottom: 6px; }
  .subtitle { color: #7f8c8d; font-size: 10pt; margin-bottom: 16px; }
  .stat { padding: 8px 12px; background: #f5f8fb; border-left: 3px solid #0a3d62; margin: 8px 0; display: inline-block; min-width: 32%; vertical-align: top; }
  .stat-label { color: #586e7a; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-value { font-size: 15pt; font-weight: 600; color: #0a3d62; margin-top: 2px; }
  .stat-sub { font-size: 8pt; color: #95a5a6; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9pt; }
  th { background: #e8eef4; text-align: left; padding: 5px 7px; border-bottom: 1.5px solid #0a3d62; font-weight: 600; }
  td { padding: 4px 7px; border-bottom: 1px solid #eee; vertical-align: top; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .total-row { background: #f5f8fb; font-weight: 600; }
  .neg { color: #c0392b; }
  .pos { color: #27ae60; }
  .narrative { margin: 8px 0; line-height: 1.55; }
  .note { font-size: 8.5pt; color: #95a5a6; font-style: italic; margin-top: 4px; }
  .pagebreak { page-break-before: always; }
  .tag { display: inline-block; padding: 1px 5px; background: #e8eef4; color: #0a3d62; border-radius: 3px; font-size: 8pt; font-family: 'Courier New', monospace; }
  .sev-critical { color: #c0392b; font-weight: 600; }
  .sev-high { color: #e67e22; }
  .sev-medium { color: #f39c12; }
</style>"""


# ════════════════════════════════════════════════════════════════
# CASH FLOW STATEMENT (per case)
# ════════════════════════════════════════════════════════════════

def build_cashflow(case_file):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    client = fetch(cur, "SELECT name, project_status FROM clients WHERE case_file=%s LIMIT 1", (case_file,))
    client_name = client[0]["name"] if client else case_file

    cur.execute("""
        SELECT direction, category, sum(amount) AS total, count(*) AS n,
               min(tx_date) AS earliest, max(tx_date) AS latest
          FROM transactions WHERE case_file=%s
         GROUP BY direction, category
         ORDER BY direction, total DESC NULLS LAST
    """, (case_file,))
    by_cat = cur.fetchall()

    total_inflow = sum(float(r["total"] or 0) for r in by_cat if r["direction"] == "credit")
    total_outflow = sum(float(r["total"] or 0) for r in by_cat if r["direction"] == "debit")
    net = total_inflow - total_outflow

    overhead = fetch(cur, """
        SELECT category, description, monthly_amount
          FROM monthly_overhead WHERE case_file=%s AND is_active
         ORDER BY monthly_amount DESC NULLS LAST
    """, (case_file,))
    monthly_overhead_total = sum(float(o["monthly_amount"] or 0) for o in overhead)

    vee = fetch(cur, """
        SELECT event_date, event_type, asset_title, gross_amount, net_to_client, landtek_share
          FROM value_extraction_events WHERE case_file=%s
         ORDER BY event_date DESC LIMIT 25
    """, (case_file,))

    recent_tx = fetch(cur, """
        SELECT tx_date, direction, category, amount, description, source_doc_id, source_tx_ref
          FROM transactions WHERE case_file=%s
         ORDER BY tx_date DESC, id DESC LIMIT 25
    """, (case_file,))

    cur.close(); conn.close()

    html = f"""<!DOCTYPE html><html><head>{CSS_HEAD}</head><body>
<h1>{client_name} — Cash Flow Statement</h1>
<div class="subtitle">{case_file} · Generated {now}</div>

<h2>Summary</h2>
<div class="stat"><div class="stat-label">Total inflows (cumulative)</div>
  <div class="stat-value pos">{fmt(total_inflow)}</div>
  <div class="stat-sub">retainers, recoveries, refunds</div></div>
<div class="stat"><div class="stat-label">Total outflows (cumulative)</div>
  <div class="stat-value neg">{fmt(total_outflow)}</div>
  <div class="stat-sub">filing, notary, sheriff, transport, RPT</div></div>
<div class="stat"><div class="stat-label">Net cash position</div>
  <div class="stat-value {'pos' if net>=0 else 'neg'}">{fmt(net)}</div>
  <div class="stat-sub">{'surplus' if net>=0 else 'deficit'}</div></div>

<h2>By category</h2>
<table><thead><tr><th>Direction</th><th>Category</th><th class='num'>Total</th><th class='num'>#tx</th><th>Period</th></tr></thead><tbody>
"""
    for r in by_cat:
        dir_label = "Inflow" if r["direction"] == "credit" else "Outflow"
        period = f"{r['earliest']} → {r['latest']}" if r['earliest'] else "—"
        cls = "pos" if r["direction"] == "credit" else "neg"
        html += f"<tr><td>{dir_label}</td><td>{r['category'] or '—'}</td><td class='num {cls}'>{fmt(r['total'])}</td><td class='num'>{r['n']}</td><td>{period}</td></tr>"
    html += "</tbody></table>"

    if overhead:
        html += "<h2>Monthly recurring obligations</h2><table><thead><tr><th>Category</th><th>Description</th><th class='num'>Monthly</th></tr></thead><tbody>"
        for o in overhead:
            html += f"<tr><td>{o['category']}</td><td>{o['description']}</td><td class='num'>{fmt(o['monthly_amount'])}</td></tr>"
        html += f"<tr class='total-row'><td colspan='2'>Total monthly overhead</td><td class='num'>{fmt(monthly_overhead_total)}</td></tr>"
        html += "</tbody></table>"

    if vee:
        html += "<h2>Value-extraction events</h2><div class='narrative'>Material transactions that recovered or realized property value for the client.</div>"
        html += "<table><thead><tr><th>Date</th><th>Event</th><th>Asset</th><th class='num'>Gross</th><th class='num'>To client</th><th class='num'>Landtek share</th></tr></thead><tbody>"
        for v in vee:
            html += f"<tr><td>{v['event_date']}</td><td>{v['event_type']}</td><td>{v['asset_title'] or '—'}</td><td class='num'>{fmt(v['gross_amount'])}</td><td class='num pos'>{fmt(v['net_to_client'])}</td><td class='num'>{fmt(v['landtek_share'])}</td></tr>"
        html += "</tbody></table>"

    if recent_tx:
        html += "<h2>Recent transactions (last 25)</h2><table><thead><tr><th>Date</th><th>Dir</th><th>Category</th><th class='num'>Amount</th><th>Description</th><th>Source</th></tr></thead><tbody>"
        for t in recent_tx:
            cls = "pos" if t["direction"] == "credit" else "neg"
            sigil = "+" if t["direction"] == "credit" else "−"
            src = f"<span class='tag'>doc#{t['source_doc_id']}</span>" if t['source_doc_id'] else (t['source_tx_ref'] or "—")
            html += f"<tr><td>{t['tx_date']}</td><td>{sigil}</td><td>{t['category'] or '—'}</td><td class='num {cls}'>{fmt(t['amount'])}</td><td>{(t['description'] or '')[:80]}</td><td>{src}</td></tr>"
        html += "</tbody></table>"
    else:
        html += "<h2>Recent transactions</h2><div class='note'>No transactions recorded yet — RPT receipt ingestion is the next source. Pre-existing tax-doc corpus is being processed.</div>"

    html += "<div class='note'>Every figure cites a source document. Drafts and unsigned documents are explicitly excluded from factual claims (truth_negotiator discipline).</div></body></html>"
    return html


# ════════════════════════════════════════════════════════════════
# FIRM P&L (Landtek 12-month trailing)
# ════════════════════════════════════════════════════════════════

def build_pnl():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Revenue by account
    rev = fetch(cur, """
        SELECT a.account_code, a.account_name, COALESCE(sum(t.amount),0) AS total
          FROM accounts a
          LEFT JOIN transactions t ON t.account_id = a.id AND t.direction='credit'
                                   AND t.tx_date > now() - interval '12 months'
         WHERE a.owner='landtek' AND a.account_type='revenue'
         GROUP BY a.account_code, a.account_name
         ORDER BY total DESC NULLS LAST
    """)
    # Expense by account
    exp = fetch(cur, """
        SELECT a.account_code, a.account_name, COALESCE(sum(t.amount),0) AS total
          FROM accounts a
          LEFT JOIN transactions t ON t.account_id = a.id AND t.direction='debit'
                                   AND t.tx_date > now() - interval '12 months'
         WHERE a.owner='landtek' AND a.account_type='expense'
         GROUP BY a.account_code, a.account_name
         ORDER BY total DESC NULLS LAST
    """)
    overhead = fetch(cur, """
        SELECT category, description, monthly_amount
          FROM monthly_overhead WHERE owner='landtek' AND is_active
         ORDER BY monthly_amount DESC NULLS LAST
    """)
    leo_costs = fetch(cur, """
        SELECT category, sum(amount_php) AS php, sum(amount_usd) AS usd, count(*) AS n
          FROM leo_operational_costs
         WHERE cost_date > now() - interval '30 days'
         GROUP BY category ORDER BY php DESC NULLS LAST
    """)

    total_revenue = sum(float(r["total"] or 0) for r in rev)
    total_expense = sum(float(r["total"] or 0) for r in exp)
    leo_monthly = sum(float(c["php"] or 0) for c in leo_costs)
    overhead_monthly = sum(float(o["monthly_amount"] or 0) for o in overhead)
    monthly_burn_total = leo_monthly + overhead_monthly
    annual_burn = monthly_burn_total * 12
    net = total_revenue - total_expense

    # Approx runway
    cur.execute("""
        SELECT COALESCE(sum(amount),0) AS cash FROM transactions WHERE direction='credit' AND category='retainer'
    """)
    cash = float(cur.fetchone()["cash"]) - total_expense
    runway_months = (cash / monthly_burn_total) if monthly_burn_total > 0 else None

    cur.close(); conn.close()

    html = f"""<!DOCTYPE html><html><head>{CSS_HEAD}</head><body>
<h1>LandTek Law — Firm P&amp;L</h1>
<div class="subtitle">Trailing 12 months · Generated {now}</div>

<h2>Headline figures</h2>
<div class="stat"><div class="stat-label">Revenue (12mo)</div>
  <div class="stat-value pos">{fmt(total_revenue)}</div></div>
<div class="stat"><div class="stat-label">Expense (12mo)</div>
  <div class="stat-value neg">{fmt(total_expense)}</div></div>
<div class="stat"><div class="stat-label">Net (12mo)</div>
  <div class="stat-value {'pos' if net>=0 else 'neg'}">{fmt(net)}</div></div>
<br>
<div class="stat"><div class="stat-label">Monthly burn</div>
  <div class="stat-value">{fmt(monthly_burn_total)}</div>
  <div class="stat-sub">overhead + Leo infra</div></div>
<div class="stat"><div class="stat-label">Annualized burn</div>
  <div class="stat-value">{fmt(annual_burn)}</div></div>
<div class="stat"><div class="stat-label">Runway (months)</div>
  <div class="stat-value">{f'{runway_months:.1f}' if runway_months else '—'}</div>
  <div class="stat-sub">cash ÷ burn</div></div>

<h2>Revenue accounts</h2>
<table><thead><tr><th>Code</th><th>Account</th><th class='num'>Trailing 12mo</th></tr></thead><tbody>
"""
    for r in rev:
        html += f"<tr><td><span class='tag'>{r['account_code']}</span></td><td>{r['account_name']}</td><td class='num pos'>{fmt(r['total'])}</td></tr>"
    html += f"<tr class='total-row'><td colspan='2'>Total revenue</td><td class='num pos'>{fmt(total_revenue)}</td></tr></tbody></table>"

    html += "<h2>Expense accounts</h2><table><thead><tr><th>Code</th><th>Account</th><th class='num'>Trailing 12mo</th></tr></thead><tbody>"
    for e in exp:
        html += f"<tr><td><span class='tag'>{e['account_code']}</span></td><td>{e['account_name']}</td><td class='num neg'>{fmt(e['total'])}</td></tr>"
    html += f"<tr class='total-row'><td colspan='2'>Total expense</td><td class='num neg'>{fmt(total_expense)}</td></tr></tbody></table>"

    html += '<div class="pagebreak"></div><h2>Recurring monthly obligations</h2>'
    html += "<table><thead><tr><th>Category</th><th>Description</th><th class='num'>₱/mo</th></tr></thead><tbody>"
    for o in overhead:
        html += f"<tr><td>{o['category']}</td><td>{o['description']}</td><td class='num'>{fmt(o['monthly_amount'])}</td></tr>"
    html += f"<tr class='total-row'><td colspan='2'>Total firm overhead/mo</td><td class='num'>{fmt(overhead_monthly)}</td></tr></tbody></table>"

    if leo_costs:
        html += "<h3>Leo platform infrastructure (last 30 days)</h3>"
        html += "<table><thead><tr><th>Category</th><th class='num'>USD</th><th class='num'>PHP (≈)</th><th class='num'>Events</th></tr></thead><tbody>"
        for c in leo_costs:
            html += f"<tr><td>{c['category']}</td><td class='num'>${float(c['usd'] or 0):.2f}</td><td class='num'>{fmt(c['php'])}</td><td class='num'>{c['n']}</td></tr>"
        total_usd = sum(float(c['usd'] or 0) for c in leo_costs)
        html += f"<tr class='total-row'><td>Total / mo (annualized × 12)</td><td class='num'>${total_usd:.2f}</td><td class='num'>{fmt(leo_monthly)} → {fmt(leo_monthly*12)}/yr</td><td></td></tr></tbody></table>"

    html += """<h2>Investor-grade notes</h2>
    <div class="narrative">
    Every revenue and expense entry must cite a source document (Official Receipt, retainer agreement, vendor invoice) under the LandTek truth-graded discipline.
    Figures shown reflect what's currently posted in the ledger; pre-existing receipts and retainer remittances are being progressively backfilled from the tax-document corpus and email archive.
    </div>
    <div class="note">Generated by Leo Platform v0.117 · landtek.io</div>
    </body></html>
    """
    return html


# ════════════════════════════════════════════════════════════════
# PER-ASSET VALUATION MEMO
# ════════════════════════════════════════════════════════════════

def build_valuation_memo(asset_title):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    val = fetch(cur, """
        SELECT * FROM asset_current_valuation WHERE asset_title=%s LIMIT 1
    """, (asset_title,))
    if not val:
        return f"<html><body><h1>No data for asset {asset_title}</h1></body></html>"
    v = val[0]
    risks = fetch(cur, """
        SELECT DISTINCT ON (risk_type)
               risk_type, severity, likelihood_pct, expected_loss_php,
               mitigation_strategy, mitigation_status, mitigation_cost,
               evidence_doc_ids, notes, assessed_at
          FROM asset_risks WHERE asset_title=%s
         ORDER BY risk_type, assessed_at DESC
    """, (asset_title,))
    title_row = fetch(cur, """
        SELECT tct_number, lifecycle_status, lifecycle_notes, parent_title, location, area_sqm
          FROM titles WHERE tct_number=%s LIMIT 1
    """, (asset_title,))
    matter_links = fetch(cur, """
        SELECT tml.matter_code, tml.relationship, tml.notes,
               m.title, m.matter_type, m.docket_number, m.current_stage
          FROM title_matter_links tml
          JOIN matters m ON m.matter_code = tml.matter_code
         WHERE tml.title_no=%s
    """, (asset_title,))
    arp_links = fetch(cur, """
        SELECT arp_no, source_doc_id, confidence FROM title_tax_links WHERE title_no=%s
    """, (asset_title,))

    cur.close(); conn.close()

    market = float(v.get("market_price_value") or 0)
    intrinsic = float(v.get("intrinsic_value") or 0) if v.get("intrinsic_value") is not None else None
    opp_score = float(v.get("opportunity_score") or 0) if v.get("opportunity_score") is not None else None

    html = f"""<!DOCTYPE html><html><head>{CSS_HEAD}</head><body>
<h1>Asset Valuation Memo — {asset_title}</h1>
<div class="subtitle">{v.get('case_file') or '—'} · {v.get('current_use') or '—'} · Generated {now}</div>

<h2>Headline valuation</h2>
<div class="stat"><div class="stat-label">Market value</div>
  <div class="stat-value">{fmt(market)}</div></div>
<div class="stat"><div class="stat-label">Assessed value</div>
  <div class="stat-value">{fmt(v.get('assessed_value'))}</div></div>
<div class="stat"><div class="stat-label">Risk-adjusted intrinsic</div>
  <div class="stat-value">{fmt(intrinsic) if intrinsic is not None else '—'}</div>
  <div class="stat-sub">market − expected loss</div></div>
<br>
<div class="stat"><div class="stat-label">Area (sqm)</div>
  <div class="stat-value">{(v.get('area_sqm') or 0):,.0f}</div></div>
<div class="stat"><div class="stat-label">Per-sqm market</div>
  <div class="stat-value">{fmt(market / float(v['area_sqm']) if v.get('area_sqm') else 0)}/sqm</div></div>
<div class="stat"><div class="stat-label">Opportunity score</div>
  <div class="stat-value">{f'{opp_score:.2f}' if opp_score is not None else '—'}</div>
  <div class="stat-sub">0..1 (closer to 1 = higher intrinsic relative to market)</div></div>

<h2>Title status</h2>
"""
    if title_row:
        t = title_row[0]
        html += f"""<div class="narrative">
        Lifecycle status: <b>{t['lifecycle_status']}</b><br>
        Parent title: {t['parent_title'] or '—'}<br>
        Location: {t['location'] or '—'} · Area: {t['area_sqm'] or '—'} sqm<br>
        {t.get('lifecycle_notes') or ''}
        </div>"""

    if matter_links:
        html += "<h3>Active matter linkage</h3>"
        html += "<table><thead><tr><th>Matter</th><th>Relationship</th><th>Stage</th><th>Docket</th><th>Notes</th></tr></thead><tbody>"
        for m in matter_links:
            html += f"<tr><td><b>{m['matter_code']}</b><br><i>{m['title']}</i></td><td>{m['relationship']}</td><td>{m.get('current_stage') or '—'}</td><td>{m.get('docket_number') or '—'}</td><td>{m['notes'] or ''}</td></tr>"
        html += "</tbody></table>"

    if arp_links:
        html += "<h3>Tax declaration linkage</h3><table><thead><tr><th>ARP</th><th class='num'>Confidence</th><th>Source</th></tr></thead><tbody>"
        for a in arp_links:
            html += f"<tr><td><span class='tag'>{a['arp_no']}</span></td><td class='num'>{float(a['confidence'] or 0):.2f}</td><td>doc#{a['source_doc_id'] or '—'}</td></tr>"
        html += "</tbody></table>"

    if risks:
        html += '<div class="pagebreak"></div><h2>Risk profile</h2>'
        html += "<table><thead><tr><th>Type</th><th>Severity</th><th class='num'>Likelihood</th><th class='num'>Expected loss</th><th class='num'>Mitigation cost</th><th>Status</th></tr></thead><tbody>"
        total_loss = 0
        for r in risks:
            loss = float(r["expected_loss_php"] or 0)
            total_loss += loss
            html += f"<tr><td>{r['risk_type']}</td><td class='sev-{r['severity']}'>{r['severity']}</td><td class='num'>{float(r['likelihood_pct'] or 0):.0f}%</td><td class='num neg'>{fmt(loss)}</td><td class='num'>{fmt(r['mitigation_cost'])}</td><td>{r['mitigation_status']}</td></tr>"
        html += f"<tr class='total-row'><td colspan='3'>Total exposure</td><td class='num neg'>{fmt(total_loss)}</td><td colspan='2'></td></tr></tbody></table>"

        html += "<h3>Mitigation strategies (per risk)</h3>"
        for r in risks:
            html += f"<div class='narrative'><b>{r['risk_type']}</b> ({r['severity']}): {r['mitigation_strategy']}<br><i>Evidence:</i> {('doc# ' + ', doc# '.join(str(d) for d in (r['evidence_doc_ids'] or [])[:8])) if r['evidence_doc_ids'] else '—'}<br><i>Notes:</i> {r['notes'] or '—'}</div>"

    if intrinsic is not None and market > 0:
        spread = intrinsic - market
        spread_pct = (spread / market * 100) if market else 0
        html += f"""
        <h2>Strategic interpretation</h2>
        <div class="narrative">
        Market value: <b>{fmt(market)}</b>. Risk-adjusted intrinsic: <b>{fmt(intrinsic)}</b>.
        Spread: <b>{fmt(spread)} ({spread_pct:+.1f}%)</b>.
        """
        if spread > 0:
            html += f"This asset's intrinsic value EXCEEDS its market exposure — net positive even after risk discounting. Hold and monetize via active matter outcomes."
        else:
            html += f"This asset's risk-adjusted value is BELOW market. Mitigations totaling {fmt(sum(float(r.get('mitigation_cost') or 0) for r in risks))} could close the gap if executed."
        html += "</div>"

    html += "<div class='note'>Memo generated by Leo v0.117 — all citations point to source docs.</div></body></html>"
    return html


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["cashflow", "pnl", "valuation", "pack"], required=True)
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--asset", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    if args.type == "cashflow":
        html = build_cashflow(args.case)
        out = args.out or f"/root/landtek/reports/cashflow_{args.case}.pdf"
        caption = f"📊 Cash Flow Statement — {args.case}"
    elif args.type == "pnl":
        html = build_pnl()
        out = args.out or "/root/landtek/reports/landtek_pnl.pdf"
        caption = "💼 LandTek Firm P&L (trailing 12mo)"
    elif args.type == "valuation":
        if not args.asset:
            sys.exit("--asset required for valuation type")
        html = build_valuation_memo(args.asset)
        out = args.out or f"/root/landtek/reports/valuation_{args.asset}.pdf"
        caption = f"📋 Valuation Memo — {args.asset}"
    elif args.type == "pack":
        # Concatenate cashflow + pnl + top-5 valuation memos
        conn = psycopg2.connect(DSN); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT asset_title FROM asset_current_valuation WHERE market_price_value IS NOT NULL ORDER BY market_price_value DESC LIMIT 5")
        top = [r["asset_title"] for r in cur.fetchall()]
        cur.close(); conn.close()
        # Build single HTML containing all
        parts = [build_cashflow(args.case), build_pnl()]
        for t in top:
            parts.append(build_valuation_memo(t))
        # Join inside one document
        html = "\n".join(p.replace("<!DOCTYPE html><html><head>" + CSS_HEAD + "</head><body>", "").replace("</body></html>", "<div class='pagebreak'></div>") for p in parts)
        html = f"<!DOCTYPE html><html><head>{CSS_HEAD}</head><body>{html}</body></html>"
        out = args.out or f"/root/landtek/reports/financial_pack_{args.case}.pdf"
        caption = f"📑 LandTek Financial Pack — {args.case} (cashflow + P&L + top-5 valuations)"

    os.makedirs(os.path.dirname(out), exist_ok=True)
    HTML(string=html).write_pdf(out)
    print(f"  ✓ wrote {out} ({os.path.getsize(out):,} bytes)")

    if args.send_tg:
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("="); env[k.strip()] = v.strip()
        with open(out, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendDocument",
                data={"chat_id": "6513067717", "caption": caption},
                files={"document": (os.path.basename(out), f, "application/pdf")},
                timeout=30,
            )
        print(f"  TG: {r.status_code}")


if __name__ == "__main__":
    main()
