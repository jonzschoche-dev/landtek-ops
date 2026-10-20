# Agent 005 — the Drip  (obligation-clock engine: offices stay on their toes because nothing lapses silently)

*Spec (no code). Written 2026-09-11. Operator's name for the idea: "the drip — focused communications
out to offices to keep them on their toes." The manual prototype already exists and WORKS:
`case_work/MWK-001/DEMAND_CLOCK_LEDGER_2026-09.md` (7 officer clocks + the DILG edition track). This
agent turns that ledger into typed rows + a $0 sweep + staged instruments — with the operator's own
8-Sep process flag encoded as truth-tests. NB: `landtek-geometry-drip.timer` is an unrelated OCR
drain; this spec owns the name "drip" for correspondence from here on.*

---

## v2 ALGORITHM: the drip as the stack's fabric (redraft 2026-10-19 · **APPROVED by Jonathan 2026-10-20 07:40 PHT with Grok's CHANGEs** · drip_sweep stays SHADOW)

*Why v2: after five weeks live the engine is sound but starved. It has 8 rows, all MWK-001, and **0 served**,
so 0 clocks run, while about 60 officer/duty targets sit in desk markdown (intake dry run 2026-10-19:
`ops/drip/DRIP_INTAKE_RANKED_2026-10-19.md`). v2 does three things. It makes the registry complete. It makes
every row cross-referenced and checkable. And it ties the drip into the **reasoning equilibrium** (the inquiry
spine: who is asking → matter_facts → fact_fields → matter_brief) and the **relationship equilibrium** (A76
propagation). The drip stops being a side engine and becomes the obligation layer of the one loop in MASTER_PLAN
§0: **goal → front → obligation → served → clock → result**. Where v1 text below conflicts with this section,
this section wins once approved.*

**Respects: A1, A2, A5, A20, A21, A39, A65, A68, A71, A74, A75, A76** · standing orders §0.4.1–7 ·
speed doctrine §0.11 · bridge §0.12

### v2 GO and the applied CHANGEs (2026-10-20, DRIP_THREAD Grok 07:35 ANSWER; migration `migrations/drip_v2_fabric_REVISED_2026-10-20.sql`)
Jonathan's GO (20 Oct 2026 07:40 PHT) covers this spec, the revised fabric SQL and the law ingest. Applied on the
VPS in one transaction after a rolled-back dry run. Where any text below conflicts with this block, this block wins.
- **C1 No receipt, no clock (DB).** CHECK `drip_running_clock_needs_proof` (validated): `served_running`,
  `replied_not_performed`, `partial`, `lapsed` require `served_at` AND `service_proof_doc_id`.
- **C2 Tone = calm/routine (20 Oct tone doctrine).** "The drip is not meant to be combative; it's meant to make them
  go to sleep while the record builds." Outward registers (`official`, `supervisor`, `phone_drip`) are
  `calm_routine`: ordinary administrative follow-up, courteous and plain, one small easy ask, a polite reply-by
  date, a reference to the last letter by its date, no effusive praise, no adjectives about conduct. `very_warm`
  no longer exists. Escalation language only at the complaint rung and only after Jonathan's go.
- **C3 Lint.** `threat_early` refuses "Ombudsman", "failure to comply/act" and "complaint" at editions/R1
  (audiences official · supervisor · phone_drip). `internal_goal_leak` refuses internal labels (rope-a-dope,
  counter-punch, rope phases, patient record, walk-away, "go to sleep") in every outward audience incl. counsel.
- **C4 15-working-day floor (DB).** No `escalation_rung` may leave `pending`, and no R1/R2/R3 `drip_instrument`
  may be approved/printed/served, until 15 working days from **proven** receipt (day of receipt excluded,
  Sat/Sun skipped; Rule 22 §1, legal_chunks 3837; RA 6713 §5(a), chunk 133). Holidays come from
  `drip_nonworking_day`, EMPTY until the 2026 proclamation is ingested and verified [NEEDS-COUNSEL-VERIFICATION].
  The 5-day reiteration is a courtesy only (Legal 00:15). Credibility debt ranks the next courteous edition,
  never "stage a rung within 24h".
- **C5 Amount roles.** `fact_fields.amount_role` ∈ {at_stake, cost, valuation, unknown}. CV6839 at-stake =
  ₱5,124,922.47 (TOTAL of the "Unpaid Amount" column, doc 377; matter_objectives 14 money target). ₱48,250,900 =
  `valuation` (FMV) on all 25 rows; it never enters the money input.
- **C6 Patient record.** ARTA RA 11032 §21 is not a general period for routine asks (Sec. 4(f), chunks 34/40);
  anchor on RA 6713 §5(a). Main legal risk is RA 6770 §20(3) "vexatious / bad faith" (chunk 1969); the
  anti-salvo rule and calm tone are the controls. Rows with `goal_set_by='proposed:*'` never feed the pick.
- **Not in this GO:** hearing rows and calendar W1–W6 wiring (on hold until Claude and Legal agree); intake
  `--apply`; any timer change; any send path. `drip_sweep.py` behaviour is unchanged and stays SHADOW.

### The fabric in one paragraph
Every front's next move toward an office is an **obligation**: one officer, one duty, one instrument, one clock.
Obligations are the edges the company pulls on. The **reasoning equilibrium** tells the drip what is true:
which facts are verified, which amounts are at stake, which dates are live or stale, and which contradictions
are open. The **relationship equilibrium** tells the drip what each move touches: the ego-network of the
obligation's matter, the keystones it cascades into, and the client wall it must not cross. The drip in turn
feeds the equilibrium: every state change (approved, served, replied, lapsed, performed) is a perturbation that
propagates before anything surfaces. **Accuracy lives inside, gentleness at the edge.** The pick is computed on
the full, hot graph (internal plane). Only the dosed delta (A71) in the recipient's form (A75) reaches a person.

