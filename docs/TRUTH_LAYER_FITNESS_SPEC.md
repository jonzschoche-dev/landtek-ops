# Truth-Layer Fitness Harness — v1 Foundation Spec (+ Improvement Lab appendix)

**Status:** DRAFT for operator review. No code, no migration, no deploy until approved.
**Anchor:** component of MASTER_PLAN **§6B (Live Layer — Corpus Connectivity)**, serving the **§4A** 7-pillar
north star. This is **not** a roadmap; MASTER_PLAN remains the single source of truth for direction/status.
**Reconciliation with MASTER_PLAN §6A ("the simulator stays dead — it was the money pit"):** that dead
thing was an *LLM-interrogation QA harness* that spent metered budget grading prose. This is the opposite: a
**mechanical, $0, grounded instrument** that **reads** the truth layer, **writes no facts**, calls **no model**
on its measurement path, and **auto-deploys nothing**. Different object, different failure surface. It is named
a *harness*, not a *simulator*, on purpose.

---

## PART I — FOUNDATION: Truth-Layer Fitness Harness (TLFH) v1

### 0. Purpose, non-goals, safety boundary

**Purpose.** Continuously measure whether LandTek's information is *available, readable, parsed, grounded,
connected, consistent, current, findable, and safe to use*, expose exactly where it is not, and drive
**measured** remediation — without fabricating facts, auto-verifying facts, or letting a retrieval miss
demote grounded evidence.

**Non-goals.** No synthetic facts. No auto-verification. No LLM-as-judge of open-ended quality. No aggregate
"fitness score" used as a gate. No foundation-model training.

**Safety boundary (enforced by DB privilege, not convention):**

| The harness MAY (automatically) | The harness MAY NOT (ever, automatically) |
|---|---|
| inspect, grade, replay, diagnose, prioritize | declare a fact verified |
| test a candidate remediation in shadow | resolve a contradiction |
| recalculate fitness, record experience | rewrite source evidence / change a legal conclusion |
| emit hypotheses + named remediation targets | modify a governance rule |
|  | publish/send an output |
|  | deploy its own correction |

DB enforcement: the harness runs under a role with **SELECT-only** on all fact tables (`documents`, `titles`,
`title_chain`, `entities`, `matter_facts`, `instruments_on_title`, `transfer_doc_status`, `extraction_chunks`)
and **INSERT-only** on its own ledger (no UPDATE/DELETE → append-only by privilege + a `BEFORE UPDATE/DELETE`
guard trigger, not by code convention).

### 1. Domain-agnostic design (not hardcoded to MWK / titles)

The five dimensions apply to **any truth-layer object**, not just title documents. The unit of measurement is a
`fitness_object = (domain, object_type, object_id)`. Domains (all first-class): **legal, mapping, tenants,
mining, accounting, property, communications, business.**

Each domain supplies a **DomainAdapter** that maps the five dimensions to that domain's real columns/oracles:

```
DomainAdapter(domain):
  enumerate_objects()                 -> [(object_type, object_id, client_code)]
  availability(object)  -> submeasures ; parsing(object) -> submeasures ; ... (all 5 dimensions)
  extraction_contract(object_type)    -> required/conditional fields (or None)
  status()  -> 'instrumented' | 'not_instrumented'   # a domain with no real data returns not_instrumented
```

**v1 ships the `legal/title-document` adapter only** (it has real corpus + a real contract, `tct_v3_canonical`).
The other seven adapters are **defined-interface stubs returning `not_instrumented`** — the framework is
domain-agnostic from day one, but a dimension is only *measured* where real data exists (measuring an empty
`tenants` domain would manufacture false gaps — a violation, inverted). Adding a domain later = writing an
adapter, **no schema or harness redesign** (the "cannot dead-end" guarantee).

### 2. The five composite fitness dimensions

Each dimension is a **named set of sub-measurements kept separately**. An aggregate exists only as a
convenience view; **gates and promotion rules read the sub-measurements, never the aggregate** — so no single
number can hide a critical failure.

