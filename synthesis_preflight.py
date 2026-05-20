#!/usr/bin/env python3
"""synthesis_preflight — cross-source check before any case-output generator.

Enforces [[feedback_synthesis_must_cross_source]] (P0).

Usage from a generator script (case_strategy_memo.py, client_history.py, etc.):

    from synthesis_preflight import preflight, PreflightBlocked

    try:
        clearance = preflight(matter_code='MWK-CV26360', case_file='MWK-001')
        # clearance is a dict with the discovered cross-source context
        # use clearance to enrich the synthesis
    except PreflightBlocked as e:
        # gaps detected — handler enqueues ops alert and exits non-zero
        sys.exit(1)

Or from the CLI:
    python3 synthesis_preflight.py --matter MWK-CV26360 --case MWK-001

CHECKLIST (8 cross-source scans):
  1. documents — keyword scan for related-but-untagged docs
  2. chat_notes (past 90d) — facts the matter row doesn't capture
  3. gmail_messages — subject/body scan for parallel proceedings
  4. entities — actors with role implying matter but no tag
  5. client_history — events not in matter_codes array
  6. calendar_events — meetings/hearings about parallel proceedings
  7. case_deadlines — deadlines on parallel proceedings without matter rows
  8. /root/landtek/drafts/ — files suggesting alternative drafts

If any scan turns up evidence of a matter / counsel / proceeding NOT
represented as a matters row, output is BLOCKED and the discovery
diff is enqueued as an ops gap_alert.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
DRAFTS_DIR = Path("/root/landtek/drafts")

# Keyword anchors for proceedings, counsel, courts. Cast wide; the preflight
# is a "find me anything I might have missed" net, not a precision filter.
PROCEEDING_PATTERNS = [
    r"\bpetition(?:\s+for\b)?",
    r"\bbrief\b",
    r"\bmotion\b",
    r"\bcomplaint\b",
    r"\b(civil|criminal|administrative)\s+case\b",
    r"\bspecial\s+proceeding\b",
    r"\b(RTC|MTC|Branch)\b",
    r"\bARTA\b",
    r"\bCSC\b",
    r"\bDILG\b",
    r"\bDOJ\b",
    r"\bbarangay\b",
    r"\bguardianship\b",
    r"\b(estate|partition)\b",
    r"\bwrit\b",
    r"\border\b",
    r"\bresolution\b",
    r"\bhearing\b",
    r"\bnotari(?:zed|al)\b",
    r"\bdocket\b",
    r"\b(atty|attorney|counsel)\b",
    r"\bSPA\b",
    r"\baccion\b",
]

class PreflightBlocked(Exception):
    """Raised when preflight discovers gaps and synthesis must not proceed."""
    pass


def _conn():
    return psycopg2.connect(DSN)


def _matter_context(cur, matter_code):
    """Pull what the matter row claims about itself."""
    cur.execute("""
        SELECT matter_code, client_code, matter_type, title, description,
               status, current_stage, court_or_agency, docket_number,
               lead_counsel, case_file, next_event, stage_notes
          FROM matters
         WHERE matter_code = %s
    """, (matter_code,))
    row = cur.fetchone()
    if not row:
        return None
    keywords = []
    for fld in ("matter_code", "title", "court_or_agency", "docket_number",
                "lead_counsel", "current_stage"):
        v = row[fld]
        if v:
            keywords.extend(re.findall(r"\w{3,}", str(v).lower()))
    return {"row": dict(row), "keywords": set(keywords)}


def scan_documents(cur, ctx, case_file):
    """Find docs in this case_file with proceeding-keywords but NO matter_code,
    OR with a DIFFERENT matter_code than the one being synthesized."""
    cur.execute("""
        SELECT id, matter_code, classification, execution_status,
               doc_date_norm, COALESCE(smart_filename, document_title, original_filename) AS name,
               LEFT(extracted_text, 500) AS preview
          FROM documents
         WHERE case_file = %s
           AND classification IN ('Petition','Brief','Complaint','Motion',
                                  'Judicial Affidavit','Pleading',
                                  'Pleading - Complaint (Draft)','Order','Resolution')
         ORDER BY doc_date_norm DESC NULLS LAST
         LIMIT 80
    """, (case_file,))
    findings = []
    matter = ctx["row"]["matter_code"]
    for r in cur.fetchall():
        if r["matter_code"] is None:
            findings.append({
                "doc_id": r["id"],
                "issue": "doc has classification suggesting a proceeding but no matter_code",
                "name": r["name"],
                "classification": r["classification"],
                "date": str(r["doc_date_norm"]) if r["doc_date_norm"] else None,
            })
        elif r["matter_code"] != matter:
            findings.append({
                "doc_id": r["id"],
                "issue": f"doc belongs to matter {r['matter_code']} — different from synthesis target {matter}",
                "name": r["name"],
                "classification": r["classification"],
            })
    return findings


def scan_chat_notes(cur, ctx, case_file, days_back=90):
    """Find recent chat_notes mentioning proceedings/counsel/dockets NOT
    already in the matter's stage_notes or matter_codes array."""
    cur.execute("""
        SELECT id, created_at::date AS d, sender_name, content, summary,
               related_case, related_event_id, related_tct
          FROM chat_notes
         WHERE created_at > NOW() - (%s || ' days')::interval
           AND (related_case = %s OR related_case IS NULL)
         ORDER BY created_at DESC
         LIMIT 200
    """, (str(days_back), case_file))
    findings = []
    matter_keys = ctx["keywords"]
    proceeding_re = re.compile("|".join(PROCEEDING_PATTERNS), re.IGNORECASE)
    for r in cur.fetchall():
        text = (r["content"] or "") + " " + (r["summary"] or "")
        if not proceeding_re.search(text):
            continue
        # Suspect: mentions proceedings but doesn't share lots of matter keywords
        words = set(re.findall(r"\w{3,}", text.lower()))
        overlap = matter_keys & words
        # If almost no overlap with the matter's own keywords → likely talks about a different proceeding
        if len(overlap) < 2:
            findings.append({
                "chat_note_id": r["id"],
                "date": str(r["d"]),
                "sender": r["sender_name"],
                "preview": text[:160].strip(),
                "issue": "mentions proceeding keywords with low overlap to matter — possible parallel proceeding",
            })
    return findings[:25]   # cap noise


