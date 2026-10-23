# DRIP FEEDBACK LEDGER (internal, never outward)

*Live, regenerated 23 Oct 2026 12:39 PHT from `drip_feedback`. Read this before drafting, revising or even considering a drip. Jonathan's own words are quoted; the lesson is the rule the stack now follows; 'enforced by' says where.*

## The Charter (governs everything below)

- 20 Oct 2026 16:34 · **DRIP_CHARTER** · Jonathan: “Adopt it”  
  **Lesson:** The Drip Charter (Q1–Q12, 20 Oct 2026) is adopted as the drip's governing document; it outranks the steering guide, spec and templates.  
  *Enforced by:* drip_card.py line 0 CHARTER; 005 spec header; steering guide §0

## Rules for every drip

- 23 Oct 2026 08:00 · Jonathan: “I dont think the drip should be creating long term legal positions its job is to follow”  
  **Lesson:** The drip follows decided positions (records asks, acknowledgments, tracers, status asks, clocks). Legal stands (e.g. Land Bank challenge, SB road-lot completion) are legal-desk papers Jonathan adopts first; only then does the drip carry their follow-ups.  
  *Enforced by:* memory feedback-drip-follows-not-positions; this ledger
- 23 Oct 2026 08:00 · Jonathan: “take ownership: five-table consolidation and the single logging step”  
  **Lesson:** Everything enters the drip through scripts/drip_log.py (sent, drafted, receipt, reply, refused, rule); clocks start only on a corpus proof document; the nightly reconcile logs office mail and our sends nobody logged.  
  *Enforced by:* scripts/drip_log.py; migrations/drip_core_2026-10-23.sql
- 23 Oct 2026 08:00 · Jonathan: “the drip needs to scan all matters and suggest the next target based on importance ad calendar”  
  **Lesson:** Every night the drip ranks next targets across all matters by matter weight x urgency + calendar anchors (DRIP_PRIORITIES.json). NOTE: conflicts with Charter §9 (all matters equal) until Jonathan amends it.  
  *Enforced by:* drip_board.py pick_targets; landtek-drip-nightly.timer
- 21 Oct 2026 14:45 · Jonathan: “I think we sent too many emails about that make sure we dont do that again”  
  **Lesson:** One message per office per 15 working days (~21 days) unless the office has replied since. Corrections and add-on asks WAIT for the reply or go by phone/text. Run scripts/drip_cadence_check.py on every recipient before drafting; BLOCK means do not draft.  
  *Enforced by:* scripts/drip_cadence_check.py (pre-draft); drip_event 'sent' log
- 21 Oct 2026 13:15 · Jonathan: “theyve already offered ... your denr letter again seems off”  
  **Lesson:** Before any tracer, read the office's LATEST reply: if it already offered release/pickup (DENR SMD 24 Sep: 'personally pick up… Window 3'), the next step is COLLECTION, not another letter asking whether it is ready. (Paracale DENR tracer of 21 Oct re-asked readiness.)  
  *Enforced by:* X16 history read; pre-draft gate HISTORY line
- 21 Oct 2026 08:00 · Jonathan: “we have evrything in the corpus for 6839 already / we have all these things”  
  **Lesson:** CV 6839 and SP 2680 records asks are retired: search the corpus before asking any office for what we already hold.  
  *Enforced by:* drip_card 4 HISTORY; this ledger
- 21 Oct 2026 08:00 · Jonathan: “then they can throw out my case and I will have to start over”  
  **Lesson:** No drips to RTC Branch 41 while SP 2680 is pending.  
  *Enforced by:* this ledger; posture
- 21 Oct 2026 08:00 · Jonathan: “lets start to engage the barangay captains not individuals barangay records”  
  **Lesson:** Barangays: ask the Punong Barangay for barangay records, never individuals; deliver by rider; capture stamp, receiver name, time and photo; a refusal goes by registered mail with a Taglish cover letter, cc Mayor and MLGOO (MLGOO copy as JPEG).  
  *Enforced by:* BRGY-* ladders; BARANGAY_RECEPTION_LOG_2026-10.md
- 21 Oct 2026 08:00 · Jonathan: “lets use their form and email them”  
  **Lesson:** When an office has its own request form, use it (RD: LTCP Form 0012 v2.0, official PDF on lra.gov.ph; OCC: SC-OCA Access to Information Request Form).  
  *Enforced by:* ladder folders RD-T52540-ENTRIES, OCC-NOTARIAL-ASIS-BELEN
- 21 Oct 2026 08:00 · Jonathan: “I think we sent too many emails about that make sure we dont do that again”  
  **Lesson:** One touch per office per 15 working days (checked as 21 calendar days); extras go by phone or wait for the office's reply.  
  *Enforced by:* scripts/drip_cadence_check.py; drip_board picker channel
