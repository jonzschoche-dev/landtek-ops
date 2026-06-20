#!/usr/bin/env python3
"""source_read_facts.py — Phase 1: write VERIFIED facts read FROM source documents (cited). $0.

The comprehension is done by the Cowork subscription (reading the OCR'd text in `documents`); this
tool writes the result as gate-compliant verified facts — each carries source_kind=doc + a resolving
source_id + the quoted excerpt (the span), so it passes the provenance write-gate (deploy_504). This
is how 'inferred/operator' becomes 'verified': by reading the source and citing it, never by assertion.

Idempotent (skips a statement already present for the matter). The FACTS list below is the auditable
record of exactly what was read and from where.

  python3 scripts/source_read_facts.py --apply
"""
import argparse
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

# (matter_code, doc_id, statement, excerpt_quoted_span) — each READ from the cited document.
FACTS = [
    # ── doc 419 = AFFIDAVIT OF ADVERSE CLAIM of Patricia Keesey Zschoche (Feb 2023), NOT the
    #    complaint despite the filename. The void-chain narrative, in the affiant's own words. ──
    ("MWK-CV26360", 419,
     "Patricia Keesey Zschoche is one of three children of the late Mary Worrick Keesey (died in "
     "America 17 March 1988); her sisters are Geraldine Keesey Hoppe and Marcia Ellen Keesey.",
     "I am one of the three (3) children of the late Mary Worrick Keesey, who died in America last "
     "March 17, 1988. My two (2) other sisters are Geraldine Keesey Hoppe and Marcia Ellen Keesey"),
    ("MWK-CV26360", 419,
     "On 16 March 1992 the heirs granted Cesar de la Fuente only LIMITED authority — to perfect the "
     "sale of portions to persons who already held a Contract to Sell or had made down/partial "
     "payment to Ben Llamazares (the prior administrator).",
     "we granted on March 16, 1992 Mr. Cesar de Fuente limited authority to perfect the sale of "
     "portions of said property in favor of those who already possessed Contract to Sell, or have "
     "had made down/partial payment to Ben Llamazares, our previous administrator"),
    ("MWK-CV26360", 419,
     "On 15 August 2005 the heirs designated Ida M. Buenaventura as new attorney-in-fact and "
     "disowned/revoked any SPA given to other persons (including de la Fuente), effective 15 Aug "
     "2005; de la Fuente was well aware of this revocation.",
     "we designate on August 15, 2005 a new attorney-in-fact in the person of Ida M. Buenventura ... "
     "we disowned and rendered without force and effect any SPA given to persons other than Ms. "
     "Buenaventura, effective August 15, 2005. Mr. De La Fuente was well aware of this move"),
    ("MWK-CV26360", 419,
     "On 29 September 2016 de la Fuente sold 2,587 sqm to Gloria Balane for P250,000 (Entry No. "
     "2021003235, 23 Nov 2021, in TCT No. T-52540) — executed beyond the 2005 revocation, therefore "
     "unauthorized and null and void.",
     "that sale he made on September 29, 2016 in favor of Gloria Balane conveying unto the latter "
     "2,587 for P250,000.00, per Entry No. 2021003235 dated November 23, 2021 ... in TCT No. T-52540"),
    ("MWK-CV26360", 419,
     "On 28 March 2017 de la Fuente executed a Deed of Confirmation confirming the sale to Gloria "
     "Balane (Entry No. 2021003235).",
     "That on March 28, 2017, Mr. De La Fuente also executed a Deed of Confirmation, confirming the "
     "said sale made in favor of Gloria Balane, per Entry No. 2021003235"),
    ("MWK-CV26360", 419,
     "The Balane-acquired portion is now covered by a SEPARATE title, TCT No. 079-2021002126, in the "
     "name of Gloria Balane (note: 079-2021002126, the operative Balane title number).",
     "now covered by a separate title identified as TCT No. 079-2021002126 in the name of Gloria Balane"),
    ("MWK-CV26360", 419,
     "DOCUMENT IDENTITY CORRECTION: doc 419, filenamed 'Exhibit I - Complaint - Civil Case 26-360', "
     "is in fact the AFFIDAVIT OF ADVERSE CLAIM of Patricia Keesey Zschoche (subscribed Makati, Feb "
     "2023) plus an OCR-garbled copy of TCT T-4497 — it is NOT the operative complaint. The complaint "
     "/ full defendant roster (incl. Engr. Erwin Balane's actual role) must be read from another doc.",
     "AFFIDAVIT OF ADVERSE CLAIM ... I, PATRICIA KEESEY ZSCHOCHE ... SUBSCRIBED AND SWORN TO before "
     "me ... of February, 2023 at Makati City"),

    # ── doc 384 = the ARTA-0747 COMPLAINT-AFFIDAVIT (Jonathan v. Mayor Pajarillo, RA 11032), NOT a
    #    generic complaint. Clean OCR; the operative pleading for MWK-ARTA-0747. ──
    ("MWK-ARTA-0747", 384,
     "ARTA Case CTN SL-2025-1021-0747 is Jonathan Zschoche (Attorney-in-Fact for heir Patricia Keesey "
     "Zschoche) v. Mayor Alexander L. Pajarillo of Mercedes, for violations of R.A. 11032 Sec. 21(b), "
     "21(d) and 21(e).",
     "JONATHAN ZSCHOCHE ... Attorney-in-Fact for Patricia Keesey Zschoche, an Heir of Mary Worrick "
     "Keesey), Complainant, For: Violations of R.A. 11032 Sec. 21(b), 21(d), and 21(e) - versus - "
     "HON. ALEXANDER L. PAJARILLO Municipal Mayor"),
    ("MWK-ARTA-0747", 384,
     "On 1 Oct 2025 Jonathan requested the LGU release Building Permits + Tax Declarations re Antonio "
     "Teope (the Mayor's Chief of Staff) and Miguel Baliza (Draftsman in the Municipal Assessor's "
     "Office), or a written statement of their non-existence.",
     "The request sought the release of the identified records (Building Permits and Tax Declarations "
     "regarding Antonio Teope, Personal Assistant and Chief of Staff to the Mayor, and Miguel Baliza, "
     "Draftsman in the Municipal Assessor's Office)"),
    ("MWK-ARTA-0747", 384,
     "On 6 Oct 2025 Municipal Engineer ERWIN H. BALANE refused/declined to act on the request absent "
     "an SPA (admitted in the Engineer's Explanation) — basis of the Sec. 21(b) additional-requirement "
     "charge. (Erwin Balane's role HERE is Municipal Engineer; distinct from his CV-26360 role.)",
     "Oct 6, 2025 Municipal Engineer Erwin H. Balane refused/declined to act absent SPA "
     "(admitted/confirmed in Engineer's Explanation)"),
    ("MWK-ARTA-0747", 384,
     "On 9 Oct 2025 Mayor Pajarillo imposed an 'All-Heirs SPA' requirement not in the Citizen's Charter "
     "— a prohibited additional requirement under R.A. 11032 Sec. 21(b).",
     "On October 9, 2025, Respondent Mayor Alexander L. Pajarillo issued a written response ... imposed "
     "an additional requirement not found in the Citizen's Charter ... all legal heirs execute a "
     "Special Power of Attorney (SPA)"),
    ("MWK-ARTA-0747", 384,
     "The Citizen's-Charter processing deadline (Simple Transaction, 3 working days) expired 6 Oct 2025 "
     "with no disposition — the Sec. 21(e) failure-to-render-service charge.",
     "this is a 'Simple Transaction' mandated to be completed within three (3) working days. The "
     "deadline expired on October 6, 2025. No final disposition ... has been made as of the filing"),
    ("MWK-ARTA-0747", 384,
     "Legal ground asserted: co-owners have independent standing under Art. 487 Civil Code to protect "
     "the property (Heirs of Julian Dela Cruz v. Heirs of Alberto Cruz, G.R. No. 162890, 2005) — "
     "defeating the All-Heirs-SPA demand.",
     "co-owners have independent standing under Article 487 of the Civil Code to bring actions for the "
     "protection of the property ... Heirs of Julian Dela Cruz v. Heirs of Alberto Cruz, G.R. No. 162890 (2005)"),

    # ── CV-6839 (the ₱20M just-compensation case). The Commissioner's valuation report is in the
    #    corpus, but the AWARD FIGURE itself sits in OCR-corrupted tables — so the ₱20M stays
    #    OPERATOR-asserted (NOT faked into a verified fact). Only the clean valuation fact is verified. ──
    ("MWK-CV6839", 683,
     "Civil Case 6839 (just compensation, RTC Camarines Norte): the Commissioner's valuation report "
     "was submitted to the court by Commissioner Rodolfo M. Yago on 18 November 2015. NOTE: the award "
     "AMOUNT (operator-stated ~₱20M+) is in valuation tables whose OCR is corrupted/unreadable — NOT "
     "yet citable; it must be verified from the court's decision/order or a clean re-OCR.",
     "WHEREFORE, the undersigned hereby submits the foregoing valuation for consideration and "
     "appreciation of the Honorable Court. RODOLFO M. YAGO ... November 18, 2015"),

    # ── doc 781 = the REAL CV-26360 complaint ('Latest Draft Complaint - Zschoche v. Balane, et al.',
    #    from the Barandon email thread). Legible. Foundational facts beyond the party/cause structure. ──
    ("MWK-CV26360", 781,
     "The CV-26360 subject property is a 2,587 sqm portion of TCT T-52540 (28,891 sqm, Brgy. San Roque, "
     "Mercedes), now embraced by the assailed TCT No. 079-2021002126 and Declaration of Real Property "
     "ARP No. GR-2023-II-07-001-00256 in Gloria Balane's name; assessed value Php257,670 (within MTC "
     "Mercedes jurisdiction).",
     "a portion of the above-mentioned parcel of land measuring 2,587 square meters and which currently "
     "embraced by Transfer Certificate of Title No. 079-2021002126 ... and Declaration of Real Property "
     "No. GR-2023-II-07-001-00256 ... The assessed value of the subject property is Php257,670.00"),
    ("MWK-CV26360", 781,
     "The 16 March 1992 SPA authorized Cesar de la Fuente only to 'negotiate for the sale ... in favor "
     "of third persons in possession of CONTRACTS TO SELL executed by the previous administrator, MR. "
     "BEN LLAMANZARES and/or to those who have paid their down-payments or made partial payments' — a "
     "power to negotiate, NOT a power to sell (the SJ kill-shot, now from the operative complaint).",
     "authorizing the latter to “negotiate for the sale of the [property] in favor of third persons in "
     "possession of CONTRACTS TO SELL executed by the previous administrator, MR. BEN LLAMANZARES "
     "and/or to those who have paid their down-payments or have made partial payments therefor"),

    # ── doc 376 = Yuzon Law Office memo on CV-6839 (legible email attachment). Finally gives the real
    #    CV-6839 identity/parties/theory — the system knew it only as 'the ₱20M case'. (The award FIGURE
    #    is in doc 351's valuation tables, still tabular — the ₱20M stays operator until cleanly read.) ──
    ("MWK-CV6839", 376,
     "Civil Case 6839 is 'Heirs of Mary Worrick Keesey v. The Department of Agrarian Reform and "
     "LandBank of the Philippines' — a just-compensation / agrarian-reform expropriation case (RTC "
     "sitting as Special Agrarian Court), NOT a private dispute.",
     "Civil Case No. 6839 titled 'Heirs of Mary Worrick Keesey v. The Department of Agrarian Reform "
     "and LandBank of the Philippines'"),
    ("MWK-CV6839", 376,
     "Preliminary payments of just compensation were made to the heirs of Mary Worrick Keesey through "
     "their attorney-in-fact Cesar M. de la Fuente — the SAME de la Fuente later central to the void "
     "Balane sale in CV-26360; per the memo these payments do not absolve the government of delay liability.",
     "there were preliminary payments to the heirs of Mary Worrick Keesey through their attorney-in-fact, "
     "Cesar M. De La Fuente, does not in any way absolve, relieve, or exempt the government from liability "
     "for the delay"),
    ("MWK-CV6839", 376,
     "The SPA dated 17 May 1999 (Geraldine Keesey Hoppe, Patricia Keesey Zschoche, Marcia Ellen Keesey "
     "→ Ida M. Buenaventura) did NOT authorize Buenaventura to represent the heirs in CV-6839; DAR raised "
     "this in a Motion for Reconsideration dated 29 Dec 1999. Her authority came only via the separate "
     "SPA dated 15 August 2005 (the same revocation-SPA at the heart of CV-26360).",
     "Nowhere did it state in the said Special Power of Attorney that Ida M. Buenaventura was authorized "
     "to represent the principals in Civil Case No. 6839. Such authority was only granted to Ida M. "
     "Buenaventura only through the execution of a separate Special Power of Attorney dated 15 August 2005"),
    ("MWK-CV6839", 376,
     "Under R.A. 6657 (CARL), just compensation to landowners is paid in cash AND bonds; the landowner "
     "cannot insist on cash alone — relevant to how any CV-6839 award would be satisfied.",
     "the Comprehensive Agrarian Reform Law provides that just compensation to landowners shall be paid "
     "in cash and bonds. Accordingly, the landowner cannot insist to be paid in cash alone"),

    # ── doc 967 = the ARTA RESOLUTION on CTN SL-2025-1021-0747 (legible). A real outcome for ARTA-0747. ──
    ("MWK-ARTA-0747", 967,
     "ARTA issued a Resolution on CTN SL-2025-1021-0747 REFERRING the complaint to the CART/Agency under "
     "the R.A. 11032 referral procedure (not a merits ruling), signed by the Regional Chief, ARTA "
     "Southern Luzon.",
     "during the period that the Complaint is with the CART/Agency, the Complainant may, at any time, "
     "submit a Request for Termination of Referral to ARTA"),
    ("MWK-ARTA-0747", 967,
     "Zschoche submitted the Initial Complaint in ARTA CTN SL-2025-1021-0747 on 20 October 2025, charging "
     "Mayor Pajarillo with imposing additional requirements and failure to render service within the "
     "prescribed processing time.",
     "On 20 October 2025, Zschoche submitted an Initial Complaint charging Hon. Pajarillo for imposing "
     "additional requirements and for his failure to render government service within the prescribed processing"),
    ("MWK-ARTA-0747", 967,
     "Grounds on which the complainant may request Termination of Referral include (a) the official "
     "complained-of is the CART approving Chairperson / Head of Agency, and (c) lapse of 20 working days "
     "from referral with no resolution — both live triggers for escalating ARTA-0747.",
     "The government official complained of is the approving Chairperson of the CART or the Head of "
     "Agency; ... Lapse of twenty working (20) days or any extension from the time of the referral and "
     "no resolution is met"),
    ("MWK-ARTA-0747", 967,
     "Mayor Alexander Pajarillo — the respondent — is identified in the Resolution as the CART "
     "Chairperson (copy-furnished as 'CART Chairperson / Mayor'); the respondent thus heads the very "
     "body the complaint is referred to (squarely Termination-of-Referral ground (a)).",
     "HON. ALEXANDER PAJARILLO CART Chairperson Mayor"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN); c.autocommit = True
    cur = c.cursor()
    written = skipped = failed = 0
    for mc, doc_id, stmt, excerpt in FACTS:
        cur.execute("SELECT 1 FROM matter_facts WHERE matter_code=%s AND statement=%s", (mc, stmt))
        if cur.fetchone():
            skipped += 1; continue
        if not a.apply:
            written += 1; continue
        try:
            cur.execute("""INSERT INTO matter_facts
                (matter_code,statement,fact_kind,source_kind,source_id,excerpt,provenance_level,confidence,created_by,created_at)
                VALUES (%s,%s,'source_read','doc',%s,%s,'verified',1.0,'cowork_source_read',now())""",
                (mc, stmt, str(doc_id), excerpt))
            written += 1
        except psycopg2.Error as e:
            failed += 1
            print(f"  ✗ doc:{doc_id} rejected by gate: {str(e).splitlines()[0][:90]}")
    verb = "wrote" if a.apply else "would write"
    print(f"[source-read] {verb} {written} verified facts · {skipped} already present · {failed} gate-rejected")
    cur.execute("SELECT count(*) FROM matter_facts WHERE provenance_level='verified'")
    print(f"[source-read] total verified facts now: {cur.fetchone()[0]}")


if __name__ == "__main__":
    main()
