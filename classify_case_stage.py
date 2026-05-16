#!/usr/bin/env python3
"""Case-stage classifier (deploy_111-B, v2).

For each matter:
  1. Find all pleadings/orders/filings that reference the matter's docket
  2. Tag each doc with the ONE stage it most strongly represents
  3. Pick the LATEST stage-indicating doc → that's the current stage
  4. Record transition into case_stage_transitions

A 'stage indicator' is a doc whose nature inherently signals a procedural moment:
  - Complaint → complaint_filed
  - Answer with Counterclaim → answer_filed
  - Notice of Pre-trial Conference → pretrial_pending
  - Pre-trial Order → pretrial_order
  - Motion / Reply → motion practice (still answer_filed unless other signal)
  - Plaintiff/Defendant's Memorandum → memoranda
  - Decision → decision_rendered
  - Notice of Appeal → appeal_period
  - Order of Dismissal → dismissed
"""
import argparse
import json
import re
from datetime import date, datetime, timedelta
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# Order matters — later stages override earlier ones in same case (when tied).
STAGE_ORDER = [
    "pre_filing", "complaint_filed", "summons_served", "answer_period",
    "answer_filed", "pretrial_pending", "pretrial", "pretrial_order",
    "trial_plaintiff_evidence", "trial_defendant_evidence", "formal_offer",
    "memoranda", "decision_pending", "decision_rendered", "appeal_period",
    "appeal_pending", "final", "dismissed", "settled", "withdrawn",
]
STAGE_RANK = {s: i for i, s in enumerate(STAGE_ORDER)}


