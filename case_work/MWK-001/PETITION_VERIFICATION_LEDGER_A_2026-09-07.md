# PETITION VERIFICATION LEDGER A — adversarial source audit
**Target:** `case_work/MWK-001/DEMAND_PROVINCIAL_OVERSIGHT_2026-09.md` — Cover Letter + Petition Parts I, II, III, V, VII, VIII
**Auditor:** truth-qa-gate · **Date:** 2026-09-07 · **Matter:** MWK-001 only
**Verdict: FAIL — DO NOT SERVE.** 8 WRONG · 8 UNSUPPORTED · 6 UNVERIFIED-PRIMARY.

**Method.** Every assertion re-derived from primary sources only: the live corpus (`documents`,
`gmail_messages`, `legal_chunks`), the OCR'd DILG 2 Sep packet, and `Binder1.pdf` (found at
`/Users/jonathanzschoche/Downloads/Binder1.pdf`, 27pp image-only, OCR'd — it contains the primary
1 Sep 2026 Mayor and Olaguera replies, the 24 Jul 2026 Mayor letter, the 26 Aug 2026 DILG letter and
the 23 Jun 2026 CSC letter). The `# INTERNAL` provenance table was **not** relied on and was itself
found to contain errors (noted at the end).

Grades: **V**=verified · **P**=partial · **U**=unsupported · **W**=wrong (source contradicts) ·
**UP**=unverified-primary (only a secondary/self-authored memo carries it).

---

## A. COVER LETTER

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-1 | Cover, addressee | Hon. Ricarte R. Padilla, Provincial Governor | **V** | Binder1 pg-19 (CSC ltr); Binder1 pg-3 (PPDO transmittal); doc 228 | "RICARTE R. PADILLA / Governor" | Name and office confirmed on two government instruments. |
| C-2 | Cover ¶1 | Governor received Jonathan at the Capitol; offered a letter to Mayor Alex; photograph taken | **UP** | none — Jonathan's own account | — | No document. Acceptable as first-person narrative, but it is the letter's opening credibility anchor. Keep as personal recollection; do not let it drift into "of record". |
| C-3 | Cover ¶2 | Patricia appealed to the Governor's Office; received 29 Aug 2023 | **V** | docs 228, 1065 | "OFFICE OF THE GOVERNOR PROVINCIAL CAPITOL DAET… RECEIVED"; "29 August 2023" | Both bear the Office of the Governor received stamp. |
| C-4 | Cover ¶2 | The appeal concerned the Province's realty-tax amnesty | **V** | doc 1065 | "the Amnesty being extended by the Provincial Government on realty tax which will expire on September 30, 2023 and Section 270" | — |
| C-5 | Cover ¶2 | "provincial oversight got the taxes updated" | **UP** | internal note only; Macale 21 Jul 2026 says payments "since 2023" | b-4: "every time he made payment since 2023 up to present" | No document ties the tax update to *provincial* action. Causation is inferred. |
| C-6 | Cover ¶2 | "That is the one time provincial supervision has been exercised here" | **U** | none | — | Absolute claim; no source establishes the Province acted on the 2023 letter. See C-5. |
| C-7 | Cover ¶4 | "The Provincial Legal Officer has held my complaints since March" | **P** | gmail 107, 103 | to "Provincial Government Camarines Norte <pgcamarinesnorte@gmail.com>" | DILG's March referrals went to the **Provincial Government** generally. The PLO is first addressed in DILG's 2 Sep 2026 letter ("ATTN: PROVINCIAL LEGAL OFFICER"). Attributing custody to the PLO since March is inference. |
| C-8 | Cover ¶4 | DILG asked him on 2 September to answer me directly | **V** | DILG 2 Sep 2026 ltr to Governor (`DILG_enclosures/source/…Relucio_2026-09-02…pdf` p.2) | "may we respectfully request your Office to provide him directly with an update on the actions taken" | — |
| C-9 | Cover ¶4 | Provincial Assessor promised in writing on 1 July that all requested relief would be replied with; took the titles; went silent | **V** | doc 1623 / gmail 98305 | "Rest assured that all your requested relief will be replied with upon my return on Monday, July 6, 2026" | Titles furnished 2 Jul (gmail 99969). No later inbound from that sender in `gmail_messages` (mirror current to 2026-09-07). |
| C-10 | Cover ¶4 | Provincial Treasurer received the 13 July protest and never wrote me a line | **P** | gmail 103665; BLGF PDF b-5, b-6 | b-6 Gmail print bears "OFFICE OF THE GOVERNOR PROVINCIAL [CAPITOL] DAET… RECEIV[ED]" | Receipt by the Province ✓ and Manlapaz acted 17 Jul ✓. "Never wrote me" ✓ (zero inbound rows). But the filing went to the shared `pgcamarinesnorte@gmail.com`, not to Manlapaz directly — see C-33. |
| C-11 | Cover ¶4 | ARTA focal sent the complaint about the Mayor's own committee to the Mayor, with the Governor's signature under "Noted" | **V** | Binder1 pg-3 (PPDO 23 Jun 2026) | "for your information, reference and appropriate actions"; "Noted / RICARTE R. PADILLA / Governor" | Strongest fact in the letter. |
| C-12 | Cover ¶5 | The Mayor told me himself that no one can stop him; "Mercedes vote" advice | **UP** | none — Jonathan's account | — | Correctly flagged internally as needing date/place. No document. |
| C-13 | Cover ¶5 | "Nothing your Office has done in fifteen months" | **V** | arithmetic | 15 May 2025 → 7 Sep 2026 = 15 months 23 days | Sound **if** anchored to 15 May 2025. Ambiguous because Part II's ledger opens at 29 Aug 2023 (36 months). |
| C-14 | Cover ¶6 | Proceeding pending before the OP; further petition filed this week | **P** | doc 702 | "05 May 2026 … 050526-MRO-234187 … Petition for Supervisory Review and Corrective Action over the Anti-Red Tape Authority's Resolution dated 07 April 2026" | It is a review of an **ARTA resolution** in the Balane dockets (0690/0792), not a general proceeding on the Municipality's conduct. See C-58. |
| C-15 | Cover ¶6 | Code lists "gross negligence, or dereliction of duty" as a disciplinary ground | **V** | `legal_chunks` id 11 (RA 7160 §60) | "(c) Dishonesty, oppression, misconduct in office, gross negligence, or dereliction of duty" | Verbatim. |
| C-16 | Cover ¶6 | A complaint against a governor goes to the Office of the President | **V** | `legal_chunks` id 12 (§61(a)) | "A complaint against any elective official of a province … shall be filed before the Office of the President" | — |
| C-17 | Cover ¶7 | Annex "R" lists **thirty-five** records | **V** | `RECORDS_RELEASE_SCHEDULE_2026-09.md` | 35 numbered rows counted | Petition is right; the INTERNAL table's "36 rows" is the stale figure. |
| C-18 | Cover ¶7 | "Mercedes has released none in full" | **UP** | `RECORDS_RELEASE_SCHEDULE_2026-09.md` §G | — | Corpus-derived scoreboard in a working memo; not independently re-derived here. |

