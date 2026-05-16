#!/usr/bin/env python3
"""Layer 5 — Hyper-vigilance meta-agent.

Per [[feedback_hyper_vigilance_meta_agent]] + architecture review 2026-05-16.
Runs ~20 invariants hourly. Each invariant is a SQL query that SHOULD return zero
rows. Any non-zero row is a "gap" — surfaces as a queued Telegram inquiry.

The meta-agent is the system's immune system: it catches the imperceptible gaps
that humans don't notice until they're catastrophic (e.g., May 13 pretrial bug).

Cost: pure SQL. Zero LLM calls. Runs in <5s.

Usage:
  python3 meta_agent.py            # one cycle, prints findings
  python3 meta_agent.py --enqueue  # also enqueue inquiries for findings
  python3 meta_agent.py --json     # machine-readable output
"""
import argparse
import json
import sys
from datetime import datetime
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Each invariant: (id, severity, name, sql, message_template)
# Severity: P0 (jump queue) | P1 (urgent) | P2 (normal) | P3 (housekeeping)
# SQL MUST return zero rows for the invariant to hold. Non-zero rows = failure.
# message_template uses {n} for the count of failed rows.
INVARIANTS = [
    # ─── DEADLINE / STAGE INTEGRITY ──────────────────────────────────────
    dict(id="DEADLINE_STAGE_CONTRADICTION", severity="P0",
         name="Pending deadline contradicted by post-deadline filing",
         sql=r"""
            SELECT cd.id, cd.case_file, cd.title, cd.due_date,
                   COUNT(d.id) FILTER (WHERE d.doc_date_norm > cd.due_date) AS post_deadline_filings
              FROM case_deadlines cd
              JOIN documents d ON d.case_file = cd.case_file
             WHERE cd.status = 'pending'
               AND d.execution_status IN ('executed_filed','executed_notarized','government_issued')
               AND d.doc_date_norm > cd.due_date
             GROUP BY cd.id, cd.case_file, cd.title, cd.due_date
            HAVING COUNT(*) > 0
         """,
         msg="{n} pending deadline(s) have post-deadline filings — sentinel should have auto-completed."),

    dict(id="OVERDUE_NO_AUTO_COMPLETE_ATTEMPT", severity="P1",
         name="Deadline overdue >7 days without auto-complete attempt",
         sql=r"""
            SELECT cd.id, cd.title FROM case_deadlines cd
             WHERE cd.status = 'pending' AND cd.due_date < CURRENT_DATE - INTERVAL '7 days'
         """,
         msg="{n} deadline(s) overdue >7 days. Stage-awareness guard may be silent."),

    dict(id="DEADLINE_NULL_SOURCE", severity="P2",
         name="Active deadline with NULL source_doc_id",
         sql=r"""
            SELECT id, title FROM case_deadlines
             WHERE status='pending' AND source_doc_id IS NULL AND created_by != 'jonathan'
         """,
         msg="{n} pending deadline(s) have no source doc. Were they hallucinated like the May-13 incident?"),

    # ─── MATTER COMPLETENESS ─────────────────────────────────────────────
    dict(id="ORPHAN_CASE_FILE", severity="P1",
         name="case_file in documents but no matter row",
         sql=r"""
            SELECT DISTINCT d.case_file, COUNT(*) AS n_docs
              FROM documents d
             WHERE d.case_file IS NOT NULL
               AND d.case_file NOT IN ('unknown','Unknown','Owner')
               AND d.case_file NOT IN (SELECT case_file FROM matters WHERE case_file IS NOT NULL)
             GROUP BY d.case_file
         """,
         msg="{n} case_file value(s) have documents but no matter row. Auto-promote needed."),

    dict(id="MATTER_NO_STAGE", severity="P2",
         name="Active matter with NULL current_stage",
         sql=r"""
            SELECT matter_code, title FROM matters
             WHERE status='active' AND (current_stage IS NULL OR current_stage = '')
         """,
         msg="{n} active matter(s) have no current_stage set. Can't surface next step."),

    dict(id="MATTER_STALE_STAGE", severity="P3",
         name="Active matter stage not updated in 14 days",
         sql=r"""
            SELECT matter_code FROM matters
             WHERE status='active' AND stage_updated_at < NOW() - INTERVAL '14 days'
         """,
         msg="{n} matter(s) haven't had stage_updated_at refreshed in 14+ days."),

    dict(id="MATTER_NO_DOCS", severity="P3",
         name="Active matter referenced by zero documents",
         sql=r"""
            SELECT m.matter_code FROM matters m
             WHERE m.status='active'
               AND m.case_file IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM documents d
                                WHERE d.case_file = m.case_file
                                  AND (d.extracted_text ILIKE '%' || COALESCE(m.docket_number,'NEVERMATCH') || '%'
                                       OR m.docket_number IS NULL))
         """,
         msg="{n} active matter(s) have no documents referencing their docket."),

    # ─── CASE NUMBER DETECTION ───────────────────────────────────────────
    dict(id="ARTA_CASE_UNTRACKED", severity="P1",
         name="ARTA case number in corpus not in matters",
         sql=r"""
            WITH found AS (
              SELECT DISTINCT regexp_replace(
                       (regexp_matches(extracted_text, 'CTN\s*SL[\s\-]*\d{4}[\s\-]*\d{4}[\s\-]*\d{4}', 'g'))[1],
                       '\s+', '', 'g'
                     ) AS norm
                FROM documents
               WHERE extracted_text ~ 'CTN\s*SL[\s\-]*\d{4}'
            )
            SELECT norm AS arta_case FROM found
             WHERE norm NOT IN (
               SELECT regexp_replace(docket_number, '\s+', '', 'g')
                 FROM matters WHERE docket_number IS NOT NULL
             )
         """,
         msg="{n} ARTA case number(s) in corpus have no matter row."),

    # ─── INTAKE COMPLETENESS ─────────────────────────────────────────────
    dict(id="INTAKE_STALE", severity="P2",
         name="Open intake aged >7 days without response",
         sql=r"""
            SELECT id FROM stage_intake_response
             WHERE status IN ('open','partial') AND fired_at < NOW() - INTERVAL '7 days'
         """,
         msg="{n} intake(s) have been open >7 days. Re-prompt or close."),

    # ─── DATA QUALITY ────────────────────────────────────────────────────
    dict(id="DOC_DATE_UNPARSEABLE", severity="P3",
         name="documents.doc_date unparseable",
         sql="""SELECT id FROM documents WHERE doc_date_quality = 'unparseable'""",
         msg="{n} document(s) have unparseable doc_date strings."),

    dict(id="EXECUTED_FILED_NO_DATE", severity="P2",
         name="executed_filed doc with no parseable date",
         sql=r"""
            SELECT id, smart_filename FROM documents
             WHERE execution_status = 'executed_filed' AND doc_date_norm IS NULL
         """,
         msg="{n} executed_filed doc(s) have no parseable date — breaks stage-awareness."),

    dict(id="DUPLICATE_DOCKET", severity="P1",
         name="Multiple matters with same docket_number",
         sql=r"""
            SELECT docket_number, COUNT(*) FROM matters
             WHERE docket_number IS NOT NULL AND docket_number != ''
             GROUP BY docket_number HAVING COUNT(*) > 1
         """,
         msg="{n} docket number(s) appear on multiple matters — merge or distinguish."),

    # ─── EXTRACTION PROVENANCE ───────────────────────────────────────────
    dict(id="LOW_CONFIDENCE_PARTY_FILING", severity="P3",
         name="case_party_filing confidence < 0.4",
         sql="""SELECT id FROM case_party_filings WHERE confidence < 0.4""",
         msg="{n} party-filing classification(s) below 0.4 confidence. Run disambiguator."),

    dict(id="HALLUCINATION_LOG_FRESH", severity="P0",
         name="Hallucination logged in last 24h",
         sql="""SELECT id FROM hallucination_log WHERE occurred_at > NOW() - INTERVAL '24 hours'""",
         msg="{n} fresh hallucination(s) logged. Manual review required."),

    # ─── EXTRACTION INFRASTRUCTURE ───────────────────────────────────────
    dict(id="ALL_GEMINI_COOLED_LONG", severity="P2",
         name="All Gemini keys cooled >12h",
         sql=r"""
            SELECT key_label FROM gemini_key_state
             WHERE cooldown_until > NOW() + INTERVAL '12 hours'
         """,
         msg="{n} Gemini key(s) cooled >12h ahead. Extraction stalled — consider Claude fallback."),

    dict(id="HEARTBEAT_MISSING", severity="P1",
         name="A critical cron stopped emitting heartbeat",
         sql=r"""
            WITH expected AS (
              SELECT unnest(ARRAY['deadline-sentinel','drive-sync','gmail-watcher','tct-sweep']) AS src
            )
            SELECT src FROM expected
             WHERE src NOT IN (SELECT source FROM system_heartbeat
                                WHERE emitted_at > NOW() - INTERVAL '3 hours')
         """,
         msg="{n} expected cron heartbeat(s) missing in last 3h. Service may have crashed."),

    # ─── COST ────────────────────────────────────────────────────────────
    dict(id="DAILY_COST_THRESHOLD", severity="P2",
         name="Today's LLM cost > $5",
         sql=r"""
            SELECT 1 WHERE (
              SELECT COALESCE(SUM(cost_usd),0) FROM llm_calls
               WHERE called_at >= date_trunc('day', NOW())
            ) > 5.0
         """,
         msg="Today's LLM spend has crossed $5 threshold. Review."),

    # ─── QUEUE SANITY ────────────────────────────────────────────────────
    dict(id="MULTIPLE_ACTIVE_INQUIRIES", severity="P0",
         name="More than one tg_inquiry active (should be impossible)",
         sql="""SELECT id FROM tg_inquiry_queue WHERE status='active' OFFSET 1""",
         msg="{n} extra active inquiry rows — unique constraint should prevent this."),

    # ─── BACKTEST REGRESSIONS ────────────────────────────────────────────
    dict(id="BACKTEST_REGRESSION", severity="P1",
         name="Back-test failed in last 24h",
         sql=r"""
            SELECT test_id FROM back_test_runs
             WHERE passed = false AND run_at > NOW() - INTERVAL '24 hours'
         """,
         msg="{n} back-test failure(s) in last 24h. Truth-negotiator may have regressed."),

    # ─── TIMELINE INTEGRITY (per directive 2026-05-16: timelines are the system-health test) ──
    dict(id="MATTER_DOCS_NO_DATE", severity="P1",
         name="Matter has docs but their doc_date_norm is NULL — invisible in timeline",
         sql=r"""
            SELECT m.matter_code, COUNT(d.id) AS docs_undated
              FROM matters m
              JOIN documents d ON d.case_file = m.case_file
             WHERE m.status='active'
               AND d.doc_date_norm IS NULL
               AND d.execution_status IN ('executed_filed','executed_notarized','government_issued')
               AND (m.docket_number IS NULL OR d.extracted_text ILIKE '%' || m.docket_number || '%')
             GROUP BY m.matter_code
            HAVING COUNT(d.id) > 0
         """,
         msg="{n} matter(s) have executed_filed docs invisible in their timeline (no parseable date)."),

    dict(id="MATTER_GMAIL_NO_DOC", severity="P2",
         name="Matter has gmail correspondences with attachments but matching docs not yet extracted",
         sql=r"""
            SELECT m.matter_code, COUNT(gm.id) AS unextracted_attachments
              FROM matters m
              JOIN gmail_messages gm ON gm.case_file = m.case_file
             WHERE m.status='active'
               AND gm.has_attachments = true
               AND gm.document_id IS NULL
               AND m.docket_number IS NOT NULL
               AND (gm.subject ILIKE '%' || m.docket_number || '%' OR gm.body_plain ILIKE '%' || m.docket_number || '%')
             GROUP BY m.matter_code
            HAVING COUNT(gm.id) > 0
         """,
         msg="{n} matter(s) have gmail attachments still unextracted into documents. Run extract_email_attachments."),

    dict(id="ACTIVE_MATTER_TIMELINE_SPARSE", severity="P3",
         name="Active matter has fewer than 3 events in scoped timeline",
         sql=r"""
            WITH event_counts AS (
              SELECT m.matter_code,
                     (SELECT COUNT(*) FROM documents d
                       WHERE d.case_file = m.case_file
                         AND d.doc_date_norm IS NOT NULL
                         AND (m.docket_number IS NULL
                              OR d.extracted_text ILIKE '%' || m.docket_number || '%'))
                   + (SELECT COUNT(*) FROM gmail_messages gm
                       WHERE gm.case_file = m.case_file
                         AND m.docket_number IS NOT NULL
                         AND (gm.subject ILIKE '%' || m.docket_number || '%'
                              OR gm.body_plain ILIKE '%' || m.docket_number || '%'))
                  AS n_events
                FROM matters m
               WHERE m.status = 'active'
            )
            SELECT matter_code, n_events FROM event_counts WHERE n_events < 3
         """,
         msg="{n} active matter(s) have sparse timelines (<3 events scoped). Either docket-mismatch or genuinely empty."),
]