### Stage 0. INTAKE: the registry is complete (weekly, Monday sweep)
1. **Harvest.** Read every desk instrument (`case_work/**`: DEMAND_*, NOTICE_*, *_Request*, CSC_*, OP_*,
   TRANSMITTAL_LOG, STATUS.md) plus `matters`, `work_orders` and `ombudsman_candidates`. Emit one candidate per
   **officer + one statutory duty + one instrument** (the v1 splitting rule). An LLM may *propose* candidates
   (capability `extract`, via the model router). A row lands only after the Stage 1 validators pass. The model
   proposes; Postgres disposes. Tool: `scripts/drip_intake.py` (dry run by default; `--apply` commits).
2. **Target test.** A public office or officer, or an institution with a legal duty, owing a specific act we
   requested, demanded, filed or paid for. Not targets: private litigants, transferees, own counsel, heirs,
   clients. Those belong to the strategy and litigation lanes.
3. **Finest matter wins.** A row carries the most specific `matter_code` (e.g. `MWK-OP-PETITION`, not
   `MWK-001`), because the relationship graph can only tell rows apart by matter. A client code is allowed
   only when no matter row exists, and it is flagged for re-homing.
4. **Land as `draft_held`** with its full `escalation_rung` ladder (Stage 4). Upsert on `drip_dedup`. Never
   delete and reinsert.
5. **Coverage invariant (A74 shape).** Every outward instrument under `case_work/` maps to a row or carries a
   written exclusion reason. The weekly diff is a finding with a re-check condition, never a silent gap.

### Stage 1. CROSS-REFERENCE: every row reconciles (deterministic, $0, every tick)
A row is **clean** only if all checks pass. A failure blocks clock start and opens a finding with its re-check
condition. Nothing is auto-fixed.

| # | Check | Against | Fail ⇒ |
|---|---|---|---|
| X1 | the matter or client exists, and its client equals the instrument's and the proof doc's | `matters`/`clients`, `_client_of()` | block (A5) |
| X2 | the instrument resolves to a repo file, a `documents.id` or a `gmail_messages.id`, and names this officer and duty | repo + corpus | block |
| X3 | `statutory_basis` / `clock_rule` cited verbatim and present in the law corpus | `doc_requirements_law` / `legal_authority` | block the clock; the row may sit held |
| X4 | proof of receipt = a same-client `documents.id` showing receipt **by this office** of **this instrument** | corpus | no clock (corpus-proof rule) |
| X5 | the officer still holds the office at the instrument date | `entities`, latest mention | `[HUMAN VERIFY]` |
| X6 | the email carries a source and a confidence | `email_source` | strip and flag |
| X7 | the same officer and duty is not live under another matter, docket or OMB lead | registry, `ombudsman_candidates` | merge proposal, never a silent double clock |
| X8 | the counsel gate comes from `matters.lead_counsel`; CV 26-360 defendants route to counsel | `matters` | `held_counsel_route` |
| X9 | edition counters recompute byte-identically from cited anchor dates | SoR | block the edition |
| X10 | calendar, `work_orders` and the markdown ledger agree with the row | `calendar_events`, `work_orders` | finding; the DB wins, markdown regenerates |
| **X13** | **sworn-instrument truth floor**: every factual sentence in an affidavit is `verified` and has an attachment (exhibit test); nothing about anyone's state of mind; no inference | provenance + annex manifest | refuse the affidavit (perjury exposure) |
| **X14** | **notarial validity** on the signing date. Paper: the notary's commission term covers the date (the Exh. L/M/N lesson). E-notary: listed in the SC ENP directory, the certificate's term field is valid, the affiant's ID is unexpired, the affiant is physically in the PH (REN geolocation; never a VPN), and capacity is annexed (SPA + apostille) | notarization record | the rung can't be staged |
| **X15** | **forum intake**: the receiving forum accepts the instrument's form (e-notarized PDF / printout / wet ink) and channel | `forum_intake` | unknown ⇒ one test document first, or the paper/IEN fallback |
| **X11** | **equilibrium consult**: no open `contradictions` row touches the obligation's ego-network facts | `propagate(seed='obligation')` → `contradictions` | **hold the clock or rung; the day's ask becomes "resolve this contradiction"** |
| **X12** | **brief freshness**: the matter's `matter_brief` is not stale, and its deadline isn't marked `stale` | `v_matter_brief_staleness`, `angle_status.deadlines` | re-materialize first; a stale date never ranks |

**Conflicts are contradictions, not notes.** When harvest sources disagree on a fact a row depends on (e.g. the
Macale protest dated 7 Jul vs 13 Jul), the intake writes a `contradictions` row (`kind='drip_xref'`, the
competing values, the fact or doc ids). A65's register then owns it, and X11 holds the row until it is
resolved. The drip never picks a value.

**Proof candidates are proposed, never applied.** A likely receipt is noted as a proof candidate. A clock starts
only on `drip_sweep.py --record-service <id> --proof-doc <documents.id>` after a human confirms.