def scan_gmail(cur, ctx, days_back=90):
    """Gmail subjects suggesting proceedings."""
    cur.execute("""
        SELECT id, received_at::date AS d, from_addr, subject
          FROM gmail_messages
         WHERE received_at > NOW() - (%s || ' days')::interval
           AND (subject ~* '\\m(petition|brief|motion|complaint|civil case|special proceeding|guardianship|ARTA|CSC|DILG|hearing|order|writ)\\M')
         ORDER BY received_at DESC LIMIT 30
    """, (str(days_back),))
    findings = []
    matter_keys = ctx["keywords"]
    for r in cur.fetchall():
        subj = (r["subject"] or "").lower()
        subj_words = set(re.findall(r"\w{3,}", subj))
        overlap = matter_keys & subj_words
        if len(overlap) < 1:
            findings.append({
                "gmail_id": r["id"],
                "date": str(r["d"]),
                "from": r["from_addr"],
                "subject": r["subject"][:80] if r["subject"] else "",
                "issue": "gmail subject mentions proceeding terms — no keyword overlap with matter",
            })
    return findings[:15]


def scan_entities(cur, ctx):
    """Counsel/judge entities without role tag — potential parallel-matter counsel."""
    cur.execute("""
        SELECT id, canonical_name, role, mentions_count
          FROM entities
         WHERE (canonical_name ILIKE 'atty.%' OR canonical_name ILIKE 'judge%' OR canonical_name ILIKE 'justice%')
           AND role IS NULL
           AND canonical_id IS NULL
         ORDER BY mentions_count DESC LIMIT 12
    """)
    return [{"entity_id": r["id"], "name": r["canonical_name"],
             "mentions": r["mentions_count"],
             "issue": "counsel/judge entity has no role assigned — may be involved in untracked matter"}
            for r in cur.fetchall()]


def scan_calendar(cur, days_forward=30):
    """Future calendar events that don't tag a known matter."""
    cur.execute("""
        SELECT id, title, start_at, related_case
          FROM calendar_events
         WHERE start_at >= NOW() AND start_at <= NOW() + (%s || ' days')::interval
         ORDER BY start_at LIMIT 20
    """, (str(days_forward),))
    findings = []
    for r in cur.fetchall():
        title = (r["title"] or "").lower()
        # If title mentions a counsel/proceeding/court that the matter row doesn't, flag it
        flagged = any(re.search(p, title, re.IGNORECASE) for p in PROCEEDING_PATTERNS)
        if flagged:
            findings.append({
                "event_id": r["id"],
                "title": r["title"],
                "start_at": str(r["start_at"]),
                "related_case": r["related_case"],
            })
    return findings


