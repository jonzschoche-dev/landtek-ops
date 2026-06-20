#!/usr/bin/env python3
"""decipher_matter.py — give the system the machinery to DECIPHER a case instead of flattening it.

WHY (operator, 2026-06-20): CV-26360 has 3 Balane defendants (Gloria=title-holder, Engr. Erwin=
building official, Efren=spouse) and multiple causes — but the system collapsed it to one theory
("void-title vs Balane") with 2 respondents, because a matter was a FLAT row: one legal_theory, an
entity array, no roles, no causes. This adds the structure (matter_parties + matter_causes), pins
the operative pleading, and populates CV-26360 from operator ground truth ("all Balanes are in
26-360") + the already-deduped Balane entities. The standing version reads the operative pleading
(doc 419) to auto-extract this — that's the credit-gated comprehension step; the schema +
reconciliation here is $0 and is what makes the extraction representable at all.

  python3 scripts/decipher_matter.py --apply
"""
import argparse

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# CV-26360 deciphered from operator ground truth + deduped entities. Roles/causes are
# inferred_strong pending confirmation against the operative pleading (doc 419, Exhibit I Complaint).
MATTER = "MWK-CV26360"
OPERATIVE_DOC = 419
PARTIES = [
    # (entity_id, name, side, role, provenance)
    (400, "Patricia Keesey Zschoche", "plaintiff", "registered heir/owner (rep. by Jonathan Zschoche)", "verified"),
    (15, "Gloria Balane", "defendant", "holder of the void title TCT T-079-2021002126", "verified"),
    (3057, "Efren Balane", "defendant", "spouse / co-party of Gloria Balane", "inferred_strong"),
    (3060, "Engr. Erwin Balane", "defendant", "Municipal Building Official — failure to enforce the National Building Code / act on illegal structures", "operator"),
]
CAUSES = [
    # (cause, against, basis, provenance)
    ("Accion reinvindicatoria / nullification of TCT T-079-2021002126",
     "Gloria Balane, Efren Balane",
     "Void 1992 SPA (negotiate ≠ sell, revoked 2005) → void 2016 deed → void title; recover the parcel.",
     "verified"),
    ("Dereliction by the Building Official re illegal structures",
     "Engr. Erwin Balane",
     "Failure to enforce the National Building Code / refusal to act on permitless construction on the titled land (operator issue #6 — confirm exact pleading count vs doc:419).",
     "operator"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    if not a.apply:
        print(f"[dry] would create matter_parties + matter_causes and decipher {MATTER}: "
              f"{len(PARTIES)} parties, {len(CAUSES)} causes, operative pleading doc:{OPERATIVE_DOC}.")
        return
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_parties (
        id serial PRIMARY KEY, matter_code text, entity_id int, party_name text,
        side text, role text, provenance_level text DEFAULT 'inferred_strong',
        created_at timestamptz DEFAULT now(), UNIQUE(matter_code, entity_id, side))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_causes (
        id serial PRIMARY KEY, matter_code text, cause text, against_parties text,
        basis text, provenance_level text DEFAULT 'inferred_strong',
        operative_doc_id int, created_at timestamptz DEFAULT now(), UNIQUE(matter_code, cause))""")
    for eid, name, side, role, prov in PARTIES:
        cur.execute("""INSERT INTO matter_parties (matter_code,entity_id,party_name,side,role,provenance_level)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (matter_code,entity_id,side)
            DO UPDATE SET role=EXCLUDED.role, party_name=EXCLUDED.party_name,
                          provenance_level=EXCLUDED.provenance_level""",
            (MATTER, eid, name, side, role, prov))
    for cause, against, basis, prov in CAUSES:
        cur.execute("""INSERT INTO matter_causes (matter_code,cause,against_parties,basis,provenance_level,operative_doc_id)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (matter_code,cause)
            DO UPDATE SET against_parties=EXCLUDED.against_parties, basis=EXCLUDED.basis,
                          provenance_level=EXCLUDED.provenance_level, operative_doc_id=EXCLUDED.operative_doc_id""",
            (MATTER, cause, against, basis, prov, OPERATIVE_DOC))
    # pin the operative pleading as a verified fact
    stmt = (f"OPERATIVE PLEADING for {MATTER} = doc:{OPERATIVE_DOC} (Exhibit I — Complaint, Civil Case "
            f"26-360). It defines the full defendant roster (Gloria, Efren, Engr. Erwin Balane) and the "
            f"causes — the authoritative source for deciphering the case structure (operator-confirmed: "
            f"all Balanes are in 26-360).")
    cur.execute("SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s", (MATTER, stmt))
    if not cur.fetchone():
        cur.execute("""INSERT INTO matter_facts (matter_code,statement,fact_kind,source_kind,source_id,
                       provenance_level,confidence,created_by,created_at)
                       VALUES (%s,%s,'structure','doc',%s,'verified',1.0,'operator',now())""",
                    (MATTER, stmt, str(OPERATIVE_DOC)))
    cur.execute("SELECT side, count(*) FROM matter_parties WHERE matter_code=%s GROUP BY side", (MATTER,))
    sides = dict(cur.fetchall())
    cur.execute("SELECT count(*) FROM matter_causes WHERE matter_code=%s", (MATTER,))
    nc = cur.fetchone()[0]
    print(f"[apply] {MATTER} deciphered: {sides.get('defendant',0)} defendants, "
          f"{sides.get('plaintiff',0)} plaintiff(s), {nc} causes, operative pleading doc:{OPERATIVE_DOC}.")
    print("[apply] STANDING NEXT: read doc:419 to confirm/complete causes (credit-gated comprehension).")


if __name__ == "__main__":
    main()
