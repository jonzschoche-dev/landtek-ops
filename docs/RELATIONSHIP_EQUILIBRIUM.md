# RELATIONSHIP EQUILIBRIUM — every relationship is an equation (the reactive half of A70)

**Status:** DESIGN (ontology-first, per the 2026-07-11 exchange) · **Invariant:** A76 (ONTOLOGY §4, 🟡 doctrine)
**Grounded:** 2026-07-11 against the live DB — every "exists" claim below was checked, two corrected.

## 1. What this is

Incorporation today is **batch** (the calendar pulse fires on dates) and **per-deliverable** (the answer-gate,
the A70 gate, the A75 projection fire when something is about to emit). The missing half is **reactive**:
one interaction lands — a reply, a comment, a decision, an attachment — and the system recomputes its effect
across every related node (fact · person · obligation · deadline · keystone · client boundary) *before any
output surfaces*, then doses each affected recipient's marginal next-increment. Two paths, same graph:
**the pulse fires on dates; the equilibrium engine fires on interactions.**

## 2. The tension, resolved by the projection boundary

"Gentle AND hair-splitting accurate, at speed" is contradictory only in a system with one surface:

- **INTERNAL = maximally accurate.** Full graph, all edges, all contradictions, all cascade implications.
  No dumbing-down. Accuracy lives in the graph.
- **EXTERNAL = gentle.** Each recipient gets only their marginal increment, dosed to metabolizable
  capacity (A71), shaped by their profile (A75). Gentleness lives in the projection.

They stop competing because they sit on opposite sides of the A75 boundary: the engine computes the hot,
complete equilibrium internally and only ever emits the cool, dosed delta.

## 3. The formalism

Edge: `e = (source, target, type, accuracy_weight, dose_ceiling, direction, cadence_trigger)`.
The type set is the ontology's existing relation vocabulary — no new semantics, just unification:

| Edge type | Today's carrier (grounded) |
|---|---|
| fact→fact (provenance/support) | `fact_edges` — **schema exists, 0 rows** (aspirational since §2.5) |
| fact→keystone (cascade) | `keystones` (3) + `cross_matter_links` (3, `proof_doc_id`-gated, A14) |
| person→matter (role) | `doc_entities` / `matters` role columns |
| obligation→deadline | `surfaced_deadlines` + the pulse spine (A68) — **NB: no `obligations` table exists**; the draft that claimed one was corrected here |
| channel_user→client (identity) | `channel_users.mapped_client_code` (11, A25/V7) |
| message→document (sink link) | `scripts/comms_artifact_sink.py` output links — **a script, not a table** |
| reply→message (thread) | `channel_messages.reply_to_id` (intra-channel; A29 cross-channel ○) |
| decision→work_order (pulse) | `pulse_work_log` (7) → `work_orders` (A59) |
| contradiction | `contradictions` (44 — detected, out-of-lane; A65 owns the arrow-of-time rule) |

**On the propagation event** (a comment/reply/decision lands):
1. **Parse** into graph deltas (new nodes/edges) — external content stays DATA (A66).
2. **Resolve accuracy** — provenance tier; if it asserts a fact, through the answer-gate/propose path (A49).
3. **Propagate the ego-network** — the N-hop neighborhood of the changed node only (never the whole
   corpus; that's what makes millisecond-scale honest): contradiction check (vs verified facts → surface,
   never silently pick — A65's register is the outlet), obligation extraction (does this create a
   deadline? → the A68 proposal path, source-cited, never a fabricated forward date), cascade check
   (keystone touched?), **isolation check (an edge crossing a client boundary is refused, not weighted — A5
   is a hard constraint, not a parameter)**.
   **The document-bridge constraint (proven live, 2026-07-11 P1 exercise):** documents are client-agnostic
   cut-vertices — the direct cross-client fact→fact edge is refused, but `fact → document → fact` bridged
   Paracale-001 → doc 1176 → NIBDC-001 at hop 2. Therefore the traversal carries a **per-hop A5 guard**:
   expanding through a document node may only reach nodes of the SAME resolved client as the perturbation's
   origin; a document with an UNRESOLVED owner (`case_file` NULL) is **not traversable at all** (the V4
   null-owner bypass class — A77(1) territory; live instance: docs 1172/1177 bled facts into MWK-OP-PETITION
   on 2026-07-11). `fact→document` stays in the view for provenance display; the constraint binds PROPAGATION.
