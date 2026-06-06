#!/usr/bin/env python3
"""Seed the financial baseline (deploy_113-A backfill).

- Chart of accounts (Landtek firm + MWK-001 client)
- Best-estimate monthly_overhead (Leo infra costs, firm operating costs)
- Best-estimate leo_operational_costs for the last 30 days
- Asset_valuations skeletons for the major MWK-001 titles (TBD figures)

These are inferred_strong placeholders — every figure marked
provenance_level='inferred_strong' until Jonathan confirms or sources are
cited. NO claim is presented as verified until backed by a doc.
"""
import psycopg2
from datetime import date, timedelta

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# --- Chart of accounts ----------------------------------------------------
CHART = [
    # Landtek firm-level
    ("LT-REV-RETAINER",   "Retainer Revenue",                  "revenue", "landtek", None),
    ("LT-REV-SUCCESS",    "Success Fees / Contingency",        "revenue", "landtek", None),
    ("LT-REV-ADVISORY",   "Advisory Fees",                     "revenue", "landtek", None),
    ("LT-REV-PRODUCT",    "Leo Platform Licensing (future)",   "revenue", "landtek", None),
    ("LT-EXP-API",        "LLM API spend (Anthropic/Gemini)",  "expense", "landtek", None),
    ("LT-EXP-SERVER",     "VPS + Server costs",                "expense", "landtek", None),
    ("LT-EXP-SOFTWARE",   "Software & SaaS subscriptions",     "expense", "landtek", None),
    ("LT-EXP-SALARY",     "Salaries / Counsel fees",           "expense", "landtek", None),
    ("LT-EXP-OFFICE",     "Office / Rent / Utilities",         "expense", "landtek", None),
    ("LT-EXP-TRAVEL",     "Travel & transport",                "expense", "landtek", None),
    ("LT-EXP-FILING",     "Filing fees + court costs",         "expense", "landtek", None),
    ("LT-EXP-NOTARY",     "Notarial fees",                     "expense", "landtek", None),
    ("LT-EXP-MISC",       "Miscellaneous operating",           "expense", "landtek", None),
    ("LT-ASSET-CASH",     "Cash on hand",                      "asset",   "landtek", None),
    ("LT-ASSET-AR",       "Accounts receivable",               "asset",   "landtek", None),
    ("LT-LIAB-AP",        "Accounts payable",                  "liability","landtek", None),
    ("LT-EQUITY-FOUNDER", "Founder's equity",                  "equity",  "landtek", None),

    # MWK-001 client-side
    ("MWK-EXP-RPT",       "Real Property Tax (MWK-001)",           "expense", "MWK-001", "MWK-001"),
    ("MWK-EXP-FILING",    "Filing fees for MWK matters",           "expense", "MWK-001", "MWK-001"),
    ("MWK-EXP-NOTARY",    "Notarial fees for MWK",                 "expense", "MWK-001", "MWK-001"),
    ("MWK-EXP-PROFLEGAL", "Professional legal fees paid",          "expense", "MWK-001", "MWK-001"),
    ("MWK-EXP-TRAVEL",    "Travel for MWK matters",                "expense", "MWK-001", "MWK-001"),
    ("MWK-EXP-MISC",      "Other MWK expenses",                    "expense", "MWK-001", "MWK-001"),
    ("MWK-REV-RECOVERY",  "Recovered amounts (settlements/sales)", "revenue", "MWK-001", "MWK-001"),
    ("MWK-REV-RENT",      "Rental income from MWK assets",         "revenue", "MWK-001", "MWK-001"),
    ("MWK-ASSET-LAND",    "Land assets under MWK-001",             "asset",   "MWK-001", "MWK-001"),
]

# --- Monthly overhead estimates ------------------------------------------
# These are Jonathan-confirmable starting points. Marked as estimates.
OVERHEAD = [
    ("landtek", None, "api_anthropic",  "Anthropic API (Claude Opus/Sonnet/Haiku)", 8000.00),
    ("landtek", None, "api_gemini",     "Gemini API (vision OCR)",                   1000.00),
    ("landtek", None, "server",         "VPS hosting (this server)",                 1500.00),
    ("landtek", None, "software",       "Software subscriptions (misc)",             500.00),
    ("MWK-001", "MWK-001", "rpt",       "Estimated annual RPT (divided by 12)",      5000.00),
]

