#!/usr/bin/env python3
"""apply_deploy_326_obligations_phases_needs.py — Leo knows what we owe.

Three new first-class concepts:

  landtek_obligations  — what LandTek owes each client. Deliverables,
                         standing duties, fiduciary obligations, deadlines
                         we committed to meet. Source-tracked so Leo can
                         cite the basis ('per retainer', 'per email of X',
                         'per Manifestation filing').

  project_phases       — where each case sits in its arc (pretrial prep /
                         evidence consolidation / discovery / mediation /
                         trial / appeal / closure). One active phase per
                         case; ordered; success criteria + exit signals.

  client_needs         — what clients currently need from us. Surfaced
                         from explicit requests or inferred from patterns.
                         Status open/addressed/obsolete.

Seed:
  6 obligations per CLAUDE.md mandate (representation, evidence integrity,
    communication relay, Manifestation filing, fiduciary on case docs,
    pretrial preparation)
  3 active project phases (MWK-001: pretrial_prep; Paracale-001:
    discovery; Archive: dormant)
  4 anticipated client_needs (Patricia: status updates; Allan: case
    boundary clarity; HMWK admin: standing communications; new prospects:
    onboarding readiness)

Views:
  v_open_obligations_by_client       — what we owe each client now
  v_obligations_at_risk              — overdue or due-within-14d
  v_current_phase_per_case           — where each case is
  v_open_client_needs                — what clients want from us

Combined with refresh_realtime_flow (deploy_325) Leo can answer:
  "What does Patricia need from us right now?"
  "What obligations do we have on MWK-001?"
  "Are we at risk of breaching any obligations?"
  "What phase is the Paracale matter in?"
"""
from __future__ import annotations
import os, json
from datetime import datetime, timezone, timedelta
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── landtek_obligations ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS landtek_obligations (
            id              SERIAL PRIMARY KEY,
            client_code     text NOT NULL,
            case_file       text,
            matter_code     text,
            obligation_kind text NOT NULL CHECK (obligation_kind IN (
              'deliverable','deadline_meet','communication','representation',
              'milestone','standing_duty','fiduciary','reporting','custody')),
            short_label     text NOT NULL,
            description     text NOT NULL,
            promised_at     timestamptz,
            due_by          timestamptz,
            status          text NOT NULL DEFAULT 'open' CHECK (status IN (
              'open','in_progress','done','blocked','waived','breached')),
            priority        integer NOT NULL DEFAULT 3,
            related_claims  integer[],
            related_events  integer[],
            related_docs    text[],
            source_kind     text CHECK (source_kind IN (
              'retainer','email','court_filing','verbal_commit','statutory',
              'fiduciary_by_role','derived_from_mandate','client_request') OR source_kind IS NULL),
            source_ref      text,
            notes           text,
            created_at      timestamptz NOT NULL DEFAULT now(),
            updated_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_client ON landtek_obligations(client_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_status ON landtek_obligations(status) WHERE status IN ('open','in_progress')")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_obl_due ON landtek_obligations(due_by) WHERE due_by IS NOT NULL AND status NOT IN ('done','waived')")
    print("✓ landtek_obligations")

    # ── project_phases ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_phases (
            id              SERIAL PRIMARY KEY,
            case_file       text NOT NULL,
            phase_label     text NOT NULL,
            phase_order     integer NOT NULL,
            status          text NOT NULL DEFAULT 'pending' CHECK (status IN (
              'pending','active','completed','blocked','skipped')),
            started_at      timestamptz,
            completed_at    timestamptz,
            description     text,
            success_criteria text,
            exit_signals    text[],
            current_focus   text,
            UNIQUE (case_file, phase_label)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_phase_case_active ON project_phases(case_file) WHERE status='active'")
    print("✓ project_phases")

    # ── client_needs ───────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_needs (
            id              SERIAL PRIMARY KEY,
            client_code     text NOT NULL,
            need_kind       text NOT NULL CHECK (need_kind IN (
              'information_request','document_provision','decision_required',
              'emotional_assurance','status_update','urgent_response',
              'milestone_celebration','boundary_clarification','introduction')),
            short_label     text NOT NULL,
            description     text,
            surfaced_from   text CHECK (surfaced_from IN (
              'explicit_request','pattern_inference','proactive_anticipation',
              'compliance_calendar','client_relationship_norm','derived') OR surfaced_from IS NULL),
            priority        integer NOT NULL DEFAULT 3,
            status          text NOT NULL DEFAULT 'open' CHECK (status IN (
              'open','addressed','obsolete','escalated')),
            acknowledged_at timestamptz,
            resolved_at     timestamptz,
            notes           text,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_cn_client ON client_needs(client_code) WHERE status='open'")
    print("✓ client_needs")

    # ── views ─────────────────────────────────────────────────────────
    cur.execute("""
        CREATE OR REPLACE VIEW v_open_obligations_by_client AS
        SELECT o.client_code,
               c.name AS client_name,
               COUNT(*) AS total_open,
               COUNT(*) FILTER (WHERE o.status='blocked') AS blocked,
               COUNT(*) FILTER (WHERE o.due_by < now() + interval '14 days'
                                AND o.due_by IS NOT NULL) AS imminent,
               COUNT(*) FILTER (WHERE o.due_by < now() AND o.due_by IS NOT NULL) AS overdue,
               json_agg(jsonb_build_object(
                 'id',          o.id,
                 'kind',        o.obligation_kind,
                 'label',       o.short_label,
                 'due_by',      o.due_by,
                 'status',      o.status,
                 'priority',    o.priority,
                 'source',      o.source_kind
               ) ORDER BY o.priority DESC, o.due_by NULLS LAST, o.id) AS obligations
          FROM landtek_obligations o
          LEFT JOIN clients c ON c.client_code = o.client_code
         WHERE o.status IN ('open','in_progress','blocked')
         GROUP BY o.client_code, c.name
         ORDER BY MAX(o.priority) DESC
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_obligations_at_risk AS
        SELECT o.id, o.client_code, o.short_label, o.description,
               o.due_by, o.status, o.priority, o.obligation_kind,
               (o.due_by - now()) AS time_until_due,
               CASE
                 WHEN o.due_by < now()                       THEN 'overdue'
                 WHEN o.due_by < now() + interval '7 days'   THEN 'imminent'
                 WHEN o.due_by < now() + interval '14 days'  THEN 'approaching'
                 ELSE 'on_horizon'
               END AS risk_window
          FROM landtek_obligations o
         WHERE o.status IN ('open','in_progress','blocked')
           AND o.due_by IS NOT NULL
           AND o.due_by < now() + interval '14 days'
         ORDER BY o.due_by NULLS LAST
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_current_phase_per_case AS
        SELECT p.case_file, p.phase_label, p.phase_order, p.description,
               p.started_at, p.current_focus, p.success_criteria, p.exit_signals
          FROM project_phases p
         WHERE p.status = 'active'
         ORDER BY p.case_file
    """)
    cur.execute("""
        CREATE OR REPLACE VIEW v_open_client_needs AS
        SELECT n.client_code, c.name AS client_name, n.need_kind,
               n.short_label, n.description, n.priority,
               n.surfaced_from, n.created_at
          FROM client_needs n
          LEFT JOIN clients c ON c.client_code = n.client_code
         WHERE n.status = 'open'
         ORDER BY n.priority DESC, n.created_at DESC
    """)
    print("✓ 4 views: v_open_obligations_by_client, v_obligations_at_risk, v_current_phase_per_case, v_open_client_needs")

    # ── seed obligations ──────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM landtek_obligations")
    if cur.fetchone()["count"] == 0:
        # client_code values: MWK-CV26360 for Patricia (Civil Case 26-360); Paracale-001 for Allan; HMWK for Don Qi/admin; Archive for archived
        # Use the clients table as ground truth.
        obligations = [
            # MWK-CV26360 (Patricia Keesey Zschoche)
            ("MWK-CV26360", "MWK-001", "representation",
             "Plaintiff representation through Atty Barandon",
             "Maintain plaintiff-side counsel coordination with Atty Bonifacio Jr. Barandon "
             "(Barandon Law Offices, Daet) for Civil Case 26-360 throughout pretrial, trial, and appeal.",
             None, "open", 5, "retainer", "client_relationship_norm"),
            ("MWK-CV26360", "MWK-001", "deliverable",
             "Manifestation re ARTA-1210 filing",
             "File formal Manifestation re ARTA Resolution at OP docket. Currently blocked: draft on session branch session/manifestation-arta-1210-2026-05-30 needs finalization + Atty Barandon review.",
             None, "open", 4, "court_filing", None),
            ("MWK-CV26360", "MWK-001", "milestone",
             "Pretrial conference readiness",
             "Achieve full pretrial readiness: marked exhibits, void-chain narrative articulated, stipulation position decided, mediation referral decision made.",
             None, "open", 5, "statutory", None),
            ("MWK-CV26360", "MWK-001", "fiduciary",
             "Evidence integrity custody",
             "Maintain integrity of evidence trail — all assertions backed by verified provenance "
             "(provenance_level='verified'), no inference-grade claims presented as fact, "
             "chain-of-custody preserved on every primary exhibit.",
             None, "open", 5, "fiduciary_by_role", None),
            ("MWK-CV26360", "MWK-001", "standing_duty",
             "Relay Atty Barandon communications",
             "Relay all Atty Barandon correspondence to plaintiff Patricia Keesey Zschoche through Jonathan within the same business day.",
             None, "open", 4, "client_relationship_norm", None),
            # Paracale-001 (Allan Inocalla)
            ("Paracale-001", None, "standing_duty",
             "Monthly status updates",
             "Provide Datu Allan Inocalla monthly status update on his matters (EXPA-000250-V, mineral land, mining partnership events) by the 5th of each month.",
             None, "open", 3, "client_relationship_norm", None),
            ("Paracale-001", None, "communication",
             "Mining partnership event surfacing",
             "Maintain awareness of any new mining-partnership events Allan reports; record into priority_signals; reflect in REALTIME_FLOW.",
             None, "open", 3, "client_request", None),
        ]
        for cc, cf, kind, lbl, desc, due, st, pr, src_kind, _ in obligations:
            cur.execute("""
                INSERT INTO landtek_obligations (client_code, case_file, obligation_kind,
                  short_label, description, due_by, status, priority, source_kind)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (cc, cf, kind, lbl, desc, due, st, pr, src_kind))
        cur.execute("SELECT COUNT(*) FROM landtek_obligations")
        print(f"✓ seeded {cur.fetchone()['count']} obligations")
    else:
        print("✓ obligations already populated")

    # ── seed phases ────────────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM project_phases")
    if cur.fetchone()["count"] == 0:
        phases = [
            # MWK-001
            ("MWK-001", "evidence_consolidation", 1, "completed",
             "Initial document ingestion + extraction (388+ documents indexed, 977 with LT-NNNN).",
             "All known case documents in the index with provenance_level assigned",
             None),
            ("MWK-001", "evidence_trail_build", 2, "active",
             "Construct the evidence trail — link documents to claims with weight + relation. Currently 6 claims seeded; 16 Opus proposals pending review; 0 primary exhibits linked.",
             "All 6 seeded claims have ≥2 primary exhibits + 1 corroborating exhibit each",
             ["filing_gaps_count = 0", "all seeded claims with primary linkage"]),
            ("MWK-001", "pretrial_prep", 3, "pending",
             "Translate evidence trail into pretrial deliverables: marked exhibit list, opening narrative, stipulation position, mediation decision.",
             "Pretrial conference readiness 100% per prep_requirements",
             ["pretrial_readiness_pct >= 90"]),
            ("MWK-001", "pretrial_conference", 4, "pending",
             "Attend Pretrial conference (2026-08-01); exchange exhibits; seek favorable stipulation or trial calendaring.",
             "Court-marked exhibit list accepted",
             None),
            ("MWK-001", "trial", 5, "pending",
             "Civil Case 26-360 trial proceedings.",
             "Judgment rendered", None),
            ("MWK-001", "post_trial", 6, "pending",
             "Post-trial: appeal preparation OR judgment enforcement.",
             "Final order satisfied or appeal docketed", None),
            # Paracale-001
            ("Paracale-001", "ongoing_advisory", 1, "active",
             "Advisory + filing support for Allan's Paracale matters (EXPA-000250-V mining claim, mineral land issues).",
             "Allan's matters tracked + monthly updates delivered",
             None),
        ]
        for cf, lbl, ordr, st, desc, suc, exits in phases:
            cur.execute("""
                INSERT INTO project_phases (case_file, phase_label, phase_order, status,
                  description, success_criteria, exit_signals, started_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s='active' THEN now() ELSE NULL END)
            """, (cf, lbl, ordr, st, desc, suc, exits, st))
        cur.execute("SELECT COUNT(*) FROM project_phases")
        print(f"✓ seeded {cur.fetchone()['count']} project_phases")
    else:
        print("✓ project_phases already populated")

    # ── seed client_needs ─────────────────────────────────────────────
    cur.execute("SELECT COUNT(*) FROM client_needs")
    if cur.fetchone()["count"] == 0:
        needs = [
            ("MWK-CV26360", "status_update",
             "Pretrial readiness summary",
             "Patricia (or her representative) reasonably expects a clear pretrial readiness summary as the conference approaches. Surface readiness % when she or her rep makes contact.",
             "client_relationship_norm", 4),
            ("Paracale-001", "boundary_clarification",
             "MWK vs Paracale scope clarity",
             "Allan has historically asked about MWK matters that are outside his case scope. Maintain awareness; gently redirect; track inquiries that may indicate scope confusion.",
             "pattern_inference", 3),
            ("HMWK", "status_update",
             "Standing communication relay",
             "Don Qi / HMWK administrator receives Starlink + property-related communications. Maintain delivery quality; flag any failed relays.",
             "client_relationship_norm", 3),
            ("MWK-CV26360", "document_provision",
             "Pretrial exhibit list disclosure",
             "Patricia + Atty Barandon need the final marked exhibit list available for review before pretrial. Currently blocked on evidence_trail population.",
             "compliance_calendar", 5),
        ]
        for cc, kind, lbl, desc, src, pr in needs:
            cur.execute("""
                INSERT INTO client_needs (client_code, need_kind, short_label, description,
                  surfaced_from, priority)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (cc, kind, lbl, desc, src, pr))
        cur.execute("SELECT COUNT(*) FROM client_needs")
        print(f"✓ seeded {cur.fetchone()['count']} client_needs")

    cur.execute("""
        INSERT INTO deploy_log (deploy_id, summary) VALUES ('deploy_326',
         'Obligation-aware flow: landtek_obligations + project_phases + client_needs + 4 views. Seeded 7 obligations (representation, Manifestation filing, pretrial readiness, evidence integrity, Barandon relay, Allan monthly updates, mining partnership awareness), 7 project_phases (MWK-001 phases 1-6 + Paracale advisory), 4 client_needs.')
        ON CONFLICT (deploy_id) DO UPDATE SET summary=EXCLUDED.summary
    """)
    print("\n=== summary ===")
    cur.execute("SELECT * FROM v_current_phase_per_case")
    for r in cur.fetchall():
        print(f"  ACTIVE PHASE  {r['case_file']:15s}  {r['phase_label']:25s}  ({r['phase_order']})")
    cur.execute("SELECT client_code, total_open, blocked, imminent, overdue FROM v_open_obligations_by_client")
    print()
    for r in cur.fetchall():
        print(f"  OBLIGATIONS   {r['client_code']:15s}  open={r['total_open']}  "
              f"blocked={r['blocked']}  imminent={r['imminent']}  overdue={r['overdue']}")
    cur.execute("SELECT client_code, COUNT(*) AS open_needs FROM client_needs WHERE status='open' GROUP BY client_code")
    print()
    for r in cur.fetchall():
        print(f"  CLIENT NEEDS  {r['client_code']:15s}  open={r['open_needs']}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
