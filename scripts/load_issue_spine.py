#!/usr/bin/env python3
"""load_issue_spine.py — stand up the operator's canonical issue registry (the SPINE) and begin
correcting the data layer against it. $0 — operator assertions ARE verified provenance.

WHY (operator, 2026-06-20): "we don't even have the data layer correct, and the build needs to
happen simultaneously." Proven true — the ₱20M DAR case (CV-6839) had a NULL value field, 0
verified facts, and the guardianship→DAR gate was unmodeled (fact_edges had 0 rows). You can't
anchor a spine to that; laying the spine IS the correction. This encodes the 10-issue inventory
as the canonical truth, maps each issue to the system matters that (should) cover it with an
audit verdict, records the load-bearing facts as VERIFIED (operator-asserted), and models the
guardianship keystone gate. Idempotent.

  python3 scripts/load_issue_spine.py            # dry: print plan
  python3 scripts/load_issue_spine.py --apply
"""
import argparse
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
CF = "MWK-001"

# The operator's Master Inventory (2026-06-20). coverage = audit verdict against the data layer.
ISSUES = [
    (1, "DAR just-compensation award (~₱20M+)",
     "Awarded but not collected. Requires Writ of Execution. Blocked by lack of guardianship.",
     ["MWK-CV6839"], 20000000, "MWK-GUARDIANSHIP", "tracked_but_unvalued"),
    (2, "Guardianship (Atty. Don Botor)",
     "Required to collect the DAR funds on behalf of the heirs; confers authority to litigate.",
     ["MWK-GUARDIANSHIP"], None, None, "tracked_stale_stage"),
    (3, "Improper real-property-tax assessments (esp. Brgy Sinco)",
     "Taxes paid under protest; Assessor's failure to properly assess improvements.",
     [], None, None, "UNTRACKED"),
    (4, "Illegal structures / encroachments on titled land",
     "Multiple structures built without permits; Civil Code Art. 445 (builder in bad faith).",
     [], None, None, "UNTRACKED"),
    (5, "Municipal Assessor — Gemma P. Abla",
     "Delay/refusal of certified tax records; extra requirements; failure to assess improvements; "
     "questionable counter-affidavit.",
     ["MWK-ARTA-1321"], None, None, "tracked"),
    (6, "Building Official — Engr. Erwin Balane",
     "Failure to enforce the National Building Code; refusal to act on illegal construction. "
     "NOTE: operator ties this to Case 26-360 (Aug 12 testimony) — system frames 26-360 as the "
     "void-title case vs GLORIA Balane. Scope clash to resolve.",
     ["MWK-ARTA-0792", "MWK-ARTA-1378", "MWK-CV26360"], None, None, "MIS-FRAMED_vs_26360"),
    (7, "Mayor Alexander Pajarillo",
     "Protecting illegal builders / erring officials; abuse of authority / retaliation; "
     "failure to supervise the Assessor and Building Official.",
     ["MWK-ARTA-0747"], None, None, "tracked_appeal_overdue"),
    (8, "ARTA cases & mishandling",
     "Multiple pending cases, inconsistent treatment; one referred back to Provincial DILG.",
     ["MWK-ARTA-0690", "MWK-ARTA-1210", "MWK-ARTA-1212", "MWK-ARTA-1319",
      "MWK-ARTA-1378", "MWK-ARTA-1891", "MWK-ARTA-DILG"], None, None, "tracked_no_followup_dates"),
    (9, "Register of Deeds — de la Fuente transfers",
     "Failure to provide documents on the Cesar de la Fuente transfers; incomplete/missing "
     "transfer documents.",
     ["MWK-TCT4497"], None, None, "tracked_demand_overdue"),
    (10, "Sangguniang Bayan",
     "Failure to act on illegal structures; retaliation against the Senior Citizens Association "
     "President.",
     [], None, None, "UNTRACKED"),
]

