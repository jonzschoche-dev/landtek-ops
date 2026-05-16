#!/usr/bin/env python3
"""deploy_123 — stage-intake bi-directional inquiry system.

Per [[feedback_stage_transition_intake]] + Jonathan's 2026-05-16 directive
("all pending matters should have a pre and post inquiry by Leo"):

  • stage_intake_template — per stage / deadline_type, defines the PRE checklist
    (fires at T-3d before the event) and POST checklist (fires when event done).
  • stage_intake_response — tracks which items the client has fulfilled.

Seeds 8 common PH civil-procedure stages with pre/post templates.
"""
import json
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SCHEMA = """
CREATE TABLE IF NOT EXISTS stage_intake_template (
  id              serial PRIMARY KEY,
  stage_key       text NOT NULL,
  timing          text NOT NULL CHECK (timing IN ('pre','post')),
  fire_days_before integer,
  title           text NOT NULL,
  checklist       jsonb NOT NULL,
  notes           text,
  UNIQUE (stage_key, timing)
);

CREATE TABLE IF NOT EXISTS stage_intake_response (
  id              serial PRIMARY KEY,
  deadline_id     integer REFERENCES case_deadlines(id) ON DELETE CASCADE,
  template_id     integer REFERENCES stage_intake_template(id),
  timing          text NOT NULL,
  fired_at        timestamptz NOT NULL DEFAULT now(),
  items_total     integer NOT NULL,
  items_received  integer DEFAULT 0,
  items_skipped   integer DEFAULT 0,
  status          text NOT NULL DEFAULT 'open',  -- open | partial | complete | stale
  notes           text
);

CREATE INDEX IF NOT EXISTS idx_intake_resp_deadline ON stage_intake_response(deadline_id, timing);
CREATE INDEX IF NOT EXISTS idx_intake_resp_status ON stage_intake_response(status, fired_at DESC);
"""

