#!/usr/bin/env python3
"""Tag each document with its filing party (deploy 119).

For docs in active matters:
  - 'plaintiff' — filed by Patricia Zschoche / Jonathan / Atty. Barandon side
  - 'respondent' — filed by Balane / Pajarillo / Macale / defendants
  - 'court' — issued by RTC/MTC/CA/SC/judge
  - 'witness' — judicial affidavits by third parties
  - 'counsel' — attorney correspondence
  - 'agency' — gov office (RD, ARTA, DILG, assessor)
  - 'third_party' — none of above

Regex-driven (deterministic). For ambiguous, falls back to "third_party" with
low confidence — manual review surfaced via /case_status.
"""
import argparse, re, sys
from datetime import date
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

PLAINTIFF_TOKENS = [
    # filename + body markers
    r"\bPatricia\s+Keesey\s+Zschoche\b",
    r"\bPatricia\s+Zschoche\b",
    r"Jonathan\s+(?:Paul\s+)?Zschoche",
    r"Barandon\s+Law\s+Offices?",
    r"\bAtty\.\s+(?:Bonifacio|Ronald\s+A\.)\s+(?:Barandon|Ramos)",
    r"PLAINTIFF\s*['']?S?\s+(?:REPLY|MOTION|MEMORANDUM|BRIEF|JUDICIAL\s+AFFIDAVIT|COMPLAINT)",
    r"COMES\s+NOW,?\s+(?:the\s+)?PLAINTIFF",
    r"complainant\s+through\s+(?:the\s+)?undersigned\s+counsel",
    r"Heirs?\s+of\s+Mary\s+Worrick\s+Keesey.{0,80}Plaintiff",
]
PLAINTIFF_FILENAME_TOKENS = [
    r"[Vv]erification\s*-\s*Reply",
    r"\bReply\b",
    r"Motion\s+to\s+Render\s+Summary\s+Judgment",
    r"Plaintiff",
    r"[Jj]onathan",
    r"Affidavit\s*-\s*Summary\s+Judgment",
    r"Judicial\s+Affidavit\s+of\s+Jonathan",
]
RESPONDENT_TOKENS = [
    r"\bGloria\s+Balane\b",
    r"\bEfren\s+Balane\b",
    r"\bSpouses?\s+Balane\b",
    r"\bPrincess\s+(?:Balane\s+)?Torralba\b",
    r"\bEngr\.\s+Erwin\s+(?:H\.\s+)?Balane\b",
    r"DEFENDANT['']?S?\s+(?:ANSWER|COMMENT|OPPOSITION|MOTION)",
    r"defendants?\s+through\s+(?:the\s+)?undersigned\s+counsel",
    r"\bMayor\s+(?:Alexander\s+)?Pajarillo\b|Pajarillo,\s+Alexander",
    r"\bLoida\s+E\.?\s+Macale\b",
    r"Salvador\s+Osum\s+(?:Dela|De\s+la)\s+Fuente",  # son of Cesar, witness for defendants
    r"Atty\.\s+Ronald\s+A\.\s+Ramos",  # defendants' counsel
]
RESPONDENT_FILENAME_TOKENS = [
    r"Answer\s+with",
    r"Comment\s+Opposition",
    r"Comment/Opposition",
    r"Judicial\s+Affidavit\s+of\s+Salvador",
    r"Judicial\s+Affidavit\s+of\s+Princess",
    r"Judicial\s+Affidavit\s+of\s+(?:Engr\.\s+)?Erwin",
    r"Mayor\s+Alex",
    r"Pajarillo",
]
COURT_TOKENS = [
    r"REGIONAL\s+TRIAL\s+COURT|MUNICIPAL\s+TRIAL\s+COURT",
    r"NOTICE\s+OF\s+PRE-?TRIAL\s+CONFERENCE",
    r"PRE-?TRIAL\s+ORDER",
    r"ORDER[\s\.]+(?:dated|of)|ORDER OF (?:DISMISSAL|EXECUTION)",
    r"BY\s+ORDER\s+OF\s+THE\s+COURT",
    r"DECISION\s+is\s+hereby\s+rendered",
    r"WHEREFORE.{0,200}judgment",
    r"BRANCH\s+\d+,\s+(?:DAET|NAGA|CAMARINES)",
    r"(?:Hon\.|Honorable)\s+(?:Judge|Justice)\s+\w+",
    r"SO\s+ORDERED",
    r"clerk\s+of\s+court",
    r"writ\s+of\s+(?:execution|preliminary)",
]
COURT_FILENAME_TOKENS = [
    r"^Order[\s\-_]",
    r"[Nn]otice\s+of\s+(?:[Pp]re[\s\-]?trial|[Hh]earing)",
    r"\bDecision\b.*\.pdf",
    r"\bResolution\b.*\.pdf",
    r"[Pp]retrial[\s\-_]Order",
    r"Writ[\s\-_]of",
]
AGENCY_TOKENS = [
    r"ANTI-?RED\s+TAPE\s+AUTHORITY|ARTA",
    r"LAND\s+REGISTRATION\s+AUTHORITY|LRA",
    r"REGISTER\s+OF\s+DEEDS|REGISTRY\s+OF\s+DEEDS",
    r"BUREAU\s+OF\s+INTERNAL\s+REVENUE|BIR",
    r"DEPARTMENT\s+OF\s+(?:THE\s+)?INTERIOR\s+AND\s+LOCAL\s+GOVERNMENT|DILG",
    r"DEPARTMENT\s+OF\s+AGRARIAN\s+REFORM|DAR",
    r"MUNICIPAL\s+TREASURER|OFFICE\s+OF\s+THE\s+MUNICIPAL\s+TREASURER",
    r"PROVINCIAL\s+ASSESSOR|MUNICIPAL\s+ASSESSOR",
    r"NATIONAL\s+ARCHIVES",
]


