#!/usr/bin/env python3
"""apply_deploy_342_correspondence_spine.py — email ↔ client ↔ matter ↔ goals.

Closes the "matters floating everywhere" gap:
  (1) gmail_messages.client_code + relevance_status columns
  (2) correspondence_links — why each email matters (matter / goal / duty)
  (3) assessments — durable judgments on correspondence (optional per email)
  (4) v_client_goals — unified index of client_outcome + landtek_duty
  (5) v_correspondence_triage — emails missing client or goal linkage
  (6) Backfill client_code on all existing gmail_messages
  (7) Extend gmail_autolink trigger to set client_code on INSERT
  (8) Companion: scripts/correspondence_matcher.py (15-min cron)
  (9) client_history_scan.py gmail path fixed (matter_codes + client_code)

No LLM in this deploy. Pure SQL + deterministic matcher.
"""
from __future__ import annotations
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from correspondence_spine import resolve_client_code  # noqa: E402

SCHEMA_SQL = """
-- ── assessments (durable correspondence judgments) ───────────────────
CREATE TABLE IF NOT EXISTS assessments (
    id               SERIAL PRIMARY KEY,
    client_code      text NOT NULL,
    subject_type     text NOT NULL CHECK (subject_type IN (
                       'gmail_message','chat_note','document','meeting','assertion')),
    subject_id       text NOT NULL,
    hat              text NOT NULL DEFAULT 'legal' CHECK (hat IN (
                       'legal','property','finance','risk','ops')),
    assessment_text  text NOT NULL,
    implication      text,
    confidence       text NOT NULL DEFAULT 'inferred_strong' CHECK (confidence IN (
                       'verified','inferred_strong','inferred_weak')),
    provenance_level text NOT NULL DEFAULT 'inferred_strong',
    assessed_by      text NOT NULL DEFAULT 'correspondence_matcher',
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (subject_type, subject_id, hat)
);

CREATE INDEX IF NOT EXISTS idx_assessments_client
    ON assessments(client_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_assessments_subject
    ON assessments(subject_type, subject_id);

-- ── correspondence_links (email → matter / goal / duty) ─────────────
CREATE TABLE IF NOT EXISTS correspondence_links (
    id           BIGSERIAL PRIMARY KEY,
    gmail_id     integer NOT NULL REFERENCES gmail_messages(id) ON DELETE CASCADE,
    link_type    text NOT NULL CHECK (link_type IN (
                   'matter','client_goal','company_obligation','claim','deadline')),
    link_key     text NOT NULL,
    relation     text NOT NULL DEFAULT 'unclear' CHECK (relation IN (
                   'advances','threatens','satisfies','creates','neutral','unclear')),
    confidence   text NOT NULL DEFAULT 'inferred_strong' CHECK (confidence IN (
                   'verified','inferred_strong','inferred_weak')),
    rationale    text,
    assessed_by  text NOT NULL DEFAULT 'correspondence_matcher',
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (gmail_id, link_type, link_key)
);

CREATE INDEX IF NOT EXISTS idx_corr_links_gmail ON correspondence_links(gmail_id);
CREATE INDEX IF NOT EXISTS idx_corr_links_type_key ON correspondence_links(link_type, link_key);

-- ── gmail_messages spine columns ────────────────────────────────────
ALTER TABLE gmail_messages
    ADD COLUMN IF NOT EXISTS client_code text,
    ADD COLUMN IF NOT EXISTS relevance_status text DEFAULT 'unlinked'
        CHECK (relevance_status IN (
          'unlinked','client_only','matter_linked','goal_linked','assessed')),
    ADD COLUMN IF NOT EXISTS assessment_id integer REFERENCES assessments(id);

CREATE INDEX IF NOT EXISTS idx_gmail_client_code
    ON gmail_messages(client_code) WHERE client_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_gmail_relevance_status
    ON gmail_messages(relevance_status)
    WHERE relevance_status NOT IN ('goal_linked','assessed');

-- ── v_client_goals: unified goal index ──────────────────────────────
CREATE OR REPLACE VIEW v_client_goals AS
SELECT ('obligation_' || o.id::text) AS goal_id,
       o.client_code,
       'landtek_duty'::text AS goal_kind,
       o.short_label,
       o.description,
       o.status,
       o.priority,
       o.matter_code,
       'landtek_obligations'::text AS source_table,
       o.id::text AS source_id
  FROM landtek_obligations o
 WHERE o.status IN ('open','in_progress','blocked')
UNION ALL
SELECT ('need_' || n.id::text) AS goal_id,
       n.client_code,
       'client_outcome'::text AS goal_kind,
       n.short_label,
       n.description,
       n.status,
       n.priority,
       NULL::text AS matter_code,
       'client_needs'::text AS source_table,
       n.id::text AS source_id
  FROM client_needs n
 WHERE n.status IN ('open','escalated');

-- ── v_correspondence_triage: emails needing linkage work ──────────────
CREATE OR REPLACE VIEW v_correspondence_triage AS
SELECT g.id AS gmail_id,
       g.client_code,
       g.case_file,
       g.matter_codes,
       g.relevance_status,
       g.from_addr,
       LEFT(g.subject, 120) AS subject_short,
       g.sent_at,
       g.received_at,
       (SELECT COUNT(*) FROM correspondence_links cl WHERE cl.gmail_id = g.id) AS link_count
  FROM gmail_messages g
 WHERE g.relevance_status IN ('unlinked','client_only','matter_linked')
    OR g.client_code IS NULL
    OR (cardinality(COALESCE(g.matter_codes, '{}'::text[])) = 0
        AND g.relevance_status NOT IN ('goal_linked','assessed'))
 ORDER BY COALESCE(g.received_at, g.sent_at) DESC NULLS LAST;

-- ── v_email_goal_map: drill-down for Leo ────────────────────────────
CREATE OR REPLACE VIEW v_email_goal_map AS
SELECT g.id AS gmail_id,
       g.client_code,
       g.matter_codes,
       g.subject,
       g.relevance_status,
       cl.link_type,
       cl.link_key,
       cl.relation,
       cl.rationale,
       cl.confidence
  FROM gmail_messages g
  JOIN correspondence_links cl ON cl.gmail_id = g.id
 ORDER BY g.id DESC, cl.link_type;
"""

