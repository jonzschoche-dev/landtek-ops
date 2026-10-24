#!/usr/bin/env python3
"""Court Record CLI (deploy_1109). Deterministic: Postgres + rules; tesseract only for OCR.

  court_record.py [--db DSN] intake FILE --case SP-2680 [--kind K] [--from P] [--to P]
                  [--doc-date YYYY-MM-DD] [--received YYYY-MM-DD] [--summary S] [--status in_hand]
  court_record.py report --case SP-2680 --kind letter_received --from "Gerry Hoppe" --summary ..   (reported_not_in_hand)
  court_record.py list|search [--case C] [--kind K] [--party P] [--from-date D] [--to-date D] [--text T]
  court_record.py fee add --case C --amount 1234.00 [--or-no N] [--date D] [--payee P] [--purpose P] [--receipt-id ID]
  court_record.py fees --case C
  court_record.py missing [--case C]
DSN: --db, else $LANDTEK_DSN, else libpq env (PGHOST etc., as loaded from .env)."""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_once import sha256, extract_text
import psycopg2

KINDS = ['filing', 'order', 'notice', 'letter_received', 'pleading', 'receipt']

def connect(dsn):
    return psycopg2.connect(dsn or os.environ.get('LANDTEK_DSN', ''))

def case_id(cur, code):
    cur.execute('SELECT id FROM court_case WHERE code=%s', (code,))
    r = cur.fetchone()
    if not r:
        sys.exit(f'unknown case {code!r}; add it to court_case first')
    return r[0]

def table(rows, headers):
    rows = [['' if v is None else str(v) for v in r] for r in rows]
    w = [min(60, max([len(h)] + [len(r[i]) for r in rows])) for i, h in enumerate(headers)]
    line = lambda r: '  '.join(c[:60].ljust(w[i]) for i, c in enumerate(r))
    print(line(headers)); print('  '.join('-' * x for x in w))
    for r in rows: print(line(r))
    print(f'({len(rows)} rows)')

def cmd_intake(a, con):
    path = os.path.abspath(a.file)
    digest = sha256(path)
    cur = con.cursor(); cid = case_id(cur, a.case)
    cur.execute('SELECT id FROM court_record WHERE case_id=%s AND sha256=%s', (cid, digest))
    if (r := cur.fetchone()):
        print(f'duplicate: already court_record #{r[0]} (sha256 {digest[:12]})'); return
    text, method = extract_text(path)
    kind = a.kind or 'filing'
    cur.execute("""INSERT INTO court_record (case_id,date_received,date_of_document,kind,from_party,to_party,
                   summary,file_path,sha256,ocr_text,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'in_hand')
                   ON CONFLICT (case_id,sha256) DO NOTHING RETURNING id""",
                (cid, a.received, a.doc_date, kind, a.from_, a.to, a.summary, path, digest, text))
    r = cur.fetchone(); con.commit()
    print(f'inserted court_record #{r[0]} kind={kind} text={method} chars={len(text)}' if r else 'duplicate (race)')

def cmd_report(a, con):
    cur = con.cursor(); cid = case_id(cur, a.case)
    cur.execute("""INSERT INTO court_record (case_id,date_of_document,kind,from_party,to_party,summary,status)
                   VALUES (%s,%s,%s,%s,%s,%s,'reported_not_in_hand') RETURNING id""",
                (cid, a.doc_date, a.kind, a.from_, a.to, a.summary))
    print(f'recorded reported_not_in_hand #{cur.fetchone()[0]}'); con.commit()

def cmd_list(a, con):
    q = ["""SELECT r.id, c.code, r.kind, r.date_of_document, r.date_received, r.from_party, r.to_party,
                 r.status, coalesce(r.summary, left(regexp_replace(r.ocr_text,'\\s+',' ','g'),60)), r.file_path
            FROM court_record r JOIN court_case c ON c.id=r.case_id WHERE true"""]; p = []
    if a.case: q.append('AND c.code=%s'); p.append(a.case)
    if a.kind: q.append('AND r.kind=%s'); p.append(a.kind)
    if a.party: q.append('AND (r.from_party ILIKE %s OR r.to_party ILIKE %s)'); p += [f'%{a.party}%'] * 2
    if a.from_date: q.append('AND coalesce(r.date_of_document,r.date_received)>=%s'); p.append(a.from_date)
    if a.to_date: q.append('AND coalesce(r.date_of_document,r.date_received)<=%s'); p.append(a.to_date)
    if getattr(a, 'text', None):
        q.append("AND (r.ocr_text ILIKE %s OR r.summary ILIKE %s OR r.from_party ILIKE %s)"); p += [f'%{a.text}%'] * 3
    q.append('ORDER BY coalesce(r.date_of_document,r.date_received) NULLS LAST, r.id')
    cur = con.cursor(); cur.execute(' '.join(q), p)
    table(cur.fetchall(), ['id', 'case', 'kind', 'doc_date', 'received', 'from', 'to', 'status', 'summary', 'file'])

