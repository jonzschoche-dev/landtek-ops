# Ombudsman Case Builder — Ontology Integration & Client-Safety Audit

*Meta-layer report (Ontology / Governance / Supervision). Mechanical signals first; no case work.
Prepared 2026-07-06. Scope: make `ombudsman_hunter` safe, efficient, and first-tier for ALL clients.*

## 0. Reconciliation to LIVE state (2026-07-07) — supersedes the number in §4/§7

A parallel session is **actively authoring `ONTOLOGY.md`** (deploy_735→745, ~8-min cadence, v0.10→v0.15,
"reconciling the A-series"). Re-verified live facts:
- **A-series max is now `A34`** (not A8). My earlier "A9" is WRONG — **A9 is already taken** (parcel
  geometry isolation). The ombudsman invariant's provisional number is **`A35`** — but numbering is
  **owned by the parallel session; treat A35 as a placeholder until authorship quiesces.**
- **Validators live:** V1/V3/V4 = `block`; **V6, V7 = `log` (shadow)**; V5 is unused/skipped. The
  ombudsman validator would be the next family member — **provisionally V8 (or the unused V5) — number
  deferred to the ONTOLOGY session.**
- **`ombudsman_candidates` still has NO `client_code`** (only `matters[]`); UNIQUE still
  `(official, violation_code)` — the leak surface is **unchanged since this report was written.**
- **Precedent pattern confirmed:** client-isolation is a *family* — A5/V4 (`matter_facts`), A9/V6
  (`parcels`/`map_parcels`, `client_code` added deploy_733, V6 shadow-DRAFT), A25/V7 (`channel_users`,
  `mapped_client_code`, V7 shadow deploy_743). **Ombudsman is the next member of this exact family.**
- **The v1.0 renumber is gated SOLELY on ONTOLOGY.md authorship quiescence** (deploy_740). All
  ONTOLOGY.md / A-number / V-number edits below **WAIT for quiescence**; the schema + code + truth-test
  work does **not** touch ONTOLOGY.md and is independently safe.

---

---

## 1. Current State Analysis

The engine was **partially generalized by deploy_684** (`--client` selector, per-client `CASES` theory
with a `GENERIC_CASE` fallback, per-client compiled signals, trigram indexes on the 3 read sources).
So the *analytical read path over `matter_facts`/`documents` is client-scoped*. But three layers are
**not** generalized, and the engine sits **outside** the now-ENFORCING A5 client-isolation governance:

| Dimension | State | Evidence |
|---|---|---|
| `matter_facts` reads | ✅ SCOPED (`matter_code LIKE active_scope()`) | `_fetch_facts`, `_hunt_one`, `_gather_element_evidence` |
| `documents` reads | ◐ SCOPED via `document_matter_links`, **UNSCOPED fallback** | `_scoped_docs` 705–709; `_fetch_docmap` 435 reads all |
| `entities` reads (officer discovery) | 🔴 **UNSCOPED** — returns officers from ALL matters/clients | `discover_officers` 290–297 |
| `ombudsman_candidates` writes | 🔴 **UNSCOPED, un-client-tagged** | `upsert` 632–645; `UNIQUE(official,violation_code)` |
| `ombudsman_candidates` reads | 🔴 **UNSCOPED** — board/reason/verify/candidate/playbook read ALL clients | 853, 1021/1023/1025, 1100, 1113, 1133, 1164 |
| Case theory / roster | 🔴 **MWK-hardcoded** in 3 constructs regardless of `--client` | `CORE_SEVEN` 670, `SEED_ROSTER` 208, `THEORY_HINTS` 987 |
| Governance binding | 🔴 **NONE** — no validator, no truth-test, not in a work-kind | (deploy_659 table is unvalidated) |

**Net:** today it is safe *only because* 40 candidate rows are all MWK. The moment a second client is
hunted, the structure permits **collision on write** and **mixing on read**. This is a *structural*
client-separation risk, not yet an active contamination.