---

## B. PART I — PRELIMINARY STATEMENT

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-19 | I ¶1 | "For fifteen months the Province … has held both the mandate and the written notice" | **P** | arithmetic | 15 May 2025 → 7 Sep 2026 = 15m 23d | Defensible from 15 May 2025, but Part II's own first row is 29 Aug 2023. Anchor it explicitly or the addressee will read it as an error. |
| C-20 | I ¶1 | Province has not issued one written directive to Mercedes | **V** | negative check | no responsive document or email of record | Consistent with DILG's 2 Sep letter ("we have not received any correspondence specifically indicating the action taken"). |

---

## C. PART II — THE PROVINCE'S OWN LEDGER

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-21 | II row 1 | 29 Aug 2023 letters received; no response of record | **V** | docs 228, 1065 | received stamp, above | — |
| C-22 | II row 2 | 15 May 2025 letter to Governor Padilla re amnesty parity | **V** | doc 365 (`2025-05-15_letter_to_governor_padilla.pdf`) | index item 1: "Letter to Governor Dong Padilla — Request to compel the LGU to offer the same amnesty extended to those who have been transferring family properties illegally" | Note doc 365 is a **compilation with a contents index**, and the index's explicit "May 15, 2025" date is attached to item 5, the letter to the **Mayor**. Confirm the Governor letter's own date on the paper before service. |
| C-23 | II row 2 | SPA condition "represented to me at the time as issued **on the direction of the Provincial Legal Officer**" | **UP** | doc 365 index item 3 | "Treasurer was allegedly under the direction of the Provincial Legal Officer." | Source is Jonathan's own compilation index and says "**allegedly**" — it does not say who represented it, or when. The hedge is right; the sourcing is self-referential. Prayer VI-A-4 rests on this. |
| C-24 | II row 3 | DILG referrals of 16 and 17 Mar 2026 to the Provincial Government, with those titles | **V** | gmail 107 (2026-03-16), gmail 103 (2026-03-17) | subjects "REFERRAL OF REQUESTS/ISSUES RAISED BY MR JONATHAN ZSCHOCHE" / "LETTER FROM JONATHAN ZSCHOCHE REITERATING REQUEST"; both to `pgcamarinesnorte@gmail.com` | Titles and dates match exactly. |
| C-25 | II row 3 | "following **my letters of 13 and 17 March 2026 to the Governor**" | **U** | — | DILG 2 Sep ltr: "forwarded by this Office to your Office on March 13, 2026, March 17, 2026, and June 4, 2026" | 13 / 17 March are **DILG's forward dates**, not dates of letters by Jonathan to the Governor. No such letters found. The corpus forward is dated **16** March, not 13. |
| C-26 | II row 3 | Per DILG's 2 Sep letter the Province "referred [the complaints] to LGU Mercedes on jurisdictional grounds" — placed against the **16–17 Mar** row | **W** | DILG 2 Sep 2026 ltr to Jonathan, p.1 | "we have **not received any correspondence** specifically indicating the action taken on the aforementioned letters. **However, in our subsequent memorandum dated June 4, 2026** … the Provincial Government took action by reviewing your complaints and referring the same to the LGU of Mercedes" | **Event mis-attribution.** DILG says the opposite of the petition's row: it has *no* information on the March letters, and attributes the referral to the **4 Jun** memo. The petition's rows 3 and 4 are inverted — row 4 (4 Jun) reads "No response of record" when that is the one item DILG says drew action. |
| C-27 | II row 5 | ARTA Referral CTN SL-2026-0423-1891 transmitted 23 Jun 2026 by the Provincial ARTA Focal to Mayor Pajarillo for "appropriate actions", Noted by Governor Padilla | **V** | Binder1 pg-3 | "June 23, 2026 … HON. ALEXANDER L. PAJARILLO … for your information, reference and appropriate actions"; "Noted / RICARTE R. PADILLA / Governor" | Focal is PPDC/ARTA Focal Person of the Provincial Planning and Development Office. |
| C-28 | II row 5 | The CART is "**chaired by the Mayor**" | **V** | Binder1 pg-19 (CSC 23 Jun 2026); doc 711; docs 712–716 | "with Hon. Alexander Pajarillo, in his capacity as the Municipal Mayor **and as the CART Chairperson**"; doc 711: "Hon. Alexander Pajarillo - Municipal Mayor/CART Chairperson" | — |
| C-29 | II row 6 | Magana email of 1 July 2026, quoted | **V** | doc 1623 / gmail 98305 | "Rest assured that all your requested relief will be replied with upon my return on Monday, July 6, 2026" | Verbatim. |
| C-30 | II row 6 | Requested certified copies of T-4497, T-32911, Psd-12802 "for our verification in the tax mapping records"; furnished 2 July | **V** | doc 1623 | "kindly submit to us certified copy of Title TCT-T-4497 and TCT-T-32911 and Survey Plan Psd-12802 **for our verification in the tax mapping records**" | Verbatim; furnished by gmail 99969 (2 Jul 2026). |
| C-31 | II row 6 | "more than nine weeks after a written commitment" | **V** | arithmetic | 1 Jul → 7 Sep 2026 = 68 days = 9 wks 5 days | Conservative and true. |
| C-32 | II row 7 | 13 Jul 2026 Formal Protest, ARP No. 001-00249, ₱14,391.50, to Prov. Treasurer + BLGF R5 | **V** | gmail 103665; doc 2929; BLGF b-4 | subject "…ARP No. 001-00249 / PHP 14,391.50"; b-4: "short tax of … (Php 14,391.50) for FY2026" | — |
| C-33 | II row 7 | "with **nineteen** enumerated questions" | **W** | doc 2929 (the filed protest) | "II. THREE RECORDS AND DETERMINATIONS REQUIRED" (items 1–3); "III. QUESTIONS FOR INDEPENDENT SUPERVISORY ANSWER" — **A, B, C, D, E** | **The document has five lettered questions**, plus three determinations and five reliefs. There is no set of nineteen. The addressee holds this document. Repeated at C-52 and in Prayer VI-C-1. |
| C-34 | II row 7 | Prov. Treasurer asked the Municipal Treasurer for explanation (17 July); Municipal Treasurer answered the Provincial Treasurer (21 July), not me | **V** | BLGF PDF b-5, b-4 | b-5: "July 17, 2026 … We would like to request your written explanation"; signed "DANTE E. MANLAPAZ, Provincial Treasurer". b-4: "In response to your letter dated July 17, 2026, and received by this office today July 21, 2026" | — |
| C-35 | II row 7 | "more than thirty-five working days" | **V** | arithmetic | 13 Jul → 7 Sep 2026 = 40 weekdays; less 21 & 31 Aug holidays = 38 | True and conservative. |
| C-36 | II row 8 | DILG's 2 Sep letter asks the PLO to "provide [me] directly" an update | **V** | DILG 2 Sep ltr to Governor | "provide him directly with an update on the actions taken" | — |
| C-37 | II ¶after | "**The Provincial Government of Camarines Norte has never sent me a single communication.**" | **W** | gmail 98305 (2026-06-30), gmail 105394 (2026-02-27) | Magana: "Rest assured that all your requested relief will be replied with…" — signed "MAXIMO P. MAGANA JR. REA / **Provincial Assessor**" | **Self-contradicted two rows above.** The Provincial Assessor is a Provincial Government office (LGC §472) and wrote twice. Zero rows from `pgcamarinesnorte@gmail.com` is true — but that is a narrower claim than the one made. |