def score_party(text, filename):
    text_only = (text or "")[:25000]
    fn = filename or ""
    sample = text_only + " " + fn
    scores = {"plaintiff": 0, "respondent": 0, "court": 0, "agency": 0}
    for rx in PLAINTIFF_TOKENS:
        if re.search(rx, sample, re.IGNORECASE):
            scores["plaintiff"] += 1
    for rx in PLAINTIFF_FILENAME_TOKENS:
        if re.search(rx, fn, re.IGNORECASE):
            scores["plaintiff"] += 2  # filename match weighted higher (more reliable signal)
    for rx in RESPONDENT_TOKENS:
        if re.search(rx, sample, re.IGNORECASE):
            scores["respondent"] += 1
    for rx in RESPONDENT_FILENAME_TOKENS:
        if re.search(rx, fn, re.IGNORECASE):
            scores["respondent"] += 2
    for rx in COURT_TOKENS:
        if re.search(rx, sample, re.IGNORECASE):
            scores["court"] += 1
    for rx in COURT_FILENAME_TOKENS:
        if re.search(rx, fn, re.IGNORECASE):
            scores["court"] += 3  # filename court signal is very strong
    for rx in AGENCY_TOKENS:
        if re.search(rx, sample, re.IGNORECASE):
            scores["agency"] += 1
    return scores