---

## 2. Canonical Concepts (definitions)

- **OmbudsmanMatter** — a client-specific proceeding the hunter builds against public officers.
  Canonically a row-set in `matters` (keyed on `client_code`); the hunter selects it via `--client`
  → `active_scope()` (`matter_code LIKE 'PREFIX%'`). *One client, one isolation boundary (A5).*
- **CaseTheory** — the structured theory of the case (scheme, actors/roles, counts, controlling
  authorities, defenses, clinch-gaps). Currently the per-client `CASES[...]` dict + `cmd_reason`
  output. Must be **100% client-parameterized** — no MWK persons/facts leaking via shared keys.
- **SignalPattern** — configurable, client-aware regex/keyword patterns that surface candidate facts
  (`SIGNAL_PATTERNS` + per-client `insider_names` injected). Client-aware for *names*; **not** for
  the intent-inference narrative (`THEORY_HINTS`).
- **CandidateFinding** — a row in `ombudsman_candidates`: an inference-grade LEAD (`provenance=
  inferred_strong`) whose `signals`/`elements` cite `fact_id`/`doc` handles. **Must be client-tagged**
  and must cite evidence from exactly one client (an A5-class projection of documents).
- **CorpusCombingStrategy** — how the engine fans a query across data sources. Today: `matter_facts`
  (scoped) + `documents.extracted_text` (scoped) + `entities` (unscoped). Should fan, client-scoped,
  across `matter_facts` · `documents` · `gmail_messages` · `doc_entities`/`knowledge_graph_triples` ·
  (for law) `legal_chunks` via `matter_authorities` — trigram- or semantic-indexed.
- **ClientSeparation** — the guarantee that one client's data/theory never enters another's. The
  platform key is **`clients.client_code`** (ONTOLOGY §5); A5 enforces it as a **`block` write-trigger
  on `matter_facts`** (V4, `_client_of()` resolution). The hunter is **outside** this boundary.
- **GovernedSource** — a canonical, provenance-gated table/view the hunter should *consume* rather
  than re-derive: `matter_facts` (A5/V3-gated on write), `matter_authorities`→`legal_chunks`
  (grounded law), and the *pattern* of `v_evidence_gaps` (gaps are a derived view, never asserted).

---

## 3. Mapping — concept → code → canonical table → status

| Concept | Code construct | Canonical table | Governance status |
|---|---|---|---|
| OmbudsmanMatter | `--client`, `set_client`, `active_scope` | `matters` (`client_code`) | ✅ A5-governed at source |
| CaseTheory | `CASES[...]`, `cmd_reason`, `THEORY_HINTS` | (in-code) | 🔴 partly MWK-hardcoded |
| SignalPattern | `SIGNAL_PATTERNS`, `_scan_signals`, `insider_names` | (in-code) | ◐ names client-aware, hints not |
| CandidateFinding | `upsert`, `build_candidates` | `ombudsman_candidates` | 🔴 un-tagged, un-gated |
| CorpusCombingStrategy | `cmd_scan`/`_hunt_one`/`_gather_element_evidence`/`discover_officers` | `matter_facts`, `documents`, `entities` | ◐ 2 of 3 read-scoped; 3 sources unread |
| ClientSeparation | `MATTER_SCOPE`/`active_scope` (reads only) | `clients.client_code` (A5) | 🔴 not applied to candidates/entities |
| GovernedSource | `_fetch_facts` (reads `matter_facts`) | `matter_facts`, `v_evidence_gaps` | ◐ consumes facts; re-derives its own gaps |

`ombudsman_candidates` **is** already in ONTOLOGY.md §2.6 (“Ombudsman lead”) and §8.5 (Offense) — but
registered **without** `client_code` and **without** an isolation invariant.

---

## 4. Client-Separation Assessment (the core risk) + recommended fixes

