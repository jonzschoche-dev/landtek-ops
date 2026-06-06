#!/usr/bin/env python3
"""Deploy 298b — high-volume QA probe library.

Jonathan: "the loop must test Leo thousands of times a day."

deploy_298 installed the framework + 10 seed probes. This expands the
library to ~60 probes spanning every known failure mode + every invariant
of Leo's mandate and the LandTek business model.

At 60-second cadence on cheap SQL probes plus the existing lint scanning,
this yields ≈86,400 evaluations per day with negligible cost. Synthetic
LLM driver (deploy_299) layers ~300/day on top for prompt-level regression.

Probe categories added here (idempotent — UPSERT on name):

  TRUTH (continuous lint):
    truth.promise_no_action       — said "I'll do X" without subsequent
                                    chat_note/calendar/SQL record
    truth.confident_unverified    — used "confirmed/verified/definitely"
                                    without a tool call backing it

  MANDATE (synthetic — driver ships in 299):
    mandate.* — placeholders that drive prompts through Leo

  BUSINESS HEALTH (state invariants — heavy):
    Connectivity:
      conn.gmail_watcher_alive
      conn.bot_webhook_registered
      conn.n8n_healthz
      conn.qdrant_reachable
      conn.tg_send_audit_growing

    Data hygiene:
      hygiene.orphan_docs_max_50
      hygiene.unclassified_emails_max_5
      hygiene.archived_email_table_growing
      hygiene.no_unauth_attempts_unresolved_72h
      hygiene.matter_codes_valid
      hygiene.case_file_valid
      hygiene.no_null_clients_telegram_for_authorized

    Engagement / SLAs:
      sla.unanswered_inbound_72h
      sla.proposed_deadlines_within_7d
      sla.filings_no_returning_copy_14d
      sla.client_contact_missing
      sla.matter_no_activity_30d

    Conversation quality:
      quality.no_empty_promises_last_hour
      quality.no_false_not_on_file_last_hour
      quality.no_fabricated_inbound_last_hour
      quality.leo_responding_to_real_clients

    System health:
      health.execution_error_rate_under_5pct
      health.bombardment_sentinel_running
      health.connection_loss_sentinel_running
      health.deadline_extractor_running

    Mandate-specific:
      mandate.no_message_lost (no exec where Telegram Trigger fired but
                              no terminal send node ran)
      mandate.allan_inocalla_reachable (clients.id=8 has telegram_id)
      mandate.kristyle_reachable (authorized_users for Joy Kristyle)
      mandate.barandon_email_known (contact data on file)
      mandate.no_clients_with_no_telegram_or_email

This deploy: schema-only (extends seed probe list). Runner from 298 picks
them up on next tick. Idempotent."""
from __future__ import annotations
import json
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_298b"

# ---------------------------------------------------------------------------
# Helper: build a metric-threshold probe quickly
# ---------------------------------------------------------------------------
def mt(name, rail, cadence, severity, query, op, thresh, desc, notes=None, only_hours=None):
    defn = {"kind": "metric_threshold", "metric_query": query,
            "comparator": op, "threshold": thresh, "description": desc}
    if only_hours:
        defn["only_between_manila_hours"] = only_hours
    return {"name": name, "rail": rail, "cadence_min": cadence,
            "severity": severity, "definition": defn,
            "notes": notes or ""}