---

## D. PART III — THE MUNICIPAL RECORD

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-38 | III.1 | Session records of 21/22 Jan, 4 Feb and 11 Feb 2026 "were requested on 11 February 2026, fees tendered" | **P** | doc 765; Binder1 pg-14 | doc 765: "your request dated February 11, 2026 for: 1. … the 30th Regular Session … dated January 21, 2026. 2. A Certified True Copy of the official minutes of the recent session…" | Doc 765 answers a request naming **only the 21 Jan session**. The three-session set appears first in the 18 Aug 2026 letter, indorsed 25 Aug (pg-14). "Fees tendered" has no source; pg-14 asks about "official fee assessments", i.e. none had been assessed. |
| C-39 | III.1 | SB Secretary refused on 5 Mar 2026 (**"certified copies only after review and adoption"**) | **W** | doc 765 | "the minutes **must first be reviewed and adopted by the body** before a Certified True Copy may be issued" | The quoted string does not appear in the document. Fabricated quotation (accurate paraphrase, wrongly punctuated as a quote). |
| C-40 | III.1 | On 1 Sep 2026 the same Secretary wrote the records "are being verified and consolidated" and will be released "upon … payment of prescribed fees" | **V** | Binder1 pg-25 (Olaguera, 1 Sep 2026) | "The requested records of the sessions dated 21/22 January, 4 February, and 11 February 2026 **are being verified and consolidated**. Certified copies … shall be made available upon compliance with the applicable requirements and **payment of prescribed fees**." | Both quotes verbatim. |
| C-41 | III.1 | "**seven months** after the request" | **P** | arithmetic | 11 Feb → 1 Sep 2026 = 6 months 21 days | Overstated. "Nearly seven months" is exact. |
| C-42 | III.1 | assessing no fee, stating no adoption status, producing nothing | **V** | Binder1 pg-25 | no fee figure, no per-session adoption status, no enclosure | — |
| C-43 | III.1 | §469(c)(5) makes furnishing a duty | **V** | `legal_chunks` id 2558 | "(5) Furnish, upon request of any interested party, certified copies of records of public character in his custody, upon payment to the treasurer of such fees as may be prescribed by ordinance" | — |
| C-44 | III.1 | §469(c)(7) "makes the office and records open to the public" | **P** | `legal_chunks` id 2558 | "(7) Keep his office and all **non-confidential** records therein open to the public during the usual business hours" | Drops "non-confidential" — hands the LGU a free rebuttal. |
| C-45 | III.1 | Street-naming matter "has already been acted upon … through its official proceedings", without number, date or minutes | **V** | Binder1 pg-25 ¶3 | "has already been acted upon and addressed by the Sangguniang Bayan through its official proceedings" | Verbatim; no resolution number given in the source. |
| C-46 | III.2 | On 24 Jul 2026 the Mayor asserted the Municipality's "legal title" to the Municipal Hall compound | **V** | Binder1 pg-18 (24 Jul 2026 Mayor ltr p.1) + pg-8 (p.2) | "presented Options for an Agreement asserting his claim over the property occupied by the Municipal Hall Compound. **Believing in the validity of its own legal title**, this LGU maintained that it will not enter into any agreement…" | **Not an operator-photo gap** — the primary letter is in Binder1. Update the INTERNAL ledger. |
| C-47 | III.2 | On 26 Aug 2026 DILG directed him, by Supplemental Indorsement, to "**cite the specific public instrument, deed, title, or expropriation record**" | **W** | Binder1 pg-20 (DILG 26 Aug 2026) | "Directing the Municipality to formally **identify and produce the specific public instrument, title, deed, or record** on which its 24 July 2026 written representation of 'legal title' rests" | Misquotation of a government directive: "cite" is not in the source, "expropriation record" is not in the source, and the noun order is altered. |
| C-48 | III.2 | On 1 Sep 2026 he answered "a valid Deed of Donation" — no date, donor, notarial details, acceptance resolution, registration or copy | **V** | Binder1 pg-2 (Mayor 1 Sep 2026, item 4) | "The LGU maintains its lawful claim over the Municipal Hall premises by virtue of **a valid Deed of Donation**." | Verbatim; the source supplies none of the listed particulars. |
| C-49 | III.2 | Only paper ever shown is an unsigned, unregistered photocopy | **UP** | Binder1 pg-4/pg-15 (Jonathan's 26 Aug 2026 letter) | "the only paper I have ever encountered … is a photocopy of an unsigned instrument — unregistered, never annotated on any certificate of title" | Jonathan's own statement. Fine as his averment; not an independent record. |
| C-50 | III.2 | TCT No. T-32911 "carries no annotation of any donation or municipal transfer" | **V** | doc 2539 (CTC of T-32911, 4pp) | Memorandum of Encumbrances holds only (i) the 1992 SPA to Cesar de la Fuente and (ii) the 1994 cancellation of the Rule 74 two-year lien; pp. 3–4 blank | Solid. Note the LGU's counter-record (doc 6908) asserts Lot 2-A was "donated to the LGU in 1953" — expect that response. |
| C-51 | III.2 | SB resolution of 13 March 1996 describes the acquisition as "proposed" | **V** | doc 389 (Res. No. 76-96) | "RESOLUTION CREATING AD HOC COMMITTEE TO TREAT MATTER WITH THE **PROPOSED** LEGAL ACQUISITION/DONATING OF PARCEL OF LAND OWNED BY MARY WORRICK KEES[E]Y ESTATE"; session held "ON MARCH 13, 1996" | Date and word both exact. |
| C-52 | III.3 | Asked for its basis, the Mayor on 1 Sep 2026 cited "**no law**, no ordinance, and no Citizen's Charter provision — only the general welfare clause, 'implied powers', and parens patriae" | **W** | Binder1 pg-27 / pg-2 (Mayor 1 Sep 2026, item 2) | "**Pursuant to Section 16 of the Local Government Code of 1991 (R.A. No. 7160)**, this LGU is vested with both express and necessarily implied powers…"; "Under the doctrine of parens patriae…" | Self-contradictory: LGC §16 **is** a law, and the same sentence concedes it. The quotes "implied powers" and parens patriae are sound. Recast as: cited no law *authorizing the requirement*, no ordinance, and no Citizen's Charter provision. |
| C-53 | III.3 | Reason given in writing: the representations "concern the very parcel of land upon which the Municipal Hall itself is situated" | **P** | Binder1 pg-2 (top) | page opens mid-sentence: "**Municipal Hall itself is situated.** Where an individual claims to act on behalf of an estate…" | The tail of the quote is verbatim; the head falls on the bottom line of pg-27, which OCR'd illegibly. **Re-read the physical page before serving a verbatim quote.** |
| C-54 | III.3 | Provincial Assessor Memorandum No. 2024-01, **Section 5** exempts a party to a pending case | **UP** | doc 2388 (Jonathan's own 13 Jul 2026 letter) | "provides at [§]5 that 'any party to a pending case shall be exempt from the requirement of a Special Power of Attorney or Authorization, provided that a duly certified or duplicate original copy of the complaint or information is presented'" | The Memorandum's own text is **not in the corpus**; only Jonathan's letter quotes it. Annex "L" must be the issuance itself. |
| C-55 | III.4 | ARTA referred Teope to the Ombudsman under R.A. 3019 §3(i) | **V** | doc 3754 | "REFERRAL of this case to the OFFICE OF THE OMBUDSMAN … against TONY TEOPE, in his capacity as the Assistant to the Municipal Mayor … for the alleged violation of Section 3(i) of R.A. No. 3019" | — |
| C-56 | III.4 | Teope is "the Mayor's Executive Assistant" | **V** | doc 711 (CART Minutes 6 Apr 2026) | "Antonio B. Teope - Executive Assistant" | — |
| C-57 | III.4 / III.7 / VI-A-3 | ARTA referred "the **Municipal Building Official**" to the CSC | **P** | doc 719 (ARTA Resolution 7 Apr 2026) | "REFERRAL of this case to the CIVIL SERVICE COMMISSION - REGIONAL OFFICE V … against ENGR. ERWIN H. BALANE, in his capacity as the **Municipal Engineer** of the Municipal Engineering Office" | Every corpus document — ARTA, the CART minutes, his own letterhead — names him **Municipal Engineer**. (LGC §443(a) does create a combined "municipal engineer/building official" post, but no instrument of record uses "Building Official" for him.) The referral was to **CSC Regional Office V**. |
| C-58 | III.4 | On 1 Sep 2026 the Mayor wrote "there are no further administrative actions required or appropriate on the part of the LGU at this stage"; "He has declared in writing that he will not" | **P** | Binder1 pg-27 item 1 | "In view of the fact that the matter is now formally pending before the said agencies, the LGU must defer to their jurisdiction. **Consequently, there are no further administrative actions required or appropriate on the part of the LGU at this stage.**" | Quote verbatim ✓. The gloss over-reads: the stated ground is deference pending agency jurisdiction, not a declared refusal. Keep the quote; drop "he will not". |
| C-59 | III.4 | §444(b)(1)(x) duty quoted | **V** | `legal_chunks` id 2480/2510 | "cause to be instituted administrative or judicial proceedings against any official or employee of the municipality who may have committed an offense **in the performance of his official duties**" | Petition truncates before the closing clause without ellipsis — add "…" or restore it. |
| C-60 | III.5 | Records service paid for on 20 June 2025, O.R. No. 7383466 | **UP** | ABLA_COMPARATOR / ARTA 1321 filings (docs 6907/6908, 730 reference the OR) | OR number present across ARTA 1321 filings | The receipt itself was not read here. Annex "J" must carry it. |
| C-61 | III.5 | "**Fifteen months** later nothing has been rendered" | **W** | arithmetic | 20 Jun 2025 → 7 Sep 2026 = 444 days = **14 months 18 days** | Should read "fourteen months". |
| C-62 | III.5 | ARTA's Resolution of 25 Aug 2026 (CTN SL-2026-0209-1321) **found** the elapsed period "would substantially exceed" the charter | **W** | doc 6908 (ARTA 1321 Resolution) | "**Ordinarily, such period would substantially exceed** the two (2) to three (3)-day processing period… **Nevertheless, the mere existence of delay does not, by itself, establish a violation of Section 21(e)** … Here, **ARTA finds that the circumstances sufficiently establish just cause for the delay.**" | The words are verbatim but the sentence is a hypothetical that ARTA then rejects. Presenting it as ARTA's finding mischaracterises a resolution **adverse** to us — and the Province can pull the resolution. Also: the period ARTA measured was "approximately ten (10) months … until … March 2026", not fifteen. |
| C-63 | III.5 | A chartered two-to-three-day records service | **V** | doc 6908 | "requests involving multiple records are allotted two (2) to three (3) days" | — |
| C-64 | III.5 | "The Assessor **swore in May 2026** that the history '**cannot possibly be done**'" | **W** | doc 732 / doc 6908 (quoting her letter); doc 1046 (the sworn document) | "In a response **dated June 16, 2025** … the Respondent Assessor … stated that the history '**cannot possibly be done in just 15 working days**,' requesting 'ample time'" | Three errors: (1) it is a **16 Jun 2025 letter**, not a May 2026 affidavit — the phrase does **not appear** in doc 1046, the 28 May 2026 counter-affidavit; (2) it was not sworn; (3) truncating "in just 15 working days" **reverses the meaning** from a request for more time into a declaration of impossibility, which is precisely the use the petition makes of it. |
| C-65 | III.5 | Provincial Assessor's office reported in writing on 26 Jan 2026 that it had "done the research of all transactions" | **UP** | docs 6908, 730, 2388 | phrase present in ARTA filings | The originating 26 Jan 2026 email is flagged TO-OBTAIN in the working memos and was not located. Quote is repeated only inside our own filings. |
| C-66 | III.5 | Memo 2024-01's "own text **excepts tax maps**" | **U** | — | — | No source anywhere for a tax-map exception. The pending-case exemption (C-54) is separately sourced; this is not. |
| C-67 | III.5 | A draftsman asserts a one-hectare, ₱3.4-million "purchase" under a revoked SPA | **UP** | doc 719 (Jonathan's 4 Oct 2025 letter to the Mayor, annexed) | "**I have been informed** that Mr. Miguel Baliza claims to have purchased one (1) hectare of the property for ₱3.4 million from the late Mr. Cesar De la Fuente" | Self-reported hearsay in our own letter. "Draftsman" as his job title is not established in any corpus document — doc 719 says only "Mr. Baliza's role in the Assessor's Office". |
| C-68 | III.6 | CY 2026 assessment requested 10 Dec 2025, furnished 7 Mar 2026 | **V** | doc 2929 Q.A; BLGF b-4 | b-4: "on March 7, 2026 … he received from this office the RPT TAX ASSESSMENT FOR 2026"; doc 2929: "the response to the 10 December request" | — |
| C-69 | III.6 | "after **six weeks** of docketed demands" | **U** | arithmetic | 10 Dec 2025 → 7 Mar 2026 = 87 days = **12.4 weeks** | Either the figure or its referent is wrong; no source defines a six-week demand run. |
| C-70 | III.6 | Interest charged Jan–Apr on the whole year's tax | **V** | BLGF b-4 | "an interest of 2% per month or a total of Eight Percent (8%) was incurred **from January to April 2026** and added to the Tax Due" | — |
| C-71 | III.6 | §250 gives quarterly instalments; §255 runs interest from expiry of the §250 periods | **P** | `legal_chunks` 2352 (§250); BLGF b-1 (§255) | §250: "in four (4) equal installments"; §255: "upon the expiration of the periods as provided in Section 250, **or when due, as the case may be**" | §250 ✓. The §255 characterisation drops "or when due, as the case may be" — the exact clause BLGF and the Treasurer rely on. State it and answer it, or the Province answers it for you. |
| C-72 | III.6 | "Three different ordinances have been cited for the same charge" | **U** | doc 2929; BLGF b-4, b-2 | doc 2929: Treasurer cited "Section 208 of Provincial Ordinance No. **2-2004**"; b-4 and b-2: "Provincial Ordinance No. **22-2024**"; Ord. **31-2015** is cited by *us*, not by the LGU | At most **two** LGU citations, and they are plausibly one ordinance transcribed two ways. Not three. |
| C-73 | III.6 | ORs for a 7 Apr 2026 payment issued 7 Jul 2026, marked "paid under protest" | **V** | doc 2929; doc 1615 (OR image, 7/7/2026) | "Official receipts totaling PHP 41,118.56 were issued on 7 July and marked 'paid under protest.'" | Payment was transferred 5 Apr and credited 5 and 7 Apr; "a 7 April payment" tracks the credit date. |
| C-74 | III.6 | "The **7 July 2026 reconsideration demand** received no decision within the sixty days §252 allows; that period lapsed on or about 5 September 2026" | **U** | — | doc 2929 (13 Jul): "**this letter** also constitutes the owner's written protest under Section 252 … concerning the payment officially receipted on 7 July 2026" | No document or email dated 7 July 2026 from Jonathan exists in the corpus. If the §252 protest is the **13 July** letter, the sixty days expire **~11 September 2026**, not 5 September. The lapse date is currently unanchored — and the prayer (VI-C-2) is built on it. |
| C-75 | III.6 | §252 allows sixty days | **V** | `legal_chunks` id 32/2353 | "who shall decide the protest within sixty (60) days from receipt" | — |
| C-76 | III.6 | The Bureau's Regional Office "answered **none of the nineteen questions**" | **W** | doc 2929; BLGF PDF b-1/b-2 | see C-33 | The count is wrong (five lettered questions). Separately, BLGF *did* engage the substance of several — legal basis for interest, the ordinance, statements of account — so "answered none" also over-claims. |
| C-77 | III.6 | "Treasurer Manlapaz: you received that request the same day" | **P** | gmail 103665; BLGF b-6, b-5 | b-6 print bears the Office of the Governor received stamp of 13 Jul; b-5 is Manlapaz's 17 Jul letter | Provincial receipt on 13 Jul ✓; Manlapaz's **personal** receipt that day is inferred. The filing was addressed to `pgcamarinesnorte@gmail.com`. |
| C-78 | III.6 | §200 quoted | **V** | `legal_chunks` id 2333 | "shall be primarily responsible for the proper, efficient and effective administration of the real property tax" | Verbatim. |
| C-79 | III.7 | On 21 Oct 2025 the official wrote "there is no building permit issued recently pertaining to that particular area" | **V** | doc 837 | "As far as this office is concerned **there is no building permit issued recently pertaining to that particular area**." | Verbatim. Signed **ERWIN H. BALANE, Municipal Engineer** — see C-57. |
| C-80 | III.7 | …of the structure maintained on estate land in Barangay 1 by the Mayor's Executive Assistant | **P** | doc 837 | "the Construction in Brgy. 1, this municipality **in a lot currently occupied by Mr. Antonio Teope**" | The letter says "occupied by", not maintained/built by, and does not characterise the lot as estate land. |
| C-81 | III.7 | "referred the question of older permits to '**the previous building official**'" | **P** | doc 837 | "I would strongly encourage **to check their records** so that we can ascertain that no permits were issued by the previous building official" | The quoted words exist ✓, but he referred Jonathan to *the occupants' records*, not the question to that officer. |
| C-82 | III.7 | "an office he himself has held **since February 2010**" | **P** | doc 1037 ¶1 | "Respondent is **Municipal Engineer** of LGU Mercedes **since February 2010**" | Date ✓. The office in the source is Municipal Engineer, not Building Official — the sentence's sting depends on the identity, so name it as the source does. |
| C-83 | III.7 | "No notice of violation, work-stoppage order, or other enforcement has followed in the **eleven months** since" | **W** | arithmetic + negative check | 21 Oct 2025 → 7 Sep 2026 = 321 days = **10 months 17 days** | "Ten months". The enforcement negative itself has no affirmative source — it rests on our own non-receipt. |
| C-84 | III closing | Guerrero's Indorsements of 25 and 26 Aug 2026 drew written answers within a week | **V** | Binder1 pg-14 (25 Aug), pg-13/pg-20 (26 Aug), pg-25 & pg-27 (both 1 Sep) | 25/26 Aug → 1 Sep replies | — |
| C-85 | III closing | "which **fifteen months** of provincial referral never did" | **W** | arithmetic | first provincial referral 16 Mar 2026 → 7 Sep 2026 = **5 months 22 days** | Provincial referral is about six months old, not fifteen. |

---

## E. PART V — REFERRAL IS NOT SUPERVISION

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-86 | V ¶1 | The Municipal Assessor sat on the CART | **V** | doc 711 | present: "Gemma P. Abla - Municipal Assessor" | — |
| C-87 | V ¶1 | CART resolved the LGU "**shall not release, provide, or act upon the requested documents**" until personality proved | **P** | doc **6907** (ARTA 1321 Resolution Part 2), quoting Abla's Counter-Affidavit ¶13 | "the CART resolved that LGU **shall not release, provide, or act upon the requested documents** of Complainant unless he sufficiently proves and establishes his legal personality" | Quote verbatim ✓, **but the citation in the INTERNAL table (doc 6908) is wrong** — it is in 6907. More important: this is the **Respondent's characterisation** of the CART resolution reproduced in the ARTA resolution, not the CART Resolution's own operative text. Cite CART Resolutions Nos. 1–6 (docs 712–716) directly, or attribute the words to Abla's sworn pleading. |
| C-88 | V ¶1 | The complaint about the committee was referred by the Province to the committee's chairman | **V** | Binder1 pg-3 + pg-19 | see C-27, C-28 | The strongest paragraph in the petition. |

---

## F. PART VII — NOTICE

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-89 | VII.1 | RA 6713 §5(a) quoted / fifteen working days | **V** | `legal_chunks` id 133 | "within fifteen (15) working days from receipt thereof, respond to letters… The reply must contain the action taken on the request." | Verbatim. |
| C-90 | VII.2 | RA 3019 §3(f) quoted | **V** | `legal_chunks` id 112 | matches, with the omission correctly marked by ellipsis | — |
| C-91 | VII.3 | Civil Code Art. 27 quoted | **V** | `legal_chunks` id 397 | verbatim | — |
| C-92 | VII.4 | §61(b) quoted | **P** | `legal_chunks` id 12 | "(b) A complaint against any elective official of a municipality shall be filed before the sangguniang panlalawigan **whose decision may be appealed to the Office of the President**" | Petition ends the quotation with a period, dropping the appeal clause without ellipsis. Add "…". |
| C-93 | VII.4 | §60(c) quoted | **V** | `legal_chunks` id 11 | verbatim | — |
| C-94 | VII.4 | §61(a) sends a provincial complaint to the OP | **V** | `legal_chunks` id 12 | verbatim | — |
| C-95 | VII.5 | OP proceeding pending since May 2026, Transmittal Ref. 050526-MRO-234187 | **V** | doc 702 | "05 May 2026 … 050526-MRO-234187" | Reference and date confirmed on the filing. |
| C-96 | VII.5 | "A proceeding **on the conduct of this Municipality**" | **P** | doc 702 | "Petition for Supervisory Review and Corrective Action over the Anti-Red Tape Authority's Resolution dated 07 April 2026 … ARTA Case Nos. CTN SL-2025-1008-0690 and CTN SL-2025-1104-0792" | It is a review of an **ARTA resolution** concerning one municipal officer. Describe it accurately; the OP holds the file and will read this line. |
| C-97 | VII.5 | "with **three** manifestations since" | **U** | corpus search | only doc 1189 "OP SECOND MANIFESTATION" and doc 1246 "Manifestation of Correction (Errata) — OP" locate to the OP | Two found, not three. (doc 1189 is untagged — `case_file` NULL.) |

---

## G. PART VIII + service list

| # | Location | Claim (short) | Grade | Source | Supporting quote | Note |
|---|---|---|---|---|---|---|
| C-98 | VIII | Makes no compensation demand, asserts no taking date, no accusation against Guerrero | **V** | the document itself | — | Carve-outs held throughout. Confirmed. |
| C-99 | VIII | "those matters are with counsel of record on a separate track" | **V** | memory: counsel-is-per-matter (Botor lane) | — | Consistent. |
| C-100 | To / cc | HON. MAXIMO P. MAGANA, JR., REA — Provincial Assessor | **V** | doc 1623 | "MAXIMO P. MAGANA JR. REA / Provincial Assessor" | — |
| C-101 | To | HON. `[OPERATOR: full name]` MANLAPAZ — Provincial Treasurer | **V (gap closable)** | BLGF PDF b-5, b-4, b-6 | "**DANTE E. MANLAPAZ** / Provincial Treasurer" (his own signature block) | The corpus already holds the first name. The `[OPERATOR]` placeholder is unnecessary. |
| C-102 | cc | ATTY. ARNALDO E. ESCOBER, JR., CESO III — Regional Director, DILG Region V | **V** | Binder1 pg-1, pg-12, pg-17 | verbatim, incl. "CESO III" | — |
| C-103 | cc | DIR. MELODY E. RELUCIO, CESO V — Provincial Director, DILG–Camarines Norte | **V** | DILG 2 Sep letters; Binder1 pg-1 | signature block "…ODY E. RELUCIO, CESO V / Provincial Director" | — |
| C-104 | cc | **MS. CONSOLACION Q. AGCAOILI — Executive Director, Bureau of Local Government Finance** | **U** | corpus search: 0 hits | the only "Agcaoili" in MWK-001 is **Atty. Ma. Carmen Agcaoili-Orena, Agcaoili & Associates** — the heirs' own Makati counsel (docs 782, 783, 789, 381) | **No source at all for this name or title.** An unsourced named official on the service list of a document being served on three government offices. Verify against BLGF's published roster or drop to "The Executive Director, BLGF". |
| C-105 | cc | DIR. JESSIE B. DOCTOLERO — Regional Director, BLGF Regional Office No. V | **V** | BLGF PDF b-4 cc block | "Dir. Jessie B. Doctolero-REA,REB,REC / BLGF Regional Director / Rawis, Legazpi City" | — |
| C-106 | cc | ATTY. ARIEL G. RONQUILLO — Assistant Commissioner for Legal, CSC, "**holder of** ARTA Notice of Referral, CTN SL-2026-0423-1891" | **P** | Binder1 pg-19 (CSC letter, 23 Jun 2026) | "Atty. ARIEL G. RONQUILLO / Assistant Commissioner"; "**We are respectfully forwarding to that Office the said NOR** considering that the person involved is an elective official" | Name, office and past custody ✓. But he **forwarded the NOR to the Ombudsman on 23 June 2026** — he is not the current holder. Stale as written. |
| C-107 | cc | MR. VENCER KRYSTIAN M. GUERRERO — MLGOO / LGOO VI, DILG–Mercedes | **V** | Binder1 pg-22 | "MR. VENCER KRYSTIAN M. GUERRERO / LGOO VI, MLGOO" | — |
| C-108 | Annex "A" | "the **Licarte**–Padilla transmittal of 23 Jun 2026" | **P** | Binder1 pg-3 | signature OCR: "…LICARTE, EnP, RPF / PPDC / ARTA Focal Person" | Surname and role ✓. The given name "Teodoro L." has **zero corpus support** — do not use it. |
| C-109 | Annex "N" | BLGF Region V letter of 31 Jul 2026 | **P** | `2026-08-14_BLGF_R5_reply_RPT_protest_denial.pdf` p.1 | date line OCR'd as "Jualy G1, 2086" — illegible | Emailed 14 Aug 2026 (gmail 118367). Read the date off the paper before citing "31 Jul". |
| C-110 | client separation | Any fact belonging to another matter | **PASS** | — | — | No Paracale-001 / LTC-001 / NIBDC / CV26360 content bleeds into the petition. ARTA dockets 1891 (CART) and 1321 (Assessor) are kept distinct as required. Untagged corpus rows encountered (docs 1189, 1615, 1616, 2387) are missing `case_file`, not cross-matter leaks. |

---

# ORDERED FIX LIST — every W / U / UP item

## P0 — WRONG (source contradicts; fix before the document goes anywhere)

1. **C-33 / C-76 / Prayer VI-C-1 — "nineteen enumerated questions."**
   The 13 July 2026 protest (doc 2929) contains **three** determinations (1–3) and **five** lettered
   questions (A–E). Replace all three occurrences with **"five enumerated questions (A to E), together
   with three records-and-determination items"**. In VI-C-1 read: *"answering its five enumerated
   questions and three determination items, or stating, item by item, that your Office declines."*
   If the intended referent is the "matrix of unanswered inquiries" attached as an exhibit, cite that
   exhibit by name and re-count it — do not attribute nineteen questions to the protest itself.

2. **C-37 — "The Provincial Government of Camarines Norte has never sent me a single communication."**
   Disproved by the petition's own Part II row 6 (Provincial Assessor Magana, 1 July 2026).
   Replace with: **"Apart from the Provincial Assessor's acknowledgment of 1 July 2026, no office of the
   Provincial Government has ever written to me — not the Governor's Office, not the Provincial Legal
   Officer, not the Provincial Treasurer."**

3. **C-64 — the Assessor "swore in May 2026 that the history 'cannot possibly be done'."**
   Source is a **letter of 16 June 2025**, not a May 2026 affidavit, and the quote is truncated so as to
   reverse its sense. Replace with: **"In her letter of 16 June 2025 the Municipal Assessor called the
   properties 'complex in nature' and said the history 'cannot possibly be done in just 15 working days,'
   asking for 'ample time' — while the Provincial Assessor's own office…"**

4. **C-47 — the 26 August 2026 Supplemental Indorsement quote.**
   Replace `"cite the specific public instrument, deed, title, or expropriation record"` with the
   source's words: **"formally identify and produce the specific public instrument, title, deed, or record
   on which its 24 July 2026 written representation of 'legal title' rests"** (Binder1 pg-20).

5. **C-62 — ARTA "found the elapsed period 'would substantially exceed' the charter."**
   ARTA said this hypothetically and then found just cause. Replace with: **"ARTA's Resolution recorded
   that the elapsed period would ordinarily 'substantially exceed' the two-to-three-day charter period,
   though it found just cause on the record then before it."** Never cite this resolution as a finding in
   our favour — it is adverse and the Province can pull it.

6. **C-39 — the 5 March 2026 refusal quote.**
   `"certified copies only after review and adoption"` is not in doc 765. Either drop the quotation marks,
   or quote the source: **"the minutes must first be reviewed and adopted by the body before a Certified
   True Copy may be issued."**

7. **C-52 — "cited no law, no ordinance, and no Citizen's Charter provision."**
   The Mayor cited LGC §16. Replace with: **"cited no law authorizing the requirement, no ordinance and no
   Citizen's Charter provision — only the general welfare clause of Section 16, 'implied powers', and
   parens patriae."**

8. **C-61, C-83, C-85 — duration arithmetic.**
   - III.5: "Fifteen months later nothing has been rendered" → **"Fourteen months later"** (20 Jun 2025 → 7 Sep 2026 = 14m 18d).
   - III.7: "in the eleven months since" → **"in the ten months since"** (21 Oct 2025 → 7 Sep 2026 = 10m 17d).
   - III closing: "which fifteen months of provincial referral never did" → **"which six months of provincial referral never did"** (16 Mar 2026 → 7 Sep 2026 = 5m 22d).
   - III.1: "seven months after the request" → **"nearly seven months"** (11 Feb → 1 Sep 2026 = 6m 21d).
   - Keep "more than thirty-five working days" and "more than nine weeks" — both verified and conservative.

9. **C-26 — Part II rows 3 and 4 are inverted.**
   DILG's 2 Sep letter says it has **no** information on the March letters and attributes the
   "reviewed and referred to LGU Mercedes" action to the **4 June 2026** memorandum. Move the
   "referred … on jurisdictional grounds" entry to the **4 Jun 2026** row, and make row 3 read:
   *"Per DILG's letter of 2 Sep 2026, DILG has 'not received any correspondence specifically indicating
   the action taken on the aforementioned letters.'"* That is a stronger fact than the one now stated.

## P1 — UNSUPPORTED (no source found; cut or source before service)

10. **C-104 — "MS. CONSOLACION Q. AGCAOILI — Executive Director, Bureau of Local Government Finance."**
    Zero corpus support; the only Agcaoili of record is the heirs' own Makati counsel. **Highest-risk item
    in the service list.** Verify against BLGF's official roster, or address the office by title only.
11. **C-25 — "following my letters of 13 and 17 March 2026 to the Governor."** No such letters exist.
    Rewrite as: *"following DILG's forwards to your Office, which DILG records as made on 13 March,
    17 March and 4 June 2026."*
12. **C-72 — "Three different ordinances have been cited for the same charge."** At most two
    (Prov. Ord. 2-2004 as we recorded the Treasurer's citation; Prov. Ord. 22-2024 as she and BLGF wrote),
    plausibly one ordinance transcribed two ways. Rewrite as: **"The same charge has been attributed to
    Provincial Ordinance No. 2-2004 and to Provincial Ordinance No. 22-2024 in different documents, and
    neither provision has been produced."** That is both true and sharper.
13. **C-74 — the "7 July 2026 reconsideration demand" and the 5 September lapse.** No 7 July 2026
    document or email exists. Doc 2929 says the **13 July** letter is itself the §252 protest, which puts
    the sixty days at **~11 September 2026**. Re-derive the date from the instrument actually filed, or
    cut the lapse assertion and Prayer VI-C-2's "so the estate may proceed on the lapse".
14. **C-97 — "with three manifestations since."** Two OP manifestations located. Say **"with two
    manifestations since"**, or name them.
15. **C-66 — Memo 2024-01 "excepts tax maps."** No source. Cut, or produce the Memorandum's text.
16. **C-69 — "after six weeks of docketed demands."** The 10 Dec → 7 Mar gap is 12.4 weeks. State the
    gap ("nearly three months") or cut the six-week figure.
17. **C-6 — "That is the one time provincial supervision has been exercised here."** No document shows
    the Province acted on the 2023 letter. Soften to: *"It is the one time this Office was asked and the
    taxes then moved."*
18. **C-83 (second limb) — the enforcement negative.** "No notice of violation, work-stoppage order, or
    other enforcement has followed" rests only on our non-receipt. Add **"none has been furnished to the
    owner"** or mark it `[HUMAN VERIFY]`.

## P2 — UNVERIFIED-PRIMARY (only a secondary or self-authored source carries it)

19. **C-54 — Memorandum No. 2024-01 §5.** Text exists only inside our own 13 July letter (doc 2388).
    Annex "L" must be the issuance itself, or the sentence must read *"as quoted in our letter of 13 July 2026"*.
20. **C-23 — the Provincial Legal Officer attribution.** Only doc 365's self-authored index, which says
    "**allegedly**". Keep the existing hedge and add the qualifier that it is our own contemporaneous note —
    Prayer VI-A-4 is the right way to put it to them, and should carry the weight instead.
21. **C-65 — "done the research of all transactions" (26 Jan 2026).** Originating email not located;
    quoted only inside our own ARTA filings. Obtain it or attribute it as quoted in our filings.
22. **C-67 — the Baliza ₱3.4M / one-hectare claim, and "draftsman".** Sourced to our own letter's
    "I have been informed". Recast as: *"a person holding a position in the Municipal Assessor's Office is
    reported to assert…"* and drop "draftsman" unless a document gives that title.
23. **C-5 — "provincial oversight got the taxes updated."** Causation inferred. See item 17.
24. **C-60 — O.R. No. 7383466 / 20 June 2025.** Read the receipt itself before it goes into Annex "J".

## P3 — precision fixes (quotation integrity and titles)

25. **C-57, C-79, C-82 — "Municipal Building Official."** Every instrument of record names Erwin H.
    Balane **Municipal Engineer**. Change all occurrences (III.4, III.7, Prayer VI-A-3), and note the CSC
    referral went to **CSC Regional Office V**.
26. **C-92 — §61(b).** Restore or ellipsis the dropped clause "whose decision may be appealed to the
    Office of the President."
27. **C-44 — §469(c)(7).** Insert "**non-confidential**": *"makes the office and its non-confidential
    records open to the public."*
28. **C-59 — §444(b)(1)(x).** Close the quote at "…in the performance of his official duties" or mark the
    truncation.
29. **C-71 — §255.** Acknowledge "or when due, as the case may be" and answer it, rather than omitting it.
30. **C-53 — the "very parcel of land" quote.** The head of the sentence falls on an illegible line of
    Binder1 pg-27. **Re-read the physical page** before serving it as a verbatim quotation.
31. **C-106 — Ronquillo.** He forwarded the NOR to the Ombudsman on 23 June 2026. Change "holder of" to
    **"who referred ARTA Notice of Referral CTN SL-2026-0423-1891 to the Office of the Ombudsman,
    23 June 2026"**.
32. **C-87 — the CART quote.** Cite **doc 6907** (not 6908), and attribute the words to Abla's sworn
    Counter-Affidavit ¶13 as reproduced in the ARTA Resolution — or quote CART Resolutions Nos. 1–6
    (docs 712–716) directly.
33. **C-96 — the OP proceeding.** Describe it as what it is: a petition for supervisory review of ARTA's
    7 April 2026 Resolution in CTN SL-2025-1008-0690 and CTN SL-2025-1104-0792.
34. **C-58 — "He has declared in writing that he will not."** Keep the verbatim quote; drop the gloss, or
    recast as *"He has declared in writing that he considers no action required."*
35. **C-38 — the session-records request.** Doc 765 answers a request naming only the 21 January session;
    the three-session set is first indorsed 25 Aug 2026. And **"fees tendered" has no source** — pg-14
    asks for a *fee assessment*, i.e. none was made. Fix both here and in Prayer VI-A-1(a)
    ("fees stand tendered").

## Housekeeping — errors found in the `# INTERNAL` provenance table itself

- CART "shall not release" is in **doc 6907**, not doc 6908.
- Mayor 24 Jul "legal title" is **not** an INGEST-GAP — the primary letter is Binder1 pp. 18 + 8.
- The 26 Aug Supplemental Indorsement is **not** ingest-pending — it is Binder1 pp. 13 and 20, and its
  wording differs from what the petition quotes (item 4 above).
- "Annex R scoreboard (36 rows)" — the schedule has **35** rows; the petition's "thirty-five" is right.
- Provincial Treasurer's first name is already of record: **Dante E. Manlapaz** (BLGF PDF pp. 4–6).
- Working-day table: the "more than thirty-five working days" and "more than nine weeks" figures both
  recompute correctly. The "fifteen months" figures do not (item 8).

---

**Bottom line.** The petition's spine — the Province's own transmittals (C-11/C-27/C-88), the 1 September
LGU replies (C-40/C-45/C-48), TCT T-32911's clean encumbrance page (C-50), Res. 76-96's "proposed"
(C-51), and every statutory quotation in Part IV — is sound and well sourced. What fails is a layer of
unverified numbers, clipped quotations, and one unsourced official's name laid over it. Fix the P0 and P1
lists and this becomes a document that survives being checked against the addressee's own file.
