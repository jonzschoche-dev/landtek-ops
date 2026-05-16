#!/usr/bin/env python3
"""Unified per-matter timeline generator.

Per Jonathan directive 2026-05-16: "all cases complaints or pending events
letters should have a list of events by date that the system can produce on
demand. This will be a test to see the health of the system too. If
correspondences are missing we cannot have a reliable system."

For any input (matter_code | case_file | docket_number), produce a chronological
event stream merging:

  • documents (filings, letters, orders, exhibits) — keyed by doc_date_norm
  • case_deadlines (pending + completed, both planned and actual)
  • gmail_messages (INBOX + SENT) — every correspondence touching the matter
  • transactions (payments, fees, receipts)
  • title_transfers (title-chain events, for property matters)
  • instruments_on_title (Memorandum of Encumbrances entries)
  • stage_intake_response (what Leo asked / what Jonathan answered)
  • truth_negotiations (verifications run)

Each event has fixed columns: when, kind, source, who, what, ref, citation.

Usage:
  python3 timeline.py --matter MWK-CV26360
  python3 timeline.py --case MWK-001
  python3 timeline.py --docket "CTN SL-2026-0218-1378"
  python3 timeline.py --matter MWK-CV26360 --since 2026-01-01
  python3 timeline.py --matter MWK-CV26360 --json
  python3 timeline.py --matter MWK-CV26360 --health   # health-test mode

Zero LLM cost. Pure SQL. Output: markdown to stdout (or json).
"""
import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def resolve_matter(cur, matter_code=None, case_file=None, docket=None):
    """Return list of (matter_code, case_file, docket_number) that match the input."""
    if matter_code:
        cur.execute("""
            SELECT matter_code, case_file, docket_number, title, current_stage, status
              FROM matters WHERE matter_code = %s
        """, (matter_code,))
        rows = cur.fetchall()
    elif docket:
        cur.execute("""
            SELECT matter_code, case_file, docket_number, title, current_stage, status
              FROM matters
             WHERE regexp_replace(docket_number, '\\s+', '', 'g') = regexp_replace(%s, '\\s+', '', 'g')
                OR docket_number = %s
        """, (docket, docket))
        rows = cur.fetchall()
    elif case_file:
        cur.execute("""
            SELECT matter_code, case_file, docket_number, title, current_stage, status
              FROM matters WHERE case_file = %s
        """, (case_file,))
        rows = cur.fetchall()
    else:
        rows = []
    return rows


def docket_match_patterns(docket):
    """Return list of substring patterns to search for the docket variants.

    Handles docket → common shorthand. e.g.,
      'CV-2026-360'           → ['CV-2026-360', '2026-360', '26-360', 'Civil Case No. 26-360']
      'CTN SL-2025-1021-0747' → ['CTN SL-2025-1021-0747', '2025-1021-0747', '1021-0747', and no-space variants]
      'NOR-CTN SL-2026-0423-1891' → similar
      'T-4497'                → ['T-4497']  (no variants needed)
    """
    if not docket:
        return []
    pats = [docket]
    parts = docket.replace("NOR-", "").replace("CV-", "").replace("CTN", "").replace("SL-", "").strip().split("-")
    parts = [p for p in parts if p.strip()]
    if len(parts) >= 2:
        pats.append("-".join(parts[-2:]))     # last two segments
    if len(parts) >= 3:
        pats.append("-".join(parts[-3:]))     # last three
    if docket.startswith("CV-"):
        # CV-2026-360 → "26-360" colloquial form
        parts = docket.replace("CV-", "").split("-")
        if len(parts) == 2:
            yr_short = parts[0][-2:]
            pats.append(f"{yr_short}-{parts[1]}")
            pats.append(f"Civil Case No. {yr_short}-{parts[1]}")
            pats.append(f"Civil Case No {yr_short}-{parts[1]}")
    if "CTN" in docket and "SL" in docket:
        # No-space variant: CTNSL-... and CTN SL ...
        nospace = docket.replace(" ", "")
        if nospace != docket:
            pats.append(nospace)
    return list(set(pats))


