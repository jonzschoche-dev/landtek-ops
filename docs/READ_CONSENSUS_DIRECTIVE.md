# Read-Side Consensus Layer — "the Answer Plane / Read Composer" (design directive, v2)

> **Status: DESIGN — not built.** v1 authored 2026-07-18 (Mac desk) from the read-side gap analysis;
> **v2 same day: converged with the peer desk's composer brief** (adopting the hit/partial/miss/hold
> envelope, the one-reply-brain-first wiring, the drain-or-funeral decision gate, the scoped temporal
> cut, and the fleet self-inventory lane; retaining the registry-table authority source over
> fixed-in-code).
>
> **Live grounding (VPS, 2026-07-18):** documents 2,051 · pending_classification 1,156 (~56%) ·
> matter_facts ~41k · fact_fields ~39k · document_fields ~14.5k · **proposed_facts 261 = 249 pending +
> 12 contradiction_hold, ~0 ever closed** · verified_claims 1 · contradictions 44 (unowned) ·
> knowledge_graph_triples 74 · **agent_work_queue 616 pending** · matters dated 11/38 ·
> calendar_events 29 · map_parcels 70 · parcels 88.
>
> The diagnosis both desks agree on: **write-side ontology shipped; read-side consensus was named in
> doctrine and never shipped as one component. Gates refuse; they do not compose.** The stack is a
> high-assurance write warehouse without a consensus reader — which is why it is simultaneously
> over-engineered and useless to users: 40+ doors, no organ.
>
> **Respects: A5, A19, A24, A32, A50, A65, A71, A74, A75, A79, A85.** Mints one invariant candidate: **A86**.

---

## 1. The one-sentence design

One component — `compose_answer(intent, client_code, role)` — that every surface calls; it ranks the
canonical stores by **registry-declared authority**, reconciles them by a **named mechanical rule**,
and **always returns an envelope**: status + claims-with-citations + confidence + gaps + a render
frame. Gates refuse; the composer composes.

## 2. Design principles

1. **One reader (A86 — the read-side twin of A85).** For any governed concept, exactly one component
   composes answers. No surface reads fact stores raw. **Corollary (hard rule): once the composer owns
   a read path, deploy_97x-style bespoke per-ask-shape readers are FORBIDDEN** — a new ask-shape is a
   composer intent, never a new hand-join.
2. **Always answer; degrade with honesty; refuse only on scope.** `status` makes degradation
   machine-legible: `hit` (composed from answer-grade stores) · `partial` (gaps declared) · `miss`
   (nothing answer-grade; gaps say why + what unblocks, A73/A74 pattern) · `hold` (A5 scope violation
   or A79 clamp — the only refusals). A thin matter yields `partial`/`miss` with named gaps, never
   silence. Legal surfaces still filter to `verified` downstream (A19 unchanged).
3. **Consensus is mechanical (A24).** Reconciliation = deterministic functions of provenance tier,
   `as_of`, corroboration count, operator override. No LLM decides truth; LLMs paraphrase the resolved
   frame at the emission plane (A75/A79), never upstream of it.
4. **Reads drive drainage.** Dissent observed at read time is written as an owned contradiction with a
   machine recheck condition (A65 gets its lane via A74). Reading the data forces the queues to shrink —
   or forces the honest funeral (§6).
5. **Derived, rebuildable, scope-first (A50/A5).** The layer owns no truth; client scope is in the SQL,
   not post-filtered. This is also what makes multi-user real: per-client answers by construction.

## 3. The envelope (merged shape)

```python
ComposedAnswer(
  status   = 'hit' | 'partial' | 'miss' | 'hold',
  claims   = [{text/value, source_table, source_id, excerpt_ref, provenance}],
  confidence = ...,             # derived from the tier the answer actually earns
  dissent  = [...],             # losing values + which store said them; never silently dropped
  gaps     = [...],             # from a SHARED GAP CATALOG (typed, e.g. doc_unread(410),
                                #   needs_date(matter), pending_adjudication(n), no_verified_fact(topic))
  frame    = {...},             # render-ready structure A75 projection consumes (HUMAN vs MACHINE form)
  freshness = ...,
)
```