# --- Leo operational costs — last 30 days estimate -----------------------
# Anthropic dashboard shows real numbers in production; this is a placeholder.
LEO_COSTS_30D = [
    # (days_back, category, amount_usd, units, notes)
    (1, "anthropic_api", 0.50, 50000,  "Haiku — extraction + synthesis"),
    (2, "anthropic_api", 1.20, 80000,  "Sonnet — case_report synthesis"),
    (3, "anthropic_api", 0.30, 30000,  "Haiku — chunk extraction"),
    (5, "anthropic_api", 2.00, 100000, "Sonnet — large educate_leo batches"),
    (7, "anthropic_api", 1.80, 90000,  "Opus + Sonnet — deploy work"),
    (10, "anthropic_api", 0.40, 40000, "Haiku — daily learning"),
    (15, "anthropic_api", 0.60, 60000, "Sonnet — case_report"),
    (20, "anthropic_api", 1.10, 70000, "Haiku — extraction"),
    (25, "anthropic_api", 0.90, 50000, "Haiku — synthesis"),
    (1, "vps_server", 1.65, 1, "Daily VPS prorate (≈$50/mo)"),
    (1, "storage", 0.25, 1, "Storage daily prorate"),
]

# --- Asset valuation skeletons for known MWK titles ---------------------
# These are placeholders requiring source-doc verification. provenance='inferred_weak'.
KNOWN_TITLES_FOR_VALUATION = [
    # (asset_title, case_file, current_use, notes)
    ("T-4497",  "MWK-001", "mixed",        "Mother title — Heirs of Mary Worrick Keesey"),
    ("T-32917", "MWK-001", "mixed",        "Lot 2-X-6 San Roque, parent of the 17 sub-subdivisions"),
    ("T-32916", "MWK-001", "residential",  "Lot 2-X-4 Brgy 3 Daet"),
    ("T-31298", "MWK-001", "mixed",        "Lost annotations title"),
    ("T-52540", "MWK-001", "agricultural", "Contested — cancelled by void-SPA deed"),
]


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()

    # ── Accounts ──
    new = existing = 0
    for code, name, atype, owner, cf in CHART:
        cur.execute("SELECT 1 FROM accounts WHERE account_code=%s", (code,))
        if cur.fetchone():
            existing += 1; continue
        cur.execute("""
            INSERT INTO accounts (account_code, account_name, account_type, owner, case_file)
            VALUES (%s,%s,%s,%s,%s)
        """, (code, name, atype, owner, cf))
        new += 1
    print(f"  accounts:          {new} new / {existing} existing")

    # ── Monthly overhead ──
    new = existing = 0
    for owner, cf, cat, desc, amt in OVERHEAD:
        cur.execute("""
            SELECT 1 FROM monthly_overhead
             WHERE owner=%s AND category=%s AND LEFT(description,40)=LEFT(%s,40)
        """, (owner, cat, desc))
        if cur.fetchone():
            existing += 1; continue
        cur.execute("""
            INSERT INTO monthly_overhead (owner, case_file, category, description, monthly_amount, start_date)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (owner, cf, cat, desc, amt, date.today().replace(day=1)))
        new += 1
    print(f"  monthly_overhead:  {new} new / {existing} existing")

    # ── Leo operational costs (last 30d sample) ──
    cur.execute("SELECT count(*) FROM leo_operational_costs WHERE source='manual_seed'")
    if cur.fetchone()[0] == 0:
        for days_back, cat, usd, units, notes in LEO_COSTS_30D:
            d = date.today() - timedelta(days=days_back)
            php = round(usd * 56.5, 2)  # rough USD→PHP
            cur.execute("""
                INSERT INTO leo_operational_costs (cost_date, category, amount_usd, amount_php, units, notes, source)
                VALUES (%s,%s,%s,%s,%s,%s,'manual_seed')
            """, (d, cat, usd, php, units, notes))
        print(f"  leo_costs:         {len(LEO_COSTS_30D)} sample rows seeded")
    else:
        print(f"  leo_costs:         (already seeded)")

    # ── Asset valuation skeletons ──
    new = existing = 0
    today = date.today()
    for title, cf, use, notes in KNOWN_TITLES_FOR_VALUATION:
        cur.execute("""
            SELECT 1 FROM asset_valuations WHERE asset_title=%s AND snapshot_date=%s
        """, (title, today))
        if cur.fetchone():
            existing += 1; continue
        cur.execute("""
            INSERT INTO asset_valuations (asset_title, case_file, snapshot_date, current_use, provenance_level, notes)
            VALUES (%s,%s,%s,%s,'inferred_weak',%s)
        """, (title, cf, today, use, f"{notes} — figures TBD from tax dec + appraisal docs"))
        new += 1
    print(f"  asset_valuations:  {new} skeletons / {existing} existing")

    print("\n  Summary:")
    for q, label in [
        ("SELECT count(*) FROM accounts", "accounts"),
        ("SELECT count(*) FROM monthly_overhead", "monthly_overhead"),
        ("SELECT count(*) FROM leo_operational_costs", "leo_operational_costs"),
        ("SELECT count(*) FROM asset_valuations", "asset_valuations"),
        ("SELECT count(*) FROM firm_goals", "firm_goals"),
    ]:
        cur.execute(q)
        print(f"    {label:24s}  {cur.fetchone()[0]}")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
