#!/usr/bin/env python3
"""ingest_transactions.py — pull a financial-account export into the expense engine.

The operator funds estate expenses via Robinhood (card), and BofA -> GCash/cash.
This ingests an EXPORTED statement/CSV from any of those into a staging table
(`expense_intake_raw`), auto-mapping the date/amount/description columns. Nothing
is claimed until it is classified estate-related and PROMOTED to legal_cost_actuals
(reimbursable). This never touches a live account — you export, it ingests.

Workflow:
  1) Export CSV from the app (Robinhood / BofA / GCash).
  2) python3 scripts/ingest_transactions.py --source robinhood --file rh.csv [--matter MWK-001]
  3) python3 scripts/ingest_transactions.py --classify           # review + tag estate rows
  4) python3 scripts/ingest_transactions.py --promote            # move estate rows -> ledger

Staging holds EVERYTHING (for reconciliation vs Colen's statement); only confirmed
estate rows reach the reimbursement ledger.
"""
import os, sys, csv, json, argparse, datetime as dt

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

DATE_KEYS = ("date", "posted", "transaction date", "trans date", "activity date", "process date")
AMT_KEYS  = ("amount", "debit", "withdrawal", "amount (php)", "amount (usd)", "total", "value")
DESC_KEYS = ("description", "memo", "merchant", "name", "details", "payee", "particulars", "narration")

DDL = """
CREATE TABLE IF NOT EXISTS expense_intake_raw (
  id            bigserial PRIMARY KEY,
  matter_code   text NOT NULL DEFAULT 'MWK-001',
  source        text NOT NULL,                 -- robinhood|bofa|gcash|cash
  txn_date      date,
  description   text,
  amount        numeric,
  currency      text DEFAULT 'PHP',
  raw           jsonb,
  estate        boolean,                        -- NULL=unreviewed, true/false after --classify
  reimburse_basis text,
  promoted      boolean DEFAULT false,          -- moved into legal_cost_actuals?
  dedup_key     text UNIQUE,                    -- source|date|amount|desc -> idempotent re-ingest
  ingested_at   timestamptz DEFAULT now()
);
"""

# PH-location / estate signal keywords for a first-pass classification hint
ESTATE_HINTS = ("assessor", "registry", "register of deeds", "rod", "bir", "notar", "lgu",
                "mercedes", "daet", "camarines", "gcash", "psa", "lra", "denr", "penro",
                "court", "docket", "filing", "atty", "law office", "certif", "survey",
                "rpt", "real property tax", "printing", "photocop", "courier", "lbc")


def connect():
    try:
        import psycopg2
    except ImportError:
        sys.exit("psycopg2 not installed (run on the VPS).")
    return psycopg2.connect(DSN)


def _find(headers, keys):
    low = {h.lower().strip(): h for h in headers}
    for k in keys:
        for lk, orig in low.items():
            if k == lk or k in lk:
                return orig
    return None


def _parse_amount(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("$", "").replace("PHP", "").replace("₱", "").strip()
    s = s.replace("(", "-").replace(")", "")
    try:
        return abs(float(s))
    except ValueError:
        return None


def _parse_date(v):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%b %d, %Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(str(v).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def ingest(cur, source, path, matter, currency):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        headers = rdr.fieldnames or []
        dcol, acol, ccol = _find(headers, DATE_KEYS), _find(headers, AMT_KEYS), _find(headers, DESC_KEYS)
        if not (dcol and acol):
            sys.exit(f"Could not map date/amount columns in {path}. Headers: {headers}")
        n = skipped = 0
        for row in rdr:
            amt = _parse_amount(row.get(acol))
            d = _parse_date(row.get(dcol))
            desc = (row.get(ccol) or "").strip() if ccol else ""
            if amt is None or amt == 0:
                continue
            key = f"{source}|{d}|{amt}|{desc[:40]}"
            try:
                cur.execute("""INSERT INTO expense_intake_raw
                    (matter_code,source,txn_date,description,amount,currency,raw,dedup_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (dedup_key) DO NOTHING""",
                    (matter, source, d, desc, amt, currency, json.dumps(row), key))
                n += cur.rowcount
                skipped += (1 - cur.rowcount)
            except Exception as e:
                print(f"  row error: {e}")
        print(f"[ingest] {source}: {n} new rows staged, {skipped} duplicates skipped.")


def classify(cur, matter):
    """First-pass: tag rows whose description hits an estate/PH keyword as estate=true (hint)."""
    cur.execute("SELECT id, description FROM expense_intake_raw WHERE matter_code=%s AND estate IS NULL", (matter,))
    rows = cur.fetchall()
    hit = 0
    for rid, desc in rows:
        d = (desc or "").lower()
        if any(k in d for k in ESTATE_HINTS):
            cur.execute("UPDATE expense_intake_raw SET estate=true, reimburse_basis='necessary' WHERE id=%s", (rid,))
            hit += 1
    print(f"[classify] {hit}/{len(rows)} unreviewed rows hint estate-related (review the rest by hand: "
          f"UPDATE expense_intake_raw SET estate=true/false WHERE id=...).")


def promote(cur, matter):
    cur.execute("""INSERT INTO legal_cost_actuals
        (matter_code,category,amount_php,currency,incurred_date,paid,description,source,paid_by,reimbursable,reimburse_basis,recorded_by)
        SELECT matter_code, 'source:'||source, amount, currency, coalesce(txn_date, now()::date), true,
               left(coalesce(description,'(no desc)'),200), 'intake:'||source, 'jonathan', true,
               coalesce(reimburse_basis,'necessary'), 'ingest_transactions'
        FROM expense_intake_raw
        WHERE matter_code=%s AND estate IS TRUE AND promoted IS FALSE""", (matter,))
    moved = cur.rowcount
    cur.execute("UPDATE expense_intake_raw SET promoted=true WHERE matter_code=%s AND estate IS TRUE AND promoted IS FALSE", (matter,))
    print(f"[promote] moved {moved} estate rows into legal_cost_actuals.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", default="MWK-001")
    ap.add_argument("--source", choices=["robinhood", "bofa", "gcash", "cash"])
    ap.add_argument("--file")
    ap.add_argument("--currency", default="PHP")
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--promote", action="store_true")
    a = ap.parse_args()
    conn = connect(); cur = conn.cursor()
    cur.execute(DDL); conn.commit()
    if a.file:
        if not a.source:
            sys.exit("--source required with --file")
        ingest(cur, a.source, a.file, a.matter, a.currency); conn.commit()
    if a.classify:
        classify(cur, a.matter); conn.commit()
    if a.promote:
        promote(cur, a.matter); conn.commit()
    if not (a.file or a.classify or a.promote):
        cur.execute("SELECT source, count(*), to_char(sum(amount),'FM999,999,999.00') FROM expense_intake_raw WHERE matter_code=%s GROUP BY source", (a.matter,))
        print("[staging] by source:")
        for s, c, tot in cur.fetchall():
            print(f"    {s:10} {c:>5} rows  PHP {tot}")


if __name__ == "__main__":
    main()
