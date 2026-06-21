#!/usr/bin/env python3
"""load_agency_mandates.py — embed each oversight body's MANDATE in the corpus. Reference-law DB.

So the stack knows, for any official's misconduct: which body has jurisdiction, what remedy it can
grant, how to invoke it, and where to appeal — turning the issue inventory into forum-routing, and
letting analyst/brief_drafter/Leo reason about WHERE to bring a case and WHAT to ask for.

Provenance discipline: this is REFERENCE LAW, cited to each body's enabling charter (RA / constitutional
article) — distinct from case-fact tiers. The charter + high-level mandate are grounded; operational
specifics (exact disciplining authority, reglementary periods) carry a `verify` note for counsel —
never fabricated as settled.

  python3 scripts/load_agency_mandates.py --apply
  python3 scripts/load_agency_mandates.py --list
"""
import argparse
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# code, name, kind, charter, mandate, jurisdiction, powers, how_to_invoke, appeal_path, relevance, verify
AGENCIES = [
    ("ARTA", "Anti-Red Tape Authority", "oversight", "R.A. 11032 (2018)",
     "Streamline government service; enforce the Citizen's Charter; act on red-tape / fixing complaints.",
     "Any government agency/LGU and its officials re: processing of transactions.",
     "Investigate, refer to the CART, recommend administrative liability; coordinate sanctions.",
     "File a complaint with ARTA → referral to the agency's CART.",
     "Office of the President / Executive Secretary.",
     "Mayor Pajarillo (0747), Assessor Abla, Mun. Engineer Balane, records refusals — the LGU red-tape cluster.",
     "Exact processing-day class (3/7/20) per transaction; sanction mechanics."),
    ("CSC", "Civil Service Commission", "oversight", "1987 Constitution Art. IX-B; Admin Code (E.O. 292)",
     "Central personnel agency; administrative discipline of civil servants.",
     "Appointive civil servants (career & non-career) in the civil service.",
     "Hear/decide administrative cases; impose suspension/dismissal; rule on appointments.",
     "Verified complaint / formal charge.",
     "CSC proper → Court of Appeals (Rule 43).",
     "Appointive LGU employees (e.g., assessor's-office staff, draftsman) — admin discipline route.",
     "Whether a given official is appointive (CSC) vs elective (DILG/OP/Sanggunian); reglementary periods."),
    ("OMBUDSMAN", "Office of the Ombudsman", "oversight", "1987 Constitution Art. XI; R.A. 6770; A.O. 07",
     "Investigate & prosecute public officials for illegal, unjust, improper or inefficient acts (graft).",
     "ANY public official/employee (elective or appointive), incl. LGU officials.",
     "Investigate; prosecute before the Sandiganbayan/courts; order suspension/removal; direct action.",
     "Complaint-affidavit with supporting evidence.",
     "Motion for Reconsideration → CA (Rule 43, admin) / SC (Rule 65, criminal).",
     "The strongest forum for graft/conspiracy vs Pajarillo/Abla/Balane/de la Fuente acts.",
     "Counter-affidavit / MR periods; admin vs criminal track selection."),
    ("DILG", "Dept. of the Interior & Local Government", "oversight", "R.A. 6975; R.A. 7160 (LGC); E.O. 292",
     "General supervision over LGUs; receives/refers administrative complaints vs local officials.",
     "Local government units and their officials (elective & appointive).",
     "Investigate; recommend; the LGC disciplining authority imposes the sanction.",
     "Administrative complaint (often via DILG regional office).",
     "Per the LGC: Office of the President (certain elective) / Sangguniang (others).",
     "ARTA-1891 was referred here; the Sangguniang Bayan / Mayor accountability track.",
     "WHO is the disciplining authority for a given elective LGU official under R.A. 7160 — confirm w/ counsel."),
    ("OP-ES", "Office of the President / Executive Secretary", "exec", "Admin Code (E.O. 292)",
     "Administrative supervision; appellate authority over ARTA; disciplining authority for some local elective officials.",
     "ARTA appeals; certain LGU elective officials.",
     "Decide appeals; impose discipline within its authority.",
     "Petition / appeal.",
     "Court of Appeals (Rule 43) / Supreme Court.",
     "ARTA-0690 / 0792 escalated here; MWK-OP-PETITION (supervisory review).",
     "Appeal periods + which officials it disciplines directly."),
    ("DOJ-PROS", "DOJ / Office of the City/Provincial Prosecutor", "prosecution", "Admin Code; Rules on Criminal Procedure",
     "Conduct preliminary investigation of criminal complaints; file informations.",
     "Criminal complaints vs any person (incl. officials, in their personal capacity).",
     "Preliminary investigation; resolve probable cause; file in court.",
     "Complaint-affidavit for preliminary investigation.",
     "Petition for review to the DOJ Secretary → CA / SC.",
     "Falsification / estafa / graft criminal track (de la Fuente void deed; conspiracy).",
     "Venue + which office; PI periods."),
    ("SANGGUNIAN", "Sangguniang Bayan (Mercedes)", "local-legislative", "R.A. 7160 (Local Government Code)",
     "Local legislative body; disciplining authority over certain local officials per the LGC.",
     "Municipal officials within its statutory authority.",
     "Enact ordinances; hear certain administrative complaints; recommend.",
     "Verified administrative complaint per the LGC.",
     "Office of the President / courts per the LGC.",
     "Issue #10 (Sangguniang Bayan / Senior Citizens); local-official accountability.",
     "Its exact disciplinary jurisdiction vs DILG/OP — confirm w/ counsel."),
    ("COA", "Commission on Audit", "oversight", "1987 Constitution Art. IX-D",
     "Audit government revenue/expenditure; disallow irregular/illegal/unconscionable disbursements.",
     "All government funds and property, incl. LGUs.",
     "Audit; issue Notices of Disallowance; hold officials liable to refund.",
     "Request for audit / report of irregularity.",
     "COA proper → Supreme Court (Rule 64).",
     "If LGU funds/fees were misapplied (e.g., improper RPT, fees) — issue #3.",
     "Whether a COA angle exists on the specific transactions."),
    ("RD-LRA", "Register of Deeds (Cam. Norte) / LRA", "registry", "P.D. 1529 (Property Registration Decree)",
     "Register land titles & instruments; maintain the Torrens record; LRA supervises.",
     "Titled land; deeds, mortgages, adverse claims, cancellations.",
     "Register/annotate/cancel; the COURT orders cancellation of a Torrens title (RD complies).",
     "Petition/request; cancellation needs a court order (the CV-26360 prayer).",
     "Consulta to the LRA; judicial relief.",
     "TCT 079-2021002126 cancellation (CV-26360); RD de la Fuente issue (#9); TCT4497/TCT1616 chains.",
     "Administrative vs judicial cancellation limits."),
    ("DAR-DARAB", "DAR / DARAB", "agrarian", "R.A. 6657 (CARL); E.O. 229",
     "Agrarian reform implementation; DARAB adjudicates agrarian disputes; just compensation via SAC.",
     "Agricultural land under CARP; landowner/government compensation.",
     "Determine coverage; DARAB adjudication; just-compensation valuation (RTC as Special Agrarian Court).",
     "Petition / claim; just compensation fixed by the SAC.",
     "DARAB → CA; SAC decision → CA / SC.",
     "CV-6839 (Heirs of MWK v. DAR + LandBank — just compensation, 227 ha across T-4494/4501/4502).",
     "CARP coverage specifics; valuation methodology."),
    ("DENR-MGB", "DENR / Mines & Geosciences Bureau (Region V)", "mining", "R.A. 7942 (Mining Act); P.D. 1586",
     "Administer mineral resources; grant/deny mining permits & agreements; environmental compliance.",
     "Mining tenements, permits (EXPA/APSA), environmental clearances.",
     "Grant/deny/cancel permits; resolve mining disputes (Panel of Arbitrators).",
     "Application / protest before MGB.",
     "Mines Adjudication Board → CA / SC.",
     "NIBDC matters (APSA-000322, EXPA-000250) — the mining client, kept separate from MWK.",
     "Tenement status + protest procedure."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS agency_mandates (
        code text PRIMARY KEY, name text, kind text, charter text, mandate text, jurisdiction text,
        powers text, how_to_invoke text, appeal_path text, relevance text, verify_note text,
        provenance text DEFAULT 'reference', updated_at timestamptz DEFAULT now())""")
    if a.apply:
        for row in AGENCIES:
            cur.execute("""INSERT INTO agency_mandates
                (code,name,kind,charter,mandate,jurisdiction,powers,how_to_invoke,appeal_path,relevance,verify_note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, kind=EXCLUDED.kind,
                charter=EXCLUDED.charter, mandate=EXCLUDED.mandate, jurisdiction=EXCLUDED.jurisdiction,
                powers=EXCLUDED.powers, how_to_invoke=EXCLUDED.how_to_invoke, appeal_path=EXCLUDED.appeal_path,
                relevance=EXCLUDED.relevance, verify_note=EXCLUDED.verify_note, updated_at=now()""", row)
        print(f"[mandates] loaded {len(AGENCIES)} oversight bodies into agency_mandates")
    cur.execute("SELECT code, name, charter, left(relevance,60) FROM agency_mandates ORDER BY kind, code")
    rows = cur.fetchall()
    print("=" * 80); print(f"OVERSIGHT-MANDATE DB ({len(rows)} bodies)"); print("=" * 80)
    for code, name, charter, rel in rows:
        print(f"  {code:12} {name[:40]:40} {charter[:22]}")
        print(f"               ↳ ours: {rel}")
    if not rows:
        print("  (empty — run with --apply)")


if __name__ == "__main__":
    main()
