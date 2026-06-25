#!/usr/bin/env python3
"""correspondence_ledger.py — the delivery-aware, quote-verified correspondence ledger.

The "growing intimate knowledge of the correspondences": every letter/request/reply as an event that
records claimed_date vs actual delivery/receipt, with delivery_status (delivered | failed | phantom |
late | unknown). DELIVERY IS NEVER ASSUMED FROM A DOCUMENT'S DATE — it is its own fact. Every field-claim
is backed by a VERBATIM quote that must be a whitespace-normalized substring of its cited source document,
else the proof is marked unverified (no-guess gate). The GAPS (claimed≪received, failed/phantom, late) are
the candidate findings — in a §21 case the violations largely ARE the non-deliveries.

Runs ON THE VPS (psycopg2 → internal DSN).
  python3 correspondence_ledger.py --init
  python3 correspondence_ledger.py --seed seed.json
  python3 correspondence_ledger.py --render --matter MWK
  python3 correspondence_ledger.py --gaps --matter MWK
"""
import argparse
import json
import re
import sys
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DDL = """CREATE TABLE IF NOT EXISTS correspondence_events (
  id serial PRIMARY KEY, matter_code text, author text, addressee text, subject text,
  claimed_date date, channel text, sent_to text, delivery_status text, received_date date,
  gap_flag text, proofs jsonb, all_verified bool, created_at timestamptz default now());"""


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def verify_proofs(cur, proofs):
    """Each proof's quote MUST be a (normalized) substring of its cited document, or it's unverified."""
    out, all_ok = [], True
    for p in proofs:
        cur.execute("SELECT regexp_replace(coalesce(extracted_text,''),'[[:space:]]+',' ','g') FROM documents WHERE id=%s",
                    (p["doc_id"],))
        row = cur.fetchone()
        ok = bool(row) and _norm(p["quote"]) in _norm(row[0])
        out.append({**p, "verified": ok})
        all_ok = all_ok and ok
    return out, all_ok


def add_event(cur, e):
    proofs, all_ok = verify_proofs(cur, e.get("proofs", []))
    cur.execute("""INSERT INTO correspondence_events
        (matter_code,author,addressee,subject,claimed_date,channel,sent_to,delivery_status,
         received_date,gap_flag,proofs,all_verified)
        VALUES (%(matter_code)s,%(author)s,%(addressee)s,%(subject)s,%(claimed_date)s,%(channel)s,
         %(sent_to)s,%(delivery_status)s,%(received_date)s,%(gap_flag)s,%(proofs)s::jsonb,%(av)s)
        RETURNING id""",
        {**{k: e.get(k) for k in ("matter_code", "author", "addressee", "subject", "claimed_date",
                                  "channel", "sent_to", "delivery_status", "received_date", "gap_flag")},
         "proofs": json.dumps(proofs), "av": all_ok})
    return cur.fetchone()[0], all_ok, proofs


def render(conn, matter, gaps_only=False):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = "matter_code ILIKE %s"
    if gaps_only:
        where += " AND (delivery_status IN ('failed','phantom','late') OR (received_date IS NOT NULL AND received_date > claimed_date + 30))"
    cur.execute(f"SELECT claimed_date,author,addressee,subject,channel,sent_to,delivery_status,"
                f"received_date,gap_flag,proofs,all_verified FROM correspondence_events "
                f"WHERE {where} ORDER BY claimed_date", (matter + "%",))
    rows = cur.fetchall()
    print(f"=== correspondence ledger — {matter} ({'GAPS only' if gaps_only else 'all'}) : {len(rows)} events ===\n")
    for r in rows:
        flag = {"phantom": "⚠ PHANTOM", "failed": "⚠ FAILED", "late": "⚠ LATE",
                "delivered": "✓ delivered", "unknown": "? unknown"}.get(r["delivery_status"], r["delivery_status"])
        print(f"[{r['claimed_date']}] {r['author']} → {r['addressee']}")
        print(f"    {r['subject']}")
        print(f"    delivery: {flag}" + (f" · sent to {r['sent_to']}" if r["sent_to"] else "")
              + (f" · received {r['received_date']}" if r["received_date"] else ""))
        if r["gap_flag"]:
            print(f"    GAP: {r['gap_flag']}")
        for p in (r["proofs"] or []):
            mark = "✓" if p.get("verified") else "✗ UNVERIFIED"
            print(f"      {mark} doc {p['doc_id']}: \"{p['quote'][:90]}\"")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--seed")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--gaps", action="store_true")
    ap.add_argument("--matter", default="MWK")
    a = ap.parse_args()
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    if a.init:
        cur.execute(DDL); print("[ledger] table ready")
    if a.seed:
        events = json.load(open(a.seed))
        for e in events:
            eid, ok, proofs = add_event(cur, e)
            nbad = sum(1 for p in proofs if not p["verified"])
            print(f"[ledger] event {eid} added · all_verified={ok}" + (f" · {nbad} UNVERIFIED proof(s)!" if nbad else ""))
    if a.gaps:
        render(conn, a.matter, gaps_only=True)
    elif a.render:
        render(conn, a.matter, gaps_only=False)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