The shared gap catalog is itself a small registry table — gap kinds are typed so the write-back half
(gap drive / drain) can consume them mechanically, and so "what's missing" is countable across surfaces.

## 4. Authority order (single source: the registry TABLE, never per-surface, never scattered in code)

`consensus_registry` (concept → ordered store list with roles → reconcile rule → staleness horizon)
is the executable form of ONTOLOGY §2. **Chosen over fixed-in-code** (the peer brief's variant)
because a table is diffable against ONTOLOGY.md nightly (`ontology_check.py --registry`, same pattern
as `--enforcement`) — code constants are where doc-drift starts. Per-surface overrides are forbidden
either way.

Canonical rank (seed):

| Rank | Source | Role |
|---|---|---|
| 0 | Operator corrections (locked rows; `parcel_course_corrections` pattern) | outranks everything |
| 1 | `verified` / `operator` tier on the SoR (titles · verified matter_facts) | answer |
| 2 | Derived cards (`title_brief` / `matter_brief`) **if fresh** per staleness horizon | answer (cache) |
| 3 | `title_chain` / `document_fields` / `field_consensus` | support / corroborate |
| 4 | `inferred_*` tiers | answer ONLY labeled; external emission per A79/A75 dose |
| 5 | Mention-grade stores (`document_titles`, `doc_entities`, co-occurrence counts) | **mention_only — leads & gaps, NEVER answer values** (bakes mention≠membership into the machine) |
| — | Raw `proposed_facts` | **never asserted truth**; contributes only the typed gap `pending_adjudication(n)` |

Reconcile rules: `authority` (tier ladder) · `latest_verified` (A65 arrow of time; superseded → dissent) ·
`corroboration_n` (generalizes `field_consensus`/`geometry_consensus` — the two places consensus already
works) · `operator_wins` (rank 0).

## 5. First clients & the done-test (PR-C3 — one reply brain)

The composer's **first wiring target is the forked reply brain**: Telegram and Messenger both call
`compose_answer` and only differ in transport + projection profile. This makes the A85 dual-brain
violation the composer's first kill, and gives the acceptance test:

> **Done when: the same question asked on Messenger and Telegram yields the same frame** (channel
> changes transport, never content). Generalized as the sim probe family: same ask via three surfaces
> → identical envelope.

Then digest → briefs → dossier pre-flight → cockpit, in that order. The answer-gate and the
deploy_972 title inventory refactor ONTO the composer — their bespoke readers deleted, not wrapped.

## 6. The adjudication decision gate (PR-C1 — drain or funeral, decided on evidence)

261 fed / ~0 closed means the propose→adjudicate design is currently a fiction. Two honest exits;
**do not choose now — measure first**:

- **Step 1 (one day):** run `adjudicate_sweep.py` ONCE — mechanical classes only, through the existing
  gated write path: verbatim-substring proposals conflicting with nothing → promote (A2-satisfying by
  construction); exact dupes → merge; quarantined-source → reject. Record the closure rate.
  **→ MEASURED 2026-07-18 (sweep built + run, --go):** 261 examined · **mechanical closure 19/261 = 7%**
  (19 duplicates rejected+ledgered · 0 promotable — the DB gate still refuses every re-offered verified
  insert, so the residue is genuinely not-groundable, not stale-blocked · 12 contradiction_holds persist,
  0 released · 1 owner-unresolvable). **Residue for the A/B decision: 242.** Option A's premise
  ("mechanical closure is high") is FALSE — the residue needs either the dose-capped operator queue
  (A, ~242 items at ≤10/day ≈ 5 weeks) or the funeral (B). Operator decision, now evidence-backed.
- **Option A (drain is real):** if mechanical closure is high, keep the sweep on a timer + a
  dose-capped operator batch queue (≤10 one-tap items/day in the digest, A71) with an SLA; unactioned
  items past horizon expire to labeled `inferred_*`, never linger.
- **Option B (the honest funeral):** if the residue still needs Jonathan at scale and doesn't drain in
  2 weeks — **freeze `proposed_facts` writes**, mark the loop dead, and re-scope A19's language to
  what is true: consensus = mechanical reconcilers (field, geometry) + operator corrections. Stop
  feeding a queue nobody drains; a dead mechanism honestly buried beats a live-looking lie.
- Either way: contradictions (44) get owners + recheck conditions via composer dissent writes; the
  12 `contradiction_hold` proposals are the first owned batch.

## 7. Companion lanes the composer depends on (scoped, not totality)

- **Intake exit ramp (PR-C2, P1):** `pending_classification` (1,156) needs an automated or batch exit —
  even coarse (`ingested_usable` vs `needs_human`) — or the composer answers from a sliver by doctrine.
  Fail-closed stays for evidence-tier absorption; a coarse usability tier is not a connectivity claim.
- **Temporal spine, scoped (PR-C4, P2):** explicitly **defer A67 totality**. Ship: one forward-date
  home for the matters that matter (court dates) + an honest `undated: n` count in every status frame.
  No "calendar is the pulse of everything" claims until the body has date columns.
- **Fleet self-consensus (PR-C5, P2):** one *generated* inventory — systemd units ∪ `agent_registry` ∪
  scripts/ — reconciled like any other concept ("consensus about self"). The 42 `unset` tiers classify
  to `dead` or `wartime_only`; `agent_work_queue` (616 pending) gets the same drain-or-funeral gate as §6.
  CLIs remain as plumbing; **the composer + gap drive become the only product entry points.**

## 8. Honest capability contract (MASTER_PLAN-facing)

Until the composer is live, the plan must not claim: "ask anything, one grounded answer" · "multi-user
Leo" · "verified truth for the whole corpus" · "calendar is the pulse of everything." It may claim:
client-isolated provenance-tagged storage · specific deterministic tools · operator-correctable spine ·
fail-closed blocking of bad sends (which does not guarantee good ones). **The honesty is part of the
prescription** — a §4A build-status row for the composer keeps the gap grep-able.

## 9. What this layer is NOT

- Not a new store (A50): briefs are the only caches, rebuildable at will.
- Not a writer: auto-adjudication flows through existing gated writes (V3/V4/A20 fire as usual);
  the composer itself writes only dissent rows + audit log.
- Not an LLM judge (A24).
- Not a projection bypass: composer output is the INTERNAL plane; A79 clamps, A75 shapes, downstream,
  unchanged — two-plane law intact.

## 10. Order of implementation

1. `compose_answer` + audit log (every envelope logged — the emission-audit half rides for free)
2. Wire Leo **both channels** through it only (the done-test)
3. Adjudication decision gate: measure → drain or funeral (§6)
4. Reconcile + gap batch (write-side attach; composer emits typed gaps, drain consumes them)
5. Intake limbo exit (even crude)
6. Wartime evidence track continues in parallel throughout (2016 Deed CTC · chain holes · 1132–1134
   vision-OCR) — highest external value, never queued behind architecture
7. Map keystones once the composer can already list living titles correctly

## 11. Metrics (mechanical trend-lines)

1. `proposed_facts` pending: 261 ↓ (or frozen-with-funeral, recorded)
2. un-owned open contradictions: 44 → 0
3. raw-reader inventory (A75's 36-script list = the A86 graduation tracker): ↓
4. cross-surface identity probe (TG = Messenger frame): green
5. "clueless"-class probe families: green without per-shape patches
6. `pending_classification`: 1,156 ↓ once the exit ramp lands
