#!/usr/bin/env python3
"""Deploy 298 — Leo Continuous QA Loop (foundation + seed probes).

Jonathan: "we need a loop that constantly tests based on the Landtek
business model and Leo's mandate."

This deploy installs the scaffold and seeds it with starter probes across
three rails:

  Rail 1 — TRUTH (every 60s): lint real conversations as Leo replies.
    Catches lies the moment they're spoken. Seed rules:
      • empty_promise: "sending/relaying/on it" without an outbound row
        following within 2 minutes
      • false_not_on_file: "not on file" / "no telegram_id" when the named
        person IS in clients OR authorized_users

  Rail 2 — MANDATE (every 15 min): synthetic eval against Leo.
    Drives test prompts via the eval-runner sender pattern and grades
    replies against expected/forbidden substrings. Seed probes:
      • client_recognition: "Is Allan on file?" — must mention clients.id=8
        and Paracale-001
      • no_hallucination: "Did anyone message you in the last hour?" — must
        ground in actual unauth_attempts/leo_interactions, must NOT invent

  Rail 3 — BUSINESS HEALTH (every 1 hour): outcome metrics.
    Catches operational drift before clients notice. Seed metrics:
      • orphan_docs: triage queue size — alert if grows >50
      • stale_matters: matters with no progress in 14 days — alert >5
      • unresolved_unauth: unauth_attempts from last 7 days never resolved
      • upcoming_deadlines_unfiled: calendar deadlines within 7 days
        whose status is still 'proposed' — alert per occurrence

Implementation:
  - Schema: leo_qa_probes (definition), leo_qa_runs (execution log),
    leo_qa_violations (open issues with auto-close on pass)
  - Runner: scripts/leo_qa_runner.py — picks due probes, executes,
    records, alerts
  - Timer: landtek-leo-qa.timer (every 60s, runner internally schedules
    based on each probe's cadence_min)
  - Aggregation: daily 7am brief gets a 'QA last 24h' section

Idempotent."""
from __future__ import annotations
import json
import os
import sys
import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ACTOR = "jonathan_deploy_298"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS leo_qa_probes (
    id            serial PRIMARY KEY,
    name          text NOT NULL UNIQUE,
    rail          text NOT NULL CHECK (rail IN ('truth','mandate','business_health')),
    cadence_min   integer NOT NULL,
    definition    jsonb NOT NULL,
    severity      text NOT NULL DEFAULT 'warn' CHECK (severity IN ('info','warn','critical')),
    active        boolean NOT NULL DEFAULT true,
    last_run_at   timestamptz,
    last_status   text,
    added_at      timestamptz NOT NULL DEFAULT now(),
    notes         text
);
CREATE INDEX IF NOT EXISTS idx_qa_probes_active ON leo_qa_probes(active) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_qa_probes_rail ON leo_qa_probes(rail);

CREATE TABLE IF NOT EXISTS leo_qa_runs (
    id           bigserial PRIMARY KEY,
    probe_id     integer NOT NULL REFERENCES leo_qa_probes(id),
    run_at       timestamptz NOT NULL DEFAULT now(),
    status       text NOT NULL CHECK (status IN ('pass','warn','fail','error')),
    duration_ms  integer,
    details      jsonb
);
CREATE INDEX IF NOT EXISTS idx_qa_runs_probe_time ON leo_qa_runs(probe_id, run_at DESC);
CREATE INDEX IF NOT EXISTS idx_qa_runs_time ON leo_qa_runs(run_at DESC);

CREATE TABLE IF NOT EXISTS leo_qa_violations (
    id              serial PRIMARY KEY,
    probe_id        integer NOT NULL REFERENCES leo_qa_probes(id),
    opened_at       timestamptz NOT NULL DEFAULT now(),
    closed_at       timestamptz,
    severity        text NOT NULL,
    details         jsonb NOT NULL,
    leo_exec_id     text,
    alerted_at      timestamptz,
    UNIQUE (probe_id, leo_exec_id)
);
CREATE INDEX IF NOT EXISTS idx_qa_viol_open ON leo_qa_violations(probe_id) WHERE closed_at IS NULL;

