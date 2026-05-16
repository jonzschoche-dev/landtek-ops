#!/usr/bin/env python3
"""Data completeness audit — what's the gap between what Leo has and what it needs?"""
import psycopg2, psycopg2.extras
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

def main():
    conn = psycopg2.connect(DSN); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    findings = []

    # ── Documents ──
    cur.execute("""
        SELECT count(*) AS total,
               count(*) FILTER (WHERE extracted_text IS NOT NULL AND length(extracted_text) >= 200) AS extracted,
               count(*) FILTER (WHERE case_file = 'MWK-001') AS mwk,
               count(*) FILTER (WHERE case_file IS NULL OR case_file = '') AS uncorrelated,
               count(*) FILTER (WHERE execution_status IS NOT NULL AND execution_status <> 'unknown') AS classified
          FROM documents
    """)
    s = cur.fetchone()
    findings.append(("DOCUMENTS",
        f"{s['total']} in DB · {s['extracted']} extracted ({s['extracted']*100//s['total']}%) · "
        f"{s['mwk']} MWK-001 · {s['uncorrelated']} uncorrelated"))

    # Drive gap
    import json
    inv = json.load(open("/root/landtek/drive_inventory.json"))
    drive_total = sum(len(v) for v in inv.values() if isinstance(v, list))
    cur.execute("SELECT count(DISTINCT drive_file_id) FROM documents WHERE drive_file_id IS NOT NULL")
    linked = cur.fetchone()["count"]
    findings.append(("DRIVE INGEST GAP",
        f"Drive has {drive_total} files · {linked} ingested · "
        f"<b>{drive_total - linked} NOT YET INGESTED</b>"))

    # ── Email ──
    cur.execute("""SELECT count(*) AS total, max(ingested_at)::date AS last_pull,
                          count(*) FILTER (WHERE ingested_at > now() - interval '7 days') AS recent
                     FROM gmail_messages""")
    e = cur.fetchone()
    findings.append(("EMAIL",
        f"{e['total']} ingested · last pull {e['last_pull']} · "
        f"<b>0 active scraping</b> · last 7d: {e['recent']} new"))

    # ── Transactions ──
    cur.execute("""SELECT count(*) AS total,
                          count(*) FILTER (WHERE category='rpt') AS rpt,
                          count(*) FILTER (WHERE category='filing_fee') AS filing,
                          count(*) FILTER (WHERE category='registration_fee') AS reg,
                          count(*) FILTER (WHERE direction='credit') AS revenue
                     FROM transactions""")
    t = cur.fetchone()
    findings.append(("TRANSACTIONS",
        f"{t['total']} total · {t['rpt']} RPT · {t['filing']} filing · "
        f"{t['reg']} reg · <b>{t['revenue']} revenue entries (basically zero income recorded)</b>"))

    # ── Bills ──
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name='pending_bills'")
    has_bills = bool(cur.fetchone())
    findings.append(("BILLS",
        f"{'pending_bills table exists' if has_bills else '<b>NO bill ingestion at all — schema not built</b>'} · "
        f"<b>0 bills in system, 0 payee records, no recurring vendor data</b>"))

    # ── Assets ──
    cur.execute("""SELECT count(DISTINCT asset_title) AS unique_assets,
                          count(*) FILTER (WHERE market_price_value > 0) AS with_market,
                          count(*) FILTER (WHERE intrinsic_value IS NOT NULL) AS with_intrinsic
                     FROM asset_valuations""")
    a = cur.fetchone()
    findings.append(("ASSETS",
        f"{a['unique_assets']} unique · {a['with_market']} have market value · "
        f"{a['with_intrinsic']} have intrinsic value computed · "
        f"<b>0 zonal values, 0 appraisal values, 0 acquisition costs</b>"))

    # ── Title-ARP linkage ──
    cur.execute("SELECT count(*) FROM title_tax_links")
    tt = cur.fetchone()["count"]
    findings.append(("TITLE↔ARP LINKAGE",
        f"{tt} links · <b>most ARPs still not linked to a TCT</b>"))

    # ── Risks ──
    cur.execute("SELECT count(*) FROM asset_risks")
    findings.append(("ASSET RISKS",
        f"{cur.fetchone()['count']} seeded · <b>per-asset risk profile incomplete</b> (only 7 of 67 active tax decs have a risk row)"))

    # ── Case stage / matters ──
    cur.execute("""SELECT count(*) AS total,
                          count(*) FILTER (WHERE current_stage IS NOT NULL) AS staged
                     FROM matters WHERE status='active'""")
    m = cur.fetchone()
    findings.append(("MATTERS",
        f"{m['total']} active · {m['staged']} with stage · "
        f"<b>3 of 4 matters (estate, ARTA-DILG, TCT4497) have no stage tracking yet</b>"))

    # ── Real overhead ──
    cur.execute("SELECT count(*), sum(monthly_amount) FROM monthly_overhead WHERE source_doc_id IS NULL")
    o = cur.fetchone()
    findings.append(("MONTHLY OVERHEAD",
        f"{o['count']} rows · ₱{float(o['sum'] or 0):,.0f}/mo · "
        f"<b>ALL still estimates (source_doc_id NULL on 100%) — Landtek's real burn unknown</b>"))

    # ── Leo API spend ──
    cur.execute("SELECT count(*), sum(amount_usd) FROM leo_operational_costs WHERE source='manual_seed'")
    lc = cur.fetchone()
    findings.append(("LEO OPERATIONAL COSTS",
        f"{lc['count']} rows · ${float(lc['sum'] or 0):.2f} · "
        f"<b>ALL seed estimates — no Anthropic/Gemini billing API connected for real numbers</b>"))

    # ── Heir/estate ──
    cur.execute("""SELECT count(*) FROM entities
                    WHERE canonical_name ILIKE '%keesey%' OR canonical_name ILIKE '%zschoche%'""")
    findings.append(("HEIRS DATA",
        f"{cur.fetchone()['count']} Keesey/Zschoche entities · "
        f"<b>positions of Marcia, Geraldine, Ellen on case strategy unknown</b>"))

    # ── Approval chain ──
    cur.execute("SELECT count(*) FROM channel_users WHERE onboarding_state='approved'")
    findings.append(("APPROVED USERS",
        f"{cur.fetchone()['count']} approved · <b>Atty. Barandon, Atty. Botor, no clients onboarded yet</b>"))

    cur.close(); conn.close()

    print("─" * 70)
    print("DATA COMPLETENESS AUDIT")
    print("─" * 70)
    for cat, gap in findings:
        print(f"\n{cat}:\n  {gap}")
    return findings


if __name__ == "__main__":
    main()
