#!/usr/bin/env python3
"""generate_case_bible.py — Layer D+E of the bible architecture (deploy_156).

Produces a chronological Master Case Bible for a matter from client_history,
with forward projection from stage rules and gap detection.

Hierarchy (per Jonathan 2026-05-17 spec):
  1. Document Header
  2. Executive Summary & Forward Projection (Layer E)
  3. Master Timeline grouped by YEAR (the core)
  4. Missing / Anomalous Gaps

Dual delivery:
  - PDF saved to Google Drive Outputs folder (service-account credentials)
  - PDF sent to Jonathan's Telegram via sendDocument

Usage:
  python3 generate_case_bible.py --matter MWK-CV26360            # full pipeline
  python3 generate_case_bible.py --matter MWK-CV26360 --md-only  # MD only (no PDF, no delivery)
  python3 generate_case_bible.py --matter MWK-CV26360 --no-deliver  # MD + PDF, no Drive/TG
  python3 generate_case_bible.py --case MWK-001                  # by case_file
"""
import argparse
import io
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
JONATHAN_TG_ID = "6513067717"
GOOGLE_CREDS_PATH = "/root/landtek/google-creds.json"

# Drive output folder per client (Outputs subfolder of the LANDTEK shared folder).
# These folders need to be created in Drive ahead of time; SA must be granted edit.
DRIVE_OUTPUT_FOLDER = {
    "MWK-001":      "1roy5YlHJIHKbV8hYsxYu6ptonlM7Lmj2",   # MWK shared folder
    "Paracale-001": "1eDLECG_Lu9dXh-FLeCTvjI3fJclMid2b",   # Owner / Paracale
}


# ── Forward-projection rules (Layer E) ─────────────────────────────────
# Stage → list of (relative_days, projected_event_label, kind)
STAGE_PROJECTIONS = {
    "post_pretrial_pending_trial_schedule": [
        (30,  "Pre-Trial Order issued by RTC (sets trial date + stipulations)", "court_order"),
        (90,  "First trial date (typical PH RTC scheduling)",                   "trial"),
        (210, "Direct examination of plaintiff witnesses begins",               "trial"),
        (365, "Trial concludes / decision under submission",                    "trial"),
    ],
    "pretrial": [
        (1,   "Pretrial conference",                                            "judicial"),
        (30,  "Pre-Trial Order issued",                                         "court_order"),
    ],
    "pre_mediation": [
        (1,   "Mediation conference",                                           "mediation"),
        (30,  "Mediation report due (settlement or referral back to court)",    "court_filing"),
    ],
    "complaint_filed": [
        (15,  "Summons served on defendants",                                   "court_filing"),
        (45,  "Defendants' Answer due",                                         "court_filing"),
        (90,  "Pretrial conference",                                            "judicial"),
    ],
    "answer_filed": [
        (30,  "Pretrial conference",                                            "judicial"),
        (60,  "Pre-Trial Order",                                                "court_order"),
    ],
    # MWK-specific stages surfaced in omnibus run
    "just_compensation_halted_pending_substitution": [
        (15,  "File Motion for Substitution of Party (substitute heirs for deceased MWK)", "court_filing"),
        (45,  "Court order on substitution + revival of just-compensation proceedings",    "court_order"),
        (90,  "Commissioners' valuation hearing resumes",                                   "judicial"),
    ],
    "complaint_filed_awaiting_response": [
        (15,  "ARTA agency response deadline (RA 11032 §10: 3-day acknowledgement, 7-day action)", "agency_response"),
        (30,  "If no response: file referral / escalation to next-level agency",                    "court_filing"),
    ],
    "referred_to_csc_dilg_awaiting": [
        (30,  "CSC/DILG initial action / acknowledgement",                                   "agency_response"),
        (90,  "Initial CSC/DILG ruling or further referral",                                 "agency_response"),
    ],
    "arta_referral_filed_awaiting_response": [
        (15,  "ARTA referral acknowledgement window",                                        "agency_response"),
        (60,  "Substantive response or further referral",                                    "agency_response"),
    ],
    "demand_letter_pending_send": [
        (3,   "Send demand letter (currently in draft / pending dispatch)",                  "correspondence"),
        (20,  "Recipient response window (typical 15-day demand-letter cycle)",              "correspondence"),
        (45,  "Escalation if non-response: court filing or admin escalation",                "court_filing"),
    ],
    "estate_administration_active_no_immediate_deadline": [
        # No fixed dates — just procedural milestones
    ],
}


def db_connect():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def resolve_matter(cur, matter_code=None, case_file=None):
    if matter_code:
        cur.execute("""
            SELECT matter_code, case_file, client_code, title, court_or_agency,
                   docket_number, current_stage, stage_updated_at, next_event,
                   next_deadline, stage_notes
              FROM matters WHERE matter_code = %s
        """, (matter_code,))
        m = cur.fetchone()
        if m: return m
    if case_file:
        cur.execute("""
            SELECT matter_code, case_file, client_code, title, court_or_agency,
                   docket_number, current_stage, stage_updated_at, next_event,
                   next_deadline, stage_notes
              FROM matters WHERE case_file = %s
             ORDER BY stage_updated_at DESC NULLS LAST LIMIT 1
        """, (case_file,))
        m = cur.fetchone()
        if m: return m
        # Fall back to clients table if no matters row exists
        cur.execute("SELECT case_file, client_code FROM clients WHERE case_file = %s", (case_file,))
        c = cur.fetchone()
        if c:
            return dict(c, matter_code=None, title=None, court_or_agency=None,
                        docket_number=None, current_stage=None, stage_updated_at=None,
                        next_event=None, next_deadline=None, stage_notes=None)
    return None


def fetch_events(cur, matter_code, case_file):
    """Enriched event fetch (deploy_157) — JOINs to documents/transactions/gmail/calendar
    to pull substantive payload, not just metadata tags.

    For every event row, we have:
      - the bible-level metadata (date, kind, parties, provenance)
      - the SOURCE-LEVEL substance:
        * documents:  classification, smart_filename, document_title,
                      first 600 chars of extracted_text, analyst_memo JSON,
                      execution_status
        * transactions: amount, counterparty, category, payment_method,
                      description, direction (in/out)
        * gmail:    subject, from_addr, first 400 chars of body_plain
        * calendar: title, description, location, attendees
        * title_transfers: instrument_type, parent/derivative, transferor/transferee, status
    """
    where_clause = ("(%s = ANY(h.matter_codes) OR h.case_file = %s)"
                    if matter_code else "h.case_file = %s")
    params = (matter_code, case_file) if matter_code else (case_file,)

    cur.execute(f"""
        SELECT
          h.id,
          COALESCE(h.event_date, h.date_executed, h.date_filed, h.date_received) AS primary_date,
          h.event_date, h.event_datetime, h.event_kind, h.event_kind_canonical,
          h.date_executed, h.date_filed, h.date_received,
          h.who_from, h.who_to, h.what_summary, h.citation_ref,
          h.provenance, h.source_table, h.source_id,
          h.matter_codes, h.title_refs, h.party_refs,

          d.classification     AS doc_classification,
          d.smart_filename     AS doc_smart_filename,
          d.original_filename  AS doc_original_filename,
          d.document_title     AS doc_title,
          d.execution_status   AS doc_execution_status,
          LEFT(d.extracted_text, 600) AS doc_text_snippet,
          d.analyst_memo       AS doc_analyst_memo,

          t.amount             AS tx_amount,
          t.direction          AS tx_direction,
          t.category           AS tx_category,
          t.counterparty       AS tx_counterparty,
          t.payment_method     AS tx_payment_method,
          t.description        AS tx_description,

          g.subject            AS gmail_subject,
          g.from_addr          AS gmail_from,
          g.from_name          AS gmail_from_name,
          LEFT(g.body_plain, 400) AS gmail_body_snippet,

          ce.title             AS cal_title,
          ce.description       AS cal_description,
          ce.location          AS cal_location,
          ce.attendees         AS cal_attendees,

          tt.instrument_type   AS tt_instrument_type,
          tt.parent_title      AS tt_parent_title,
          tt.derivative_title  AS tt_derivative_title,
          tt.transferor        AS tt_transferor,
          tt.transferee_name   AS tt_transferee_name,
          tt.entry_pe_number   AS tt_pe_number,
          tt.status            AS tt_status
        FROM client_history h
        LEFT JOIN documents d
          ON h.source_table = 'documents'      AND h.source_id = d.id::text
        LEFT JOIN transactions t
          ON h.source_table = 'transactions'   AND h.source_id = t.id::text
        LEFT JOIN gmail_messages g
          ON h.source_table = 'gmail_messages' AND h.source_id = g.id::text
        LEFT JOIN calendar_events ce
          ON h.source_table = 'calendar_events' AND h.source_id = ce.id::text
        LEFT JOIN title_transfers tt
          ON h.source_table = 'title_transfers' AND h.source_id = tt.id::text
        WHERE {where_clause}
        ORDER BY primary_date NULLS LAST, event_datetime NULLS LAST, h.id
    """, params)
    return cur.fetchall()