4. **Project per recipient** — the marginal increment via A75 form + A71 dose.
5. **Queue outputs** — pulse orders, brief lines, outward replies (all still behind their gates: A21/A26/S14).

**Reactivity semantics (the designer's open question, answered):** the law is per-interaction —
*no output may surface from a perturbation that has not been propagated.* Coalescing a burst inside one
metabolic window is a permitted implementation optimization; skipping propagation before surfacing is not.

## 4. What exists vs what's missing (grounded 2026-07-11)

**Exists as pieces:** `matter_facts` (18,237) · `keystones`/`cross_matter_links` · `channel_users` ·
`surfaced_deadlines` + pulse spine · `recipient_projection` (A75) · `leo_answer_gate` · `comms_artifact_sink` ·
`calendar_orchestrator` (batch pulse) · `contradictions` (44) · `incorporation_verdicts` (A70).

**Missing — the unifying layer:**
1. **One relationship graph** with typed edge equations + weights (`fact_edges` is the empty seed;
   `knowledge_graph_triples` (74) is the underused triple store — unify, don't add a third).
2. **A reactive propagation function** (ego-network recompute on inbound; today only timers fire).
3. **Contradiction detection wired to an owner** (44 rows sit out-of-lane — A65's graduation and this
   engine's step 3 are the same build).
4. **The tuning surface + ledger** — edge weights / dose ceilings / hop depth / cadence triggers recorded
   per interaction (what propagated, who received what), so "gentle and hair-splitting" is TUNABLE and
   inspectable, never hardcoded. Shadow-first, A/B against the ledger — the Leo discipline.

## 5. Phased build (shadow-first; each phase graduates separately)

- **P1 — graph schema: RULED + BUILT (deploy_882, desk-ratified 2026-07-12).** The carrier is the DERIVED
  VIEW `v_relationship_graph` (34k edges — rebuildable over the SoR, A50-consistent), with persistence ONLY
  in the `propagation_log` ledger. Neither `fact_edges` (stays drift) nor `knowledge_graph_triples` becomes
  the spine — no third store. The per-hop A5 guard is the view's `WHERE client_code = seed_client` clause;
  NULL-client edges are unreachable by construction (LOAD-BEARING — never relax to `OR client_code IS NULL`).
- **P2 — reactive propagation: SHADOW-LIVE (deploy_882).** `equilibrium_propagate.py` — internal plane only, gate-free (the two-plane law: accuracy inside, A79 clamp + A75 projection at the emission plane only), ledgers to `propagation_log`, emits nothing.
- **P3 — contradiction detection:** wire step-3 checks to `contradictions` with owners (graduates A65 too).
- **P4 — tuning ledger + calibration:** the observability surface; only then may outputs go live per path.

## 5b. Fleet / CoS roster as a perturbation (2026-09-26)

`agent_registry` enumerates desks (Grok Bot seats + Claude subagents via `scripts/cos_bridge.py`;
systemd/cron/catalog via `fleet_registry.py`). A roster change is a **graph perturbation** too —
every CoS action should affect the stack (equilibrium), not chat-only memory.

Hook (shadow, reuse existing ledgers — no second brain):
- `python3 scripts/cos_bridge.py --sync --pulse` upserts seats, then writes
  `propagation_log` with `seed_type='fleet'` (deploy_881) and a note row in
  `equilibrium_coverage_log` (deploy_934).
- Importable stub: `from cos_bridge import on_fleet_change`.
- Real CoS moves (assign bot, pause Discovery, approve outward) still enqueue
  **`work_orders`** and cue related subjects; the pulse ledgers the change so A76 can see it.

Full ego-network `equilibrium_propagate` stays for client-scoped seeds (fact/matter/chat).
Fleet events are company-level and stay SHADOW until a later path wires them to recipients.

## 6. What the ontology does NOT define (execution lanes)

The store's DDL, the propagation code and its hop-depth defaults, weight values, queue mechanics, and
performance targets are the builder's. The ontology fixes: the edge-type vocabulary (§3 table), the five
propagation obligations (parse-as-data · accuracy-resolve · propagate-before-surface · refuse cross-client
edges · project-then-dose), and the graduation bar: **A76 floors only when the propagation function exists
and is negative-tested — a planted contradiction is caught, a cross-client edge is refused, an N-hop
increment lands correctly dosed.** Until then A76 is doctrine; do not phantom-enforce.

## 7. Reasoning equilibrium: the strategic layer (redraft 2026-10-19, PROPOSED, in the Claude↔Grok ping-pong)

**Why.** The reasoning spine (deploy_934: `v_inquiry_principal` → `matter_facts` → `fact_fields` → `matter_brief`)
answers *what is true*. The strategy pieces (`strategy_engine.py` north-star, leverage and keystones;
`play_engine.py` plays × `matter_elements`; `ombudsman_hunter.py` ripeness; the game-theory frame in
`case_work/MWK-001/GAME_THEORY_LIABILITY_2026-09.md`) answer *what would move the campaign*. They don't feed
one decision. This layer joins them, so that every move the stack proposes (a drip ask, a filing, a play) is
**the strongest legal, sequenced, credible move toward the client's goal**. It stays mechanical: no LLM judges
strategy, and every input is a row with provenance.

**Respects: A2, A5, A20, A21, A65, A71, A74, A76** · truth-seeking doctrine (law-anchored; a resolution is a
claim to test) · decision-first doctrine (claim ↔ forum ↔ remedy first) · anti-trap doctrine (measure, don't model)

Grounded 2026-10-19 (counts): `client_goals` 6 · `matter_objectives` 25 · `matter_elements` 169 · `matter_plays` 40 ·
`keystones` 3 · `ombudsman_candidates` 42 · open `contradictions` 46. **No dependency table exists.** Prerequisites
live in prose (e.g. CV6839 execution queued behind SP 2680). S2 below adds it.

### 7.1 The strategic value of a move: eight mechanical tests
Each candidate move (a drip obligation, a rung, a play) is evaluated against these. The first three are **gates**:
fail one and the move is not pickable, and the gap itself becomes the move.

| # | Test | Mechanical input | Fail ⇒ |
|---|---|---|---|
| G1 | **Position fit**: does this forum have power to grant the remedy that advances the goal? (the ARTA-1319 lesson) | `matters.forum` × the remedy in `matter_objectives` × the forum-power table (S1) | not pickable, unless it is tagged an *exhaustion exhibit* for a forum that can grant the remedy |
| G2 | **Prerequisites met**: every move it depends on is done | `move_dependency` (S2) | not pickable; **the prerequisite becomes the candidate** (e.g. guardianship → CV6839 execution) |
| G3 | **Truth floor**: every element the move asserts is `verified` (or `operator`), no open contradiction touches it, and the law is cited verbatim | `matter_elements.status`, `contradictions`, `legal_authority` | not pickable; the missing element or open contradiction becomes the ask |
| V1 | **Goal leverage**: how much this advances the north-star, × how many matters the outcome cascades into | `matter_objectives.leverage` × `keystones.cascade_matters` + ego-network matters (A76) | ranks |
| V2 | **Pressure delta (Game B)**: what the move does to the counterparty's cost of deflecting: *attributes* the duty to a named signer, *ripens* personal liability, *removes* Deflect (a ministerial duty, mandamus), or *prices* delay (Game A) | `pressure_type` on the obligation or play (S3), from the game-theory table, not inferred per run | ranks; `none` = 0 |
| V3 | **Credibility**: a staged consequence we haven't pulled discounts every other clock ("a demand not followed through re-prices every other clock to zero") | count of `lapsed` rows with no rung staged in 24h | **lapses jump the queue** after money: keeping our word is strategy |
| V4 | **Exposure**: the strongest counter-move is known and we hold a standing answer | `counter_move` + `standing_answer` refs (S4; the red-team annexes are the source) | an unanswered counter ⇒ prepare the answer first (that becomes the move) |
| V5 | **Optionality**: reversible and internal beats irreversible when V1–V4 tie; irreversible acts (filing, service) only when ripe | the §0.6 action tier + `ombudsman_candidates` ripeness | tiebreak |

### 7.2 The strategic order (feeds 005 v2 Stage 5; formula fixed, inputs move)
Filter: G1 ∧ G2 ∧ G3, and the A5 wall. Then lexicographic:
1. **Money at stake**: verified, typed `at_stake` (E3).
2. **Credibility debt (V3)**: an un-pulled lapse.
3. **Live sourced deadline**: stale dates never rank (E2).
4. **Goal leverage × cascade (V1)**: this replaces the bare unblock count.
5. **Pressure delta (V2)**.
6. **Ripeness, then optionality (V5), then age.**

Jonathan's rule stays "money, then deadline, then unblocks". V3 sits between because an un-pulled lapse is a
deadline we already missed. V1 is the rigorous form of "unblocks". **Disagreements G1–G3 surface as asks, never
as silent drops**, so strategic mastery shows up as *fewer, sharper* asks, not as hidden reasoning.

### 7.3 Learning loop (measure, don't model)
Every outcome per office (performed · replied-not-performed · deflected · silent past lapse) is a `drip_event`.
`v_office_response_rate` (S5) counts outcomes by office type × pressure type × rung. After N≥5 outcomes per
cell, V2's weight for that cell is the observed performance rate, not an assumption. Counts only; no LLM
re-weighting, and any weight change is logged and shown to Jonathan. This is how communications and silence
re-tune the equilibrium (Grok's point 9) without making the pick opaque.

### 7.4 Schema deltas (small, additive, shadow-first)
| # | Delta | Notes |
|---|---|---|
| S1 | `forum_power(forum, remedy, basis)`: what each forum can grant | seeded from law-corpus citations; an unknown forum/remedy pair = G1 `[HUMAN VERIFY]`, not a pass |
| S2 | `move_dependency(move_ref, requires_ref, basis, recheck_condition)` | A74: every dependency names what clears it |
| S3 | `pressure_type` on `office_obligation` + `matter_plays` | enum: attribution · personal_liability · removes_deflect · prices_delay · none |
| S4 | `counter_move`, `standing_answer` refs on plays and obligations | point at red-team annex lines; no answer = exposure |
| S5 | `v_office_response_rate` view over `drip_event` | derived, rebuildable |

### 7.5 Graduation (negative tests)
- A move in a forum that cannot grant the remedy is refused (planted: an ARTA move seeking title relief).
- A move with an unmet prerequisite surfaces its prerequisite instead (planted: CV6839 execution before SP 2680).
- A move touching an open contradiction becomes "resolve the contradiction" (planted: the Macale 7 vs 13 Jul date).
- A lapse with no rung outranks a fresh demand of equal money.
- The same DB gives the same order.
- A cross-client cascade is refused (A5).

Until these pass, the layer runs in shadow: it computes the order next to the live pick and logs both, and
Jonathan sees the differences.

### 7.6 Play doctrine: the patient record ("rope-a-dope"), operator request 2026-10-20
**Idea.** We don't escalate early. We keep asking, politely, for things the law already obliges the office to do,
and we let the office's own pattern of non-performance build a record that a prosecutor can file without
hesitation. Pressure comes from accumulation, not volume. The official who deflects comfortably for 250 days has
written our exhibit for us.

**The bright line: entrapment yes, instigation never.** In Philippine law, instigation (inducing the act) is a
complete defense. Every rope step must therefore be:
- (i) a **genuine** request we actually need, under a duty that already exists;
- (ii) truthful, with no pretext, no false identity and no manufactured urgency;
- (iii) reasonable in scope and cadence, so it can't be painted as harassment (stagger, never salvo, A71);
- (iv) never an invitation to an unlawful act: no bribe offers, no "facilitation" asks, no off-record channels.

The official's free choice to ignore a lawful duty is the whole case. Anything else poisons it. Statute periods
and prescription: NEEDS-COUNSEL-VERIFICATION.

**What "comfortable to prosecute" means, mechanically.** A case the Ombudsman or CSC files without strain has:
- **One duty, one failure.** A single ministerial act, explainable in ten minutes (the small-players sheet logic),
  not a land-title theory.
- **Due demand, proved.** Each request is in the corpus with its proof of receipt (X4). No receipt, no rung.
- **Time on the clock.** The period ran out: RA 6713 §5(a), a reply with the action taken within 15 working days
  from receipt, for every official; LGC §252, 60 days, for the Treasurer row only. RA 11032 §21 is **not** a general
  rope period, because ARTA reaches only applications or requests for a permit or similar (Sec. 4(f); Grok/Legal
  20 Oct). No escalation rung before 15 working days from receipt. The day counters come from the record (X9).
- **A comparator.** Proof the act was possible: the office did it for someone else, or did it before (e.g.
  Olaguera's 15 Dec 2025 ₱60 assessment).
- **No justification on record.** Their written answers are kept verbatim. A reply that doesn't perform is
  logged as `replied_not_performed`, never as compliance.
- **The benefit element, for RA 3019 §3(f).** Who gains from the inaction (their own interest, a favored party
  such as a relative or subordinate, or discrimination against us) must be documented separately. Without it,
  the count stays administrative (Grave Misconduct / Conduct Prejudicial / RA 6713), which is still a strong
  case.
- **A requester in good faith.** Our tone stays courteous and our asks stay lawful, so the respondent's best
  defense ("harassment") has nothing to stand on.

**How it runs in the engine (no new machinery).**
| Phase | Engine state | What we do | What builds |
|---|---|---|---|
| Rope 1: ask | `draft_held → approved → served_running` | one lawful request, proof of receipt | due demand + clock |
| Rope 2: patient reminder | edition (Lane 2), counters advanced | the Schedule of Continuing Default, no threats | the day counter, published to the supervisor |
| Rope 3: supervisor | rung R1 (upward) | reiteration to the supervising office, cc the officer | attributability: the supervisor can't say they didn't know |
| Rope 4: notarized | rung R2 | the same courteous letter (unsworn) + Jonathan's remote-e-notarized **Affidavit of Facts and Service** (A.M. No. 24-10-14-SC), attaching the letter and every prior proof of receipt | an evidentiary-grade, QR-verifiable record; the affidavit is the exhibit test made sworn |
| Counter-punch | rung R3, `consequence_staged` | file in **one** forum, **one** officer, the ripest count | the case files itself from the annex packs |

**When the rope stops paying (Game A check).** Waiting costs the estate too. The rope runs only on fronts where
delay doesn't block money. Where a money front is held up (e.g. CV 6839 collection), the strategic order
(§7.2) moves to forums that can compel (court / mandamus) and keeps the rope running in parallel on the
officials. G1 still applies: the rope's counter-punch must land in a forum that can sanction the officer
(CSC-RO V for appointive officers, the Ombudsman for elective officers and §3 counts), not in a forum that only
refers.

**Ripeness signal (V2/V3 inputs).** A rope target is `ripe` when all of these hold: proof of receipt, clock
lapsed, a comparator or an admitted capability, no justification, the R1 supervisor informed, and (for §3(f)) the
benefit element documented. Short of that it's `building`. The engine never files. Ripe means
`consequence_staged` for Jonathan's go, through the matter's counsel where the matter requires it (§0.5).

**The live legal risk is "vexatious", not only instigation.** RA 6770 §20(3) lets the Ombudsman dismiss a complaint
"vexatious or made in bad faith". The controls are the anti-salvo rule, the calm routine tone, and one officer and one
count per filing.

**Tone (Jonathan, 20 Oct, via Grok 07:30):** *"the drip is not meant to be combative, it's meant to make them go to
sleep while the record builds."* Use the live `calm_routine` register: courteous, plain, ordinary administrative
follow-up. No effusive praise. Rope-a-dope, counter-punch, ripeness and similar terms are **internal labels only**,
and lint keeps them out of every outward draft.

**Negative tests.** A rope step without a corpus proof doc can't advance a rung. A rung earlier than 15 working days
from receipt is refused. An outward instrument without an `approval_ref` is refused. A template containing an offer,
inducement or pretext wording is refused by the drafting lint. Two new rungs to one office cluster in one week
are refused (anti-salvo). A `ripe` flag without the benefit element is capped at administrative counts.

### 7.7 The financial-legal angle against every official, where it applies (operator, 2026-10-20)
**Principle.** Each official's dereliction is priced: time × the duty they sit on → pesos (`loss_line` →
`v_dereliction_meter`). They are **told, warmly and in writing, what the open request costs**. The record logs that
they were told (`loss_notice`, proof of receipt required), so continuing becomes a choice made *with knowledge*.
Knowledge is what turns neglect into "without just cause" (Art. 27), "gross inexcusable negligence or evident bad
faith" (§3(e)) and gross neglect (dismissal with forfeiture). The money angle is the **seventh value test (V6)**: a
move that creates or proves a pleadable loss, or puts an official on notice of one, outranks an equal move that
doesn't.

**Remedies** (`financial_remedy`, seeded; all NEEDS-COUNSEL-VERIFICATION):
- **Paid personally by the official:** Art. 27, Art. 32(6), §3(e) restitution, a COA disallowance, and forfeiture of
  retirement benefits on dismissal (paid to nobody, but the largest personal exposure there is).
- **Paid by the institution:** LGC §24 compensation for use, and the RPT refund.
- **Both:** mandamus with damages.

**Elements discipline.**
- §3(e) needs **actual, quantified, directly caused** injury (Llorente). Only `actual_proven` + `direct` lines count
  (`v_official_loss.s3e_injury_element_present`).
- A demand-based stream (compensation for use) **doesn't run until the demand is served with proof**. The meter shows
  what each unserved month costs, so our own closer gap is priced too.
- Estimates and evidentiary-delay lines never leave the internal plane. The `loss_notice` trigger and the
  `unpleadable_amount` lint enforce this.

**Tone.** Burden statements follow §7.6 and Stage 8. For example: *"For completeness of the record, and so your good
office has the full picture, we note respectfully that while this request remains open the estate continues to bear
[₱amount] each month [basis: your office's own valuation, Annex A-2]. We remain glad to help in any way that makes
the release easy."* Never a threat, never an adjective, and always the easy yes beside it.

**First fit, 20 Oct 2026** (`official_remedy_fit`, proposed; source: `v_dereliction_meter` dry run + the track
inventory):

| Official | Money angle that applies now | Applies once… | Missing / gate |
|---|---|---|---|
| **Abla** (Assessor) | Art. 27 (₱300 paid, 486 days unrendered); **§3(e) injury element present** (₱547.97 actual, direct: fee + courier) | the burden notice is served → mandamus with damages for the chartered service | §3(e) still needs bad faith or gross negligence on the record (the comparator does this); forum-shopping cert vs OP 1321 |
| **Macale** (Treasurer) | Art. 27 (the §252 decision lapsed ~11 Sep); RPT refund | **paid under protest** → ₱14,391.50 becomes actual → §3(e) injury | Pay under protest is the switch (your call); COA disallowance only if she certified the 2024 ₱2.88M DV (to obtain) |
| **Pajarillo** (Mayor) | — (elective; institution pays the compensation) | the **Schedule is served** → LGC §24 ₱59,521.00/mo vs the LGU + Art. 27/32 personally for enabling the occupation; mandamus for the §444 duties | **Serve the Schedule** (the biggest money switch on the board); COA ND on the 2024 DV if he approved it |
| **Engr. Balane** (Building Official) | — | after 26-360 strategy clears it: Art. 27/32 for non-enforcement vs the unpermitted structure | **Barandon gate** (26-360 defendant) |
| **Fulo** (Accountant) | — | the 2024 DV shows her certification → COA disallowance personally | obtain the DV (COA request of 13 Jul / RA 11032 request) |
| **Olaguera** (SB Secretary) | Art. 27 (records, 250 days) | the fee assessment is tendered and refused → mandamus with damages | no money loss yet; costs incurred (couriers, trips) to be ingested |
| **Torralba / Teope** | — | Teope: compensation for use on his structure once the Schedule is served on him | Torralba counsel-gated; Teope's area survey [___ sq m] |
| **Supervisors** (Doctolero, Magana, Manlapaz, Escober, Relucio, Guerrero) | none: record-builders | Art. 27 only if they refuse a supervisory duty *after* a burden notice | keep them warm allies: they're the R1/R2 audience, not targets |

**Biggest single money move:** serve the Schedule of Reasonable Compensation. Until then the largest stream
(₱59,521.00 per month on the LGU's own valuations) can't run. **Cheapest:** pay Macale's ₱14,391.50 under protest
(it turns her line into actual injury and starts the refund). Both are your go.