# Each entry: stage_key, deadline_types that map to it, pre/post timing, checklist items.
TEMPLATES = [
    # ─── PRETRIAL ───────────────────────────────────────────────────────────
    {
        "stage_key": "pretrial",
        "timing": "pre",
        "fire_days_before": 7,
        "title": "Pretrial conference — prep checklist (T-7d)",
        "checklist": [
            "Pre-Trial Brief filed (Rule 18 Sec. 6 — at least 3 days before pretrial).",
            "Witnesses confirmed available (and subpoenaed if necessary).",
            "Exhibits compiled + numbered + copies for opposing counsel.",
            "Stipulations to propose (facts you'd ask defendant to admit) — drafted.",
            "Settlement / compromise position decided (per Rule 18 amicable settlement clause).",
            "Travel arrangements + filing fees ready for the day.",
            "Confirmed counsel availability + alternate plan if conflicted.",
        ],
        "notes": "Per PH Rules of Court Rule 18. Failure to appear by plaintiff = dismissal; by defendant = ex parte plaintiff evidence.",
    },
    {
        "stage_key": "pretrial",
        "timing": "post",
        "fire_days_before": None,
        "title": "Pretrial conference — completed, intake checklist",
        "checklist": [
            "Pre-Trial Order (court's roadmap — stipulations + issues + trial schedule).",
            "Receipts (filing fees, transportation, witness fees, per diems).",
            "Brief report: outcome, adverse rulings, settlement offers, any orders from the bench.",
            "Trial date(s) extracted from the Pre-Trial Order.",
            "New exhibits identified at the conference (theirs + ours).",
        ],
        "notes": "Pre-Trial Order is the single most-important post-pretrial artifact — sets the case roadmap.",
    },
    # ─── TRIAL ──────────────────────────────────────────────────────────────
    {
        "stage_key": "trial",
        "timing": "pre",
        "fire_days_before": 7,
        "title": "Trial date — prep checklist (T-7d)",
        "checklist": [
            "Witness availability confirmed (each one).",
            "Witnesses' Judicial Affidavits filed (per JA Rule).",
            "Exhibits authenticated + pre-marked.",
            "Trial brief filed (if directed by Pre-Trial Order).",
            "Subpoena duces tecum issued for any documents needed.",
            "Counsel's calendar cleared. Co-counsel briefed.",
            "Travel + lodging arranged.",
        ],
        "notes": "PH civil trials proceed by Judicial Affidavit Rule — direct testimony in affidavit form, cross only on the affidavit.",
    },
    {
        "stage_key": "trial",
        "timing": "post",
        "fire_days_before": None,
        "title": "Trial day — completed, intake checklist",
        "checklist": [
            "TSN (Transcript of Stenographic Notes) requested + received.",
            "Receipts (witness fees, transportation, etc.).",
            "Brief report on each witness's performance + cross-exam.",
            "Adverse witness testimony — assess credibility / contradictions.",
            "Next trial date or submission date.",
        ],
        "notes": "Each trial date should be tracked individually in case_deadlines.",
    },
    # ─── MOTION / HEARING ───────────────────────────────────────────────────
    {
        "stage_key": "motion_hearing",
        "timing": "pre",
        "fire_days_before": 3,
        "title": "Motion hearing — prep (T-3d)",
        "checklist": [
            "Opposing party's Comment/Opposition received (if filed).",
            "Reply drafted (if responsive arguments warranted).",
            "Authorities cited in motion — re-read; pull additional supporting cases.",
            "Oral argument outline drafted.",
        ],
    },
    {
        "stage_key": "motion_hearing",
        "timing": "post",
        "fire_days_before": None,
        "title": "Motion hearing — completed",
        "checklist": [
            "Court's order/ruling on the motion (or note submitted-for-decision).",
            "Receipts.",
            "Brief report: how it went, any signals from the bench.",
            "Date of expected resolution if submitted for decision.",
        ],
    },
    # ─── DECISION / APPEAL ──────────────────────────────────────────────────
    {
        "stage_key": "decision_received",
        "timing": "post",
        "fire_days_before": None,
        "title": "Decision received — appeal window opens",
        "checklist": [
            "Full Decision PDF.",
            "Date Decision was RECEIVED (15-day appeal clock starts ticking).",
            "Strategic decision: appeal vs accept (or motion for reconsideration first).",
            "If MR: drafted within 15 days.",
            "If appeal: Notice of Appeal drafted + ready to file.",
            "Receipts.",
        ],
        "notes": "Rule 41: appeal must be perfected within 15 days from receipt of judgment. Rule 37: MR also within 15 days.",
    },
    # ─── GENERIC: SEND DEMAND LETTER (or any drafted-doc-to-send obligation)
    {
        "stage_key": "send_demand_letter",
        "timing": "pre",
        "fire_days_before": 3,
        "title": "Send demand letter — prep (T-3d)",
        "checklist": [
            "Letter drafted in final form.",
            "Reviewed by counsel.",
            "Recipient name + complete service address confirmed.",
            "Service method chosen (registered mail / personal service / courier with proof).",
            "Tracking number prepared for return receipt.",
        ],
    },
    {
        "stage_key": "send_demand_letter",
        "timing": "post",
        "fire_days_before": None,
        "title": "Demand letter sent — intake",
        "checklist": [
            "Send date.",
            "Service method actually used.",
            "Tracking number / proof of service.",
            "Recipient acknowledgment (if any).",
            "Next follow-up date (typical: 15 or 30 days for response).",
        ],
    },
    # ─── GOV-SUBMISSION FOLLOW-UP (ARTA, RD, BIR, Assessor) ─────────────────
    {
        "stage_key": "gov_submission_followup",
        "timing": "pre",
        "fire_days_before": 3,
        "title": "Government office submission/follow-up — prep (T-3d)",
        "checklist": [
            "Submission packet finalized (cover letter + supporting docs).",
            "Submitting party + receiving office name confirmed.",
            "Reference number from prior correspondence (if any).",
            "Receipt-of-filing copy prepared.",
        ],
    },
    {
        "stage_key": "gov_submission_followup",
        "timing": "post",
        "fire_days_before": None,
        "title": "Gov submission filed — intake",
        "checklist": [
            "Stamped received copy.",
            "Reference number assigned by office.",
            "Officer who received it (for follow-up).",
            "Expected response timeline.",
        ],
    },
]


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute(SCHEMA)
    for t in TEMPLATES:
        cur.execute("""
            INSERT INTO stage_intake_template (stage_key, timing, fire_days_before, title, checklist, notes)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (stage_key, timing) DO UPDATE
              SET fire_days_before = EXCLUDED.fire_days_before,
                  title = EXCLUDED.title,
                  checklist = EXCLUDED.checklist,
                  notes = EXCLUDED.notes
        """, (t["stage_key"], t["timing"], t.get("fire_days_before"),
              t["title"], json.dumps(t["checklist"]), t.get("notes")))
    cur.execute("SELECT COUNT(*) FROM stage_intake_template")
    n = cur.fetchone()[0]
    print(f"deploy_123: stage_intake_template seeded ({n} templates) + stage_intake_response table ready")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
