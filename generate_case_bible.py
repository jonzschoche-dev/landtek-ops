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
    """Pull events: prefer matter-attributed, fall back to case_file."""
    if matter_code:
        cur.execute("""
            SELECT id, COALESCE(event_date, date_executed, date_filed, date_received) AS primary_date,
                   event_date, event_datetime, event_kind, event_kind_canonical,
                   date_executed, date_filed, date_received,
                   who_from, who_to, what_summary, citation_ref,
                   provenance, source_table, source_id,
                   matter_codes, title_refs, party_refs
              FROM client_history
             WHERE %s = ANY(matter_codes) OR case_file = %s
             ORDER BY primary_date NULLS LAST, event_datetime NULLS LAST, id
        """, (matter_code, case_file))
    else:
        cur.execute("""
            SELECT id, COALESCE(event_date, date_executed, date_filed, date_received) AS primary_date,
                   event_date, event_datetime, event_kind, event_kind_canonical,
                   date_executed, date_filed, date_received,
                   who_from, who_to, what_summary, citation_ref,
                   provenance, source_table, source_id,
                   matter_codes, title_refs, party_refs
              FROM client_history
             WHERE case_file = %s
             ORDER BY primary_date NULLS LAST, event_datetime NULLS LAST, id
        """, (case_file,))
    return cur.fetchall()


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


def detect_gaps(events, deadlines):
    """Anomaly detection over the timeline. Returns list of findings."""
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
        findings.append({
            "kind": "orphan_legal_acts",
            "severity": "medium",
            "detail": (f"{len(orphans)} legal-act events have no linked TCT or party "
                       "(can't be queried by 'what touched T-4497' or 'what did Cesar do')."),
        })

    # 5. Critical missing primary instruments (known gaps from project memory)
    known_gaps = [
        ("2005 Revocation of SPA (Cesar dela Fuente)",
         "Currently testimonial via Judicial Affidavit doc#441. Primary notarized instrument missing — single biggest evidence gap on the void-SPA theory."),
        ("Mary Worrick Keesey death certificate (PSA-issued, ~1988)",
         "Testimonial only via project memory; PSA-certified primary document not in corpus."),
        ("Cesar dela Fuente death certificate (2017)",
         "Referenced in LandBank's CV-6839 filing (doc#364); primary PSA certificate not yet ingested."),
        ("The 2016 Deed of Sale (Cesar → buyer that led to T-52540 cancellation)",
         "The void deed at issue in CV 26-360. Not directly in corpus per current scan."),
    ]
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
    "Paracale-001": "Paracale Estate (Paracale-001)",
    "Owner":        "Owner File (Owner)",
}


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

    for year, year_events in groupby(dated, key=lambda e: e["primary_date"].year):
        out.append(f"### {year}")
        out.append("")
        for e in year_events:
            kind = e.get("event_kind_canonical") or e.get("event_kind") or "event"
            d = e["primary_date"].isoformat()
            # Build matter-tag prefix from matter_codes[] (omnibus-critical)
            mcodes = e.get("matter_codes") or []
            if mcodes:
                tags = [shorten_matter_tag(mc) for mc in mcodes[:3]]  # cap at 3
                tag_prefix = "[" + "|".join(tags) + "]"
            else:
                tag_prefix = "[GENERAL]"
            out.append(f"* **{d} | {kind}**")
            summary = (e["what_summary"] or "").strip()
            out.append(f"  - **Description:** {tag_prefix} {md_escape(summary)}")
            parties = []
            if e.get("title_refs"):
                parties.extend(e["title_refs"])
            if e.get("who_from") and e["who_from"] != "—":
                parties.append(f"from: {e['who_from']}")
            if e.get("who_to") and e["who_to"] != "—":
                parties.append(f"to: {e['who_to']}")
            if e.get("party_refs"):
                parties.append(f"party_ids: {','.join(str(p) for p in e['party_refs'])}")
            out.append(f"  - **Parties/Titles:** {md_escape('; '.join(parties)) if parties else '—'}")
            prov = e.get("citation_ref") or f"{e['source_table']}#{e['source_id']}"
            prov_level = e.get("provenance") or "?"
            out.append(f"  - **Provenance:** {md_escape(prov)} _[{prov_level}]_")
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

    out.append("---")
    out.append(f"_Generated by generate_case_bible.py (deploy_156) from client_history "
               f"with multi-attribution + canonical event vocabulary._")
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
    gaps = detect_gaps(events, deadlines)
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
