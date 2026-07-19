#!/usr/bin/env python3
"""expense_harvester.py — keep the MWK reimbursement ledger LIVE (loop/timer).

Finds the LATEST "JPZ ADMIN STATEMENT OF EXPENSES" xlsx in the corpus, parses its
per-category subtotals, and idempotently syncs them into `legal_cost_actuals`
(source='harvest:statement'), so the reimbursement total tracks Colen Ibasco's
newest statement automatically. When a newer statement version is ingested (new
doc id), the next run picks it up and re-syncs.

SAFETY: only writes if the parsed category subtotals reconcile to the sheet's
GRAND TOTAL (±1 peso). A bad/partial parse logs a warning and writes nothing.

Manual `add_expense.py` rows (source='manual') are PRESERVED — those are advances
not yet folded into a statement. Reconcile them out when a statement absorbs them.

Run: python3 scripts/expense_harvester.py            (sync)
     python3 scripts/expense_harvester.py --dry       (parse+report, no write)
"""
import os, sys, re, zipfile
import xml.etree.ElementTree as ET

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
MATTER = os.environ.get("MWK_MATTER", "MWK-001")
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# keyword -> reimburse_basis (first match wins); mirrors REIMBURSEMENT_LEGAL_BASIS.md
BASIS_MAP = [
    ("tax", "art488_tax"),
    ("liaison", "art488_preservation"), ("government", "art488_preservation"),
    ("tools", "necessary"), ("it,", "necessary"),          # IT/tools BEFORE 'research' so IT->necessary
    ("accommodation", "subsistence_management"), ("lodging", "subsistence_management"),
    ("transport", "necessary"), ("travel", "necessary"),
    ("office", "necessary"), ("administrative", "necessary"),
    ("research", "art488_preservation"), ("professional", "art488_preservation"),
    ("legal", "art488_preservation"),
]


def basis_for(cat):
    c = cat.lower()
    for kw, b in BASIS_MAP:
        if kw in c:
            return b
    return "necessary"


def _isnum(v):
    try:
        float(str(v).replace(",", "")); return True
    except (ValueError, TypeError):
        return False


def rows_from_xlsx(path):
    z = zipfile.ZipFile(path)
    ss = []
    try:
        r = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in r.findall(NS + "si"):
            ss.append("".join(t.text or "" for t in si.iter(NS + "t")))
    except KeyError:
        pass
    out = []
    for sh in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
        root = ET.fromstring(z.read(sh))
        for row in root.iter(NS + "row"):
            vals = []
            for c in row.findall(NS + "c"):
                v = c.find(NS + "v")
                if v is None or v.text is None:
                    continue
                vals.append(ss[int(v.text)] if c.get("t") == "s" else v.text)
            if vals:
                out.append(vals)
    return out


def parse_statement(path):
    """-> (list[(category, amount)], grand_total)."""
    cats, current, grand = [], None, None
    catre = re.compile(r"^[A-Z]\.\s+(.+)")
    for vals in rows_from_xlsx(path):
        head = vals[0].strip() if vals and isinstance(vals[0], str) else ""
        m = catre.match(head)
        if m:
            current = m.group(1).strip()[:60]
        low = " | ".join(str(v) for v in vals).lower()
        nums = [round(float(str(v).replace(",", "")), 2) for v in vals if _isnum(v)]
        if "grand total" in low and nums:
            grand = nums[-1]
        elif "subtotal" in low and current and nums:
            cats.append((current, nums[-1]))
            current = None
    return cats, grand


def connect():
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 not installed (run on the VPS).")
    return psycopg2.connect(DSN)


def candidate_statements(cur):
    cur.execute("""
        SELECT id, coalesce(file_path,''), coalesce(document_title, smart_filename, original_filename)
        FROM documents
        WHERE case_file=%s
          AND (document_title ILIKE '%%STATEMENT OF EXPENSES%%'
               OR smart_filename ILIKE '%%STATEMENT OF EXPENSES%%'
               OR original_filename ILIKE '%%STATEMENT OF EXPENSES%%')
          AND coalesce(mime_type,'') ILIKE '%%spreadsheet%%'
          AND coalesce(file_path,'') <> ''
        ORDER BY created_at DESC NULLS LAST, id DESC
    """, (MATTER,))
    return cur.fetchall()


def pick_authoritative(cur):
    """Parse every candidate; return the RECONCILING one with the highest grand total.
    (The 'updated' statement supersedes; a mis-parsed/older file is skipped.)"""
    best, newest_ok = None, True
    for i, (doc_id, path, title) in enumerate(candidate_statements(cur)):
        if not os.path.exists(path):
            continue
        try:
            cats, grand = parse_statement(path)
        except Exception as e:
            print(f"[harvester] parse error doc {doc_id}: {e}"); continue
        total = round(sum(a for _, a in cats), 2)
        reconciles = grand is not None and abs(total - grand) <= 1.0
        if i == 0 and not reconciles:
            newest_ok = False
            print(f"[harvester] WARNING: newest statement doc {doc_id} did NOT reconcile "
                  f"(sum {total:,.2f} vs grand {grand}) — falling back to best reconciling version.")
        if reconciles and (best is None or grand > best[3]):
            best = (doc_id, path, title, grand, cats)
    return best


def main():
    dry = "--dry" in sys.argv
    conn = connect(); cur = conn.cursor()
    best = pick_authoritative(cur)
    if not best:
        print("[harvester] no RECONCILING statement-of-expenses xlsx found — writing NOTHING.")
        sys.exit(2)
    doc_id, path, title, grand, cats = best
    print(f"[harvester] authoritative statement: doc {doc_id} ({title}) — grand total {grand:,.2f}")
    for c, a in cats:
        print(f"    {a:>14,.2f}  {basis_for(c):22} {c}")
    if dry:
        print("[harvester] --dry: no write."); return

    cur.execute("""DELETE FROM legal_cost_actuals
                   WHERE matter_code=%s AND source IN ('xlsx','harvest:statement')""", (MATTER,))
    for c, a in cats:
        cur.execute("""INSERT INTO legal_cost_actuals
            (matter_code, category, amount_php, currency, incurred_date, paid, description,
             source, source_doc_id, paid_by, reimbursable, reimburse_basis, or_ref, recorded_by)
            VALUES (%s,%s,%s,'PHP',now()::date,true,%s,'harvest:statement',%s,'jonathan/patricia',
                    true,%s,%s,'expense_harvester')""",
            (MATTER, c[:60], a, f"{c} (from statement doc {doc_id})", doc_id,
             basis_for(c), f"doc{doc_id} Index of Receipts"))
    conn.commit()
    cur.execute("SELECT to_char(sum(amount_php),'FM999,999,999.00') FROM legal_cost_actuals WHERE matter_code=%s", (MATTER,))
    print(f"[harvester] synced {len(cats)} categories from doc {doc_id}. Ledger total = PHP {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
