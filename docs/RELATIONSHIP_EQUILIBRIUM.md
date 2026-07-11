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

- **P1 — graph schema:** unify the edge carriers into one typed relationship view/store (decide
  `fact_edges` vs `knowledge_graph_triples` as the canonical spine — a §3-style drift ruling, desk's call).
- **P2 — reactive propagation:** the ego-network recompute, SHADOW (computes + ledgers, surfaces nothing).
- **P3 — contradiction detection:** wire step-3 checks to `contradictions` with owners (graduates A65 too).
- **P4 — tuning ledger + calibration:** the observability surface; only then may outputs go live per path.

## 6. What the ontology does NOT define (execution lanes)

The store's DDL, the propagation code and its hop-depth defaults, weight values, queue mechanics, and
performance targets are the builder's. The ontology fixes: the edge-type vocabulary (§3 table), the five
propagation obligations (parse-as-data · accuracy-resolve · propagate-before-surface · refuse cross-client
edges · project-then-dose), and the graduation bar: **A76 floors only when the propagation function exists
and is negative-tested — a planted contradiction is caught, a cross-client edge is refused, an N-hop
increment lands correctly dosed.** Until then A76 is doctrine; do not phantom-enforce.