# Load-bearing facts to record as VERIFIED (operator-asserted) — the ones the audit found missing.
OPERATOR_FACTS = [
    ("MWK-CV6839",
     "DAR/CARP just compensation (~₱20,000,000+) has been AWARDED in Civil Case 6839 (RTC Cam. "
     "Norte, special agrarian) but NOT yet collected — collection requires a Writ of Execution and "
     "is blocked until a guardian is appointed for the heirs (operator-asserted, 2026-06-20; exact "
     "award figure to confirm from the decision).", "operator"),
    ("MWK-GUARDIANSHIP",
     "The guardianship grant is the MASTER GATE: until a guardian is appointed (the prior heir-"
     "representative Cesar de la Fuente is deceased), the heirs can neither collect the ₱20M DAR "
     "award (CV-6839) nor prosecute as substituted parties in CV-26360. Filed with Atty. Don Botor "
     "(operator-asserted, 2026-06-20).", "operator"),
]

KEYSTONE = ("MWK-001",
    "Guardianship grant = master gate — unblocks the ₱20M DAR collection (CV-6839) AND confers heir "
    "authority to prosecute CV-26360",
    "MWK-GUARDIANSHIP", ["MWK-CV6839", "MWK-CV26360"],
    "Heirs cannot collect the awarded just compensation or be substituted as parties until a guardian "
    "is appointed; the prior representative (Cesar de la Fuente) is deceased.", "open")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.apply:
        print(f"[dry] would create client_issues + load {len(ISSUES)} issues, "
              f"{len(OPERATOR_FACTS)} verified operator facts, 1 keystone gate. Use --apply.")
        for i in ISSUES:
            print(f"  #{i[0]:>2} [{i[6]}] {i[1]}")
        return
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_issues (
            id serial PRIMARY KEY, case_file text NOT NULL, issue_no int,
            title text NOT NULL, detail text, maps_to_matters text[],
            value_amount numeric, gated_by text, coverage text,
            status text DEFAULT 'open', provenance_level text DEFAULT 'operator_asserted',
            created_by text DEFAULT 'operator', created_at timestamptz DEFAULT now(),
            updated_at timestamptz DEFAULT now(), UNIQUE(case_file, issue_no))""")
    for no, title, detail, matters, val, gated, cov in ISSUES:
        cur.execute("""INSERT INTO client_issues
            (case_file,issue_no,title,detail,maps_to_matters,value_amount,gated_by,coverage)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (case_file,issue_no) DO UPDATE SET title=EXCLUDED.title,
              detail=EXCLUDED.detail, maps_to_matters=EXCLUDED.maps_to_matters,
              value_amount=EXCLUDED.value_amount, gated_by=EXCLUDED.gated_by,
              coverage=EXCLUDED.coverage, updated_at=now()""",
            (CF, no, title, detail, matters, val, gated, cov))
    # load-bearing facts → verified (operator-asserted); skip if an identical statement exists
    for mc, stmt, by in OPERATOR_FACTS:
        cur.execute("SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s", (mc, stmt))
        if not cur.fetchone():
            cur.execute("""INSERT INTO matter_facts
                (matter_code,statement,fact_kind,source_kind,source_id,provenance_level,confidence,created_by,created_at)
                VALUES (%s,%s,'issue','operator','operator-2026-06-20','verified',1.0,%s,now())""",
                (mc, stmt, by))
    # the guardianship gate keystone
    cf, label, ctrl, casc, basis, st = KEYSTONE
    cur.execute("SELECT 1 FROM keystones WHERE controlling_matter=%s AND label=%s", (ctrl, label))
    if not cur.fetchone():
        cur.execute("""INSERT INTO keystones (case_file,label,controlling_matter,cascade_matters,basis,status,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,now())""", (cf, label, ctrl, casc, basis, st))
    # report
    cur.execute("SELECT count(*) FROM client_issues WHERE case_file=%s", (CF,))
    n_iss = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM client_issues WHERE case_file=%s AND coverage LIKE '%%UNTRACKED%%'", (CF,))
    n_unt = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM matter_facts WHERE provenance_level='verified' AND source_kind='operator'")
    n_vf = cur.fetchone()[0]
    print(f"[apply] client_issues: {n_iss} issues loaded ({n_unt} untracked flagged).")
    print(f"[apply] verified operator facts now: {n_vf}; guardianship gate keystone modeled.")


if __name__ == "__main__":
    main()
