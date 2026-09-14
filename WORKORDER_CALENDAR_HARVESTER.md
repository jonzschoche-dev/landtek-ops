# Work Order — Calendar Date Harvester (Fix #2: un-starve the pulse at the ROOT)

**Context.** deploy_1048 (Fix #1) wired the pulse/brief to read the full deadline substrate
(`gather_from_deadline_substrate`). That removed the *blindness* but not the *starvation*:
the substrate itself is near-empty (~3 future-dated items across ~17 date-bearing tables)
because the live September work — ARTA windows, hearing cards, demand clocks, "file by
11 Sep" — lives in `case_work/*.md` + the operator's head and **was never written into any
structured table.** An undated goal is invisible to the pulse ([[calendar-is-the-pulse]]).

**Objective.** Lift the dates that ALREADY EXIST (in procedural rules + cited case-work) into
the structured spine — **grounded, proposed, operator-approved, NEVER fabricated.**

## Hard doctrine (non-negotiable)
- **Never fabricate a date.** Only two legitimate sources: (a) a date *literally present* in a
  cited source (a `case_work/<MATTER>/*.md` line, a gmail/doc), or (b) a date *rule-derived
  from a cited anchor* (e.g. ARTA RA-11032 §21 15-day OP window measured from a notice date
  that is itself cited). Anything else → `OPERATOR_INPUT`, not a guess.
- **Propose, don't write.** Everything lands in the existing `date_proposals` ledger
  (`scripts/date_proposer.py`) with `status='pending'`; the operator approves → the approve
  path writes to `matters.next_deadline` / `case_deadlines`. Reuse date_proposer's approve
  flow; do not fork it.
- **A5 client separation.** Matter tag comes from the case_work FOLDER (`case_work/MWK-001/…`
  → MWK) or an in-file matter code, never from a bare place-keyword ([[client-separation-place-keyword-leak]]).
- **Provenance on every proposal.** `basis_rule` ∈ {`PROCEDURAL_RULE`, `HARVESTED_CASEWORK`,
  `DRIP_CLOCK`}; `basis_detail` cites the exact `file:line` or `rule + anchor doc`.

## Reuse (do NOT reinvent)
- `scripts/deadline_extractor.py` — the regex-only ABSOLUTE/RELATIVE date extractor already
  exists; point it at case_work markdown, not just docs/emails.
- `scripts/date_proposer.py` — the proposal ledger + `--review`/`--approve` flow.
- `calendar_sync.load_matters_index` — folder/code → client resolution.
- The DRIP (`drip_edition`, `office_obligation`) + demand-clock ledgers are already structured
  and now read by the substrate — harvest only what ISN'T yet structured.

## Pipeline (proposed)
1. **Scan** `case_work/<MATTER>/*.md` (+ `DEMAND_CLOCK_LEDGER*`, hearing cards): regex dates +
   deadline keywords (file/hearing/due/lapse/window/by <date>), matter = folder.
2. **Procedural lane:** for ARTA/DILG/court items with a cited anchor date, apply the known
   statutory windows (encode the small rule table; ARTA posture per [[project-arta-cluster-positioned-to-lose]]).
3. **Emit** proposals → `date_proposals` (pending), each with the citing `file:line`.
4. **Operator** `date_proposer --review` → `--approve <id>` → spine gets the date → the pulse
   (Fix #1) fires it automatically next tick.
5. **Timer** (later): a daily harvest scan so new case-work dates surface without being asked.

## Acceptance / truth-floor
- A negative test: a case-work line with NO date, or a keyword with no cited anchor, produces
  **zero** proposals (never a fabricated date) — mirror `test_date_proposer_guards.py`.
- Coverage line: report `N harvested-proposed · M procedural-derived · K operator-input`, and
  after approval the pulse's "dated items inside T-14" rises measurably (the un-starving proof).

## Sequencing
Independent of any P2 hold. Build the case_work scanner + procedural rule-table first (highest
yield: it turns the visible September deadlines into pulse-fired work), timer last. Every
proposal stays operator-gated — this harvester makes the calendar *offer* the dates it can
prove, and the operator confirms; it does not decide.