**Gaps (mechanical):**
1. **No `client_code` on `ombudsman_candidates`; `UNIQUE(official, violation_code)` is not client-scoped.**
   → Two clients with the same official/violation collide and overwrite (`upsert` 632–645).
2. **Every candidate READ is unscoped** — `cmd_board` (1113), `cmd_reason` (853), `cmd_verify` (1021/1023/1025),
   `cmd_candidate` (1133), `cmd_playbook` (1164) — a board/reason for client PAR would render MWK rows.
3. **`discover_officers` reads `entities` unscoped** (290–297) — officers from all clients enter any client's roster.
4. **`THEORY_HINTS` (987), `SEED_ROSTER` (208), `CORE_SEVEN` (670) inject MWK persons/facts regardless of `--client`.**
   Worst case: verifying a *PAR* candidate's `(ra3019_3f, purpose)` feeds Ollama the MWK Teope/Baliza/EO-2 narrative.
5. **No A5 (V4-equivalent) validator on `ombudsman_candidates` writes**, and no truth-test — the offense layer is A5-blind.

**Recommended fixes (deterministic, ordered):**
- **F1 (P0) — tag + scope.** Add `client_code text` to `ombudsman_candidates`; backfill via
  `_client_of(matters[1])`; change `UNIQUE` → `(client_code, official, violation_code)`; add
  `WHERE client_code = %(client)s` to **all** candidate reads/writes; derive the active `client_code`
  from `set_client`. *(Draft migration in §7.)*
- **F2 (P0) — scope discovery.** `discover_officers` must restrict candidate officers to those
  appearing in the client's matters (join `doc_entities`/`matter_facts` filtered to `active_scope()`),
  or at least tag each discovered officer with the matter it was seen in.
- **F3 (P1) — parameterize theory.** Move `CORE_SEVEN`/`SEED_ROSTER`/`THEORY_HINTS` **into `CASES[...]`**
  per client (key `THEORY_HINTS` by `(client, violation, element)`); `GENERIC_CASE` supplies neutral,
  client-agnostic hints. Guard `--hunt seven` behind the active case's own roster (error if unconfigured).
- **F4 (P1) — governance guard.** Add a **V5** validator (block-mode after a shadow window): an
  `ombudsman_candidates` row's `client_code` must equal `_client_of()` of **every** cited fact/doc in
  `signals`/`elements`. Reuse the exact `ontology_reject`/`ontology_validator_config` machinery.
- **F5 (P0) — truth-test.** `truth_tests/test_ombudsman_client_separation.py`: assert no candidate cites
  a handle whose fact/doc resolves to a different `client_code` (deploy-gate + nightly), mirroring
  `test_cross_client_integrity.py`.

---

## 5. Corpus-Combing Recommendations (efficiency + coverage)

Trigram indexing already works (EXPLAIN confirms `idx_mf_statement_trgm` is used; `matter_code` is a
post-filter). The gains are **more sources** and **client-scoped fan-out**, not more LLM:

1. **Comb `gmail_messages` (770 rows) — a rich UNREAD client-comms source.** Officers' admissions,
   agency replies, and delivery proof live in email bodies. Add a client-scoped read (join
   `email_documents`→`documents`→`document_matter_links`) and **trigram-index `gmail_messages.body`**.
2. **Comb the entity graph, not just names.** Use `doc_entities.role`/`context_excerpt` (8,928 rows,
   already trigram-adjacent) and `knowledge_graph_triples` to surface an officer's *acts* and
   *relationships* (e.g. officer→beneficiary), scoped to the client — deeper than a surname regex.
3. **Ground law from `legal_chunks` via `matter_authorities`** (jurisprudence is already linked to
   matters/elements). `cmd_verify`/`cmd_reason` should pull the controlling holding from the linked
   authority instead of relying only on the in-code `THEORY_HINTS`.