def fetch_events(cur, m, since=None, until=None):
    """Pull events from every source for the given matter. Returns list of dicts.

    Scoping: when matter has a specific docket_number, narrow docs to those that
    actually mention it OR any colloquial variant; otherwise fall back to case_file.
    """
    case_file = m["case_file"]
    docket = m["docket_number"]
    matter_code = m["matter_code"]
    docket_pats = docket_match_patterns(docket)

    since_clause = " AND doc_date_norm >= %s" if since else ""
    since_params = (since,) if since else ()

    events = []

    # ─── 1. DOCUMENTS — scoped to docket variants if available, else case_file.
    # Use BOTH ILIKE (fast) and regex (OCR-line-break tolerant). Build a single
    # whitespace-tolerant regex from the LAST docket pattern (most specific suffix).
    if docket_pats:
        ilike_clauses = " OR ".join(["extracted_text ILIKE %s"] * len(docket_pats))
        # Whitespace-tolerant regex: e.g., "0218-1378" → "0218[\s\-]*1378"
        suffix = sorted(docket_pats, key=len)[0]  # shortest variant = most specific suffix
        regex_pat = "[\\s\\-]*".join(re.escape(c) for c in suffix.replace("-", "").replace(" ", ""))
        params = (case_file,) + since_params + (m.get("first_verified_doc_id"),) \
                 + tuple(f"%{p}%" for p in docket_pats) + (regex_pat,)
        cur.execute(f"""
            SELECT id, doc_date_norm, classification, execution_status,
                   smart_filename, original_filename
              FROM documents
             WHERE case_file = %s AND doc_date_norm IS NOT NULL {since_clause}
               AND (id = %s OR {ilike_clauses} OR extracted_text ~ %s)
             ORDER BY doc_date_norm
        """, params)
    else:
        cur.execute(f"""
            SELECT id, doc_date_norm, classification, execution_status,
                   smart_filename, original_filename
              FROM documents
             WHERE case_file = %s AND doc_date_norm IS NOT NULL {since_clause}
             ORDER BY doc_date_norm
        """, (case_file,) + since_params)
    for r in cur.fetchall():
        events.append({
            "when":     r["doc_date_norm"],
            "kind":     "filing" if (r["classification"] or "").lower() in
                        ("complaint","answer","motion","reply","affidavit","judicial affidavit",
                         "court filing","memorandum","resolution") else
                        ("order"  if (r["classification"] or "").lower() in ("order","decision","notice")
                                  else "doc"),
            "source":   "documents",
            "who":      r["execution_status"] or "—",
            "what":     f"{r['classification'] or 'doc'} — {(r['smart_filename'] or r['original_filename'] or '(no name)')[:75]}",
            "ref":      f"doc#{r['id']}",
            "citation": r["execution_status"],
        })

    # ─── 2. CASE DEADLINES (scoped if docket specific) ──────────────────
    if docket_pats:
        clauses = " OR ".join(["title ILIKE %s OR description ILIKE %s OR notes ILIKE %s"] * len(docket_pats))
        params = [case_file] + [f"%{p}%" for p in docket_pats for _ in range(3)]
        cur.execute(f"""
            SELECT id, title, description, due_date, status, stage_key, source_doc_id,
                   reminder_t14_sent_at, reminder_t0_sent_at, updated_at
              FROM case_deadlines
             WHERE case_file = %s AND ({clauses})
             ORDER BY due_date
        """, params)
    else:
        cur.execute("""
            SELECT id, title, description, due_date, status, stage_key, source_doc_id,
                   reminder_t14_sent_at, reminder_t0_sent_at, updated_at
              FROM case_deadlines
             WHERE case_file = %s
             ORDER BY due_date
        """, (case_file,))
    for r in cur.fetchall():
        events.append({
            "when":     r["due_date"],
            "kind":     "deadline_" + (r["status"] or "pending"),
            "source":   "case_deadlines",
            "who":      "Jonathan / counsel",
            "what":     f"{r['stage_key'] or 'deadline'} — {r['title'][:90]}",
            "ref":      f"deadline#{r['id']}",
            "citation": f"source_doc#{r['source_doc_id']}" if r["source_doc_id"] else "no_source",
        })

    # ─── 3. GMAIL (INBOX + SENT) — scoped to docket variants if specific
    if docket_pats:
        clauses = " OR ".join(["subject ILIKE %s OR body_plain ILIKE %s"] * len(docket_pats))
        params = [case_file] + [f"%{p}%" for p in docket_pats for _ in range(2)]
        cur.execute(f"""
            SELECT id, message_id, sent_at, received_at, from_addr, to_addrs, subject,
                   labels, has_attachments, case_file
              FROM gmail_messages
             WHERE case_file = %s AND ({clauses})
             ORDER BY COALESCE(sent_at, received_at)
        """, params)
    else:
        cur.execute("""
            SELECT id, message_id, sent_at, received_at, from_addr, to_addrs, subject,
                   labels, has_attachments, case_file
              FROM gmail_messages
             WHERE case_file = %s
             ORDER BY COALESCE(sent_at, received_at)
        """, (case_file,))
    for r in cur.fetchall():
        direction = "SENT" if "SENT" in (r["labels"] or []) else "RECEIVED"
        events.append({
            "when":     (r["sent_at"] or r["received_at"]).date() if (r["sent_at"] or r["received_at"]) else None,
            "kind":     f"email_{direction.lower()}",
            "source":   "gmail",
            "who":      r["from_addr"] or "—",
            "what":     f"📧 {direction} — {(r['subject'] or '(no subject)')[:90]}"
                        + (" 📎" if r.get("has_attachments") else ""),
            "ref":      f"gmail#{r['id']}",
            "citation": "labels:" + ",".join(r["labels"] or [])[:50],
        })

    # ─── 4. TRANSACTIONS — scoped to docket variants if specific ───────
    if docket_pats:
        clauses = " OR ".join(["description ILIKE %s"] * len(docket_pats))
        params = [case_file] + [f"%{p}%" for p in docket_pats]
        cur.execute(f"""
            SELECT id, tx_date, category, amount, description, source_doc_id
              FROM transactions
             WHERE case_file = %s AND ({clauses})
             ORDER BY tx_date
        """, params)
    else:
        cur.execute("""
            SELECT id, tx_date, category, amount, description, source_doc_id
              FROM transactions
             WHERE case_file = %s
             ORDER BY tx_date
        """, (case_file,))
    for r in cur.fetchall():
        events.append({
            "when":     r["tx_date"],
            "kind":     f"tx_{r['category']}",
            "source":   "transactions",
            "who":      "—",
            "what":     f"💰 {r['category']} ₱{float(r['amount'] or 0):,.2f} — {(r['description'] or '')[:80]}",
            "ref":      f"tx#{r['id']}",
            "citation": f"doc#{r['source_doc_id']}" if r["source_doc_id"] else None,
        })

    # ─── 5. TITLE TRANSFERS (only for matters involving titles) ─────────
    if docket and docket.startswith("T-"):
        cur.execute(f"""
            SELECT id, parent_title, derivative_title, transferor, transferee_name,
                   transfer_date, annotation_date, instrument_type, entry_pe_number,
                   provenance_level, status
              FROM title_transfers
             WHERE parent_title = %s OR derivative_title = %s
             ORDER BY COALESCE(transfer_date, annotation_date)
        """, (docket, docket))
        for r in cur.fetchall():
            events.append({
                "when":     r["transfer_date"] or r["annotation_date"],
                "kind":     "title_transfer",
                "source":   "title_transfers",
                "who":      f"{(r['transferor'] or '?')[:40]} → {(r['transferee_name'] or '?')[:40]}",
                "what":     f"🏷 {r['instrument_type'] or '?'} ({r['parent_title']} → {r['derivative_title'] or '?'})",
                "ref":      f"tt#{r['id']}",
                "citation": f"PE:{r['entry_pe_number']} prov={r['provenance_level']}",
            })

    # ─── 6. STAGE INTAKE — scoped by docket variants via deadline ──────
    if docket_pats:
        clauses = " OR ".join(["cd.title ILIKE %s OR cd.notes ILIKE %s"] * len(docket_pats))
        params = [case_file] + [f"%{p}%" for p in docket_pats for _ in range(2)]
        cur.execute(f"""
            SELECT sir.id, sir.deadline_id, sir.timing, sir.fired_at, sir.status,
                   sit.title AS template_title, cd.title AS deadline_title
              FROM stage_intake_response sir
              JOIN stage_intake_template sit ON sit.id = sir.template_id
              JOIN case_deadlines cd ON cd.id = sir.deadline_id
             WHERE cd.case_file = %s AND ({clauses})
             ORDER BY sir.fired_at
        """, params)
    else:
        cur.execute("""
            SELECT sir.id, sir.deadline_id, sir.timing, sir.fired_at, sir.status,
                   sit.title AS template_title, cd.title AS deadline_title
              FROM stage_intake_response sir
              JOIN stage_intake_template sit ON sit.id = sir.template_id
              JOIN case_deadlines cd ON cd.id = sir.deadline_id
             WHERE cd.case_file = %s
             ORDER BY sir.fired_at
        """, (case_file,))
    for r in cur.fetchall():
        events.append({
            "when":     r["fired_at"].date() if r["fired_at"] else None,
            "kind":     f"intake_{r['timing']}_{r['status']}",
            "source":   "stage_intake_response",
            "who":      "Leo → Jonathan",
            "what":     f"📋 {r['timing'].upper()}-intake fired — {r['template_title'][:70]}",
            "ref":      f"intake#{r['id']}",
            "citation": f"deadline#{r['deadline_id']}",
        })

    return events