TRIGGER_SQL = r"""
-- deploy_342: extend autolink trigger to also set client_code + relevance_status.

CREATE OR REPLACE FUNCTION gmail_autolink_matters()
RETURNS TRIGGER AS $$
DECLARE
    haystack TEXT;
    sender_lower TEXT;
    mc_set TEXT[] := ARRAY[]::TEXT[];
    candidate TEXT;
    suffix TEXT;
    m RECORD;
    valid_codes TEXT[];
    derived_client TEXT;
BEGIN
    haystack := COALESCE(NEW.from_addr,'') || ' ' || COALESCE(NEW.subject,'') || ' ' || COALESCE(NEW.body_plain,'');
    sender_lower := LOWER(COALESCE(NEW.from_addr,''));

    -- Matter autolink (only when matter_codes empty) — same as deploy_277
    IF cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) = 0 THEN
        IF sender_lower LIKE '%barandon_lawoffice%' THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%colenacious%'        THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%dilgcamarinesnorte%' THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%litigationdivision@arta%' THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%lourdestotanes%'     THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;

        FOR m IN
            SELECT (regexp_matches(haystack,
                    '\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b',
                    'gi'))[3] AS s
        LOOP
            suffix := m.s;
            IF length(suffix) = 3 THEN suffix := '0' || suffix; END IF;
            candidate := 'MWK-ARTA-' || suffix;
            IF NOT (candidate = ANY(mc_set)) THEN mc_set := array_append(mc_set, candidate); END IF;
        END LOOP;

        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*26-?360' THEN
            IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*6839' THEN
            IF NOT ('MWK-CV6839' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV6839'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*13-?131220' THEN
            IF NOT ('PAR-CV13-131220' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'PAR-CV13-131220'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*8563' THEN
            IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        END IF;

        IF cardinality(mc_set) > 0 THEN
            SELECT array_agg(DISTINCT mc) INTO valid_codes
              FROM unnest(mc_set) mc
             WHERE mc IN (SELECT matter_code FROM matters);
            IF cardinality(COALESCE(valid_codes, '{}'::text[])) > 0 THEN
                NEW.matter_codes := valid_codes;
                NEW.relevance_reasons := COALESCE(NEW.relevance_reasons, '{}'::text[])
                                         || ARRAY['deploy_342:trigger_autolink'];
            END IF;
        END IF;
    END IF;

    -- client_code derivation (deploy_342)
    IF NEW.client_code IS NULL OR NEW.client_code = '' THEN
        IF NEW.case_file IS NOT NULL AND NEW.case_file <> '' THEN
            SELECT c.client_code INTO derived_client
              FROM clients c WHERE c.case_file = NEW.case_file LIMIT 1;
            IF derived_client IS NULL THEN
                SELECT DISTINCT m.client_code INTO derived_client
                  FROM matters m WHERE m.case_file = NEW.case_file LIMIT 1;
            END IF;
        END IF;
        IF derived_client IS NULL AND cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
            SELECT DISTINCT m.client_code INTO derived_client
              FROM matters m
             WHERE m.matter_code = ANY(NEW.matter_codes)
             LIMIT 1;
        END IF;
        IF derived_client IS NULL AND cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
            IF (NEW.matter_codes)[1] LIKE 'MWK-%' THEN derived_client := 'MWK-001'; END IF;
            IF (NEW.matter_codes)[1] LIKE 'PAR-%' THEN derived_client := 'Paracale-001'; END IF;
        END IF;
        IF derived_client IS NOT NULL THEN
            NEW.client_code := derived_client;
        END IF;
    END IF;

    -- relevance_status snapshot (matcher may upgrade to goal_linked later)
    IF NEW.assessment_id IS NOT NULL THEN
        NEW.relevance_status := 'assessed';
    ELSIF cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
        NEW.relevance_status := 'matter_linked';
    ELSIF NEW.client_code IS NOT NULL THEN
        NEW.relevance_status := 'client_only';
    ELSE
        NEW.relevance_status := 'unlinked';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS gmail_messages_autolink_matters_trigger ON gmail_messages;
CREATE TRIGGER gmail_messages_autolink_matters_trigger
    BEFORE INSERT OR UPDATE OF case_file, matter_codes, client_code, assessment_id
    ON gmail_messages
    FOR EACH ROW
    EXECUTE FUNCTION gmail_autolink_matters();
"""