# ── Classification → human Action translation ──────────────────────────
# Avoids per-event LLM cost (1034 events would cost too much). The
# classification field is the canonical source of "what kind of doc this is";
# we lift it into verb-form action.
CLASSIFICATION_TO_ACTION = {
    "deed":                          "Execution of Deed",
    "deed_of_sale":                  "Execution of Deed of Sale",
    "deed_of_absolute_sale":         "Execution of Deed of Absolute Sale",
    "deed_of_donation":              "Execution of Deed of Donation",
    "deed_of_confirmation":          "Execution of Deed of Confirmation",
    "special_power_of_attorney":     "Execution of Special Power of Attorney",
    "power_of_attorney":             "Execution of Power of Attorney",
    "affidavit":                     "Execution of Affidavit",
    "judicial_affidavit":            "Execution of Judicial Affidavit",
    "affidavit_of_confirmation":     "Execution of Affidavit of Confirmation",
    "affidavit_of_loss":             "Execution of Affidavit of Loss",
    "complaint":                     "Filing of Complaint",
    "complaint-affidavit":           "Filing of Complaint-Affidavit",
    "motion":                        "Filing of Motion",
    "petition":                      "Filing of Petition",
    "petition_for_certiorari":       "Filing of Petition for Certiorari",
    "reply":                         "Filing of Reply",
    "answer":                        "Filing of Answer",
    "court_filing":                  "Court Filing",
    "court_order":                   "Issuance of Court Order",
    "order":                         "Issuance of Court Order",
    "decision":                      "Court Decision Issued",
    "resolution":                    "Resolution Issued",
    "notice":                        "Notice Issued",
    "letter":                        "Correspondence (Letter)",
    "demand_letter":                 "Demand Letter Sent",
    "transcript":                    "Hearing Transcript",
    "tax_document":                  "Tax Declaration / Tax Document",
    "receipt":                       "Payment Receipt",
    "title":                         "Title Document",
    "title_(tct/oct)":               "Title (TCT/OCT) — Issuance or Certification",
    "title_(tct)":                   "Title (TCT) — Issuance or Certification",
    "title_issued":                  "Title Issued",
    "certificate":                   "Certificate Issued",
    "death_certificate":             "Death Certificate",
    "government_submission":         "Government Submission",
    "request":                       "Formal Request Submitted",
    "legal_memorandum":              "Legal Memorandum",
    "memorandum":                    "Memorandum",
    "contract":                      "Contract Executed",
    "plan":                          "Survey / Subdivision Plan",
    "financial_statement":           "Financial Statement",
    "newspaper":                     "Newspaper Publication / Notice",
}


def translate_action(event):
    """Map a row's classification/event_kind to a human verb-phrase. No LLM."""
    raw = (event.get("doc_classification") or event.get("event_kind") or "").strip().lower().replace(" ", "_")
    raw = raw.replace("(tct/oct)", "(tct/oct)")  # normalize
    if raw in CLASSIFICATION_TO_ACTION:
        return CLASSIFICATION_TO_ACTION[raw]
    # Try prefix match for annotation_*
    if raw.startswith("annotation_"):
        sub = raw.replace("annotation_", "").replace("_", " ").strip()
        return f"Annotation on Title — {sub.title()[:60]}"
    if raw.startswith("tx_"):
        return "Transaction"
    if raw.startswith("intake_"):
        return f"System Intake ({raw.replace('intake_','').replace('_', ' ')})"
    if raw.startswith("deadline_"):
        return f"Deadline ({raw.replace('deadline_','')})"
    # Fall back to source_table verbs
    st = (event.get("source_table") or "").lower()
    if st == "gmail_messages":
        # direction inferred from event_kind raw
        if "sent" in (event.get("event_kind") or "").lower():
            return "Outbound Email"
        return "Inbound Email"
    if st == "transactions":
        d = event.get("tx_direction") or ""
        return f"Money {'Outflow' if d=='out' else 'Inflow' if d=='in' else 'Transaction'}"
    if st == "title_transfers":
        return "Title Transfer / Lineage Event"
    return "Event"


def build_substantive_context(event):
    """Compose the rich context line. NEVER 'unknown' — either substance or
    explicit '[Context Missing in DB]' marker.
    """
    parts = []

    # Document substance
    if event.get("doc_text_snippet"):
        snippet = event["doc_text_snippet"].strip()
        # Filter obvious OCR noise (mostly non-ascii / short tokens)
        if len(snippet) >= 30 and sum(c.isalpha() for c in snippet) / max(len(snippet), 1) > 0.5:
            # Drop leading garbage like "rtEstsoONO64460..." — take first sentence
            import re
            sentences = re.split(r'(?<=[.!?:])\s+', snippet)
            keep = " ".join(s for s in sentences if len(s) > 12 and
                            sum(c.isalpha() for c in s) / max(len(s), 1) > 0.55)[:500]
            if keep:
                parts.append(keep)
    # Document title (often a manual one-liner)
    if event.get("doc_title") and event["doc_title"] != event.get("doc_smart_filename"):
        parts.append(f"Title: {event['doc_title']}")
    # Analyst memo (JSON — pull useful fields)
    memo = event.get("doc_analyst_memo")
    if memo and isinstance(memo, dict):
        for key in ("summary", "subject_brief", "key_facts"):
            if memo.get(key):
                parts.append(f"{key}: {str(memo[key])[:300]}")
                break

    # Transaction substance
    if event.get("tx_amount") is not None:
        d = event.get("tx_direction") or "?"
        cat = event.get("tx_category") or "transaction"
        cp = event.get("tx_counterparty") or "(counterparty unknown)"
        method = event.get("tx_payment_method") or ""
        amt = float(event["tx_amount"])
        verb = "Paid" if d == "out" else "Received" if d == "in" else "Movement of"
        parts.append(f"{verb} P{amt:,.2f} for {cat} to/from {cp}"
                     + (f" via {method}" if method else ""))
        if event.get("tx_description"):
            parts.append(f"  Description: {event['tx_description'][:300]}")

    # Gmail substance
    if event.get("gmail_subject"):
        sender = event.get("gmail_from_name") or event.get("gmail_from") or "?"
        parts.append(f"Subject: {event['gmail_subject'][:200]} (from: {sender})")
    if event.get("gmail_body_snippet"):
        body = event["gmail_body_snippet"].strip().replace("\n", " ")
        if len(body) > 20:
            parts.append(f"Body: {body[:400]}")

    # Calendar substance
    if event.get("cal_title"):
        parts.append(f"Event: {event['cal_title']}"
                     + (f" @ {event['cal_location']}" if event.get("cal_location") else ""))
        if event.get("cal_description"):
            parts.append(f"  {event['cal_description'][:300]}")

    # Title transfer substance
    if event.get("tt_instrument_type"):
        ext = (f"{event['tt_instrument_type']}: "
               f"{event['tt_parent_title']} → {event['tt_derivative_title']} "
               f"(transferor: {event['tt_transferor'] or '?'} → "
               f"transferee: {event['tt_transferee_name'] or '?'})")
        if event.get("tt_pe_number"):
            ext += f" [PE# {event['tt_pe_number']}]"
        parts.append(ext)

    if parts:
        return " · ".join(parts)
    # Fall back to bible-level what_summary
    if event.get("what_summary") and not event["what_summary"].startswith("doc — "):
        return event["what_summary"]
    return "[Context Missing in DB]"


