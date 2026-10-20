# DRIP FEEDBACK LEDGER (internal, never outward)

*Live, regenerated 20 Oct 2026 16:34 PHT from `drip_feedback`. Read this before drafting, revising or even considering a drip. Jonathan's own words are quoted; the lesson is the rule the stack now follows; 'enforced by' says where.*

## The Charter (governs everything below)

- 20 Oct 2026 16:34 · **DRIP_CHARTER** · Jonathan: “Adopt it”  
  **Lesson:** The Drip Charter (Q1–Q12, 20 Oct 2026) is adopted as the drip's governing document; it outranks the steering guide, spec and templates.  
  *Enforced by:* drip_card.py line 0 CHARTER; 005 spec header; steering guide §0

## Rules for every drip

- 20 Oct 2026 16:06 · Jonathan: “theres no counsel theres just us”  
  **Lesson:** Outside court filings that need a signature, LandTek is the legal desk. Verify the law ourselves from the law corpus (legal_chunks, jurisprudence) and decide. Never write 'counsel should confirm'; mark [VERIFY] only where the corpus lacks the text, and close that gap ourselves.  
  *Enforced by:* memory feedback-dont-gate-on-counsel; this ledger
- 20 Oct 2026 15:10 · Jonathan: “just run the drip here for now on one by one … my feedback should be somewhere in the corpus … we need a LIVE corpus”  
  **Lesson:** Every critique goes into this ledger; the ledger and the steering guide regenerate and re-ingest automatically; read the ledger before drafting or considering any drip.  
  *Enforced by:* drip_feedback table; scripts/drip_feedback_ledger.py; 005 X18
- 20 Oct 2026 12:50 · Jonathan: “using two ai is not working we need to trigger from a single input and output”  
  **Lesson:** One brain (Claude) owns the drip; one input (Jonathan), one output (one draft at a time).  
  *Enforced by:* 005 ONE BRAIN, ONE LOOP
- 20 Oct 2026 12:20 · Jonathan: “the drip should always be drafts for comment, program that into the system so there is constant movement”  
  **Lesson:** There are always ≥5 drafts awaiting comment, shown one at a time; every comment or approval refills the queue.  
  *Enforced by:* 005 THE REVIEW QUEUE; drip_queue_config.min_awaiting_comment
- 20 Oct 2026 12:10 · Jonathan: “all emails come from jonzschoche@gmail.com or from their origin; sometimes im using hayuma.org; keep the same thread”  
  **Lesson:** Send from the account where the office's thread lives; always reply in the same thread.  
  *Enforced by:* 005 SENDING ACCOUNT AND THREAD; step_plan.send_account/thread_ref
- 20 Oct 2026 11:00 · Jonathan: “all communications anchored in the greater goal”  
  **Lesson:** No goal, no communication: every step names the goal element it serves.  
  *Enforced by:* 005 §v2 Stage 8 internal goal; step_plan.goal_element
- 20 Oct 2026 10:45 · Jonathan: “yes but we need to baby step to our legal and financial goals”  
  **Lesson:** Each drip earns one record element toward a set goal (legal or financial); ladders lead to the goal.  
  *Enforced by:* 005 BABY-STEP LADDERS; step_plan
- 20 Oct 2026 10:30 · Jonathan: “the documents presented are highly strategic and against the mandate of the stated drip algo … should be noncombative, put them to sleep building a case over time”  
  **Lesson:** Strategic instruments (schedules, amounts, comparators, the office's own declarations, supervisor cc's) are never openers; they are the last rung of a ladder, on Jonathan's go.  
  *Enforced by:* 005 SLEEP DOCTRINE; lint strategic_tell, adverse_annex_early, supervisor_cc_early; step_plan CHECK (strategic never step 1)
- 20 Oct 2026 09:00 · Jonathan: “the drip is not meant to be combative, it's meant to make them go to sleep while the record builds”  
  **Lesson:** Routine drips are calm and plain: one small ask, the easy yes, a polite reply period, the last letter cited by date; no threats, adjectives or forum names.  
  *Enforced by:* 005 §v2 C2 + SLEEP DOCTRINE; lint threat_early, cold_tone, strategic_tell

## By office / official

- 20 Oct 2026 14:25 · **Provincial Assessor Magana** · Jonathan: “provinicial assessor does not hadle improvements”  
  **Lesson:** Custodian map: declarations of improvements are kept by the MUNICIPAL Assessor, not the Provincial. Where the municipal custodian is a respondent (X17), use counsel's subpoena duces tecum, not a drip letter.  
  *Enforced by:* step note; CV 26-360 subpoena request (Municipal Assessor item)