| # | Dimension | Sub-measurements (stored separately) | Real oracle (legal adapter) |
|---|---|---|---|
| 1 | **Availability & connectivity** | `bytes_present`, `custody_hash_ok`, `bound_to_client`, `bound_to_object` | `content_hash`, `verification_lock`; A5/A25/A77 owner-gate |
| 2 | **Parsing & structural coverage** | `classified`, `required_fields_extracted_pct`, `conditional_fields_resolved`, `parser_version` | `documents.classification`; `extraction_contract`; `instruments_on_title` |
| 3 | **Grounding & provenance** | `provenance_level`, `source_quote_present`, `quote_supports_value`, `cross_doc_corroboration` | `provenance_level`, `source_quote` (A2/A78) |
| 4 | **Consistency & freshness** | `no_open_contradiction`, `source_current`, `not_superseded`, `recheck_satisfied` | A78 / `holes_findings`; `external_state_last_verified`, A74; `cancelled_by_title` |
| 5 | **Findability & answerability** | `exact_retrieval`, `semantic_recall`, `answerable` | `rag_embed_local.retrieve`; keyword; the eval ledger |

**Hard invariant (dimension 5 ↔ 3):** a `semantic_recall`/`exact_retrieval` miss **records a findability
weakness on its own axis** and **never** changes any dimension-3 grounding value. Evidence coverage and
retrieval recall are independent metrics.

### 3. Data model (ledger tables — additive, append-only)

```
fitness_object            -- the enumerated objects under test
  id, domain, object_type, object_id, client_code, first_seen, last_graded

fitness_measurement       -- APPEND-ONLY; one row per object × dimension × sub-measure × cycle
  id, object_pk, cycle_id, dimension, submeasure, value TEXT, numeric NUMERIC NULL,
  basis JSONB,            -- {evidence_doc_id, source_quote, requirement_id, retrieval_rank, ...}
  weakness_target JSONB NULL,  -- named remediation when the submeasure fails (else NULL = no noise)
  prev_value TEXT NULL,  cycle_at         -- prev_value → regression/stale detection

fitness_cycle             -- per-run rollup + self-reported kill-criteria + fingerprint
  id, domain, cohort, cycle_at, n_objects, per_dimension_json, fingerprint JSONB, kill_criteria JSONB

eval_scenario             -- the grounded evaluation set (see §5)
  id, cohort, domain, object_ref, prompt, expected JSONB, human_review BOOL,
  ruleset_version, created_from, sealed BOOL

eval_result               -- APPEND-ONLY; one row per scenario × assistant-config × run
  id, scenario_id, assistant_config, run_at, per_axis JSONB, passed_mechanical BOOL,
  human_verdict TEXT NULL, fingerprint JSONB

compounding_metric        -- the measured proof of leverage (§7)
  id, metric, value NUMERIC, window, attributed_to, fingerprint JSONB, measured_at
```

`fitness_measurement` and `eval_result` are **INSERT-only** (privilege + guard trigger). `weakness_target`
is `NULL` unless a resolvable, named remediation exists — **untargetable weaknesses are preserved as an
explicit `needs_triage` value, never silently suppressed.**

### 4. The mechanical graders (per dimension, real columns, model-free)

Each sub-measurement is a pure SQL / retrieval / set-membership check. Illustrative (legal adapter):

- `Grounding.provenance_level` = `matter_facts/…provenance_level`; **`grounded` requires `='verified'` +
  non-empty `source_quote`**; `inferred_*`/`asserted` are their own values, never coerced to grounded.
- `Grounding.quote_supports_value` = the parsed value appears **verbatim** in `source_quote` (deterministic).
- `Availability.custody_hash_ok` = recomputed hash matches `content_hash`.
- `Parsing.required_fields_extracted_pct` = extracted fields present / contract-required (honoring
  `doc_requirements_law.required_when` — a **conditional/inapplicable** field is `not_applicable`, **never a gap**).
