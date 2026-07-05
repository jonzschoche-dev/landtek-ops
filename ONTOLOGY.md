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

## 3. Drift / legacy — do **not** write here (consolidation backlog)

| 🔴 Table | Rows | Verdict | Canonical instead |
|---|---|---|---|
| `chain_of_title` | ~174 | **Staging.** Raw per-chunk extraction (`source_chunk_id`→`extraction_chunks`); flat, no locks. | `title_chain` + `titles` |
| `finance_transactions` | 0 | **Schema drift.** Cleaner `client_code`/`matter_code` columns but never populated. | `transactions` (~174, holds the data) — *or* migrate data into `finance_transactions` and retire `transactions`; **pick one, don't keep both** |
| `cases` | ~2 | **Legacy.** Older matter concept keyed on `client_id` (int); superseded. | `matters` (~38, keyed on `client_code`) |
| `fact_edges` | 0 | **Aspirational.** Empty KG-edge table. | leave until §2.5 pipeline needs edges |

> **Reconciliation is a post-Aug-12 chore, not a wartime task.** Listing them here *is* the fix for now:
> it stops the drift from compounding by naming the canonical target. Do not migrate live tables during
> the litigation window.

---

## 4. Invariants (ontology axioms — enforced or asserted)

| # | Axiom | Enforcement |
|---|---|---|
| A1 | Every fact-bearing row has a non-null `provenance_level`. | 🟢 **DB `NOT NULL`** (deploy_341) |
| A2 | `verified` ⇒ a real `source_doc_id`/`source_id` + excerpt exists. | 🟢 provenance write-gate + `_safe` views + **`ontology_validator` V3 (shadow, deploy_691)** |
| A3 | No instrument may be executed by an actor outside their lifespan. | 🟢 **trigger** `enforce_actor_lifespan_on_instruments` + `v_actor_lifespan_violations` |
| A4 | A locked/cited row (`verification_lock`, `cited_by_compound_claims`) is immutable until unlocked. | 🟢 lock columns + content_hash |
| A5 | A matter belongs to exactly one client; client data never crosses (`client_code`). | 🟡 **partial** — FK on `matters`/`map_parcels`/`assets`; corpus isolates on looser `case_file`/`matter_code` text (§5). **Detector live:** `ontology_validator` V4 view `v_ontology_client_cross` (deploy_691) — caught + re-homed 6 Paracale facts mis-filed under MWK on first run. |
| A6 | Inference substituted for source content is flagged inline, never silent. | 🟡 asserted (MASTER_PLAN §4 principle 9); known past violations |

**A5 is the load-bearing gap.** It is the extension point for the `ontology_validator`
(see `docs/ontology_validator_spec.md`).

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

This file is hand-curated but **verified against the live schema**. To re-ground rowcounts and catch new
drift, diff the live table list against §2–§3 (a `scripts/ontology_check.py` generator is the natural next
step — spec'd but not yet built; it belongs to the `ontology_validator` work, not this doc).

**Change log**
- v0.2 (2026-07-05) — `ontology_validator` applied in **shadow** (deploy_691): V1 drift-guard (4 tables),
  V3 grounding (matter_facts, 0 false positives), V4 client-isolation detector. V4 caught + re-homed
  **6 Paracale (Allan Inocalla / OCT P-1616) facts mis-filed under MWK-TCT4497** → moved to PAR-TCT1616;
  contamination now 0. Provenance vocab corrected to the real 5-value set. `scripts/ontology_check.py`
  added (whole-corpus linter). Enforcement still `log`-only — flip to `block` after a 72h clean run.
- v0.1 (2026-07-05) — first canonical baseline; grounded on live schema; drift list = 4 tables.