def backfill_client_codes(cur) -> int:
    """Set client_code on rows still missing it."""
    cur.execute("""
        SELECT id, case_file, matter_codes, client_code
          FROM gmail_messages
         WHERE client_code IS NULL OR client_code = ''
    """)
    rows = cur.fetchall()
    n = 0
    for row in rows:
        cc = resolve_client_code(
            cur,
            case_file=row["case_file"],
            matter_codes=row["matter_codes"] or [],
            existing=row["client_code"],
        )
        if cc:
            cur.execute(
                "UPDATE gmail_messages SET client_code = %s WHERE id = %s",
                (cc, row["id"]),
            )
            n += 1
    return n


def backfill_relevance_status(cur) -> int:
    cur.execute("""
        UPDATE gmail_messages g
           SET relevance_status = CASE
             WHEN assessment_id IS NOT NULL THEN 'assessed'
             WHEN EXISTS (
               SELECT 1 FROM correspondence_links cl
                WHERE cl.gmail_id = g.id
                  AND cl.link_type IN ('client_goal','company_obligation')
             ) THEN 'goal_linked'
             WHEN cardinality(COALESCE(matter_codes, '{}'::text[])) > 0 THEN 'matter_linked'
             WHEN client_code IS NOT NULL THEN 'client_only'
             ELSE 'unlinked'
           END
         WHERE relevance_status IS DISTINCT FROM CASE
             WHEN assessment_id IS NOT NULL THEN 'assessed'
             WHEN EXISTS (
               SELECT 1 FROM correspondence_links cl
                WHERE cl.gmail_id = g.id
                  AND cl.link_type IN ('client_goal','company_obligation')
             ) THEN 'goal_linked'
             WHEN cardinality(COALESCE(matter_codes, '{}'::text[])) > 0 THEN 'matter_linked'
             WHEN client_code IS NOT NULL THEN 'client_only'
             ELSE 'unlinked'
           END
    """)
    return cur.rowcount