### Stage 2. STATE MACHINE: every transition is a perturbation
`draft_held → approved → served_running → {replied_not_performed | partial | performed | lapsed} →
consequence_staged → consequence_filed` (plus `held_counsel_route` and `withdrawn`, which never tick).
- **`approved`** (new) is Jonathan's go for that item, recorded with its approval reference (A39). It separates
  "waiting on Jonathan" from "waiting on service". The **closer** owns `approved → served_running`: it emits an
  officer task (print · serve · LBC · collect the stamped copy · ingest) and watches for the proof doc.
- **Every transition calls `equilibrium_propagate.propagate('obligation', id)`** before anything surfaces. This
  is the A76 law: no output from an unpropagated perturbation. Shadow mode first. It ledgers to
  `propagation_log` and emits nothing. The transition also writes a `drip_event` and a `work_orders` /
  `cos_bridge --pulse` perturbation.
- **Every transition re-materializes the matter's brief** (`materialize_matter_brief.py --matter`). The brief's
  `angle_status.drip` slice (open · approved_unserved · clocks_running · next_lapse) keeps inquiry answers
  ("where are we with the Assessor?") and the pick reading the same state.

### Stage 3. TICK (daily 23:30 UTC)
Lapse → stage the lowest pending rung as an `outward_action` (T3). Edition dues → stage the edition with
counters advanced. `partial` → same-day "partial ≠ compliance" draft. Calendar sync gives no date to unserved
rows. **No send path exists** (grep-floor truth test).

### THE SLEEP DOCTRINE as hard gates (Jonathan, 20 Oct 2026: "noncombative, put them to sleep building a case over time"; PROPOSED delta `migrations/DRAFT_drip_v2_delta_sleep.sql`, not applied)
Trigger: the LGU Schedule packet (compensation, ₱ amounts, the office's own declarations annexed, supervisors cc'd)
was judged "highly strategic and against the mandate". C2 set the tone; this makes it **structural**, so a
strategic document can't leave as a routine drip.

**Principle.** The record builds from receipt, silence and the next courteous letter, not from what a letter argues.
All strategy lives in the internal plane (goals, tracks, pressure, meter, ripeness). The outward plane is dull on
purpose.

**A routine drip (first ask, editions, R1) is:**
1. one small, ordinary ask any clerk could answer (a copy, a status, a note that none exists);
2. neutral identification: who writes, in what capacity, the reference number, the previous letter by its date;
3. the easy yes (we pay, collect, or accept e-mail or a short note);
4. a polite reply period stated plainly, with no statute cited;
5. at most ~250 words and one page. The only annex is the authority (SPA).

**Never in a routine drip** (lint class `strategic_tell` + code checks):
- peso amounts or rates;
- posture words: without prejudice, reserved, accrue, compensation, occupy, demand, liability, damages, remedies,
  unlawful, registered owner;
- statute citations;
- any forum named;
- cc to supervisors or other offices (`supervisor_cc_early`), **unless Jonathan directs it for that item**. Then the
  cc is "Copy furnished, for information" only, to offices whose mandate touches the ask, with nothing addressed to
  them in the body. The override is recorded with the item's `approval_ref` (first use: LGU-COMPOUND step 1, cc
  Provincial Assessor Magana + BLGF RD Doctolero, 20 Oct 2026);
- adverse annexes: the office's own declarations, comparators, admissions (`adverse_annex_early`);
- over-length (`routine_too_long`).

**The cost leaves the routine plane.** The cost line moves to `burden_line_from_rung = 2` (from 1). The running cost
is computed and logged internally every cycle (`loss_line`). It is first stated, as sworn neutral fact, in the R2
affidavit, and only on go.

**Strategic instruments are later rungs.** Schedules of compensation, damages demands, comparator exhibits and
supervisor packs wait in `HELD_LATER_RUNG/` until the record makes them inevitable. Each needs its own go.

**The trade-off, stated once.** Compensation for use accrues only from a demand (Art. 1169). Each month the
Schedule waits is ₱59,521.00 of the LGU stream that can't be claimed later. Jonathan sets when it moves.

### BABY-STEP LADDERS: how sleep still reaches the goals (Jonathan, 20 Oct: "baby step to our legal and financial goals"; PROPOSED `migrations/DRAFT_drip_v2_delta_baby_steps.sql`)
Sleep is the *form*; the ladder is the *direction*. Every goal is decomposed into the **record elements** it needs
(a due request with proof of receipt, an answer or a recorded silence, an admission such as "none on file", an
official receipt, a demand). Each baby step is **one routine ask that earns exactly one element**:
- 15 working days apart from proven receipt;
- staggered per office cluster;
- passing the sleep lint.

**Strategic instruments are the last step of a ladder** (CHECK: never step 1), reached when the earlier elements are on
record, so the strategic step reads as the obvious next thing and not as an attack. `step_plan` holds the ladders, and
`v_next_baby_step` feeds the Stage 5 pick, which ranks them on the same money → deadline → leverage order.
`goal_element` is internal only.