4. **One `CorpusCombingStrategy` abstraction** — a single `comb(query, active_scope)` that fans across
   `[matter_facts, documents, gmail_messages, doc_entities]`, all client-scoped, dedup by source
   handle. This replaces the ad-hoc per-command SQL and makes “comb all data” a mechanical guarantee.
5. **Semantic fallback for paraphrase.** For evidence the regex misses, add a `rag_local` (pgvector)
   nearest-neighbor pass scoped to the client's docs — creditless (local embeddings).
6. **Index hygiene:** trigram `gmail_messages.body` and `legal_chunks.text`; a `matter_code` btree on
   `matter_facts` so the scope filter is an index condition, not a post-filter, at multi-client scale.

---

## 6. Governance Recommendations (how it plugs into the ontology)

- **Consume, don't re-derive truth.** The hunter already reads `matter_facts` (A5/V3-gated at write),
  which is correct. Keep the candidate table as a *projection*, never a parallel truth store.
- **Gate the projection.** Bind `ombudsman_candidates` writes to A5 via the V5 validator (F4) using the
  same `_client_of()` + `ontology_validator_config` machinery — no new framework.
- **Gaps as a derived view.** The hunter computes per-count clinch gaps in code. Follow the
  `v_evidence_gaps` doctrine: expose a `v_ombudsman_gaps` view (candidate × thin-element × clinch),
  so gaps are queried, not asserted — and so the table becomes **consumed** (clears the DEAD-PRODUCER
  flag in `agent_concept_map --triage`).
- **Filing stays on the universal chokepoint.** Do **not** add an ombudsman work-kind. Filing routes
  through `supervisor.py` **`outward_action --target ombudsman:officer-X`** (T2 prepare → T3 human
  approve; `governance_block` fail-closes on the outward verb). This is already the intended path.
- **Provenance vocab is correct** — candidates are `inferred_strong` LEADS; keep them out of `_safe`
  views until a human promotes.

---

## 7. Proposed ONTOLOGY.md changes (draft text)

**(a) §2.6 — replace the Ombudsman row to record client-tagging:**
```
| Ombudsman lead | 🟢 `ombudsman_candidates` | ~40 | element/prescription-gated graft LEADS (inferred_strong); **`client_code` (A35 isolation, provisional #)**; `signals`/`elements` cite fact_id/doc handles; filing held (T3) via `outward_action` |
```

**(b) §4 — add an invariant (provisional `A35`; number owned by the ONTOLOGY session) extending client-isolation to the offense layer:**
```
| A35 | An `ombudsman_candidates` row belongs to exactly one client; its cited evidence (`signals`/`elements` handles) may not resolve to another client's fact/doc. Extends A5 to the offense layer. | 🟡 → 🟢 **ontology_validator V8** (shadow→block; `_client_of()` on every handle) + `truth_tests/test_ombudsman_client_separation.py` (deploy-gate + nightly) |
```

**(c) §5 — append to “Client isolation — the one to watch”:**
> A5 is enforced at `matter_facts`. The **offense layer (`ombudsman_candidates`) is the next surface**:
> it must carry `client_code` and be V5-gated so a multi-client hunter cannot collide or mix clients.

**(d) §8.5 (Offense) — note the combing sources + governance:**
> `ombudsman_hunter` combs, client-scoped: `matter_facts` · `documents` · `gmail_messages` ·
> `doc_entities`/`knowledge_graph_triples`; grounds law from `legal_chunks` via `matter_authorities`.
> Writes `ombudsman_candidates` (V5-gated); gaps via `v_ombudsman_gaps`; filing via `outward_action`.

---

## 8. Impact on Existing Tools