def filing_role(classification, smart_filename):
    cls = (classification or "").lower()
    fn = (smart_filename or "").lower()
    if any(k in cls for k in ("complaint", "answer", "motion", "reply", "court filing", "memorandum")): return "pleading"
    if "order" in cls or "decision" in cls or "resolution" in cls: return "order"
    if "notice" in cls: return "notice"
    if "affidavit" in cls or "judicial affidavit" in fn: return "affidavit"
    if "letter" in cls or "correspondence" in cls or "demand" in cls: return "correspondence"
    if "title" in cls or "tax" in cls or "deed" in cls or "spa" in fn: return "evidence"
    if "exhibit" in cls or "exhibit" in fn: return "evidence"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT id, smart_filename, classification, execution_status, doc_date,
               LEFT(extracted_text, 25000) AS text
          FROM documents
         WHERE case_file=%s
           AND extracted_text IS NOT NULL AND length(extracted_text) >= 200
           AND (execution_status IN ('executed_filed', 'executed_notarized', 'executed_signed_only',
                                       'government_issued') OR
                classification IN ('Complaint','Court Filing','Motion','Answer','Reply','Order',
                                    'Notice','Memorandum','Resolution','Affidavit','Judicial Affidavit',
                                    'Demand Letter','Letter','Correspondence'))
         ORDER BY id
    """, (args.case,))
    docs = cur.fetchall()
    print(f"  scanning {len(docs)} filing-class docs for {args.case}")

    # Determine matter_code from case_file
    cur.execute("SELECT matter_code FROM matters WHERE case_file=%s AND matter_type='civil_case' LIMIT 1", (args.case,))
    m = cur.fetchone()
    civil_matter = m["matter_code"] if m else None

    stats = {"plaintiff": 0, "respondent": 0, "court": 0, "agency": 0, "third_party": 0, "ambiguous": 0}
    inserted = 0
    for d in docs:
        scores = score_party(d["text"], d["smart_filename"])
        winner_score = max(scores.values())
        if winner_score == 0:
            party = "third_party"
            conf = 0.3
            stats["third_party"] += 1
        else:
            # Pick highest. Tie-break by priority hierarchy: court > respondent > plaintiff > agency.
            # Only flag ambiguous if STRICTLY tied (top1 == top2) AND tie is between adversarial parties.
            top = sorted(scores.items(), key=lambda x: -x[1])
            PRIORITY = {"court": 4, "respondent": 3, "plaintiff": 2, "agency": 1}
            if len(top) > 1 and top[0][1] == top[1][1]:
                tied_parties = {p for p, s in top if s == top[0][1]}
                # If court is among tied parties, court wins (procedural docs from court override).
                if "court" in tied_parties:
                    party = "court"
                    conf = 0.7
                    stats[party] += 1
                # If plaintiff AND respondent both tied, that's true ambiguity (joint pleadings, citations).
                elif "plaintiff" in tied_parties and "respondent" in tied_parties:
                    party = "third_party"
                    conf = 0.4
                    stats["ambiguous"] += 1
                else:
                    # Otherwise, priority hierarchy resolves
                    party = max(tied_parties, key=lambda p: PRIORITY.get(p, 0))
                    conf = 0.6
                    stats[party] += 1
            else:
                party = top[0][0]
                conf = min(1.0, 0.5 + winner_score * 0.1)
                stats[party] += 1
        role = filing_role(d["classification"], d["smart_filename"])

        if args.dry_run:
            print(f"  [DRY] #{d['id']:4d}  {party:11s} ({role:12s} conf={conf:.2f})  {(d['smart_filename'] or '—')[:60]}")
            inserted += 1
            continue

        try:
            cur.execute("""
                INSERT INTO case_party_filings
                  (matter_code, case_file, doc_id, filing_party, filing_role,
                   filing_date, confidence, detection_method, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'regex_v2', %s)
                ON CONFLICT (doc_id, filing_party) DO UPDATE SET
                  confidence = EXCLUDED.confidence,
                  filing_role = EXCLUDED.filing_role,
                  filing_date = EXCLUDED.filing_date,
                  detection_method = EXCLUDED.detection_method,
                  notes = EXCLUDED.notes
            """, (civil_matter, args.case, d["id"], party, role,
                  d["doc_date"], conf,
                  f"scores={scores}"))
            inserted += 1
        except Exception as e:
            print(f"  ⚠ doc#{d['id']}: {e}")

    print(f"\n  inserted/updated: {inserted}")
    print(f"  by party:")
    for p, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {p:14s}  {n}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