def collect_entities_titles(event):
    """Combine title_refs[] + key parties (transferees + email senders + transaction
    counterparties) into a single list for the Key Entities/Titles line."""
    parts = []
    if event.get("title_refs"):
        parts.append("Titles: " + ", ".join(event["title_refs"][:8]))
    persons = []
    for k in ("tt_transferor", "tt_transferee_name", "tx_counterparty",
               "gmail_from_name", "who_from", "who_to"):
        v = event.get(k)
        if v and v not in ("—", "?", "unknown", ""):
            persons.append(v)
    if persons:
        parts.append("Persons: " + ", ".join(dict.fromkeys(persons[:6])))  # dedup, preserve order
    if event.get("tx_amount") is not None:
        parts.append(f"Amount: P{float(event['tx_amount']):,.2f}")
    if event.get("party_refs"):
        parts.append("party_ids: " + ", ".join(str(p) for p in event["party_refs"][:5]))
    if not parts:
        return "[No entities/titles linked]"
    return " · ".join(parts)


def fetch_critical_deadlines(cur, case_file):
    cur.execute("""
        SELECT id, title, due_date, status, priority_tier, deadline_type, stage_key
          FROM case_deadlines
         WHERE case_file = %s AND status IN ('pending','at_risk')
         ORDER BY due_date NULLS LAST
    """, (case_file,))
    return cur.fetchall()


def fetch_coverage_warnings(cur, client_code):
    """Only the latest audit run (de-dups multi-run accumulation)."""
    cur.execute("""
        WITH latest AS (
          SELECT MAX(audit_run_at) AS run_at
            FROM coverage_audit_findings
           WHERE client_code = %s
        )
        SELECT reason, COUNT(*) AS n,
               (SELECT run_at FROM latest)::date AS run_date
          FROM coverage_audit_findings, latest
         WHERE client_code = %s
           AND audit_run_at = latest.run_at
         GROUP BY reason
         ORDER BY n DESC
    """, (client_code, client_code))
    return cur.fetchall()


def project_forward(matter_row):
    """Single-matter projection (used in matter-scoped runs)."""
    if not matter_row or not matter_row.get("current_stage"):
        return []
    return _project_one(matter_row.get("matter_code") or matter_row.get("case_file"),
                        matter_row["current_stage"], matter_row.get("stage_updated_at"))


def _project_one(matter_code, stage, anchor):
    proj_rules = STAGE_PROJECTIONS.get(stage)
    if not proj_rules:
        return []
    if anchor and hasattr(anchor, 'date'):
        anchor_date = anchor.date()
    elif anchor:
        anchor_date = anchor
    else:
        anchor_date = date.today()
    today = date.today()
    out = []
    for days, label, kind in proj_rules:
        projected_date = anchor_date.fromordinal(anchor_date.toordinal() + days)
        delta = (projected_date - today).days
        when = ("OVERDUE by " + str(-delta) + "d" if delta < 0 else
                "TODAY" if delta == 0 else
                "in ~" + str(delta) + " days")
        out.append({
            "matter_code": matter_code, "date": projected_date,
            "label": label, "kind": kind, "delta": delta, "when": when,
        })
    return out


def project_forward_omnibus(cur, case_file):
    """Omnibus projection: every active matter under the case_file contributes."""
    cur.execute("""
        SELECT matter_code, current_stage, stage_updated_at, title
          FROM matters
         WHERE case_file = %s
           AND current_stage NOT IN ('resolved_no_merit','closed','disposed','dismissed')
           AND current_stage IS NOT NULL
         ORDER BY matter_code
    """, (case_file,))
    all_proj = []
    for m in cur.fetchall():
        per_matter = _project_one(m["matter_code"], m["current_stage"], m["stage_updated_at"])
        all_proj.extend(per_matter)
    # Merge: sort by date, take next 10 (omnibus shows more since multiple matters firing)
    all_proj.sort(key=lambda p: (p["date"], p["matter_code"]))
    upcoming = [p for p in all_proj if p["delta"] >= -90]  # show overdue up to 90d back too
    return upcoming[:10]


PER_CLIENT_KNOWN_GAPS = {
    "MWK-001": [
        ("2005 Revocation of SPA (Cesar dela Fuente)",
         "Currently testimonial via Judicial Affidavit doc#441. Primary notarized "
         "instrument missing — single biggest evidence gap on the void-SPA theory."),
        ("Mary Worrick Keesey death certificate (PSA-issued, ~1988)",
         "Testimonial only via project memory; PSA-certified primary document not in corpus."),
        ("Cesar dela Fuente death certificate (2017)",
         "Referenced in LandBank's CV-6839 filing (doc#364); primary PSA certificate not yet ingested."),
        ("The 2016 Deed of Sale (Cesar → buyer that led to T-52540 cancellation)",
         "The void deed at issue in CV 26-360. Not directly in corpus per current scan."),
    ],
    "Paracale-001": [
        # Allan's known evidence gaps go here as they surface. Empty until
        # Allan's case theory enumerates load-bearing missing instruments
        # (e.g., PAR-VITO-CRUZ judgment certified copy, PAR-TCT1616 mother title).
    ],
    "Owner": [],
}

# Per-client orphan-event probe (replaces the MWK-specific T-4497/Cesar hint).
PER_CLIENT_ORPHAN_HINT = {
    "MWK-001":      "what touched T-4497 or what did Cesar do",
    "Paracale-001": "what touched PAR-TCT1616 or what did Allan Inocalla do",
    "Owner":        "what's in the family-history archive",
}


def detect_gaps(events, deadlines, case_file="MWK-001"):
    """Anomaly detection over the timeline. Returns list of findings.

    Parameterized by case_file so per-client known-evidence-gaps surface in
    the gap report without cross-contaminating other clients' bibles. Each
    client's BIBLE_KNOWN_GAPS list lives in PER_CLIENT_KNOWN_GAPS[case_file].
    """
    findings = []
    # 1. Year-gap detection: contiguous years where no events exist (suggests missing records)
    years_with_events = sorted({e["primary_date"].year for e in events if e["primary_date"]})
    if years_with_events:
        for i in range(len(years_with_events) - 1):
            gap = years_with_events[i+1] - years_with_events[i]
            if gap >= 3:
                findings.append({
                    "kind": "year_gap",
                    "severity": "medium",
                    "detail": (f"No events recorded between {years_with_events[i]} and "
                               f"{years_with_events[i+1]} ({gap}-year gap)."),
                })

    # 2. Date-inconsistency: date_filed before date_executed (impossible)
    for e in events:
        if e["date_executed"] and e["date_filed"] and e["date_filed"] < e["date_executed"]:
            findings.append({
                "kind": "date_anomaly",
                "severity": "high",
                "detail": (f"Event #{e['id']} ({e['what_summary'][:80]}): "
                           f"date_filed {e['date_filed']} precedes "
                           f"date_executed {e['date_executed']}."),
            })

    # 3. Uncited assertions: events with provenance!='verified' on legal_act / title_event
    weak_legal = [e for e in events
                  if e.get("event_kind_canonical") in ("legal_act","title_event","title_annotation")
                  and e.get("provenance") not in ("verified",)]
    if weak_legal:
        findings.append({
            "kind": "weak_legal_provenance",
            "severity": "high",
            "detail": (f"{len(weak_legal)} legal-act/title events lack verified provenance "
                       "— cannot be cited as fact in court output without upgrade."),
        })

    # 4. Orphan events: legal_act with no title_refs and no party_refs (rootless)
    orphans = [e for e in events
               if e.get("event_kind_canonical") == "legal_act"
               and not e.get("title_refs") and not e.get("party_refs")]
    if orphans:
        hint = PER_CLIENT_ORPHAN_HINT.get(case_file, "what touched the case")
        findings.append({
            "kind": "orphan_legal_acts",
            "severity": "medium",
            "detail": (f"{len(orphans)} legal-act events have no linked TCT or party "
                       f"(can't be queried by '{hint}')."),
        })

    # 5. Critical missing primary instruments (per-client known gaps).
    known_gaps = PER_CLIENT_KNOWN_GAPS.get(case_file, [])
    for label, why in known_gaps:
        findings.append({
            "kind": "missing_primary_instrument",
            "severity": "critical",
            "detail": f"{label}: {why}",
        })

    return findings