- **`agent_concept_map --triage`:** `ombudsman_hunter` is currently RETAINED-BY-DISPOSITION / would
  read as DEAD-PRODUCER (its output table isn't read by any python agent). Adding `v_ombudsman_gaps`
  (a VIEW consumer, detected by `view_consumed_tables`) makes it **ACTIVE** — a real loop closes.
- **`ontology_check.py --coverage`:** unaffected (table already registered); the new `client_code`
  column + A9 row keep coverage green. New reads (`gmail_messages`, `legal_chunks`) appear as new
  consumed edges in the derived map.
- **`truth_tests/`:** +1 test (F5), wired into the deploy gate + nightly, like `test_separate_matters`
  and `test_cross_client_integrity`. Assertion count rises; no existing test changes.
- **`ontology_validator`:** +1 check row (V5) in `ontology_validator_config`, same shadow→block
  lifecycle as V1/V3/V4; zero effect while in `log` mode.
- **`supervisor.py`:** no new kind; the existing `outward_action` chokepoint already covers filing.

---

## 9. Flagged Items (need human decision / protected-layer risk)

- 🚩 **Schema change on a live shared table.** Adding `client_code` + changing the `UNIQUE` constraint
  on `ombudsman_candidates` is safe now (40 MWK rows, backfillable) but touches a governed table —
  apply via a numbered migration with a truncate-or-backfill decision, **with go-ahead**.
- 🚩 **New A5-class validator (V5) on the offense layer.** This extends the client-isolation invariant
  beyond `matter_facts`. Land it in **shadow (`log`) first**, prove 0 false-positives (as V4 did),
  then flip to `block`. Do **not** ship it block-first.
- 🚩 **Behavior change from removing MWK hardcoding.** Parameterizing `THEORY_HINTS`/`SEED_ROSTER`/
  `CORE_SEVEN` changes `--reason`/`--verify` output for MWK (should be identical if MWK config mirrors
  the constants) — verify MWK output is unchanged before/after (a golden-file check).
- 🚩 **Combing `gmail_messages`.** Email is client comms — the new read MUST be client-scoped through
  `document_matter_links`; an unscoped email comb would be a fresh leak vector. Gate it behind the
  same `active_scope()`.
- ⚠️ **`v_evidence_gaps` is NOT directly reusable** by the hunter (it is title-transfer/record-specific).
  Reuse the *pattern* (a derived view), not the view itself — build `v_ombudsman_gaps`.

---

## 10. Recommended Next Steps (prioritized for first-tier, all clients)

| # | Action | Priority | Risk | Deliverable |
|---|---|---|---|---|
| 1 | **F1** — add `client_code` + backfill + client-scope every candidate read/write + fix `UNIQUE` | **P0** | 🚩 schema (go-ahead) | migration + `ombudsman_hunter.py` patch |
| 2 | **F5** — `test_ombudsman_client_separation.py` (deploy-gate + nightly) | **P0** | low | truth-test |
| 3 | **F2** — scope `discover_officers` to the client's matters | **P1** | low | patch |
| 4 | **F3** — move `CORE_SEVEN`/`SEED_ROSTER`/`THEORY_HINTS` into per-client `CASES`; golden-file MWK | **P1** | 🚩 behavior | patch + golden check |
| 5 | **F4** — V5 client-isolation validator on `ombudsman_candidates` (shadow→block) | **P1** | 🚩 protected layer | migration (log-mode) |
| 6 | Comb `gmail_messages` + `doc_entities` (client-scoped) + trigram-index email/body | **P2** | 🚩 leak-scope | patch + index |
| 7 | Ground law from `legal_chunks` via `matter_authorities` in verify/reason | **P2** | low | patch |
| 8 | `v_ombudsman_gaps` derived view → makes the table consumed (clears DEAD-PRODUCER) | **P2** | low | migration |
| 9 | ONTOLOGY.md updates (§2.6, A9, §5, §8.5) | **P3** | none | doc edit |

**Fastest path to first-tier for all clients: #1 + #2 first** (closes the leak with a mechanical guard),
then #3/#4 (kills residual MWK-bleed), then #6/#7 (deeper, client-scoped combing). Everything is
deterministic; the only LLM touch (`--verify`) already exists and becomes *more* correct once the theory
is client-parameterized.
</content>