def severity_priority(sev: str) -> int:
    return {"P0": 0, "P1": 10, "P2": 20, "P3": 30}.get(sev, 30)


def enqueue_consolidated_digest(cur, failures: list):
    """Enqueue ONE consolidated gap_digest inquiry covering ALL failures.

    Per feedback_telegram_inquiry_queue (one-at-a-time rule) + Jonathan's
    'I recommend consolidating' directive 2026-05-16: bundle every failed
    invariant into a single digest message, never fire N separate inquiries.

    Dedup: if a queued/active gap_digest with the same failure-set already exists,
    don't duplicate. Use a hash of failure IDs as the dedup key.
    """
    if not failures:
        return False
    inv_ids = sorted(f["id"] for f in failures)
    dedup_key = "digest:" + ",".join(inv_ids)[:200]
    cur.execute("""
        SELECT id FROM tg_inquiry_queue
         WHERE kind='gap_alert' AND notes = %s AND status IN ('queued','active')
    """, (dedup_key,))
    if cur.fetchone():
        return False

    # Highest severity drives the queue priority
    sev_order = ["P0", "P1", "P2", "P3"]
    top_sev = min((f["severity"] for f in failures), key=lambda s: sev_order.index(s) if s in sev_order else 99)

    lines = [f"⚠️ <b>Meta-agent gap digest — {len(failures)} finding(s)</b>",
             f"<i>Highest severity: {top_sev}</i>", ""]
    # Group by severity for readability
    by_sev = {}
    for f in failures:
        by_sev.setdefault(f["severity"], []).append(f)
    for sev in sev_order:
        if sev not in by_sev: continue
        sev_emoji = {"P0": "🚨", "P1": "🆘", "P2": "🟠", "P3": "🟡"}.get(sev, "•")
        lines.append(f"<b>{sev_emoji} {sev}</b>")
        for f in by_sev[sev]:
            lines.append(f"  • <b>{f['name']}</b>")
            lines.append(f"    {f['message']}")
            for ev in f.get("evidence", [])[:2]:
                ev_str = str(ev)[:160].replace("<", "&lt;").replace(">", "&gt;")
                lines.append(f"    <code>{ev_str}</code>")
        lines.append("")
    lines.append("<i>Reply /skip to dismiss, /done when resolved, or describe action taken.</i>")
    html = "\n".join(lines)[:4000]  # Telegram cap

    cur.execute("""
        INSERT INTO tg_inquiry_queue
          (kind, priority, source_table, composed_html, notes)
        VALUES ('gap_alert', %s, 'meta_agent', %s, %s)
    """, (severity_priority(top_sev), html, dedup_key))
    return True


