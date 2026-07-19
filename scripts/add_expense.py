#!/usr/bin/env python3
"""add_expense.py — log a new estate advance into the reimbursement engine.

The estate-expense total keeps rising (guardianship filing, mandamus, CV6839
execution costs, ongoing RPT). This is the intake that keeps `legal_cost_actuals`
and the `v_mwk_reimbursement` view current, so every new peso spent stays on the
Art. 488 / Rule 96 reimbursement claim.

Source of truth for MWK remains Colen Ibasco's Statement of Expenses (doc 777) +
its Index of Receipts (Annexes); use --doc to cite the receipt/OR document id.

Usage:
  python3 scripts/add_expense.py \\
      --category rpt_taxes --amount 75000 --date 2026-07-19 \\
      --basis art488_tax --desc "2026 RPT payment, LGU Mercedes" \\
      --or-ref "OR#12345" --doc 812

  python3 scripts/add_expense.py --report            # just show the running totals

Reimburse-basis (strength for recovery, strongest first):
  art488_tax          - taxes paid (Art. 488 names 'the taxes' explicitly)
  art488_preservation - preservation/protection expenses (Art. 488)
  rule96_guardian     - guardian's necessary expense (Rule 96 s8, off the top, court-fixed)
  rule96_compensation - guardian's COMPENSATION for services / full-time administration (Rule 96 s8; separate head)
  subsistence_management - presence/subsistence costs, wholly estate-attributable (no PH citizenship/work/residence)
  agency_1912         - sums advanced under the SPA (Art. 1912-1913, principal reimburses)
  negotiorum_2144     - management of the refusing heirs' neglected property (Arts. 2144-2150)
  necessary           - necessary/useful but more contestable (lodging/travel/office/IT)
"""
import argparse, os, sys

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
BASES = ["art488_tax", "art488_preservation", "rule96_guardian",
         "rule96_compensation", "subsistence_management",
         "agency_1912", "negotiorum_2144", "necessary"]


def connect():
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 not installed on this host (run on the VPS).")
    return psycopg2.connect(DSN)


def report(cur, matter):
    cur.execute("SELECT * FROM v_mwk_reimbursement WHERE matter_code=%s", (matter,))
    row = cur.fetchone()
    if not row:
        print(f"No expenses logged yet for {matter}."); return
    cols = [d[0] for d in cur.description]
    d = dict(zip(cols, row))
    print(f"\n=== Reimbursement — {matter} ===")
    print(f"  Total advanced      : PHP {d['total_advanced']:,.2f}")
    print(f"  Strong Art.488 base : PHP {d['strong_base']:,.2f}")
    print(f"  Gerry owes  (all / strong): PHP {d['gerry_owes_all']:,.2f} / {d['gerry_owes_strong']:,.2f}")
    print(f"  Marcia owes (all / strong): PHP {d['marcia_owes_all']:,.2f} / {d['marcia_owes_strong']:,.2f}")


def main():
    ap = argparse.ArgumentParser(description="Log an estate advance / show reimbursement totals.")
    ap.add_argument("--matter", default="MWK-001")
    ap.add_argument("--report", action="store_true", help="show running totals only")
    ap.add_argument("--category")
    ap.add_argument("--amount", type=float)
    ap.add_argument("--date", help="YYYY-MM-DD incurred date")
    ap.add_argument("--basis", choices=BASES)
    ap.add_argument("--by", default="jonathan/patricia")
    ap.add_argument("--desc")
    ap.add_argument("--or-ref", dest="or_ref", default="")
    ap.add_argument("--doc", type=int, default=None, help="source_doc_id (receipt/OR)")
    ap.add_argument("--unpaid", action="store_true", help="mark as not-yet-paid (accrued)")
    a = ap.parse_args()

    conn = connect(); cur = conn.cursor()
    if a.report:
        report(cur, a.matter); return
    missing = [f for f in ("category", "amount", "date", "basis", "desc") if not getattr(a, f)]
    if missing:
        sys.exit(f"Missing required args for logging: {', '.join('--'+m for m in missing)} "
                 f"(or use --report).")
    cur.execute(
        """INSERT INTO legal_cost_actuals
           (matter_code, category, amount_php, currency, incurred_date, paid, description,
            source, source_doc_id, paid_by, reimbursable, reimburse_basis, or_ref, recorded_by)
           VALUES (%s,%s,%s,'PHP',%s,%s,%s,'manual',%s,%s,true,%s,%s,'add_expense')""",
        (a.matter, a.category, a.amount, a.date, not a.unpaid, a.desc,
         a.doc, a.by, a.basis, a.or_ref))
    conn.commit()
    print(f"Logged: {a.matter} / {a.category} / PHP {a.amount:,.2f} / {a.basis}"
          f"{' [ACCRUED-unpaid]' if a.unpaid else ''}")
    report(cur, a.matter)


if __name__ == "__main__":
    main()