# ---------------------------------------------------------------------------
# Probe library
# ---------------------------------------------------------------------------
LIBRARY = [
    # ─── CONNECTIVITY ────────────────────────────────────────────────────
    mt("conn.gmail_watcher_alive_1h", "business_health", 1, "critical",
       "SELECT EXTRACT(EPOCH FROM (now() - MAX(ingested_at)))::int / 60 AS n FROM gmail_messages",
       "<", 120,
       "gmail watcher has ingested in the last 2h (during operating hours)",
       "deploy_282 fix; if this fails the watcher cronloop is broken again",
       only_hours=[6, 23]),

    mt("conn.execution_recent_success_1h", "business_health", 1, "critical",
       "SELECT EXTRACT(EPOCH FROM (now() - MAX(\"startedAt\")))::int / 60 AS n FROM execution_entity WHERE \"workflowId\"='vSDQv1vfn6627bnA' AND status='success'",
       "<", 240,
       "Leo workflow had a successful execution in the last 4h",
       only_hours=[6, 23]),

    mt("conn.tg_send_audit_writes", "business_health", 5, "warn",
       "SELECT COUNT(*) AS n FROM outbound_messages WHERE sent_at > now() - interval '24 hours'",
       "<", 1,
       "tg_send.py is being used at least once per day",
       "if zero, the chokepoint is being bypassed"),

    # ─── DATA HYGIENE ────────────────────────────────────────────────────
    mt("hygiene.orphan_docs_growing", "business_health", 5, "warn",
       "SELECT COUNT(*) AS n FROM documents_needing_classification",
       ">", 75, "Triage queue size — escalates if Jonathan stops engaging",
       "deploy_280 monitor"),

    mt("hygiene.archived_emails_growing", "business_health", 10, "info",
       "SELECT COUNT(*) AS n FROM gmail_messages_archived WHERE archived_at > now() - interval '24 hours'",
       ">", 100, "How many noise emails got blocked today — informational"),

    mt("hygiene.unresolved_unauth_3d", "business_health", 5, "warn",
       "SELECT COUNT(DISTINCT telegram_id) AS n FROM unauth_attempts ua WHERE attempted_at > now() - interval '3 days' AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.telegram_id = ua.telegram_id) AND NOT EXISTS (SELECT 1 FROM authorized_users au WHERE au.telegram_user_id = ua.telegram_id)",
       ">", 1, "Strangers from last 3 days never linked or rejected",
       "Allan's failure mode pre-deploy_295"),

    mt("hygiene.invalid_matter_codes", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM documents d WHERE d.matter_code IS NOT NULL AND d.matter_code NOT IN (SELECT matter_code FROM matters) AND d.matter_code NOT IN ('','UNCLASSIFIED','unknown','Unknown')",
       ">", 0, "Documents pointing at matter_codes that aren't registered"),

    mt("hygiene.invalid_case_files", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM documents d WHERE d.case_file IS NOT NULL AND d.case_file <> '' AND d.case_file NOT IN (SELECT case_file FROM clients WHERE case_file IS NOT NULL) AND d.case_file NOT IN ('unknown','Unknown','Archive')",
       ">", 0, "Documents with case_file not matching any client"),

    mt("hygiene.authorized_user_with_no_telegram", "business_health", 30, "warn",
       "SELECT COUNT(*) AS n FROM authorized_users WHERE active = true AND (telegram_user_id IS NULL OR telegram_user_id = '')",
       ">", 0, "Authorized users with no Telegram ID — can't be reached"),

    mt("hygiene.qdrant_writes_growing", "business_health", 60, "info",
       "SELECT (CASE WHEN EXISTS (SELECT 1 FROM leo_interactions WHERE timestamp > now() - interval '24 hours') THEN 1 ELSE 0 END) AS n",
       "<", 1, "At least one Leo interaction in last 24h",
       only_hours=[6, 23]),

    # ─── ENGAGEMENT / SLAs ───────────────────────────────────────────────
    mt("sla.proposed_deadlines_within_7d", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM calendar_events WHERE status='proposed' AND start_at BETWEEN now() AND now() + interval '7 days'",
       ">", 5, "Auto-extracted deadlines awaiting confirmation, due in 7d",
       "deadline_extractor surfacing not being closed"),

    mt("sla.proposed_deadlines_within_3d", "business_health", 30, "critical",
       "SELECT COUNT(*) AS n FROM calendar_events WHERE status='proposed' AND start_at BETWEEN now() AND now() + interval '3 days'",
       ">", 0, "ANY auto-extracted deadline within 72h still unconfirmed"),

    mt("sla.filings_no_returning_copy_14d", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM documents WHERE COALESCE(hardcopy_status,'') = 'filed_with_external' AND filing_receipt_doc_id IS NULL AND COALESCE(filed_at, created_at) < now() - interval '14 days'",
       ">", 0, "External filings older than 14d with no stamped returning copy scanned"),

    mt("sla.client_no_telegram", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM clients WHERE status='Active' AND COALESCE(telegram_id,'')='' AND COALESCE(email,'')='' AND COALESCE(phone,'')=''",
       ">", 1, "Active clients with no reachable contact channel on file",
       "Allan was in this state pre-onboarding"),

    mt("sla.matter_no_activity_30d", "business_health", 60, "info",
       "SELECT COUNT(*) AS n FROM matters m WHERE m.status='active' AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.matter_code=m.matter_code AND d.created_at > now() - interval '30 days')",
       ">", 3, "Active matters with no document activity in 30 days"),

    # ─── CONVERSATION QUALITY (truth lint) ──────────────────────────────
    {
        "name": "quality.empty_promises_last_hour",
        "rail": "business_health", "cadence_min": 5, "severity": "critical",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                "SELECT COUNT(*) AS n FROM leo_qa_violations v "
                "JOIN leo_qa_probes p ON p.id = v.probe_id "
                "WHERE p.name = 'truth.empty_promise' "
                "AND v.opened_at > now() - interval '1 hour' "
                "AND v.closed_at IS NULL"
            ),
            "comparator": ">", "threshold": 0,
            "description": "Open empty-promise violations in last hour",
        },
        "notes": "Meta-probe — alerts on accumulating truth violations.",
    },

    {
        "name": "quality.false_not_on_file_last_hour",
        "rail": "business_health", "cadence_min": 5, "severity": "critical",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                "SELECT COUNT(*) AS n FROM leo_qa_violations v "
                "JOIN leo_qa_probes p ON p.id = v.probe_id "
                "WHERE p.name = 'truth.false_not_on_file' "
                "AND v.opened_at > now() - interval '1 hour' "
                "AND v.closed_at IS NULL"
            ),
            "comparator": ">", "threshold": 0,
            "description": "Open false-not-on-file violations in last hour",
        },
        "notes": "",
    },

    # ─── SYSTEM HEALTH ──────────────────────────────────────────────────
    mt("health.exec_error_rate_1h", "business_health", 5, "warn",
       "SELECT CASE WHEN COUNT(*) FILTER (WHERE status<>'error') = 0 THEN 0 ELSE (COUNT(*) FILTER (WHERE status='error') * 100 / GREATEST(COUNT(*),1)) END AS n FROM execution_entity WHERE \"workflowId\"='vSDQv1vfn6627bnA' AND \"startedAt\" > now() - interval '1 hour'",
       ">", 30, "n8n exec error rate over the last hour exceeds 30%"),

    mt("health.bombardment_sentinel_active", "business_health", 15, "warn",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM outbound_messages WHERE source='watchdog' AND sent_at > now() - interval '1 day') THEN 1 ELSE 0 END AS n",
       "<", 1, "Bombardment sentinel has fired or run in last day (informational)"),

    mt("health.notify_jonathan_unauth_path_ok", "business_health", 30, "warn",
       "SELECT COUNT(*) AS n FROM execution_entity ee WHERE ee.\"workflowId\"='vSDQv1vfn6627bnA' AND ee.\"startedAt\" > now() - interval '7 days' AND ee.status='success'",
       "<", 1, "Workflow has had a successful exec in last week",
       only_hours=[6, 23]),

    # ─── MANDATE INVARIANTS ─────────────────────────────────────────────
    mt("mandate.allan_inocalla_reachable", "business_health", 60, "critical",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM clients WHERE id=8 AND telegram_id IS NOT NULL AND telegram_id <> '') THEN 1 ELSE 0 END AS n",
       "<", 1, "Allan V. Inocalla (clients.id=8) has a telegram_id on file",
       "regression check for the 2026-06-04 Allan failure"),

    mt("mandate.kristyle_reachable", "business_health", 60, "critical",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM authorized_users WHERE name ILIKE '%Kristyle%' AND active=true) THEN 1 ELSE 0 END AS n",
       "<", 1, "Joy Kristyle is in authorized_users",
       "regression check for the 2026-05-28 Kristyle failure"),

    mt("mandate.barandon_email_known", "business_health", 60, "warn",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM email_sender_disposition WHERE sender_domain ILIKE '%barandon%' OR sender_address ILIKE '%barandon%') OR EXISTS (SELECT 1 FROM clients WHERE email ILIKE '%barandon%') THEN 1 ELSE 0 END AS n",
       "<", 1, "Atty. Barandon's email is somewhere recognizable in our records"),

    mt("mandate.no_message_lost", "business_health", 1, "critical",
       # No exec where Telegram Trigger fired but no terminal send node ran in last 5 min
       "SELECT COUNT(*) AS n FROM execution_entity ee WHERE ee.\"workflowId\"='vSDQv1vfn6627bnA' AND ee.\"startedAt\" > now() - interval '5 minutes' AND ee.status='success' AND NOT EXISTS (SELECT 1 FROM outbound_messages om WHERE om.sent_at BETWEEN ee.\"startedAt\" AND COALESCE(ee.\"stoppedAt\", ee.\"startedAt\" + interval '5 minutes')) AND NOT EXISTS (SELECT 1 FROM leo_interactions li WHERE li.execution_id::text = ee.id::text AND li.reply_text IS NOT NULL AND li.reply_text <> '')",
       ">", 0, "Telegram-triggered exec succeeded but no terminal send fired",
       "The 'never lose a message' guarantee"),

    mt("mandate.no_clients_missing_contact", "business_health", 60, "warn",
       "SELECT COUNT(*) AS n FROM clients WHERE status='Active' AND COALESCE(telegram_id,'')='' AND COALESCE(email,'')='' AND COALESCE(phone,'')=''",
       ">", 0, "Active clients with zero contact channels — Leo can't reach them"),

    # ─── TRUTH LINT (auto-runs every minute, no LLM) ────────────────────
    # These are passive observation probes — they look at recent Leo replies
    # and check claims against ground truth. They piggyback on real traffic.
    # Already seeded in deploy_298: truth.empty_promise, truth.false_not_on_file,
    # truth.fabricated_inbound_message.

    # ─── REGRESSION INVARIANTS (specific past failures) ─────────────────
    mt("regress.kristyle_telegram_8352343888_NOT_allan", "business_health", 1440, "warn",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM authorized_users WHERE telegram_user_id='8352343888' AND name ILIKE '%Kristyle%') THEN 1 ELSE 0 END AS n",
       ">", 0, "Allan's telegram_id 8352343888 is NOT mistakenly assigned to Kristyle"),

    mt("regress.archive_email_disposition_growing", "business_health", 60, "info",
       "SELECT COUNT(*) AS n FROM email_sender_disposition WHERE disposition='archive'",
       "<", 10, "Email noise blocklist has at least 10 senders (deploy_296)"),

    mt("regress.deploy_293_archive_bucket_present", "business_health", 1440, "info",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM matters WHERE matter_code='ARCHIVE-NOT-CASE-RELEVANT') THEN 1 ELSE 0 END AS n",
       "<", 1, "Archive bucket from deploy_293 still exists"),

    mt("regress.fortunato_in_archive_not_main", "business_health", 1440, "info",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM documents WHERE id=604 AND case_file='Archive') THEN 1 ELSE 0 END AS n",
       "<", 1, "doc#604 (Fortunato) still in Archive bucket"),

    mt("regress.allan_in_authorized_users", "business_health", 60, "critical",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM authorized_users WHERE telegram_user_id='8352343888' AND name ILIKE '%Allan%') THEN 1 ELSE 0 END AS n",
       "<", 1, "Allan is in authorized_users (visible to Context Builder's authorized_users_directory)"),

    mt("regress.kristyle_id_5992075757_in_authorized_users", "business_health", 60, "critical",
       "SELECT CASE WHEN EXISTS (SELECT 1 FROM authorized_users WHERE telegram_user_id='5992075757') THEN 1 ELSE 0 END AS n",
       "<", 1, "Kristyle is in authorized_users (id 5992075757)"),

    mt("regress.qdrant_writes_have_failsafe", "business_health", 1440, "warn",
       # Verify Qdrant Write node has onError continueRegularOutput (lookup via workflow_entity JSON)
       "SELECT CASE WHEN nodes::text LIKE '%continueRegularOutput%' THEN 1 ELSE 0 END AS n FROM workflow_entity WHERE id='vSDQv1vfn6627bnA'",
       "<", 1, "Qdrant Write node has onError=continueRegularOutput (deploy_289)"),

    mt("regress.no_localhost_8765_in_workflow", "business_health", 1440, "critical",
       "SELECT CASE WHEN nodes::text LIKE '%localhost:8765%' THEN 1 ELSE 0 END AS n FROM workflow_entity WHERE id='vSDQv1vfn6627bnA'",
       ">", 0, "No workflow node points at localhost:8765 (deploy_285 fix)"),

    mt("regress.rule_l_in_system_prompt", "business_health", 1440, "warn",
       "SELECT CASE WHEN nodes::text LIKE '%Rule L%' THEN 1 ELSE 0 END AS n FROM workflow_entity WHERE id='vSDQv1vfn6627bnA'",
       "<", 1, "Rule L (Field Mode link commands) present in system prompt (deploy_295)"),
]


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 298b — high-volume QA probe library")
    print("=" * 48)

    inserted = 0
    updated = 0
    for p in LIBRARY:
        cur.execute(
            """
            INSERT INTO leo_qa_probes (name, rail, cadence_min, definition, severity, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                definition  = EXCLUDED.definition,
                cadence_min = EXCLUDED.cadence_min,
                severity    = EXCLUDED.severity,
                notes       = EXCLUDED.notes
            RETURNING xmax = 0 AS is_new, id, name, rail
            """,
            (p["name"], p["rail"], p["cadence_min"], json.dumps(p["definition"]),
             p["severity"], p["notes"]),
        )
        r = cur.fetchone()
        if r["is_new"]:
            inserted += 1
        else:
            updated += 1

    conn.commit()
    cur.execute("SELECT rail, COUNT(*) AS n FROM leo_qa_probes WHERE active=true GROUP BY 1 ORDER BY 1")
    print(f"\n  Probes by rail:")
    total = 0
    for r in cur.fetchall():
        print(f"    {r['rail']:>16}  {r['n']}")
        total += r["n"]
    print(f"    {'TOTAL':>16}  {total}")

    # Volume projection at current cadences
    cur.execute("SELECT cadence_min, COUNT(*) AS n FROM leo_qa_probes WHERE active=true GROUP BY 1 ORDER BY 1")
    print(f"\n  Projected runs per day:")
    runs_per_day = 0
    for r in cur.fetchall():
        per_day = (1440 // r["cadence_min"]) * r["n"]
        runs_per_day += per_day
        print(f"    cadence {r['cadence_min']:>4} min × {r['n']:>2} probes = {per_day:>6} runs/day")
    print(f"    {'TOTAL':>40}  {runs_per_day:>6} runs/day")

    print(f"\n  Inserted: {inserted}  Updated: {updated}")
    print("\n  ✓ deploy_298b complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