- `Consistency.no_open_contradiction` = no open A78 / `holes_findings` row references the object.
- `Findability.semantic_recall` = grounding `doc_id ∈ rag_embed_local.retrieve(question, k, ids=<matter set>)`;
  record `retrieval_rank`; miss → `not_indexed`/`missed` (its own axis).

**Chain-provenance ≠ instrument-validity (constitutional correctness rule):** a verified `title_chain` edge
proves the transfer is *recorded*, not that the instrument was *valid / authorized / non-void*. The grader
**never** emits a `valid/non-void` judgment; validity/authority is a **separate, human-reviewed** scenario axis.

### 5. The evaluation corpus — four cohorts + typed expected properties

**Four cohorts (the grounded eval set):**

| Cohort | Role | Anti-abuse property |
|---|---|---|
| `frozen_core` | stable regression baseline; the fixed A/B comparator | never mutated once sealed |
| `sealed_holdout` | measures true generalization | **unavailable to candidate generation** (referee-only) |
| `rolling_real_failures` | grown from real production Leo failures | every real failure → a permanent scenario |
| `adversarial_mutation` | deterministic perturbations of **real** objects (OCR flips a title digit, date swap, wrong-client attach, draft-vs-executed) | tests the **gates**; mutations are **never written to the corpus** |

**Typed expected properties (per scenario `expected` JSONB) — "no fabricated citation" is necessary but not
sufficient:**

```
expected = {
  evidence_docs:  [ids],       # accepted evidence-document set; every cite must fall inside
  exact_values:   {field:val}, # deterministically checkable exact matches (title no., date, amount)
  required_holds: [...],       # MUST hold/refuse (outward-without-approval, unresolved sender, ...)
  prohibited:     [...],       # MUST NOT: cross-client leak, out-of-set cite, ungrounded assertion, internal→outward
  provenance:     'verified',  # grounding basis required
  human_review:   false        # true → open-ended legal/strategic quality; routed to a human, NEVER machine-passed
}
```

### 6. The mechanical scorer battery (reuse the existing gates)

Per scenario, run the assistant, then mechanically check the typed properties:

- `cite_integrity` — every `doc:N ∈ evidence_docs` (no fabricated / out-of-set cite). *Necessary, not sufficient.*
- `value_match` — `exact_values` present and correct.
- `hold_compliance` — `required_holds` occurred (A21/A25).
- `isolation` — `prohibited` absent (A5/A79 — cross-client, internal→outward).
- `grounding` — `provenance` satisfied.
- `coverage` — the grounded answer was surfaced (answerable).
- `cost` / `reliability` — tokens, latency, error/empty.

**The constitutional regression gate is the existing suite:** the **185-test truth suite + the channel-inputs
matrix** run against any assistant version; the eval scenarios add the coverage/quality layer on top. Anything
`human_review=true` goes to a human queue and is **never** counted as a mechanical pass.

### 7. Compounding metrics — measured, never claimed

The word "exponential" is prohibited unless the following are **measured** (not predicted):

- **`docs_improved_per_fix`** — after a parser/workflow correction, re-run over the object class and **count**
  objects whose sub-measurement flipped better. `>1` is the definition of compounding.
- **`attributable_improvement`** — delta on the `sealed_holdout` attributable to a specific promoted candidate
  (fingerprinted, so attribution is real).
- **`recurrence_reduction`** — rate a fixed failure-class reappears; should trend to 0 once a regression
  scenario guards it.
- **`time_to_usable_data`** — ingestion → usable-structured-data latency.

Compounding is *asserted only when* `docs_improved_per_fix > 1` **and** `recurrence_reduction > 0` are on record.

### 8. The continuous loop + write-safety

```
grade all objects → diagnose (weakness-type → remediation-type, a deterministic lookup) →
shadow-remediate → governed promote → recalc fitness → add regression scenario ↺
```

