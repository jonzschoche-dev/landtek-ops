-- deploy_NN: ARTA-cluster deadline-coverage hardening on MWK-001
-- Product-hardener pass, 2026-06-30. Continues the deploy_642 pattern (grounded ARTA-1891 date).
-- GROUNDED structured-date writes only — written to matters.next_deadline (the STRUCTURED column),
-- NEVER the vector store. Provenance discipline: the date ANCHOR is a cited ARTA Litigation Division
-- transmittal email (verified event); the COMPUTED decision/follow-up window is an operator/derived
-- estimate (not a statute quoted verbatim) and therefore carries [HUMAN VERIFY].
-- Client/matter separation absolute: ARTA dockets are SEPARATE matters; no date is cross-linked from
-- one docket to another. Does NOT touch any Aug-12 case-critical safety path.
--
-- ALL FOUR UPDATEs below were APPLIED LIVE on the VPS 2026-06-30 by the product-hardener; this file
-- exists for replay/audit. Two targets (1210, 1212) were deliberately LEFT NEEDS-A-DATE — see footer.
--
-- ============================================================================================
-- Change 1 — MWK-ARTA-1319 (v. PENRO Camarines Norte; CTN SL-2026-0209-1319)
--   ANCHOR (verified): gmail#90334, recv 2026-06-15 — ARTA Litigation Division transmittal of the
--     signed "Notice of Submission for Resolution (NSR)". Excerpt: "Respectfully furnishing the
--     parties the signed copy of the Notice of Submission for Resolution (NSR)."
--   WINDOW ([HUMAN VERIFY]): ARTA resolution clock ~65 working days from NSR (operator estimate,
--     not a statute quoted verbatim) -> 2026-09-14. Record is closed/submitted; respondents waived.
-- ============================================================================================
UPDATE matters
SET next_deadline = DATE '2026-09-14',
    next_event = 'Await ARTA resolution — CTN SL-2026-0209-1319 SUBMITTED FOR RESOLUTION (NSR transmitted, recv 2026-06-15, gmail#90334). [HUMAN VERIFY] decision window ~65 working days from NSR (est mid-September); an adverse/no-jurisdiction ruling becomes ammunition in CV-26360, so file the narrow-and-reserve manifestation if not yet filed. Anchor: gmail#90334.',
    -- NOTE: the computed ISO deadline (2026-09-14) lives ONLY in next_deadline, NOT in this prose,
    -- so the engine's free-text date parser does not re-surface it as a duplicate obligation.
    stage_updated_at = now()
WHERE matter_code = 'MWK-ARTA-1319';