def cmd_fee_add(a, con):
    cur = con.cursor(); cid = case_id(cur, a.case)
    cur.execute("""INSERT INTO fee_payment (case_id,date,or_no,amount,payee,purpose,receipt_record_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (case_id,or_no) DO NOTHING RETURNING id""",
                (cid, a.date, a.or_no, a.amount, a.payee, a.purpose, a.receipt_id))
    r = cur.fetchone(); con.commit()
    print(f'fee_payment #{r[0]}' if r else f'duplicate OR {a.or_no} for {a.case}; not added')

def cmd_fees(a, con):
    cur = con.cursor(); cid = case_id(cur, a.case)
    cur.execute('SELECT id,date,or_no,amount,payee,purpose,receipt_record_id FROM fee_payment WHERE case_id=%s ORDER BY date NULLS LAST,id', (cid,))
    table(cur.fetchall(), ['id', 'date', 'or_no', 'amount', 'payee', 'purpose', 'receipt_rec'])
    cur.execute('SELECT count(*), coalesce(sum(amount),0), count(*) FILTER (WHERE receipt_record_id IS NULL) FROM fee_payment WHERE case_id=%s', (cid,))
    n, s, nr = cur.fetchone(); print(f'TOTAL {a.case}: PHP {s:,.2f} across {n} payments ({nr} without a receipt record)')

def cmd_missing(a, con):
    a.kind = a.party = a.from_date = a.to_date = None; a.text = None
    cur = con.cursor()
    q = """SELECT r.id,c.code,r.kind,r.date_of_document,r.from_party,r.to_party,r.summary FROM court_record r
           JOIN court_case c ON c.id=r.case_id WHERE r.status='reported_not_in_hand'"""
    p = []
    if a.case: q += ' AND c.code=%s'; p.append(a.case)
    cur.execute(q + ' ORDER BY r.id', p)
    table(cur.fetchall(), ['id', 'case', 'kind', 'doc_date', 'from', 'to', 'summary'])

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db'); sp = ap.add_subparsers(dest='cmd', required=True)
    def meta(p, need_case=True):
        p.add_argument('--case', required=need_case); p.add_argument('--kind', choices=KINDS)
        p.add_argument('--from', dest='from_'); p.add_argument('--to')
        p.add_argument('--doc-date'); p.add_argument('--summary')
    i = sp.add_parser('intake'); i.add_argument('file'); meta(i); i.add_argument('--received')
    r = sp.add_parser('report'); meta(r)
    for n in ('list', 'search'):
        l = sp.add_parser(n); l.add_argument('--case'); l.add_argument('--kind', choices=KINDS); l.add_argument('--party')
        l.add_argument('--from-date'); l.add_argument('--to-date'); l.add_argument('--text')
    f = sp.add_parser('fee'); fs = f.add_subparsers(dest='feecmd', required=True); fa = fs.add_parser('add')
    fa.add_argument('--case', required=True); fa.add_argument('--amount', required=True); fa.add_argument('--or-no')
    fa.add_argument('--date'); fa.add_argument('--payee'); fa.add_argument('--purpose'); fa.add_argument('--receipt-id', type=int)
    sp.add_parser('fees').add_argument('--case', required=True)
    sp.add_parser('missing').add_argument('--case')
    a = ap.parse_args()
    if a.cmd == 'report' and not a.kind: ap.error('report needs --kind')
    con = connect(a.db)
    {'intake': cmd_intake, 'report': cmd_report, 'list': cmd_list, 'search': cmd_list,
     'fee': cmd_fee_add, 'fees': cmd_fees, 'missing': cmd_missing}[a.cmd](a, con)

if __name__ == '__main__':
    main()