def md_escape(s):
    if s is None: return ""
    return str(s).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def shorten_matter_tag(mc):
    """Make a compact human-readable tag for inline timeline use.
    MWK-CV26360       → CV-26360
    MWK-ARTA-1378     → ARTA-1378
    MWK-PARALLEL-CV6922 → PAR-CV6922
    MWK-TCT4497       → TCT-4497
    MWK-ESTATE        → ESTATE
    """
    if not mc: return "GENERAL"
    parts = mc.split("-", 1)
    if len(parts) == 2 and parts[0] == "MWK":
        return parts[1].replace("PARALLEL-", "PAR-")
    return mc


# Client display names — used for omnibus header
CLIENT_DISPLAY_NAMES = {
    "MWK-001":      "Heirs of Mary Worrick Keesey (MWK-001)",
    "Paracale-001": "Paracale Estate of Allan V. Inocalla (Paracale-001)",
    "Owner":        "Owner File (Owner)",
}


# ── Per-client critical-facts framing for the year-narrative LLM ────────
# THIS IS THE LOAD-BEARING ANTI-CROSS-CONTAMINATION DICTIONARY.
# Each entry tells the narrative-LLM:
#   - what client we're writing for
#   - which matter codes are in scope
#   - which factual invariants must not be violated
#   - which adjacent matters to NOT bleed into the narrative
# Symptom of bad framing: a Paracale-001 bible whose narrative reads
# "# MWK-ESTATE Master Case Bible — 2021 Summary". See drafts/
# bible_OMNIBUS_Paracale-001_2026-06-05.md pre-fix.
BIBLE_NARRATIVE_CRITICAL_FACTS = {
    "MWK-001": (
        "## CRITICAL FACTS — these MUST be respected (Opus audit gate enforced)\n\n"
        "- **MWK-001 / MWK-ESTATE is the TOP-LEVEL parent.** CV-26360, CV-6839, "
        "TCT-4497 chain verification, ARTA matters, and tax/title administration "
        "are SIBLING subtracks. Do NOT collapse estate work into CV-26360.\n"
        "- **Cesar N. dela Fuente died 21 June 2017** (cited in LandBank's filing "
        "in CV-6839, doc#364). ANY narrative attributing legal action to Cesar after "
        "21 June 2017 is IMPOSSIBLE and a data error. Omit him from 2018+ attribution; "
        "attribute to Patricia/Jonathan/Atty. Barandon or the holding office instead.\n"
        "- **Civil Case 26-360 trial court: Municipal Trial Court of Mercedes**, "
        "Province of Camarines Norte, Fifth Judicial Region "
        "(mtc2mcd000@judiciary.gov.ph). VERIFIED via Notice of Pre-trial Conference "
        "(doc#392) and the court Order (doc#423), both officially headed MTC Mercedes. "
        "Court-annexed mediation is hosted at the RTC Daet Mediation Center "
        "(Philippine Mediation Center). 'Daet RTC' references in chat notes refer to "
        "the mediation venue, NOT a transfer of the case file from MTC.\n"
        "- **Mediation HELD on 2 June 2026** (per Jonathan direct, chat_notes#1208). "
        "Attendees: Atty. Barandon (plaintiff counsel), Efren M. Balane "
        "('Councilor Balane' / Kgd. Sanggunian member, defendant), Engr. Erwin H. "
        "Balane (defendant). Notably absent: Gloria H. Balane (primary TCT-holder "
        "defendant). Specific outcome (settlement / impasse / continuance) pending "
        "capture.\n"
        "- **Balane defendant family** (verified via Jonathan / Rule S13): Gloria H. "
        "Balane + Efren M. Balane are spouses + primary defendants; Princess Balane "
        "Torralba is their daughter (also a defendant, married to Jomil Torralba). "
        "The case is a family enterprise, not independent co-defendants.\n"
        "- **CV-6839 (just-compensation vs LandBank)** is its own track, applying "
        "ONLY to the agrarian/CARP title set {T-30681, T-30682, T-30683, T-4494, "
        "T-4501, T-4502, T-4503, T-14}. Do NOT mix with T-4497 chain.\n"
        "- **TCT-4497 chain** is the contested-Balane chain "
        "(T-4497 → T-32916/32917/31298 → T-079-2021002126). Title-chain certification "
        "work is ESTATE administration, NOT Balane litigation, unless a pleading cites it.\n"
        "- **Patricia Keesey Zschoche** (spelling KEESEY — verified against 307 corpus "
        "occurrences including her birth certificate and the RTC Order caption).\n"
        "- **Two distinct Pajarillos:** Alexander L. Pajarillo (Mayor of Mercedes, "
        "ARTA-0747 respondent — our matter) and Amado V. Pajarillo (deceased "
        "landowner in parallel CV-6922 — NOT our matter). Do not conflate.\n"
        "- **Parallel-tracking matters CV-6922 (Pajarillo Heirs vs DAR) and Crim-9221 "
        "(People vs Eduardo Ibana)** are observed, not litigated by MWK. Do not "
        "narrate them as MWK actions. Only mention if a doc# directly references them.\n"
        "- **ARTA dockets:** 0690, 0747, 0792, 1210, 1212, 1319, 1321, 1378, 1891, DILG. "
        "All 10 exist. Do not invent dockets or assume typos.\n"
        "- **DO NOT bleed in PAR / Paracale / Inocalla / Capacuan / Vito Cruz / Golden Sand. "
        "Those are a different client's matters.**\n"
    ),
    "Paracale-001": (
        "## CRITICAL FACTS — these MUST be respected\n\n"
        "- **Client: Allan V. Inocalla** (Paracale-001). The matters in scope are the "
        "PAR-* set: PAR-CAPACUAN, PAR-CASE-88750 (Inocalla estate mineral rights), "
        "PAR-COMPLAINT-ACE, PAR-CV13-131220, PAR-GOLDEN-SAND (Golden Sand Beach Resort), "
        "PAR-TCT1616 (title-chain verification), PAR-VITO-CRUZ (judgment won, "
        "pending title reconveyance), and AUTO-PARACALE_001.\n"
        "- **DO NOT bleed in MWK / Mary Worrick Keesey / Patricia Keesey Zschoche / "
        "Cesar de la Fuente / Gloria Balane / T-4497 / CV-26360 / CV-6839 / ARTA. "
        "Those are a DIFFERENT CLIENT's matters and have no place in a Paracale narrative.**\n"
        "- **PAR-CAPACUAN** = Capacuan mining/asset dispute, linked to Paracale Gold "
        "Corporation (PGC) TSX-V listing tracking — see case_theories/par_capacuan_tsx_listing.py.\n"
        "- **PAR-VITO-CRUZ** has a final judgment in Allan's favor; the open work is "
        "title reconveyance, NOT relitigation.\n"
        "- **PAR-CV13-131220** was declared unrelated by the principal on 2026-05-20; "
        "mention only if a doc explicitly references it for record-keeping.\n"
        "- Allan's matters are in Paracale / Camarines Norte / Manila NCR jurisdictions. "
        "If an event has no PAR-* matter tag, attribute it to PAR-* only via doc# citation.\n"
        "- Inocalla family members: Allan V. Inocalla (principal), Jesus V. Inocalla "
        "(sibling co-petitioner), Shishir Allan Inocalla (martial-arts persona — may be "
        "the same person, held separate canonical pending clarification). Francisco V. "
        "Inocalla appears in Civil Case 98-88750 collateral material.\n"
    ),
    "Owner": (
        "## CRITICAL FACTS — Owner bucket\n\n"
        "- **Owner = Jonathan Paul Zschoche's personal/family file** (passports, "
        "birth records, family research, archive certifications).\n"
        "- This is NOT a legal matter in the representation sense. Narratives should "
        "be factual and family-historical, not litigation-flavored.\n"
        "- Some Owner docs cross-link to MWK matters (e.g., Patricia's passport copy "
        "may be MWK-ESTATE evidence). Cross-references are fine; do not import MWK "
        "litigation framing into Owner narratives.\n"
    ),
}


