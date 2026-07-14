# LandTek — Canonical Domain Ontology

> **Purpose.** One authoritative map of *what concepts exist* in this system, *which table
> is canonical* for each, and *which tables are drift/staging/legacy* so no agent "consolidates"
> the wrong pair or writes a fact into a dead table. This is the concept-level companion to
> `ARCHITECTURE.md` (the technical-layer view) and `SYSTEM_CONSTITUTION.md` (the verified-facts view).
>
> **Grounded against the live schema on 2026-07-05** (`n8n-postgres-1`, DB `n8n`, schema `public`).
> Rowcounts are `pg_stat_user_tables` live estimates — a freshness signal, not an exact count.
> **This file is checked against reality, not authored from memory.** Re-ground before trusting a
> rowcount older than a few weeks (`scripts/landtek_git_routine.sh` era).
>
> **Structure & growth:** how this document is organized (the five logical layers, state markers, the
> new-domain template, invariant conventions, and the maintenance protocol) is defined in
> `docs/ONTOLOGY_STRUCTURE.md`. Add domains by *appending* (§2.N + new A-numbers), never by renumbering.
>
> **Ontology version: v0.42 (2026-07-14).** **Property Development + Revenue precondition spine LANDS
> (deploy_911 schema/engine; deploy_912 V12 shadow).** Graduates two Future Domains in one spine
> (Revenue/Valuation/Portfolio + Construction/Project Delivery — design `docs/PROPERTY_DEVELOPMENT_SPINE.md`).
> Hub-on-`property_assets` (origin=title stubs vs seed/operator curated); generalized ledger
> `asset_preconditions` (all four modes; asset-owned = engine-derived cache; project-owned sourcing);
> `development_projects` / `development_permits` / link tables (`asset_titles` · `asset_map_parcels` ·
> `asset_survey_parcels`); views `v_development_board` · `v_asset_inventory`. **A81–A84 MINTED.**
> **V12 SHADOW (log):** owner-existence + cross-client isolation on the spine tables (polymorphic
> `asset_preconditions.owner_code` has no FK — V12 is the floor). A80 remains highest *prior* mint;
> A81–A84 continue the series. Live proof: 83/83 client_code · 1 project · 38 preconds · 10/10
> truth_tests. **v0.41 (2026-07-12).** **A62 re-audited + scope-corrected** (required legs green;
> encrypted offsite optional / transport-blocked on gdrive-sa 403). **v0.40 (2026-07-12).** **The
> comms buildout brought up to law (L4 unblocked).**
> **A79 MINTED** (role clamp at the single gate — deploy_880 built it citing an invariant that didn't exist;
> law now matches build): role from `comms_role_policy`, counterparty ⇒ facts/strategy refused, clamp emits
> `{disclosure_ceiling, projection_profile}` for A75 — clamp decides, projection shapes. **A80 MINTED ○**
> (output disclosure classified BEFORE the clamp: verified_fact/strategy/contradiction/cross_matter_cascade/
> general; unclassifiable ⇒ most-restrictive, recorded per emission) — the richer classifier L4 consumes when
> built. **A76 updated**: P2 shadow-live (deploy_882), two-plane split is law, the VIEW is the graph carrier
> (P1 ruling ratified; fact_edges stays drift), per-hop guard's NULL semantics recorded as load-bearing.
> Registered: `meta_pulse_state` · `assistant_proposals` · `parcel_course_proposals`.
> > **Ontology version: v0.39 (2026-07-11).** **A77/A78 LAND (deploy_870 executor + desk verification) — the
> P2 substrate precondition is MET.** A77: graded bind (0.80 threshold, held-never-guessed) + writer-lane
> owner gate (>99% of automated writes) + raw-text audit trail, truth-floored; **V11 null-owner edge guard
> shipped in shadow (deploy_871)** — closes the V4 NULL bypass at the DB for the remaining writers (proven:
> logs on doc 1172, block-mode RAISE, no false fires). A78: contradiction-at-ingest live (held upstream of
> propagation) + verified-basis already DB-enforced + re-arm/challenge cycle, truth-floored. A74 first floor
> (recheck_condition + auto-release, ingestion class). Suite 153-green. P2 may dispatch, carrying the
> document-bridge constraint. **v0.38 (2026-07-11).** **A62 v2 — the survivable record, redesigned and FULLY GREEN.**
> Operator reassessment: the full nightly dump was 2.6GB of non-record around an 86MB record, and the off-box
> leg had died twice on third-party knobs. v2 = domain dump (94% smaller) + the Mac as the off-box node
> (tailnet pull, sha256 receipt, $0, no third party) + Sunday full dump local; B2 retired, no cap raise
> needed. Restore drill RUN (faithful, 2042=2042). The standing A62 gate-note red is CLEARED.
> **v0.37 (2026-07-11).** A75 graduations applied (executor close-out, desk-verified live):
> **verify-worker** (2nd agent pull path — scope in `doc_worklist` SQL, degrade=hold-the-tick) + **pulse-
> orchestrator** (1st PUSH path — dose ceiling executable via the profile) now flow through RecipientProfiles;
> truth-floor `test_recipient_projection.py` incl. the un-wired inventory (36 raw readers = the tracker).
> **v0.36 (2026-07-11).** **A76 — relationship equilibrium (the reactive half of A70,
> 🟡 doctrine).** Every interaction is a graph perturbation: ego-network recompute BEFORE any surface —
> contradiction surfaced (A65's register), obligation via A68, cascade via keystones, cross-client edges
> REFUSED (A5 hard constraint). Accuracy internal / gentleness external (the A75 boundary generalized to the
> whole web). Design: `docs/RELATIONSHIP_EQUILIBRIUM.md` — grounded (corrected the draft: no `obligations`
> table exists; `fact_edges` is an empty seed; `contradictions` 44 sit out-of-lane awaiting P3, which
> graduates A65 too). Phased P1–P4 shadow-first; floors only on a negative-tested propagation function. *(v0.36 also RECORDS
> the peer-authored **A77** — ingestion fidelity: resolution + media→fact gates before an artifact seeds the
> fact graph — and **A78** — verified is EARNED, never promoted; a record contradicting a verified fact is
> refused/held AT THE GATE, the gate-side complement of A76's contradiction-at-propagation. Both landed from
> the answer-gate window without a history entry; desk-validated, correctly 🟡.)*
> **v0.35 (2026-07-11).** **A75 — universal recipient projection (one truth, N
> recipient-shaped projections, never N sources).** Generalizes ClientProjection (A32/A33) to every
> recipient: a RecipientProfile fixes WHO (A5 wall in the query) · PURPOSE (next increment) · FORM (HUMAN
> translated vs MACHINE handles-intact) · DOSE (push ceiling vs PULL_COMPLETE — humans fail from too much,
> agents from too little). Design `docs/RECIPIENT_PROJECTION.md` · registry `leo_tools/recipient_projection.py`
> · first agent proof: the ombudsman hunter's fact slice now flows through its profile.
> **v0.34 (2026-07-11).** **A70–A74 — the identity axioms + the awareness post-mortem.**
> A70 (incorporation precedes decision — the metabolism gate) · A71 (hydroponic cadence — feed to
> metabolizable capacity) · A72 (profit is the shadow of usefulness) — designer-window authored, desk-validated
> per `WORKORDER_A70-A72_incorporation.md`; **A70's first floor is LIVE**: `scripts/incorporation_gate.py`
> (fuses matter_readiness + A57/A67 + A5, verdicts recorded in `incorporation_verdicts`, fail-closed) wired
> into the Ombudsman playbook path + truth-floored (`test_incorporation_gate.py`, count-independent:
> no-READY-on-thin · fail-closed · wiring grep-floor; 1891 verified READY at 91 facts — was 0 at authoring).
> A71/A72 stay doctrine (no speculative floors). **A73** (a goal names its evidence dependencies) + **A74**
> (a recorded blocker carries its re-check condition) — from the doc-410 post-mortem (the defendant's own
> title sat unread among 63 dark docs; a "blocked on quota" finding was never re-tested when local vision
> arrived). **v0.33 (2026-07-10).** **§2.19 Calendar & Cadence — the pulse (operator vision:
> timelines and goals attached to everything, agentically).** Concepts: CalendarEvent (`calendar_events`, 27) ·
> DerivedObligation (`deadline_extractor`) · timeline-attachment (grounded gap: `work_orders`/plays/objectives
> have NO forward-date column) · Cadence (digest + S14 pacing). Invariants **A67** (temporal totality — every
> active governed object dated or explicitly dateless; generalizes A57) · **A68** (a date is a fact: derived
> obligations carry provenance; prose dates never promoted forward — the 642/644 trap as an axiom) · **A69**
> (the calendar sets the cadence; the pulse is client-scoped, projection-rendered, S14-gentle by construction).
> Build lanes: `docs/CALENDAR_CADENCE_DIRECTIVE.md` (C1 totality → C2 derivation → C3 client pulse).
> **v0.32 (2026-07-10).** **Five assumption-level invariants — A62–A66** (from the "what
> haven't we governed" review; each grounded live before writing): **A62** the record survives the machine —
> 🟢 asserted, `truth_tests/test_survivable_record.py` (dump fresh ≤26h + size floor · log-window clean covers
> the rclone off-box copy network-free · restore-drill days-since reported; the nightly pg_dump existed but was
> UNGOVERNED) · **A63** a human sign-off is an authenticated identity, never a string (grounded: `--grant --by`
> is free text; build = SUPERVISION_DIRECTIVE §9-D4) · **A64** chain of custody — evidence binaries verify
> against intake hash (periodic sweep pending; court-facing) · **A65** truth has an arrow of time (later
> verified fact supersedes; `contradictions` gets an owner) · **A66** external content is DATA never
> instructions (S1–S4 generalized stack-wide). Suite +3 (all-green at add).
> **v0.31 (2026-07-09).** §2.4 gains the geometry-consensus concepts (routed by the mapping
> desk, tables live deploys 818/819): **CourseAssertion** (`parcel_courses`, 83 — per-source course w/ verbatim
> `raw_call` excerpt; `geometry_consensus.py` aligns copies → corroborated/single-source/CONFLICT, the geometry
> analogue of `field_consensus`; parcels written only on closure + ≥1 independent area affirmation) and
> **CourseCorrection** (`parcel_course_corrections` — operator-provenance corrections that outrank OCR, A6-clean).
> Closes the coverage gap the sentinel flagged (53/54→54/54). Companion: `docs/GEOMETRY_CAMPAIGN_DIRECTIVE.md`
> (the campaign order + V6 soak/flip plan).
> **v0.30 (2026-07-09).** **§9 handoff closed — A61 GRADUATES 🟢, A59 stays 🟡 (trigger
> named).** Grounded desk review of the supervision desk's deploy_810 (D1/D2/D3 executed in one commit):
> **A61** → 🟢 enforced-by-construction — `agent_registry` (99 rows, ALL provisional, 0 self-raised) +
> `fleet_registry.py --grant` (refuses without `--evidence` + `--by`); both §9-D3 trigger halves met.
> **A59** stays 🟡 half-met: sentinel + 3 lanes shipped, but 0 live orders — graduation trigger named (first
> LIVE order cycle through a Phase-2 lane). §2.12 oriented `agent_registry` + `supervisor_sentinel.py`
> (closes the coverage gap the deploy_811 verification flagged mid-flight); §2.18 AutonomyTier → 🟢 active.
> Builder's missing §9 sign-off noted + the verification record written there by this desk (the
> GovernanceHandoff durable-artifact rule). Open to supervision desk: classify the 42 `unset` tiers; first
> live Phase-2 order.
> **v0.29 (2026-07-09).** **Coverage + graduation-trigger tidy (completes the v0.28
> re-ground).** (1) `incorporation_log` (the §6B W4 connectivity-trend table, `incorporation_status.py --log`)
> oriented in §2.17 components — closes the open 2026-07-08 `ontology_coverage_gap` finding
> (`document_type_proposals`, the finding's other table, was already named by v0.22). (2) Last LIVE stale-V6
> prose re-grounded — the §2.4 note still said "shadow-DRAFT, still not applied"; §4's A9 row was fixed by
> v0.28 but `--enforcement` parses only §4 rows, so blockquote prose drifted past it. Changelog entries
> (v0.7/v0.8/v0.9) left as-is — history records what was true then. (3) **V5 (A35) and V7 (A25) now carry
> NAMED graduation triggers** per the `ONTOLOGY_ALIGNMENT.md` §9 bar, joining V6 (A9) and V8 (A42/§6B pilot):
> each names its dormancy honestly (V5's pipeline hasn't written yet; V7's churn is low) so a 0-findings
> shadow is never mistaken for flip evidence — every log→block flip is now trigger-named, none is "after soak."
> **v0.28 (2026-07-09).** **Enforcement-reality check built** — `ontology_check.py
> --enforcement` verifies every §4 validator-mode CLAIM (ENFORCED(block) / shadow / not-applied) against the
> LIVE `ontology_validator_config` + `ontvv_v*` triggers; phantom enforcement (doc claims a guard that is
> un-flipped or dropped) = exit 1 + a daily-sentinel `phantom_enforcement` finding. The rung above
> `--invariants` (artifact exists → enforcement is LIVE). Negative-tested both ways (V9 un-flip + V10
> trigger-drop caught, rolled back). **First run caught 3 real stale rows, re-grounded same day:** A2 (V3 was
> already BLOCK, row said shadow) · A9 (V6 already APPLIED in shadow on both arms, row said not-yet-applied) ·
> A52 (loose V4 cite). Governance directives filed: `SUPERVISION_DIRECTIVE.md` §9 (D1 Phase-2-scoped-by-A59 ·
> D2 stalled-order sentinel · D3 unified fleet roster → A61 registry) + `ONTOLOGY_ALIGNMENT.md` §9 (the
> 5-step validator graduation checklist + blocked-write-visibility backlog).
> **v0.27 (2026-07-09).** **NEW §2.18 Service Delivery & Deliverables + invariants A57–A61 —
> the AFFIRMATIVE side.** ~50 of 56 prior invariants governed what an agent must NEVER do; §2.18 governs what a
> premium service provider must ALWAYS do: **A57** deadline totality (Principle 2 as an axiom — surface fresh +
> complete, gaps reported never fabricated; `truth_tests/test_deadline_totality.py`, 🟢 asserted, negative-tested) ·
> **A58** deliverable integrity (WorkProduct + machine-listable manifest + immutable-once-delivered, ○) · **A59**
> governed task completion (a task finishes or surfaces — the Supervisor Phase-2 target, ○) · **A60** metered
> inference ledgered + budget-gated (Principle 8 as an axiom; pins the n8n blind spot as a tracked violation) ·
> **A61** the autonomy ladder is governance (tier raises = metric gate + human sign-off, recorded). Also names
> **GovernanceHandoff** (§2.12) — the directive→review→invariants→sign-off→graduation pattern that ran the
> composition layer. +3 assertions (suite 105-green at add). **v0.26 (2026-07-09):** composition layer governed + enforced same-day —
> A54 (client-scoped composition) + A56 (finalized-filing immutability) 🟢 ENFORCED via **V9/V10 block triggers**
> on `case_thread_documents` (flipped after clean pre-flight; extend to `filing_exhibits` when built); A55 (a part
> inherits its parent, never separately gated) 🟡 honored-by-absence. **v0.25 (2026-07-08).** **A53 law-completeness check added** — `truth_tests/test_matter_law_is_embedded.py`
> (deploy-gate + nightly) asserts every legal authority a matter relies on is available OFFLINE (local `full_text`
> or embedded `legal_chunks`): **59/59, 0 gap** (LGC · PD 1529 · RA 11032 · RA 3019/6713 · Civil Code · RPC · Constitution),
> negative-tested. A53 is now two-sided + corpus-checked (offline_audit core capability + this law completeness).
> Suite 96→98. **v0.24:** **Offline sovereignty is now a first-class invariant — A53.** The
> stack REASONS with no internet: the local core (Postgres + Ollama + embedded `legal_chunks` + `extracted_text`)
> is self-contained; every external (Gemini/Telegram/Gmail/Drive/GitHub/lawphil) is an EDGE, never required to
> reason. 🟢 asserted — backed by `scripts/offline_audit.py` (VERDICT green). Elevated from a scattered rider
> (A17/A46/A50) + `ONTOLOGY_STRUCTURE §5` doctrine to a numbered axiom.
> **v0.23:** **Hybrid-retrieval governance — Postgres SoR + Qdrant projection.**
> §2.17 clarified (A41 is store-agnostic: the `embedded` signal is the Postgres flag `corpus_backfill_state.embedded`,
> NOT presence in any vector store — so Qdrant is invisible to the gate, A43 stays fail-closed) + **invariants
> A50** (RetrievalProjection is derived/rebuildable, never authoritative) · **A51** (every Qdrant payload traces to
> a `documents.id` + carries SoR-projected client/matter) · **A52** (retrieval isolation holds in BOTH tiers +
> reconciles to SoR — a mis-scoped filter = cross-client leak, the top risk). **Boundary: V8 is Postgres-resident
> and does NOT reach Qdrant; the projection enforcement is a cross-tier audit the ingestion/ops side builds.** All
> ○ forward-governance (Qdrant not yet the live store; `RAG_RETRIEVAL_ARCHITECTURE_DIRECTIVE` pending commit).
> **v0.22:** **Extended document/semantic model GRADUATED** (converged design of
> the ontology desk + ingestion agent, deploy_785/787). §2.17 extended (DocumentSignal · DocumentClassification ·
> DocumentRole · DocumentFiling/Inventory + the Semantic layer Entity/Fact/Relationship) + **invariants A44–A49**.
> **A48 was GROUNDED-corrected before graduating:** the draft "a Fact ⇐ a ConnectedDocument" was falsified (971
> fact-source docs, only 84 connected; even verified-tier scoping too strong at 13/484) → A48 now asserts a Fact
> requires the **`text` signal** (not the 5-signal gate), backed by `truth_tests/test_fact_requires_text.py`
> (suite 94→96, negative-tested). Q6: `knowledge_graph_triples` canonical, `entity_relationships` drift. All
> additive; A41–A43 + `_connect_verify` untouched. **v0.21:** **A42 DB write-guard built — V8 shadow.** `ontvv_v8_provenance_earned`
> trigger (`BEFORE INSERT OR UPDATE OF model_used ON documents`, config `V8='log'`, deploy_769) logs
> `ONTOLOGY_PROVENANCE_UNEARNED` when a `model_used` stamp lacks a completed `extraction_runs` row — the
> real-time complement to the batch `test_provenance_earned_from_run.py`. Resilient, non-blocking in shadow;
> verified 0/86 false-fire + block-mode RAISE proven. A42 → asserted(batch) **+ shadow write-guard**. The last
> §2.17 code follow-on is now closed. **v0.20:** **A41 now has a corpus-wide mechanical assertion** —
> `truth_tests/test_connected_document_count.py` (deploy gate + nightly, suite 89→91): a count-independent
> consistency check that every `model_used`-stamped doc clears all 5 signals (86/1579 now governed + printed,
> not anecdotal), negative-tested to bite. A41 → gate-enforced **and** corpus-asserted. **v0.19:** **New §2.17 Document Connectivity & Provenance** — models the
> live §6B connectivity work: `ConnectedDocument` (⊂ IngestionComplete) · the 5-signal fail-closed
> `ConnectivityGate` (`supervisor.py::_connect_verify`) · `DeterministicConnectStage` vs the EARNED
> `ProvenanceStamp` (`documents.model_used`) · the deterministic-vs-earned boundary + embedded's one canonical
> source (`corpus_backfill_state.embedded`, not `rag_local`). Invariants **A41** (all-5-signals),
> **A42** (`model_used` earned, never fabricated — candidate shadow V8, flagged), **A43** (gate fail-closed).
> Resolves the `ONTOLOGY_ALIGNMENT.md` G4 gap; A41–A43 were the guard's forward-references, now defined.
> **v0.18:** **A32 enforcement begins — client render-audit shadow guard.**
> `scripts/ontology_check.py --render-audit` (+ daily sentinel) projects every leak-prone field's raw values
> through `client_ontology` and flags any forbidden internal token (matter_code/§/docket/CTN/gmail#/§4B-tag/
> raw-provenance) that survives → `holes_findings` `client_render_leak`. Negative-tested (catches flagship
> `MWK-CV26360`); first run 489 scanned / 4 shadow leaks. A32 marker: asserted → **asserted + shadow guard**.
> Flip 🟡→🟢 when leaks=0 AND wired into the deploy gate. **v0.17:** **§2.14 Communications deepened + reconciled to the live coordinator.**
> The `PlatformCoordinator`'s four responsibilities (identity resolution · bus routing · exposure enforcement ·
> activation lifecycle) and the `UnifiedClientPersona`↔`CrossChannelThread` composition (WHO vs WHAT, both keyed
> to `client_code`) are now explicit. **Reconciled to deploy_752: the INTERNAL half went LIVE** —
> `platform_coordinator.py --tick` (`--resolve` conservative identity binder + `--audit` + heartbeat, on
> `landtek-coordinator.timer`) — so PlatformCoordinator/A31 move ○→🟡, and A38 (resolve-before-act) is now
> **asserted** (a real resolver that leaves NULL when unsure). The OUTWARD half (routing/exposure) stays gated.
> New comms invariants **A38** (resolve-before-act), **A39** (per-message exposure decision is
> traceable), **A40** (activation record complete + deactivation symmetric). **New §2.16 Offensive Leverage
> (Ombudsman)** domain model + **A35–A37** (client-scoped candidates/reads/seed-knowledge) landing the
> deploy_750 isolation work in the doc. Corrected the §8.10 stale premise (`model_used` is earned-only 86/1579,
> not 0). *(Note: the corpus-connectivity 5-signal domain is drafted for §2.17 / A41–A43 / shadow V8 — handed
> in reconciled, not yet applied; a pasted directive targeting §2.8/A7–A9/V5 was stale and NOT used.)*
> **v0.16:** A27/A30 given mechanical floors: `truth_tests/test_comms_bus_integrity.py`
> (bus normalization) + `test_comms_activation_audit.py` (held-channel silent-activation guard) — suite 84→89,
> negative-tested to bite (deploy_746). **v0.15:** A25 enforcement begins: **V7 applied in shadow** (deploy_743,
> `log` mode) on `channel_users` — the first comms invariant off the page and onto the DB; A25 marker
> asserted→shadow (Part 1 validity live; Part 2 held on `entity_id`). **v0.14:** §2.15: formalized the **Client-Facing Projection** layer
> (`ClientProjection`/`ClientFacingView`/`ClientSafeField`) + invariants **A32–A34** (client-safe projection is
> mandatory · totality with logged safe-generic fallback · provenance→plain confidence). Presentation companion
> to `UnifiedClientPersona` (A28 = the VOICE; projection = the safe PRESENTATION of facts). **v0.13:** §2.14: added **A31** (the `PlatformCoordinator`, once built, is
> the single authoritative enforcement point for comms identity + routing/exposure). **v0.12:** added **A30**
> (channel activation needs an auditable `channel_audit` record) + enriched the definition (consistent
> persona/memory; audited exposure). **v0.11:** §2.14 Communications extended with **UnifiedClientPersona**
> (🟡 — same personality/memory per client, every channel) and **CrossChannelThread** (○ — one conversation
> across channels), + invariants **A28** (consistent persona) / **A29** (cross-channel thread continuity).
> **v0.10:** Communications & Omnichannel formalized as a Layer III model (§2.14) — CommunicationChannel ·
> ChannelUser · ChannelMessage · PlatformCoordinator (○ planned) · ExternalExposureGate — with invariants
> **A25** (cross-channel identity is client-scoped), **A26** (outbound comms is exposure-gated;
> token-as-switch), **A27** (one bus, one S14 guard). **v0.9:** Six core domains formalized to the §2.4 rigor — Case Theory
> (§2.8), Entity Resolution (§2.9), Client/Matter Separation (§2.10), Fact Harvesting & Provenance (§2.11),
> Supervision & Work Ordering (§2.12), Truth & Reconciliation (§2.13) — with invariants A12–A24. **v0.7**
> formalized the Geometry/Mapping `GeometrySource` + `MapVisibility` vocabularies (§2.4) + staged geometry
> governance. **v0.8** resolves the A9 blocker: **`parcels.client_code` added (deploy_733)** → both geometry
> layers now carry a declared client; V6 authored for both arms (shadow-DRAFT, not applied). **v0.9** adds §9
> **Future Domains** registry + the `docs/ONTOLOGY_STRUCTURE.md` growth framework, and drives A15 (entity
> merge-graph DAG) to 🟢 mechanically enforced (`test_entity_merge_dag.py`, deploy_732).
> Semver: patch = new alias/deprecation noted; minor = new concept class; major = a canonical table changes.

---

## 0. The two ground planes

The `n8n` database holds **both** planes. They are ontologically separate; never model across them.

| Plane | Meaning | Belongs to |
|---|---|---|
| **Domain (LandTek)** | ~200 tables — the legal / land-ops knowledge model below | LandTek |
| **Plumbing (n8n)** | ~50 tables — workflow engine internals | n8n; do **not** treat as domain |

**n8n plumbing (ignore for domain work):** `workflow_*`, `execution_*`, `credentials_entity`,
`shared_credentials`, `oauth_*`, `chat_hub_*`, `instance_ai_*`, `installed_*`, `folder*`, `data_table*`,
`annotation_*`, `webhook_entity`, `tag_entity`, `project*`, `settings`, `migrations`, `user`,
and — critically — **`role` / `scope` / `role_scope`** (these are n8n's platform RBAC, **not** LandTek's
access model; see §6).

---

## 1. The organizing axiom

> **A `document` is the only source of truth. Every other fact-bearing row is a provenance-gated
> projection of one or more documents, and carries a `provenance_level`.** Nothing is "verified"
> unless it names a `source_doc_id` (or `source_id`) + an excerpt. ~40 tables carry a foreign key
> back to `documents`. This is enforced in DB triggers (`deploy_341` + the `ontology_validator` of
> `deploy_691`), not in application code, so **every** writer is bound — Python workers, `psql`, and
> Leo's n8n LangChain.js path alike.

**Provenance vocabulary (canonical set — grounded on live values 2026-07-05):**
`verified` · `operator` (operator-asserted) · `inferred_strong` · `inferred_corroborated`
(corroboration ladder) · `inferred_weak`. *(An earlier draft listed only 3; the live set is 5.)*
*(Resolved deploy_693: `knowledge_graph_triples.provenance_level` was formerly overloaded with
extraction-method strings; the method moved to a new `extraction_method` column and the tier was
rewritten to the canonical vocab. `scripts/ontology_check.py` now reports vocab clean.)*

---

## 2. Concept registry — canonical table per concept

Legend: 🟢 canonical (write here) · 🟡 staging/index (feeds a canonical) · 🔴 drift/legacy (do **not** write; see §3).

### 2.1 Corpus (the provenance root)

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| Document (the atom) | 🟢 `documents` | ~1,480 | hub of the whole ontology; `execution_status`, `version_chain_id`, `content_hash`, `doc_role`/`exhibit_tier` |
| RAG chunk / embedding | 🟢 `rag_local` | ~9,446 | the vector store |
| Extraction pass | 🟢 `extraction_runs` → `extraction_chunks` | ~1,142 / ~833 | versioned by `extraction_contract` (`tct_v3_canonical`) |
| Multi-pass agreement | 🟢 `field_consensus` | ~394 | cross-corroboration between two extraction runs |
| Email-as-document | 🟢 `gmail_messages` / `email_documents` | ~2,151 / ~829 | envelope + body; links to `documents.id` |
| Dedup group | 🟢 `duplicate_groups` → `duplicate_group_members` | ~31 / ~117 | canonical-doc resolution |

### 2.2 Real-world actors & tenancy

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| Legal person / org / ref | 🟢 `entities` | ~4,820 | self-ref `canonical_id` = merge graph; `phonetic_key` (Keesey/Keesee); `verification_lock` |
| Document ↔ actor role | 🟢 `doc_entities` | ~8,928 | performative `role` + `context_excerpt` per doc |
| **Actor lifespan (the axiom carrier)** | 🟢 `actor_lifespan` | ~2 | `alive_from`/`alive_until` + `is_actor_alive_on()`; **trigger blocks post-death instruments** |
| Client (tenancy root) | 🟢 `clients` | ~7 | **`client_code` is the isolation key** (§5) |
| Matter / proceeding | 🟢 `matters` | ~38 | `client_code` FK; `legal_theory`, `forum`, `current_stage`, `next_deadline` |
| Knowledge-graph triple | 🟡 `knowledge_graph_triples` | ~74 | subject–relation–object over entities; underused |

### 2.3 Title / chain-of-title (the signature subgraph)

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| A TCT as an object | 🟢 `titles` | ~77 | `lifecycle_status`, `cancelled_by_title`, provenance-locked |
| Lineage edge (parent→child) | 🟢 `title_chain` | ~107 | `provenance_quote`, `subdivision_plan_id`, locks |
| Transfer event (evidence-gap engine) | 🟢 `title_transfers` | ~41 | CNR status, `evidence_missing`, `cancelled_by_doc_id` |
| Per-transfer rule eval | 🟢 `transfer_doc_status` | ~486 | `title_transfers` × `doc_requirements_law` |
| Encumbrance / instrument on title | 🟢 `instruments_on_title` | ~102 | executor + notary (the void-SPA query) |
| Survey plan | 🟢 `subdivision_plans` | ~64 | `parent_title`→`child_titles`, surveyor, approval |
| Doc ↔ TCT mention index | 🟡 `document_titles` | ~559 | mention count, not a title record |
| Title ↔ matter link | 🟢 `title_matter_links` | ~24 | |
| Raw per-chunk chain extraction | 🔴 `chain_of_title` | ~174 | **staging** from `extraction_chunks`; NOT the curated chain — see §3 |

### 2.4 Geometry / Mapping — the user-facing spatial domain (7 concepts, 2 layers)

The client-facing mapping surface ("see my property; stand inside my boundary"). Two geometry
**layers** (relative vs absolute — never consolidate) carry seven concepts. Legend adds:
**○ planned** (net-new, no schema yet — do NOT build without governance sign-off) ·
**⛔ intentionally schema-less** (an invariant, not a store).

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **MappedProperty** | 🟢 `map_parcels` (row) | seeded (~1) | a property w/ geometry; `client_code`+`matter_code`+`title_no`. Per-LOT today; a multi-parcel property aggregate would bridge to `property_assets` (§8.8) — modeling choice, **flagged** |
| **SurveyGeometry** (relative) | 🟢 `parcels` | empty | metes-and-bounds; `geom_wkt`, `closure_error_m`, `calls`; local metres, un-georeferenced |
| **SurveyGeometry** (absolute) | 🟢 `map_parcels.geom_geojson` | seeded | WGS84; the relative shape placed on the globe |
| **GeometrySource** | 🟡 `map_parcels.accuracy_tier`+`source_note` · `parcels.provenance_level` · `reocr_log.note` | partial | HOW geometry was produced (local-vision-ocr / gemini-ocr / operator-trace / survey-plan / satellite / ortho); controlled vocab TBD — **tier ≠ source** |
| **CourseAssertion** | 🟢 `parcel_courses` (83) | active (deploy_818) | a PER-SOURCE metes-and-bounds course assertion — `title_no` · `source_doc_id` · `seg`/`idx` · `azimuth_deg`/`distance_m` · **verbatim `raw_call`** (the excerpt — provenance carried at course level). Aligned across independent title copies by `scripts/geometry_consensus.py` → **corroborated / single-source / CONFLICT** — the geometry analogue of `field_consensus` (§2.1). An assertion is NEVER a truth-claim: `parcels` is written only when the ring closes **AND ≥1 independent area source affirms** (deploy_819 gate — closure alone passed a well-closed WRONG polygon on T-4497) |
| **CourseProposal** | 🟡 `parcel_course_proposals` | active | proposed course readings pre-adjudication (the A45/A19 proposals pattern applied to geometry) |
| **CourseCorrection** | 🟢 `parcel_course_corrections` (0) | ready (deploy_818) | operator manual correction of a course (review+correct CLI): `action` · corrected `azimuth_deg`/`distance_m` · `reason` · `provenance_level`='operator' — **outranks OCR assertions** in consensus, never a silent edit (A6: the correction is its own provenance-tagged row, the raw assertion stays) |
| **AreaAssertion** | 🟢 `titles.area_sqm` (gated) · `map_parcels.stated_area_sqm`/`area_sqm` · `parcels.stated_ha`/`area_matches` | active | stated (title) vs computed (courses) vs operator-asserted; each provenance-tagged (T-4497=13.9 ha set via truth-override is the pattern) |
| **ExternalMapReference** | ○ `map_parcels.ortho_tiles_url` only | **NET-NEW** | Google Earth/Maps deep-links, KML/KMZ, embedded/tile URLs. Publishing **exports client geometry to a third party** → outward-guarded; **do not build without sign-off** |
| **MapVisibility** | 🟡 `map_parcels.status` (awaiting_plot/plotted/published) + `client_access_tokens` | partial | who sees it via which surface (internal / token-client / earth / app / public); `published` = the held switch (`no-external-exposure-until-ready`) |
| **UserLocationContext** | ⛔ schema-less by design | invariant | device GPS is ephemeral + client-side (browser point-in-polygon in `leo_tools/mapping.py`); **NEVER persisted server-side** (A10) |

> ⚠️ **Do not "consolidate" `parcels` into `map_parcels`** — relative survey shape vs globe-placed shape;
> the bridge is a tie-point georeference (`parcels` → `survey`-tier `map_parcels`). Known trap.
> ⚠️ **`survey_geometry` is a SCRIPT** (`scripts/survey_geometry.py`, the courses→polygon math), **not a table**.
> ✅ **`parcels` now carries `client_code`** (deploy_733 — nullable, FK→`clients`, populated by `_client_of(matter_code)` at write) — symmetric with `map_parcels`; A9 now has a DECLARED client on **both** geometry layers, so V6 covers both arms uniformly (the blocker is resolved; **V6 APPLIED IN SHADOW** — `log`-mode triggers `ontvv_v6_map_parcels` + `ontvv_v6_parcels` live since 2026-07-06; graduation bar in A9).
> **Enforcement:** geometry is *mapped, not gated* (derived shapes, not truth-claims) — but it carries its OWN
> mechanical validators: `closure_error_m` + area-vs-title cross-check. **AreaAssertions that feed legal output stay gated** (they ride provenance-locked `titles`).

**GeometrySource — controlled vocabulary (formalized v0.7).** *How* a geometry was produced, ordered by
fidelity. A SEPARATE axis from `accuracy_tier` (the resulting confidence): a source *implies* a tier, but
they are not the same field. Canonical set:

`local_vision_ocr` · `gemini_ocr` · `operator_trace` · `survey_plan` · `satellite_rough` · `tie_point_georef` · `orthomosaic`

| Source | typical `accuracy_tier` | notes |
|---|---|---|
| `satellite_rough` / `operator_trace` | `rough` | hand-placed on imagery; the "APPROXIMATE" banner path |
| `local_vision_ocr` / `gemini_ocr` / `survey_plan` | `survey`(-pending) | courses read from a title/plan → `parcels`; closure-error validated |
| `tie_point_georef` | `survey` | relative `parcels` shape placed absolutely via a control monument |
| `orthomosaic` | `ortho` | sub-metre drone; the only tier that clears the APPROXIMATE banner |

> ⚠️ **No `source` COLUMN exists yet** — today it's implicit in `map_parcels.source_note` / `reocr_log.note`
> (`ok:local:qwen2.5vl`) / `parcels.provenance_level`. Promoting it to a typed column + enum check is a
> **schema change → flagged, NOT done here.** The vocabulary is fixed now so a future column has a target.

**MapVisibility — surfaces & audiences (formalized v0.7).** Two axes. **Lifecycle** = `map_parcels.status`
(`awaiting_plot` → `plotted` → `published`). **Audience/surface** (canonical set):

`internal_ops` (behind ops-auth) · `token_client` (a `client_access_tokens` magic-link — the only *live*
external surface) · `google_earth` · `app` · `public`

> The last three are **○ planned** and gated by **A11** (audited publish gate) + `no-external-exposure-until-ready`.
> `status='published'` is the switch; flipping it for any audience beyond `internal_ops`/`token_client` is an
> **outward action** → belongs under the outward-guard. Governance boundary detail + the V6 draft live in
> `docs/ontology_validator_spec.md` §8–§9.

### 2.5 Knowledge / claims / facts — **a pipeline, not duplicates**

The proposal that called these "redundant" was wrong; they are gated stages of one flow:

```
proposed_facts (HITL inbox) ──gate──▶ matter_facts (verified ledger)
claims (what we must prove) ──▶ truth_negotiations ──▶ claim_truth_verdicts ──▶ verified_claims
```

| Concept | Canonical table | Rows | Stage |
|---|---|---|---|
| Verified fact ledger | 🟢 `matter_facts` | ~8,853 | post-gate; `fact_kind`, `element_code`, `excerpt`, `as_of` |
| Proposed fact (pre-gate) | 🟢 `proposed_facts` | ~107 | HITL inbox; `status` |
| Litigation claim ("must prove") | 🟢 `claims` | ~6 | `required_to_prove`; underused, distinct from facts |
| Truth verdict on a claim | 🟢 `claim_truth_verdicts` / `verified_claims` | ~6 / ~1 | adjudicated |
| Fact→fact edge | 🟡 `fact_edges` | 0 | aspirational KG edges over `matter_facts` |
| Cross-matter cascade | 🟢 `cross_matter_links` | ~3 | `proof_doc_id`-gated; A supports B |
| Keystone (controlling fact) | 🟢 `keystones` | ~3 | `controlling_matter` → `cascade_matters[]` |

### 2.6 Strategy / matter reasoning

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| Matter freshness | 🟢 `matter_state` | ~33 | `is_stale` fingerprint → re-synthesize |
| Strategic play | 🟢 `matter_plays` | ~40 | `readiness`, `urgency_days`, `score` (Strategy Engine) |
| Legal authority | 🟢 `legal_authorities` | ~60 | statute/jurisprudence; `matter_authorities` links to matter |
| Property-law rule | 🟢 `doc_requirements_law` | ~36 | drives `transfer_doc_status` |
| Ombudsman lead | 🟢 `ombudsman_candidates` | ~40 | element/prescription-gated graft leads |
| ARTA docket | 🟢 `arta_cases` | ~9 | |
| Case thread | 🟢 `case_threads` | ~5 | `thread_scope_sql` (RD title-history thread) |

### 2.7 Interface / comms

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| Channel | 🟢 `channels` → `channel_messages` | ~9 / ~20 | omnichannel bus |
| Outbound send | 🟢 `outbound_messages` | ~1,898 | |
| **Comms guardrail log** | 🟢 `outbound_blocks` | ~14,345 | S14 enforcement — the most-exercised control |
| Leo turn | 🟢 `leo_interactions` | ~2,994 | |
| Client access token | 🟢 `client_access_tokens` | ~7 | token-gated portal; `client_code` FK |

---

### 2.6 Gated-core tables the first pass omitted (added after the deploy_719 coverage audit)

The hand-curated §2 missed genuine evidence-grade concepts. These are **core, gated** (not §8):

| Concept | Table | Notes |
|---|---|---|
| Document ↔ matter join | `document_matter_links` (+ `document_matter_links_unlinked_bak` backup) · `document_links` | the corpus-to-matter connection |
| Per-transfer documents | `transfer_documents` | the evidence-gap engine's doc side |
| The named transferees/defendants | `transferees` | the case's core actors (20) |
| Title fraud flags | `fraud_indicators` | visual title anomalies (CLAUDE.md key) |
| Evidence chain | `evidence_trail` · `evidence_trail_proposals` | fact → supporting doc |
| Gap register (feeds `v_evidence_gaps`) | `record_gaps` | governance depends on it |
| Chunk stores | `legal_chunks` · `document_chunks` | law + doc RAG chunks |
| Matter structure | `matter_parties` · `matter_causes` | parties + causes of action |
| Adjudications / prep | `resolutions` · `prep_requirements` | forum outcomes + prep |
| Case events / lifecycle | `case_events` · `case_stage_transitions` · `case_intelligence_log` · `case_reports` · `case_keywords` · `title_tax_links` · `thread_relationships` | matter timeline + linkage |
| Truth-guard | `hallucination_log` | logged hallucination catches (near provenance) |

## 2.8 Case Theory & Legal Reasoning — *what we must prove, and the move that proves it*

> **Definition.** The layer that turns a matter into a litigable position — the **elements** a cause of
> action requires, the **objectives** and **plays** that advance it, and the **authorities** that ground
> it — the bridge from raw facts (§2.5) to a forum-ready argument. *(Elevates the terse §2.6.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Matter (the proceeding) | 🟢 `matters` (38) | active | `legal_theory`·`forum`·`current_stage`·`next_deadline`; `client_code` FK |
| Cause of action | 🟢 `matter_causes` (9) | active | legal-theory instances per matter |
| Element to prove | 🟢 `matter_elements` (169) | active | the atomic burdens a cause decomposes into |
| Objective | 🟢 `matter_objectives` (21) | active | what a win looks like for the matter |
| Strategic play | 🟢 `matter_plays` (40) | active | `readiness`·`urgency_days`·`score` (Strategy Engine) |
| Party | 🟢 `matter_parties` (19) | active | who is on each side |
| Legal authority | 🟢 `legal_authorities` (60) → `matter_authorities` (88) | active | statute/jurisprudence ↔ matter |
| Litigation claim | 🟢 `claims` (6) | 🟡 underused | `required_to_prove`; distinct from facts |
| Keystone / cascade | 🟢 `keystones` (3) | active | controlling fact → `cascade_matters[]` |
| Offense lead | 🟢 `ombudsman_candidates` (40) · `arta_cases` (9) | active | element/prescription-gated |
| Case thread | 🟢 `case_threads` (5) | active | `thread_scope_sql` |

*Components: Strategy Engine (`strategy_engine/`, `play_engine`), `load_issue_spine`, `case_theories/` module
(per-matter theories + `_clients.py` allowlist). **Invariants: A12–A14.***

## 2.9 Entity Resolution & Canonical Knowledge Base — *one real-world actor, one canonical node*

> **Definition.** The layer that collapses many document mentions of the same person/org/reference into
> one **canonical entity**, maintains the merge graph, and exposes the entity↔document role index the whole
> knowledge base joins on. *(Elevates the entity portion of §2.2.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Canonical entity | 🟢 `entities` (4,820) | active | `canonical_id` self-ref = merge graph; `phonetic_key` (Keesey/Keesee); `verification_lock` |
| Doc↔actor role | 🟢 `doc_entities` (8,928) | active | performative `role` + excerpt per doc (the join spine) |
| Entity type vocab | 🟢 `entity_types` (10) | active | controlled kind vocabulary |
| Merge proposal | 🟢 `entity_merge_proposals` (207) | 🟡 dormant | acted-on then idle since Jun 15 (§3) |
| Resolution audit | 🟢 `entity_resolution_log` (126) | active | applied merges |
| Alias / relationship | 🟡 `entity_aliases` (0) · `entity_relationships` (0) | ○ dormant | schema present, unpopulated — KG-edge aspiration |
| KG triple | 🟡 `knowledge_graph_triples` (74) | 🟡 underused | subject–relation–object over entities |
| Generic change proposal | 🟡 `proposed_changes` (275) | 🟡 partial | entity/data change inbox |

*Components: `entity_resolve`·`consolidate_entities`·`promote_proposals`; `cross_client_sentinel` (merge-drift
guard). A8 (MMK≠MWK) is an entity-conflation carrier. **Invariants: A15–A16.***

## 2.10 Client & Matter Separation Model — *the tenancy firewall*

> **Definition.** The multi-client isolation model: every matter, document, fact, and geometry belongs to
> exactly one **client** (`client_code`), and no data — fact citation, entity merge, doc link, or map — may
> cross that boundary except through an audited allowlist. *(Elevates §5.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Client (tenancy root) | 🟢 `clients` (7) | 🟢 enforced | `client_code` = the isolation key |
| Matter ↔ client | 🟢 `matters.client_code` FK (38) | 🟢 enforced | A5 |
| Doc ↔ matter link | 🟢 `document_matter_links` (2,302) | 🟡 asserted | cross-client link guard = A18 (asserted, not blocked) |
| Cross-client principal allowlist | 🟢 `case_theories/_clients.py` | active | the legitimate-overlap exception (`test_cross_client_integrity`) |
| Internal-vs-outward registry | 🟢 `internal_targets` (4) | active | operator + sim; the `outward_guard` classifier |
| Cross-client drift flag | 🟢 `cross_client_flags` (0) | 🟢 clean | detector output (0 = clean) |

*Enforcement: A5 (V4 block-trigger on `matter_facts`), `cross_client_sentinel`, `test_cross_client_integrity`
(3 assertions), `_client_of()` resolver. **Invariants: A17–A18.***

## 2.11 Fact Harvesting & Provenance — *how a document becomes a citable fact*

> **Definition.** The gated pipeline that lifts raw document text into the **verified fact ledger**: candidate
> facts land in an inbox, pass a provenance gate (cited doc + verbatim excerpt), and only then become
> authoritative `matter_facts` that legal output may quote. *(Elevates §2.5 + §1.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Verified fact ledger | 🟢 `matter_facts` (15,554) | active | `fact_kind`·`element_code`·`excerpt`·`as_of`; the authoritative store |
| Proposed fact (pre-gate) | 🟢 `proposed_facts` (213) | 🟡 loop-open | HITL inbox; adjudication loop unclosed (§3) — NOT authoritative |
| Provenance tier | 🟢 `matter_facts.provenance_level` | 🟢 enforced | 5-value vocab (§1); A1 NOT NULL |
| Evidence chain | 🟢 `evidence_trail` (30) · `evidence_trail_proposals` (72) | 🟡 partial | fact → supporting doc |
| Encoding audit | 🟢 `fact_encoding_log` (1,326) | active | harvest trace |
| Hallucination catch log | 🟢 `hallucination_log` (2) | active | logged truth-guard catches |
| Gap register | 🟢 `record_gaps` (6) → `v_evidence_gaps` (457) | active | what's missing (derived) |

*Enforcement: `enforce_provenance_facts` trigger (excerpt = verbatim substring), `ontology_validator` V3 (A2),
`_safe` views. Components: `harvest_facts`·`source_read_facts`·`reconciler`. **Invariants: A19–A20.***

## 2.12 Supervision & Work Ordering — *governed execution across the fleet*

> **Definition.** The Postgres-native coordination layer that routes a unit of work through multi-step,
> resumable **work orders** under fail-closed governance, funnels every outward action through one
> chokepoint, and continuously self-audits the ~50-agent fleet via the holes framework. *(Elevates §8.11/§8.14.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Work order (state machine) | 🟢 `work_orders` (5) | 🟡 Phase-2 machinery (deploy_810) | JSONB steps + `current_step` + audit; fail-closed `governance_block()`; 3 lanes (`ocr_remediation` · `evidence_gap` · `deliverable` produce→verify→certify[T3 human]) + the stalled-order sentinel — live flow pending (A59) |
| **Fleet tier registry (A61 substrate)** | 🟢 `agent_registry` (99) ← `fleet_registry.py --sync` (runtime ground truth: 37 systemd timers + cron, overlaid with `agents.py`) | active — ALL tiers `provisional` (42 T1 · 10 T2 · 5 T3 · 42 honest `unset`), 0 granted | ONE enumerable roster (the ~30 previously-invisible runtime agents now rostered); a tier RISES only via `--grant`, which refuses without `--evidence` (metric gate) + `--by` (human sign-off) and is never stomped by re-sync — A61 enforced by construction at the registry |
| **Stalled-order sentinel (A59 "or surfaces")** | 🟢 `scripts/supervisor_sentinel.py` → `holes_findings` + `notifications/pending.txt` | active (nightly, fail-soft) | per-status review horizons (72h, incl. `blocked_governance` so held orders can't rot); auto-closes when the order goes terminal |
| Outward chokepoint | 🟢 `internal_targets` (4) + `outward_shadow_log` (0) | 🟡 shadow | `outward_guard` at the exits; block-mode dormant |
| Gap-finding routine ledger | 🟢 `holes_findings` (22) · `holes_runs` (3,018) | active | self-audit (dispatcher every 15m) |
| Fleet health / pulse | 🟢 `system_heartbeat` (16,377) · `sentinel_alerts` (826) · `agent_audit` (7) | active | T0/T1 report-health tier |
| Comms guardrail log | 🟢 `outbound_blocks` (14,346) | active | S14 — the most-exercised control |
| Derived work source | 🟢 `v_evidence_gaps` (457) | active | the enforced gap-order write-path |
| **GovernanceHandoff** | 🟢 directive docs (`INGESTION_DIRECTIVE.md` §sign-offs · `ONTOLOGY_ALIGNMENT.md` · MASTER_PLAN `Respects:` tags) | active (named 2026-07-09) | the inter-desk coordination pattern, now a NAMED concept: **directive → grounded review → invariants → recorded sign-off → explicit graduation trigger**. This ran the composition layer (handoff→A54-56→V9/V10 flip→graduation, deploys 801-804) without a single collision. Durable artifact + named graduation trigger are what make it work — keep both, every handoff |

*Components: `supervisor.py` (KINDS registry), `SUPERVISION_DIRECTIVE.md` (tier model + §9 handoff record),
`fleet_registry.py` (--sync/--health/--grant), `supervisor_sentinel.py`, `outward_guard.py`,
`holes/` framework + `dispatcher.py`. **Invariants: A21–A22 (+ A59/A61, defined in §2.18).***

## 2.13 Truth & Reconciliation — *is the claim actually true against the record?*

> **Definition.** The adversarial verification layer that tests claims against the verified record and law,
> records verdicts, and — post-`truth_qa` — does so **mechanically** (SQL assertions + write-triggers) rather
> than by LLM interrogation, keeping a durable audit of every truth check. *(Elevates §2.5 + §8.1.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| Truth negotiation | 🟢 `truth_negotiations` (820) | active | challenger runs (`truth_negotiator`) |
| Claim verdict | 🟢 `claim_truth_verdicts` (6) → `verified_claims` (1) | 🟡 underused | adjudicated truth on a `claims` row |
| Back-test suite | 🟢 `back_test_suite` (5) → `back_test_runs` (175) | active | calibration cases (hourly `systems_analyzer` + daily `a1`) |
| Contradiction register | 🟢 `contradictions` (40) | 🟡 out-of-lane | detected internal conflicts |
| Truth audit ledger | 🟢 `truth_audit_log` (2,360) | active | the durable audit (successor to `audit_log`) |
| Mechanical assertion suite | 🟢 `truth_tests/` (82 assertions) | active | deploy-gate + nightly; the `truth_qa` replacement |
| Egress hallucination canary | 🟢 `holes.a3` (mechanical) | active | ungrounded-title guard (deploy_728) |

*Doctrine: mechanical > LLM (A24). Enforcement: `ontology_validator` V1/V3/V4, `truth_tests/run_all.py`.
The LLM `truth_qa` retirement is recorded in §4. **Invariants: A23–A24.***

## 2.14 Communications & Omnichannel — *one identity, many doors, one governed exit*

> **Definition.** The multi-channel reach layer: a person contacts LandTek (and Leo replies) over any
> supported channel (Telegram · Email · WhatsApp · Viber · Messenger), meeting **one consistent persona and
> memory**, normalized onto a single bus, resolved to one client identity, and released outward only through
> an **audited** exposure gate. *(Elevates the terse §2.7 and the §8.6 operational cluster.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **CommunicationChannel** | 🟢 `channels` (~9) → `channel_messages` (~20) | active | a supported medium; per-channel readiness varies — Telegram 🟢 live · Email 🟢 inbound-live/send-held (deploy_654) · WhatsApp 🟡 armed/tokenless (662) · Viber 🟡 armed/tokenless (663) · Messenger ○ not built |
| **ChannelUser** | 🟡 `channel_users.mapped_client_code` | partial | a person across ≥1 channel → **one** `client_code`; slot exists, resolver + separation-guard not built (A25) |
| **UnifiedClientPersona** | 🟡 `conversation_context`/`conversation_chunks` (🌱 dormant) · `chat_notes` · `client_history` · `leo_interactions` + the shared AI `systemMessage` (config, ⛔ not a table) | partial | the AI's persistent identity, tone, memory & relationship state **per client** — the same persona on every channel; relationship data exists but cross-channel memory is dormant + not persona-keyed (A28) |
| **ChannelMessage** | 🟢 `channel_messages` (~20) + `channel_audit` · `outbound_messages` (~1,898) · `outbound_blocks` (~14,346) | active | inbound/outbound on the bus, `channel_audit` the event/audit companion; older stores (`leo_interactions` ~2,994, `gmail_messages`) still carry most live traffic — the bus is the *intended* single normalizer, not yet universal (A27) |
| **CrossChannelThread** | ○ *(none — planned; `channel_messages.reply_to_id` is intra-channel only)* | **NET-NEW** | one logical conversation spanning channels for the same person; continuity resolves via the same `client_code` as A25 (A29) |
| **PlatformCoordinator** | 🟡 `scripts/platform_coordinator.py` (`--tick` via `landtek-coordinator.timer`) | **partial — internal live** | **INTERNAL half is live (deploy_752):** `--resolve` (conservative identity resolver → binds a `channel_users` identity to one `client_code` only on a unique match, leaves NULL when unsure — never guesses/crosses, A25/A38) · `--audit` (writes `channel_audit` activation records, A30) · health heartbeat. **Still ○ planned:** the OUTWARD half — unified bus routing (A27) + per-message exposure enforcement (A26/A39) stay gated behind `outward_guard`; the single-authoritative-for-all-four graduation (A31) is not yet complete. **Do not wire the outward half without governance sign-off.** |
| **ExternalExposureGate** | 🟡 `internal_targets` (4) · `outward_guard_config` · `outbound_blocks` · `channel_audit` (activation record) | partial | *when* a channel may reach outside; email splits inbound/send, inline-send channels gate on the token = the switch (A26); channel activation needs an audit row (A30); rides A21 + `no-external-exposure-until-ready` |

> ⚠️ **Token-as-switch (do not confuse the two send models).** Email separates inbound (internal, safe to
> schedule) from `--send` (outward). WhatsApp/Viber/Messenger send **inline** — gated only by whether the
> provider token + webhook are provisioned, so provisioning IS opening the channel (an outward action).
> ⚠️ **The bus is not yet the single point of truth** — `channel_messages` (~20) is light; convergence
> onto it is the PlatformCoordinator's remit. Do **not** assert the older comms stores as drift (§3) yet.
> ⚠️ **Persona is per-client, not per-channel** — UnifiedClientPersona + CrossChannelThread key tone/memory
> to `client_code`, so switching channels must **not** reset personality or history (A28/A29); cross-channel
> continuity depends on A25 resolving identity first. Channel activation is itself audited in `channel_audit`.
> **Enforcement:** S14 (human-readable · one-point · no-double-tap) in `tg_send.py` → `outbound_blocks`;
> outward funnels through `outward_guard` (A21, shadow). Client identity across channels rides A5 (A25).

> **PlatformCoordinator — the four responsibilities (INTERNAL half live deploy_752; A31 the single locus).**
> It owns exactly four duties, previously **scattered** across adapters, bridges, and timers — the
> fragmentation A31 exists to prevent. Two are now live in `platform_coordinator.py --tick`, two remain gated:
> 1. **Identity resolution** 🟡 **live (`--resolve`)** — resolve a `ChannelUser` to one `client_code` before any
>    reply or persona-memory write (A38), or hold it `unresolved`; the v1 resolver binds only on a unique match
>    and leaves NULL when unsure — never guesses, never crosses clients (A25).
> 2. **Routing / bus normalization** ○ **planned** — land every event on the unified bus and dispatch to the
>    right handler and client persona (A27); still distributed across the bridges.
> 3. **Exposure enforcement** ○ **planned** — release outward only through the gate with a per-message recorded
>    decision (A26/A39); today `outward_guard` holds this separately (shadow).
> 4. **Channel health + activation lifecycle** 🟡 **live (`--audit`)** — write the audited activation record
>    for each active surface into `channel_audit` (A30/A40); deactivation symmetry + full completeness pending.
> **The internal half (resolve/audit/heartbeat) is safe and running; do NOT wire the outward half (2 & 3)
> without governance sign-off** (§9) — that is the outward-enforcement chokepoint.
>
> **Persona vs Thread — they compose, they don't overlap.** `UnifiedClientPersona` is the **WHO**: the AI's
> identity, tone, memory and relationship state, keyed to `client_code` (A28). `CrossChannelThread` is the
> **WHAT**: one continuous conversation for that person spanning channels (A29). The thread is what makes the
> persona's memory *coherent* across doors — moving from Telegram to email continues the **same** thread, so
> the persona recalls the same history. Persona without thread = consistent voice but amnesiac continuity;
> thread without persona = a continuous log with no relationship. **Both resolve through the same `client_code`
> (A25), so identity resolution (A38) is the prerequisite for either** — which is why all three converge on the
> PlatformCoordinator as the one place resolution happens.

*Components: `leo_tools/channel_adapters.py` (webhooks + `/api/channel/send`) · `tg_send.py` (S14) ·
`{email,whatsapp,viber}_channel_bridge.py` (feed + backlog drain) · `landtek-{email,whatsapp,viber}-bridge.timer`
· `channel_audit` (activation/adapter audit) · `conversation_context`/`conversation_chunks` (persona memory, 🌱) ·
`internal_targets`/`outward_guard.py` (exposure gate) · `truth_tests/test_comms_bus_integrity.py` +
`test_comms_activation_audit.py` (the A27/A30 mechanical floors, deploy_746) · `scripts/platform_coordinator.py`
(🟡 `--tick` LIVE — resolve+audit+heartbeat via `landtek-coordinator.timer`, deploy_752; the internal enforcement
point, A31) · `_client_of()`. Lineage: deploy_114 (bus) → 654 (email) → 662/663 (Meta/Viber armed) → 736–747
(§2.14 formalized, A25–A31 + shadow V7 + floors) → **752 (PlatformCoordinator internal half live)**.
**Invariants: A25–A31, A38–A40.***

---

### 2.15 Client-Facing Projection — the client-safe presentation layer

> **The problem it solves.** The domain model stores RAW internal typed fields — snake_case
> `current_stage`, "/"-mashed `forum`, `legal_theory` strategy paragraphs, `next_event` prose full
> of `gmail#`/`CTN`/docket/`§`/matter-code tokens, and §4B provenance tags (`[OPERATOR-ATTESTED]`,
> `[HUMAN VERIFY]`, `[v:…]`). Rendering any of these to a paying client is a defect. This layer is the
> **governed translation** from typed internal concepts → a controlled, client-safe vocabulary. It is the
> **presentation companion to `UnifiedClientPersona`** (§2.14, A28): *persona is the AI's VOICE per client;
> projection is the safe PRESENTATION of facts.* It **rides A5** (isolation — only this client's data reaches
> the view; separation is upstream, not this layer's job), **A6** (inference-flagged — realized client-side as
> plain confidence), and **A11** (no external exposure — the view is token-gated; projection governs WORDING,
> not access).

| Concept | Canonical | State | Notes |
|---|---|---|---|
| **ClientProjection** | 🟢 `leo_tools/client_ontology.py` | **built (this pass)** | the governed translator: `client_stage`(status) · `client_forum`(venue) · `client_matter_kind` · `client_provenance`/`client_confidence`(confidence) · `client_next_step`(clean step) · `friendly_title`/`friendly_date`. Pure, $0, deterministic — no LLM at render. |
| **ClientSafeVocabulary** | 🟢 the enumerated maps inside `ClientProjection` | built | exact-match → keyword → safe-generic, per field; keyed on the LIVE distinct values. |
| **ClientSafeField** | *(concept, not a table)* | — | a field value that has passed through `ClientProjection`; the **only** unit permitted on a `ClientFacingView`. |
| **ClientFacingView** | 🟡 `leo_tools/client_portal.py` (portal + matter-detail); future: client email, the installable PWA/app | partial | any surface a client sees; must render ONLY `ClientSafeField`s. Today it still renders some raw fields — wiring it to render THROUGH `ClientProjection` is the **next step** (A32 not yet enforced). |
| **UnmappedValueLog** | 🟢 `client_ontology.unmapped_report()` | built | records any value that hit the safe-generic fallback → drives principled extension of the vocab; the audit trail of A33 totality. |

> **Governance — what a client MAY vs MAY NOT see.**
> **MAY:** plain matter *kind*; plain *status* (from `current_stage`); plain *venue* (from `forum`); a deadline
> *date* + friendly countdown; a *clean next-step*; grounded facts at `verified`/`operator` tier with plain
> confidence; servable **received** (non-draft) documents. **MAY NOT:** raw internal codes (`matter_code`,
> docket/`CTN`/`SL`, `gmail#`/`doc#`); `§` statute cites; `legal_theory` strategy paragraphs; operator notes /
> internal reasoning (`case_stage_transitions.notes`); raw §4B tags; **draft** documents; `inferred_weak`
> claims as settled fact; anything belonging to another client (A5). **Changing the `ClientSafeVocabulary` is a
> governance act** — a client-facing phrase is reviewed like a truth-QA change; the `UnmappedValueLog` drives
> extension (add a mapping when a real value appears — never guess).

**Invariants: A32–A34.***

---

## 2.16 Offensive Leverage (Ombudsman) — *turning the client's grievance into pressure on officials*

> **Definition.** The offense engine: from one client's verified corpus it derives ranked, element-gated
> graft/misconduct leads against public officers (RA 3019 / 6713 / RPC), assembles a prosecutor's theory,
> and holds every filing for a human. It runs **within one client** — a hunt for client X never sees, seeds,
> or reasons over client Y's officials, allies, or candidates. (Elevates the §8.5 operational cluster.)

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **OmbudsmanMatter** | 🟡 `matters` row + `client_code` (the offense track) | partial | the tenancy root; a hunt runs *within* one `client_code`, scoped by `MATTER_SCOPE` |
| **CandidateFinding** | 🟢 `ombudsman_candidates` (+ `client_code`) | active | one client per row; identity `(client_code, official, violation_code)` — the collision fix (A35) |
| **CaseTheory** | ⛔ *schema-less by design* (assembled at read by `--reason`) | invariant | derived **only** from the active client's findings — never persisted, never cross-client (A36) |
| **SignalPattern** | 🟡 `CASES[client]['roster'/'ourside']` + `THEORY_HINTS` (code config) | partial | the seed roster + own-side exclusion + hints — **client-scoped knowledge** (A37); non-MWK starts empty |

*Components: `scripts/ombudsman_hunter.py` (scan/hunt/verify/reason, all `_client_code()`-scoped) ·
`ontvv_v5_ombudsman` (shadow client-isolation trigger, deploy_750) · `ombudsman_candidates` · `_client_of()`.
**Invariants: A35–A37.*** Filing stays human-gated — these are LEADS, not facts.

---

## 2.17 Document Connectivity & Provenance — *is a document actually wired into the stack, or just sitting in it?*

> **Definition.** The contract for a document being *connected* — not merely stored. A `ConnectedDocument`
> has cleared the **5-signal ConnectivityGate** (`supervisor.py::_connect_verify`), the fail-closed check that
> a (re-)ingested doc actually re-wired to the corpus. It is a strict *subset* of `IngestionComplete` (the
> 6-signal "done" of `docs/INGESTION_DIRECTIVE.md`). The governing distinction is **deterministic vs earned**:
> four signals a *stage mechanically produces*, and one — provenance — that can only be **earned** from a real
> extraction run and must never be fabricated to make a doc "look connected." Live: **86/1579 fully connected;
> 0/388 Paracale** (provenance is the binding scarcity).

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **ConnectedDocument** | 🟡 a `documents` row clearing all 5 gate signals | partial (**86/1579**; 0/388 Paracale) | `⊂ IngestionComplete`; "in the DB" ≠ "connected" |
| **ConnectivityGate** | 🟢 `scripts/supervisor.py::_connect_verify` | **enforced** at the OCR-remediation chokepoint | the 5-signal check; returns ok **only** when zero issues (A43) |
| **DeterministicConnectStage** | 🟢 OCR ladder · `ocr_quality.py` · `rag_embed_local` · `doc_classification` | active | the stages that *produce* the 4 deterministic signals (text · quality · embedded · type) |
| **ProvenanceStamp** (the EARNED signal) | 🟡 `documents.model_used` ← `extraction_runs` | asserted / **earned-only** | the ONE signal a stage can't just set: which engine actually read the doc. 86 earned, **0 fabricated** (A42) |
| **IngestionComplete** (the 6-signal superset) | 🟡 `docs/INGESTION_DIRECTIVE.md` "DONE" | partial | gate's 5 + entity-resolution + `matter_facts` harvest + tracker-baseline — the fuller per-matter target |

> **The 5 gate signals + their ONE canonical source each:** text (`documents.extracted_text` ≥ 50) · provenance
> (`documents.model_used`) · quality (`ocr_quality.score`, latest) · **embedded (`corpus_backfill_state.embedded`
> = true — NOT `rag_local` presence;** the two can diverge, so the gate reads the flag, not the vector store) ·
> type (`documents.document_type`). ⚠ **Deterministic ≠ earned:** the first/third/fourth/fifth are produced by a
> stage; `model_used` is **earned** — backfilled only from a real `extraction_runs` record (the 86 truthful
> stamps came from there), never written to satisfy the gate. Fabricating it is the failure A42 forbids.

**Extended document/signal model (graduated deploy_788 — converged design of the ontology desk + ingestion agent).**
The connectivity core above is one layer of a fuller model — full detail + the layered frame (Raw→Signal→
Semantic→Projection→Agent) in `docs/DOCUMENT_MODEL_DRAFT.md`. First-class concepts, each grounded in live or
proposed tables: **DocumentSignal** (the 5 mandatory gate signals + an extensible `document_signals` ○ store, A44)
· **DocumentClassification** (`documents.document_type`/`doc_role` ← `document_type_proposals` → the proposed
`document_classifications` adjudication layer; **inferred/LLM types are proposals, deterministic-map exempt**, A45)
· **DocumentRole** (intrinsic `doc_role` vs contextual per-matter `relation_kind`, A47) · **DocumentFiling /
FilingLocation / DocumentInventory / FilingRule / SyncRule** (leo primary + Drive secondary + vault; leo-filing is
**outward**, held, A46) · and the **Semantic layer** — `Entity` (§2.2) · `EntityLink` (`doc_entities`) · `Fact`
(`matter_facts`) · `Relationship` (🟢 `knowledge_graph_triples` canonical; `entity_relationships` is drift) —
which **rises from a document's `text` signal and stays cited** (A48), and to which agents contribute only through
the write-gate (A49). All additive/shadow-first; A41–A43 + `_connect_verify` + earned-provenance are untouched.

**Hybrid retrieval — SoR vs RetrievalProjection (governs `RAG_RETRIEVAL_ARCHITECTURE_DIRECTIVE`, deploy_790).**
The connectivity model is **store-agnostic and stays that way** under the proposed Postgres-SoR + Qdrant-projection
split. **A41 does NOT change:** the `embedded` signal is the Postgres flag `corpus_backfill_state.embedded` (not
presence in *any* vector store, deploy_789), so a `ConnectedDocument` is defined entirely by SoR signals — moving
vectors from `rag_local` to Qdrant is invisible to the gate, and A43 stays fail-closed (the gate never depends on
an external cache). Qdrant is a **`RetrievalProjection`** — derived, rebuildable, never authoritative (A50);
every payload traces to a `documents.id` + carries SoR-projected `client_code`/`matter_code` (A51); retrieval
isolation holds in *both* tiers and the projection reconciles to the SoR (A52). **The projection layer's
enforcement is a cross-tier audit (ingestion/ops builds it), NOT V8** — V8 is a Postgres write-trigger and does
not reach Qdrant. *(Directive file pending commit; these invariants guide the build and reconcile on its landing.)*

*Components: `supervisor.py` (`_connect_verify` + the `ocr_remediation` work-order kind that gates remediation
output) · `corpus_backfill_state` (embedded flag) · `ocr_quality` · `extraction_runs` (provenance source) ·
`rag_embed_local` · `document_type_proposals` · `v_incorporation_status`/`v_doc_connectivity` + `incorporation_log`
(`scripts/incorporation_status.py` — the W4 measurement views + nightly `--log` trend of connected-count over time,
MASTER_PLAN §6B W4) · `truth_tests/test_fact_requires_text.py` (A48) ·
`docs/INGESTION_DIRECTIVE.md` (6-signal runbook) + `DOCUMENT_MODEL_DRAFT.md` (extended model) +
`RAG_RETRIEVAL_ARCHITECTURE_DIRECTIVE.md` (○ hybrid retrieval, A50–A52).
**Invariants: A41–A52.***

## 2.18 Service Delivery & Deliverables — *the affirmative standard: on time, complete, traceable*

> **Definition.** The domain that governs what a premium service provider must ALWAYS do — where §2.10–§2.17
> govern what an agent must NEVER do. Three concepts: the **DeadlineSurface** (the stack tells the operator
> what is due, unprompted — Principle 2 as an axiom), the **WorkProduct** (a client deliverable as a
> first-class, manifest-carrying, immutable-once-delivered object), and the **AutonomyTier** (an agent's
> privilege rung, raised only through a metric gate + human sign-off). *Companion: §2.15 governs what a
> deliverable may SHOW; this section governs whether it is complete, on time, and reconstructable.*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **DeadlineSurface** | 🟢 `surfaced_deadlines` (daily `as_of` snapshots) ← `matters.next_deadline` + `client_goals.target_date` via `scripts/deadlines.py::digest` | active | the proactive layer: fresh (written daily) + complete (no dated active matter dropped) — A57. The dateless classification (`needs_date`/`watch`/`orphan`, `classify_gap`) is an HONEST gap — reported, never fabricated (the deploy_642/644 phantom-date lesson) |
| **WorkProduct** | ○ *(none — planned; today deliverables are files from `dossier_pipeline.py`/`case_bundle.py` with no DB identity)* | **NET-NEW** | a client deliverable (dossier · bound PDF · memo · portal view) as an object: assembled only through `_safe` views + ClientProjection (A19/A32), carrying a machine-listable **manifest** of every doc/fact it contains, versioned + **immutable once delivered** (the A56 pattern generalized) — A58. Schema is the delivery side's to design; the ontology fixes identity + invariants |
| **DeliverableManifest** | ○ *(rides WorkProduct)* | **NET-NEW** | the enumerable contents: every `doc_id`/`fact_id` a deliverable contains, so "detailed results" = every detail cited + reconstructable (the traceability gate of the no-hallucination pipeline) |
| **AutonomyTier** | 🟢 `agent_registry.tier` (+ `tier_status`/`tier_evidence`/`tier_signed_off_by`) ← `fleet_registry.py --grant`; doctrine in `SUPERVISION_DIRECTIVE.md` (T0–T3) + per-step `work_orders.governance_block()` | active (deploy_810 — all 99 rows `provisional`, first grant pending) | the privilege rung (read-only → propose → execute-low-risk); a rung raise is a governed, recorded event, never self-granted — A61. Encodes MASTER_PLAN §6A pillar 4 ("earn autonomy slowly, metric-gated") |

*Components: `scripts/deadlines.py` (surface + classify + escalate) · `landtek-deadline-*` timers ·
`truth_tests/test_deadline_totality.py` (A57) · `dossier_pipeline.py`/`case_bundle.py` (the deliverable
producers a future WorkProduct store would receive) · `llm_calls`/`llm_spend` + `cost_governor` (A60).
**Invariants: A57–A61.***

## 2.19 Calendar & Cadence — *the pulse: timelines and goals attached to everything, agentically*

> **Definition.** The temporal spine of the stack (operator vision, 2026-07-10): the calendar is not a
> feature but the PULSE — it sets the cadence for all communications and work. Every governed object with
> a lifecycle carries a forward timeline; obligations are DERIVED from the record agentically (never only
> hand-typed); and the calendar drives a gentle, client-scoped, exposure-gated rhythm of briefs and
> reminders. Extends §2.18's A57 (the matters slice) toward temporal totality. *(Grounded 2026-07-10.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **CalendarEvent** | 🟢 `calendar_events` (27) | active | dated commitments (hearings · filings · meetings); synced/briefed by `scripts/calendar_sync.py` + `calendar_briefer.py`; client calendar access via `mint_calendar_token.py` (token = the A26-style switch) |
| **DeadlineSurface** | 🟢 `surfaced_deadlines` (126, daily `as_of`) | active | §2.18 — the A57-governed proactive layer |
| **DerivedObligation** | 🟡 `scripts/deadline_extractor.py` output → `matters.next_deadline` / surfaced rows | partial | an obligation MINED from the record (court order · statute period · email); must carry its source (A68) and never promote a historical prose date to a forward deadline (the deploy_642/644 trap, gated in `deadlines.py`) |
| **Timeline attachment** | 🟡 `matters.next_deadline` · `client_goals.target_date` | **partial — the A67 gap** | grounded: `work_orders` / `matter_plays` / `matter_objectives` carry NO forward-date column — timelines do not yet attach to *everything* |
| **Cadence** | 🟡 daily digest (07:00 due-dates-first) · `deadlines.py::escalate` · S14 pacing · `agent_deadline_orchestration.py` | partial | the rhythm: lead-time-laddered reminders, never floods — pacing is a GUARANTEE (S14 no-double-tap), not a hope |

*Registered here: `meta_pulse_state` (the pulse's own tick-state, 🟢) · `assistant_proposals` (assistant-suggested actions, HITL inbox — A19-pattern, 🟡) · `assistant_nudge_log` (per-receiver nudge ledger — the A71 dose-accounting substrate, 🟡) · `pulse_work_log` (the orchestrator's idempotency ledger, 🟢 — deploy_840) · `leo_shadow_replies` (the headless-Leo shadow-loop reply ledger, 🟡 — test surface, sends nothing) · `date_proposals` (deterministic date-proposal inbox pre-confirm — deploy_842, the A68 proposal path, 🟡) · `exhibit_spine_proposals` (exhibit-composition proposals pre-adjudication — the A19/A45 pattern on filings, 🟡) · `leo_channel_mode` (per-channel live/shadow switch — deploy_853, the A26-adjacent rollback knob, 🟢). Components: `deadlines.py` (surface/classify/escalate) · `deadline_extractor.py` · `calendar_sync.py` ·
`calendar_briefer.py` · `mint_calendar_token.py` · `agent_deadline_orchestration.py` · `landtek-deadline-*`
timers · `truth_tests/test_deadline_totality.py` (A57). Build directive: `docs/CALENDAR_CADENCE_DIRECTIVE.md`.
**Invariants: A57, A67–A69.***

---

## 3. Drift / legacy — do **not** write here (consolidation backlog)

| 🔴 Table | Rows | Verdict | Canonical instead |
|---|---|---|---|
| `chain_of_title` | ~174 | **Staging.** Raw per-chunk extraction (`source_chunk_id`→`extraction_chunks`); flat, no locks. | `title_chain` + `titles` |
| `finance_transactions` | 0 | **Schema drift.** Cleaner `client_code`/`matter_code` columns but never populated. | `transactions` (~174, holds the data) — *or* migrate data into `finance_transactions` and retire `transactions`; **pick one, don't keep both** |
| `cases` | ~2 | **Legacy.** Older matter concept keyed on `client_id` (int); superseded. | `matters` (~38, keyed on `client_code`) |
| `fact_edges` | 0 | **Aspirational.** Empty KG-edge table. | leave until §2.5 pipeline needs edges |
| `document_entities` | 0 | **Superseded.** Empty variant of the doc↔entity join. | `doc_entities` (~8,928 — holds the data) |
| `audit_log` · `audit_events` | 0 | **Superseded.** Generic audit, never populated. | `truth_audit_log` + `holes_findings` (the real audit) |
| `document_matter_links_unlinked_bak` | ~95 | **Backup.** One-time snapshot of purged links. | `document_matter_links` (prunable after review) |
| **re-OCR result overlap** — `re_ocr_results` (78) · `reocr_log` (44) · `reocr_backup` (54) · `heightened_ocr_results` (0) | — | **Overlap (4 tables, one concept).** Three populated variants of "re-OCR output" built across iterations + the intended DIC target. | **consolidate to one** as part of DIC/remediation activation (§8.10); `reocr_backup` is prunable |
| `event_kind_canonical_def` (13) · `event_kind_taxonomy` (83) | — | **Possible overlap** — two event-taxonomy tables; confirm before consolidating. | pick the canonical event taxonomy |

> **Reconciliation is a post-Aug-12 chore, not a wartime task.** Listing them here *is* the fix for now:
> it stops the drift from compounding by naming the canonical target. Do not migrate live tables during
> the litigation window.

**Built-but-not-acted-upon (a loop, not drift — flagged, not consolidated):** `proposed_facts` (213, ALL
`pending`, still growing) — the reconciler *writes* candidate facts but nothing adjudicates them; the
propose→adjudicate→promote loop never closes (the direct `verify_worker`→gate path is the one that works).
`entity_merge_proposals` (135 accepted / 72 held) was acted upon then went **dormant June 15**. Decision
for the operator: activate the adjudication loop, or mark `proposed_facts` legacy/secondary. Not an
ontology fix — a strategy call. Surface via `agent_concept_map.py --review`.

---

## 4. Invariants (ontology axioms — enforced or asserted)

| # | Axiom | Enforcement |
|---|---|---|
| A1 | Every fact-bearing row has a non-null `provenance_level`. | 🟢 **DB `NOT NULL`** (deploy_341) |
| A2 | `verified` ⇒ a real `source_doc_id`/`source_id` + excerpt exists. | 🟢 provenance write-gate + `_safe` views + **`ontology_validator` V3 — BLOCK write-trigger `ontvv_v3_matter_facts`** (installed shadow deploy_691; live mode `block`, grounded vs config 2026-07-09 — the `--enforcement` check caught this row still claiming shadow) |
| A3 | No instrument may be executed by an actor outside their lifespan. | 🟢 **trigger** `enforce_actor_lifespan_on_instruments` + `v_actor_lifespan_violations` |
| A4 | A locked/cited row (`verification_lock`, `cited_by_compound_claims`) is immutable until unlocked. | 🟢 lock columns + content_hash |
| A5 | A matter belongs to exactly one client; client data never crosses (`client_code`). | 🟢 **ENFORCED (deploy_716)** — `ontology_validator` V4 is now a `block` write-trigger on `matter_facts`: a fact cannot cite a document owned by a different client (verified live: MWK fact citing Paracale doc 637 rejected). Client resolved via `_client_of()` = matters→clients OR clients directly (handles `case_file≠matter_code`, e.g. the 'MWK-001' client-code tags). Backed by the `matters.client_code→clients` FK. *(A rigid `matter_code→matters` column FK was rejected — `matter_code` legitimately holds matter-or-client codes; a trigger is the correct instrument.)* |
| A6 | Inference substituted for source content is flagged inline, never silent. | 🟡 asserted (MASTER_PLAN §4 principle 9); known past violations |
| A7 | T-30683 (Manguisoc) & T-4494 (Cabanbanan) are SEPARATE matters — never derivatives of T-4497. | 🟢 **asserted** `truth_tests/test_separate_matters.py` (direct-edge + recursive-descendant, deploy gate + nightly) |
| A8 | MMK ≠ MWK — no entity conflates Mary Worrick Keesey with MMK. | 🟢 **asserted** `truth_tests/test_separate_matters.py::no_mmk_mwk_conflation` |
| A9 | A parcel's geometry belongs to exactly one client; a `map_parcels`/`parcels` row may only carry or expose geometry for its own `client_code`. | 🟡 **shadow** — extends A5. `parcels.client_code` added (deploy_733) so both geometry layers carry a declared client; **V6 APPLIED IN SHADOW (`log`) on BOTH arms** — triggers `ontvv_v6_map_parcels` + `ontvv_v6_parcels` live (grounded vs config 2026-07-09; this row previously under-claimed — the `--enforcement` check caught the drift). Flip to `block` after an active-pipeline soak (geometry writes are near-dormant, so 0-findings is trivially clean — see `--shadow-status` caveat) |
| A10 | User/device location is **ephemeral and client-side**; it is NEVER persisted server-side without a consent record. | 🟡 **asserted** — satisfied today (point-in-polygon runs in-browser; no location table exists, by design) |
| A11 | No `MappedProperty` reaches an external or public surface (published status, KML/Earth/Maps link, tile export) except through an audited **publish gate** consistent with `no-external-exposure-until-ready`. | 🟡 **asserted** — no external-publish path built; `ExternalMapReference` held **○ planned** |
| A12 | Every strategy object (`matter_plays`/`matter_objectives`/`matter_elements`/`matter_causes`) belongs to a `matters` row carrying a `client_code` — no orphan or client-less strategy. | 🟡 **asserted** — FK to `matters` present; client resolution rides A5 |
| A13 | A `claims` row is "proven" only when each `required_to_prove` element is backed by a `verified` `matter_facts` row — never from `proposed_facts`. | 🟡 **asserted** — model defined; `claims` underused (6), not yet gate-checked |
| A14 | A `keystones`/`cross_matter_links` cascade edge must name a `proof_doc_id`; cross-matter support is evidence-gated, never assumed. | 🟢 **asserted** — `cross_matter_links` is `proof_doc_id`-gated (§2.5) |
| A15 | `entities.canonical_id` forms a DAG (no merge cycles); a merged entity resolves to exactly one canonical head. | 🟢 **asserted** (deploy_732) — `truth_tests/test_entity_merge_dag.py` (recursive cycle-walk + no-dangling; deploy gate + nightly; negative-tested to bite) |
| A16 | An entity merge joining actors of two different clients requires the cross-client principal allowlist (`case_theories/_clients.py`). | 🟢 **asserted** — `test_cross_client_integrity::no_cross_principal` |
| A17 | `internal_targets` is the single source of truth for internal-vs-outward classification; every comms/outward guard resolves against it (with a hardcoded floor for offline-sovereignty). | 🟢 **asserted** — `outward_guard` + `tg_send` consult it |
| A18 | No `document_matter_links` row may connect a document to a matter of a different client than the document's owner. | 🟡 **asserted** — extends A5 to the link table; detector-only, not yet a block-trigger (**flagged**) |
| A19 | `proposed_facts` is an inbox, never authoritative; only gated `matter_facts` may be quoted in legal output (via `_safe` views). | 🟢 **asserted** — `_safe` views read `matter_facts` only; propose→adjudicate loop open (§3) |
| A20 | Every `verified` `matter_facts` row's `excerpt` is a verbatim substring of its cited document. | 🟢 **ENFORCED** — `enforce_provenance_facts` trigger |
| A21 | Every outward action (send/file/publish/invoice) funnels through the `outward_action` chokepoint / `outward_guard`, fail-closed (held for human on any ambiguity). | 🟡 **shadow** — guard wired at the exits; block-mode dormant, exit-criteria pending |
| A22 | A `work_orders` step executes only via a governed path (tier ≤ T2, tagged, non-outward); T3/untagged/outward-verb steps hold for a human. | 🟢 **ENFORCED** — `governance_block()` fail-closed (Phase-1) |
| A23 | `verified_claims` derive only from an adjudicated `claim_truth_verdicts` row citing its negotiation + evidence; a claim is never "verified" by assertion. | 🟡 **asserted** — model defined; layer underused (6 verdicts / 1 verified) |
| A24 | Truth invariants are checked **mechanically** (`truth_tests/` + `ontology_validator`), never by a standing LLM-interrogation harness. | 🟢 **doctrine** — enforced by the `truth_qa` retirement (below); mechanical suite is the deploy gate |
| A25 | A `ChannelUser` resolves to **at most one** `client_code`; the same human across multiple channels resolves to a single client identity, and no channel identity is mapped across two clients. | 🟡 **shadow** — extends A5/A16 to the comms identity layer. **V7 Part 1 APPLIED IN SHADOW (deploy_743, `log` mode):** trigger `ontvv_v7_channel_users` + view `v_ontology_channel_cross` on `channel_users` (declared `mapped_client_code` must resolve via `_client_of()`); 0 live violations on apply. Validity half live; **Part 2 (cross-channel same-human → one client) blocked on the held `channel_users.entity_id` decision.** **Graduation trigger (`ONTOLOGY_ALIGNMENT.md` §9 bar):** ≥7d of REAL `channel_users` churn observed in shadow with 0 findings (churn is low today — a clean vacuum doesn't count) + pre-flight + rolled-back exception test; flip post-Aug-12 + approval |
| A26 | No `ChannelMessage` is delivered to an **external** recipient except through the outward chokepoint (A21) under `no-external-exposure-until-ready`. *Corollary (token-as-switch):* for inline-send channels (WhatsApp/Viber/Messenger) the provider credential IS the external switch, so provisioning it is an outward action requiring sign-off; email alone splits inbound (internal) from send (outward). | 🟡 **asserted / flagged** — email split live (deploy_654); Meta/Viber armed-but-tokenless by design (662/663); S14 + `outbound_blocks` + `outward_guard` partially enforce; block-mode dormant |
| A27 | Every comms event, inbound or outbound, on any channel normalizes onto the unified bus (`channels`/`channel_messages`), and any message reaching Jonathan passes the S14 human-readability + no-double-tap pacing gate; no adapter may send outside the bus-plus-guard path. When built, the `PlatformCoordinator` is the concrete chokepoint that enforces this. | 🟡 **asserted** — S14 enforced in `tg_send` (14,346 blocks); **bus-normalization floor now mechanical: `truth_tests/test_comms_bus_integrity.py`** (no-orphan · direction-domain · outbound-tracked-status; deploy_746, deploy-gate + nightly, negative-tested to bite); universal bus + a single PlatformCoordinator still ○ planned |
| A28 | The AI presents a **consistent persona** — personality, memory, and relationship context — to a client regardless of channel; a `UnifiedClientPersona` is keyed to `client_code`, never re-initialized per channel. | 🟡 **asserted / flagged** — one shared `systemMessage` gives a uniform personality, but cross-channel memory (`conversation_context`) is 🌱 dormant + not persona-keyed, so continuity is not yet guaranteed |
| A29 | Messages from the same resolved person continue a **single logical thread** (`CrossChannelThread`) spanning channels, not a fresh context per channel; thread continuity resolves through the same `client_code` as A25. | 🟡 **asserted / flagged** — model defined; no cross-channel thread store exists (`channel_messages.reply_to_id` is intra-channel only) — the concept that operationalizes A28 |
| A30 | A channel becomes **externally active** (webhook registered / outbound sending enabled) only with an **auditable activation record** in `channel_audit`; activation is a governed outward action, never silent. | 🟡 **asserted** — `channel_audit` exists (deploy_114); **interim floor now mechanical: `truth_tests/test_comms_activation_audit.py`** (audit-surface-present · held-channels-no-silent-delivery; deploy_746, negative-tested to bite). Systematic activation-logging into `channel_audit` still pending — until then the "arm but hold the external switch" pattern is the discipline the floor guards |
| A31 | Once implemented, the `PlatformCoordinator` is the **single authoritative component** for cross-channel identity resolution (A25/A28/A29) and governed routing + exposure enforcement (A26/A27/A30); no parallel coordinator or bypass path may resolve comms identity or release messages. | 🟡 **partial (deploy_752)** — `scripts/platform_coordinator.py --tick` is live for the INTERNAL half (identity `--resolve` + `--audit` + heartbeat, on `landtek-coordinator.timer`); it is now the concrete resolver/auditor. The OUTWARD half (routing/exposure release) still rides `outward_guard`, so "single authoritative for ALL of A26/A27/A30" is not yet complete — the graduation to 🟢 is when the outward half converges here too. |
| A32 | No value reaches a `ClientFacingView` except through the `ClientProjection` layer (§2.15); a raw internal field, code, docket/`CTN`/ref (`gmail#`/`doc#`), `§` statute cite, `legal_theory` strategy string, operator note, or raw §4B/provenance tag on a client surface is a violation. | 🟡 **asserted + SHADOW GUARD (deploy_756)** — `ClientProjection` built (deploy_744), portal wiring partial (deploy_754). **Mechanical render-audit now LIVE in shadow:** `scripts/ontology_check.py --render-audit` (+ daily sentinel) projects every leak-prone field's raw values and flags any forbidden internal token — matter_code · §/R.A. cite · docket/`CTN`/`SL` · `gmail#`/`doc#` · §4B inference tag · raw provenance enum · control code — surviving projection, writing `holes_findings` `client_render_leak`. Negative-tested to bite (incl. flagship `MWK-CV26360`). **Triaged (deploy_757):** guard now whitelists client-owned government permit IDs (`EXPA`/`APSA`/`MPSA`…) — those 2 were over-filter, not leaks. **2 real projection gaps remain (both `client_ontology`, live-layer to apply):** (a) `next_event` leaves bare agency-docket refs (`ARTA-1210`); (b) `client_doc_name` `_STRIP_CTN_SPACE_RE` only handles `CTN SL …`, so a `CTN CL …` filename leaves the `CTN` label. Minimal fixes proposed to the live layer. **Graduates 🟡→🟢** when `--render-audit` = 0 AND the guard is wired into the deploy gate (`block`). |
| A33 | The `ClientProjection` is **total**: every projected field maps to a defined client-safe output; an unmapped value falls back to a safe generic phrase **and** is logged (`UnmappedValueLog`) — the raw string never reaches the client. | 🟢 **by construction** — every `client_ontology` function returns a mapped/keyword/generic value, never its raw input; each fallback calls `_flag_unmapped()`. |
| A34 | Provenance is projected to **meaning-preserving** plain confidence: raw provenance levels / §4B tags never render to a client; their uncertainty is translated (never dropped, **never upgraded**) into plain language, and a sub-`operator` tier is never presented as settled fact. Client-side companion to A6. | 🟡 **asserted** — `client_provenance`/`client_confidence` built; "never upgraded" rides the source `provenance_level`; the show-as-fact gate (`provenance_is_solid`) is available for the view to honor. |
| A35 | Every `ombudsman_candidates` row belongs to exactly one client (`client_code` NOT NULL, the canonical `clients.client_code`); candidate identity is client-scoped `(client_code, official, violation_code)` — two clients' same official+violation are distinct rows, never a merged UPSERT (§2.16). | 🟡 **shadow** — V5 trigger `ontvv_v5_ombudsman` (deploy_750, `log`) rejects a candidate citing another client's matter (`_client_of` mismatch); UNIQUE re-keyed client-scoped + 40 rows canonicalized to `MWK-001`; negative-tested to bite (cross-client rejected in block, same-client allowed). **Graduation trigger (`ONTOLOGY_ALIGNMENT.md` §9 bar):** the guarded pipeline is DORMANT (VPS `--scan` still pending — 0 findings all-time is a clean vacuum, not evidence); flip `block` only after the first real scan cycle writes candidates through the shadow guard (≥7d of active writes, 0 findings) + pre-flight + rolled-back exception test + approval. |
| A36 | No candidate report (`--reason`/`--board`/`--verify`/`--candidate`/`--playbook`) reads an `ombudsman_candidates` row outside the active `client_code`; a candidate never enters another client's theory of the case. | 🟢 **asserted (code, deploy_750)** — all five reads scoped by `_client_code()`; the mechanical `truth_tests` grep-floor (no unscoped `SELECT * FROM ombudsman_candidates`) is the pending assertion (**flagged**). |
| A37 | The offense engine's seed knowledge — roster (`SEED_ROSTER`), own-side exclusion (`_OURSIDE_RE`), entity-keyed hints — is client-scoped; an official or ally registered under one client never seeds or filters another's hunt. | 🟢 **asserted (code, deploy_750)** — moved into per-client `CASES[...]`; a non-MWK client starts with an empty roster + a generic own-side pattern (no MWK allies leak in). |
| A38 | No inbound message is acted on (replied, written to persona memory, or routed) before its `ChannelUser` is resolved to a `client_code` or explicitly held `unresolved`; an unresolved identity never inherits another client's persona or thread. | 🟡 **asserted (deploy_752)** — sharpens A25 (resolution must PRECEDE action). `platform_coordinator.py --resolve` is the live v1 resolver: it binds only on a unique-contact match and **leaves NULL when unsure** (the explicit `unresolved` hold), so it never guesses a client. The remaining gap is the *ordering* guarantee — that no reply/memory-write fires before resolve runs — which the coordinator's routing half (○ planned) must enforce. |
| A39 | Every outbound `ChannelMessage` to an external recipient carries a recorded exposure decision (the `outward_guard` verdict + its approval/hold reference); an external send whose decision cannot be reconstructed from the record is a violation. | 🟡 **asserted / flagged** — sharpens A26; `outbound_blocks` logs holds and `outward_guard` shadow-logs decisions, but per-message *allow*-decision logging on real external sends is pending (block-mode dormant). |
| A40 | A `channel_audit` activation record is COMPLETE (channel · surface · actor · timestamp · approval ref) and BOTH activation and deactivation are recorded; a channel's external-active state is always reconstructable from `channel_audit` alone. | 🟡 **asserted / flagged** — sharpens A30 (completeness + deactivation symmetry); `truth_tests/test_comms_activation_audit.py` floors the surface, systematic per-activation rows still pending. |
| A41 | A `ConnectedDocument` satisfies ALL 5 ConnectivityGate signals (text · `model_used` · `ocr_quality` · `corpus_backfill_state.embedded` · `document_type`); a half-connected doc is never treated as fully connected or absorbed as evidence (§2.17). | 🟢 **ENFORCED at the chokepoint** (`scripts/supervisor.py::_connect_verify`, fail-closed) **+ 🟢 asserted CORPUS-WIDE** (`truth_tests/test_connected_document_count.py`, deploy gate + nightly): every `model_used`-stamped doc must clear all 5 signals — a **count-independent consistency** check (not a `==86` threshold, which would punish progress), negative-tested to bite (stamp + null `document_type` → RED). The 86/1579 is now a governed, printed number, not an anecdote. Legacy backlog (1493 docs missing ≥1 signal) is tracked, not asserted-red. |
| A42 | `documents.model_used` (the ProvenanceStamp) is **EARNED** — set only from a real `extraction_runs` record, and **NEVER fabricated** to make a document "look connected." Provenance is the one signal a stage cannot simply assert. | 🟢 **asserted (batch) + SHADOW WRITE-GUARD (V8, deploy_769)** — batch: `truth_tests/test_provenance_earned_from_run.py` (deploy+nightly, corpus-wide). Real-time: **`ontvv_v8_provenance_earned` trigger** `BEFORE INSERT OR UPDATE OF model_used ON documents` (config `V8='log'`) logs `ONTOLOGY_PROVENANCE_UNEARNED` to `holes_findings` when a stamp lacks a completed `extraction_runs` row; **shadow — blocks nothing**. Resilient (check errors degrade to allow); verified: 0/86 false-fire, non-blocking self-test PASS, block-mode RAISE proven. **Flip to enforce:** `UPDATE ontology_validator_config SET mode='block' WHERE check_code='V8';` (after clean shadow + approval). |
| A43 | The `ConnectivityGate` is **FAIL-CLOSED** — any missing signal → the document is rejected/held, never partially absorbed; connectivity is **proven, never assumed**. | 🟢 **ENFORCED** — `_connect_verify` returns ok **only** when `issues == []`; a missing text/provenance/quality/embed/type each blocks. Verified: `model_used`=0 corpus-wide once meant 0 docs passed — the gate did not lie. |
| A44 | The A41 `ConnectivityGate` is exactly the **5 mandatory** `DocumentSignal`s; a new/experimental/agentic signal is **additive** (a proposed `document_signals` shadow store) and never enters the gate except by explicit governance promotion (version bump + invariant edit). | 🟡 **asserted-in-principle** — the gate is stable (A41/A43); the extensible `document_signals` table is ○ proposed (ingestion architecture, deploy_785), not built. Protects A41's stability as the corpus grows. §2.17 · `docs/DOCUMENT_MODEL_DRAFT.md` §1. |
| A45 | An **inferred/LLM** `document_type`/`doc_role` is written to a proposals layer (`document_type_proposals` → generalizing to `document_classifications`) with confidence + method + source; only an adjudicated proposal (`status`) sets the cached `documents.document_type`/`doc_role`. **Deterministic-map classification is exempt** — a rule-set type is directly authoritative. | 🟡 **asserted** — `document_type_proposals` (71) is the live proposal layer (Q1 sign-off: A45 governs *inferred* classification only); the generalized `document_classifications` is ○ proposed. Classification analogue of A19. |
| A46 | A `DocumentFiling` copy in a non-corpus location must reconcile to the corpus (checksum); a divergence is a `DocumentInventory` gap, never silent. **A filing write/rename to leo.hayuma.org is an OUTWARD action (client-facing front) held behind the exposure gate (A11/A21); Drive/vault filing is internal.** | 🟡 **asserted** — Drive (`drive_*`) + vault (`vault_*`) columns exist; unified `DocumentInventory`/`FilingRule`/`SyncRule` are ○ proposed (design-only, held). Rides offline-sovereignty + no-external-exposure. |
| A47 | A contextual `DocumentRole` (`document_matter_links.relation_kind`) is per doc-matter link and inherits client separation (A5); intrinsic role (`documents.doc_role`) is global. A role never crosses a document into another client's theory. | 🟡 **asserted** — `relation_kind` + `doc_role` exist; rides A5. Intrinsic-vs-contextual role split endorsed by the ingestion sign-off (deploy_787). |
| A48 | A `Fact`/`Relationship` must cite a **source document with a usable `text` signal** (`text_length ≥ 50`) — knowledge is never extracted from a textless doc; `verified` additionally requires a verbatim `excerpt` (A2/A20). **The full 5-signal `ConnectivityGate` is NOT a fact prerequisite** — connectivity governs a doc's *completeness* (A41), not whether its text yields a cited fact. | 🟢 **asserted** — `truth_tests/test_fact_requires_text.py` (deploy gate + nightly). **Grounded correction (2026-07-08):** the draft "fact ⇐ ConnectedDocument" was FALSIFIED — all 971 fact-source docs have text (0 violations) while only 84 are fully connected; even the "scope to `verified`" fallback was too strong (only 13/484 verified-fact docs are connected). Text is the true signal→semantic dependency. Negative-tested to bite. |
| A49 | An agent (or any projection) contributes to the semantic layer only through the propose→adjudicate→`verified` write-gate; none writes a `verified` `Fact`/`Relationship` directly, nor reads a sub-`verified` tier out as settled fact. | 🟡 **asserted / ○** — the `matter_facts` write-gate (`enforce_provenance_facts`) + `_safe` views enforce it today; the Agent Interaction layer that will inherit it is ○ planned. Extends A19. |
| A50 | Postgres is the **System of Record** (documents · metadata · provenance · entities · matter links); a vector store (`rag_local` today · **Qdrant** as the proposed high-performance projection) is a **REBUILDABLE `RetrievalProjection`, never authoritative.** The A41 `ConnectivityGate` and every provenance/isolation truth read ONLY SoR signals — the `embedded` signal is the Postgres flag `corpus_backfill_state.embedded`, NOT presence in any vector store — so no gate/invariant depends on a projection's liveness. A projection can be dropped and rebuilt from the SoR with zero loss of truth. | 🟡 **asserted-in-principle / ○** — A41 is already store-agnostic (reads the SoR flag, deploy_789); preserves A43 fail-closed + offline-sovereignty. Qdrant is ○ proposed (`RAG_RETRIEVAL_ARCHITECTURE_DIRECTIVE`, pending commit) — this guides the build; reconcile when it lands. |
| A51 | Every point in a `RetrievalProjection` (a Qdrant payload/vector) **traces to a `documents.id`** and carries the `client_code`/`matter_code` **projected FROM the SoR at write time** (never inferred at query time). A payload with no resolving source doc, or whose client scope ≠ its source doc's, is invalid. | 🟡 **asserted / ○** — extends A42 (provenance) + A5 (isolation) to the projection. Enforcement is a **projection-audit** the ingestion/ops side builds — **V8 is Postgres-resident and does NOT reach Qdrant** (explicit boundary). ○ until Qdrant is the live store. |
| A52 | (a) **Retrieval isolation holds in BOTH tiers** — every projection query is client/matter-scoped by a payload filter derived from the SoR; a query for client X never returns client Y's point (the fast path must NOT bypass A5/V4). (b) The projection is **reconcilable to the SoR** — a point whose source doc was deleted, re-tiered, or un-embedded is STALE; the SoR wins on conflict and drift is surfaced, never silently trusted. | 🟡 **asserted / ○** — the highest-risk invariant: a mis-scoped Qdrant filter = **cross-client leak via retrieval, bypassing the Postgres client-isolation block-trigger (A5).** Enforcement = a **cross-tier projection-audit** (shadow), NOT V8. ○ until Qdrant live. |
| A53 | **The stack REASONS with no internet.** The local core — Postgres (SoR) + Ollama inference + embedded `legal_chunks` law + `documents.extracted_text` — is self-contained; **every external service (Gemini · Telegram · Gmail · Drive · GitHub · lawphil) is an EDGE** (delivery / ingestion / binary-view / sync / one-time), **never REQUIRED-TO-REASON.** A document's TEXT must stay local even when its binary is offloaded to Drive (`drive_offload` drops a PDF only when `extracted_text<>''`), and the **applicable LAW a matter relies on must be embedded** (`matter_authorities` → local `full_text`/`legal_chunks`), so reasoning stays offline-complete on both the fact and the law side. | 🟢 **asserted (two-sided, corpus-checked)** — (core capability) `scripts/offline_audit.py` (deploy_562) verifies Postgres+Ollama+law+text are local + classifies every external touchpoint required-vs-edge, VERDICT green; (law completeness) **`truth_tests/test_matter_law_is_embedded.py`** (deploy_791+, deploy-gate + nightly) asserts every matter-relied legal authority is offline-available — **59/59, 0 gap** (LGC RA 7160 · PD 1529 · RA 11032 · RA 3019/6713 · Civil Code · RPC · Constitution), negative-tested to bite; (regression detector) **`scripts/offline_audit.py --check` now runs NIGHTLY** (`landtek-truth-tests-wrapper`, deploy_793) → writes `notifications/pending.txt` on a capability regression (a NEW external became required-to-reason, or the embedded-law/local-text substrate eroded), transient Ollama left ungated; negative-tested (bad DSN → exit 1). Elevated from the `ONTOLOGY_STRUCTURE §5` doctrine + riders A17/A46/A50. **Watch:** docs with no local text — keep extraction ahead of Drive-offload. |
| A54 | **Composition is client-scoped.** A filing and EVERY exhibit/part it binds (`filing_exhibits.filing_doc_id` + each `exhibit_doc_id`, and any `document_parts` parent) resolve to exactly ONE `client_code` — no cross-client exhibit, regardless of the exhibit's source (email attachment · scanned bundle · separate ingest). | 🟢 **ENFORCED (block)** — **V9** (`ontvv_v9_ctd`, BEFORE INSERT/UPDATE on `case_thread_documents`) rejects a cross-client doc→composition bind at the write; flipped log→block 2026-07-09 after a clean pre-flight (0 existing cross-client links, 0 shadow violations) + a rolled-back exception test (the A54 exception fired). **Currently scoped to the live composition table `case_thread_documents`** (211 links); **extends to `filing_exhibits` when that table lands.** Extends A5/A18 — the load-bearing composition invariant (a mis-scoped bind = cross-client leak). |
| A55 | **A `document_part` inherits its parent; it is never separately gated.** A part is a LOGICAL segment (page range · annex · exhibit · email body/attachment) of a physical document; connectivity (A41) and provenance (A42) are measured at the PHYSICAL document — a part inherits the parent's signals and is never separately gated, stamped, or counted. A `Fact` may cite a part for precision, but the citation resolves to the connected parent (A48). | 🟡 **asserted** — clarifies A41/A42; `document_parts` now exists (2026-07-09) and is correctly **NOT gated** (no per-part connectivity/provenance trigger) — the invariant is honored *by absence*, connectivity stays per-physical-doc. No positive artifact to name; stays asserted. |
| A56 | **A finalized filing's exhibit composition is immutable.** Once a filing is finalized (`execution_status` ∈ filed/received), its `filing_exhibits` set + `order_seq` + labels are locked — they are evidence of *what was submitted*; edits are barred unless the filing is explicitly re-opened. Before finalization the composition is freely mutable (drafting). | 🟢 **ENFORCED (block)** — **V10** (`ontvv_v10_ctd`, BEFORE UPDATE/DELETE on `case_thread_documents`) freezes a finalized thread's composition (set/order/labels); flipped log→block 2026-07-09. Inert until a thread/filing is finalized (0 finalized today → no live effect yet, correctly). Extends A4 + received-not-draft; ties to `execution_status`. **Extends to `filing_exhibits` when built.** |
| A57 | **Deadline totality (Principle 2 as an axiom).** The proactive `DeadlineSurface` is (a) **FRESH** — `surfaced_deadlines` written within 2 days (the layer is alive, not silently dead) — and (b) **COMPLETE** — every active matter's structured `next_deadline` ≤90d out appears in the latest surface. A dateless matter is honestly classified (`needs_date`/`watch`/`orphan`) and the gap **reported, never silenced by a fabricated date** (the deploy_642/644 phantom-date trap). | 🟢 **asserted** — `truth_tests/test_deadline_totality.py` (deploy-gate + nightly): surface-fresh + surface-complete raise RED; the dateless classification is a threshold-free report line. Grounded 2026-07-09: surface fresh (11 rows/day), 9 dated ≤90d, 0 dropped; negative-tested to bite. The FIRST affirmative-side invariant — converts the operator's worst recorded failure ("missing every important date", §6A) into a nightly regression detector. |
| A58 | **Deliverable integrity.** A client `WorkProduct` (dossier · bound PDF · memo · portal view) is assembled ONLY through `_safe` views + the `ClientProjection` (inherits A19/A32), carries a machine-listable **`DeliverableManifest`** (every doc/fact it contains, enumerable + cited), and is **immutable once delivered** (the A56 pattern generalized from filings to deliverables; a revision is a NEW version, never an edit of the delivered one). | 🟡 **○ planned** — today `dossier_pipeline.py`/`case_bundle.py` produce files with no DB identity; the WorkProduct store + manifest is the delivery side's to build (ontology fixes identity + invariants, not schema). Graduates when the store lands with the manifest + immutability enforced. |
| A59 | **Governed task completion.** Any multi-step task that mutates governed data runs under a `work_orders` record reaching a **terminal state** — `done`, `held`, or `failed`-with-reason — never silently abandoned; an order stalled past its review horizon surfaces to the operator. A22 guarantees a step is SAFE; A59 guarantees the task FINISHES OR SURFACES. | 🟡 **machinery shipped, live flow pending (deploy_810)** — Phase-2 delivered BOTH halves' mechanics: 3 governed lanes (`ocr_remediation` · `evidence_gap` · `deliverable` produce→verify→certify[T3]) + the stalled-order sentinel (`supervisor_sentinel.py`, nightly: non-terminal past its horizon → `holes_findings` + `pending.txt`, auto-close on terminal). **Stays 🟡 — the trigger is half-met:** D2 active ✓, but 0 live work has run through a lane (`work_orders` = 5 all-terminal). **Graduation trigger (named): the first LIVE order cycle reaching a terminal state through a Phase-2 lane** (e.g. the first bound-PDF via `deliverable`, or the OCR pilot when Gemini quota returns). Desk-verified 2026-07-09 (SUPERVISION_DIRECTIVE §9 record). |
| A60 | **Metered inference is ledgered and budget-gated.** Every credit-consuming LLM call lands in the spend ledger (`llm_calls`/`llm_spend`) and passes `cost_governor.can_afford()` while metered; **unledgered spend is a violation** (Principle 8 as an axiom). Local/owned inference (Ollama) is exempt — it is the free tier by design. | 🟡 **asserted / flagged** — ledger + governor + spend-bridge built; bridge timer DISABLED and the n8n LangChain path is a KNOWN unledgered blind spot (moot while credits are depleted + sim dead, but this row keeps it a tracked violation). **Re-instrument before any credit top-up or sim re-enable** (MASTER_PLAN §3). |
| A61 | **The autonomy ladder is governance.** An agent's privilege tier (read-only → propose → execute-low-risk → …) may only RISE via a metric gate + human sign-off, recorded durably; **no agent raises its own tier**, and a tier grant names its metric evidence. Encodes §6A pillar 4 + the SUPERVISION_DIRECTIVE tier model; the validator mode-flip discipline (shadow `log` → evidence → approved `block`) is the same ladder applied to enforcement itself. | 🟢 **ENFORCED by construction at the registry (deploy_810, desk-verified + graduation recorded 2026-07-09)** — `agent_registry` (99 rows) is the per-agent tier registry; `scripts/fleet_registry.py --sync` assigns PROVISIONAL tiers only (never grants), and a tier RISES only via `--grant`, which refuses without `--evidence` (the metric gate) + `--by` (the human sign-off) and survives re-sync. Verified live: 100% provisional (42 T1 · 10 T2 · 5 T3 · 42 `unset`), 0 granted, 0 self-raised. Both §9-D3 trigger halves met (registry exists + the documented tier-raise procedure references it). The lived flip-discipline (V4–V10, `--stamp` supervised-first, `scripts/leo_proposal_apply.py`) continues unchanged. Watch: 42 `unset` tiers await the supervision desk's classification pass; first recorded grant will be the first positive artifact. Record: SUPERVISION_DIRECTIVE §9. |
| A62 | **The record survives the machine.** The SoR (Postgres) is backed up FRESH (≤26h), the copy leaves the box, and a restore has been DRILLED — every other invariant assumes the SoR exists (A50 "rebuild from SoR", A53 "reason from local Postgres"); A62 governs the assumption. A backup whose pipeline can die silently, or that has never been restored, is a hope, not a backup. | 🟢 **asserted — v2 (deploy_862); REQUIRED LEGS GREEN + DRILLED (re-audited + corrected 2026-07-12).** v2 killed two flaws (the full dump was 2.6GB of NON-record around an ~86MB record; the off-box leg died twice on third-party knobs): nightly **DOMAIN dump** (`--exclude-table-data`; Sunday full local-only 28d) + **the Mac as a second independent off-box node** (`offbox_backup_pull.sh` via launchd: tailnet pull + sha256 + a receipt written only after a verified copy exists — $0, A53-clean). Truth-floored green: fresh (40MB floor) · last-run log clean · off-box receipt <30h + sha matches · **binary gate** (`binary_sources_offbox`, deploy_888: every non-empty VPS document binary carries a Drive ID — a 2026-07-12 re-audit caught 28 local-only binaries incl. the Keesey SPA PDFs; **remediated**) · **restore drill RUN** (faithful, documents 2042=2042). Negative-tested. **HONEST SCOPE (correcting the prior ‘FULLY GREEN’ overstatement, peer-caught):** the invariant — *the record survives the loss of ONE machine* — is met by two independent nodes + a proven restore. The encrypted-Drive **OFFSITE** copy (deploy_889, guards the rarer both-local-nodes-lost case) is **OPTIONAL hardening, NOT a requirement A62 waits on**, and is currently **transport-blocked**: `gdrive-sa` returns `403 storageQuotaExceeded` (service accounts have no Drive quota — re-verified live 2026-07-12) → needs OAuth delegation or a Workspace Shared Drive (**operator decision**). Its truth-test is **report-only until operational, then ratchets** to a hard gate. B2 retired; its stray 1.3GB unencrypted full dump **purged 2026-07-12**. |
| A63 | **A human sign-off is an authenticated identity, never a string.** Every recorded human decision the governance ladder terminates in — A61 `--grant --by`, A22 T3 approvals, validator log→block flips, A11 publish — resolves to a REGISTERED operator principal authenticated on a known surface (ops-auth session · Telegram id `6513067717` · an allowlisted key), not free text. The governance analogue of Leo's Rule S2 (identity integrity). | 🟡 **○ planned** — grounded 2026-07-10: `scripts/fleet_registry.py --grant --by` is free text (`--by jonathan` typeable by any process). Build directive filed: SUPERVISION_DIRECTIVE §9-D4 (operator principal registry + `--by` resolves against it). Graduates when `--by`/T3-approve refuse an unregistered principal. |
| A64 | **Chain of custody: an evidence binary is verifiable against its intake hash.** Provenance (A2/A42) governs where FACTS came from; A64 governs that the DOCUMENT BINARY is bit-identical to what was received — every evidence-tier doc's `content_hash` is recorded at intake and re-verifiable NOW; silent corruption or a swapped file is detected, never trusted. OpenTimestamps anchoring is the later upgrade (§4A pillar 6). | 🟡 **○ planned** — `content_hash` + `forensic_hash.py` (sha256/phash/EXIF) exist; what's missing is the PERIODIC VERIFY SWEEP (re-hash Drive/local binaries vs intake hash → mismatch = a `holes_findings` custody violation). Court-facing (certified-copy comparisons, Aug-12). Graduates when the sweep runs nightly on evidence-tier docs. |
| A65 | **Truth has an arrow of time.** A `verified` fact contradicted by a LATER verified fact is SUPERSEDED or flagged — the two never silently coexist as equally current; `as_of` ordering + the `contradictions` register decide, and every open contradiction has an owner/lane. (The T-52540 face-read-"clean" vs chain-cancelled incident is the class.) | 🟡 **○ planned** — `matter_facts.as_of` exists; `contradictions` (40) is detected-but-out-of-lane (§2.13). Graduates when contradictions carry an owner + a supersession/flag path and a truth_test asserts no un-owned open contradiction older than its horizon. |
| A66 | **External content is DATA, never instructions.** No agent treats inbound external content (email body/attachment · Telegram message · scraped page · OCR'd doc) as an instruction to itself — the injection boundary is stack-wide, not Leo-local (generalizes Rules S1–S4). A tool-call, tier change, config write, or outward action triggered BY ingested content is a violation; the outward chokepoint (A21) + tier ladder (A22/A61) are the named backstop. | 🟡 **asserted (doctrine)** — lived in Leo (S1–S4, sim-proven) but unstated for the wider fleet (ingest/comprehend/comms-spine loops all read external text). Graduates with a mechanical floor: an audit that no ingest-path agent carries write-tools beyond its lane (the `agent_registry` tier column is the substrate). |
| A67 | **Temporal totality — a timeline attaches to every governed object.** Every ACTIVE object with a lifecycle (matter · client_goal · work_order · play/objective · deliverable/filing) carries a FORWARD timeline (deadline · target_date · review horizon · cadence) or an explicit dateless classification; an object with neither is an awareness gap surfaced daily, never invisible. Generalizes A57 (the matters slice) to the whole stack — "timelines and goals attached to everything." | 🟡 **partial** — matters + goals covered (A57 test); **grounded gap 2026-07-10: `work_orders`/`matter_plays`/`matter_objectives` carry NO forward-date column.** Build: `docs/CALENDAR_CADENCE_DIRECTIVE.md` C1. Graduates when each governed kind carries its timeline AND the A57 test generalizes across kinds. |
| A68 | **A date is a fact — derived obligations carry provenance.** Every calendar/deadline entry names its source (cited doc/excerpt · court order · statute period · operator assertion at `operator` tier); agentic derivation (`deadline_extractor`) writes PROPOSALS, and a **historical date in prose is NEVER promoted to a forward deadline** (the deploy_642/644 phantom-date trap — a NULL `next_deadline` is an operator's explicit signal, not a slot to fill). Extends A2/A19 into time. | 🟡 **asserted** — `deadlines.py` source-tags every surfaced row + hard-gates prose harvest to already-dated matters (the 644 root-cause gate, in code); extractor lane exists. Graduates with a truth_test: no forward deadline without a resolvable source. |
| A69 | **The calendar sets the cadence — and the pulse is scoped and gated.** Calendar-driven communications ride the existing gates, never bypass them: a client-facing calendar surface shows ONLY that client's projected events (A5 isolation + A32 projection; token = the switch, A26); outbound rhythm honors S14 pacing (one point, no double-tap) + A21 chokepoint; reminders are lead-time-laddered — the pulse is **gentle by construction**, a flood is a violation. | 🟡 **asserted** — digest leads with due-dates; S14 enforced (14k+ blocks); `mint_calendar_token` exists; client calendar surface not yet wired through `ClientProjection` (C3). Graduates when the client calendar renders via projection AND reminder pacing is mechanically floored. |
| A70 | **Incorporation precedes decision — the metabolism gate (the identity axiom).** LandTek's identity is *cadence and awareness*: no stakeholder-facing decision or deliverable (affidavit · demand · filing · client answer · outward action) emits until a fresh **incorporation pass** has (a) assembled the **client-isolated whole** relevant to that stakeholder's identity/role/purpose/timeline (A5/A35 walls make the "whole" trustworthy — isolation is the *precondition* of incorporation, not its enemy), (b) declared its own **verified/gap state** (the readiness self-knowledge — a matter at 0-verified says so and the decision holds, per the 1891 lesson), and (c) **refused** when the base is too thin. A decision emitted over an un-incorporated or gap-blind base is a violation. This generalizes the affidavit-readiness gate to every governed output — awareness stops being enforced by hand and becomes the system's reflex. | 🟡 **FIRST FLOOR LIVE — the Ombudsman path (deploy_843)** — `scripts/incorporation_gate.py::require_incorporation(matter, stakeholder)` fuses `matter_readiness` (the whole + blockers) + A57/A67 timeline note + A5 client resolution; every verdict RECORDED in `incorporation_verdicts` (READY | HOLD:thin | HOLD:gap-blind, fail-closed). Wired into `ombudsman_hunter.py::cmd_playbook`: every matter a candidate cites is gated; ONE thin/blind matter holds the whole draft. Verified live 2026-07-11: 1891 → READY at 91 verified (at authoring it was 0 — the gate would have held, per the lesson); nonexistent matter → HOLD:gap-blind. Truth-floor `truth_tests/test_incorporation_gate.py` (no-READY-on-thin · fail-closed exercised live · wiring grep-floor), negative-tested. Stays 🟡 until the other deliverable paths (dossier · case_bundle · demand · client answer) call the gate — graduation = every governed deliverable path gated. |
| A71 | **Hydroponic cadence — feed to metabolizable capacity, never to capacity.** The rate of incorporation and of urging-forward is bounded by what the receiver (stakeholder · operator · agent) can absorb into a real next action; over-feeding is noise and a violation as surely as starvation is neglect. Each surfaced item must attach to an actionable step within the receiver's identity/role/timeline (A67), be lead-time-laddered (A69), and honor pacing (S14, one point / no double-tap). The system pushes the *next right increment*, not the whole backlog — gentle, evidentiary, continuous. | 🟡 **asserted (doctrine)** — S14 pacing live (14k+ blocks); A69 floors calendar pulse; digest leads with the next due thing. What's unstated mechanically is the *metabolizability* bound across ALL surfacing (not just calendar): no surface dumps more than N actionable items per receiver per window. Graduates with a per-receiver cadence floor + a truth_test that no digest/surface exceeds the metabolizable-batch ceiling. |
| A72 | **Profit is the shadow of usefulness — the overarching, subtle goal.** LandTek's agents are tasked with making the corpus profitable, but profitability is never pursued as a direct outward act; it is the *emergent result* of being genuinely useful to the operator (and, through the operator, to each stakeholder). No agent optimizes for billing/revenue at the expense of the truth, isolation, or pacing invariants; monetary action stays behind the A21 outward chokepoint (invoice = outward, human-gated), and "usefulness" is measured by decisions the operator could actually act on, not volume produced. The subtle overarching goal governs, but never overrides, the evidentiary and isolation gates above it. | 🟡 **asserted (doctrine / value-axiom)** — `client_dependability` scores ship-readiness (a usefulness proxy); invoicing rides `outward_action` (A21). What's missing is a stated, checked link: a "usefulness" signal (operator-actioned deliverables) that the fleet optimizes, with a guard that no revenue-seeking path bypasses truth/isolation/pacing. Graduates when a usefulness metric is recorded per deliverable and no monetary action exists outside the outward chokepoint. |
| A73 | **A goal names its evidence dependencies.** An active objective that needs specific record inputs (a title's technical description · a deed's terms · a witness statement) declares dependency edges (goal → doc/title); a dependency doc failing its readability/connectivity signals (A41) escalates **at the goal's priority** — never as an anonymous member of the OCR backlog. From the doc-410 post-mortem: the defendant's own title sat unread among 63 dark MWK docs because no row said *"the Balane plot is blocked by doc 410."* Extends the evidence-gap engine (`v_evidence_gaps`, legal elements) to operational goals. | 🟡 **○ planned** — no goal→doc dependency store exists; `v_evidence_gaps` covers legal elements only. Graduates when goals carry dependency edges AND a dark dependency surfaces ranked by its goal (the daily surface), truth-floored. |
| A74 | **A recorded blocker carries its re-check condition.** Any held/blocked finding names WHAT unblocks it (a quota returning · a credential provisioned · an engine becoming available), and is RE-EVALUATED when that condition changes — a dead-end without a re-check trigger is a violation, not a record. From the doc-410 post-mortem: "0 usable of 54 — blocked on Gemini quota" was honestly recorded, then never re-tested when local vision arrived; the stack stayed blind for 3+ weeks while holding the answer. Extends A59 ("finishes or surfaces") to held work. | 🟡 **asserted — first floor LIVE (deploy_870)**: the ingestion-gate class carries a machine-checkable `recheck_condition` on every hold (`ingest_gate` owner-holds · `contradiction_challenge` findings) + `contradiction.close_resolved_challenges()` auto-releases when the condition clears — the A74 pattern proven end-to-end in one finding class. Graduates when generalized to ALL held `holes_findings` (a recheck field + one sweep over every open hold). |
| A75 | **Projection is universal and recipient-shaped — one truth, N projections, never N sources.** No pulse event reaches ANY recipient (human OR agent) except through a `RecipientProfile` fixing four axes: WHO (the A5/A35 isolation wall, enforced in the query) · PURPOSE (the next actionable increment, A71) · FORM (HUMAN: narrative, one point, plain confidence per A34 vs MACHINE: typed, provenance handles INTACT) · DOSE (push ceiling per A71; a PULLED work-slice is complete-in-one-payload — humans fail from too much, agents from too little). `ClientProjection` (A32/A33) is ONE instance of this, not a special case. | 🟡 **THREE PATHS LIVE + truth-floored (deploys 844/858/860, desk-verified)** — design: `docs/RECIPIENT_PROJECTION.md`; registry: `leo_tools/recipient_projection.py` (code-first; reuses `client_ontology` for HUMAN form — `render_human_fact`/`render_human_reply` serve the answer-gate). Wired: (1) `ombudsman_hunter::_fetch_facts` (pull, deploy_844); (2) **verify-worker** via `project_doc_slice` — scope bound INSIDE `verify_loop.doc_worklist` SQL, PULL_COMPLETE, projection error HOLDS the tick (no raw fallback); identical-output 121/121 + 0-leak isolation proven (deploy_858, wo#30); (3) **pulse-orchestrator** (the first PUSH path) via `project_pulse_payload` — per-tick cap READS `dose.push_max_per_window` (the mapping is executable, not documentation), idempotency re-proven 2nd-tick=0 (deploy_858, wo#31). Floor: `truth_tests/test_recipient_projection.py` (per-path wiring grep-floors · profile totality · fail-closed refusal · A5-in-SQL · the report-only UN-WIRED INVENTORY — 36 scripts still read `matter_facts` raw, the shrinking list IS the graduation tracker), negative-tested. Stays 🟡 until the inventory's high-traffic paths graduate; next: dossier/case_bundle family · the tenant/rent pair (Property v2.0). *(Directive drafted this as "A73"; renumbered — A73/A74 taken by deploy_843.)* |
| A76 | **Relationship equilibrium — every relationship is an equation (the reactive half of A70).** Every interaction (comment · reply · decision · attachment) is a GRAPH PERTURBATION, not an isolated event: the system recomputes the affected **ego-network** (never the whole corpus) BEFORE any output surfaces — contradiction checked (surfaced to the A65 register, never silently resolved) · obligation extracted (via the A68 source-cited proposal path) · cascade checked (keystones) · **isolation checked (an edge crossing a client boundary is REFUSED, not weighted — A5 is a hard constraint, not a parameter)**. Accuracy lives INTERNAL (full graph, all edges, all contradictions); gentleness lives EXTERNAL (each recipient's marginal increment via A75 form + A71 dose). Reactivity is per-interaction: coalescing a burst is permitted; surfacing from an un-propagated perturbation is not. The reactive complement of the batch pulse (§2.19) — two paths, one graph. | 🟡 **P2 SHADOW-LIVE (deploy_882, builder-tested; desk structural verification 2026-07-12)** — `scripts/equilibrium_propagate.py` computes on **`v_relationship_graph`** (34k edges — a DERIVED, rebuildable projection over the SoR, A50-consistent; **the P1 ruling, ratified**: the VIEW is the graph carrier, persistence ONLY in the `propagation_log` ledger; `fact_edges` stays drift, `knowledge_graph_triples` untouched — no third store). **Two-plane split is law**: the INTERNAL reasoning plane is gate-free (maximal accuracy — full edges, contradictions, cascades); ONLY the emission plane is clamped (A79) then projected (A75). Per-hop A5 guard = `WHERE client_code = seed_client` on the view — structurally closes the document-bridge; **NULL-client edges are unreachable by construction (3 exist, inert) — these NULL semantics are LOAD-BEARING: any future `OR client_code IS NULL` relaxation reopens the bridge.** Emits nothing in shadow. STAYS 🟡: floors only when the desk runs the graduation negative-tests (planted contradiction caught · cross-client + doc-bridge traversal refused · N-hop increment correctly dosed) against the live engine. |
| A77 | **Ingestion fidelity is a fact-source, not a file-drop.** Every artifact the sink lands must clear TWO gates before its contents can seed the fact graph: (1) RESOLUTION — the artifact is bound to a client_code with confidence ≥ threshold, or it is held (never guessed, A5); an unresolved artifact never forms an edge. (2) MEDIA→FACT — OCR/transcription (local Ollama / Whisper, $0) is logged with a confidence + a raw-vs-structured split, and no structured field (title no., date, party) enters `matter_facts` as VERIFIED without a traceable basis (A2). A misread at ingest is a confident error downstream; the engine propagates it at speed, so ingestion accuracy IS engine accuracy. Extends the comms sink (deploy_847/849) from "land the binary" to "land a trustworthy fact-source." | 🟢 **asserted + FLOORED (deploy_870, desk-verified) + V11 shadow (deploy_871)** — graduated on the executor's close-out: (a) **graded bind** — `comms_artifacts.bind_confidence` + `matched_identity`, threshold 0.80 (`COMMS_BIND_MIN_CONF`): below → HELD with the candidate recorded, never guessed; (b) **writer-lane owner gate** — `scripts/ingest_gate.py::owner_gate` refuses+holds a fact citing an owner-unresolvable doc (A74-style `recheck_condition`), wired into `harvest_facts` + `verify_worker` (>99% of automated writes); (c) raw-text audit trail behind every verified fact (extracted_text + reocr_backup + engine/quality log; verified structured fields must excerpt-ground verbatim). Truth-floor `truth_tests/test_ingestion_fidelity.py`, negative-tested (low-confidence bind held · owner-gate refusal · verify_worker pre-inference hold). **V11** (`ontvv_v11_matter_facts`, config `log`) closes the null-owner bypass AT THE DB (the client-isolation block-trigger passes on a NULL owner) for the remaining writers (decipher_matter/reconciler/n8n/ad-hoc) — shadow-proven (logs on doc 1172, no false fire on owned docs, block-mode RAISE proven, rolled back); flip per ALIGNMENT §9 after soak. HONEST LIMIT: confident-but-wrong OCR above threshold is discoverable (audit trail + reground demotion + contradiction gate), not preventable. |
| A78 | **A verified fact is earned, not promoted — and contradiction is caught at the gate, not after propagation.** `matter_facts` provenance tiers (verified / asserted / inferred) are ENFORCED: a fact becomes VERIFIED only via a traceable verification path (source doc + verify step), never by assertion, inference, or LLM confidence. Any incoming record that CONTRADICTS a VERIFIED fact is refused entry (or held for explicit resolution) at ingest — the equilibrium engine must never propagate a conflict it didn't know about. Facts also do not rot: a verified fact is re-checked when its source is re-ingested or challenged (A74 re-check). This is the substrate every reactive edge computes on; a wrong VERIFIED fact is a wrong equilibrium. | 🟢 **asserted + FLOORED (deploy_870, desk-verified)** — (a) verified-basis was ALREADY DB-enforced twice (`enforce_provenance_facts` + V3 block, BEFORE INSERT OR UPDATE — the T0 audit's finding); (b) **contradiction-at-ingest is now live**: `scripts/contradiction.py` (`conflicts_with_verified`, deterministic, $0) (deterministic, $0) gates `harvest_facts` + `verify_worker` — a conflicting incoming record is HELD upstream of any propagation (`proposed_facts.status='contradiction_hold'`), never silently admitted; (c) **facts don't rot**: reground guard also re-arms the verify cooldown on text change, and verified-fact conflicts raise `contradiction_challenge` findings with machine-checkable `recheck_condition` + an auto-release sweep (44 live challenges opened). Truth-floor `truth_tests/test_verified_fact_integrity.py`, negative-tested (contradicting ingest held · demote-and-re-arm · challenge open/close). CAVEAT: the gate is deliberately conservative — against a multi-dated verified baseline, false-positive HOLDS are possible: visible and recoverable, never silent loss. |
| A79 | **The role clamp at the single gate — emission is role-aware by construction.** Every outbound CANDIDATE (bot reply · pulse increment · engine emission) passes ONE role-aware clamp at the outward gate BEFORE projection: the recipient's role resolves from `comms_role_policy` (client · internal-agent · counsel · **counterparty ⇒ facts/strategy REFUSED** · unknown ⇒ most-restrictive), and the clamp EMITS the `{disclosure_ceiling, projection_profile}` directive that A75 consumes downstream — **the clamp decides, the projection shapes, in that order**; both recorded per A39. Corollary of the two-plane law: the internal reasoning plane is never clamped; the emission plane is never un-clamped. | 🟡 **shadow (deploy_880; MINTED by the desk 2026-07-12** — the clamp was built citing "A79" before this row existed; law now matches build). `comms_role_policy` seeded (6 roles); shadow clamp at `outward_guard` (every outbound path reads the policy once). Graduates to enforce per the ALIGNMENT §9 checklist after the L4 soak on real traffic + desk verification; sends stay off until then (A21/A26 unchanged). |
| A80 | **Output disclosure is classified before it is clamped.** Every candidate output carries a DISCLOSURE TIER — `verified_fact` · `strategy` · `contradiction` · `cross_matter_cascade` · `general` — assigned BEFORE the A79 clamp decides, so the clamp hair-splits on WHAT is being disclosed, not just to whom; the tier is recorded with the emission decision (reconstructable, A39). **Fail-closed: an UNCLASSIFIABLE candidate takes the most-restrictive tier.** A candidate emitted without a recorded tier is a violation. | 🟡 **○ planned (minted 2026-07-12 on the comms desk's request)** — today's classifier is a crude `contains_facts` bool (their honestly-surfaced gap); L4 consumes `classify_output_disclosure()` when built. Graduates when the classifier returns this tier vocabulary, the clamp consumes it, and a truth-floor proves the fail-closed default + tier-recorded-per-emission (negative-tested). |
| A81 | **Property-spine rows carry a declared `client_code`; cross-client asset/title/parcel/project links are refused.** Every governed row on the Property Development + Revenue spine (`property_assets` · `development_projects` · `development_permits` · `asset_titles` · `asset_map_parcels` · `asset_survey_parcels` · `asset_preconditions`) declares a `client_code` (nullable only on `property_assets` for degrade-don't-crash when `_client_of` cannot resolve — isolation stays dark, never invents). A link whose asset client differs from the linked map/survey parcel client, or whose project client differs from its asset, is a violation. Extends A5/A9 into the monetization board. | 🟡 **partial (deploy_911 + V12 shadow deploy_912)** — schema + nullable FK on `property_assets.client_code` live; 83/83 backfilled via `_client_of`. **V12 log-mode** triggers refuse/log cross-client links + orphan polymorphic owners. Graduates to 🟢 when V12 flips `block` after shadow soak (ALIGNMENT §9) + revenue_engine is a ledger writer (second-writer pressure). |
| A82 | **A precondition may only be `ok` with evidence — fail-closed.** `asset_preconditions.status='ok'` requires `source_doc_id` OR non-empty `evidence_ref` OR `provenance_level='operator'`. **Write-path law (Refinement 1):** the engine/reconciler may never self-assign `provenance_level IN ('operator','verified')`; engine `ok` only via doc or **deterministic** `evidence_ref` + `inferred_*`. `operator` is reserved for an operator-authenticated write path. **Asset-owned codes are a derived cache (Refinement 2):** `secure_tenure` / `survey_geometry` / `possession` / `marketable_title` / … are engine-sole-writer projections of title/geometry facts — never hand-set, never operator-`ok`. Operator `ok` is legal only on project-owned sourcing codes (`capital_partner`, `feasibility`, `buyer_price`, `tenant`, …). | 🟢 **DB CHECK + engine + truth-floored (deploy_911)** — constraint `asset_preconditions_ok_requires_evidence` rejects silent `ok`; `test_property_development` proves bite + operator-attested accept + engine rows never `operator`/`verified`. Graduates further when operator-set path is principal-authenticated (A63). |
| A83 | **Geometry for an asset only via link tables — no free-text coordinates on the project.** An asset's spatial claim rides `asset_map_parcels` → `map_parcels` and/or `asset_survey_parcels` → `parcels` (hard FK); optional soft `map_parcels.asset_code`. Projects do not store lat/lng/WKT/GeoJSON columns. Extends A9/A11: plotting stays on the geometry spine; money board *reads* survey readiness via precondition `survey_geometry` (tier-aware: ortho/survey → ok; rough → todo; none → unknown). | 🟢 **asserted + schema-floored (deploy_911)** — no free-coord columns on `development_projects`; link tables only; truth_test `A83_no_free_coords`. |
| A84 | **Project stage `ready` requires all mode preconditions `ok` (asset-owned ∪ project-owned).** Engine may *suggest* ready; operator commits stage (Sprint-1). A project cannot honestly claim shovel-ready while tenure, geometry, permits, capital, or feasibility is non-ok for its mode. | 🟡 **engine + truth_test (deploy_911)** — no live project at `ready` with a non-ok precond; stage owner = engine-suggests. DB trigger optional later. |

**A5 is now enforced (was the load-bearing gap).** It is the extension point for the `ontology_validator`
(see `docs/ontology_validator_spec.md`).

**Retired: the LLM truth_qa harness (deploy_725).** `truth_qa.py`/`truth_qa_loop.py`/`truth_judge.py`
interrogated Leo in natural language via the **Anthropic API** to check the truth invariants — expensive,
died 2026-06-12, gave no signal for 3+ weeks, not a protected sentinel. Its checks were re-homed to the
**mechanical, creditless** layer: A2/A5 by `ontology_validator` V3/V4 write-triggers (block at source),
and A7/A8 + T-4497 ownership + client isolation by `truth_tests/` SQL assertions (deploy gate + nightly).
When the harness was removed, an audit (2026-07-06) found A7/A8 were the one gap the mechanical suite did
NOT yet cover → `test_separate_matters.py` was added to close it (76→79 assertions; negative-tested to
confirm it bites). **Do not resurrect the LLM harness; add cheap SQL assertions instead.**

---

## 5. Client isolation — the one to watch

`clients.client_code` is the intended tenancy key for the whole multi-matter story, but only
`matters`, `map_parcels`, `parcels` (added deploy_733), `assets`, and `conversation_context` carry a real FK to it. The corpus
(`documents`) isolates on the **looser text columns** `case_file` / `matter_code`, which are not
FK-constrained. Until A5 is hardened, **client separation is a discipline, not a guarantee** — the exact
risk flagged in `memory/client-separation-invariants.md`.

---

## 6. Access-model note (prevents a recurring mistake)

LandTek's access model is **not** RBAC. It is a capability-flag list (`authorized_users`:
`can_transcribe`/`can_verify`/`can_admin`) plus token-gating (`client_access_tokens`, `file_access_tokens`).
The `role`/`scope`/`role_scope` tables are **n8n's platform RBAC** and govern the workflow engine, not the
legal data. Do not model LandTek permissions on them. (Full governance map: `ARCHITECTURE.md` §8.)

---

## 7. How to regenerate / re-ground

This file is hand-curated but its **completeness is now machine-verified** — two live guards keep it honest
so it can't silently drift the way §8's first pass did (it missed 100 tables):

- **`ontology_check.py --coverage`** — diffs every *live populated* domain table against the actual text of
  this file (token-precise). "Nothing orphaned" is a CHECK: 201/201 named, exit-1 on any gap. Wired into the
  daily sentinel — a new unnamed table writes a `holes_findings` row (`ontology_coverage_gap`).
- **`agent_concept_map.py`** — the **agent↔concept join**, DERIVED from code+DB: parses each agent script for
  the tables it reads/writes → binds the control plane (`SUPERVISION_DIRECTIVE.md` agents) to this data
  plane. `--orphans` lists tables no python agent touches (n8n/trigger/dormant candidates). Regenerated, so
  the binding can't drift.

## 8. The Oriented Operational Map — every concept its purpose, connection, and state

§2–§6 govern the **evidence-grade core** (facts/titles/entities/docs) — the only tier that is
provenance-gated + validator-enforced. But the ~53 agents run a **10-domain operation**, and ~205 live
+ ~46 dormant domain tables sit *outside* that gated core. **None of them is dead weight** — each was
built for a purpose. This section orients them: purpose · how each connects to the core · and its state.

**Enforcement scope is unchanged.** Everything below is **mapped, not gated** — these are process,
comms, valuation, and governance concepts, not truth-claims, so they are named here for a shared
vocabulary but never provenance-enforced (gating `work_orders` or `channels` would be a category error).

**Orientation-state legend:**
`🟢 ACTIVE` populated + connected + serving · `🌱 DORMANT` purpose-built, awaiting the named activation
flow · `⚪ HEALTHY-EMPTY` an exception log; empty *is* the healthy state · `🔁 SUPERSEDED` purpose now
served by a named successor · `⚙️ INFRA` n8n/platform plumbing, not a domain concept.

### 8.1 Verification & Truth machinery — *is every fact earned?*
| Cluster | Purpose | → core | State |
|---|---|---|---|
| `verification_queue` (52k) · `verify_worker_log` · `field_consensus` · `ocr_quality` · `corpus_backfill_state` | scout→reader pipeline that turns docs into cited facts | feeds `matter_facts` | 🟢 |
| `truth_audit_log` · `truth_negotiations` · `claim_truth_verdicts` · `truth_qa_results` · `verified_claims` | the truth-test / negotiation ledger | gates `matter_facts`/`claims` | 🟢 |
| `holes_runs`/`holes_findings` · `coverage_audit_findings` · `contradictions` · `back_test_runs`/`suite` | diligence self-heal + regression on the truth base | audits the core | 🟢 |

### 8.2 Proposals & Adjudication — *the human-in-loop gate*
`proposed_facts` · `proposed_changes` · `proposed_actions` · `doc_role_proposals` · `doc_classification_proposals` · `entity_merge_proposals` · `review_queue` → propose → gate → `matter_facts`/`entities`/`documents`. **🟢 ACTIVE** (the reconciler flow).

### 8.3 Legal Strategy — *what move, and why*
`matter_plays` · `keystones` · `cross_matter_links` · `matter_state` · `matter_elements` · `matter_objectives` · `matter_authorities` → hang off `matters` + `matter_facts`. **🟢 ACTIVE.**

### 8.4 Forums & Procedure — *the adversarial clocks*
`case_forums` · `arta_cases` · `case_deadlines`/`surfaced_deadlines` · `case_party_filings` · `case_threads`/`case_thread_documents` · `filing_alerts` · `execution_audit` → `matters`/`documents`. **🟢 ACTIVE.**

### 8.5 Offense — *turn defense into pressure on officials*
`ombudsman_candidates` (graft/misconduct leads, ripeness-gated) → `entities` (officials) + `matters`. **🟢 ACTIVE** (filing held T3).

### 8.6 Comms / Omnichannel — *reach, governed by S14*
`channels`/`channel_messages` · `outbound_messages` · `outbound_blocks` (S14, 14k) · `leo_interactions` · `conversations` · `chat_notes` · `correspondence_links`/`events` · `telegram_inbox`/`tg_inquiry_queue` · `gmail_messages` · `client_history` → `documents`/`matters`/`clients`. **🟢 ACTIVE.** `conversation_context`/`conversation_chunks` = **🌱 DORMANT** (Leo long-term memory — activation: wire the comms-memory write). **→ elevated to a Layer III model in §2.14 (Communications & Omnichannel; invariants A25–A27).**

### 8.7 Client & Matter Management — *the tenancy spine*
`clients` · `client_goals`/`needs`/`issues`/`dependability` · `client_access_tokens` · `authorized_users` → the `client_code` isolation key (A5, now enforced). **🟢 ACTIVE.** `contact_roles` = **🌱 DORMANT** (party-role graph).

### 8.8 Revenue / Valuation / Portfolio + Property Development — **spine LIVE (deploy_911); valuation deep still dormant**
| Cluster | Purpose | State |
|---|---|---|
| `property_assets` (hub; `origin` = title stubs vs seed/operator curated) · `asset_titles` · `asset_map_parcels` · `asset_survey_parcels` | land/asset register + multi-title/multi-lot links | 🟢 **ACTIVE (deploy_911)** — 83 assets (77 title stubs + 6 curated); A81 client_code |
| `development_projects` · `development_permits` · `asset_preconditions` · `v_development_board` · `v_asset_inventory` | deal tracks + **all-mode** precondition ledger (sale/lease/develop/mineral) + boards | 🟢 **ACTIVE (deploy_911)** — engine `scripts/development_engine.py`; first project `DEV-PAR-GOLDEN-SAND` |
| `assets` · `asset_valuations` · `asset_risks` | older register / risk tables | 🟢 (partial; do not dual-write — `property_assets` is the money-board hub) |
| `transactions` · `accounts` · `monthly_overhead` · `llm_calls` · `inference_audit` · `llm_spend` · `leo_operational_costs` | the cost/finance ledger | 🟢 |
| `market_observations` · `dominion_value_estimates` · `valuation_change_events` · `value_extraction_events` · `asset_development_plans` · `legal_outcome_estimates` · `financial_projections` · `legal_cost_actuals` · `risk_change_events` · `priority_signals` · `settlement_valuations`/`settlement_scenarios` | the **valuation/revenue/risk engine** — schema built, FK-wired to `assets`/`matters` | **🌱 DORMANT** (not the precondition spine) |

**Law:** design of record `docs/PROPERTY_DEVELOPMENT_SPINE.md`. Invariants **A81–A84**. Isolation **V12 shadow (deploy_912)**. Next activation: converge `revenue_engine` → ledger writer (all 83 assets, all modes) under V12; then map-link proof on GOLDEN-SAND.

### 8.9 Mapping / Geospatial — *the client can stand inside their boundary*
`map_parcels` (world-placed, seeded) 🟢 · `subdivision_plans` (64) 🟢 · `parcels` (relative survey shape) **🌱** · `geometry_priority` (drip queue, 8) **🌱**. `survey_geometry` is a **script** (`scripts/survey_geometry.py`, the courses→polygon math), **not a table**. **Pipeline:** creditless **local-vision OCR** (`reocr_local.py`, Mac Ollama `qwen2.5vl` over Tailscale — the $0 default; `reocr_gemini.py` = token path) cleans garbled title/plan text → `strip_plot_info.py` → `survey_geometry` → `parcels` → tie-point georeference → `map_parcels`. **Full 7-concept model in §2.4.** **Activation frontier:** the `GeometrySource` controlled vocab, and the **○ planned** `ExternalMapReference`/`MapVisibility` surfaces (held behind governance — A10/A11). → `titles`/`matters`/`clients`.

### 8.10 Structured Extraction (DIC) — *typed fields, not just text*
`extraction_contract` (8 contracts incl `court_order`/`spa`/`deed`/`affidavit` — schema 🟢) · `heightened_ocr_queue` (159) 🟢 · `heightened_ocr_results` **🌱 DORMANT**. **Activation:** wire classify→contract routing so contracts run automatically → typed fields on `documents`. *This is the corpus-connection frontier — `model_used` is **EARNED-only**: 86/1579 stamped from `extraction_runs` as of 2026-07-06 (0/388 Paracale); never fabricated. See the connectivity 5-signal contract (○ to be modeled §2.17).*

### 8.11 Governance / Supervision / QA — *the pillars (now registered in their own ontology)*
`ontology_validator_config` · `v_evidence_gaps` · `v_ontology_client_cross` · `holes_findings` · `work_orders`(+`target_ref`) · `internal_targets` · `outward_guard_config` → they govern the core. **🟢 ACTIVE** (outward-guard in 🌱 shadow). `sim_leak_incidents` · `cross_client_flags` · `audit_rejected_messages` · `real_traffic_violations` = **⚪ HEALTHY-EMPTY** (no incidents = the good state).

### 8.12 Superseded / drift (oriented, not deleted — carry the lineage)
`document_entities`→`doc_entities` · `finance_transactions`→`transactions` · `audit_log`/`audit_events`→`truth_audit_log` · `chain_of_title`→`title_chain` (§3) · `cases`→`matters` (§3) · `fact_edges` = 🌱 aspirational KG-edge layer (activation: fact-graph build).

### 8.13 Infra (⚙️ excluded — not domain concepts)
n8n/platform: `workflow_*` · `execution_*` · `chat_hub_*` · `instance_ai_*` · `oauth_*` · `credential*`/`token_*` · `role`/`scope`/`user` · `folder`/`project`/`variables` · `data_table*`.

### 8.14 Autonomous-stack health & self-heal — *where the ~38 report-health agents write*
`system_heartbeat` (16k — the fleet's pulse) · `sentinel_alerts` · `cron_health_state` · `system_analyzer_findings` · `agent_audit` · `escalations` · `escalations_log` · `bottlenecks` · `service_recoveries` · `token_health` · `awareness_log` · `comms_health_alert_state` · `cooldown_log` · `phase_log` · `sim_monitor_state`. **🟢 ACTIVE** — this is the data footprint of the T0/T1 report-health tier in `SUPERVISION_DIRECTIVE.md` §1.

### 8.15 Simulator / Smartness-loop QA — *the adversarial self-improvement subsystem*
`leo_qa_runs` (490k) · `leo_qa_sim_payloads` · `leo_qa_violations` · `leo_qa_probes` · `leo_workflow_snapshots` · `leo_improvement_proposals` · `simulator_budget_log` · `simulator_session_results` · `simulator_sessions` · `back_test_suite`. **🟢 ACTIVE** (its own CLAUDE.md section). Governs Leo's learning loop; not evidence — mapped, not gated.

### 8.16 Scheduling / assistant / deadlines / actions
`calendar_events` · `deadline_alerts` · `calendar_briefs_sent` · `calendar_sync_map` · `email_briefs_sent` · `action_items` · `pending_questions` · `pending_inquiries`. **🟢 ACTIVE** — the agentic-calendar + operator-nudge layer → `matters`/`case_deadlines`.

### 8.17 Strategy-prep & adversary modeling
`planned_moves` · `opposing_responses` · `stage_intake_template` · `stage_intake_response` · `prep_requirements`. **🟢/🌱** — scenario-tree + intake scaffolds → `matters`/`matter_plays`.

### 8.18 Operational logs, dedup, config & credentials (the minor tail — mapped, low-stakes)
- **Verify/triage/re-OCR pipeline state:** `matter_relevance` · `doc_relevance_triage` · `doc_triage_pushed` · `fact_encoding_log` · `re_ocr_results` · `reocr_log` · `reocr_backup` · `ocr_browser_log` · `llm_extracted_lineage` · `doc_link_candidates`.
- **Entity-graph / resolution:** `entity_resolution_log` · `entity_types` (with the dormant `entity_relationships`/`entity_aliases`, §8.12).
- **Comms extra:** `gmail_messages_archived` · `correspondence_events` · `email_sender_disposition` · `channel_users`.
- **Forums / obligations:** `agency_mandates` · `jurisprudence_wishlist` · `landtek_obligations` · `landtek_duties` · `firm_goals`.
- **Client extra:** `client_dependability` · `client_issues` · `client_needs` · `associates` · `assessments`.
- **Dedup / ops / config:** `deploy_log` · `unauth_attempts` · `vault_sections` · `drive_duplicates` · `docs_dupes` · `event_kind_taxonomy` · `event_kind_canonical_def` · `constitution_regen_log` · `forensic_findings` · `extraction_budget` · `landtek_config` · `gemini_key_state` · `tg_update_cursor` · `gmail_oauth_tokens`.

### 8.19 Script triage disposition — *the removal bar (systematic pass, deploy_727)*
`agent_concept_map.py --triage` buckets the ~500 DB-touching scripts. A full pass (2026-07-06) applied the
truth_qa methodology to every DEAD-PRODUCER / overlap / expensive-LLM candidate. **Outcome: the truth_qa
harness was the one genuine nuke; nothing else cleared the bar.** The bar for REMOVAL is all of:
*expensive OR truly dead (crashed/stale) · AND not a protected sentinel/meta/ingest/core · AND not
intentionally-dormant (documented here) · AND not consumed by any path (python, SQL view, web route, n8n).*
- **Tool sharpened, not scripts cut:** `--triage`/`--review` now detect **SQL-view consumers**
  (`view_consumed_tables()`), so tables fed to a view no longer false-flag as dead
  (`map_parcels`→`map_parcels_client`, `opposing_responses`→`v_planned_moves_with_predictions`). DEAD-PRODUCER 16→13.
- **The remaining 13 are retained by disposition, not neglect:** omnichannel bridges (`channel_*`, §8.6 —
  provisioning-gated dormant) · `ombudsman_hunter` (§8.5 offense, filing human-gated) · `client_access`/
  `file_access` (portal token issue+validate — consumed in-module, a read-regex blind spot, not dead) ·
  case-work/strategy subsystems `contradiction`/`forensic_hash`/`cross_matter`/`relevance_triage`/
  `jurisprudence_steward`/`calendar_sync` (out of the ontology/governance/supervision lane — operator's
  activate-or-retire call, collected in the pass's flag list).
- **Cost:** external-LLM spend is **$0.76/30d** (governed); the top active spender `truth_negotiator`
  (holes/ challenger, claude-sonnet-4-6) is **$3.13 since May 16** (~$0.06/wk), active + consumed
  (holes_findings→digest). No second truth_qa-style expensive-dead path exists.

**Orientation summary (VERIFIED by `ontology_check.py --coverage`, not claimed):** every populated domain
table is now named — §2 gated-core (incl. the 2.6 additions), §8.1–8.13 operational clusters, and the
§8.14–8.18 subsystems the first hand-curated pass missed. A whole **dormant business/valuation/geometry/
extraction layer** stands as a roadmap; ~4 healthy-empty sentinels; superseded tables carry successors.
The `--coverage` check is the guard: "nothing orphaned" is now a mechanical invariant, not a claim.

---

## 9. Future Domains — *planned surfaces of the platform (○ placeholders, not yet built)*

The platform is a full Philippine property operation; these domains are **on the roadmap but not yet
modeled**. Each is a growth slot — when it earns a schema and agents, it graduates to a Layer III model
(§2.N) via the template in `docs/ONTOLOGY_STRUCTURE.md §4`, inheriting the system invariants (§5 of that
doc / A5·A21·A24 here). Listing them here is deliberate: it reserves the shape so a future agent slots in
cleanly instead of inventing a parallel structure. **○ = planned; do not build without governance sign-off.**

| Future domain | One-line intent | State | Inherits (system invariants) |
|---|---|---|---|
| **Payments & Billing** | retainer invoicing, receipts, per-matter cost/margin ledger | ○ planned | provenance · client separation · outward chokepoint (invoice = outward) |
| **Tenant / Lease Management** | occupancy, lease terms, rent roll on managed parcels | ○ planned | client separation · provenance |
| **Construction / Project Delivery** | build scopes, milestones, contractor + permit tracking per property | 🟡 **partial — spine live (deploy_911)** · projects/permits/preconditions; full construction delivery still ahead | client separation (A81) · A67 timeline · outward (permits/filings) |
| **Calendar & Deadlines** *(partial today)* | agentic calendar, forum clocks, operator nudges — has tables (§8.16), not yet a Layer III model | 🟡 partial | provenance · governance |
| **Client Portal & Access** *(partial today)* | token-gated client surface (status, map, documents) — `client_access_tokens` live, external switch held; sits on the Communications reach layer (§2.14) | 🟡 partial | client separation · no-external-exposure |
| **Revenue / Valuation / Portfolio** | asset valuation, portfolio ROI — **precondition/money board spine live** (§8.8); deep valuation tables still dormant | 🟡 **partial — spine live (deploy_911)** · valuation engine 🌱 | provenance · client separation (A81–A84) |
| **Agent Fleet Registry** | a first-class model of the ~50 agents themselves (capability, tier, cadence) — today derived, not modeled | ○ planned | governance · component-mapping (Layer V) |

> **How a Future Domain graduates:** (1) it gets a schema → a §3 canonical-table decision; (2) it gets an
> agent → it appears in `agent_concept_map.py`; (3) it earns a §2.N Layer III model + 2–3 invariants; (4)
> version bump + change-log entry; (5) `--coverage` stays green. No domain reaches a client surface without
> the outward chokepoint (A21) and client-separation (A5) wired first.

---

**Change log**
- v0.16 (2026-07-07) — **A27/A30 mechanical floors.** Two comms invariants driven from asserted-flagged to
  asserted-mechanical: `truth_tests/test_comms_bus_integrity.py` (A27 — no orphan `channel_messages`,
  direction ∈ {inbound,outbound}, every outbound row carries a tracked status) + `test_comms_activation_audit.py`
  (A30 — `channel_audit` surface present; no held channel {whatsapp,viber,email} ever silently delivers an
  external message). Suite 84→89, all green on live data + negative-tested to bite (orphan probe, inverted
  direction/status predicates). A27/A30 markers → 🟡 **asserted**. Full A30 (every activation logged to
  `channel_audit`) still pending the activation-logging wiring. Test-only; no schema/enforcement change. (deploy_746)
- v0.15 (2026-07-07) — **A25 enforcement begins — V7 applied in shadow.** First comms invariant driven off
  the page and onto the DB: `migrations/apply_deploy_743_ontology_validator_v7.py` applied live on the VPS in
  `log` mode — trigger `ontvv_v7_channel_users` + detector view `v_ontology_channel_cross` on `channel_users`
  (reuses deploy_691's `ontology_reject` logger + deploy_716's `_client_of()`), self-test confirmed
  non-blocking, **0 live violations**. A25 marker: 🟡 asserted → 🟡 **shadow** (Part 1 = declared-client
  validity). A25 **Part 2** (cross-channel same-human → one client) stays blocked on the held
  `channel_users.entity_id` decision. Flip to `block` post-Aug-12 + approval. No prose change to §2.14.
- v0.14 (2026-07-07) — **§2.15 — Client-Facing Projection layer formalized.** The client dashboard was leaking
  raw internal typed fields (snake_case `current_stage`, "/"-mashed `forum`, `next_event` prose full of
  `gmail#`/`CTN`/`§`/matter-code tokens, raw §4B provenance tags) to paying clients. Modeled the governed
  translation layer that fixes it BY CONSTRUCTION: **`ClientProjection`** (🟢 `leo_tools/client_ontology.py` —
  typed concept → controlled client-safe vocabulary, total with logged safe-generic fallback), **`ClientFacingView`**
  (🟡 the portal, not yet rendering fully through it), **`ClientSafeField`** / **`ClientSafeVocabulary`** /
  **`UnmappedValueLog`**. Three new invariants, monotonic from A31 (nothing renumbered): **A32** (client-safe
  projection is mandatory — no raw internal token on a client surface), **A33** (projection is total + safe-generic
  fallback + logged), **A34** (provenance→meaning-preserving plain confidence; client-side companion to A6;
  sub-`operator` tiers never shown as settled fact). Presentation companion to **`UnifiedClientPersona`** (A28 = the
  VOICE; projection = the safe PRESENTATION of facts). NEXT: wire the portal to render THROUGH the layer, then a
  validator/render-audit check to graduate A32 🟡→🟢, then the visual redesign.
- v0.13 (2026-07-06) — **§2.14 — single-authoritative-coordinator invariant.** Added **A31** (once
  implemented, the `PlatformCoordinator` is the single authoritative component for cross-channel identity
  resolution + governed routing/exposure enforcement; no parallel coordinator or bypass path) — reserving
  the enforcement locus so it can't fragment when it graduates. Minor: `channel_audit` added to the
  ChannelMessage canonical home; PlatformCoordinator row notes A31. **Numbering reconciliation (3rd pass):**
  an incoming proposal used A28–A33; five collided with live invariants. Mapped to the real series: A28→A28
  (persona), A29→A29 (thread), A30→**A25**, A31→**A30**, A32→**A27**, A33→**new A31**. One new invariant;
  nothing renumbered. **Doc-only — no schema, no code, no enforcement change.**
- v0.12 (2026-07-06) — **§2.14 hardened — channel-activation audit + governance prose.** Added **A30**
  (a channel goes externally active only with an auditable activation record in `channel_audit`; activation
  is a governed outward action, never silent) — the one genuinely-new axiom in a stronger incoming proposal.
  Enriched the §2.14 definition (consistent persona/memory; *audited* exposure gate) and the
  ExternalExposureGate row (`channel_audit` as the activation-audit home). **Numbering reconciliation (again):**
  the incoming proposal used A28–A32; three collided with just-committed invariants. Mapped to the real
  monotonic series: proposed A28 → existing **A28** (persona), A29 → existing **A29** (thread), A30
  (ChannelUser→one client_code) → existing **A25**, A31 (activation audit record) → **new A30**, A32
  (outbound governed routing) → existing **A27**. Net: one new invariant, nothing renumbered.
  **Doc-only — no schema, no code, no enforcement change.**
- v0.11 (2026-07-06) — **§2.14 Communications extended — persona + cross-channel continuity.** Added two
  concepts to the §2.14 table: **UnifiedClientPersona** (🟡 — the AI's persistent identity/tone/memory/
  relationship state per client, the *same* persona on every channel; relationship data lives in
  `client_history`/`chat_notes`/`leo_interactions` but cross-channel memory `conversation_context` is 🌱
  dormant + not persona-keyed) and **CrossChannelThread** (○ planned — one logical conversation spanning
  channels; `channel_messages.reply_to_id` is intra-channel only). Two new invariants: **A28** (consistent
  persona across channels) and **A29** (single logical thread across channels). Component line + a persona
  guardrail note added; `PlatformCoordinator` named as the concrete future enforcement point for A26/A27.
  **Numbering reconciliation:** an incoming proposal used A20–A23 for these, which **collide** with existing
  invariants (A20 verbatim-excerpt · A21 outward-chokepoint · A22 work-order-governed-path · A23
  verified_claims). Per the constitution (one monotonic series, never reused/renumbered), the intent was
  mapped onto the real series: proposed A20 → existing **A25**, proposed A21 → new **A28**, proposed A22 →
  existing **A27** (coordinator = its concrete enforcement), proposed A23 → existing **A26** (token-as-switch
  + `channel_audit` activation audit). **Doc-only — no schema, no code, no enforcement change.**
- v0.42 (2026-07-14) — **Property Development + Revenue spine.** Registered `property_assets` (promoted hub) ·
  `development_projects` · `development_permits` · `asset_preconditions` · `asset_titles` ·
  `asset_map_parcels` · `asset_survey_parcels` · `v_development_board` · `v_asset_inventory`. Minted
  **A81–A84**. V12 owner-existence + cross-client isolation **shadow (log)** deploy_912. Design:
  `docs/PROPERTY_DEVELOPMENT_SPINE.md`. Future Domains Construction + Revenue graduated ○→🟡 partial.
  Schema deploy_911 already live; this version is the ontology/enforcement land.
- v0.10 (2026-07-06) — **Communications & Omnichannel formalized (§2.14).** Elevated the terse §2.7 +
  the §8.6 operational cluster to a full Layer III model: five concepts (CommunicationChannel 🟢 ·
  ChannelUser 🟡 · ChannelMessage 🟢 · **PlatformCoordinator ○ planned** · ExternalExposureGate 🟡),
  state-marked and mapped to the live bus (`channels`/`channel_messages`/`channel_users`/`outbound_blocks`)
  + adapters/bridges (deploys 114·654·662·663). Added three honestly-🟡-asserted invariants: **A25**
  (a `ChannelUser` resolves to ≤1 `client_code` — extends the A5 firewall to comms; resolver not built —
  **flagged, the highest-value gap**), **A26** (outbound comms exposure-gated; *token-as-switch* for
  inline-send channels, email alone splits inbound/send), **A27** (one bus, one S14 guard). §8.6 pointer +
  §9 Client-Portal cross-ref added. **Doc-only — no schema, no code, no enforcement change.** No new table
  names introduced (all already named), so `ontology_check.py --coverage` cannot regress — re-run on the
  VPS as the mechanical confirmation, and re-ground the comms rowcounts there before trusting them.
- v0.9 (2026-07-06) — **Ontology framework + Future Domains.** Added §9 **Future Domains** registry
  (Payments, Tenant/Lease, Construction, Calendar, Client Portal, Revenue/Valuation, Agent-Fleet — ○/🟡
  growth slots) and `docs/ONTOLOGY_STRUCTURE.md` (the five logical layers · state-marker vocabulary ·
  new-domain copy-paste template · system-invariant set · versioning + re-grounding maintenance protocol).
  Drove **A15** (entity merge-graph is a DAG) from 🟡 flagged → 🟢 enforced via `test_entity_merge_dag.py`
  (recursive cycle-walk + no-dangling; negative-tested to bite; suite 82→84). Doc + one assertion; no
  schema change. Structure is additive-only — existing section numbers unchanged.
- v0.8 (2026-07-06) — **A9 blocker resolved: `parcels.client_code` added** (deploy_733, operator decision
  7.1). Nullable, FK→`clients`, populated by `_client_of(matter_code)` at write (`parcels.py`); `parcels`
  is empty so backfill is a no-op. Both geometry layers now carry a declared `client_code` → **V6 geometry
  client-isolation authored for BOTH arms** (`docs/ontology_validator_spec.md` §8), still **shadow-DRAFT,
  NOT applied** (enforcement is the separate 7.2 approval; ships `log` first). §5 FK list + A9 updated.
  Schema change is additive + idempotent; no enforcement turned on.
- v0.7 (2026-07-06) — **Geometry/Mapping governance-readiness prep.** Formalized two controlled
  vocabularies in §2.4: **`GeometrySource`** (`local_vision_ocr`/`gemini_ocr`/`operator_trace`/`survey_plan`/
  `satellite_rough`/`tie_point_georef`/`orthomosaic` — separate axis from `accuracy_tier`; no column yet →
  schema change flagged) and **`MapVisibility`** (lifecycle `status` × audience `internal_ops`/`token_client`/
  `google_earth`/`app`/`public` — the last three ○ planned, A11-gated). Staged geometry governance in
  `docs/ontology_validator_spec.md`: **V6 (geometry client isolation, A9) shadow-DRAFT — view+config+trigger,
  NOT applied**, blocked on the `parcels.client_code` decision; plus §9 governance boundaries for the two
  high-risk surfaces (`ExternalMapReference` publishing, stored `UserLocationContext`). **Conservative: no
  schema changes, no new tables, no enforcement applied.**
- v0.6 (2026-07-06) — **Six core domains formalized to §2.4 rigor.** Added §2.8 Case Theory & Legal
  Reasoning, §2.9 Entity Resolution & Canonical KB, §2.10 Client & Matter Separation, §2.11 Fact
  Harvesting & Provenance, §2.12 Supervision & Work Ordering, §2.13 Truth & Reconciliation — each with a
  concept table (state-marked), a component mapping, and 2–3 invariants (A12–A24). All rowcounts re-grounded
  live (matter_facts 8,853→15,554; proposed_facts→213; entity_aliases/entity_relationships confirmed 0).
  Doc-only — no schema/enforcement change; new invariants are honestly marked 🟡 asserted / **flagged**
  where not yet mechanically enforced (A15 merge-cycle check, A18 doc-link block-trigger).
- v0.5 (2026-07-06) — **Mapping/Geospatial domain formalized.** §2.4 expanded from 2 tables to the full
  **7-concept model** (MappedProperty · SurveyGeometry rel/abs · GeometrySource · AreaAssertion · the
  net-new **ExternalMapReference ○** · **MapVisibility 🟡** · **UserLocationContext ⛔-schemaless**). Added
  asserted axioms **A9** (geometry client isolation — extends A5; blocked on `parcels.client_code`),
  **A10** (user location ephemeral/client-side; no server store without consent), **A11** (no external map
  surface without an audited publish gate). §8.9 corrected (`survey_geometry` is a script; creditless
  local-vision OCR is the default path). Mechanical hardening: `parcels` added to `ontology_check.py`
  `PROVENANCE_TABLES`; new **`ACCURACY_VOCAB`** audit for `map_parcels.accuracy_tier` (kept **separate**
  from the 5-value provenance set). **Conservative scope:** no schema changes; no external-publish path or
  location storage built (held ○ planned behind governance); V6 geometry-isolation drafted **shadow-only**,
  not applied. Coverage unaffected (all geometry tables already named).
- v0.4 (2026-07-06) — **coverage audit falsified "nothing orphaned"** (§8 hand-curation silently missed
  100 populated domain tables incl. `system_heartbeat`, `document_matter_links`, `transferees`,
  `fraud_indicators`, and two whole subsystems). Fix: `ontology_check.py --coverage` now diffs live
  populated domain tables vs the actual file (token-precise) → **completeness is a CHECK, not a claim**.
  Filled §2.6 (gated-core omissions) + §8.14 (autonomous health) + §8.15 (simulator QA) + §8.16–8.18
  (scheduling, strategy-prep, ops tail). Re-verified: **201/201 named, 0 gaps.**
- v0.3 (2026-07-06) — added §8 **Oriented Operational Map**: all ~53 agents' concepts across 10 domains
  given purpose · core-connection · orientation-state (Active/Dormant/Healthy-empty/Superseded/Infra).
  Surfaces the dormant valuation/geometry/extraction layer as an activation backlog; registers the
  governance/supervision pillars. Enforcement scope unchanged (evidence core only). Also: V4
  client-isolation flipped to **block** (deploy_716) — A5 enforced.
- v0.2 (2026-07-05) — `ontology_validator` applied in **shadow** (deploy_691): V1 drift-guard (4 tables),
  V3 grounding (matter_facts, 0 false positives), V4 client-isolation detector. V4 caught + re-homed
  **6 Paracale (Allan Inocalla / OCT P-1616) facts mis-filed under MWK-TCT4497** → moved to PAR-TCT1616;
  contamination now 0. Provenance vocab corrected to the real 5-value set. `scripts/ontology_check.py`
  added (whole-corpus linter). Enforcement still `log`-only — flip to `block` after a 72h clean run.
- v0.1 (2026-07-05) — first canonical baseline; grounded on live schema; drift list = 4 tables.
