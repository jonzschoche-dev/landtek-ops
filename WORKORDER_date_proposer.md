# Work Order — build `date_proposer.py` (the front-end of the pulse)

**For:** the executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). Grounded against the live scripts 2026-07-10.
**Doctrine:** calendar is the pulse (the orchestrator), not a display. The pulse can only
fire work for DATED items; the ~51 NEEDS-A-DATE rows are literally unproduced work. This
agent turns dark items into GROUNDED date proposals — never fabricating — so the pulse can
reach them.

---

## The goal

Build `scripts/date_proposer.py`: for every **NEEDS-A-DATE** row that
`timeline_coverage.py` surfaces, emit ONE of:
  - **PROPOSAL** — a forward date derived from real signal, carrying provenance, OR
  - **FLAG** — honest "no derivable date; needs operator input," with the reason.

Never invent a date. A70/A68 govern: a proposal without a resolvable source is a violation;
a NULL stays NULL until the operator or a cited source fills it.

---

## Ground truth already on disk (reuse, do not reinvent)

1. **`scripts/timeline_coverage.py`** — the source of the NEEDS-A-DATE queue. It classifies
   7 primitive date-bearers (matters.next_deadline · client_goals.target_date ·
   firm_goals.target_date · landtek_obligations.due_by · case_actions.due_date ·
   action_items.due_date · matter_plays(ready)→matter date) into NEEDS-A-DATE vs LEGIT-DARK
   (status in out_of_scope/pending_* /closed/archived, or stage observation_only etc.).
   **Import its classification — do not re-derive "what is dark."** Refactor its per-class
   query logic into a shared helper if needed so both tools agree on the queue.

2. **`scripts/deadline_extractor.py`** — the EXISTING regex-only derivation lane. It already
   turns inbound doc/email prose into `status='proposed'` calendar events with
   `source_doc_id`/`source_email_id` + verbatim `raw_clause` + `extraction_method='regex'` +
   `deadline_kind`. **The date_proposer must PREFER this lane's output**: if a dark item's
   matter already has a `proposed` extracted deadline, the proposal is "adopt the extracted
   date" (highest provenance), not a fresh derivation.

3. **`scripts/deadlines.py`** — A57/A68 doctrine (source-tagged, prose-harvest gated to
   already-dated matters). Honor it: the proposer writes PROPOSALS, never promotes historical
   prose dates to forward deadlines.

---

## Derivation rules (in priority order — highest provenance first)

For each NEEDS-A-DATE row, try these in order; stop at the first that yields a grounded date:

1. **ADOPT-EXTRACTED (verified-grade).** The row's matter/client has a `deadline_extractor`
   `proposed`/`scheduled` event not yet reflected on the primitive → propose that exact date,
   provenance = the extractor's source_doc_id + raw_clause. (Statutory appeal windows etc.)

2. **DERIVE-FROM-ANCHOR (operator-grade).** The row cites/links a dated event with a known
   statutory/procedural period (e.g. an ARTA resolution + "15 days to appeal") → propose
   anchor + N days, status='proposed', provenance = anchor doc + the period rule. Never guess
   the period; only apply a period that is itself sourced (from embedded law or the doc).

3. **INHERIT-FROM-PARENT (derived-grade).** A play/objective/goal whose parent matter or goal
   IS dated → propose the parent's date (or parent_date − lead_time if a lead rule exists).
   This mirrors timeline_coverage's "transitive coverage" design.

4. **FLAG (honest darkness).** No derivable signal → emit a FLAG row: the item, its client,
   why no date, and the SPECIFIC input needed from the operator (e.g. "date of receipt of
   Resolution 1210 to start the appeal clock"). This is the date-proposal agent's most
   important honest output — darkness named, not filled.

---

## Output contract

- **Default `--dry-run`**: print a table — item · client · rule-hit · proposed date OR
  FLAG+reason · provenance. Change nothing. (Safe by construction.)
- **`--write`**: write PROPOSALS to the proposals inbox (mirror `deadline_extractor`'s
  `status='proposed'` pattern — NOT directly onto the primitive date column; the operator/
  supervisor promotes). FLAGS go to a surfaced queue (holes_findings or the digest's
  "needs-a-date" section) so they enter the pulse as *known gaps*, not silence.
- **Idempotent**: dedupe on (item_key, rule, proposed_date/flag_hash). Second run writes 0.
- **Client-isolated (A5)**: resolve client_code per item; a proposal's provenance doc must
  belong to the item's client. Never derive a date for client A from client B's document.

---

## Guardrails (hard)

- **A68 / A70 — no phantom dates.** Propose-or-flag only. A proposal ALWAYS carries a
  resolvable source; a period rule is applied only when itself sourced. Historical prose date
  ≠ forward deadline.
- **Fail-closed.** On ambiguity → FLAG, never a bare guess.
- **Reuse.** Import timeline_coverage's queue + deadline_extractor's output; do not fork the
  definition of "dark" or re-parse prose the extractor already parsed.
- **Read-only until `--write`.** No primitive date column is mutated by this agent — it feeds
  the proposals inbox; promotion stays with the operator/supervisor (governance decides).
- **Two-agent protocol:** you (VPS) commit/push. Gates green first.

---

## Verify before commit

- `python3 scripts/date_proposer.py --dry-run` on live DB → every one of the ~51 items gets
  exactly one PROPOSAL or FLAG (no item silently dropped; count reconciles with
  `timeline_coverage.py --summary` NEEDS-A-DATE count).
- Negative test: an item with no signal MUST FLAG, never emit a date.
- `python3 scripts/timeline_coverage.py --summary` before/after `--write` → dated count rises
  only by adopted/derived proposals the operator promotes (proposals inbox, not the primitive).
- Add `truth_tests/test_date_proposer_grounding.py`: assert no PROPOSAL row lacks a resolvable
  source; wire into `run_all.py`.

## Definition of done

- [ ] `scripts/date_proposer.py` exists; `--dry-run` covers all NEEDS-A-DATE items 1:1.
- [ ] Every PROPOSAL carries provenance (adopted/derived/inherited); every un-derivable item
      FLAGS with the specific operator input needed.
- [ ] Client-isolated; idempotent; read-only until `--write`; proposals to inbox not primitive.
- [ ] `test_date_proposer_grounding.py` green + negative-tested, in `run_all.py`.
- [ ] (optional) a `landtek-date-proposer.timer` proposed for the daily pre-pulse tick so dark
      items get proposals BEFORE the 05:30 orchestrator fires — closing the loop.
