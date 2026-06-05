#!/usr/bin/env python3
"""apply_deploy_325_realtime_preparation.py — case is a moving target.

Transforms Leo from snapshot-aware to preparation-aware. Tables:

  case_events           — meetings, court appearances, filings, calls,
                          deadlines, decisions. Each event has a date,
                          participants, expected outcome.

  prep_requirements     — per-event line items: documents needed (cite by
                          LT-NNNN), talking points, decisions to make,
                          actions to complete BEFORE the event.

  priority_signals      — temporal events that shift case posture (new
                          evidence linked, new email from opposing counsel,
                          deadline moved, claim status changed). Each signal
                          flags which events / claims it affects.

Views:
  v_upcoming_events_30d         — events in next 30d with prep readiness %
  v_prep_status_per_event       — per-event line items grouped by status
  v_active_priority_signals_7d  — recent shifts (last 7d) affecting priorities

Seed: events from CLAUDE.md (pretrial conference, ARTA-1210 deadline,
Manifestation filing, etc.) with initial prep requirements citing the
seeded claims from deploy_317.

When Jonathan asks "what do I need for the Barandon meeting?" or "what's
my prep status for the pretrial?" Leo consults these tables and generates
a specific, actionable answer with LT-NNNN citations.
"""
from __future__ import annotations
import os, json
from datetime import date, timedelta
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── case_events ────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS case_events (
            id                  SERIAL PRIMARY KEY,
            case_file           text NOT NULL,
            event_kind          text NOT NULL CHECK (event_kind IN (
                                'court_hearing','meeting','filing_deadline',
                                'phone_call','client_check_in','internal_review',
                                'decision_point','correspondence_due','other')),
            short_label         text NOT NULL,
            scheduled_for       timestamptz NOT NULL,
            duration_minutes    integer DEFAULT 60,
            location            text,
            participants        text[],
            description         text,
            expected_outcome    text,
            status              text NOT NULL DEFAULT 'upcoming'
                                CHECK (status IN ('upcoming','in_progress','done','cancelled','postponed')),
            priority            integer NOT NULL DEFAULT 3,
            related_claims      integer[],
            related_matters     text[],
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_case_events_scheduled ON case_events(scheduled_for) WHERE status IN ('upcoming','in_progress')")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_case_events_case_file ON case_events(case_file)")
    print("✓ case_events")

    # ── prep_requirements ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prep_requirements (
            id                  SERIAL PRIMARY KEY,
            event_id            integer NOT NULL REFERENCES case_events(id) ON DELETE CASCADE,
            requirement_kind    text NOT NULL CHECK (requirement_kind IN (
                                'document','talking_point','decision','action',
                                'verification','outreach','review','memo')),
            description         text NOT NULL,
            required_doc_lts    text[],
            required_claim_ids  integer[],
            status              text NOT NULL DEFAULT 'open'
                                CHECK (status IN ('open','in_progress','done','blocked','waived')),
            blocker             text,
            assignee            text DEFAULT 'jonathan',
            due_date            date,
            notes               text,
            created_at          timestamptz NOT NULL DEFAULT now(),
            completed_at        timestamptz
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prep_req_event ON prep_requirements(event_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_prep_req_status ON prep_requirements(status) WHERE status='open'")
    print("✓ prep_requirements")

    # ── priority_signals ───────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS priority_signals (
            id                  SERIAL PRIMARY KEY,
            occurred_at         timestamptz NOT NULL DEFAULT now(),
            signal_kind         text NOT NULL CHECK (signal_kind IN (
                                'new_evidence','new_email','new_doc',
                                'deadline_change','claim_status_change',
                                'inquiry_received','hallucination_flagged',
                                'leak_detected','manual_priority_change',
                                'external_filing')),
            short_text          text NOT NULL,
            detail              text,
            source_kind         text,
            source_id           integer,
            affects_event_ids   integer[],
            affects_claim_ids   integer[],
            affects_matters     text[],
            actionable          boolean NOT NULL DEFAULT true,
            acknowledged_at     timestamptz,
            acknowledged_by     text
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_priority_signals_recent ON priority_signals(occurred_at DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_priority_signals_unack ON priority_signals(occurred_at DESC) WHERE acknowledged_at IS NULL AND actionable")
    print("✓ priority_signals")

    # ── views ──────────────────────────────────────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_upcoming_events_30d AS
        SELECT e.id, e.case_file, e.event_kind, e.short_label,
               e.scheduled_for, e.location, e.priority,
               e.expected_outcome, e.participants,
               (e.scheduled_for - now()) AS time_until,
               COUNT(pr.id)                                  AS req_total,
               COUNT(pr.id) FILTER (WHERE pr.status = 'done') AS req_done,
               COUNT(pr.id) FILTER (WHERE pr.status = 'open') AS req_open,
               COUNT(pr.id) FILTER (WHERE pr.status = 'blocked') AS req_blocked,
               CASE WHEN COUNT(pr.id) = 0 THEN 0.0
                    ELSE ROUND(100.0 * COUNT(pr.id) FILTER (WHERE pr.status='done')
                               / COUNT(pr.id), 1) END AS readiness_pct
          FROM case_events e
          LEFT JOIN prep_requirements pr ON pr.event_id = e.id
         WHERE e.status IN ('upcoming','in_progress')
           AND e.scheduled_for BETWEEN now() AND now() + interval '30 days'
         GROUP BY e.id
         ORDER BY e.scheduled_for
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW v_prep_status_per_event AS
        SELECT e.id AS event_id, e.short_label, e.scheduled_for,
               COALESCE(
                 json_agg(jsonb_build_object(
                   'req_id',    pr.id,
                   'kind',      pr.requirement_kind,
                   'status',    pr.status,
                   'desc',      pr.description,
                   'lts',       pr.required_doc_lts,
                   'due_date',  pr.due_date,
                   'blocker',   pr.blocker
                 ) ORDER BY
                   CASE pr.status
                     WHEN 'blocked' THEN 1 WHEN 'open' THEN 2
                     WHEN 'in_progress' THEN 3 ELSE 4 END,
                   pr.due_date NULLS LAST
                 ) FILTER (WHERE pr.id IS NOT NULL),
                 '[]'::json) AS requirements
          FROM case_events e
          LEFT JOIN prep_requirements pr ON pr.event_id = e.id
         WHERE e.status IN ('upcoming','in_progress')
         GROUP BY e.id
    """)

    cur.execute("""
        CREATE OR REPLACE VIEW v_active_priority_signals_7d AS
        SELECT id, occurred_at, signal_kind, short_text, detail,
               affects_event_ids, affects_claim_ids, affects_matters,
               acknowledged_at
          FROM priority_signals
         WHERE occurred_at > now() - interval '7 days'
           AND actionable
         ORDER BY occurred_at DESC
    """)
    print("✓ 3 views: v_upcoming_events_30d, v_prep_status_per_event, v_active_priority_signals_7d")

    # ── seed events from CLAUDE.md ─────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM case_events")
    if cur.fetchone()["count"] == 0:
        # Approximate pretrial target: 2026-08-01 (confirm against latest Barandon email)
        events = [
            ("MWK-001", "court_hearing", "Pretrial conference — Civil Case 26-360",
             "2026-08-01 09:00 UTC", 180,
             "RTC Daet Branch 38",
             ["Atty Barandon (counsel)", "Jonathan (plaintiff rep)", "RTC judge"],
             "Formal pretrial — exchange of exhibits, stipulation, marking. Critical milestone for the void-chain attack on Balane's title.",
             "Marked exhibits accepted; preliminary stipulations of fact; mediation referral or trial calendaring.",
             "upcoming", 5,
             [1, 2, 3, 4, 5, 6],
             ["MWK-CV26360"]),
            ("MWK-001", "filing_deadline", "Manifestation re ARTA-1210 (OP docket)",
             (date.today() + timedelta(days=14)).isoformat() + " 16:00 UTC", 0,
             "OP docket (electronic filing)",
             ["Jonathan"],
             "Formal Manifestation submitting position re ARTA Resolution. Pending finalization of draft on session branch session/manifestation-arta-1210-2026-05-30.",
             "Filed; receipt logged.",
             "upcoming", 4,
             None,
             None),
            ("MWK-001", "meeting", "Barandon strategy session — pretrial prep",
             (date.today() + timedelta(days=7)).isoformat() + " 06:00 UTC", 90,
             "Telegram / phone",
             ["Atty Barandon", "Jonathan"],
             "Review exhibit list, void-chain narrative, stipulation strategy. Confirm pretrial date.",
             "Final exhibit list agreed; opening statement outline drafted.",
             "upcoming", 4,
             [1, 2, 3],
             ["MWK-CV26360"]),
            ("Paracale-001", "client_check_in", "Allan Inocalla check-in — mineral land + mining partnership",
             (date.today() + timedelta(days=10)).isoformat() + " 04:00 UTC", 30,
             "Telegram",
             ["Datu Allan Inocalla", "Jonathan"],
             "Status of EXPA-000250-V; update on mining partnership events Allan was to surface.",
             "Allan reports any new partnership events; confirm filing status.",
             "upcoming", 3,
             None,
             ["Paracale-001"]),
        ]
        for ef, kind, label, sched, dur, loc, parts, desc, exp, st, prio, claims, matters in events:
            cur.execute("""
                INSERT INTO case_events (case_file, event_kind, short_label, scheduled_for,
                  duration_minutes, location, participants, description, expected_outcome,
                  status, priority, related_claims, related_matters)
                VALUES (%s,%s,%s,%s::timestamptz,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
            """, (ef, kind, label, sched, dur, loc, parts, desc, exp, st, prio, claims, matters))
            evid = cur.fetchone()["id"]

            # Seed initial prep requirements per event
            if "Pretrial conference" in label:
                reqs = [
                    ("document", "Final list of marked exhibits (cite by LT-NNNN, all primary)", [], "open"),
                    ("document", "Certified true copy of T-4497 + derivative chain documents", [], "open"),
                    ("talking_point", "Void-chain narrative: revoked SPA → 2016 Deed → T-52540 cancelled → Balane's TCT", [], "open"),
                    ("decision", "Decide whether to consent to mediation referral", [], "open"),
                    ("verification", "Confirm Patricia Keesey Zschoche representation through Atty Barandon", [], "open"),
                    ("action", "Pre-mark all primary exhibits before hearing", [], "open"),
                ]
            elif "Manifestation" in label:
                reqs = [
                    ("document", "Manifestation draft finalized (currently on session branch)", [], "blocked"),
                    ("review", "Atty Barandon review of draft", [], "open"),
                    ("action", "OP docket electronic filing", [], "open"),
                ]
            elif "Barandon" in label:
                reqs = [
                    ("talking_point", "Confirm pretrial date and venue", [], "open"),
                    ("document", "Bring updated exhibit list", [], "open"),
                    ("decision", "Position on mediation referral", [], "open"),
                    ("decision", "Position on stipulation of facts (which claims to concede vs. contest)", [], "open"),
                ]
            elif "Allan" in label:
                reqs = [
                    ("talking_point", "EXPA-000250-V status check", [], "open"),
                    ("talking_point", "Any new mining-partnership events to surface", [], "open"),
                    ("action", "Confirm Allan's understanding of his case scope (MWK vs Paracale boundary)", [], "open"),
                ]
            else:
                reqs = []

            for k, d, lts, st_r in reqs:
                cur.execute("""
                    INSERT INTO prep_requirements (event_id, requirement_kind, description,
                      required_doc_lts, status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (evid, k, d, lts, st_r))
        cur.execute("SELECT COUNT(*) FROM case_events")
        ce = cur.fetchone()["count"]
        cur.execute("SELECT COUNT(*) FROM prep_requirements")
        pr = cur.fetchone()["count"]
        print(f"✓ seeded {ce} case_events with {pr} prep_requirements")
    else:
        print("✓ case_events already populated (skipping seed)")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_325',
         'Real-time preparation system: case_events + prep_requirements + priority_signals tables + 3 views. Seeded with pretrial conference, ARTA-1210 Manifestation, Barandon strategy session, Allan check-in. Refresh-realtime-flow + Rule S9/S10 ship in companion file.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    print("\n=== summary ===")
    cur.execute("SELECT id, short_label, scheduled_for::timestamp(0), priority, readiness_pct FROM v_upcoming_events_30d")
    for r in cur.fetchall():
        print(f"  [{r['id']}] {r['scheduled_for']}  p{r['priority']}  readiness={r['readiness_pct']}%  {r['short_label']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
