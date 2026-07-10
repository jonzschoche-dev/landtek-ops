# CALENDAR & CADENCE DIRECTIVE — the pulse (operator vision, 2026-07-10)

**Pattern:** `GovernanceHandoff` (ONTOLOGY §2.12) · **Governing invariants:** A57, A67–A69 (ONTOLOGY §2.19 / §4)
**Vision (operator, verbatim intent):** the calendar is the most underrated tool — it sets the pulse for all
communications and creates a cadence. A living, breathing temporal spine gently driving clients and LandTek
to their most productive selves. Widespread and robust; **timelines and goals attached to everything,
agentically.**

**Grounded starting state (2026-07-10):** `calendar_events` (27) · `surfaced_deadlines` (126, A57-governed
fresh+complete) · `client_goals.target_date` (6) · scripts live: `deadlines.py` / `deadline_extractor.py` /
`calendar_sync.py` / `calendar_briefer.py` / `mint_calendar_token.py` / `agent_deadline_orchestration.py` ·
daily digest leads with due-dates · **gap: `work_orders`/`matter_plays`/`matter_objectives` carry NO
forward-date column** — timelines do not yet attach to everything.

## Lanes (route to desks when assigned; each stays inside the named invariants)

### C1 — Timelines attach to everything (A67) → product-hardener / supervision desk
Add forward-timeline semantics to the governed kinds that lack them: `work_orders` (review horizon —
also serves §9-D2's stalled-order sentinel), `matter_plays`/`matter_objectives` (target dates), and the
future WorkProduct (A58: a deliverable has a due date from birth). Every ACTIVE object: dated or explicitly
dateless-classified — then generalize `test_deadline_totality.py` across kinds (the A67 graduation).

### C2 — Agentic derivation with provenance (A68) → live-layer / product-hardener
`deadline_extractor.py` mines obligations from the record (court orders · statute periods · emails) into
PROPOSALS carrying source doc + excerpt; operator confirms what drives outward cadence. Hard rules already
in code, keep them: a NULL `next_deadline` is an operator signal; historical prose dates are NEVER promoted
forward (deploy_642/644). Graduation artifact: a truth_test that no forward deadline lacks a resolvable source.

### C3 — The client-facing pulse (A69) → ship-packager
The client calendar surface (via `mint_calendar_token`) renders ONLY that client's events, through
`ClientProjection` (A32 — no internal codes/dockets on a calendar entry), with lead-time-laddered reminders
riding S14 pacing + the A21 chokepoint. The pulse is gentle by construction: one point, no double-tap,
no floods. External calendar publishing (ics/Google) is an OUTWARD switch — held until Jonathan's go.

**Respects: A5, A21, A26, A32, A57, A67–A69.** Sequencing: C1 (cheap, unblocks the totality test) →
C2 (the agentic depth) → C3 (client-visible, gated). Close-out per lane returns to the ontology desk.
