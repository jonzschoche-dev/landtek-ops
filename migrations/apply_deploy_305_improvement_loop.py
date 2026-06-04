#!/usr/bin/env python3
"""apply_deploy_305_improvement_loop.py — schema for the smartness feedback loop.

Tables:
  - leo_improvement_proposals
       Opus-drafted patches to Leo's system prompt (and later, other surfaces).
       Lifecycle: pending → approved → applied → verified
                                    └→ rejected
                                    └→ failed_to_apply
  - leo_workflow_snapshots
       Pre-patch snapshots of workflow_entity.nodes so any applied proposal
       can be reverted by ID. Append-only; never trimmed automatically.

Convention:
  - target_probes is a JSON array of probe names this patch should fix.
  - patch_kind is one of: system_prompt_add | system_prompt_replace.
    (More kinds — context_builder_add, tool_description, rule_clause —
    will be added as the loop matures.)
  - patch_payload is the machine-readable form: for system_prompt_add it's
    {append_text}; for system_prompt_replace it's {find_text, replace_text}.
  - baseline_pass_rate is captured at proposal-creation time, post_apply_pass_rate
    after verify-script runs. The delta is the only valid evidence of learning.
"""
from __future__ import annotations
import os
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leo_improvement_proposals (
            id                    SERIAL PRIMARY KEY,
            proposed_at           timestamptz NOT NULL DEFAULT now(),
            status                text NOT NULL DEFAULT 'pending',
            failure_pattern       text NOT NULL,
            target_probes         jsonb NOT NULL,
            patch_kind            text NOT NULL,
            patch_target          text,
            patch_diff            text NOT NULL,
            patch_payload         jsonb NOT NULL,
            rationale             text NOT NULL,
            expected_impact       text,
            baseline_pass_rate    numeric,
            post_apply_pass_rate  numeric,
            reviewed_by           text,
            reviewed_at           timestamptz,
            applied_at            timestamptz,
            verified_at           timestamptz,
            snapshot_id           integer,
            notes                 text,
            CONSTRAINT lip_status_check CHECK (status IN
                ('pending','approved','rejected','applied','verified','failed_to_apply')),
            CONSTRAINT lip_kind_check CHECK (patch_kind IN
                ('system_prompt_add','system_prompt_replace','context_builder_add',
                 'tool_description','rule_clause'))
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_lip_status
            ON leo_improvement_proposals (status, proposed_at DESC)
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leo_workflow_snapshots (
            id            SERIAL PRIMARY KEY,
            taken_at      timestamptz NOT NULL DEFAULT now(),
            workflow_id   text NOT NULL,
            reason        text NOT NULL,
            nodes_json    jsonb NOT NULL,
            connections_json jsonb,
            notes         text
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_lws_workflow
            ON leo_workflow_snapshots (workflow_id, taken_at DESC)
    """)

    # deploy_log marker
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deploy_log (
            deploy_id text PRIMARY KEY,
            summary   text NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary)
        VALUES (
            'deploy_305',
            'Smartness feedback loop: Opus reads 24h sim failures + Leos current system prompt, drafts specific patches (system_prompt_add/replace) into leo_improvement_proposals. Jonathan reviews via Telegram digest + applies via Termius. Snapshots in leo_workflow_snapshots support rollback. Verify script re-runs target probes post-apply for attributable-improvement proof.'
        ) ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)

    cur.execute("SELECT COUNT(*) FROM leo_improvement_proposals")
    print(f"leo_improvement_proposals rows: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM leo_workflow_snapshots")
    print(f"leo_workflow_snapshots rows:    {cur.fetchone()[0]}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
