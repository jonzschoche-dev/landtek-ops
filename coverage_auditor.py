#!/usr/bin/env python3
"""Coverage auditor — Layer C of the bible architecture (deploy_152).

For each source table that feeds client_history, computes:
  - rows-in-source (per client)
  - rows-in-bible referencing that source
  - delta = missing IDs, classified by reason

Reasons:
  - upstream_no_date       : source row lacks the date column the scanner needs
  - upstream_no_case_file  : source row has no case_file (won't map to a client)
  - upstream_unresolved_client : case_file exists but matters/clients lookup fails
  - scanner_skipped        : all upstream prereqs present but bible row absent
                             (REAL gap — scanner bug or sequencing issue)

Output:
  - coverage_audit_findings table (audit trail)
  - /root/landtek/drafts/coverage_audit_<date>.md (human-readable)
  - tg_inquiry_queue 'gap_alert' row IF any 'scanner_skipped' findings exist

Per Jonathan 2026-05-17 review gate: "output the list of missing documents
... so we can see why they didn't ingest before we move to Layers B, D, E."
"""
import psycopg2, psycopg2.extras
from datetime import date
from pathlib import Path

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Source-table definitions: how each table maps to bible rows.
# (table, id_col, case_file_col, date_col, extra_join_sql)
SOURCES = [
    {
        "table": "documents",
        "id_col": "id",
        "case_file_col": "case_file",
        "date_col": "doc_date_norm",
        "extra_select": "classification, COALESCE(smart_filename, original_filename) AS label",
    },
    {
        "table": "gmail_messages",
        "id_col": "id",
        "case_file_col": "case_file",
        "date_col": "COALESCE(received_at, sent_at)",
        "extra_select": "subject, from_addr",
    },
    {
        "table": "transactions",
        "id_col": "id",
        "case_file_col": "case_file",
        "date_col": "tx_date",
        "extra_select": "category, amount",
    },
    {
        "table": "case_deadlines",
        "id_col": "id",
        "case_file_col": "case_file",
        "date_col": "due_date",
        "extra_select": "title, status",
    },
    {
        "table": "title_transfers",
        "id_col": "id",
        "case_file_col": "case_file",
        "date_col": "transfer_date",
        "extra_select": "transferor, transferee_name",
    },
]