- 20 Oct 2026 12:55 · **Assessor Abla** · Jonathan: “ive already attacked her through arta”  
  **Lesson:** Never write directly to a respondent in our live proceedings (ARTA/OP/CSC/OMB/court); route to another custodian, or use a reviewed "uniquely theirs" exception.  
  *Enforced by:* 005 X17 POSTURE; drip_draft_queue.posture()
- 20 Oct 2026 11:20 · **Mayor Pajarillo** · Jonathan: “ok we are asking for something he has refused to give, the legal stack should understand where we are at”  
  **Lesson:** Read the ask history first; never re-ask a refused or answered item. Narrow it, route it to another custodian, or build on their own words.  
  *Enforced by:* 005 X16 HISTORY BEFORE EVERY ASK; step_plan.history_ref

## By ladder

- 20 Oct 2026 16:15 · **LGU-MACALE-RPT** · Jonathan: “theres more than 13”  
  **Lesson:** Work from the FULL list, never from one statement's subset: the 2026 bill (doc 1616) has 22 ARPs (₱198,646.78 for 2026: advance ₱30,640.08 + Dec 2025 ₱112,496.64 + Apr 2026 ₱41,118.56, balance ₱14,391.50). The corpus schedule has 29 parcels in the heirs' names (ESTATE_DECLARED_PARCELS_2026-09).  
  *Enforced by:* doc 1616; ESTATE_DECLARED_PARCELS_2026-09.md; this ledger
- 20 Oct 2026 16:04 · **LGU-MACALE-RPT** · Jonathan: “its not clear if I ever identified what Im protesting ?”  
  **Lesson:** A §252 protest is about tax already PAID. It must name the ARP, the OR and the amount paid under protest, and the grounds, and go to the PROVINCIAL Treasurer (for a municipality outside Metro Manila) within 30 days of payment. The 13 Jul letter disputes the UNPAID ₱14,391.50 and so is a supervisory request, not a §252 protest. Macale has no §252 decision duty, and the '60-day lapse ~11 Sep' and 'LBAA window ~14 Nov' claims are withdrawn.  
  *Enforced by:* LGC §252(a) (legal_chunks RA 7160 chunk 207); step note LGU-MACALE-RPT; DRIP_BLGF_ACK_DRAFT escalation A corrected
- 20 Oct 2026 14:20 · **CV26360-PROV-ASSESSOR** · Jonathan: “the declarations we are looking for is for imporvements”  
  **Lesson:** Name the exact record type; for structures that means declarations of improvements (buildings), not land history.  
  *Enforced by:* step note; this ledger
- 20 Oct 2026 13:20 · **BLGF-REVIEW** · Jonathan: “acknowledge receipt of the 4 Sep letter (and the 24 Aug letter) and make ONE ask … within 15 working days (RA 6713 Sec. 5(a))”  
  **Lesson:** Acknowledge an office's letters when it asks for an acknowledgment. A statute cite is allowed when Jonathan instructs it, worded to match what the law actually requires.  
  *Enforced by:* DRIP_BLGF_ACK_DRAFT.md; per-item override
- 20 Oct 2026 12:35 · **CV6839-LBP-BALANCE** · Jonathan: “make the draft from jonzschoche@gmail.com”  
  **Lesson:** Jonathan may override the thread's account per item; the override is recorded on the step.  
  *Enforced by:* step_plan.send_account; 005 account rule
- 20 Oct 2026 12:30 · **CV6839-LBP-BALANCE** · Jonathan: “test it against the 6839 legal strategy”  
  **Lesson:** Test every drip against its matter's strategy file. For CV 6839: write for Patricia as one heir (never "the heirs"), ask what is needed to release one heir's share, and keep interest out.  
  *Enforced by:* CV6839_WRIT_COLLECTION_PATH.md; LBP letter v2

## On specific drafts

- 20 Oct 2026 14:47 · **CV26360-PROV-ASSESSOR step 1** · Jonathan: “The declarations we are looking for are for improvements (buildings/structures), not the land history”  
  **Lesson:** (to distil: revision v2 shows how it was applied)  
  *Enforced by:* drip_comment #3
- 20 Oct 2026 11:30 · **LGU-COMPOUND step 1** · Jonathan: “lets also copy the blgf as well as maximo magana”  
  **Lesson:** A cc to supervisors is allowed only on Jonathan's per-item instruction, marked "for information".  
  *Enforced by:* 005 SLEEP DOCTRINE cc exception; step note "cc per Jonathan"
- 20 Oct 2026 09:19 · **CV6839-LBP-BALANCE step 1** · Jonathan: “Test vs CV6839 strategy: speak for Patricia as one heir (not 'the heirs'); ask what LBP needs to release one heir's own share; keep interest out”  
  **Lesson:** (to distil: revision v2 shows how it was applied)  
  *Enforced by:* drip_comment #1
