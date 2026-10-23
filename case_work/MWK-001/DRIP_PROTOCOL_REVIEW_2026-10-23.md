# Drip protocol review — 23 Oct 2026 (internal, never outward)

**What this is:** a check of the drip against its own design, written for Jonathan to review and refine. It does not replace the governing documents. Those remain:
- the **Charter** (`case_work/MWK-001/DRIP_CHARTER.md`, adopted 20 Oct 2026, corpus #18491), which governs everything;
- the **algorithm spec** (`agent_specs/005_drip.md`, corpus #18383);
- the **steering guide** (#18382) and the **feedback ledger** (#18479).

Corrections to the protocol go into those files, never into a parallel document.

## 1. The drip in one paragraph (as designed + as decided this week)
The drip keeps every pending matter moving by **following decided positions**: small, calm records requests, acknowledgments, tracers and status asks to offices.
- It records **proof of receipt** and runs a **15-working-day clock** (RA 6713 §5(a)).
- When an office is silent it goes **up the chain**, still partner-toned. It never sends by itself; Jonathan approves.
- It is not a strategy engine. A long-term legal position (e.g. challenging Land Bank's release process, asking the SB to name and register road lots) is legal-desk work that Jonathan adopts first. The drip then carries its follow-ups (Jonathan, 21 and 23 Oct).

## 2. The pipeline as it actually runs today
Status: WORKING · PARTIAL · STALE (built, not fed) · BROKEN · MANUAL (done in chat by Claude + Jonathan).

| # | Step | Where it lives | Status | Note |
|---|---|---|---|---|
| 1 | Inputs: office mail in | `gmail_watcher.py` (hayuma 15 min; jonzschoche via backup sweep 3 h + nightly) | WORKING since 23 Oct | jonzschoche token was dead ~22 Sep–23 Oct; re-minted, sentinel now watches it; app moved to Production |
| 2 | Inputs: paper proof (stamps, stop sheets) | Drive → `drive_backfill.py` → documents | WORKING | text waits on OCR |
| 3 | Ladders (what we ask whom, in what order) | `step_plan` (172 rows / 44 ladders) + `case_work/DRIP_LADDERS_2026-10/*` (63 folders) | STALE | step_plan last updated 20 Oct; this week's ladders live only as folders + events |
| 4 | Pre-draft gate | `drip_card.py` lines 0 CHARTER, 1 GOAL … 10 CHANNEL | PARTIAL | runs only on step_plan rows; the chat-made drips of 21–23 Oct were not carded |
| 5 | Cadence | `drip_cadence_check.py` (21 days per address) | WORKING | only as good as the 'sent' log |
| 6 | Draft | Claude in chat → Mail.app Drafts (AppleScript) / print sets | MANUAL | the `drip_stager` launchd job (every 3 min) only handles drip_instrument rows, unused since 20 Oct |
| 7 | Approval | Jonathan, one at a time in chat | MANUAL | Charter §6 (batch go per campaign) not in use |
| 8 | Send | Jonathan from Drafts | MANUAL by design | |
| 9 | Log send / receipt / reply | `drip_event` (free-form JSON) | PARTIAL | sends made from Drafts were not all logged; mail-derived sends now fill the gap |
| 10 | Clocks | `office_obligation` + `drip_sweep.py --tick` (07:30 PHT) | STALE | 8 September rows, none served; no clock has ever run here. The real clocks are computed by the board (step 11) |
| 11 | Board + next target | `drip_board.py` nightly 00:00 PHT on the VPS, `DRIP_PRIORITIES.json` | WORKING since 23 Oct | per-client boards in the corpus (#19222 MWK, #19223 Paracale) |
| 12 | Feedback → rules | `drip_feedback` (31 rows) → `drip_feedback_ledger.py` → ledger + guide | STALE | ledger last regenerated 20 Oct; only 2 rows from 21 Oct, none from 22–23 Oct (see §4) |
| 13 | Interface | Drip UI (`drip_ui/app.py`, drip-ui.service, Tailscale 100.85.203.58:8790) | BROKEN for the drip | see §6 |

## 3. The rules (Charter + ledger), short form
1. Speak for **Patricia, a co-owner (Art. 487)**, through her attorney-in-fact; never for "the heirs". Default annex: the **2025 general SPA** (Apostille 61887); the 18 May 2026 SPA stays out of routine asks.
2. **Helpful citizen-partner** tone; no threats, adjectives or forum names. Strategic instruments are never openers.
3. **Up the chain** after a due request + proof of receipt + 15 working days of silence; never a harsher letter to the same official.
4. **Never** contact a respondent in our live proceedings, or a represented party, directly (X17). CV 26-360 defendants go through Barandon.
5. **History before every ask**: never re-ask what was refused or answered.
6. **Cadence**: one touch per recipient per 15 working days (checked as 21 calendar days); one new step per office cluster per week.
7. **Channel**: reply from the thread's origin account (jonzschoche default), in the same thread, quoted original kept; never reply-all; attachments < 8 MB.
8. **Never sends by itself**; drafts only; Jonathan sends.
9. **Drip follows, never sets positions** (23 Oct).

## 4. Rules given in chat 21–23 Oct that are NOT yet in the ledger
Each should become a `drip_feedback` row so the ledger, the gate and any interface read it:
- Too many e-mails to one office — never again; one touch per office (21 Oct) → cadence check *(in ledger as a row, enforced)*.
- Replies carry the quoted original; never reply-all; rebuild recipients explicitly.
- Attachments under 8 MB (.gov.ph servers drop large mail silently); use corpus originals, not Mail.app copies.
- Use the office's own form when it has one (RD LTCP Form 0012; OCC SC-OCA Access to Information form); the official LRA form is on lra.gov.ph.
- Barangays: engage the barangay captain / barangay records, not individuals; paper by rider; stamp + receiver name + photo; refusals → registered mail + cover letter + cc Mayor and MLGOO (MLGOO copy as JPEG).
- No rider-signed notes; Jonathan relays.
- No drips to RTC Br. 41 while SP 2680 is pending.
- CV 6839 / SP 2680 records asks retired: "we have everything in the corpus".
- The SB road-lots letter is a legal stand, not a drip → withdrawn; only "what did you rule" status asks.
- **The drip follows; it does not create long-term legal positions** (23 Oct).
- Next target ranked by importance and calendar (23 Oct) → `DRIP_PRIORITIES.json` *(conflicts with Charter §9, see §7)*.

## 5. Prompts and algorithm pieces in the stack
- **Drip UI system prompt** ("Drip Bot", `drip_ui/app.py` lines 115–118):
  - short Taglish;
  - never sends, has no send tool; creates drafts only, for Go/Edit/Hold;
  - grounds facts in tools and cites [doc #id];
  - quotes the document's own words.
  - It contains none of the Charter rules in §3 or §4.
- **Drip UI tools:**
  - `search_corpus` (keyword ILIKE over all documents; matter filter optional);
  - `get_document`, `read_upload`;
  - `list_drip_queue` (reads `office_obligation`, the last 15 `drip_event` rows, and UI drafts);
  - `create_draft` (writes `drip_ui_draft`).
- **Drip UI model:** `openai/gpt-oss-120b` via the Groq API (external), temperature 0.2.
- **Gate:** `drip_card.py` lines 0 to 10 (Charter, goal, custodian, posture, history, facts, law, strategy, ledger, tone, channel).
- **Lint:** 23 rows in `drip_lint_rule` (threat_early, cold_tone, strategic_tell, adverse_annex_early, supervisor_cc_early, …).
- **Style register:** 9 rows (audience, language, max chars, one point, warmth, easy yes, gracious close …).
- **Templates and voice:** `drip_template` 0 rows, `drip_voice_profile` 0 rows (never filled).
- **Queue config** (`drip_queue_config`):
  - show_one_at_a_time = true;
  - max_new_per_cluster_per_week = 1;
  - min_working_days_between_steps = 15;
  - min_awaiting_comment = 5;
  - priority_ladders = a 20 Oct list.
- **Next-target picker** (`drip_board.py` + `case_work/DRIP_PRIORITIES.json`): matter weight × urgency + calendar proximity.
- **Spec 005 v2:** Stages 0–8 (intake, cross-reference, state machine, tick, ladder, daily pick, measure, equilibrium, output and voice), plus the sleep doctrine, baby-step ladders, one brain one loop, review queue, X16–X18.

## 6. Interface check: the Drip UI (found 23 Oct, built by another session the same day)
It is up (`/health` ok) and holds 24 chat messages and 1 held draft. As a drip interface it does not yet do what the drip is designed to do:
1. **Blind to the real state.**
   - Its queue reads `office_obligation`: 8 stale September rows, no clocks.
   - It does not read the board, the ladders, the priorities, the clocks, or this week's 12 running clocks and next targets.
2. **No Charter in the prompt.**
   - Capacity, never-for-all-heirs, cadence, posture (X17), history-before-ask, channel and "follows not positions" are all absent.
   - Its drafts never pass `drip_card.py` or `drip_cadence_check.py`.
3. **Second AI, external.**
   - It runs on Groq's gpt-oss-120b.
   - That contradicts the 20 Oct ledger rule "using two AI is not working … one brain".
   - It sends case documents to a third-party API, against the offline-sovereignty invariant.
4. **"Go" goes nowhere.**
   - A Go decision writes `drip_event` kind `ui_decision`.
   - The code says "Claude's existing loop picks up 'go' decisions", but no script reads `ui_decision`.
5. **No client separation by default.** `search_corpus` searches every client unless a matter is passed.
6. **Not in git.** `drip_ui/`, `drip_inbox/` and the migration are untracked on the VPS (with six `.bak` and `patch*.py` files).

## 7. Conflicts to resolve
- **Charter §9 vs. 23 Oct.**
  - §9 says "all matters are equally important"; today's instruction ranks by importance and calendar.
  - Either amend §9 (a dated line + a `drip_feedback` charter row), or set all weights equal and rank by calendar and money only.
- **Charter §6 (batch go per campaign) and the review queue (≥5 drafts awaiting comment) vs. practice (one at a time in chat).** Pick the one that is true.
- **office_obligation vs. the board.** Two clock systems. Either backfill office_obligation from the board (proof-doc constraint satisfied by corpus docs such as #19044), or retire it and point the UI and tick at the board.
- **One brain vs. the Drip UI's Groq model.**

## 8. Proposed fixes, in order (none done yet)
1. Log the §4 rules into `drip_feedback`, regenerate the ledger and guide, re-ingest (#18479, #18382).
2. Decide §7, then amend the Charter in place with dated lines.
3. Wire the interface to the real state:
   - its queue reads the board's rows and next targets;
   - its drafts pass `drip_card` + cadence before they show;
   - Go becomes a staged Gmail draft through the existing stager (still never sends).
4. Put the Charter rules into the interface prompt, or route the interface to Claude (one brain), per Jonathan's choice.
5. Commit `drip_ui/` to git after a clean-up, with the other session's agreement.
6. Default client scoping in the interface search.

## 9. Questions for Jonathan
1. Which interface do you mean: the Drip UI on the VPS (port 8790), Leo on Telegram, or this chat?
2. Charter §9: amend it to rank by importance and calendar, or keep "all matters equal"?
3. The Drip UI's brain: keep Groq gpt-oss, switch it to Claude, or a local model?
4. Approvals: one at a time (as now) or a batch go per campaign (Charter §6)?
