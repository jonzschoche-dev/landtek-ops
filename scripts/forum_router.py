#!/usr/bin/env python3
"""forum_router.py — wire each grievance (client_issues) to its candidate forums. The case-builder spine.

Joins the 10-issue inventory to the oversight-mandate DB: for each issue, which body(ies) have
jurisdiction, what remedy to seek there, and why. Writes `case_forums` (issue → forum → remedy /
rationale / status), which the cockpit's /ops/cases view renders live. The routing is a CURATED legal
strategy call (grounded in agency_mandates), status starts 'candidate'; the operator promotes one to
'chosen'/'filed' and the desks + execution_tracker track it from there. Specifics that decide a filing
still carry the mandate DB's NEEDS-COUNSEL-VERIFICATION caveat.

  python3 scripts/forum_router.py --apply
  python3 scripts/forum_router.py --report
"""
import argparse
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# issue_no -> [(forum_code, remedy_sought, rationale)] — curated from the mandate DB.
ROUTING = {
    1: [("DAR-DARAB", "Just compensation for 227ha (T-4494/4501/4502)", "Already in the SAC as CV-6839; RA 6657")],
    2: [("CIVIL", "Letters of guardianship over the properties", "RTC guardianship petition")],
    3: [("COA", "Notice of Disallowance / refund of improperly-collected RPT", "COA audit jurisdiction over LGU funds"),
        ("DILG", "Admin complaint re Brgy. Sinco officials", "LGU supervision"),
        ("SANGGUNIAN", "Local accountability", "LGC")],
    4: [("CIVIL", "Removal/demolition of illegal structures (Art. 445 accession)", "RTC"),
        ("ARTA", "If building permits were improperly issued/withheld", "RA 11032")],
    5: [("CSC", "Administrative discipline of Assessor Abla (if appointive)", "CSC — confirm appointive status"),
        ("OMBUDSMAN", "Graft/abuse complaint", "RA 6770")],
    6: [("CIVIL", "CV-26360 — Erwin Balane impleaded for validating the void sale", "accion reivindicatoria"),
        ("OMBUDSMAN", "Abuse of office (Mun. Engineer using office to validate a void sale)", "RA 6770"),
        ("ARTA", "Records refusal absent an SPA", "RA 11032 §21(b)")],
    7: [("ARTA", "CTN SL-2025-1021-0747 — red-tape violations", "RA 11032 §21(b)(d)(e)"),
        ("OMBUDSMAN", "Graft/abuse vs the Mayor", "RA 6770"),
        ("DOJ-PROS", "Criminal complaint", "Rules on Criminal Procedure"),
        ("OP-ES", "Appeal / supervisory review", "E.O. 292")],
    8: [("ARTA", "The ARTA case cluster", "RA 11032"),
        ("DILG", "Referrals (e.g., 1891)", "RA 6975 / 7160")],
    9: [("RD-LRA", "Cancellation of TCT 079-2021002126 (court-ordered)", "PD 1529 + the CV-26360 prayer"),
        ("DOJ-PROS", "Falsification / estafa re the void 2016 deed", "Rules on Criminal Procedure"),
        ("OMBUDSMAN", "If an RD official conspired", "RA 6770")],
    10: [("SANGGUNIAN", "Local-official accountability (Senior Citizens)", "LGC"),
         ("DILG", "Supervision", "RA 6975 / 7160")],
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS case_forums (
        issue_no int, forum_code text, remedy text, rationale text, status text DEFAULT 'candidate',
        notes text, updated_at timestamptz DEFAULT now(), UNIQUE(issue_no, forum_code))""")
    if a.apply:
        n = 0
        for issue_no, routes in ROUTING.items():
            for forum, remedy, rationale in routes:
                cur.execute("""INSERT INTO case_forums (issue_no,forum_code,remedy,rationale)
                    VALUES (%s,%s,%s,%s) ON CONFLICT (issue_no,forum_code)
                    DO UPDATE SET remedy=EXCLUDED.remedy, rationale=EXCLUDED.rationale, updated_at=now()
                    WHERE case_forums.status='candidate'""", (issue_no, forum, remedy, rationale))
                n += 1
        print(f"[forum-router] wired {n} issue→forum routes across {len(ROUTING)} issues")
    cur.execute("""SELECT cf.issue_no, coalesce(ci.title,'(issue '||cf.issue_no||')'),
                   count(*), string_agg(cf.forum_code, ', ' ORDER BY cf.forum_code)
                   FROM case_forums cf LEFT JOIN client_issues ci ON ci.issue_no=cf.issue_no
                   GROUP BY 1,2 ORDER BY 1""")
    print("=" * 78); print("FORUM ROUTING — each grievance → its candidate forums"); print("=" * 78)
    for issue_no, title, n, forums in cur.fetchall():
        print(f"  #{issue_no} {title[:42]:42} → {forums}")


if __name__ == "__main__":
    main()
