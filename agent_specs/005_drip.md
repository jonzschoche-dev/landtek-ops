# Agent 005 — the Drip  (obligation-clock engine: offices stay on their toes because nothing lapses silently)

*Spec (no code). Written 2026-09-11. Operator's name for the idea: "the drip — focused communications
out to offices to keep them on their toes." The manual prototype already exists and WORKS:
`case_work/MWK-001/DEMAND_CLOCK_LEDGER_2026-09.md` (7 officer clocks + the DILG edition track). This
agent turns that ledger into typed rows + a $0 sweep + staged instruments — with the operator's own
8-Sep process flag encoded as truth-tests. NB: `landtek-geometry-drip.timer` is an unrelated OCR
drain; this spec owns the name "drip" for correspondence from here on.*

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