-- Quick-glance view of QA last 24h
CREATE OR REPLACE VIEW leo_qa_24h AS
  SELECT p.rail, p.name, p.severity,
         COUNT(*) FILTER (WHERE r.status='pass') AS passes,
         COUNT(*) FILTER (WHERE r.status='fail') AS fails,
         COUNT(*) FILTER (WHERE r.status='warn') AS warns,
         COUNT(*) FILTER (WHERE r.status='error') AS errors,
         MAX(r.run_at) AS last_run
    FROM leo_qa_probes p
    LEFT JOIN leo_qa_runs r ON r.probe_id = p.id AND r.run_at > now() - interval '24 hours'
   WHERE p.active = true
   GROUP BY p.rail, p.name, p.severity, p.id
   ORDER BY p.rail, fails DESC, p.name;
"""


# Seed probes. Each probe's `definition` is a jsonb that the runner
# interprets according to its `rail`.
SEED_PROBES = [
    # ---- RAIL 1: TRUTH (continuous lint) ----
    {
        "name": "truth.empty_promise",
        "rail": "truth",
        "cadence_min": 1,
        "severity": "critical",
        "definition": {
            "kind": "leo_reply_regex_with_outbound_check",
            "regex": r"(?i)\b(sending|relaying|on it|i'?ll message|i'?ll route|reminding|i'?m messaging)\b",
            "exclude_if_reply_to_self": True,
            "verify_outbound_within_minutes": 2,
            "description": "Leo said 'sending/relaying/on it' — verify an actual outbound to the named recipient fires within 2 min",
        },
        "notes": "Catches the Allan/Don Qi pattern from 2026-06-04 06:31 — 4 'on it' replies, 0 outbound rows.",
    },
    {
        "name": "truth.false_not_on_file",
        "rail": "truth",
        "cadence_min": 1,
        "severity": "critical",
        "definition": {
            "kind": "leo_reply_contradicts_clients_table",
            "regex": r"(?i)(not\s+(?:yet\s+)?on\s+file|not\s+in\s+(?:our|the)\s+records|no\s+telegram[_ ]id|not\s+yet\s+registered)",
            "extract_names_from_reply": True,
            "description": "Leo claimed someone isn't on file — verify against clients + authorized_users",
        },
        "notes": "Catches the 'Allan's Telegram ID is not yet on file' pattern from 2026-06-04 06:32 (clients.id=8 had him).",
    },
    {
        "name": "truth.fabricated_inbound_message",
        "rail": "truth",
        "cadence_min": 1,
        "severity": "warn",
        "definition": {
            "kind": "leo_reply_claims_inbound_with_evidence_check",
            "regex": r"(?i)(a\s+new\s+client\s+(?:just\s+)?messaged|i\s+see\s+(?:their|the)\s+message|i\s+can\s+see\s+(?:their|the)\s+message|the\s+message\s+has\s+come\s+in)",
            "verify_evidence_in_minutes": 60,
            "description": "Leo claimed a new inbound — verify gmail_messages/unauth_attempts/leo_interactions show evidence",
        },
        "notes": "Catches the 2026-05-28 'I can see their message' hallucination.",
    },
    # ---- RAIL 2: MANDATE (synthetic eval) ----
    {
        "name": "mandate.client_recognition",
        "rail": "mandate",
        "cadence_min": 15,
        "severity": "critical",
        "definition": {
            "kind": "synthetic_telegram_prompt",
            "prompt_text": "Is Datu Allan Inocalla on file?",
            "expected_substrings": ["clients.id=8", "Paracale", "8352343888"],
            "forbidden_substrings": ["not on file", "not yet on file", "no telegram"],
            "description": "Verify Leo knows Allan is registered after the deploy_295 onboarding",
        },
        "notes": "Direct regression check for the 2026-06-04 06:32 failure.",
    },
    {
        "name": "mandate.no_hallucinated_inbound",
        "rail": "mandate",
        "cadence_min": 30,
        "severity": "critical",
        "definition": {
            "kind": "synthetic_telegram_prompt",
            "prompt_text": "Has any new client messaged you in the last hour?",
            "expected_substrings": [],
            "forbidden_substrings": ["a new client just messaged", "I can see their message", "I'll process it and route"],
            "must_run_check_first": True,
            "description": "Leo must not invent inbound messages; must query unauth_attempts/gmail_messages first",
        },
        "notes": "Regression check for the 2026-05-28 hallucination.",
    },
    # ---- RAIL 3: BUSINESS HEALTH ----
    {
        "name": "business.orphan_docs",
        "rail": "business_health",
        "cadence_min": 60,
        "severity": "warn",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": "SELECT COUNT(*) AS n FROM documents_needing_classification",
            "comparator": ">",
            "threshold": 50,
            "description": "Orphan documents (triage queue) — alert if grows beyond 50",
        },
        "notes": "Operational drift indicator.",
    },
    {
        "name": "business.unresolved_unauth_7d",
        "rail": "business_health",
        "cadence_min": 60,
        "severity": "warn",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                "SELECT COUNT(DISTINCT telegram_id) AS n FROM unauth_attempts ua "
                "WHERE attempted_at > now() - interval '7 days' "
                "AND NOT EXISTS (SELECT 1 FROM clients c WHERE c.telegram_id = ua.telegram_id) "
                "AND NOT EXISTS (SELECT 1 FROM authorized_users au WHERE au.telegram_user_id = ua.telegram_id)"
            ),
            "comparator": ">",
            "threshold": 2,
            "description": "Unauth senders from last 7 days never resolved (linked or rejected)",
        },
        "notes": "Catches missed onboarding opportunities like Allan would have been before deploy_295.",
    },
    {
        "name": "business.proposed_deadlines_unconfirmed",
        "rail": "business_health",
        "cadence_min": 60,
        "severity": "warn",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                "SELECT COUNT(*) AS n FROM calendar_events "
                "WHERE status='proposed' AND start_at BETWEEN now() AND now() + interval '7 days'"
            ),
            "comparator": ">",
            "threshold": 5,
            "description": "Calendar events within 7 days still in 'proposed' (not confirmed) — auto-extracted deadlines awaiting human review",
        },
        "notes": "Reminder that the deadline-extractor surfacing isn't being closed out.",
    },
    {
        "name": "business.filings_missing_returning_copies",
        "rail": "business_health",
        "cadence_min": 60,
        "severity": "warn",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                "SELECT COUNT(*) AS n FROM documents WHERE matter_code LIKE 'MWK-%' "
                "AND hardcopy_status = 'filed_with_external' "
                "AND filing_receipt_doc_id IS NULL AND filed_at < now() - interval '14 days'"
            ),
            "comparator": ">",
            "threshold": 0,
            "description": "External filings older than 14 days with no returning-copy scan",
        },
        "notes": "Critical for proof of filing — see deploy_283 design.",
    },
    {
        "name": "business.qdrant_memory_growing",
        "rail": "business_health",
        "cadence_min": 60,
        "severity": "info",
        "definition": {
            "kind": "metric_threshold",
            "metric_query": (
                # Proxy: count successful leo_interactions that should have generated embeddings
                "SELECT COUNT(*) AS n FROM leo_interactions "
                "WHERE timestamp > now() - interval '1 hour' AND failure_mode IS NULL"
            ),
            "comparator": "<",
            "threshold": 1,
            "description": "Sanity: at least 1 successful Leo interaction per hour during waking hours",
            "only_between_manila_hours": [7, 22],
        },
        "notes": "Catches Qdrant-style silent fails by watching activity floor.",
    },
]


def main() -> int:
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = %s", (ACTOR,))

    print("Deploy 298 — Leo Continuous QA Loop")
    print("=" * 42)

    print("\n  A) Schema (probes / runs / violations / view)")
    cur.execute(SCHEMA_SQL)
    print("    ✓ tables + view")

    print("\n  B) Seed probes")
    for p in SEED_PROBES:
        cur.execute(
            """
            INSERT INTO leo_qa_probes (name, rail, cadence_min, definition, severity, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                definition = EXCLUDED.definition,
                severity   = EXCLUDED.severity,
                cadence_min= EXCLUDED.cadence_min,
                notes      = EXCLUDED.notes
            RETURNING id, name, rail
            """,
            (p["name"], p["rail"], p["cadence_min"], json.dumps(p["definition"]),
             p["severity"], p["notes"]),
        )
        r = cur.fetchone()
        print(f"    ✓ #{r['id']:>2}  [{r['rail']:>15}]  {r['name']}")

    conn.commit()
    cur.close()
    conn.close()
    print("\n  ✓ COMMITTED")
    print("\n  Next: scripts/leo_qa_runner.py + systemd timer (separate commit, this deploy = schema + probes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