First four ladders (seeded in the draft):
- **LGU-COMPOUND:**
  1. a copy of the record on file, or "none" (drafted);
  2. a courtesy edition;
  3. openness to an arrangement (no terms);
  4. *the Schedule* (₱59,521/mo starts; Jonathan's go).
- **MACALE-RPT:**
  1. status of the 13 Jul protest decision;
  2. *pay ₱14,391.50 under protest* (Jonathan's money call; makes the injury actual);
  3. a refund request; then R1 to the Provincial Treasurer.
- **ABLA-SERVICE:**
  1. status of the paid 20 Jun 2025 request, partial release welcome;
  2. a courtesy edition; then a calm R1 to the Provincial Assessor.
- **CV6839-COLLECT:**
  1. certified decision + Entry of Judgment from the OCC;
  2. Land Bank's statement of the balance. These are plain records requests on the road to ₱5.12M principal plus
     interest.

### ONE BRAIN, ONE LOOP (Jonathan, 20 Oct 2026: "using two AIs is not working; we need to trigger from a single input and output")
**Claude owns the drip end to end**: history read, ladder step, drafting, the legal check against `legal_chunks`/the law
corpus, the sleep lint, the review queue, and staging on Jonathan's word.
- **Input:** Jonathan, in the Claude session ("next drip", a comment, "make the draft").
- **Output:** one draft at a time (`scripts/drip_draft_queue.py --next`), then a staged draft in the thread's origin
  account or a paper print set.
- **The Claude↔Grok ping-pong (Drive `Drip/to-claude` / `from-claude`, `DRIP_THREAD.md`, the
  `com.landtek.claude-pingpong` LaunchAgent) is retired for the drip.** Grok and Legal briefs are no longer an input.
  Anything they produced before 20 Oct (Drip 01, the tone doctrine C1–C6) has been folded into this spec and the
  queue.
- Rule §0.12.4 (one voice per decision) is satisfied by construction: the drip has exactly one brain and one channel
  to Jonathan.

### THE REVIEW QUEUE: constant movement (Jonathan, 20 Oct 2026; LIVE: `migrations/DRAFT_drip_v2_delta_review_queue.sql` + `..._baby_steps.sql` applied 20 Oct)
The drip is never idle. At least `drip_queue_config.min_awaiting_comment` (now **4**) drafts always wait for
Jonathan's comment. Tool: `scripts/drip_draft_queue.py`.
- **Fill:** take the next routine step per ladder in `priority_ladders` order (money first). It needs a letter
  file, the live sleep lint, and `send_account`/`thread_ref`. The step goes in as `awaiting_comment`. A step with no
  letter yet becomes a `drip_draft_needed` work order for the desk.
- **One at a time:** `--next` shows Jonathan the single next draft.
- **Comment → revise:** `--comment` records his words (`drip_comment`) and opens a `drip_revise` work order. After
  the edit, `--revised` re-lints, bumps the version and puts it back in front of him. Revisions jump the queue.
- **"Make the draft":** `--ready ID REF` sets `ready_for_draft` with his approval reference and opens a
  `drip_stage_draft` work order (e-mail draft in the thread's origin account, or the paper set). Staging is its own
  explicit step. Nothing is ever sent by the system.
- **Every action refills the queue,** so movement is continuous. Counsel-gated ladders never enter the queue.

### SENDING ACCOUNT AND THREAD (Jonathan, 20 Oct 2026)
- **The account is the thread's origin.** Every e-mail drip goes from the account where that office's thread already
  lives: **jonzschoche@gmail.com** by default for MWK (agency threads arrive there), or **jonathan@hayuma.org**
  where the conversation started there. Never switch accounts mid-thread.
- **Same thread, always.** If any prior message with that office on that subject exists, the drip is a *reply in
  that thread* (keep the subject; the Re: line in the letter may be more specific). A new thread only when none
  exists, and the new thread's account becomes the origin for that office from then on.
- **Find the thread first.** This is part of X16: the history read records `send_account` and `thread_ref` (the
  Gmail thread id / message id replied to). A draft without both isn't stageable.
- **Staging (unchanged).** Drafts only, never sent by Claude. jonzschoche@gmail.com goes through Mac Mail.app account
  "Google" (osascript `reply … with opening window`, save only). jonathan@hayuma.org goes through the Gmail
  connector (`create_draft` in the thread). Jonathan reviews and presses Send. A draft is created only when
  Jonathan says the item is ready.

### HISTORY BEFORE EVERY ASK (Jonathan, 20 Oct: "we are asking for something he has refused to give; the stack should understand where we are")
Sample 1 re-asked the Mayor for "the document on file" for the compound. He had already answered that (21 May 2025,
doc 304: a 1953 Deed of Donation, Resolution No. 21, a 1966 tax declaration) and never produced any of them despite
our 23 and 28 May 2025 requests (doc 343). **X16, ask history (blocking, before drafting):** for this office ×
subject, read the ledger of prior asks, answers, refusals (with the grounds given), silences and what we already hold.
- **Never re-ask a refused or answered item in the same form.** The next step must do one of three things:
  - **(a) Narrow** to the smallest piece they can't reasonably refuse (e.g. the *particulars* of the documents they
    themselves cited);
  - **(b) Route** to an alternate custodian (RD, notarial archives, Provincial Assessor, SB Secretary), at our own
    expense;
  - **(c) Build on their own words.** Quote their earlier statement neutrally, and ask the next small thing it
    implies.
- **Their prior statements are anchors.** A routine letter may cite *their* letter by date and restate what *they*
  said. That is neutral and sleepy, and it locks the position on record. It never characterizes or contradicts it.
- **What we already hold** (e.g. the unsigned 1953 copy) is never asked for, and never revealed in a routine drip.
- **Data:** `step_plan.history_ref` points to the ledger rows (docs/gmail ids) the step was planned from. A step
  without a history read is not draftable.

### Default posture: patient record (operator, 2026-10-20) — INTERNAL label "rope-a-dope", never outward (lint C3)
For every officer and office row, the drip runs the **patient-record doctrine** (`docs/RELATIONSHIP_EQUILIBRIUM.md`
§7.6) by default:
- **Patient.** Courteous, lawful, staggered asks.
- **Editions, not threats.** Each edition advances the day counters; it doesn't threaten.
- **Ripe before escalating.** Climbing to the supervisor or notarized rung needs the ripeness conditions. A bare
  lapse isn't enough.
- **One counter-punch.** When the six conditions are met: one forum, one officer, the ripest count.
- **Never instigation.** No pretext, no inducement, no salvo.

The exception is G1/Game A: where delay blocks a money front, that front moves in a forum that can compel, and
the rope keeps running on the officials in parallel. Each pick shows the row's rope phase (Rope 1–4 /
counter-punch) and its ripeness count (n of 6), so you always see how close each official is to a fileable case.

### Stage 4. LADDER: upward, never back at the same officer
Rungs are attached at intake, all addressed **upward**: **R1 Reiteration** to the supervising office (counters
advanced, proof annexed) → (no rung before **15 working days from receipt**, RA 6713 §5(a)) **R2 Escalation**, the same pack plus a **remote-e-notarized Affidavit of Facts and Service** by Jonathan as AIF (the letter itself stays unsworn; A.M. No. 24-10-14-SC, 4 Feb 2025, remote electronic notarization by live video, PDF/PDF-A; research: `case_work/LandTek-Corp/RESEARCH_DIGITAL_NOTARIZATION_2026-10.md`; agency acceptance of e-notarized PDFs unconfirmed, so run one test document first), to the next supervisory tier
→ **R3 Consequence forum** (CSC-RO V for appointive officers; the Ombudsman for elective officers and §3 counts;
LBAA; the courts through the matter's counsel). Each rung's annex pack is the next rung's exhibit pack.
**Floor (C4): no rung before 15 working days from proven receipt (DB trigger).** **Stagger, never salvo**, computed on the graph: at most one new rung per **office cluster** per week. Offices
that share an ego-network (the Mayor, the MLGOO and the DILG RD on the same matter) are one cluster, so
pressure accumulates by inevitability, not volume.

### Stage 5. DAILY PICK: guided by the equilibrium, dosed at the edge
**Strategic layer:** candidates first pass the gates in `docs/RELATIONSHIP_EQUILIBRIUM.md` §7: G1 position fit
(the forum can grant the remedy), G2 prerequisites met, and G3 truth floor. A failed gate turns the gap itself
into the candidate. The order below is the §7.2 strategic order. It differs from the v1 order in two places: an
un-pulled lapse (credibility debt) ranks right after money, and "unblocks" is computed as goal leverage × keystone
cascade.

**Candidates:** open rows in `draft_held·clean` (needs go), `approved` (needs service), `proof_candidate` (needs
confirm), `lapsed` (needs a rung go), `partial`, a due edition, and any open `drip_xref` contradiction (needs a
ruling).

**Score, lexicographically, on internal-plane inputs only (all sourced):**
1. **Money / resolution value.** Only **verified, typed amounts at stake**: a judgment principal, a protested
   tax, a paid but unrendered fee. Fees and costs never rank (`money_kind='cost'`). Untyped `matter_brief.amounts`
   don't count until they are typed (Stage 7). Then result-closing value: a lapse that ripens a CSC or OMB count,
   or a performance that ends a front.
2. **Deadline proximity.** The nearest **live, sourced** date: a court setting, a running clock's `due_at`, or an
   edition due. A brief date marked `stale` scores zero and raises a "re-date this front" ask instead (§0.4.1).
3. **Unblock count, from the graph.** The number of distinct matters and keystones in the obligation's ego-network
   (`propagate` → `cascades_touched` + matter nodes), not a hand-written list. That is cross-pollination (§0.4.6)
   computed rather than claimed.
4. **Goal linkage.** An obligation tied to a dated `client_goals` front outranks an unlinked one at an equal
   score. A goal with no dated front surfaces as its own ask (§0.4.1). Communications and goals move the pick
   only by changing these sourced inputs. The formula itself stays fixed (anti-trap doctrine: mechanical,
   reproducible, never model-reweighted).
5. **Tiebreak:** admin-complaint ripeness (`ombudsman_candidates` + the small-players sheet: ripe > building),
   then age in the current state.

**Emission (the edge):** the recipient resolves through `v_inquiry_principal` first. Jonathan = `operator`.
- **Dose** = min(`dose_ceiling`, **2**). S14 and A71 cap it below the role ceiling.
- **Form** (A75) = one yes/no or one blank, plain language. The "why" line is the brief's verified fields
  (`[v: doc]`). Anything inferred carries `[HUMAN VERIFY]`.
- **Cooldown:** 7 days per obligation (`assistant_nudge_log`).
- **Court days** (4 Nov, 11 Nov, 2 Dec, 9 Dec 2026; SP 2680 11 Nov): a good-luck line or nothing.
- **One brain** (§0.12.4): the pick is written to `work_orders`. Exactly one voice delivers it (per the Ping Pong
  proposal, The Drip Bot); every other surface stays silent.
- **Nothing worth it ⇒ nothing.**

### Stage 6. MEASURE (weekly into MASTER_PLAN §0.9)
Registry coverage (mapped/total instruments) · rows clean · **approved but unserved** (the closer gap) · clocks
running · lapses with a rung staged in under 24h · median go→served days · open `drip_xref` contradictions ·
pesos unlocked · propagation coverage (transitions with a `propagation_log` row / all transitions, target 100%).

### Stage 7. Equilibrium changes this algorithm needs
| # | Change | Where | State 2026-10-19 |
|---|---|---|---|
| E1 | `obligation` seed type: the client resolves from `office_obligation`, and traversal enters through the obligation's matter | `scripts/equilibrium_propagate.py` | **built, dry-tested** (ob 3/4 → MWK-001, 145-node ego, 0 cross-client) |
| E2 | Brief marks a past `next_deadline` as `stale` (never replaced) and carries the `drip` slice | `scripts/materialize_matter_brief.py` | **built, dry-tested** (CV6839: 28 Jul → `stale`) |
| E3 | Amount typing: `fact_fields` amounts get a role (`at_stake` / `cost` / `unknown`) from their verbatim span; only verified `at_stake` ranks | `fact_fields` builder | proposed |
| E4 | Intake conflicts write `contradictions(kind='drip_xref')` with owners | `scripts/drip_intake.py` | proposed |
| E5 | Obligations as first-class graph nodes (`obligation→matter`, `obligation→officer entity`) so rows on one matter can be told apart and office clusters computed | `mv_relationship_graph_structural` | proposed (until then, finest-matter rule) |

### Stage 8. OUTPUT CONSTRUCTION and VOICE (tables: `migrations/drip_v2_fabric_REVISED_2026-10-20.sql`, APPLIED 2026-10-20)
- **Internal goal first.** Every obligation points at the matter objective it serves (`serves_objective_id`,
  `how_it_serves`). Each objective carries the six things from §0.4.1 plus `success_criteria` and `walk_away`
  (`matter_objectives`, read through `v_matter_front_card`). These are **internal only**: lint
  `internal_goal_leak` refuses any outward draft that echoes them. A matter whose six things aren't complete
  surfaces as a "set the goal" ask before any office ask. As of 2026-10-20, 0 matters are complete.
- **Voice is data, not prompt text.** `drip_style_register` sets per-audience language, register, limits and
  warmth. `drip_voice_profile` sets per matter × office: the documented relationship, true and specific warm
  openers, **easy-yes offers** (we pay the fee, bring the copies, come at your convenience, accept partial
  release now), gracious closes, and topics to avoid.
- **Calm, routine, effective (live register `calm_routine`, applied 20 Oct; Jonathan: "make them go to sleep while
  the record builds").** Offices and supervisors get courteous, plain follow-up with a required easy yes and a
  gracious close, and no effusive praise. The tone never drops as rungs climb: escalation shows in the addressee and the form. The
  warmth also builds the good-faith-requester element the patient record needs (§7.6). The
  `cold_tone` lint turns "you failed to" into "the request of [date] remains open".
- **Fixed skeletons** (`drip_template`): demand · edition · R1 · R2 (unsworn letter + **Affidavit of Facts and
  Service**) · R3 complaint-affidavit · partial reply · operator ask · task card · phone drip.
- **Notarization (A.M. No. 24-10-14-SC, research 2026-10-20).**
  - *Default:* remote electronic notarization, with Jonathan as affiant (personally and as AIF) through one accredited
    platform.
  - *Affiant routing:* anything needing **Patricia's** oath goes to the US-notary + apostille lane, which is slow. The
    pick prefers instruments Jonathan can swear (G2).
  - *Documents:* PDF/PDF-A, **never pre-stamped with an image signature** (the e-signature is applied on the platform in
    the notary's view). The cover carries a one-line QR verification note for the receiving office.
  - *Records:* `instrument_notarization` keeps the platform, ENP name and commission, notarial book entry, QR/seal id,
    SC database reference and the session video path.
  - *Costs:* fees feed `loss_line` (cost_incurred).
  - *Fallback:* in-person e-notarization, or a paper notary whose commission is checked (X14), wherever X15 says the
    forum won't take e-notarized PDFs. Annexes A–E as in the v1 formula.
- **Lint gate** (`drip_lint_rule`): instigation, early threats, characterization, untagged inference,
  untraceable facts, multi-duty, multi-officer, markup, length, missing easy yes, cold tone, internal-goal leak.
  An instrument can't reach `approved` with a refuse result.
- **Every artifact is a row** (`drip_instrument`: hash, annex manifest, addressee + confidence, lint result,
  approval ref, work order). **The closer** is `drip_service_task` (print · serve · LBC · stamped copy →
  `proof_doc_id` → `record_service`).
- **Pick audit** (`drip_pick_log`): an inputs hash, the candidates with their gates and inputs, at most 2
  chosen, the suppressed ones with reasons, and exactly one delivering voice.

### Build order (agreed Claude ↔ Grok, DRIP_THREAD 2026-10-19 23:58 / 00:05 PHT)
Grok's research (23:58) confirms the gaps: A76 is still shadow, and P3/P4 aren't built. `propagation_log` is
write-only. `drip_sweep.py` transitions don't propagate. `cos_bridge --pulse` has no timer. `client_goals` isn't
linked to the drip. Point 9 is restated by both sides: **communications change the formula's sourced inputs,
never the formula.**
1. Read-only VPS check: the registry, the `propagation_log` schema, and the brief builder in place.
2. Stage 2 in shadow: every `drip_sweep` transition calls `propagate('obligation', id)` (E1, built) and
   re-materializes the brief (E2, built).
3. D5: Ping Pong files and phone drips become `work_orders` rows; `cos_bridge --pulse` goes on a timer.
4. E3 amount typing + `client_goals` links + a read-only `drip_pick` (Stage 5), shadowed next to the live pick
   for 7 days. Then the strategic layer schema S1–S5 (`docs/RELATIONSHIP_EQUILIBRIUM.md` §7.4).
5. A76 P3 (contradictions wired to owners, incl. `drip_xref`) → P4 (tuning ledger). Graduate on negative tests.
Intake `--apply` is separate and needs Jonathan's go after his review of the ranked list.

**Money note (Grok's catch).** For CV 6839 the amount at stake is the **unpaid principal ₱5,124,922.47**, plus
statutory interest. Source: **doc 377** (Yuzon financial computation, 5 Sep 2025; the 376 cite was wrong), whose TOTAL row
shows ₱5,124,922.47 under "Unpaid Amount" and ₱21,635,098.20 under "UA + Interest" (interest as of 09/05/25). Confirm it against
the decision itself. ₱48.25M is the 2015 fee-simple appraisal of Parcel 1 / T-4503, a valuation and not the
judgment, so it never enters the money input.

### Truth tests (v2)
`intake_coverage` · `xref_blocks_clock` (an X1–X4 or X11 failure never reaches `served_running`) ·
`proof_candidate_never_starts_clock` · `ladder_never_same_officer` · `transition_propagates` (every
`drip_event` transition has a `propagation_log` row) · `stale_date_never_ranks` · `cost_never_ranks` ·
`pick_is_deterministic` · `pick_dose_cap` (≤2) · `cooldown_7d` · `court_day_silence` ·
`obligation_seed_refuses_cross_client` · `sworn_facts_verified_only` · `notary_valid_on_signing_date` ·
`no_image_signature_on_enotary_pdf` · `r2_needs_forum_intake_known_or_fallback` · **`rung_before_15_working_days_refused`** (C4) · **`outward_without_approval_ref_refused`** · **`running_clock_needs_proof`** (C1) · **`routine_drip_threat_lint`** (C3) · plus all v1 tests.

### Tech standard (§0.11)
Deterministic Python + Postgres is the permanent core. Models only *propose* (intake, drafting editions),
through the router. Exposed as MCP tools when the CoS MCP lands: `list_clocks`, `record_service`,
`record_reply`, `stage_rung`, `drip_pick`. One owner: CoS runs the loop, Claude builds and maintains the
engine. Shadow first. Each new coupling (E1–E5) logs before it steers, and it graduates on its negative tests.

---

## Mandate (one line)

Track every outstanding demand/obligation on a **statutory clock that starts only at proof of receipt**;
when a clock lapses, **stage the pre-built consequence** (never another letter to that officer); keep
cadence tracks (Schedule of Continuing Default) re-issued with **counters advanced from the record**;
and stage a same-day "partial ≠ compliance" reply when token performance arrives. **Nothing ever sends
itself** — LandTek builds, Jonathan + counsel pull (A21).

Pressure comes from *inevitability*, not volume: every office knows the clock is running, the counter
is public, and the consequence is already written.

---

## The operator's 8-Sep flag = the design's negative space (encoded, not remembered)

The failure mode Jonathan rejected on 2026-09-08 is exactly what a naive "drip" becomes:

| Flag rule (verbatim intent) | Structural encoding |
|---|---|
| "Preparation does not start a deadline" | `due_at` stays NULL until `served_at` + proof; drafting never ticks a clock |
| "A reply is not itself production" | states `replied_not_performed` / `partial` ≠ `performed`; the consequence path survives a paper reply |
| No invented grace periods / lapses | every `due_at` = `served_at` + a **verbatim-cited** `clock_rule`; a row with a due date and no rule is a violation |
| No circular / repeated requests | **on lapse the sweep has NO letter-generation path** — it stages the `consequence_ref`, full stop (standing rule 3: "no further letters to that officer") |
| Don't merge matters | rows carry `excluded_scope` (e.g. Hall parcel → Atty. Botor); the edition generator never joins across matters |
| Working-day math unverified | `day_math='calendar—NEEDS-COUNSEL'` carried on every row until counsel verifies |

---

## Service exists only as a corpus document (operator rule, 2026-09-12)

> *"Unless the evidence is in the corpus, a document has to be assumed NOT served."*

Proof of service is a **`documents.id`** — the received-stamp copy or registry card, ingested — never
free text and never a drafted letter. `service_proof_doc_id` is required by DB `CHECK` for any
`served_at`; the doc must exist and belong to the same client (A5). The default state of every
instrument is therefore **not served**, and a clock can only start from a fact the corpus can show.
(Teope's 26-Aug demand: no proof doc in the corpus ⇒ unserved, no clock — regardless of what any desk
remembers.)

## Three lanes (all staged, none auto-send)

**Lane 1 — Demand clocks (per officer).** One row per officer per obligation. Served (proof of
receipt) → clock runs → on lapse: state=`lapsed`, the **pre-built consequence** is staged as an
`outward_action` work order (T3, human + counsel). Consequences are already drafted: Mayor →
Ombudsman supplemental (rides OAC-L 270); Abla → CSC-RO V verified complaint; Macale → LBAA appeal;
Teope → Ombudsman 1212 already live. *"A demand not followed through re-prices every other clock to
zero"* — so the lapse→consequence edge is the whole game, and it is never skipped and never replaced
by a reminder letter.

**Lane 2 — Edition cadence (the literal drip).** The DILG Reiteration model, generalized: a
supervision-record instrument re-issued on a cycle (~15 days; next ~25 Sep), **same schedule, every
counter advanced, performed rows marked PERFORMED** — counters recomputed from documented instrument
dates in the record (78d §444(b)(1)(x) · 227d SPA · 476d MWK Street · …), byte-reproducible. It asks
for nothing new; it measures. That is "on their toes" without a records-request in sight.

**Lane 3 — Reactive same-day.** Token performance arrives → stage the "partial is not compliance"
reply the same day (game file §4.2). A recorded full performance closes the row and is *marked* on the
next edition — credit given where earned, per the flag.

---

## The instrument formula (operator, 2026-09-11): a very concise letter with attachments

Every drip instrument — demand, lapse notice, edition — is **one cover letter ≤1 page** plus
**numbered annexes that carry all the weight**:

- **The letter** (3–5 short paragraphs, readable by a busy official in 60 seconds): who is written
  to · the one obligation · what the record shows (one sentence, pointing at the annex) · what is
  requested or noticed · what follows on continued default. One point per letter (S14/A71 applied
  to paper). The letter never argues — it *names*.
- **The annexes** prove: Annex A = the schedule/counters (recomputed from the SoR) · B = the served
  instrument(s) · C = proofs of receipt (the clock-starters) · D = verbatim law page · E = any
  comparator/reply being measured. Doc-id-cited, in order, per the distillation doctrine (synthesis
  leads; the document matrix rides behind).
- **Build = the existing bound-PDF machinery** (`case_bundle.py` pattern: cover leading + exhibits
  in order, one PDF per office per cycle). No new renderer.
- **The compounding property:** the annex pack of each cycle IS the exhibit pack of the eventual
  consequence filing — every drip edition is simultaneously pressure on the office and
  pre-assembled evidence for the Ombudsman/CSC/LBAA step. The record builds itself while it drips.

## The splitting rule (operator question resolved 2026-09-11)

**Split by clock, not by item count.** One letter = **one statutory duty + one clock + one
consequence forum** (the ledger already does this by hand — Mayor carries two instruments):

- Sub-items that are elements of the SAME duty stay together as numbered points of one demand
  (permit list → requirement → demolition = one §444(b)(3)(vi) letter, one lapse).
- Different statutory bases / consequence forums = separate letters, even to the same officer —
  each lapse must be provable independently, and a single-duty letter is binary (performed or
  lapsed; no partial-performance games). §3(f)'s "due demand" element is cleanest singular.
- **Stagger, never salvo** — serve as each matures; staggered receipts = staggered clocks =
  the sustained-drip property for free, and no harassment-optics barrage for a respondent to exhibit.
- **Demands atomic, measurement consolidated** — the edition letter is where the whole board
  appears (one Schedule annex, all counters); the officer never gets a pile of demands but
  periodically sees the full picture.
- Never multiple officers on one letter — each receipt = that officer's clock.

## Tables (one migration when built)

```
office_obligation
  id · matter_code · officer · office · obligation (the specific demanded act)
  instrument_ref (served instrument, doc-id/path) · served_at DATE NULL · service_proof
  clock_rule TEXT (statute cited verbatim) · due_at DATE NULL · day_math
  state: draft_held | held_counsel_route | served_running | replied_not_performed | partial
       | performed | lapsed | consequence_staged | consequence_filed | withdrawn
  consequence_ref (the PRE-BUILT next step) · counsel_gate (per-matter counsel, never defaulted)
  excluded_scope · notes · created_at · updated_at

drip_edition
  id · track ('DILG-supervision', …) · instrument_ref · edition_date · next_edition_due
  counters JSONB (row → day-count, each keyed to its source instrument date) · state

drip_event   -- append-only audit: every tick, stage, state change, and who pulled what (A39)
```

## Sweep (`scripts/drip_sweep.py`, daily, $0, deterministic)

1. `served_running` past `due_at` → `lapsed` → stage `consequence_ref` as `outward_action` (T3).
2. `drip_edition` past `next_edition_due` → regenerate schedule (counters from SoR dates, PERFORMED
   rows marked) → stage for Jonathan.
3. Reply recorded (manual in v1) → state transition; `partial` → stage same-day reply.
4. One S14-clean Telegram alert per staged item (one point, no chains). **Zero sends. Zero emails.**

## Seed rows (from the live ledger — states honored exactly)

Mayor ×2 (incl. the heavy §444(b)(3)(vi) demolition clock, encl. Schedule of Declared Parcels) ·
Abla · Macale (lapse-notice → LBAA window) · Teope (verify service first) · **Olaguera =
`withdrawn`** (no 5-Sep tender; no clock, no CSC trigger) · **Engr. Balane = `held_counsel_route`**
(CV 26-360 defendant — anything to him routes through Atty. Barandon; never ticks). DILG track seeds
`drip_edition` with the 10-Sep Reiteration + next ~25 Sep.

## Truth-tests

`no_clock_without_receipt` · `lapse_stages_consequence_never_letter` (asserts no letter artifact is
generated for a lapsed officer) · `reply_is_not_performance` · `no_invented_periods` (due_at ⇒
clock_rule non-empty) · `never_sends` (sweep writes only its tables + work orders; zero
outbound/gmail rows) · `held_rows_never_tick` (withdrawn/held states can never lapse or stage) ·
`matter_walls` (Botor-lane exclusion; editions never merge matters) · `counters_from_sor`
(edition day-counts recompute byte-identical from cited instrument dates).

## Honest limits (v1)

Inbound is **manually recorded** — an office reply becomes a state change when Jonathan/a desk records
it (auto-ingest from Gmail is a later lane, and it must classify reply-vs-production, which is a human
judgment first). Service proof is likewise recorded, never assumed. And every consequence stays
NEEDS-COUNSEL at the trigger per the standing rule — the drip makes pulling the trigger *effortless
and timely*, it never pulls it.

## Non-goals

Auto-send · reminder letters on lapse · new records requests · clocks from drafts · merging Botor's
lane · Engr. Balane contact · working-day math without counsel · replacing the ledger's narrative
(the markdown stays as the human record; the tables are the machine's).
