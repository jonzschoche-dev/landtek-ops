#!/usr/bin/env python3
"""decipher_matter.py — give the system the machinery to DECIPHER a case, from the SOURCE pleading.

A matter was a flat row (one legal_theory, an entity array). This populates the structure
(matter_parties + matter_causes) by READING the operative pleading and citing it — so the rows are
VERIFIED (gate-passing: source_doc_id/operative_doc_id resolves + a quoted span), not hand-fed.

CV-26360 deciphered from doc 781 — 'Latest Draft Complaint - Zschoche v. Balane, et al.' (the real
operative complaint, found in the Barandon email thread; the earlier 419/384 were mislabeled decoys).

  python3 scripts/decipher_matter.py --apply
"""
import argparse

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MATTER = "MWK-CV26360"
OPERATIVE_DOC = 781   # Latest Draft Complaint - Zschoche v. Balane, et al. (legible, in email)

# (entity_id, name, side, role, provenance, source_excerpt) — READ from doc 781, cited → verified.
PARTIES = [
    (400, "Patricia Keesey Zschoche", "plaintiff",
     "co-owner/plaintiff, represented by her son and Attorney-in-fact Jonathan Paul Zschoche", "verified",
     "PLAINTIFF PATRICIA KEESEY ZSCHOCHE ... represented by her son and Attorney-in-fact, JONATHAN PAUL ZSCHOCHE"),
    (15, "Gloria Balane", "defendant",
     "buyer under the void 2016 Deed of Absolute Sale; holder of the assailed TCT 079-2021002126", "verified",
     "herein defendant Gloria Balane fraudulently executed a Deed of Absolute Sale, conveying the subject property in favor of the latter"),
    (3057, "Efren Balane", "defendant", "spouse of Gloria Balane, sued jointly", "verified",
     "Defendant Efren Balane is being sued jointly with Gloria as her spouse"),
    (3059, "Jomil Torralba", "defendant",
     "present illegal possessor of the subject property (allowed to reside there by Gloria and Efren)", "verified",
     "defendant Spouses Jomil and Princess Balane Torralba are being impleaded as the present illegal possessors of the subject property"),
    (2391, "Princess Balane Torralba", "defendant",
     "present illegal possessor of the subject property (spouse of Jomil Torralba)", "verified",
     "defendant Spouses Jomil and Princess Balane Torralba are being impleaded as the present illegal possessors of the subject property"),
    (3060, "Engr. Erwin Balane", "defendant",
     "child of Gloria & Efren; used his official capacity as Municipal Engineer of Mercedes to perform "
     "acts validating/giving effect to the illegal sale, in conspiracy with the co-defendants", "verified",
     "Engr. Erwin Balane, one of the children of Gloria and Efren, is being impleaded for acting in "
     "conspiracy with his co-defendants by using his official capacity, authority and influence as the "
     "Municipal Engineer of Mercedes to perform acts intended to validate and give effect to the illegal sale"),
]
# (cause, against, basis, provenance, source_excerpt) — from the complaint caption + body (doc 781).
CAUSES = [
    ("Accion reivindicatoria — recovery of ownership and possession of the 2,587 sqm subject property",
     "all defendants",
     "Real action for the co-ownership; the sale among defendants is null and void for being entered "
     "into without the co-owners' knowledge and consent (Art. 487 Civil Code standing).", "verified",
     "This is a real action praying from the recovery of the ownership and possession of the subject "
     "property ... the sale executed by and among the defendants is null and void"),
    ("Declaration of nullity of the 2016 Deed of Absolute Sale",
     "Gloria Balane (and the late Cesar de la Fuente)",
     "Cesar's 1992 SPA authorized only to 'negotiate', not to sell, and only to Llamanzares CTS "
     "holders; it was revoked 15 Aug 2005 — so the 2016 sale is void.", "verified",
     "his authority was limited ... explicitly only to “negotiate” for the sale of land, which does "
     "not include the authority to sell"),
    ("Cancellation of TCT 079-2021002126 and Declaration of Real Property ARP GR-2023-II-07-001-00256",
     "Gloria Balane",
     "Cancellation/nullification of all instruments emanating from the void sale, incl. the assailed "
     "title, the tax declaration, and the annotations on plaintiff's Torrens title.", "verified",
     "cancellation and nullification of all instruments and documents emanating from the void sale, "
     "including the tax declaration issued in the name of defendants Balane and the annotations"),
    ("Accounting and damages", "all defendants",
     "Accounting of the proceeds Cesar refused to remit to the co-owners, plus the award of damages.",
     "verified", "Accounting, and Damages"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    if not a.apply:
        print(f"[dry] {MATTER}: {len(PARTIES)} parties, {len(CAUSES)} causes, operative pleading doc:{OPERATIVE_DOC}.")
        return
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_parties (
        id serial PRIMARY KEY, matter_code text, entity_id int, party_name text, side text, role text,
        provenance_level text DEFAULT 'inferred_strong', source_doc_id int, source_excerpt text,
        created_at timestamptz DEFAULT now(), UNIQUE(matter_code, entity_id, side))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_causes (
        id serial PRIMARY KEY, matter_code text, cause text, against_parties text, basis text,
        provenance_level text DEFAULT 'inferred_strong', operative_doc_id int, source_excerpt text,
        created_at timestamptz DEFAULT now(), UNIQUE(matter_code, cause))""")
    for eid, name, side, role, prov, exc in PARTIES:
        cur.execute("""INSERT INTO matter_parties
            (matter_code,entity_id,party_name,side,role,provenance_level,source_doc_id,source_excerpt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (matter_code,entity_id,side)
            DO UPDATE SET role=EXCLUDED.role, party_name=EXCLUDED.party_name,
              provenance_level=EXCLUDED.provenance_level, source_doc_id=EXCLUDED.source_doc_id,
              source_excerpt=EXCLUDED.source_excerpt""",
            (MATTER, eid, name, side, role, prov, OPERATIVE_DOC, exc))
    for cause, against, basis, prov, exc in CAUSES:
        cur.execute("""INSERT INTO matter_causes
            (matter_code,cause,against_parties,basis,provenance_level,operative_doc_id,source_excerpt)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (matter_code,cause)
            DO UPDATE SET against_parties=EXCLUDED.against_parties, basis=EXCLUDED.basis,
              provenance_level=EXCLUDED.provenance_level, operative_doc_id=EXCLUDED.operative_doc_id,
              source_excerpt=EXCLUDED.source_excerpt""",
            (MATTER, cause, against, basis, prov, OPERATIVE_DOC, exc))
    stmt = (f"OPERATIVE PLEADING for {MATTER} = doc:{OPERATIVE_DOC} ('Latest Draft Complaint - Zschoche "
            f"v. Balane, et al.', MTC Mercedes). Defendants: Sps. Efren & Gloria Balane, Sps. Jomil & "
            f"Princess Balane Torralba (illegal possessors), and Engr. Erwin Balane (Municipal Engineer, "
            f"impleaded for using his office to validate the illegal sale). Causes: accion reivindicatoria, "
            f"nullity of the 2016 deed, cancellation of TCT 079-2021002126 + ARP, accounting & damages.")
    exc = ("SPOUSES EFREN BALANE and GLORIA BALANE, SPOUSES JOMIL TORRALBA and PRINCESS BALANE TORRALBA, "
           "and ENGR. ERWIN BALANE and all other person/s deriving rights from them ... Defendants.")
    cur.execute("SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s", (MATTER, stmt))
    if not cur.fetchone():
        cur.execute("""INSERT INTO matter_facts (matter_code,statement,fact_kind,source_kind,source_id,
                       excerpt,provenance_level,confidence,created_by,created_at)
                       VALUES (%s,%s,'structure','doc',%s,%s,'verified',1.0,'cowork_source_read',now())""",
                    (MATTER, stmt, str(OPERATIVE_DOC), exc))
    cur.execute("SELECT side, count(*) FROM matter_parties WHERE matter_code=%s GROUP BY side", (MATTER,))
    sides = dict(cur.fetchall())
    cur.execute("SELECT count(*) FROM matter_causes WHERE matter_code=%s AND provenance_level='verified'", (MATTER,))
    print(f"[apply] {MATTER} deciphered from doc:{OPERATIVE_DOC} — {sides.get('defendant',0)} defendants, "
          f"{sides.get('plaintiff',0)} plaintiff(s), {cur.fetchone()[0]} verified causes (all cited).")


if __name__ == "__main__":
    main()