def ensure_findings_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS coverage_audit_findings (
            id           bigserial PRIMARY KEY,
            audit_run_at timestamptz NOT NULL DEFAULT NOW(),
            client_code  text,
            source_table text NOT NULL,
            source_id    text NOT NULL,
            reason       text NOT NULL,
            extra        jsonb DEFAULT '{}'::jsonb
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cov_audit_run
        ON coverage_audit_findings (audit_run_at DESC, reason)
    """)


def audit_source(cur, src, client_code):
    """Audit one source table for one client. Returns dict of counts + missing IDs."""
    table = src["table"]; id_col = src["id_col"]
    case_file_col = src["case_file_col"]; date_col = src["date_col"]
    extra = src["extra_select"]

    # Resolve which case_files belong to this client
    cur.execute("""
        SELECT DISTINCT case_file FROM matters WHERE client_code = %s
         UNION
        SELECT DISTINCT case_file FROM clients WHERE client_code = %s
    """, (client_code, client_code))
    case_files = [r["case_file"] for r in cur.fetchall() if r["case_file"]]
    if not case_files:
        return None

    # Total source rows for this client
    cur.execute(f"""
        SELECT {id_col} AS sid, {case_file_col} AS cf, {date_col} AS dt, {extra}
          FROM {table}
         WHERE {case_file_col} = ANY(%s)
    """, (case_files,))
    src_rows = cur.fetchall()
    total = len(src_rows)
    if total == 0:
        return None

    # Bible rows referencing this source for this client
    cur.execute("""
        SELECT source_id FROM client_history
         WHERE source_table = %s AND client_code = %s
    """, (table, client_code))
    in_bible = {r["source_id"] for r in cur.fetchall()}

    counts = {"total": total, "in_bible": 0, "no_date": 0,
              "no_case_file": 0, "scanner_skipped": 0}
    missing = []
    for r in src_rows:
        sid = str(r["sid"])
        if sid in in_bible:
            counts["in_bible"] += 1
            continue
        # Classify why missing
        if not r["cf"]:
            counts["no_case_file"] += 1
            reason = "upstream_no_case_file"
        elif not r["dt"]:
            counts["no_date"] += 1
            reason = "upstream_no_date"
        else:
            counts["scanner_skipped"] += 1
            reason = "scanner_skipped"
        missing.append({"sid": sid, "reason": reason,
                        "preview": {k: str(v)[:120] for k, v in r.items()
                                     if k not in ("sid",) and v is not None}})

    return {"table": table, "client": client_code, "counts": counts, "missing": missing}


def audit_all_clients(cur):
    cur.execute("SELECT DISTINCT client_code FROM clients WHERE client_code IS NOT NULL")
    clients = [r["client_code"] for r in cur.fetchall()]
    # Also union from matters in case clients table is sparse
    cur.execute("SELECT DISTINCT client_code FROM matters WHERE client_code IS NOT NULL")
    for r in cur.fetchall():
        if r["client_code"] not in clients:
            clients.append(r["client_code"])
    return clients


def run(verbose=True):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_findings_table(cur)

    clients = audit_all_clients(cur)
    today = date.today().isoformat()
    out = [f"# Coverage Audit — {today}", "",
           f"_Bible architecture, Layer C. Source-row → client_history coverage._\n"]

    total_scanner_skipped = 0
    total_upstream_gaps = 0
    findings_to_log = []

    for client in clients:
        out.append(f"\n## Client: `{client}`")
        for src in SOURCES:
            res = audit_source(cur, src, client)
            if not res:
                continue
            c = res["counts"]
            pct = (c["in_bible"] / c["total"] * 100) if c["total"] else 0
            line = (f"- **{src['table']}**: {c['in_bible']}/{c['total']} in bible "
                    f"({pct:.0f}%) · "
                    f"no_date={c['no_date']} · "
                    f"no_case_file={c['no_case_file']} · "
                    f"**scanner_skipped={c['scanner_skipped']}**")
            out.append(line)
            if verbose:
                print(f"  {client} / {src['table']}: {line[2:]}")
            total_scanner_skipped += c["scanner_skipped"]
            total_upstream_gaps += c["no_date"] + c["no_case_file"]
            # Log each missing row
            for m in res["missing"]:
                findings_to_log.append({
                    "client": client, "table": src["table"],
                    "sid": m["sid"], "reason": m["reason"],
                    "extra": psycopg2.extras.Json(m["preview"]),
                })

    # Persist findings (clear last run, write new)
    cur.execute("DELETE FROM coverage_audit_findings WHERE audit_run_at < NOW() - INTERVAL '30 days'")
    for f in findings_to_log:
        cur.execute("""
            INSERT INTO coverage_audit_findings
              (client_code, source_table, source_id, reason, extra)
            VALUES (%s, %s, %s, %s, %s)
        """, (f["client"], f["table"], f["sid"], f["reason"], f["extra"]))

    # Summary section
    out.append("\n---\n## Summary")
    out.append(f"- **Total missing rows:** {len(findings_to_log)}")
    out.append(f"- **Upstream gaps** (no date / no case_file — extraction backlog): {total_upstream_gaps}")
    out.append(f"- **Scanner-skipped** (real gaps — all upstream OK but bible empty): {total_scanner_skipped}")
    if total_scanner_skipped == 0:
        out.append("\n✅ **No real scanner gaps.** All missing rows are upstream backlog "
                   "(date or case_file extraction needed).")
    else:
        out.append(f"\n⚠️ **{total_scanner_skipped} scanner-skipped rows need investigation.** "
                   "Run `SELECT * FROM coverage_audit_findings WHERE reason='scanner_skipped' "
                   "ORDER BY audit_run_at DESC LIMIT 30` to inspect.")

    # Top 10 extraction-backlog items per client (most impactful since these are unblockable)
    out.append("\n## Top backlog items (run date-extraction or case-file backfill next)")
    cur.execute("""
        SELECT client_code, source_table, source_id, reason, extra
          FROM coverage_audit_findings
         WHERE audit_run_at >= NOW() - INTERVAL '1 hour'
           AND reason IN ('upstream_no_date','upstream_no_case_file')
         ORDER BY client_code, source_table, source_id::int
         LIMIT 20
    """)
    for r in cur.fetchall():
        e = r["extra"] or {}
        label = e.get("label") or e.get("subject") or e.get("title") or e.get("category") or ""
        out.append(f"  - `{r['client_code']}/{r['source_table']}#{r['source_id']}` "
                   f"({r['reason']}) — {str(label)[:80]}")

    report = "\n".join(out)
    Path("/root/landtek/drafts").mkdir(exist_ok=True)
    outpath = Path(f"/root/landtek/drafts/coverage_audit_{today}.md")
    outpath.write_text(report)
    print(f"\nWrote {outpath} ({len(report):,} chars)")

    # If any real scanner gaps → enqueue gap_alert
    if total_scanner_skipped > 0:
        alert_html = (
            f"⚠️ <b>Coverage audit — {total_scanner_skipped} scanner-skipped rows</b>\n"
            f"<i>{today} · bible architecture coverage check</i>\n\n"
            f"These are rows with all upstream prerequisites met (case_file + date) "
            f"that nonetheless aren't in client_history. Likely scanner bug.\n\n"
            f"See <code>/root/landtek/drafts/coverage_audit_{today}.md</code>"
        )
        cur.execute("""
            INSERT INTO tg_inquiry_queue
              (kind, priority, source_table, composed_html, notes)
            VALUES ('gap_alert', 10, 'coverage_audit', %s,
                    'real scanner gaps detected (deploy_152)')
        """, (alert_html,))
        print("  enqueued gap_alert")

    return outpath, total_scanner_skipped, total_upstream_gaps


if __name__ == "__main__":
    run()