- 20 Oct 2026 18:30 · Jonathan: “we send by email first and then hand delivery for the rtc”  
  **Lesson:** Court/registry records requests go by e-mail first (e-signed PDF + SPA), then hand delivery with the paper set for the receiving stamp. Every e-mailed PDF is compacted (scanned annex pages re-rendered as JPEG) and must be under 8 MB; the 20 Oct RD e-mail went out at 14 MB.  
  *Enforced by:* drip_stager.compact(); OCC rtc1daeocc@judiciary.gov.ph (Jonathan 20 Oct)
- 20 Oct 2026 17:54 · Jonathan: “I dont see the july 13 email that accompanys it”  
  **Lesson:** Replies in a thread must carry the quoted original underneath (never replace the whole body). Check outbound attachment size: >10 MB to a .gov.ph address risks a silent drop; prefer a short PDF + hand delivery.  
  *Enforced by:* stager/draft builder: quote original; size check
- 20 Oct 2026 17:12 · Jonathan: “what about the participants that the csc is in charge of overseeing? / reply drafts for the appropriate office is fine”  
  **Lesson:** Reply-in-thread never means reply-all: strip any respondent (e.g. mercedesmunicipality@gmail.com on CSC/ARTA transmittals) and unrelated offices from To/Cc; one office per draft, one ask each. Read the agency's own letter for what it did NOT cover (OAC-L 270 forwarded everything to OMB on the Mayor's elective status alone; the appointive CART members are CSC jurisdiction).  
  *Enforced by:* drafting step: recipients rebuilt explicitly; X17
- 20 Oct 2026 16:48 · Jonathan: “make the draft with some tagalog casual in there”  
  **Lesson:** Routine drips carry light, polite Tagalog warmth (Magandang araw po, Malaking tulong po ito, Maraming salamat po) inside an English letter; never slang, never in strategic instruments.  
  *Enforced by:* drip voice (calm_routine); reviewed per draft
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
- 20 Oct 2026 08:00 · Jonathan: “(lesson from lost quotes and dropped mail) replies must carry the original; never reply-all; keep attachments small”  
  **Lesson:** Replies go in the office's thread with the quoted original; recipients rebuilt explicitly (never reply-all); attachments under 8 MB from corpus originals (.gov.ph servers drop large mail silently).  
  *Enforced by:* Mail.app staging scripts; this ledger

## By office / official

- 21 Oct 2026 07:17 · **RTC Br. 41 Daet** · Jonathan: “then they can throw out my case and I will have to start over”  
  **Lesson:** No direct drip to RTC Branch 41 (Judge Dating) while SP 2680, Jonathan's own guardianship petition, is pending there. Records it holds (e.g. SP 2156) come through counsel (Barandon subpoena in 26-360) or after 2680 is decided. Generalizes: never send a records ask to a court that is deciding one of the client's own pending petitions.  
  *Enforced by:* posture check (X17 extended to courts hearing the client's own petitions); step_plan CV26360-BR41-SP2156 skipped
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

- 21 Oct 2026 08:00 · **LGU-SB-STREETS** · Jonathan: “the sb letter is not a drip its a cosequential legal stand which we are not here to pump, just need to know what they ruled”  
  **Lesson:** To the SB on the road lots: status-only ask (what action was taken on the 3 Oct 2025 referral); no requests to name or register.  
  *Enforced by:* LGU-SB-STREETS step 1; SB-ROAD-LOTS-COMPLETION withdrawn
- 21 Oct 2026 07:15 · **SP2680-BOTOR** · Jonathan: “we have all these things this is not a neccesary drip”  
  **Lesson:** SP 2680 open asks in STATUS (resetting order/time, Gerry's letter, bond, statement of account) are already in Jonathan's hands; STATUS 'Open asks' is stale. Before proposing a counsel drip, ask whether the item is already held instead of trusting a desk STATUS file.  
  *Enforced by:* X16 history read; SP2680/STATUS.md marked
- 20 Oct 2026 17:05 · **CV6839-FINALITY** · Jonathan: “we dont need this we have evrything in the corpus for 6839 already”  
  **Lesson:** CV 6839 needs no records asks: the judgment and writ of execution are already held (docs 723, 802). Before proposing a records ask, search the corpus AND Jonathan's own past statements for the item; the live CV 6839 front is authority to collect (guardianship/Rule 95), not paper.  
  *Enforced by:* drip_fact cv6839.writ; step_plan CV6839-FINALITY 1-4 skipped; X16 history read
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
