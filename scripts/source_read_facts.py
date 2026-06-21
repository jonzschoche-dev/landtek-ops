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

    # ── Aug-12 north-star docs: the Judicial Affidavit (445), the SJ-pillars memo (452), and the
    #    Defendants' Manifestation (1088) — the live Summary-Judgment fight, all legible from email. ──
    ("MWK-CV26360", 445,
     "Doc 445 is the JUDICIAL AFFIDAVIT (sworn direct testimony) of Jonathan Paul Zschoche in CV-26360, "
     "examined by Atty. Bonifacio T. Barandon Jr. — the testimony Jonathan gives as Patricia's witness.",
     "JUDICIAL AFFIDAVIT ... I, JONATHAN PAUL ZSCHOCHE ... I am being examined by Atty. Bonifacio T. "
     "Barandon, Jr."),
    ("MWK-CV26360", 445,
     "⚠ DATE DISCREPANCY (plaintiff's own documents): the Judicial Affidavit (doc 445) states the "
     "assailed Deed of Absolute Sale to Gloria Balane was executed on SEPTEMBER 26, 2019 — but the "
     "complaint (doc 781 ¶9) and Patricia's adverse-claim affidavit (doc 419) both state SEPTEMBER 29, "
     "2016. Two different sale dates in the plaintiff's filings; must be reconciled before trial.",
     "Cesar De La Fuente maliciously sold the subject property to Defendant Gloria Balane, who was not a "
     "qualified buyer under the terms of the aforesaid SPA, on September 26, 2019, executing the assailed "
     "Deed of Absolute sale to that effect"),
    ("MWK-CV26360", 452,
     "Procedural posture (CV-26360): plaintiff's Motion to Render Summary Judgment was filed 24 April "
     "2026; the Defendants' Comment/Opposition was filed 4 May 2026 by defense counsel Atty. Ronald A. "
     "Ramos; the plaintiff's Reply deadline was Monday 11 May 2026.",
     "our Motion to Render Summary Judgment filed April 24, 2026 ... the Defendants' Comment/Opposition "
     "filed by Atty. Ronald A. Ramos on May 4, 2026 ... The deadline is therefore Monday, May 11, 2026"),
    ("MWK-CV26360", 452,
     "The CV-26360 summary-judgment motion rests on Rule 35's two pillars — (1) no genuine issue of "
     "material fact and (2) movant entitled to judgment as a matter of law — supported by Laqui Sr. v. "
     "Sagun (G.R. 271967, 2024), Calubaquib v. Republic (G.R. 170658), Philippine Business Bank v. Chua "
     "(G.R. 178899), and Ley Construction v. Union Bank (G.R. 133801).",
     "Rule 35 ... summary judgment is proper when two conditions concur: PILLAR ONE: NO GENUINE ISSUE OF "
     "MATERIAL FACT ... PILLAR TWO: MOVING PARTY IS ENTITLED TO JUDGMENT AS A MATTER OF LAW"),
    ("MWK-CV26360", 452,
     "A Certified True Copy of the 1992 SPA was secured from the Registry of Deeds, Camarines Norte "
     "(Ref. No. 2025003039, 21 May 2025) — the documentary proof of the SPA's limited terms for the SJ.",
     "the Certified True Copy of the Special Power of Attorney (Registry of Deeds, Camarines Norte, Ref. "
     "No. 2025003039, May 21, 2025)"),
    ("MWK-CV26360", 1088,
     "Doc 1088 is the DEFENDANTS' Manifestation with Tender of Excluded Evidence: Gloria H. Balane's "
     "Judicial Affidavit was EXCLUDED at pre-trial because the copy presented was a scanned copy with a "
     "consular notarization (Gloria being in Canada); the defense tenders it under Rule 132 Sec 40 and "
     "alternatively moves to admit the original.",
     "the exclusion and denial of admission of the Judicial Affidavit of defendant GLORIA H. BALANE "
     "during pre-trial on the ground that the copy then presented was a scanned copy, including the "
     "consular notarization made because defendant Gloria Balane is in Canada"),
    ("MWK-CV26360", 1088,
     "CV-26360 is governed by the Rules on SUMMARY PROCEDURE (constraining dilatory/prohibited "
     "pleadings) — confirmed in the Defendants' Manifestation.",
     "this case is governed by Summary Procedure, defendants are mindful of the policy against delay and "
     "the prohibition against dilatory or prohibited pleadings"),
    ("MWK-CV26360", 1088,
     "THE DEFENSE THEORY (Gloria Balane's tendered Judicial Affidavit): the Balane family's long "
     "possession, prior rental/payment arrangements, Gloria's GOOD-FAITH reliance on the 1992 SPA to "
     "Cesar de la Fuente, ABSENCE OF PRIOR NOTICE OF THE REVOCATION, taxes paid, improvements, and no "
     "fraud/bad faith — the buyer-in-good-faith defense the SJ must defeat.",
     "Gloria Balane's good-faith reliance on the 1992 Special Power of Attorney in favor of Cesar M. de "
     "la Fuente, the absence of prior notice of revocation"),
    ("MWK-CV26360", 1088,
     "Defendant Gloria H. Balane is the registered owner named in TCT 079-2021002126 (2,587 sqm) and is "
     "currently in Canada — material to her availability as a defense witness.",
     "Defendant Gloria H. Balane is the registered owner named in Transfer Certificate of Title No. "
     "079-2021002126, covering the 2,587-square-meter property ... defendant Gloria Balane is in Canada"),

    # ── doc 701 = the operative ARTA-1891 referral wrapper (its substance was never source-read; the
    #    matter's verified facts had been peripheral DILG-orientation boilerplate). Grounds 1891 in itself. ──
    ("MWK-ARTA-1891", 701,
     "ARTA Case CTN SL-2026-0423-1891 is a complaint by Jonathan Paul Zschoche (AIF for Patricia Keesey "
     "Zschoche) against the LGU of Mercedes, over alleged procedural/institutional issues in the "
     "proceedings of the Mercedes Committee on Anti-Red Tape (CART) on 6 April 2026 and the resulting "
     "CART Resolutions Nos. 1–6, Series of 2026.",
     "the complaint filed by Mr. Jonathan Paul Zschoche, on behalf of Ms. Patricia Keesey Zschoche, "
     "against the Local Government Unit (LGU) of Mercedes. The complaint pertains to the alleged "
     "procedural and intuitional issues relative to the proceedings conducted by the Committee on "
     "Anti-Red Tape (CART) of the Municipality of Mercedes, Camarines Norte on 06 April 2026, and the "
     "resulting CART Resolutions No. 1 through 6, Series of 2026"),
    ("MWK-ARTA-1891", 701,
     "ARTA received the complaint by email on 23 April 2026 and, finding the relief best addressed by the "
     "DILG, referred it under R.A. 11032 §17(d) (ARTA's power to refer complaints to the appropriate "
     "agency) — Referral CTN SL-2026-0423-1891 dated 4 May 2026.",
     "the attached complaint from Jonathan Paul Zschoche, which was received by the Authority through "
     "email on 23 April 2026 ... in accordance with Section 17 (d) of Republic Act No. 11032 ... which "
     "provides that the Authority has the power to refer complaints to the appropriate agency, we are "
     "hereby referring the above complaint to your office"),
    ("MWK-ARTA-1891", 701,
     "On 6 May 2026 the DILG-CART endorsed the ARTA referral to the Regional Director, DILG Region V "
     "(Atty. Arnaldo E. Escober, Jr.), requesting appropriate action and a report to DILG-CART on or "
     "before 14 May 2026.",
     "MEMORANDUM TO: ATTY. ARNALDO E. ESCOBER, JR., CESO Ill Regional Director, DILG Region V SUBJECT: "
     "ARTA REFERRAL OF COMPLAINT (CTN SL-2026-0423-1891) DATE: 06 May 2026 ... submit a report on the "
     "actions taken to the DILG-CART ... on or before 14 May 2026"),
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