def stage_for_doc(d):
    """Return (stage, confidence, reason) for a single doc, or None.
    Uses smart_filename FIRST (more reliable), then extracted_text patterns.
    """
    fn = (d.get("smart_filename") or "").lower()
    txt = (d.get("extracted_text") or "")[:15000]
    txt_lower = txt.lower()
    cls = (d.get("classification") or "").lower()

    # Highest-priority filename markers
    if re.search(r"notice\s+of\s+(?:pre[\-\s]?trial|pretrial)\s+conf", fn):
        return ("pretrial_pending", 0.97, "filename: Notice of Pre-trial Conference")
    if re.search(r"pre[\-\s]?trial\s+order", fn):
        return ("pretrial_order", 0.96, "filename: Pre-trial Order")
    if re.search(r"order\s+of\s+dismissal|dismissed", fn):
        return ("dismissed", 0.95, "filename: Order of Dismissal")
    if re.search(r"notice\s+of\s+appeal", fn):
        return ("appeal_period", 0.95, "filename: Notice of Appeal")
    if re.search(r"decision", fn) and "draft" not in fn:
        return ("decision_rendered", 0.92, "filename: Decision")
    if re.search(r"answer\s+with.*?(?:counterclaim|counter[\-\s]?claim|affirmative)", fn):
        return ("answer_filed", 0.95, "filename: Answer with Counterclaim")
    if re.search(r"plaintiff'?s?\s+memorandum|defendant'?s?\s+memorandum|"
                 r"position\s+paper(?:\s+for|$)", fn):
        return ("memoranda", 0.94, "filename: party memorandum/position paper")
    if re.search(r"formal\s+offer\s+of\s+(?:plaintiff|defendant|evidence)", fn):
        return ("formal_offer", 0.94, "filename: Formal Offer of Evidence")
    if re.search(r"motion\s+to\s+(?:render\s+)?summary\s+judgment", fn) and "draft" not in fn:
        return ("answer_filed", 0.80, "filename: Motion for Summary Judgment (post-answer practice)")
    if re.search(r"motion\s+to\s+dismiss", fn):
        return ("answer_filed", 0.80, "filename: Motion to Dismiss")
    if re.search(r"reply.*?(?:civil\s+case|cv[\-\s]?\d|reply\s+brief)", fn) and "draft" not in fn:
        return ("answer_filed", 0.70, "filename: Reply pleading (post-answer)")
    if re.search(r"(?:verified\s+)?complaint(?:\s+for|$)", fn) and "exhibit" not in fn:
        return ("complaint_filed", 0.92, "filename: Complaint")
    if re.search(r"comment.*?opposition|opposition.*?comment", fn):
        return ("answer_filed", 0.70, "filename: Comment/Opposition (motion practice)")
    if re.search(r"compliance", fn) and "civil case" in fn:
        return ("answer_filed", 0.60, "filename: Compliance filing")
    if re.search(r"judicial\s+affidavit", fn):
        return ("answer_filed", 0.55, "filename: Judicial Affidavit (pre-trial prep)")

    # Text-based markers (lower precedence than filename)
    if re.search(r"NOTICE\s+OF\s+PRE[\-\s]?TRIAL\s+CONFERENCE", txt, re.IGNORECASE):
        return ("pretrial_pending", 0.92, "text: 'NOTICE OF PRE-TRIAL CONFERENCE' header")
    if re.search(r"PRE[\-\s]?TRIAL\s+ORDER\b", txt):
        return ("pretrial_order", 0.90, "text: PRE-TRIAL ORDER header")
    if re.search(r"\bWHEREFORE.{0,200}(?:judgment|decision)\s+is\s+hereby\s+rendered", txt, re.IGNORECASE):
        return ("decision_rendered", 0.93, "text: dispositive judgment language")
    if re.search(r"ANSWER\s+WITH\s+(?:SPECIAL\s+AND\s+AFFIRMATIVE\s+DEFENSES\s+AND\s+)?"
                 r"COMPULSORY\s+COUNTER[\-\s]?CLAIM", txt, re.IGNORECASE):
        return ("answer_filed", 0.94, "text: ANSWER WITH COUNTERCLAIM header")
    if re.search(r"^\s*COMPLAINT\s*$|VERIFIED\s+COMPLAINT", txt[:5000], re.IGNORECASE | re.MULTILINE):
        return ("complaint_filed", 0.85, "text: COMPLAINT header")

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", default=None)
    ap.add_argument("--case-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.matter:
        cur.execute("SELECT * FROM matters WHERE matter_code = %s", (args.matter,))
    elif args.case_file:
        cur.execute("SELECT * FROM matters WHERE case_file = %s", (args.case_file,))
    else:
        cur.execute("SELECT * FROM matters WHERE status='active'")
    matters = cur.fetchall()

    for m in matters:
        case_file = m["case_file"]; matter_code = m["matter_code"]
        docket_no = (m.get("docket_number") or "").strip()
        if not case_file:
            print(f"  ⚠ {matter_code} has no case_file — skipping"); continue
        if m.get("matter_type") not in ("civil_case", "criminal_case", "administrative"):
            print(f"  ⊘ {matter_code} (type={m.get('matter_type')}) — not stage-tracked")
            continue
        print(f"\n  matter: {matter_code} (docket={docket_no or '—'})")

        # Build docket scopes
        variants = []
        if docket_no:
            variants.append(f"%{docket_no}%")
            if "-" in docket_no:
                tail = docket_no.split("-")[-1]
                variants += [f"%26-{tail}%", f"%2026-{tail}%", f"%{tail}%"]
        if variants:
            placeholders = " OR ".join(["extracted_text ILIKE %s"]*len(variants) +
                                       ["smart_filename ILIKE %s"]*len(variants))
            params = [case_file] + list(variants)*2
            cur.execute(f"""
                SELECT id, smart_filename, classification, execution_status,
                       LEFT(extracted_text, 20000) AS extracted_text, created_at
                  FROM documents
                 WHERE case_file=%s AND extracted_text IS NOT NULL AND ({placeholders})
                 ORDER BY id
            """, params)
        else:
            cur.execute("""
                SELECT id, smart_filename, classification, execution_status,
                       LEFT(extracted_text, 20000) AS extracted_text, created_at
                  FROM documents
                 WHERE case_file=%s AND extracted_text IS NOT NULL
                 ORDER BY id
            """, (case_file,))
        docs = cur.fetchall()
        print(f"    candidates: {len(docs)}")

        # Tag each doc with its stage
        tagged = []
        for d in docs:
            r = stage_for_doc(d)
            if r:
                stage, conf, reason = r
                tagged.append({"doc": d, "stage": stage, "conf": conf, "reason": reason})

        if not tagged:
            print(f"    no stage indicators found"); continue

        # Pick the LATEST high-confidence stage indicator
        tagged.sort(key=lambda t: (t["conf"], t["doc"]["id"]), reverse=True)
        # Among the top-K by confidence (≥0.9), pick the LATEST stage (by rank)
        top = [t for t in tagged if t["conf"] >= 0.85] or tagged[:5]
        # The most procedurally-advanced of the high-confidence indicators
        top.sort(key=lambda t: (STAGE_RANK.get(t["stage"], -1), t["doc"]["id"]), reverse=True)
        winner = top[0]
        target = winner["stage"]
        source_doc = winner["doc"]["id"]
        print(f"    → stage: {target}  (doc #{source_doc}, conf={winner['conf']:.2f}, {winner['reason']})")
        print(f"      (considered {len(tagged)} indicators; top-3:)")
        for t in top[:3]:
            print(f"        - {t['stage']:22} conf={t['conf']:.2f} doc#{t['doc']['id']} — {t['reason']}")

        next_event_map = {
            "complaint_filed":          ("Await summons issuance + service", None),
            "summons_served":           ("Defendants' Answer due (15+15)", 30),
            "answer_period":            ("Defendants' Answer", 15),
            "answer_filed":             ("Pretrial conference scheduling / motions ruling", 30),
            "pretrial_pending":         ("Pretrial conference — confirm date with court", 14),
            "pretrial":                 ("Pre-trial order issuance", 14),
            "pretrial_order":           ("Trial calendar / plaintiff's evidence-in-chief", None),
            "trial_plaintiff_evidence": ("Continue plaintiff's evidence", None),
            "trial_defendant_evidence": ("Defendant's evidence", None),
            "formal_offer":             ("Opposing memorandum on offer", 15),
            "memoranda":                ("Submit for decision", None),
            "decision_pending":         ("Decision issuance", None),
            "decision_rendered":        ("Appeal window (15 days)", 15),
            "appeal_period":            ("File Notice of Appeal", 15),
            "appeal_pending":           ("CA proceedings", None),
            "final":                    ("Execution", None),
        }
        next_event, days_out = next_event_map.get(target, ("Review next steps", None))
        next_deadline = (date.today() + timedelta(days=days_out)) if days_out else None

        if args.dry_run:
            print(f"    (dry-run) would set: next_event='{next_event}' next_deadline={next_deadline}")
            continue

        prev = m.get("current_stage")
        if prev != target:
            cur.execute("""
                INSERT INTO case_stage_transitions
                  (matter_code, case_file, from_stage, to_stage, transition_doc_id, notes, confidence, detected_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (matter_code, case_file, prev, target, source_doc,
                  winner["reason"], winner["conf"], "classifier_v2"))
            print(f"    + transition: {prev or '(initial)'} → {target}")

        cur.execute("""
            UPDATE matters
               SET current_stage=%s, next_event=%s, next_deadline=%s,
                   next_event_owner=COALESCE(next_event_owner,'jonathan'),
                   stage_updated_at=now(), stage_notes=%s
             WHERE matter_code=%s
        """, (target, next_event, next_deadline, winner["reason"], matter_code))
        print(f"    ✓ stage updated")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
