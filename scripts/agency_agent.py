#!/usr/bin/env python3
"""agency_agent.py — resident agent: forum desks (ARTA / CSC / Ombudsman / Civil). $0.

One engine, four forum playbooks. Each forum has its own clocks, procedure, and escalation grounds —
an ARTA deadline must not be tracked with civil-court logic. This classifies each matter to a desk by
its forum, and for each matter surfaces: the forum's deadline rules + escalation grounds (the playbook),
the last incoming filing on record (from filing_alerts), and where it sits in that forum's procedure —
so nothing forum-specific is missed before Aug 12.

DISCIPLINE: forum deadlines are legally load-bearing. ARTA (RA 11032) and Civil (Rules of Court) rules
are encoded with their source (statute + the corpus doc that grounds them). CSC and Ombudsman have no
matter on file yet and their exact periods are marked NEEDS-COUNSEL-VERIFICATION — never fabricated.

  python3 scripts/agency_agent.py --desk ARTA      # one desk
  python3 scripts/agency_agent.py --all            # all desks + matters
"""
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

PLAYBOOKS = {
    "ARTA": {
        "name": "Anti-Red Tape Authority",
        "statute": "R.A. 11032 (Ease of Doing Business / ARTA Act of 2018)",
        "grounded": True,
        "deadlines": [
            ("Simple transaction", "3 working days", "RA 11032 §9 — grounded in doc 384"),
            ("Complex transaction", "7 working days", "RA 11032 §9"),
            ("Highly technical", "20 working days", "RA 11032 §9"),
        ],
        "procedure": ["Complaint filed", "ARTA refers to CART/Agency", "CART resolves",
                      "If unresolved → escalate", "Appeal to Office of the President / Exec. Sec."],
        "escalation": [
            "Termination of Referral if the official complained-of is the CART approving Chairperson (doc 967)",
            "Termination of Referral if 20 working days lapse from referral with no resolution (doc 967)",
        ],
        "violations": "§21(b) additional requirements · §21(d) · §21(e) failure to render service",
    },
    "CIVIL": {
        "name": "Civil / Courts (RTC / MTC)",
        "statute": "2019 Amended Rules of Civil Procedure · Rules on Summary Procedure",
        "grounded": True,
        "deadlines": [
            ("Reply to Comment/Opposition", "5 calendar days", "Rule 15 §5(c) — grounded in doc 452"),
            ("Last day on weekend/holiday → next working day", "Rule 22 §1", "grounded in doc 452"),
            ("Summary Judgment standard", "Rule 35 (no genuine issue + entitled as a matter of law)", "doc 452"),
        ],
        "procedure": ["Complaint", "Summons / Answer", "Pre-trial", "Trial / Summary Judgment",
                      "Decision", "MR / Appeal"],
        "escalation": ["Motion for Reconsideration", "Appeal per the Rules (RTC/CA)"],
        "note": "CV-26360 is governed by the Rules on Summary Procedure (doc 1088).",
    },
    "CSC": {
        "name": "Civil Service Commission",
        "statute": "CSC rules on administrative cases (e.g., 2017 RACCS)",
        "grounded": False,
        "deadlines": [("Answer to formal charge", "NEEDS-COUNSEL-VERIFICATION", "no corpus source yet"),
                      ("Appeal period", "NEEDS-COUNSEL-VERIFICATION", "no corpus source yet")],
        "procedure": ["Complaint", "Preliminary investigation", "Formal charge", "Answer",
                      "Decision", "Appeal to CSC proper / CA (Rule 43)"],
        "escalation": ["Appeal to the Commission proper", "Petition for review to CA (Rule 43)"],
        "note": "No CSC matter on file yet — desk ready; confirm all periods with counsel before relying.",
    },
    "OMBUDSMAN": {
        "name": "Office of the Ombudsman",
        "statute": "R.A. 6770 (Ombudsman Act) · Administrative Order No. 07",
        "grounded": False,
        "deadlines": [("Counter-affidavit", "NEEDS-COUNSEL-VERIFICATION", "no corpus source yet"),
                      ("Motion for Reconsideration", "NEEDS-COUNSEL-VERIFICATION", "no corpus source yet")],
        "procedure": ["Complaint-affidavit", "Evaluation", "Counter-affidavit", "Resolution",
                      "MR", "Review (CA Rule 43 admin / SC Rule 65 criminal)"],
        "escalation": ["Motion for Reconsideration", "Rule 43 (admin) / Rule 65 (criminal) review"],
        "note": "No Ombudsman matter on file yet — desk ready; confirm all periods with counsel.",
    },
}


def classify(forum):
    f = (forum or "").lower()
    if "arta" in f:
        return "ARTA"
    if "csc" in f or "civil service" in f:
        return "CSC"
    if "ombudsman" in f:
        return "OMBUDSMAN"
    if any(k in f for k in ("rtc", "mtc", "court", "agrarian", "darab")):
        return "CIVIL"
    return None


def desk_matters(cur):
    cur.execute("""SELECT matter_code, coalesce(forum, court_or_agency, '') FROM matters
                   WHERE matter_code NOT LIKE 'AUTO-%' AND matter_code NOT LIKE 'ARCHIVE-%'""")
    by = {}
    for mc, forum in cur.fetchall():
        d = classify(forum)
        if d:
            by.setdefault(d, []).append((mc, forum))
    return by


def show_desk(cur, desk, matters):
    pb = PLAYBOOKS[desk]
    tag = "✓ grounded" if pb["grounded"] else "⚠ NEEDS-COUNSEL-VERIFICATION"
    print("\n" + "=" * 74)
    print(f"DESK: {desk} — {pb['name']}   [{tag}]")
    print(f"  Authority: {pb['statute']}")
    print("  Deadlines:")
    for label, period, src in pb["deadlines"]:
        print(f"    • {label}: {period}   ({src})")
    print("  Procedure: " + " → ".join(pb["procedure"]))
    print("  Escalation grounds:")
    for e in pb["escalation"]:
        print(f"    • {e}")
    if pb.get("note"):
        print(f"  Note: {pb['note']}")
    print(f"  Matters on this desk ({len(matters)}):")
    for mc, forum in sorted(matters):
        cur.execute("SELECT count(*) FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'", (mc,))
        vf = cur.fetchone()[0]
        cur.execute("""SELECT received, left(subject,46) FROM filing_alerts WHERE matter_code=%s
                       ORDER BY received DESC NULLS LAST LIMIT 1""", (mc,))
        last = cur.fetchone()
        lastf = f"last filing {last[0]}: {last[1]}" if last else "no filing on record"
        print(f"    - {mc:20} {vf:3} verified facts · {lastf}")


def main():
    a = sys.argv
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    by = desk_matters(cur)
    desks = [a[a.index("--desk") + 1].upper()] if "--desk" in a else list(PLAYBOOKS)
    for d in desks:
        if d not in PLAYBOOKS:
            print(f"unknown desk {d}; choose from {list(PLAYBOOKS)}"); continue
        show_desk(cur, d, by.get(d, []))


if __name__ == "__main__":
    main()
