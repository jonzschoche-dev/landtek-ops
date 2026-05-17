#!/usr/bin/env python3
"""client_history_scan — append every event from every source into client_history.

Idempotent. Run after every ingest pass (or on a 30-min timer). Re-scans skip
rows already in client_history (UNIQUE on source_table + source_id).

Per Jonathan 2026-05-17: "constantly added onto for each scan, each input
should be line by line."

Output modes:
  --apply          insert new rows (default behavior; run via cron)
  --output CLIENT  print client_history ledger for the given client_code
  --since DATE     restrict ledger output
"""
import argparse
from datetime import date
import sys

sys.path.insert(0, "/root/landtek")
from landtek_core import db


def resolve_client_for_case(cur, case_file):
    """Map a case_file → client_code via clients.case_file or matters lookup."""
    if not case_file:
        return None
    cur.execute("SELECT client_code FROM clients WHERE case_file = %s LIMIT 1", (case_file,))
    r = cur.fetchone()
    if r:
        return r["client_code"]
    cur.execute("SELECT DISTINCT client_code FROM matters WHERE case_file = %s LIMIT 1", (case_file,))
    r = cur.fetchone()
    return r["client_code"] if r else None


def upsert_event(cur, row):
    """INSERT into client_history; ON CONFLICT (source_table, source_id) DO NOTHING (append-only).

    Populates event_kind_canonical via event_kind_taxonomy lookup (deploy_151).
    Rows whose raw_kind isn't in the taxonomy get 'uncategorized' so nothing is lost.
    """
    cur.execute("""
        INSERT INTO client_history
          (client_code, case_file, matter_code, event_date, event_datetime,
           event_kind, event_kind_canonical, source_table, source_id,
           who_from, who_to, what_summary, citation_ref, attachments, provenance)
        VALUES (%(client_code)s, %(case_file)s, %(matter_code)s, %(event_date)s,
                %(event_datetime)s, %(event_kind)s,
                COALESCE((SELECT canonical_kind FROM event_kind_taxonomy WHERE raw_kind = %(event_kind)s),
                         'uncategorized'),
                %(source_table)s, %(source_id)s,
                %(who_from)s, %(who_to)s, %(what_summary)s, %(citation_ref)s,
                %(attachments)s, %(provenance)s)
        ON CONFLICT (source_table, source_id) DO NOTHING
    """, row)


def scan_documents(cur):
    """Every executed doc → one event."""
    cur.execute("""
        SELECT d.id, d.case_file, d.doc_date_norm, d.classification, d.execution_status,
               d.smart_filename, d.original_filename
          FROM documents d
         WHERE d.case_file IS NOT NULL
           AND d.doc_date_norm IS NOT NULL
    """)
    docs = cur.fetchall()
    n = 0
    for d in docs:
        client_code = resolve_client_for_case(cur, d["case_file"])
        if not client_code:
            continue
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": d["case_file"],
            "matter_code": None,
            "event_date": d["doc_date_norm"],
            "event_datetime": None,
            "event_kind": (d["classification"] or "doc").lower().replace(" ", "_"),
            "source_table": "documents",
            "source_id": str(d["id"]),
            "who_from": d["execution_status"] or "—",
            "who_to": None,
            "what_summary": f"{d['classification'] or 'doc'} — {(d['smart_filename'] or d['original_filename'] or '(no name)')[:140]}",
            "citation_ref": f"doc#{d['id']} status={d['execution_status']}",
            "attachments": None,
            "provenance": "verified" if d["execution_status"] in ("executed_filed","executed_notarized","government_issued") else "inferred_strong",
        })
        n += 1
    return n