-- ============================================================================================
-- Change 2 — MWK-ARTA-1321 (v. Municipal Assessor's Office Mercedes; CTN SL-2026-0209-1321)
--   ANCHOR (verified): gmail#76281, recv 2026-06-05 — ARTA Litigation Division NSR transmittal.
--     Excerpt: "Respectfully furnishing the parties the signed copy of the Notice of Submission
--     for Resolution (NSR)." (Prior procedural anchor: Order dated 25 May 2026 on respondent
--     Abla's motion for extension, gmail#38638.)
--   WINDOW ([HUMAN VERIFY]): ~65 working days from NSR -> 2026-09-04.
-- ============================================================================================
UPDATE matters
SET next_deadline = DATE '2026-09-04',
    next_event = 'Await ARTA resolution — CTN SL-2026-0209-1321 SUBMITTED FOR RESOLUTION (NSR transmitted, recv 2026-06-05, gmail#76281). [HUMAN VERIFY] decision window ~65 working days from NSR (est early September). Companion to -1319 (filed same day); coordinate. Anchor: gmail#76281.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-ARTA-1321';

-- ============================================================================================
-- Change 3 — MWK-ARTA-1378 (v. Engr. Erwin H. Balane / Municipal Engineer's Office; CTN SL-2026-0218-1378)
--   ANCHOR (verified): gmail#72403, recv 2026-06-04 — ARTA Litigation Division NSR transmittal.
--     Excerpt: "Respectfully furnishing the parties the signed copy of the Notice of Submission
--     for Resolution (NSR)." Complainant filed a Supplemental Affidavit & Manifestation 2026-06-08
--     (gmail#90572) with Annexes E-I (incl. respondent's 21-May Counter-Affidavit, doc#1037).
--   WINDOW ([HUMAN VERIFY]): ~65 working days from NSR -> 2026-09-03.
-- ============================================================================================
UPDATE matters
SET next_deadline = DATE '2026-09-03',
    next_event = 'Await ARTA resolution — CTN SL-2026-0218-1378 (v. Engr. Erwin Balane) SUBMITTED FOR RESOLUTION (NSR transmitted, recv 2026-06-04, gmail#72403); Supplemental Affidavit+Manifestation filed 2026-06-08 (gmail#90572). [HUMAN VERIFY] decision window ~65 working days from NSR (est early September). Defense is procedural-only (defective service); perjury point on respondent non-receipt is documented. Anchor: gmail#72403.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-ARTA-1378';

-- ============================================================================================
-- Change 4 — MWK-ARTA-DILG (the DILG-referral leg of CTN SL-2026-0423-1891; merged into MWK-ARTA-1891
--   on 2026-05-16 per its own stage_notes — SAME docket, NOT a separate one, so this is not a cross-link)
--   ANCHOR (verified): gmail#65194, recv 2026-06-02 — DILG R5 Records Section "NOTICE OF REFERRAL -
--     CTN SL-2026-0423-1891 (DILG)" forwarding the referred file for "appropriate action."
--     Excerpt: "Respectfully forwarding the attached file relative to the above-mentioned subject
--     for your reference and appropriate action. Kindly acknowledge upon receipt of this email."
--   WINDOW ([HUMAN VERIFY]): 30-day operator follow-up rule from the DILG referral -> 2026-07-02.
-- ============================================================================================
UPDATE matters
SET next_deadline = DATE '2026-07-02',
    next_event = 'Follow up on DILG-referral leg of CTN SL-2026-0423-1891 — DILG R5 issued NOTICE OF REFERRAL (recv 2026-06-02, gmail#65194). [HUMAN VERIFY] 30d operator follow-up window from referral -> est 2026-07-02. This matter is merged into MWK-ARTA-1891 (same docket); track jointly, do not double-count. Anchor: gmail#65194.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-ARTA-DILG';

-- ============================================================================================
-- DELIBERATELY LEFT NEEDS-A-DATE (honest blank beats fabrication):
--
--   MWK-ARTA-1210 (CTN SL-2026-0128-1210, v. LGU Mercedes/Mayor Pajarillo + Treasurer Macale):
--     ARTA RESOLUTION dated 13 May 2026 already ISSUED; notice received 2026-05-15 (gmail#42).
--     The only window the record grounds is the 15-day Notice-of-Appeal-to-OP window ("you may file
--     a Notice of Appeal with the Office of the President within fifteen (15) days from notice"),
--     which ran from 2026-05-15 and LAPSED 2026-05-30 — a PAST window, not a forward obligation.
--     No groundable future ARTA date remains (MR is prohibited; any OP appeal lives under MWK-OP-PETITION).
--     -> No forward date manufactured. Left NEEDS-A-DATE.
--
--   MWK-ARTA-1212 (CTN SL-2026-0128-1212, v. Sangguniang Bayan Mercedes):
--     Last corpus activity = CART indorsement-to-Mayor thread, 2026-03-19 (gmail#95/#96376); CART
--     Resolution No. 3 recommended CLOSURE of this docket. No NSR, no served order, no forward-
--     obligation email in the corpus. -> No groundable forward date. Left NEEDS-A-DATE.
-- ============================================================================================
