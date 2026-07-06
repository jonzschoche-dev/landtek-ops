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
> **Ontology version: v0.15 (2026-07-07).** A25 enforcement begins: **V7 applied in shadow** (deploy_743,
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
| **AreaAssertion** | 🟢 `titles.area_sqm` (gated) · `map_parcels.stated_area_sqm`/`area_sqm` · `parcels.stated_ha`/`area_matches` | active | stated (title) vs computed (courses) vs operator-asserted; each provenance-tagged (T-4497=13.9 ha set via truth-override is the pattern) |
| **ExternalMapReference** | ○ `map_parcels.ortho_tiles_url` only | **NET-NEW** | Google Earth/Maps deep-links, KML/KMZ, embedded/tile URLs. Publishing **exports client geometry to a third party** → outward-guarded; **do not build without sign-off** |
| **MapVisibility** | 🟡 `map_parcels.status` (awaiting_plot/plotted/published) + `client_access_tokens` | partial | who sees it via which surface (internal / token-client / earth / app / public); `published` = the held switch (`no-external-exposure-until-ready`) |
| **UserLocationContext** | ⛔ schema-less by design | invariant | device GPS is ephemeral + client-side (browser point-in-polygon in `leo_tools/mapping.py`); **NEVER persisted server-side** (A10) |

> ⚠️ **Do not "consolidate" `parcels` into `map_parcels`** — relative survey shape vs globe-placed shape;
> the bridge is a tie-point georeference (`parcels` → `survey`-tier `map_parcels`). Known trap.
> ⚠️ **`survey_geometry` is a SCRIPT** (`scripts/survey_geometry.py`, the courses→polygon math), **not a table**.
> ✅ **`parcels` now carries `client_code`** (deploy_733 — nullable, FK→`clients`, populated by `_client_of(matter_code)` at write) — symmetric with `map_parcels`; A9 now has a DECLARED client on **both** geometry layers, so V6 covers both arms uniformly (the blocker is resolved; V6 is authored shadow-DRAFT, still not applied).
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
| Work order (state machine) | 🟢 `work_orders` (4) | 🟡 Phase-1 | JSONB steps + `current_step` + audit; fail-closed `governance_block()` |
| Outward chokepoint | 🟢 `internal_targets` (4) + `outward_shadow_log` (0) | 🟡 shadow | `outward_guard` at the exits; block-mode dormant |
| Gap-finding routine ledger | 🟢 `holes_findings` (22) · `holes_runs` (3,018) | active | self-audit (dispatcher every 15m) |
| Fleet health / pulse | 🟢 `system_heartbeat` (16,377) · `sentinel_alerts` (826) · `agent_audit` (7) | active | T0/T1 report-health tier |
| Comms guardrail log | 🟢 `outbound_blocks` (14,346) | active | S14 — the most-exercised control |
| Derived work source | 🟢 `v_evidence_gaps` (457) | active | the enforced gap-order write-path |

*Components: `supervisor.py` (KINDS registry), `SUPERVISION_DIRECTIVE.md` (tier model), `outward_guard.py`,
`holes/` framework + `dispatcher.py`. **Invariants: A21–A22.***

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
| **PlatformCoordinator** | ○ *(none — planned)* | **NET-NEW** | cross-channel identity resolver + unified router + per-channel health daemon; the **single authoritative** future enforcement point for A26/A27 and comms identity (A31); today scattered across adapters + bridges + timers; **do not build without governance sign-off** |
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

*Components: `leo_tools/channel_adapters.py` (webhooks + `/api/channel/send`) · `tg_send.py` (S14) ·
`{email,whatsapp,viber}_channel_bridge.py` (feed + backlog drain) · `landtek-{email,whatsapp,viber}-bridge.timer`
· `channel_audit` (activation/adapter audit) · `conversation_context`/`conversation_chunks` (persona memory, 🌱) ·
`platform_coordinator.py` (○ future — the enforcement point) · `outward_guard.py` · `_client_of()`.
**Invariants: A25–A31.***

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
| A2 | `verified` ⇒ a real `source_doc_id`/`source_id` + excerpt exists. | 🟢 provenance write-gate + `_safe` views + **`ontology_validator` V3 (shadow, deploy_691)** |
| A3 | No instrument may be executed by an actor outside their lifespan. | 🟢 **trigger** `enforce_actor_lifespan_on_instruments` + `v_actor_lifespan_violations` |
| A4 | A locked/cited row (`verification_lock`, `cited_by_compound_claims`) is immutable until unlocked. | 🟢 lock columns + content_hash |
| A5 | A matter belongs to exactly one client; client data never crosses (`client_code`). | 🟢 **ENFORCED (deploy_716)** — `ontology_validator` V4 is now a `block` write-trigger on `matter_facts`: a fact cannot cite a document owned by a different client (verified live: MWK fact citing Paracale doc 637 rejected). Client resolved via `_client_of()` = matters→clients OR clients directly (handles `case_file≠matter_code`, e.g. the 'MWK-001' client-code tags). Backed by the `matters.client_code→clients` FK. *(A rigid `matter_code→matters` column FK was rejected — `matter_code` legitimately holds matter-or-client codes; a trigger is the correct instrument.)* |
| A6 | Inference substituted for source content is flagged inline, never silent. | 🟡 asserted (MASTER_PLAN §4 principle 9); known past violations |
| A7 | T-30683 (Manguisoc) & T-4494 (Cabanbanan) are SEPARATE matters — never derivatives of T-4497. | 🟢 **asserted** `truth_tests/test_separate_matters.py` (direct-edge + recursive-descendant, deploy gate + nightly) |
| A8 | MMK ≠ MWK — no entity conflates Mary Worrick Keesey with MMK. | 🟢 **asserted** `truth_tests/test_separate_matters.py::no_mmk_mwk_conflation` |
| A9 | A parcel's geometry belongs to exactly one client; a `map_parcels`/`parcels` row may only carry or expose geometry for its own `client_code`. | 🟡 **asserted** — extends A5. **Blocker resolved (deploy_733): `parcels.client_code` added**, so both geometry layers now carry a declared client. V6 geometry-isolation is authored for **both arms** (validator spec §8), **shadow-DRAFT, not yet applied** — ready for a shadow (`log`) run on approval |
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
| A25 | A `ChannelUser` resolves to **at most one** `client_code`; the same human across multiple channels resolves to a single client identity, and no channel identity is mapped across two clients. | 🟡 **shadow** — extends A5/A16 to the comms identity layer. **V7 Part 1 APPLIED IN SHADOW (deploy_743, `log` mode):** trigger `ontvv_v7_channel_users` + view `v_ontology_channel_cross` on `channel_users` (declared `mapped_client_code` must resolve via `_client_of()`); 0 live violations on apply. Validity half live; **Part 2 (cross-channel same-human → one client) blocked on the held `channel_users.entity_id` decision.** Flip to `block` post-Aug-12 + approval |
| A26 | No `ChannelMessage` is delivered to an **external** recipient except through the outward chokepoint (A21) under `no-external-exposure-until-ready`. *Corollary (token-as-switch):* for inline-send channels (WhatsApp/Viber/Messenger) the provider credential IS the external switch, so provisioning it is an outward action requiring sign-off; email alone splits inbound (internal) from send (outward). | 🟡 **asserted / flagged** — email split live (deploy_654); Meta/Viber armed-but-tokenless by design (662/663); S14 + `outbound_blocks` + `outward_guard` partially enforce; block-mode dormant |
| A27 | Every comms event, inbound or outbound, on any channel normalizes onto the unified bus (`channels`/`channel_messages`), and any message reaching Jonathan passes the S14 human-readability + no-double-tap pacing gate; no adapter may send outside the bus-plus-guard path. When built, the `PlatformCoordinator` is the concrete chokepoint that enforces this. | 🟡 **asserted / flagged** — S14 enforced in `tg_send` (14,346 blocks); adapters route through one onboarding path, but universal bus-normalization + a single PlatformCoordinator are ○ planned |
| A28 | The AI presents a **consistent persona** — personality, memory, and relationship context — to a client regardless of channel; a `UnifiedClientPersona` is keyed to `client_code`, never re-initialized per channel. | 🟡 **asserted / flagged** — one shared `systemMessage` gives a uniform personality, but cross-channel memory (`conversation_context`) is 🌱 dormant + not persona-keyed, so continuity is not yet guaranteed |
| A29 | Messages from the same resolved person continue a **single logical thread** (`CrossChannelThread`) spanning channels, not a fresh context per channel; thread continuity resolves through the same `client_code` as A25. | 🟡 **asserted / flagged** — model defined; no cross-channel thread store exists (`channel_messages.reply_to_id` is intra-channel only) — the concept that operationalizes A28 |
| A30 | A channel becomes **externally active** (webhook registered / outbound sending enabled) only with an **auditable activation record** in `channel_audit`; activation is a governed outward action, never silent. | 🟡 **asserted / flagged** — `channel_audit` exists (deploy_114); activations to date (email 654 · whatsapp 662 · viber 663) are recorded in deploys/migrations but not yet systematically written as `channel_audit` activation rows — the "arm but hold the external switch" pattern is the interim discipline |
| A31 | Once implemented, the `PlatformCoordinator` is the **single authoritative component** for cross-channel identity resolution (A25/A28/A29) and governed routing + exposure enforcement (A26/A27/A30); no parallel coordinator or bypass path may resolve comms identity or release messages. | 🟡 **asserted / flagged** — `PlatformCoordinator` is ○ planned; reserves the enforcement locus so it isn't fragmented across half-built coordinators when it graduates (per §9) |
| A32 | No value reaches a `ClientFacingView` except through the `ClientProjection` layer (§2.15); a raw internal field, code, docket/`CTN`/ref (`gmail#`/`doc#`), `§` statute cite, `legal_theory` strategy string, operator note, or raw §4B/provenance tag on a client surface is a violation. | 🟡 **asserted / flagged** — `ClientProjection` (`leo_tools/client_ontology.py`) built this pass; the portal does not yet render fully THROUGH it (wiring is the next step). Enforcement locus = a future `ontology_validator`/render-audit check; graduates 🟡→🟢 once the view renders only `ClientSafeField`s and the check is applied. |
| A33 | The `ClientProjection` is **total**: every projected field maps to a defined client-safe output; an unmapped value falls back to a safe generic phrase **and** is logged (`UnmappedValueLog`) — the raw string never reaches the client. | 🟢 **by construction** — every `client_ontology` function returns a mapped/keyword/generic value, never its raw input; each fallback calls `_flag_unmapped()`. |
| A34 | Provenance is projected to **meaning-preserving** plain confidence: raw provenance levels / §4B tags never render to a client; their uncertainty is translated (never dropped, **never upgraded**) into plain language, and a sub-`operator` tier is never presented as settled fact. Client-side companion to A6. | 🟡 **asserted** — `client_provenance`/`client_confidence` built; "never upgraded" rides the source `provenance_level`; the show-as-fact gate (`provenance_is_solid`) is available for the view to honor. |

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

### 8.8 Revenue / Valuation / Portfolio — **the dormant business layer (the roadmap)**
| Cluster | Purpose | State |
|---|---|---|
| `assets` · `asset_valuations` · `property_assets` · `asset_risks` | the land/asset register + valuations | 🟢 (partial) |
| `transactions` · `accounts` · `monthly_overhead` · `llm_calls` · `inference_audit` · `llm_spend` · `leo_operational_costs` | the cost/finance ledger | 🟢 |
| `market_observations` · `dominion_value_estimates` · `valuation_change_events` · `value_extraction_events` · `asset_development_plans` · `legal_outcome_estimates` · `financial_projections` · `legal_cost_actuals` · `risk_change_events` · `priority_signals` · `settlement_valuations`/`settlement_scenarios` | the **valuation/revenue/risk engine** — schema built, FK-wired to `assets`/`matters` | **🌱 DORMANT** |

**Activation flow:** the `revenue-engineer` + portfolio/valuation domain (parked behind Aug-12 per MASTER_PLAN). This is the operation's *intended* business shape sitting latent — a backlog, not scaffolding.

### 8.9 Mapping / Geospatial — *the client can stand inside their boundary*
`map_parcels` (world-placed, seeded) 🟢 · `subdivision_plans` (64) 🟢 · `parcels` (relative survey shape) **🌱** · `geometry_priority` (drip queue, 8) **🌱**. `survey_geometry` is a **script** (`scripts/survey_geometry.py`, the courses→polygon math), **not a table**. **Pipeline:** creditless **local-vision OCR** (`reocr_local.py`, Mac Ollama `qwen2.5vl` over Tailscale — the $0 default; `reocr_gemini.py` = token path) cleans garbled title/plan text → `strip_plot_info.py` → `survey_geometry` → `parcels` → tie-point georeference → `map_parcels`. **Full 7-concept model in §2.4.** **Activation frontier:** the `GeometrySource` controlled vocab, and the **○ planned** `ExternalMapReference`/`MapVisibility` surfaces (held behind governance — A10/A11). → `titles`/`matters`/`clients`.

### 8.10 Structured Extraction (DIC) — *typed fields, not just text*
`extraction_contract` (8 contracts incl `court_order`/`spa`/`deed`/`affidavit` — schema 🟢) · `heightened_ocr_queue` (159) 🟢 · `heightened_ocr_results` **🌱 DORMANT**. **Activation:** wire classify→contract routing so contracts run automatically → typed fields on `documents`. *This is the corpus-connection frontier (`model_used`=0).*

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
| **Construction / Project Delivery** | build scopes, milestones, contractor + permit tracking per property | ○ planned | client separation · outward (permits/filings) |
| **Calendar & Deadlines** *(partial today)* | agentic calendar, forum clocks, operator nudges — has tables (§8.16), not yet a Layer III model | 🟡 partial | provenance · governance |
| **Client Portal & Access** *(partial today)* | token-gated client surface (status, map, documents) — `client_access_tokens` live, external switch held; sits on the Communications reach layer (§2.14) | 🟡 partial | client separation · no-external-exposure |
| **Revenue / Valuation / Portfolio** | asset valuation, portfolio ROI — dormant business layer (§8.8) | ○ dormant | provenance · client separation |
| **Agent Fleet Registry** | a first-class model of the ~50 agents themselves (capability, tier, cadence) — today derived, not modeled | ○ planned | governance · component-mapping (Layer V) |

> **How a Future Domain graduates:** (1) it gets a schema → a §3 canonical-table decision; (2) it gets an
> agent → it appears in `agent_concept_map.py`; (3) it earns a §2.N Layer III model + 2–3 invariants; (4)
> version bump + change-log entry; (5) `--coverage` stays green. No domain reaches a client surface without
> the outward chokepoint (A21) and client-separation (A5) wired first.

---

**Change log**
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