def run_cycle(enqueue=False, json_out=False, verbose=True):
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    findings = []
    failures = []
    for inv in INVARIANTS:
        try:
            cur.execute(inv["sql"])
            rows = cur.fetchall()
        except Exception as e:
            findings.append(dict(id=inv["id"], severity="P0", name=inv["name"],
                                 status="sql_error", error=str(e)[:300]))
            continue
        if not rows:
            findings.append(dict(id=inv["id"], severity=inv["severity"], name=inv["name"],
                                 status="pass", count=0))
        else:
            f = dict(id=inv["id"], severity=inv["severity"], name=inv["name"],
                     status="fail", count=len(rows),
                     message=inv["msg"].format(n=len(rows)),
                     evidence=[dict(r) for r in rows[:5]])
            findings.append(f)
            failures.append(f)

    enqueued = 0
    if enqueue and failures:
        if enqueue_consolidated_digest(cur, failures):
            enqueued = 1

    if json_out:
        # Convert dates/datetimes to iso strings for json
        def _ser(o):
            if hasattr(o, "isoformat"): return o.isoformat()
            return str(o)
        print(json.dumps(findings, default=_ser, indent=2))
    elif verbose:
        print(f"=== Meta-agent cycle {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===")
        print(f"  invariants: {len(INVARIANTS)}  passed: {sum(1 for f in findings if f['status']=='pass')}"
              f"  failed: {sum(1 for f in findings if f['status']=='fail')}"
              f"  errors: {sum(1 for f in findings if f['status']=='sql_error')}")
        for f in findings:
            if f["status"] == "fail":
                print(f"  ✗ [{f['severity']}] {f['name']} — {f['message']}")
                for ev in f.get("evidence", [])[:3]:
                    print(f"      {str(ev)[:120]}")
            elif f["status"] == "sql_error":
                print(f"  ! ERR  {f['id']}: {f['error'][:100]}")
        if enqueue:
            print(f"\n  enqueued {enqueued} new inquiry(ies)")

    # Heartbeat
    try:
        cur.execute("""
            INSERT INTO system_heartbeat (source, status, metadata)
            VALUES ('meta-agent', 'ok', %s::jsonb)
        """, (json.dumps({"passed": sum(1 for f in findings if f["status"]=="pass"),
                          "failed": sum(1 for f in findings if f["status"]=="fail"),
                          "enqueued": enqueued}),))
    except Exception:
        pass

    cur.close(); conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enqueue", action="store_true", help="Enqueue Telegram inquiries for failures")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()
    run_cycle(enqueue=args.enqueue, json_out=args.json, verbose=not args.json)


if __name__ == "__main__":
    main()
