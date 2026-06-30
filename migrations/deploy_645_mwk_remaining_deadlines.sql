-- deploy_645: MWK-001 remaining-deadline coverage hardening (guardianship grounded; OP/CV6839/LGU honestly blank)
-- Product-hardener pass, 2026-06-30. Continues the deploy_642 / deploy_644 discipline:
--   GROUNDED structured-date writes ONLY -> matters.next_deadline (the STRUCTURED column), NEVER the
--   vector store. verified = cited email/doc + quoted excerpt. The ISO date lives ONLY in next_deadline;
--   any date inside next_event / stage_notes prose is written TEXTUALLY (e.g. "27th of July", "late July")
--   so the deadlines.py free-text parser (ISO_RE / MDY_RE) does NOT re-surface it as a phantom 2nd
--   obligation. Client/matter separation absolute. Does NOT touch any Aug-12 case-critical safety path;
--   CV-26360 is left exactly as-is (still NULL / free-text only).
--
-- This UPDATE was APPLIED LIVE on the VPS 2026-06-30; this file exists for replay/audit.
-- Coverage delta proven via `python3 scripts/deadlines.py --write`:
--   MWK NEEDS-A-DATE: 14 -> 13 (MWK-GUARDIANSHIP drained). No phantom double-count on the --write re-run.
--
-- ============================================================================================
-- Change 1 (GROUNDED) — MWK-GUARDIANSHIP  -> 2026-07-27  (RTC-set initial hearing)
--   ANCHOR (verified): RTC Branch 41 Daet Order in Spec. Proc. No. 2680 (doc#1199; forwarded by
--     lead counsel Atty. Adan Botor in gmail#91604, received 2026-06-22 06:59 from the court address
--     rtc1dae041@judiciary.gov.ph). The petition is FILED + docketed (Spec. Proc. No. 2680); the Order
--     itself SETS the date — this is a court-set forward deadline, not a derived/operator estimate, so
--     it carries NO [HUMAN VERIFY] tag.
--   VERBATIM EXCERPT (doc#1199): "Finding the petition to be sufficient in form and substance under
--     Rule 93 of the Rules of Court, the Court hereby sets the hearing on the petition on July 27, 2026
--     at 8:30 in the morning through in-court proceedings."
--   Wards per the Order: Patricia Keesey Zschoche, Geraldine Alice Teresita Keesey Hoppe, Marcia Ellen
--     Keesey; subject TCT T-32911 (Mercedes, Camarines Norte, 8,706 sqm).
--   Stage corrected: petition_drafted_pending_filing (STALE — it is filed + docketed + set for hearing)
--     -> petition_filed_hearing_set.
--   NB: the ISO date 2026-07-27 lives ONLY in next_deadline. In stage_notes the same date is written
--     "27th of July" / "27 July" and the receive date "22 June" (day-month-year order), which neither
--     ISO_RE (20\d{2}-\d{2}-\d{2}) nor MDY_RE (month-name day, year) matches -> no phantom re-parse.
-- ============================================================================================
UPDATE matters
SET next_deadline = DATE '2026-07-27',
    current_stage = 'petition_filed_hearing_set',
    next_event = 'RTC Br 41 Daet initial hearing on the guardianship petition, set for late July (8:30am, in-court). Petitioner must present jurisdictional compliance, publication proof (once weekly x3 wks), and post the Rule 94 bond, or the petition is dismissed.',
    stage_notes = regexp_replace(coalesce(stage_notes,''), E'\n\n\\[2026 update\\] GROUNDED:.*', '', 's')
        || E'\n\n[2026 update] GROUNDED: Petition FILED + docketed as Spec. Proc. No. 2680, RTC Branch 41 Daet. Court Order (doc#1199, fwd by Atty. Botor gmail#91604 recv 22 June, from rtc1dae041@judiciary.gov.ph) sets the initial hearing for 27 July, 8:30am, in-court. Wards: Patricia Keesey Zschoche, Geraldine Alice Teresita Keesey Hoppe, Marcia Ellen Keesey; re TCT T-32911 (Mercedes, 8,706 sqm). Stage advanced from petition_drafted_pending_filing. Verbatim excerpt (date written textually to avoid free-text re-parse; structured date lives in next_deadline): the Court hereby sets the hearing on the petition on the 27th of July at 8:30 in the morning through in-court proceedings.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-GUARDIANSHIP';

-- ============================================================================================
-- DELIBERATELY LEFT NEEDS-A-DATE (honest blank beats a fabricated forward date):
--
--   MWK-OP-PETITION (petition_filed_awaiting_op_action):
--     FILED 2026-05-05 — "Petition for Supervisory Review and Corrective Action and a Notice of Appeal
--     in the alternative" over the 07-Apr-2026 ARTA Resolution (gmail#52, Jonathan's notice of filing).
--     ACKNOWLEDGED 2026-05-06 by Malacanang Records Office (gmail#53, from mro@op.gov.ph): "This is to
--     acknowledge receipt of your email ... forwarded to the concerned ... action office for appropriate
--     action." Both are PAST events. The OP supervisory review is a DISCRETIONARY executive review with
--     no court-set hearing and no statutorily-fixed response-by date in the corpus; the only fixed clocks
--     here are the ARTA Notice-of-Appeal/manifestation windows, which are ALREADY tracked separately under
--     MWK-ARTA-0747 (2026-06-10) and MWK-ARTA-1210 — writing a date here would double-count those onto the
--     wrong matter. No later OP correspondence exists except admin "OP Visit Registration" mail (gmail
--     #72690/#72736/#72833, 2026-06-04). -> No forward date manufactured. Left NEEDS-A-DATE.
--
--   MWK-CV6839 (just_compensation_halted_pending_substitution):
--     1998 just-compensation case vs LandBank, re 4 parcels incl. T-4494, originally prosecuted by Cesar
--     dela Fuente who died 2017-06-21 (verified, doc#364). Case is HALTED pending substitution of heirs
--     (Atty. Belen sought substitution). Substitution is a party-driven motion with NO external/court-set
--     clock, and the matter's own notes say "Status uncertain — needs follow-up with current court
--     records." No served order, hearing notice, or substitution-filing in the corpus. -> No groundable
--     forward date. Left NEEDS-A-DATE (true status: operator must pull current court records).
--
--   MWK-LGU-RECOVERY (evidence assembled; COA request filed-ready):
--     The COA Special/Fraud Audit Request is a DRAFTED counsel deliverable (doc#1247, 2026-06-29,
--     classification "Work Product — Counsel Deliverable", execution_status NULL = NOT filed). "Filed-
--     ready" means not yet filed; no COA receiving/acknowledgment exists, so no agency response window
--     has begun. An internal "we should file this" is an operator task, not a grounded external deadline.
--     -> No groundable forward date. Left NEEDS-A-DATE.
-- ============================================================================================