# ── LLM narrative synthesis (Layer D narrative weaving) ────────────────
def synthesize_year_narratives(events, case_file="MWK-001"):
    """Group events by year, send each year's enriched events to Haiku for a
    paragraph narrative. Returns {year: narrative_text}.

    Parameterized by case_file so the per-client critical-facts framing
    (BIBLE_NARRATIVE_CRITICAL_FACTS[case_file]) gates the LLM and prevents
    cross-client contamination (e.g., a Paracale-001 bible whose narrative
    leaks MWK-ESTATE framing).

    Cost-disciplined per [[feedback_cost_discipline]]:
      - Haiku only (no Sonnet/Opus)
      - Skip years with < 2 events (no narrative needed)
      - Cap events per year at 50 in the prompt
      - Cache nothing in this run; per-year calls
    Estimated cost for 1034-event corpus: $0.10-0.20.
    """
    import os
    from itertools import groupby
    if os.environ.get("BIBLE_SKIP_LLM"):
        return {}
    try:
        import anthropic
        from landtek_core import get
        from llm_billing import anthropic_call
    except Exception as e:
        print(f"  ⚠ LLM unavailable for narratives: {e}")
        return {}
    api_key = get("ANTHROPIC_API_KEY") if 'get' in dir() else None
    if not api_key:
        try:
            for l in open("/root/landtek/.env"):
                if l.startswith("ANTHROPIC_API_KEY="):
                    api_key = l.split("=", 1)[1].strip(); break
        except Exception:
            pass
    if not api_key:
        print("  ⚠ no ANTHROPIC_API_KEY — narratives skipped")
        return {}
    client = anthropic.Anthropic(api_key=api_key)

    narratives = {}
    by_year = {y: list(g) for y, g in
                groupby(sorted(events, key=lambda e: e["primary_date"]),
                        key=lambda e: e["primary_date"].year)}
    # Importance tiers for stratified sampling. Critical legal acts and judicial
    # events always included; transactions/tax_documents subsampled.
    PRIORITY_KINDS = {
        # Always include
        "legal_act": 0, "judicial_event": 0, "title_event": 0, "title_annotation": 0,
        "vital_record": 0, "procedural_intake": 0, "legal_memo": 0,
        # Cap-limited
        "correspondence": 2, "government_submission": 2, "survey_plan": 2,
        "tax_document": 3, "transaction": 3, "uncategorized": 4,
    }
    total_cost_estimate = 0.0
    for year, year_events in by_year.items():
        if len(year_events) < 2:
            continue  # single-event years are self-explanatory
        # Stratified sampling: cap = 50 per year, but always include high-tier kinds.
        # Group by tier; fill tier-0 entirely, then sample from tier-1/2/3 by count.
        from collections import defaultdict as _dd
        buckets = _dd(list)
        for ev in year_events:
            tier = PRIORITY_KINDS.get(ev.get("event_kind_canonical") or "", 5)
            buckets[tier].append(ev)
        sample = []
        for tier in sorted(buckets.keys()):
            tier_events = buckets[tier]
            if tier == 0:
                sample.extend(tier_events)  # always all
            else:
                # Stride-sample uniformly across the year
                remaining = max(0, 50 - len(sample))
                if remaining <= 0:
                    break
                if len(tier_events) <= remaining:
                    sample.extend(tier_events)
                else:
                    stride = max(1, len(tier_events) // remaining)
                    sample.extend(tier_events[::stride][:remaining])
        sample.sort(key=lambda e: e["primary_date"])
        sample = sample[:60]  # hard cap (tier-0 can blow past 50)
        lines = []
        for e in sample:
            mcodes = ", ".join(shorten_matter_tag(mc) for mc in (e.get("matter_codes") or [])[:2]) or "GENERAL"
            action = translate_action(e)
            # Brief substance for the LLM (smaller than the event-log version)
            substance_bits = []
            if e.get("doc_text_snippet"):
                t = e["doc_text_snippet"].strip()[:200].replace("\n", " ")
                if sum(c.isalpha() for c in t)/max(len(t),1) > 0.4:
                    substance_bits.append(t)
            if e.get("tx_amount") is not None:
                substance_bits.append(f"P{float(e['tx_amount']):,.0f} {e.get('tx_direction','?')} "
                                       f"{e.get('tx_category','')} "
                                       f"to/from {e.get('tx_counterparty','?')}")
            if e.get("gmail_subject"):
                substance_bits.append(f"email subj: {e['gmail_subject'][:120]}")
            if e.get("tt_instrument_type"):
                substance_bits.append(f"{e['tt_instrument_type']}: "
                                       f"{e.get('tt_parent_title','?')}→"
                                       f"{e.get('tt_derivative_title','?')}")
            substance = " | ".join(substance_bits)[:300]
            titles = ",".join((e.get("title_refs") or [])[:4])
            prov = e.get("citation_ref") or f"{e['source_table']}#{e['source_id']}"
            lines.append(f"{e['primary_date'].isoformat()} [{mcodes}] {action}"
                          + (f" — {substance}" if substance else "")
                          + (f" ({titles})" if titles else "")
                          + f" [prov: {prov}]")

        client_display = CLIENT_DISPLAY_NAMES.get(case_file, case_file)
        critical_facts = BIBLE_NARRATIVE_CRITICAL_FACTS.get(case_file, "")
        prompt = (
            f"You are a senior paralegal writing a Master Case Bible for "
            f"{client_display}, a Philippine property matter.\n\n"
            + critical_facts
            + f"\n## TASK\n\n"
            f"Below are all events recorded in {year}"
            + (f" (showing first {len(sample)} of {len(year_events)})" if len(year_events) > 50 else "")
            + ". Write a SINGLE paragraph (5-9 sentences max) summarizing this year:\n"
            f"  - What happened (concrete legal acts, not 'a document was filed').\n"
            f"  - Who was involved (named persons/entities — Patricia Keesee Zschoche, "
            f"Jonathan Zschoche, Atty. Barandon, Gloria Balane, LBP, RTC Br. 64, ARTA, etc.).\n"
            f"  - How administrative ARTA cases, civil filings, and property "
            f"transactions interconnect — but DO NOT manufacture causal chains where "
            f"the docs only co-exist temporally.\n"
            f"  - Embed provenance citations inline like [doc#123].\n\n"
            f"DO NOT use filenames. DO NOT mention .pdf. Describe LEGAL ACTIONS.\n"
            f"DO NOT soften a claim by using hedge words instead of citing the evidence — "
            f"either cite a doc# or omit the claim.\n"
            f"If the year is genuinely uneventful, say so in 1-2 sentences. Do not pad.\n\n"
            f"Events:\n" + "\n".join(lines)
        )

        try:
            msg = anthropic_call(
                client, called_from="generate_case_bible", purpose="year_narrative",
                case_file=case_file,
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                system="You are a senior paralegal. Concise, evidence-cited, no fluff.",
                messages=[{"role": "user", "content": prompt}],
            )
            text = msg.content[0].text.strip()
            narratives[year] = text
            in_tok = msg.usage.input_tokens
            out_tok = msg.usage.output_tokens
            total_cost_estimate += (in_tok * 0.8 + out_tok * 4.0) / 1_000_000
            print(f"  narrative for {year}: {in_tok}in/{out_tok}out tok ({len(year_events)} events)")
        except Exception as e:
            print(f"  ⚠ narrative error for {year}: {str(e)[:120]}")

    print(f"  ── LLM narratives: ~${total_cost_estimate:.3f} spent on {len(narratives)} years ──")
    return narratives


# ── Cross-reference index builder (Layer D appendix) ───────────────────
def build_cross_reference_index(events):
    """Aggregate every title_ref, every named person, and every matter_code
    into a relational index. Returns dict with three sub-dicts.

    deploy_167: filter to substantive events only (same rule as the detailed
    event log) — index value is navigation, not completeness; including 169
    routine tax-doc/transaction entries buries the events that matter."""
    from collections import defaultdict
    SUBSTANTIVE_KINDS = {"legal_act", "judicial_event", "vital_record",
                          "government_submission", "legal_memo", "title_event"}
    SUBSTANTIVE_CORRESPONDENCE_KEYWORDS = (
        "demand", "notice", "order", "petition", "motion", "reply",
        "complaint", "affidavit", "memorandum", "subpoena", "decision",
        "judgment", "manifestation", "rejoinder",
    )

    def _is_substantive(ev):
        kind = ev.get("event_kind_canonical") or ""
        if kind in SUBSTANTIVE_KINDS:
            return True
        if kind == "correspondence":
            blob = ((ev.get("doc_classification") or "") + " " +
                    (ev.get("doc_title") or "") + " " +
                    (ev.get("doc_smart_filename") or "")).lower()
            return any(k in blob for k in SUBSTANTIVE_CORRESPONDENCE_KEYWORDS)
        return False

    events = [e for e in events if _is_substantive(e)]
    by_title = defaultdict(list)
    by_person = defaultdict(list)
    by_matter = defaultdict(list)

    def short_summary(e):
        # Best-effort one-line summary for the index
        act = translate_action(e)
        if e.get("tx_amount") is not None:
            return f"{act} P{float(e['tx_amount']):,.0f} ({e.get('tx_category','')})"
        if e.get("gmail_subject"):
            return f"{act}: {e['gmail_subject'][:80]}"
        if e.get("tt_instrument_type"):
            return f"{act} ({e['tt_instrument_type']})"
        if e.get("doc_classification"):
            return f"{act}"
        return act

    for e in events:
        if not e.get("primary_date"):
            continue
        d = e["primary_date"]
        eid = e["id"]
        prov = e.get("citation_ref") or f"{e['source_table']}#{e['source_id']}"
        summ = short_summary(e)
        # Titles
        for t in (e.get("title_refs") or []):
            by_title[t].append((d, eid, summ, prov))
        # Persons — combine multiple sources
        persons = set()
        for k in ("tt_transferor", "tt_transferee_name", "tx_counterparty",
                   "gmail_from_name", "who_from", "who_to"):
            v = e.get(k)
            if v and v not in ("—", "?", "unknown", "", "system"):
                persons.add(v.strip())
        for p in persons:
            by_person[p].append((d, eid, summ, prov))
        # Matters
        for mc in (e.get("matter_codes") or []):
            by_matter[mc].append((d, eid, summ, prov))
    return {"by_title": by_title, "by_person": by_person, "by_matter": by_matter}


def render_cross_reference_index(index):
    out = ["", "# 5. CROSS-REFERENCE INDEX", "",
           "_Relational appendix. Every title, person, and matter mapped to every "
           "event it appears in. Use this when opposing counsel raises a specific TCT "
           "or actor — flip here, see every chronological touch._", ""]

    # By Title
    out.append("## 5.1 By Title (TCT / OCT)")
    out.append("")
    titles = sorted(index["by_title"].items(), key=lambda kv: -len(kv[1]))
    for t, entries in titles:
        if len(entries) < 1: continue
        sorted_entries = sorted(entries, key=lambda x: x[0])
        out.append(f"### {t} _({len(sorted_entries)} touches)_")
        for d, eid, summ, prov in sorted_entries:
            out.append(f"- **{d}** — {md_escape(summ)} _[event#{eid} · {prov}]_")
        out.append("")

    # By Key Person
    out.append("## 5.2 By Key Person / Entity")
    out.append("")
    persons = sorted(index["by_person"].items(), key=lambda kv: -len(kv[1]))
    # Filter noise: skip persons appearing only once unless their name is clearly substantive
    for p, entries in persons:
        if len(entries) < 2 and len(p) < 12:
            continue  # likely OCR artifact
        sorted_entries = sorted(entries, key=lambda x: x[0])[:25]  # cap per-person to 25 most recent
        out.append(f"### {md_escape(p)} _({len(entries)} touches)_")
        for d, eid, summ, prov in sorted_entries:
            out.append(f"- **{d}** — {md_escape(summ)} _[event#{eid} · {prov}]_")
        if len(entries) > 25:
            out.append(f"  _… and {len(entries)-25} earlier events suppressed._")
        out.append("")

    # By Matter
    out.append("## 5.3 By Matter")
    out.append("")
    matters = sorted(index["by_matter"].items(), key=lambda kv: -len(kv[1]))
    for mc, entries in matters:
        sorted_entries = sorted(entries, key=lambda x: x[0])
        out.append(f"### {shorten_matter_tag(mc)} _(full code: {mc} · {len(sorted_entries)} touches)_")
        # For matters with >30 events, show first + last 15 of each instead of all
        if len(sorted_entries) > 30:
            for d, eid, summ, prov in sorted_entries[:15]:
                out.append(f"- **{d}** — {md_escape(summ)} _[event#{eid}]_")
            out.append(f"  _… {len(sorted_entries)-30} middle events suppressed (see Section 3 timeline) …_")
            for d, eid, summ, prov in sorted_entries[-15:]:
                out.append(f"- **{d}** — {md_escape(summ)} _[event#{eid}]_")
        else:
            for d, eid, summ, prov in sorted_entries:
                out.append(f"- **{d}** — {md_escape(summ)} _[event#{eid}]_")
        out.append("")
    return "\n".join(out)


# ── Markdown renderer ───────────────────────────────────────────────────
def render_markdown(matter, events, deadlines, coverage, projected, gaps,
                    omnibus_mode=False, all_matters=None):
    today_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out = []

    # ── 1. Document Header ──
    out.append("# 1. DOCUMENT HEADER")
    out.append("")
    if omnibus_mode:
        client_name = CLIENT_DISPLAY_NAMES.get(matter["case_file"], matter["case_file"])
        out.append(f"- **Report Title:** Client: {client_name} — Omnibus Master Bible")
    else:
        title_id = matter.get("matter_code") or matter.get("case_file")
        out.append(f"- **Report Title:** {title_id} — Master Case Bible")
    out.append(f"- **Generated On:** {today_ts}")
    out.append(f"- **Total Logged Events:** {len(events)}")
    out.append(f"- **Case File:** {matter.get('case_file') or '—'}")
    out.append(f"- **Client Code:** {matter.get('client_code') or '—'}")
    if omnibus_mode and all_matters:
        out.append(f"- **Matters Under This Client:** {len(all_matters)}")
        out.append("")
        for m in all_matters:
            tag = shorten_matter_tag(m["matter_code"])
            stage_label = (m.get("current_stage") or "unknown")
            out.append(f"  - **[{tag}]** {m.get('title','—')[:90]} _(stage: {stage_label})_")
    elif matter.get("title"):
        out.append(f"- **Matter:** {matter['title']}")
        if matter.get("docket_number"):
            out.append(f"- **Docket:** {matter['docket_number']} · {matter.get('court_or_agency') or ''}")
        if matter.get("current_stage"):
            out.append(f"- **Current Stage:** `{matter['current_stage']}` "
                       f"(updated {matter.get('stage_updated_at').date() if matter.get('stage_updated_at') else '—'})")
    out.append("")

    # ── 2. Executive Summary & Forward Projection ──
    out.append("# 2. EXECUTIVE SUMMARY & FORWARD PROJECTION")
    out.append("")
    out.append("## Next Projected Events (stage-rule projection — Layer E)")
    if projected:
        for p in projected[:10]:
            tag = shorten_matter_tag(p.get("matter_code")) if p.get("matter_code") else ""
            tag_str = f"**[{tag}]** " if tag else ""
            out.append(f"- **{p['date']}** ({p['when']}) — {tag_str}{p['label']}  _[{p['kind']}]_")
        out.append("")
        out.append("_Projection basis: stage rules applied across every active matter under "
                   "the client. Not a substitute for actual court / agency schedules._")
    else:
        out.append("- _No projection rules defined for any active matter's current stage._")
    out.append("")

    out.append("## Critical Open Deadlines")
    if deadlines:
        for d in deadlines:
            days_until = (d["due_date"] - date.today()).days if d["due_date"] else None
            urgency = (f"OVERDUE by {-days_until}d" if (days_until is not None and days_until < 0)
                       else f"in {days_until}d" if days_until is not None
                       else "no date")
            out.append(f"- **{d['due_date']}** ({urgency}) — {d['title']} "
                       f"_[{d.get('priority_tier') or '?'}, {d['status']}]_")
    else:
        out.append("- _No open deadlines._")
    out.append("")

    out.append("## Coverage Audit Warnings (last 7 days)")
    if coverage:
        for c in coverage:
            out.append(f"- **{c['reason']}**: {c['n']} rows flagged")
    else:
        out.append("- _No outstanding coverage warnings._")
    out.append("")

    # ── 3. Master Timeline grouped by year ──
    out.append("# 3. THE MASTER TIMELINE")
    out.append("")
    from itertools import groupby
    dated = [e for e in events if e["primary_date"]]
    undated = [e for e in events if not e["primary_date"]]
    dated.sort(key=lambda e: (e["primary_date"], e["id"]))

    # Pre-compute LLM narratives for each year (cached/deduped at year level).
    # Pass case_file to engage the per-client critical-facts framing and
    # prevent cross-client contamination in the narrative text.
    year_narratives = synthesize_year_narratives(dated, case_file=matter.get("case_file") or "MWK-001")

    for year, year_events_iter in groupby(dated, key=lambda e: e["primary_date"].year):
        year_events = list(year_events_iter)
        out.append(f"### {year} — Annual Narrative Summary")
        out.append("")
        narr = year_narratives.get(year)
        if narr:
            out.append(f"*{narr}*")
        else:
            out.append(f"*{len(year_events)} events recorded in {year} "
                       "— narrative synthesis unavailable (likely <2 events or LLM error).*")
        out.append("")
        out.append("**Detailed Event Log:** _(substantive events only — legal acts, judicial events, vital records, government submissions, court orders, key correspondence)_")
        out.append("")
        # SUBSTANTIVE-ONLY FILTER (deploy_167 fix per Jonathan 2026-05-17):
        # The 635-page bloat came from rendering raw OCR for all 1,034 events including
        # 169 transactions, 109 tax docs, 52 title annotations. None of those help a
        # lawyer. Filter to high-signal canonical kinds + use analyst_memo summaries
        # instead of raw text dumps.
        SUBSTANTIVE_KINDS = {"legal_act", "judicial_event", "vital_record",
                              "government_submission", "legal_memo"}
        SUBSTANTIVE_CORRESPONDENCE_KEYWORDS = (
            "demand", "notice", "order", "petition", "motion", "reply",
            "complaint", "affidavit", "memorandum", "subpoena", "decision",
            "judgment", "manifestation", "rejoinder", "verification",
        )

        def is_substantive(ev):
            kind = ev.get("event_kind_canonical") or ""
            if kind in SUBSTANTIVE_KINDS:
                return True
            if kind == "title_event":
                # Title issuance/cancellation events are substantive; bulk
                # certification requests are not.
                cls = (ev.get("doc_classification") or "").lower()
                if "cancellation" in cls or "issuance" in cls or "transfer" in cls:
                    return True
                return False
            if kind == "correspondence":
                # Only correspondence whose action/title indicates substantive content
                action_raw = (ev.get("doc_classification") or ev.get("event_kind") or "").lower()
                title_raw = (ev.get("doc_title") or "").lower()
                fname_raw = (ev.get("doc_smart_filename") or "").lower()
                blob = action_raw + " " + title_raw + " " + fname_raw
                return any(k in blob for k in SUBSTANTIVE_CORRESPONDENCE_KEYWORDS)
            # All transactions, tax docs, title annotations, intakes, uncategorized: skip
            return False

        def extract_event_summary(ev):
            """Pull the cleanest readable summary from analyst_memo, fall back to
            what_summary, NEVER print raw OCR (the 635-page bug)."""
            memo = ev.get("doc_analyst_memo")
            if isinstance(memo, dict):
                # Prefer headline (one-liner) over summary (paragraph)
                if memo.get("headline"):
                    return memo["headline"][:280]
                if memo.get("summary"):
                    return memo["summary"][:380]
            # Calendar events have a description
            if ev.get("cal_description"):
                return ev["cal_description"][:280]
            # Gmail: use the subject (the body is usually OCR noise too)
            if ev.get("gmail_subject"):
                return f"[Email] {ev['gmail_subject'][:240]}"
            # Title transfer events have structured fields
            if ev.get("tt_instrument_type"):
                return (f"{ev['tt_instrument_type']}: "
                        f"{ev.get('tt_parent_title','?')}→{ev.get('tt_derivative_title','?')} "
                        f"({ev.get('tt_transferor','?')}→{ev.get('tt_transferee_name','?')})")
            # Last resort: the system-generated what_summary
            if ev.get("what_summary"):
                ws = ev["what_summary"].strip()
                if not ws.startswith("doc — "):  # filter out the no-context placeholder
                    return ws[:280]
            return "[no substantive summary available — see source doc]"

        substantive_events = [e for e in year_events if is_substantive(e)]
        skipped = len(year_events) - len(substantive_events)
        if skipped:
            out.append(f"_({skipped} routine event(s) suppressed — transactions, tax filings, "
                       f"bulk title certifications. Full list available in cross-reference index by matter.)_")
            out.append("")
        for e in substantive_events:
            d = e["primary_date"].isoformat()
            mcodes = e.get("matter_codes") or []
            tags = [shorten_matter_tag(mc) for mc in mcodes[:2]] if mcodes else ["GENERAL"]
            tag_str = "|".join(tags)
            action = translate_action(e)
            summary = extract_event_summary(e)
            prov = e.get("citation_ref") or f"{e['source_table']}#{e['source_id']}"
            # Compact single-bullet format — one line per event in normal cases
            out.append(f"* **{d}** · [{tag_str}] · **{action}** — {md_escape(summary)} _[{prov}]_")
        out.append("")

    if undated:
        out.append("### (Undated)")
        out.append("")
        for e in undated[:50]:
            kind = e.get("event_kind_canonical") or e.get("event_kind")
            out.append(f"* **— | {kind}** — {md_escape((e['what_summary'] or '')[:140])} "
                       f"_({e['citation_ref'] or e['source_table']+'#'+e['source_id']})_")
        if len(undated) > 50:
            out.append(f"  _… and {len(undated)-50} more undated events suppressed._")
        out.append("")

    # ── 4. Missing / Anomalous Gaps ──
    out.append("# 4. MISSING / ANOMALOUS GAPS")
    out.append("")
    if not gaps:
        out.append("_No anomalies detected._")
    else:
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        for g in sorted(gaps, key=lambda x: sev_order.get(x["severity"], 9)):
            sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(g["severity"], "⚪")
            out.append(f"- {sev_emoji} **[{g['severity'].upper()}] {g['kind']}** — {md_escape(g['detail'])}")
    out.append("")

    # ── 5. Cross-Reference Index (Appendix) ──
    index = build_cross_reference_index(dated)
    out.append(render_cross_reference_index(index))

    out.append("---")
    out.append(f"_Generated by generate_case_bible.py (deploy_157 — Bible v2 with deep "
               f"data enrichment, Haiku per-year narrative synthesis, and cross-reference "
               f"index) from client_history JOINED to documents/transactions/gmail/calendar/"
               f"title_transfers._")
    return "\n".join(out)


def render_html_from_md(md):
    """Minimal Markdown → HTML conversion for weasyprint (no external dep)."""
    import re, html as _html
    lines = md.splitlines()
    out = ['<!DOCTYPE html><html><head><meta charset="utf-8">',
           '<style>',
           'body{font-family:Helvetica,Arial,sans-serif;font-size:10pt;line-height:1.35;max-width:800px;margin:auto;color:#222;}',
           'h1{border-bottom:3px solid #222;padding-bottom:4px;margin-top:24px;}',
           'h2{color:#333;border-bottom:1px solid #888;padding-bottom:2px;margin-top:18px;}',
           'h3{color:#555;margin-top:14px;}',
           'ul{padding-left:20px;}li{margin:2px 0;}',
           'code{background:#f3f3f3;padding:1px 4px;border-radius:3px;font-size:9pt;}',
           'em{color:#666;}',
           'hr{border:none;border-top:1px solid #ccc;margin:18px 0;}',
           '@page{size:A4;margin:18mm 14mm;}',
           '</style></head><body>']
    in_list = False
    for line in lines:
        if line.startswith("# "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h1>{_html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h2>{_html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h3>{_html.escape(line[4:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list: out.append("<ul>"); in_list = True
            inner = line[2:]
            # Render **bold** and _italic_
            inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', inner)
            inner = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', inner)
            inner = re.sub(r'`([^`]+)`', r'<code>\1</code>', inner)
            out.append(f"<li>{inner}</li>")
        elif line.startswith("  -"):
            # Sub-bullet within a list item
            if in_list:
                inner = line[4:]
                inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', inner)
                inner = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', inner)
                inner = re.sub(r'`([^`]+)`', r'<code>\1</code>', inner)
                # Render as nested list (close prior li, open new ul)
                # Simpler: render as <div> indented
                out.append(f'<div style="margin-left:18px;font-size:9pt;">{inner}</div>')
            else:
                out.append(f"<p>{_html.escape(line.strip())}</p>")
        elif line.strip() == "---":
            if in_list: out.append("</ul>"); in_list = False
            out.append("<hr>")
        elif not line.strip():
            if in_list: out.append("</ul>"); in_list = False
        else:
            if in_list: out.append("</ul>"); in_list = False
            inner = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            inner = re.sub(r'(?<!_)_([^_]+)_(?!_)', r'<em>\1</em>', inner)
            out.append(f"<p>{inner}</p>")
    if in_list: out.append("</ul>")
    out.append("</body></html>")
    return "\n".join(out)


def render_pdf(md, pdf_path):
    import weasyprint
    html = render_html_from_md(md)
    weasyprint.HTML(string=html, base_url="/root/landtek").write_pdf(pdf_path)


# ── Delivery ────────────────────────────────────────────────────────────
def upload_to_drive(pdf_path, client_code):
    folder_id = DRIVE_OUTPUT_FOLDER.get(client_code)
    if not folder_id:
        return None, f"no Drive folder mapped for client_code={client_code}"
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH, scopes=['https://www.googleapis.com/auth/drive.file'])
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {'name': os.path.basename(pdf_path), 'parents': [folder_id]}
    media = MediaFileUpload(pdf_path, mimetype='application/pdf')
    f = service.files().create(body=file_metadata, media_body=media,
                                fields='id,webViewLink').execute()
    return f, None


def tg_send_document(pdf_path, caption=""):
    import requests
    tok = None
    for l in open("/root/landtek/.env"):
        if l.startswith("TELEGRAM_BOT_TOKEN="):
            tok = l.split("=", 1)[1].strip(); break
    if not tok:
        return False, "no TELEGRAM_BOT_TOKEN"
    with open(pdf_path, "rb") as f:
        files = {"document": (os.path.basename(pdf_path), f, "application/pdf")}
        data = {"chat_id": JONATHAN_TG_ID, "caption": caption[:1024], "parse_mode": "HTML"}
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument",
                          data=data, files=files, timeout=60)
        return r.status_code == 200, r.text[:300]


# ── Main pipeline ───────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter")
    ap.add_argument("--case")
    ap.add_argument("--md-only", action="store_true", help="produce Markdown only (no PDF, no delivery)")
    ap.add_argument("--no-deliver", action="store_true", help="MD + PDF, skip Drive + Telegram")
    args = ap.parse_args()
    if not (args.matter or args.case):
        sys.exit("Must specify --matter or --case")

    conn, cur = db_connect()
    omnibus_mode = bool(args.case and not args.matter)
    matter = resolve_matter(cur, args.matter, args.case)
    if not matter:
        sys.exit(f"No matter found for matter={args.matter!r} case={args.case!r}")
    case_file = matter["case_file"]
    matter_code = matter.get("matter_code") if not omnibus_mode else None
    client_code = matter["client_code"]
    print(f"  [1/6] resolved {'OMNIBUS' if omnibus_mode else 'single-matter'} mode: "
          f"case_file={case_file} / client={client_code}"
          + (f" / matter={matter_code}" if matter_code else ""))

    # In omnibus mode, fetch ALL matters under the case_file (for header listing)
    all_matters = None
    if omnibus_mode:
        cur.execute("""
            SELECT matter_code, title, current_stage, stage_updated_at
              FROM matters WHERE case_file = %s ORDER BY matter_code
        """, (case_file,))
        all_matters = cur.fetchall()
        # In omnibus mode pass matter_code=None to fetch_events so it pulls everything via case_file
        events = fetch_events(cur, None, case_file)
    else:
        events = fetch_events(cur, matter_code, case_file)
    print(f"  [2/6] fetched {len(events)} events")

    deadlines = fetch_critical_deadlines(cur, case_file)
    coverage = fetch_coverage_warnings(cur, client_code)
    if omnibus_mode:
        projected = project_forward_omnibus(cur, case_file)
    else:
        projected = project_forward(matter)
    print(f"  [3/6] projected {len(projected)} forward events"
          + (f" across {len(all_matters)} matters" if omnibus_mode else f" from stage='{matter.get('current_stage')}'"))
    gaps = detect_gaps(events, deadlines, case_file=matter.get("case_file") or "MWK-001")
    print(f"  [4/6] detected {len(gaps)} gap(s)/anomaly(ies)")

    md = render_markdown(matter, events, deadlines, coverage, projected, gaps,
                          omnibus_mode=omnibus_mode, all_matters=all_matters)
    out_dir = Path("/root/landtek/drafts")
    out_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()
    if omnibus_mode:
        slug = f"OMNIBUS_{case_file}"
    else:
        slug = (matter_code or case_file).replace("/", "_")
    md_path = out_dir / f"bible_{slug}_{today}.md"
    md_path.write_text(md)
    print(f"  [5/6] wrote Markdown to {md_path} ({len(md):,} chars, {md.count(chr(10))+1} lines)")

    # Apply deterministic narrative post-processor (deploy_163-164).
    # The Haiku narrator is faithful to source-doc OCR (which contains
    # 'MTC Mercedes' draft captions, etc.), so prompt hardening alone isn't
    # enough. Regex corrections fix venue/spelling/editorializing/header artifacts.
    try:
        from narrative_postprocess import patch_narrative_blocks
        new_md, applied = patch_narrative_blocks(md_path.read_text())
        if applied:
            md_path.write_text(new_md)
            print(f"  [5/6.5] post-processor applied {sum(a['n'] for a in applied)} narrative correction(s)")
    except Exception as e:
        print(f"  ⚠ post-processor skipped: {e}")

    if args.md_only:
        print("\n  MD-only mode — skipping PDF + delivery. Verify layout, then re-run without --md-only.")
        return

    pdf_path = out_dir / f"bible_{slug}_{today}.pdf"
    render_pdf(md, str(pdf_path))
    print(f"  [6/6] wrote PDF to {pdf_path} ({pdf_path.stat().st_size/1024:.0f} KB)")

    if args.no_deliver:
        print("\n  --no-deliver — skipping Drive + Telegram.")
        return

    try:
        drive_result, err = upload_to_drive(str(pdf_path), client_code)
        if drive_result:
            print(f"  Drive: uploaded as file_id={drive_result.get('id')} → {drive_result.get('webViewLink','')}")
        else:
            print(f"  Drive: SKIPPED — {err}")
    except Exception as e:
        # Service accounts lack storage quota on user-owned Drive folders. Don't block delivery.
        msg = str(e)[:200]
        print(f"  Drive: ⚠ FAILED (continuing with Telegram) — {msg}")
        if "storageQuotaExceeded" in msg:
            print("    NOTE: SA needs a Shared Drive (or OAuth-delegated upload) to write here.")

    cap = (f"📖 <b>{slug} — Master Case Bible</b>\n"
           f"<i>Generated {today} · {len(events)} events · {len(gaps)} gaps flagged</i>")
    ok, info = tg_send_document(str(pdf_path), caption=cap)
    print(f"  Telegram: {'✓ delivered' if ok else '✗ failed: ' + info[:120]}")


if __name__ == "__main__":
    main()
