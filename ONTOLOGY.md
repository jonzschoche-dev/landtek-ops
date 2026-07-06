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
> **Ontology version: v0.1 (2026-07-05).** First canonical baseline. Semver: patch = new alias/
> deprecation noted; minor = new concept class; major = a canonical table changes.

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

### 2.4 Geometry / cadastral — **two distinct layers, NOT redundant**

| Concept | Canonical table | Rows | Notes |
|---|---|---|---|
| Parcel on the world (absolute WGS84) | 🟢 `map_parcels` | ~1 | GeoJSON-in-JSONB; client-facing map; `accuracy_tier` rough→survey→ortho |
| Survey shape (relative local metres) | 🟢 `parcels` | 0 | metes-and-bounds; `geom_wkt`, `closure_error_m`, `calls` — un-georeferenced |

> ⚠️ **Do not "consolidate" `parcels` into `map_parcels`.** They are different layers: `parcels` is the
> relative survey shape from metes-and-bounds; `map_parcels` is that shape placed on the globe. The bridge
> is a tie-point georeference (`parcels` → `survey`-tier `map_parcels`). This is a known trap.

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
`matters`, `map_parcels`, `assets`, and `conversation_context` carry a real FK to it. The corpus
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
`channels`/`channel_messages` · `outbound_messages` · `outbound_blocks` (S14, 14k) · `leo_interactions` · `conversations` · `chat_notes` · `correspondence_links`/`events` · `telegram_inbox`/`tg_inquiry_queue` · `gmail_messages` · `client_history` → `documents`/`matters`/`clients`. **🟢 ACTIVE.** `conversation_context`/`conversation_chunks` = **🌱 DORMANT** (Leo long-term memory — activation: wire the comms-memory write).

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
`map_parcels` (world-placed, seeded) 🟢 · `subdivision_plans` (64) 🟢 · `parcels` (relative survey shape) **🌱** · `geometry_priority`/`survey_geometry` **🌱**. **Activation:** vision-OCR of survey plans → `survey_geometry` → `parcels` → georeference → `map_parcels`. → `titles`/`matters`/`clients`.

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

**Orientation summary (VERIFIED by `ontology_check.py --coverage`, not claimed):** every populated domain
table is now named — §2 gated-core (incl. the 2.6 additions), §8.1–8.13 operational clusters, and the
§8.14–8.18 subsystems the first hand-curated pass missed. A whole **dormant business/valuation/geometry/
extraction layer** stands as a roadmap; ~4 healthy-empty sentinels; superseded tables carry successors.
The `--coverage` check is the guard: "nothing orphaned" is now a mechanical invariant, not a claim.

---

**Change log**
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