def scan_gmail(cur):
    """Every email (INBOX + SENT) → one event."""
    cur.execute("""
        SELECT id, case_file, sent_at, received_at, from_addr, to_addrs, subject,
               labels, has_attachments
          FROM gmail_messages
         WHERE case_file IS NOT NULL OR landtek_thread_id IS NOT NULL
    """)
    msgs = cur.fetchall()
    n = 0
    for m in msgs:
        client_code = resolve_client_for_case(cur, m["case_file"])
        if not client_code:
            continue
        direction = "SENT" if "SENT" in (m["labels"] or []) else "RECEIVED"
        evt_dt = m["sent_at"] or m["received_at"]
        evt_date = evt_dt.date() if evt_dt else None
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": m["case_file"],
            "matter_code": None,
            "event_date": evt_date,
            "event_datetime": evt_dt,
            "event_kind": f"email_{direction.lower()}",
            "source_table": "gmail_messages",
            "source_id": str(m["id"]),
            "who_from": m["from_addr"] or "—",
            "who_to": ", ".join(m["to_addrs"] or [])[:200],
            "what_summary": f"📧 {direction} — {(m['subject'] or '(no subject)')[:140]}",
            "citation_ref": f"gmail#{m['id']} labels={','.join(m['labels'] or [])[:60]}",
            "attachments": "yes" if m["has_attachments"] else None,
            "provenance": "verified",
        })
        n += 1
    return n


def scan_transactions(cur):
    cur.execute("""
        SELECT id, case_file, tx_date, category, amount, description, source_doc_id
          FROM transactions WHERE case_file IS NOT NULL
    """)
    txns = cur.fetchall()
    n = 0
    for t in txns:
        client_code = resolve_client_for_case(cur, t["case_file"])
        if not client_code:
            continue
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": t["case_file"],
            "matter_code": None,
            "event_date": t["tx_date"],
            "event_datetime": None,
            "event_kind": f"tx_{t['category']}",
            "source_table": "transactions",
            "source_id": str(t["id"]),
            "who_from": None,
            "who_to": None,
            "what_summary": f"💰 {t['category']} ₱{float(t['amount'] or 0):,.2f} — {(t['description'] or '')[:120]}",
            "citation_ref": f"tx#{t['id']}" + (f" doc#{t['source_doc_id']}" if t["source_doc_id"] else ""),
            "attachments": None,
            "provenance": "verified" if t["source_doc_id"] else "inferred_strong",
        })
        n += 1
    return n


def scan_deadlines(cur):
    cur.execute("""
        SELECT id, case_file, title, due_date, status, source_doc_id, stage_key
          FROM case_deadlines
    """)
    n = 0
    for d in cur.fetchall():
        client_code = resolve_client_for_case(cur, d["case_file"])
        if not client_code:
            continue
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": d["case_file"],
            "matter_code": None,
            "event_date": d["due_date"],
            "event_datetime": None,
            "event_kind": f"deadline_{d['status']}",
            "source_table": "case_deadlines",
            "source_id": str(d["id"]),
            "who_from": None, "who_to": None,
            "what_summary": f"⏰ {d['stage_key'] or 'deadline'} — {d['title'][:140]}",
            "citation_ref": f"deadline#{d['id']}" + (f" doc#{d['source_doc_id']}" if d["source_doc_id"] else ""),
            "attachments": None,
            "provenance": "verified" if d["source_doc_id"] else "inferred_weak",
        })
        n += 1
    return n


def scan_instruments_on_title(cur):
    cur.execute("""
        SELECT iot.id, iot.parent_tct_number, iot.pe_number, iot.entry_date,
               iot.instrument_type, iot.executor_full_name, iot.notary_name,
               iot.doc_id, d.case_file
          FROM instruments_on_title iot
          LEFT JOIN documents d ON d.id = iot.doc_id
    """)
    n = 0
    for r in cur.fetchall():
        client_code = resolve_client_for_case(cur, r["case_file"]) if r["case_file"] else None
        if not client_code:
            continue
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": r["case_file"],
            "matter_code": None,
            "event_date": r["entry_date"],
            "event_datetime": None,
            "event_kind": f"annotation_{(r['instrument_type'] or 'unknown').lower().replace(' ', '_')[:30]}",
            "source_table": "instruments_on_title",
            "source_id": str(r["id"]),
            "who_from": r["executor_full_name"] or "—",
            "who_to": None,
            "what_summary": f"🏷 {r['instrument_type'] or '?'} on {r['parent_tct_number']} (PE {r['pe_number']}); notary {r['notary_name'] or '—'}",
            "citation_ref": f"instruments_on_title#{r['id']}" + (f" doc#{r['doc_id']}" if r["doc_id"] else ""),
            "attachments": None,
            "provenance": "verified",
        })
        n += 1
    return n


