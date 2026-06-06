#!/usr/bin/env python3
"""search_emails.py — full-text search over gmail_messages (sent + received).

Every row in gmail_messages is searchable via search_vector (subject + body).
Results cite gmail#id for Leo / operator lookup.

Usage:
  python3 scripts/search_emails.py ARTA manifestation
  python3 scripts/search_emails.py "0747" --days 30
  python3 scripts/search_emails.py del rosario --direction received
  python3 scripts/search_emails.py --matter MWK-ARTA-1210
  python3 scripts/search_emails.py --json 1210 OP
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _direction(labels: list | None) -> str:
    return "SENT" if labels and "SENT" in labels else "RECEIVED"


def _use_canonical_view(cur) -> bool:
    cur.execute("""
        SELECT 1 FROM information_schema.views
         WHERE table_schema = 'public' AND table_name = 'v_gmail_canonical'
    """)
    return bool(cur.fetchone())


def search(
    cur,
    *,
    query: str | None,
    matter_code: str | None,
    direction: str | None,
    days: int | None,
    client_code: str | None,
    limit: int,
    include_archived: bool = True,
) -> list[dict]:
    canonical = _use_canonical_view(cur) and include_archived
    clauses = ["1=1"]
    params: list = []

    if canonical and not include_archived:
        clauses.append("mailbox_status = 'active'")
    if matter_code:
        clauses.append("%s = ANY(matter_codes)")
        params.append(matter_code)
    if client_code:
        if canonical:
            clauses.append("(client_code = %s OR client_code IS NULL)")
        else:
            clauses.append("client_code = %s")
        params.append(client_code)
    if days:
        if canonical:
            clauses.append("mail_at >= now() - (%s || ' days')::interval")
        else:
            clauses.append("COALESCE(received_at, sent_at) >= now() - (%s || ' days')::interval")
        params.append(str(days))
    if direction == "sent":
        clauses.append("direction = 'SENT'" if canonical else "'SENT' = ANY(labels)")
    elif direction == "received":
        if canonical:
            clauses.append("direction = 'RECEIVED'")
        else:
            clauses.append("NOT ('SENT' = ANY(COALESCE(labels, '{}'::text[])))")

    if query and query.strip():
        q = query.strip()
        cur.execute("""
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'gmail_messages' AND column_name = 'search_vector'
        """)
        if cur.fetchone():
            clauses.append("search_vector @@ plainto_tsquery('english', %s)")
            params.append(q)
        else:
            clauses.append(
                "(subject ILIKE %s OR body_plain ILIKE %s OR from_addr ILIKE %s)"
            )
            like = f"%{q}%"
            params.extend([like, like, like])

    if canonical:
        sql = f"""
            SELECT id, source_table, citation, mailbox_status, direction, mail_at,
                   from_addr, subject, client_code, matter_codes, has_attachments,
                   relevance_status, archived_reason,
                   left(body_plain, 400) AS body_snip
              FROM v_gmail_canonical
             WHERE {' AND '.join(clauses)}
             ORDER BY mail_at DESC NULLS LAST
             LIMIT %s
        """
    else:
        sql = f"""
            SELECT id, 'gmail_messages'::text AS source_table,
                   'gmail#' || id::text AS citation,
                   'active'::text AS mailbox_status,
                   CASE WHEN 'SENT' = ANY(COALESCE(labels, '{}'::text[]))
                        THEN 'SENT' ELSE 'RECEIVED' END AS direction,
                   COALESCE(received_at, sent_at) AS mail_at,
                   from_addr, subject, client_code, matter_codes, has_attachments,
                   relevance_status, NULL::text AS archived_reason,
                   left(body_plain, 400) AS body_snip
              FROM gmail_messages
             WHERE {' AND '.join(clauses)}
             ORDER BY mail_at DESC NULLS LAST
             LIMIT %s
        """
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    out = []
    for r in rows:
        dt = r["mail_at"]
        out.append({
            "gmail_id": r["id"],
            "source_table": r["source_table"],
            "citation": r["citation"],
            "mailbox_status": r.get("mailbox_status") or "active",
            "date": dt.date().isoformat() if dt else None,
            "direction": r["direction"],
            "from": r["from_addr"],
            "subject": r["subject"],
            "client_code": r["client_code"],
            "matter_codes": list(r["matter_codes"] or []),
            "has_attachments": r["has_attachments"],
            "relevance_status": r["relevance_status"],
            "archived_reason": r.get("archived_reason"),
            "body_snip": (r["body_snip"] or "").strip()[:300],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Search gmail_messages corpus")
    ap.add_argument("terms", nargs="*", help="search terms (plain language)")
    ap.add_argument("--matter", help="filter matter_code e.g. MWK-ARTA-1210")
    ap.add_argument("--client", help="filter client_code e.g. MWK-001")
    ap.add_argument("--direction", choices=["sent", "received", "all"], default="all")
    ap.add_argument("--days", type=int, help="only emails within last N days")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    query = " ".join(args.terms) if args.terms else None
    if not query and not args.matter and not args.client:
        ap.error("provide search terms and/or --matter / --client")

    conn = psycopg2.connect(DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        rows = search(
            cur,
            query=query,
            matter_code=args.matter,
            direction=None if args.direction == "all" else args.direction,
            days=args.days,
            client_code=args.client,
            limit=args.limit,
        )
    finally:
        cur.close()
        conn.close()

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        print("No matching emails.")
        return

    print(f"# Email search — {len(rows)} hit(s)")
    if query:
        print(f"  query: {query!r}")
    for r in rows:
        mc = ", ".join(r["matter_codes"]) or "—"
        attach = " 📎" if r["has_attachments"] else ""
        arch = " [archived]" if r.get("mailbox_status") == "archived" else ""
        print(
            f"{r['citation']}  {r['date'] or '?'}  [{r['direction']}]{arch}  "
            f"from={(r['from'] or '?')[:40]}  [{mc}]{attach}"
        )
        print(f"  {(r['subject'] or '(no subject)')[:100]}")
        if r["body_snip"]:
            snip = re.sub(r"\s+", " ", r["body_snip"])[:200]
            print(f"  … {snip}")
        print()


if __name__ == "__main__":
    main()