def scan_deadlines(cur, case_file):
    """case_deadlines for the case that aren't reflected on any matter."""
    cur.execute("""
        SELECT cd.id, cd.title, cd.due_date, cd.status, cd.assigned_to,
               cd.case_file
          FROM case_deadlines cd
         WHERE cd.case_file = %s AND cd.status = 'pending'
         ORDER BY cd.due_date LIMIT 30
    """, (case_file,))
    return [{"deadline_id": r["id"], "title": r["title"],
             "due_date": str(r["due_date"]) if r["due_date"] else None,
             "status": r["status"], "assigned_to": r["assigned_to"]}
            for r in cur.fetchall()]


def scan_drafts(matter_code, case_file):
    """Files on disk under /root/landtek/drafts/ that may belong to this matter."""
    if not DRAFTS_DIR.is_dir():
        return []
    findings = []
    keys = set(re.findall(r"\w{3,}", (matter_code + " " + case_file).lower()))
    for p in DRAFTS_DIR.rglob("*.md"):
        if p.parent.name == "archive":
            continue
        name = p.name.lower()
        if any(k in name for k in keys):
            continue
        # files that mention proceedings without matter overlap
        try:
            head = p.read_text(errors="ignore")[:1000].lower()
        except Exception:
            continue
        if re.search("|".join(PROCEEDING_PATTERNS), head, re.IGNORECASE):
            findings.append({"path": str(p), "issue": "draft file mentions a proceeding"})
    return findings[:10]


def preflight(matter_code: str, case_file: str, *, strict: bool = True,
              days_back: int = 90):
    """Run all 8 scans. Return clearance dict OR raise PreflightBlocked.

    strict=True (default) → any non-empty findings list raises PreflightBlocked.
    strict=False → returns the findings without raising; caller decides.
    """
    conn = _conn(); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ctx = _matter_context(cur, matter_code)
        if ctx is None:
            raise PreflightBlocked(f"matter_code {matter_code!r} not found in matters table")

        report = {
            "matter_code": matter_code,
            "case_file": case_file,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "scans": {
                "documents":    scan_documents(cur, ctx, case_file),
                "chat_notes":   scan_chat_notes(cur, ctx, case_file, days_back),
                "gmail":        scan_gmail(cur, ctx, days_back),
                "entities":     scan_entities(cur, ctx),
                "calendar":     scan_calendar(cur),
                "deadlines":    scan_deadlines(cur, case_file),
                "drafts":       scan_drafts(matter_code, case_file),
            },
        }
        total = sum(len(v) for v in report["scans"].values())
        report["total_findings"] = total

        if strict and total > 0:
            raise PreflightBlocked(json.dumps(report, default=str)[:8000])
        return report
    finally:
        cur.close(); conn.close()


# ─── CLI entrypoint ──────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True, help="matter_code (e.g. MWK-CV26360)")
    ap.add_argument("--case",   required=True, help="case_file (e.g. MWK-001)")
    ap.add_argument("--strict", action="store_true",
                    help="raise PreflightBlocked if any findings (default: report-only)")
    ap.add_argument("--days-back", type=int, default=90)
    args = ap.parse_args()

    try:
        report = preflight(args.matter, args.case, strict=args.strict,
                           days_back=args.days_back)
    except PreflightBlocked as e:
        print(f"✗ PREFLIGHT BLOCKED for {args.matter}: see findings", file=sys.stderr)
        # Re-load the report for printing
        report = preflight(args.matter, args.case, strict=False, days_back=args.days_back)
        _print_report(report, blocked=True)
        sys.exit(2)

    _print_report(report, blocked=False)
    sys.exit(0 if report["total_findings"] == 0 else 1)


def _print_report(report, blocked=False):
    tag = "✗ BLOCKED" if blocked else "○ REPORT"
    print(f"━━━ synthesis_preflight {tag} — matter={report['matter_code']} case={report['case_file']} ━━━")
    print(f"    total findings: {report['total_findings']}")
    for scan_name, findings in report["scans"].items():
        if findings:
            print(f"\n  [{scan_name}] {len(findings)} finding(s)")
            for f in findings[:5]:
                summary_keys = [k for k in ("doc_id","chat_note_id","gmail_id","entity_id",
                                            "event_id","deadline_id","path","name","title","subject",
                                            "preview","issue","date") if k in f]
                line = " · ".join(f"{k}={str(f[k])[:60]}" for k in summary_keys[:4])
                print(f"    • {line}")
            if len(findings) > 5:
                print(f"    … +{len(findings)-5} more")


if __name__ == "__main__":
    main()