def scan_intakes(cur):
    cur.execute("""
        SELECT sir.id, sir.deadline_id, sir.timing, sir.fired_at, sir.status,
               cd.case_file, sit.title AS template_title
          FROM stage_intake_response sir
          JOIN stage_intake_template sit ON sit.id = sir.template_id
          JOIN case_deadlines cd ON cd.id = sir.deadline_id
    """)
    n = 0
    for r in cur.fetchall():
        client_code = resolve_client_for_case(cur, r["case_file"])
        if not client_code:
            continue
        evt_date = r["fired_at"].date() if r["fired_at"] else None
        upsert_event(cur, {
            "client_code": client_code,
            "case_file": r["case_file"],
            "matter_code": None,
            "event_date": evt_date,
            "event_datetime": r["fired_at"],
            "event_kind": f"intake_{r['timing']}_{r['status']}",
            "source_table": "stage_intake_response",
            "source_id": str(r["id"]),
            "who_from": "Leo",
            "who_to": "Jonathan",
            "what_summary": f"📋 {r['timing'].upper()}-intake fired — {r['template_title'][:120]}",
            "citation_ref": f"intake#{r['id']} deadline#{r['deadline_id']}",
            "attachments": None,
            "provenance": "verified",
        })
        n += 1
    return n


def run_scan():
    """One full scan pass — append every new event across all sources."""
    with db() as cur:
        before = cur.execute("SELECT COUNT(*) AS n FROM client_history") or cur.fetchone()
        before_n = cur.fetchone()["n"] if before is None else before["n"]
        # Re-query because the prior fetchone consumed the count
        cur.execute("SELECT COUNT(*) AS n FROM client_history")
        before_n = cur.fetchone()["n"]

        totals = {
            "documents":           scan_documents(cur),
            "gmail":               scan_gmail(cur),
            "transactions":        scan_transactions(cur),
            "deadlines":           scan_deadlines(cur),
            "instruments_on_title":scan_instruments_on_title(cur),
            "intakes":             scan_intakes(cur),
        }

        cur.execute("SELECT COUNT(*) AS n FROM client_history")
        after_n = cur.fetchone()["n"]
    return totals, before_n, after_n


def output_ledger(client_code, since=None):
    """Print the per-client history as a chronological ledger."""
    with db() as cur:
        params = [client_code]
        clause = ""
        if since:
            clause = " AND event_date >= %s"
            params.append(since)
        cur.execute(f"""
            SELECT event_date, event_datetime, event_kind,
                   who_from, who_to, what_summary, citation_ref, provenance
              FROM client_history
             WHERE client_code = %s {clause}
             ORDER BY event_date NULLS LAST, event_datetime NULLS LAST, id
        """, params)
        rows = cur.fetchall()
    if not rows:
        print(f"No history for client_code={client_code}.")
        return
    print(f"# Client history — {client_code} ({len(rows)} events)")
    print()
    for r in rows:
        dt = r["event_date"].isoformat() if r["event_date"] else "?"
        kind = (r["event_kind"] or "?")[:30]
        who = r["who_from"] or ""
        if r["who_to"]:
            who = f"{who} → {r['who_to'][:40]}"
        summary = (r["what_summary"] or "")[:200]
        cite = r["citation_ref"] or ""
        prov = r["provenance"] or "?"
        print(f"{dt}  [{kind:30}]  prov={prov:14}  {who[:50]:50}  {summary}  ⟨{cite}⟩")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", default=True,
                    help="run scan + append (default behavior)")
    ap.add_argument("--output", help="output ledger for given client_code")
    ap.add_argument("--since", help="YYYY-MM-DD lower bound for output")
    args = ap.parse_args()

    if args.output:
        output_ledger(args.output, since=args.since)
        return

    totals, before_n, after_n = run_scan()
    print(f"  scan source totals: {totals}")
    print(f"  client_history rows: {before_n} → {after_n} (added {after_n - before_n})")


if __name__ == "__main__":
    main()