def seed_matter_links(cur) -> int:
    """One correspondence_links row per matter_code already on the email."""
    cur.execute("""
        INSERT INTO correspondence_links (gmail_id, link_type, link_key, relation, rationale, assessed_by)
        SELECT g.id, 'matter', mc, 'unclear',
               'deploy_342 backfill from gmail_messages.matter_codes',
               'deploy_342_backfill'
          FROM gmail_messages g, unnest(COALESCE(g.matter_codes, '{}'::text[])) AS mc
         WHERE mc IN (SELECT matter_code FROM matters)
        ON CONFLICT (gmail_id, link_type, link_key) DO NOTHING
    """)
    return cur.rowcount


def main():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("deploy_342 — correspondence spine")
    print("=" * 60)

    print("\n[1/6] Schema: assessments, correspondence_links, gmail columns, views")
    cur.execute(SCHEMA_SQL)
    print("  ✓ tables + views ready")

    print("\n[2/6] Trigger: gmail_autolink_matters + client_code")
    cur.execute(TRIGGER_SQL)
    print("  ✓ trigger updated")

    print("\n[3/6] Backfill client_code on gmail_messages")
    n_cc = backfill_client_codes(cur)
    print(f"  ✓ {n_cc} rows got client_code")

    print("\n[4/6] Seed matter correspondence_links from matter_codes[]")
    n_ml = seed_matter_links(cur)
    print(f"  ✓ {n_ml} matter links inserted (idempotent)")

    print("\n[5/6] Refresh relevance_status")
    n_rs = backfill_relevance_status(cur)
    print(f"  ✓ {n_rs} rows relevance_status updated")

    print("\n[6/6] deploy_log")
    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_342',
         'Correspondence spine: assessments + correspondence_links + gmail.client_code/relevance_status + v_client_goals + v_correspondence_triage + v_email_goal_map. Backfilled client_code. Extended gmail trigger. Companion: scripts/correspondence_matcher.py + client_history_scan gmail fix.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
    """)

    cur.execute("SELECT relevance_status, COUNT(*) AS n FROM gmail_messages GROUP BY 1 ORDER BY 2 DESC")
    print("\n=== gmail relevance_status ===")
    for r in cur.fetchall():
        print(f"  {r['relevance_status'] or 'NULL':15s}  {r['n']}")

    cur.execute("SELECT COUNT(*) AS n FROM correspondence_links")
    print(f"\n  correspondence_links total: {cur.fetchone()['n']}")

    cur.execute("SELECT COUNT(*) AS n FROM v_client_goals")
    print(f"  v_client_goals rows: {cur.fetchone()['n']}")

    cur.execute("SELECT COUNT(*) AS n FROM v_correspondence_triage")
    print(f"  v_correspondence_triage (needs work): {cur.fetchone()['n']}")

    cur.close()
    conn.close()
    print("\nDone. Run: python3 scripts/correspondence_matcher.py --full")


if __name__ == "__main__":
    main()