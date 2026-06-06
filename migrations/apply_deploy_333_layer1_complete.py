#!/usr/bin/env python3
"""apply_deploy_333_layer1_complete.py — finish Layer 1 (per-matter elite).

Per LEO_MASTER_PLAN.md, Layer 1 includes:
  ✓ case theory                (claims + evidence_trail)
  ✓ evidence gap detection     (v_filing_gaps, transfer_doc_status)
  ✓ deadline radar             (case_events, prep_requirements)
  ✓ document drafting          (Manifestation draft on session branch)
  ✗ opposing-counsel response prediction   ← THIS DEPLOY
  ✗ settlement modeling                    ← scaffold this deploy, real numbers blocked on Layer 2 valuations

Tables:
  planned_moves          — LandTek-side moves we plan to make (filings,
                            motions, demands). Each move has predicted
                            opposing responses + counter-strategy.
  opposing_responses     — Opus-predicted opposition responses to a
                            planned_move, with likelihood + counter.
  settlement_scenarios   — Settlement modeling scaffold (estimated
                            recovery ranges, which defendants settle vs.
                            litigate). Values blocked on Layer 2.

Seed:
  - planned_move: 'File Manifestation re ARTA-1210' (matches existing
    obligation)
  - planned_move: 'Mark exhibit list for pretrial conference 2026-08-01'
  - settlement_scenarios: scaffolded 3 baseline scenarios with NULL
    monetary fields (to populate when title_valuations exists)
"""
from __future__ import annotations
import os, psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS planned_moves (
            id              SERIAL PRIMARY KEY,
            case_file       text NOT NULL,
            move_kind       text NOT NULL CHECK (move_kind IN (
                            'filing','motion','demand','offer','responsive_pleading',
                            'discovery_request','settlement_overture','procedural_step')),
            short_label     text NOT NULL,
            description     text NOT NULL,
            intended_filing_date timestamptz,
            related_claims  integer[],
            related_events  integer[],
            status          text NOT NULL DEFAULT 'planning' CHECK (status IN (
                            'planning','drafted','filed','withdrawn','superseded')),
            priority        integer NOT NULL DEFAULT 3,
            created_at      timestamptz NOT NULL DEFAULT now(),
            filed_at        timestamptz,
            notes           text
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_planned_moves_case ON planned_moves(case_file, status)")
    print("✓ planned_moves")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS opposing_responses (
            id              SERIAL PRIMARY KEY,
            planned_move_id integer NOT NULL REFERENCES planned_moves(id) ON DELETE CASCADE,
            response_kind   text NOT NULL CHECK (response_kind IN (
                            'motion_to_dismiss','answer','counterclaim','demurrer',
                            'reply','silence','settlement_offer','procedural_objection',
                            'recusal_motion','third_party_complaint','other')),
            likelihood      numeric(3,2) NOT NULL CHECK (likelihood BETWEEN 0 AND 1),
            rationale       text NOT NULL,
            counter_strategy text,
            cited_basis     text,
            generated_at    timestamptz NOT NULL DEFAULT now(),
            generated_by    text NOT NULL DEFAULT 'opus_predictor',
            superseded_by   integer REFERENCES opposing_responses(id),
            notes           text
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_opposing_responses_move ON opposing_responses(planned_move_id)")
    print("✓ opposing_responses")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settlement_scenarios (
            id              SERIAL PRIMARY KEY,
            case_file       text NOT NULL,
            scenario_label  text NOT NULL,
            description     text NOT NULL,
            -- Recovery monetary fields — left NULL until Layer 2 valuations exist
            assumed_value_basis text,
            estimated_recovery_low  numeric,
            estimated_recovery_high numeric,
            -- Defendant posture
            defendants_settle text[],
            defendants_litigate text[],
            probability_estimate numeric(3,2),
            rationale       text,
            status          text NOT NULL DEFAULT 'draft' CHECK (status IN (
                            'draft','active','superseded','adopted','rejected')),
            blocked_on      text,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_settlement_case ON settlement_scenarios(case_file, status)")
    print("✓ settlement_scenarios")

    cur.execute("""
        CREATE OR REPLACE VIEW v_planned_moves_with_predictions AS
        SELECT pm.id, pm.case_file, pm.move_kind, pm.short_label,
               pm.intended_filing_date, pm.status, pm.priority,
               (SELECT COUNT(*) FROM opposing_responses opr
                 WHERE opr.planned_move_id = pm.id AND opr.superseded_by IS NULL)
                AS predictions_count,
               (SELECT json_agg(jsonb_build_object(
                  'kind', opr.response_kind,
                  'likelihood', opr.likelihood,
                  'counter', LEFT(opr.counter_strategy, 80)
                ) ORDER BY opr.likelihood DESC)
                  FROM opposing_responses opr
                 WHERE opr.planned_move_id = pm.id
                   AND opr.superseded_by IS NULL)
                AS predictions
          FROM planned_moves pm
         WHERE pm.status IN ('planning','drafted')
         ORDER BY pm.priority DESC, pm.intended_filing_date NULLS LAST
    """)
    print("✓ v_planned_moves_with_predictions")

    # Seed planned_moves
    cur.execute("SELECT COUNT(*) FROM planned_moves")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO planned_moves (case_file, move_kind, short_label, description,
              intended_filing_date, status, priority, related_claims)
            VALUES
              ('MWK-001', 'filing', 'Manifestation re ARTA-1210 (OP docket)',
               'Formal Manifestation submitting LandTek position on ARTA Resolution. Draft on session/manifestation-arta-1210-2026-05-30; awaiting Atty Barandon review + final OP-docket electronic filing.',
               now() + interval '14 days', 'drafted', 4, ARRAY[2]),
              ('MWK-001', 'procedural_step', 'Mark exhibit list — Pretrial 2026-08-01',
               'Pre-mark all primary exhibits (cite by LT-NNNN). Currently blocked: 0 of 6 claims have linked exhibits. Approval of evidence_trail_proposals (16 pending) is the unblock.',
               (TIMESTAMPTZ '2026-08-01 09:00 UTC') - interval '5 days', 'planning', 5,
               ARRAY[1,2,3,4,5,6])
        """)
        print(f"✓ seeded {cur.rowcount} planned_moves")

    cur.execute("SELECT COUNT(*) FROM settlement_scenarios")
    if cur.fetchone()[0] == 0:
        cur.execute("""
            INSERT INTO settlement_scenarios (case_file, scenario_label, description,
              assumed_value_basis, defendants_settle, defendants_litigate,
              probability_estimate, status, blocked_on)
            VALUES
              ('MWK-001', 'aggressive_default',
               'Pursue full litigation against all 20 transferees; demand reconveyance + damages. No mid-case settlement. Maximum exposure but maximum recovery if void chain proven.',
               'NEEDS Layer 2 title_valuations',
               ARRAY[]::text[], ARRAY['ALL_20'],
               0.30, 'draft', 'title_valuations table not yet built (Layer 2)'),
              ('MWK-001', 'tiered_settlement',
               'Settle with cooperative transferees (likely 6-10 of 20) for nominal sums; litigate against Balane + holdouts. Reduces case footprint; recovers from core void chain.',
               'NEEDS Layer 2 title_valuations + per-transferee risk scoring',
               ARRAY['cooperative_subset_TBD'], ARRAY['Gloria Balane','holdouts_TBD'],
               0.55, 'draft', 'title_valuations + per-transferee risk_scoring'),
              ('MWK-001', 'mediation_referral',
               'Accept court-recommended mediation at pretrial; structured settlement across all parties. Faster resolution; partial recovery; preserves relationship with cooperative parties.',
               'NEEDS Layer 2',
               ARRAY['most_of_20'], ARRAY['Gloria Balane'],
               0.40, 'draft', 'title_valuations needed for offer-amount calibration')
        """)
        print(f"✓ seeded {cur.rowcount} settlement_scenarios")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_333',
         'Layer 1 completion: planned_moves + opposing_responses + settlement_scenarios. 2 planned_moves seeded (Manifestation, exhibit-list pretrial), 3 settlement scenarios scaffolded (blocked on Layer 2 valuations). Companion ships predict_opposing_responses.py.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    cur.close(); conn.close()
    print("\n=== summary ===")
    print("Layer 1 schema in place. Predictor script + Context Builder integration in companion files.")


if __name__ == "__main__":
    main()