Remediation is matched to the diagnosed weakness (missing binary→retrieve; unreadable→re-OCR;
unstructured→parse; inferred→verification pass; conflict→hold for adjudication; wrong client→ownership
resolution; missing relationship→connect via grounded ref; stale vectors→re-embed; search-miss-despite-fresh
→ retrieval/query fix; missing structure→propose schema/parser; superseded→re-evaluate dependents).

**Write-safety (the leak the shadow work could cause):** a shadow re-OCR/re-parse produces **candidate**
structured values. They land in `proposed_facts` / a shadow candidate lane — **never `matter_facts`** — and
promote only through the **existing A77/A78 governed ingestion path** with human/governed approval. The harness
reuses that gate; it does not build a second one.

### 9. Truth-tests for the harness itself (`test_truth_layer_fitness.py`)

`harness_writes_no_facts` (full cycle → zero fact-table mutations, proven by privilege + row-count) ·
`ledger_append_only_enforced` (UPDATE/DELETE on the ledger raises) · `grounded_matches_provenance_gate`
(`inferred_*` never grades grounded) · `scorer_is_model_free` (mechanical axes run with the model monkeypatched
off) · `findability_never_demotes_grounding` (a planted retrieval miss leaves grounding unchanged) ·
`conditional_rule_not_a_gap` (an inapplicable `required_when` field is `not_applicable`) ·
`chain_provenance_not_validity` (a verified edge with unknown authority never grades valid/non-void) ·
`adversarial_mutation_never_persists` (a mutation cohort run leaves the corpus byte-identical) ·
`cohort_fingerprint_recorded` · `domain_adapter_contract` (an empty domain returns `not_instrumented`, not gaps).

### 10. v1 scope + deploy plan (reversible; NO CODE UNTIL APPROVED)

- **Framework domain-agnostic; instrument the `legal/title-document` adapter first** (real data). Seven adapters
  ship as `not_instrumented` stubs.
- **First fires:** Findability (measured 0/5 recall) and Grounding (measured 0/486 verified on MWK evals).
- **One-shot, manual first** — not a timer, not folded into `meta_pulse`, until calibrated.
- Files: `migrations/<date>_truth_layer_fitness.sql` (additive DDL + append-only trigger + restricted role) ·
  `scripts/truth_layer_fitness.py` (graders + domain adapters) · `scripts/eval_corpus.py` (four cohorts) ·
  `truth_tests/test_truth_layer_fitness.py`.
- **Rollback:** disable the one-shot + revert commit; tables additive. No fact-layer touch = safe.
- Register the new tables in the ontology coverage map (via commit note to the desk; I do not edit ONTOLOGY.md).

---

## PART II — BINDING APPENDIX: The Improvement Lab interface

The Lab is **not** built in v1. This appendix is **binding**: the foundation above is built to these interfaces
so the Lab plugs in **without redesign**.

### A1. `leo_config@N` — what a versioned assistant is

A row in a new `leo_config` table, content-addressed by `config_hash`, versioning **exactly**:

```
leo_config@N = {
  prompt_set,             # system/persona prompts (leo_service.SYSTEM et al.)
  tool_manifest,          # which tools/agents are exposed
  retrieval_params,       # retriever choice + k/width/scoping
  routing,                # agent-coordination / specialist routing
  model_selection,        # which local/remote model per task
  memory_context_assembly,# how recent-turns / grounded-facts / profile are assembled
  recipient_projection    # A75/A79 projection *settings* (not the gates themselves)
}
```

The running assistant reads its config from `leo_config` where `active=true`. Rollback = flip `active` to the
previous row. **(Prerequisite: `leo_service` must become config-driven — today its prompt/retrieval/routing are
hardcoded. This is Lab-phase work, explicitly out of v1.)**

### A2. Constitutional floors — immutable, outside candidate control

These live in code/DB gates **above** `leo_config`; a candidate config **cannot physically alter them**:

- **Truth** — provenance write-gate, no-fabrication, no auto-verify.
- **Privacy / client-isolation** — A5/A25.
- **Outward-action chokepoint** — A21.
- **Role clamp** — A79.

A candidate that requires weakening any floor is **rejected at parse time**, not evaluated.

### A3. How A/B runs consume the foundation ledger

The Lab instantiates `vA = leo_config@active` and `vB = leo_config@candidate`, runs **both** against
`frozen_core` **and** `sealed_holdout`, and writes `eval_result` rows (per-axis vector + fingerprint) for each.
No new scorer is built — it **is** §6's battery.

### A4. Strict non-regression + promotion rule

> Promotion is allowed **iff** (`grounded_coverage↑` **OR** `cost↓` **OR** `latency↓`) **AND** *zero* new
> critical violation on **{truth, privacy, client-isolation, governance, reliability}**. **One new critical
> violation rejects the candidate**, regardless of coverage/efficiency gains.

Sacred axes are hard gates (read from the per-axis sub-measurements, never an aggregate). Efficiency/coverage
are the *only* dimensions whose improvement can justify a promotion.

### A5. Human promotion procedure + rollback + audit

1. Lab emits a **signed A/B report**: per-axis deltas, the fingerprints of both runs, and the exact
   `leo_config` diff (vA→vB).
2. **Jonathan approves** (human-controlled; candidate *generation* may be model-assisted, per CLAUDE.md).
3. Apply = set `vB active`, retain `vA` as the **rollback pointer** (`prev_config_id`).
4. An **audit row** records who/when/both-fingerprints/the diff. Rollback = one flip back to `prev_config_id`.

### A6. Measured outcomes → the experience ledger

Promoted-candidate measured deltas (attributable, fingerprinted) write to an **experience ledger** so future
candidate generation is informed by **what actually worked** — grounded operational experience, never synthetic
facts about the corpus.

### A7. Integration contract with existing proposal machinery — VERIFIED, RE-POINTED

Verified 2026-07-13 against the live DB + scripts:

- **Reused as-is (the ledger contract):** `leo_improvement_proposals` (proposal → snapshot → apply → verify →
  rollback semantics; columns `baseline_pass_rate`/`post_apply_pass_rate`/`snapshot_id`/`reviewed_by`).
- **Must be re-pointed (the runtime):** `leo_proposal_apply.py`/`verify.py` today **patch the n8n AI-Agent
  node's `systemMessage`, restart n8n, and grade via `leo_qa` probes** — the retired metered path. The
  sovereign `leo_service` is **not** config-versioned. Lab-phase work re-points: *apply* from "patch n8n node"
  → "swap `leo_config@N`"; *verify* from "`leo_qa` probe pass-rate" → "the §6 fitness/eval scorer battery."
- The v1 foundation's `eval_result` + fingerprints are built to **be** that new `verify` surface.

### A8. Fingerprint (recorded on every `eval_result` and A/B comparison)

```
fingerprint = { scenario_set_hash, source_snapshot_id, grader_version,
                assistant_config (leo_config_hash), code_git_sha, schema_version, ontology_version }
```

Any comparison is reproducible and attributable; a delta with a changed fingerprint on any axis is flagged as
**not comparable**, not as an improvement.

### A9. Ordering (binding, "cannot dead-end")

`config-versioning (A1)` is the gating prerequisite for the Lab and is **not** in v1. The v1 foundation is
nonetheless Lab-ready because: fingerprints already carry `assistant_config`; the scorer already emits the
per-axis vector the promotion rule (A4) consumes; `eval_result` is already keyed by config. Building the Lab
later adds `leo_config` + the A/B runner + the re-pointed apply/verify — **no change to the foundation schema.**

---

*End of spec. Awaiting operator review. On approval: implement Part I only (foundation), one-shot + manual,
truth-suite green, then return the first real fitness scorecard before any timer or Lab work.*