def health_check(events, m):
    """Return list of health-test failures for this matter's timeline."""
    issues = []
    if not events:
        issues.append("CRITICAL: matter has ZERO events in timeline — unreliable / not really active")
        return issues
    by_source = {}
    for e in events:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
    if "gmail" not in by_source:
        issues.append("WARN: matter has documents/deadlines but NO gmail correspondences — likely missing inbound/outbound emails")
    if "documents" in by_source and by_source["documents"] > 5 and "transactions" not in by_source:
        issues.append("WARN: matter has 5+ docs but NO transactions — filing/registration fees should have receipts")
    nodate = [e for e in events if not e["when"]]
    if nodate:
        issues.append(f"WARN: {len(nodate)} event(s) in timeline have no date — gap in timeline integrity")
    # Sorted check
    sorted_evs = sorted([e for e in events if e["when"]], key=lambda e: e["when"])
    if sorted_evs:
        most_recent = sorted_evs[-1]["when"]
        if isinstance(most_recent, datetime):
            most_recent = most_recent.date()
        gap_days = (date.today() - most_recent).days
        if gap_days > 60 and m.get("status") == "active":
            issues.append(f"WARN: active matter but no events in {gap_days} days — stale or untracked correspondence")
    return issues


def render_md(m, events, since=None, health_issues=None):
    today = date.today().strftime("%a %b %d, %Y")
    lines = [
        f"# Timeline — {m['matter_code']} ({m['title'] or '—'})",
        f"**Docket:** `{m['docket_number'] or '—'}` · **Case file:** `{m['case_file'] or '—'}` · **Current stage:** `{m['current_stage'] or '—'}`",
        f"**Generated:** {today}  ·  **Events:** {len(events)}" + (f"  ·  **Since:** {since}" if since else ""),
        "",
    ]

    if health_issues:
        lines.append("## 🩺 Health-test findings")
        lines.append("")
        for h in health_issues:
            lines.append(f"- {h}")
        lines.append("")

    # Group events by year-month for readability
    sortable = [e for e in events if e["when"]]
    undated  = [e for e in events if not e["when"]]
    sortable.sort(key=lambda e: e["when"])

    lines.append("## Chronological events")
    lines.append("")
    lines.append("| When | Kind | Who | What | Ref |")
    lines.append("|---|---|---|---|---|")
    for e in sortable:
        when = e["when"].isoformat() if hasattr(e["when"], "isoformat") else str(e["when"])
        what = (e["what"] or "")[:120].replace("|", "/")
        who  = (e["who"]  or "")[:50].replace("|", "/")
        lines.append(f"| `{when}` | `{e['kind']}` | {who} | {what} | `{e['ref']}` |")

    if undated:
        lines.append("")
        lines.append("## Undated events (date missing — data quality gap)")
        lines.append("")
        lines.append("| Kind | What | Ref |")
        lines.append("|---|---|---|")
        for e in undated:
            what = (e["what"] or "")[:120].replace("|", "/")
            lines.append(f"| `{e['kind']}` | {what} | `{e['ref']}` |")

    # Source breakdown
    by_src = {}
    for e in events:
        by_src[e["source"]] = by_src.get(e["source"], 0) + 1
    lines.append("")
    lines.append("## Source breakdown")
    lines.append("")
    for s, n in sorted(by_src.items(), key=lambda x: -x[1]):
        lines.append(f"- `{s}` — {n} events")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", help="matter_code (e.g., MWK-CV26360)")
    ap.add_argument("--case", help="case_file (e.g., MWK-001)")
    ap.add_argument("--docket", help="docket_number (e.g., 'CTN SL-2026-0218-1378')")
    ap.add_argument("--since", help="YYYY-MM-DD start date")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--health", action="store_true", help="only print health-check findings")
    ap.add_argument("--out", help="write to file path")
    args = ap.parse_args()

    if not (args.matter or args.case or args.docket):
        sys.exit("Usage: --matter | --case | --docket required")

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    matters = resolve_matter(cur, args.matter, args.case, args.docket)
    if not matters:
        sys.exit(f"No matter found for given input.")

    since = date.fromisoformat(args.since) if args.since else None
    all_output = []
    all_health = []
    for m in matters:
        events = fetch_events(cur, m, since=since)
        health = health_check(events, m)
        all_health.extend([(m["matter_code"], h) for h in health])
        if args.json:
            def _ser(o):
                if hasattr(o, "isoformat"): return o.isoformat()
                return str(o)
            all_output.append({
                "matter": dict(m),
                "events": events,
                "health_issues": health,
            })
        elif args.health:
            print(f"\n=== Health for {m['matter_code']} ({len(events)} events) ===")
            if not health:
                print("  ✓ no issues found")
            for h in health:
                print(f"  • {h}")
        else:
            md = render_md(m, events, since=args.since, health_issues=health)
            if args.out:
                Path(args.out).write_text(md)
                print(f"Written: {args.out} ({len(md):,} chars)")
            else:
                print(md)

    if args.json:
        def _ser(o):
            if hasattr(o, "isoformat"): return o.isoformat()
            return str(o)
        print(json.dumps(all_output, default=_ser, indent=2))

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
