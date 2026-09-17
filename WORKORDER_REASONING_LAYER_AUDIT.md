# Work Order — Full-Stack Reasoning-Layer Audit

**For:** a downstream executor (or a small fleet of them — this is phaseable, see §9).
**From:** the ontology/governance desk, 2026-07-19.
**Scope:** EVERY place in the stack where a judgment is made — not the LLM alone. Read-only audit first;
no model flips, no prompt edits, no gate changes until findings are reported and the operator picks.

---

## 0. Why this exists (the seed + the meta-lesson)

A narrow look at ONE reasoning site (the verify path) surfaced three real issues. Treat them as the **seed
pattern to hunt everywhere**, not the whole answer:

1. **Tier inversion** — the router declares `qwen2.5:14b-instruct` the reasoning default, yet the
   corpus-*building* and counsel-*facing* paths hard-code the smaller **7B**: `comprehend.py` (fact
   extraction — the front door), `verify_worker.py` (verification), `brief_drafter.py` (counsel drafts) —
   while mere checkers (`proof.py`, `case_synthesizer`, `ombudsman_hunter`) get 14B. Stakes are backwards.
2. **Verification debt** — the KB is **85.7% `inferred_strong`** (35,850) vs **14.3% `verified`** (5,999);
   the 7B harvester outran the 7B verifier ~37:1 in the last 7d. Raw model output dominates the base.
   Also: `inferred_weak` = **7 rows total** — the confidence grader calls almost everything "strong,"
   which means the tier is **not discriminating** (a calibration failure, see F5).
3. **Instrumentation blindness** — `inference_audit` logs ONLY `verify_worker`; the other ~19 reasoning
   callers (INCLUDING `comprehend`) call Ollama directly and log nothing. The path that produces 86% of the
   facts is unmonitored.

**THE META-LESSON — bake this into every step.** The first pass nearly concluded "only `verify` runs"
from `inference_audit` alone. That was wrong: the audit table is blind to 19 direct callers. **Never trust
one telemetry source. Triangulate: code (what calls the model) × DB (what it produced) × logs/timers (did
it run) × sampled output (is it right).** A reasoning issue hides precisely where one of those four is dark.

---

## 1. What "the reasoning layer" is

Every transformation where the stack DECIDES something a dumb pipe couldn't:
- reads ambiguous input (OCR: what does this smudge say?),
- extracts structure (this text → these facts / this course / this entity),
- judges truth (is this grounded? does it contradict? what confidence tier?),
- resolves identity (are these two names one person? which client owns this?),
- synthesizes (brief, memo, strategy, the equilibrium recompute),
- and decides emission (what does THIS recipient see, in what form, at what dose).

Each is a reasoning site. Each can fail silently. Audit **all** of them.

---

## 2. The reasoning map — audit stage by stage

### A. UPSTREAM — ingestion (the user asked for this in detail; it is the highest-leverage stage)
Garbage or misread here poisons everything downstream, and it is the least-monitored.

- **OCR / vision** (`reocr_local.py` 7B-VL · `reocr_gemini.py` · `survey_vision_extract.py`). Audit:
  - Which engine is chosen per doc, and is the choice logged? Is the OCR-ladder (DocAI → preprocess →
    frontier/local vision on the hard region → **reconcile vs the doc's own totals**) actually reconciling
    numbers, or just transcribing? (memory: OCR is dependable only as a *pipeline* that cross-checks the
    doc's own arithmetic; a clean transcription of a wrong digit still earns verified — A77's honest limit).
  - **Per-field OCR confidence** — memory says only doc-level `ocr_quality.score` exists. Confirm. A
    doc-level score can't flag a single misread digit in a boundary call or an amount. This is a gap.
  - **Silent OCR "corrections"** — Principle 9 / §4B inline inference marking. Grep for OCR paths that
    rewrite text without a `[OCR: raw]` tag. Past violations are recorded (`drafts/ocr_pending_write/*`).
- **Extraction** (`comprehend.py`, text → `matter_facts`/`proposed_facts`). Audit:
  - Model tier (found: 7B). Prompt quality — read `comprehend.PROMPT`; is it single-source, un-drifted?
  - How it assigns `fact_kind`/`element_code`/**`provenance_level`** — the tier assignment is itself a
    reasoning act, and F5 shows it isn't discriminating.
  - Does it emit to the gated `proposed_facts` inbox (A19/A49) or write facts directly?
- **Entity resolution** (`entities.canonical_id` merge graph). Audit: merge decisions (phonetic
  Keesey/Keesee), the DAG (A15, `test_entity_merge_dag`), cross-client merges (A16 allowlist). A wrong merge
  fuses two real people — a reasoning error with legal consequences.
- **Classification** (`classify_document_type.py`, A45). The one caller that DOES use `model_router` — use
  it as the reference pattern for wiring the others.
- **Geometry** (`strip_plot_info` → `parcel_courses` → `geometry_consensus`). Course reading is OCR-grade
  reasoning; the consensus (corroborated/single/CONFLICT) is the adjudication. Both are reasoning sites.

### B. CORE — verification & adjudication
- `verify_worker.py` (7B) — grounds facts vs verbatim excerpt (A78 gate is mechanical, so a 7B misread of
  "is this grounded" is partly backstopped — but confirm the excerpt-match is exact, not fuzzy).
- `leo_answer_gate.py`, `truth_negotiator`/`truth_judge`, the provenance write-gates (V3/V4/V11),
  contradiction-at-ingest (`contradiction.py`), the incorporation gate (A70). Audit: do any REASON in a way
  that could pass bad output, and is each gate mechanical (good) or LLM-judged (fragile — the truth_qa
  lesson: mechanical > LLM interrogation, A24)?

### C. SYNTHESIS — the high-stakes reasoning
`legal_agent` (14B), `case_synthesizer` (14B), `brief_drafter` (**7B — counsel-facing, flag**), `case_memo`,
`dossier_pipeline`, `ombudsman_hunter` (14B), `proof.py` (14B), the strategy/play engines, `equilibrium_propagate`
(A76). Audit: model tier vs stakes; whether each reads ONLY `_safe`/`verified` (A19); whether the 3-pass
harnesses (synthesize→proof→verify) actually run or are stubbed.

### D. DOWNSTREAM — emission
`recipient_projection` (A75), the A79 role clamp, `comm_agent_max`, Leo replies. Audit: does anything
reason its way PAST a gate? Is the human/machine form split (A34 vs handles-intact) honored? Does dose/clamp
depend on a model judgment that could be wrong (and if so, is it fail-closed)?

### E. CROSS-CUTTING infrastructure
- `model_router.py` — tier selection IS a reasoning-allocation decision. Is the declared 14B default
  actually reached, or does everything bypass it (found: 19 of 20 callers bypass it)?
- `inference_audit` — the telemetry. Its blindness (only verify) is itself a finding (F3).
- The prompts — the actual reasoning instructions. Drift, duplication, un-versioned edits.
- Retrieval quality feeding synthesis (rag_local / the retrieval projection) — garbage-in to a good model
  still yields garbage. Is the context a synthesizer gets actually relevant + in-scope (A5)?

---

## 3. The failure taxonomy — the classes to hunt at EVERY site in §2

- **F1 Tier–stakes mismatch** — a high-consequence judgment on a small model (or vice-versa, wasting 14B on
  a checker). Map every site → model → stakes; flag inversions.
- **F2 Un-adjudicated dominance** — raw model output entering the KB/deliverable without passing a gate, or
  a verification layer that can't keep pace (the 37:1 debt).
- **F3 Invisible errors** — a reasoning site with no telemetry, no eval, no golden reference. If it silently
  degraded tomorrow, would anything fire? If no → finding.
- **F4 Prompt drift / duplication** — the instruction the model follows is stale, forked, or un-versioned.
- **F5 Miscalibrated confidence** — the provenance/confidence tier doesn't discriminate (inferred_weak=7 of
  35k). Sample and measure whether `inferred_strong` facts are actually strong.
- **F6 Gate bypass** — reasoning output reaching a surface without its gate (A19/A21/A49/A70/A75/A79).
- **F7 Compounding** — one bad extraction spawning many derived facts/edges (the ego-network amplifies it).
  Trace: does a single low-quality source doc dominate a matter's fact base?
- **F8 Garbage-in retrieval** — the model is fine but its context is wrong-scope, stale, or cross-client.
- **F9 Missing human-in-loop** — a stakes level that demands operator adjudication is auto-resolved.

For each finding: **site · failure class · evidence (the code+DB+log triangulation) · concrete failure
scenario · proposed fix · a proposed MEASUREMENT that would catch a regression.**

---

## 4. Finding the unknown-unknowns (build DETECTION, don't just spot-check)

Spot-checks find known issues; these find the ones we can't see yet. **Mechanical-first, anti-trap
(measure-don't-model; no synthetic facts in the KB; no expensive LLM-interrogation harness — truth_qa was
killed for exactly that).**

1. **Golden set from REAL ground truth** — pick ~20 docs whose facts are independently known (physical
   originals, operator-attested, or already `verified` with verbatim excerpts). Re-run extraction; diff the
   model's output vs ground truth. This is the extraction-accuracy meter that does not exist today. Real
   docs only — never synthetic.
2. **Shadow A/B on model tier** — same real docs through 7B vs 14B; diff the extracted facts (names, dates,
   amounts, courses). Quantify what the small model gets wrong. This is the evidence to decide F1 flips —
   never flip a prod default without it.
3. **Provenance-tier calibration sample** — draw a random sample of `inferred_strong` facts, check each
   against its source (a frontier read on credits, or operator). Measure the TRUE accuracy of the tier vs
   its claimed strength. If "strong" is often wrong, the whole ladder is miscalibrated (F5).
4. **Adversarial planting (rolled back)** — inject a known-wrong fact / a contradiction / a cross-client
   citation in a TRANSACTION and confirm the gates catch it, then ROLL BACK. Never persist. This proves the
   backstops actually bite where §3 assumes they do.
5. **Telemetry backfill** — route the direct Ollama callers through `model_router` (or a thin logging
   wrapper) so `inference_audit` sees them. You cannot audit what you cannot see; this closes F3 permanently
   and makes the next audit cheap.
6. **Cross-source reconciliation** — where two independent docs assert the same thing (a title + its annex,
   two OCR passes, extraction vs the doc's own totals), do they agree? Disagreement = a reasoning error the
   single-path view can't surface. (This is `field_consensus`/`geometry_consensus` generalized.)
7. **Compounding trace** — for the top matters, rank source docs by how many facts derive from each; a
   single weak doc dominating a matter's base is a concentrated risk (F7).
8. **Completeness critic** — end each phase by asking "which reasoning site did I NOT instrument, sample, or
   cross-check?" That list is the next audit's work. Log what was left dark; silent coverage gaps read as
   "audited" when they weren't.

---

## 5. Guardrails (violations are rollbacks)

- **Read-only until findings are reported.** No model default flips, no prompt edits, no gate changes, no
  tier changes in production during the audit. Recommend; the operator picks; then shadow-A/B before any flip.
- **No synthetic facts in the KB.** Golden sets use real docs; adversarial probes run in rolled-back txns.
- **Mechanical over LLM-judge** (A24). Prefer SQL assertions, excerpt matching, arithmetic reconciliation.
  Do NOT stand up a standing LLM-interrogation harness (truth_qa is dead; don't resurrect it).
- **Provenance sacred** (A1/A2) · **client isolation** (A5 — every audit query is client-scoped; a
  cross-client sample is itself a finding) · **no phantom enforcement** (any new invariant you propose stays
  🟡 doctrine until its floor exists — the desk mints it, you don't self-promote).
- **Don't nuke-and-rebuild.** The gap is instrumentation + calibration + tier-fit on EXISTING machinery, not
  a new reasoning stack. Additive fixes.
- **Cost** — sampling that spends credits (frontier calibration, §4.3) is metered and budget-gated (A60);
  state the spend before running it. Local A/B (7B vs 14B) is $0 — prefer it.
- **Two-desk git:** `pull --rebase`, commit SPECIFIC paths, leave peer-dirty files, gates green before push.

---

## 6. Deliverable

A ranked findings report (most-severe first), each finding carrying the §3 fields. Structure it so the
operator can act per-item: site · class · evidence · failure scenario · fix · the measurement that would
detect recurrence. Where a finding warrants a durable rule, propose it to the desk as a 🟡 invariant with a
named graduation trigger (do not edit ONTOLOGY.md yourself). End with the §4.8 completeness-critic list of
what remained dark — that is the honest boundary of this pass.

## 7. Method reminder (the meta-lesson, restated because it is the whole game)

For every claim in the report, show the triangulation: **code** (what invokes the model) × **DB** (what it
produced + at what provenance) × **logs/timers** (did it actually run, how often, how slow) × **sampled
output** (is it correct against a real reference). A finding backed by only one of these is a hypothesis,
not a finding — mark it as such.

## 8. Seed facts (grounded 2026-07-19 — start from truth, don't re-derive)

- Ollama up, 5 models loaded (`qwen2.5:7b-instruct`, `qwen2.5:14b-instruct`, `qwen2.5vl:7b`, `nomic-embed-text`,
  `llama3:8b`). Inference healthy (0 fails/24h, 3 transient/7d, fallback worked). Latency swing is cold-start,
  not regression.
- `matter_facts`: 41,878 total — inferred_strong 35,850 / verified 5,999 / operator 22 / inferred_weak 7.
- `inference_audit` logs ONLY `task_type='verify'` (7B). ~19 other reasoning scripts call Ollama directly.
- Open gate holds: owner-holds 313, contradictions 45, contradiction_holds 14 (the backstops are catching
  things — quantify what and whether the rate is rising).

## 9. Phasing (optional — the audit is large; a single agent can serialize, or fan out)

P1 upstream/ingestion (§2A) — highest leverage, do first. P2 core+synthesis (§2B/C). P3 downstream+infra
(§2D/E). P4 build the detectors (§4) — golden set, A/B, telemetry backfill — these outlast the audit and make
the next one cheap. Each phase is an independent read-only pass ending in a partial findings report; nothing
downstream depends on a phase completing, so they can run in parallel.

## Close-out — Full-stack reasoning audit (parallel multi-agent, 2026-07-19)

**Mode:** read-only · 4 explore finders (OCR · extract/entity/geometry · verify/gates/synth · emission/router) · parent triangulation on live VPS Postgres + code.  
**No flips.** Operator picks; shadow A/B before any production change.

### Live re-baseline (VPS, 2026-07-19) — corrects the seed narrative

| Signal | Live | Implication |
|---|---|---|
| `matter_facts` | ~42.5k · **inferred_strong 36,511** · **verified 6,002** · operator 22 · **inferred_weak 7** | ~86/14 ratio **CONFIRMED** |
| 7d writers | **doc_populate 27,582** + **harvest 8,530** inferred · **verify_worker 948** verified | Bulk “harvester” is **regex/table populate, not 7B LLM** |
| `inference_audit` 7d | **543× verify / qwen2.5:7b** · 3× gemini tier2 · **0 fails** (3 fail rows older) · only `task_type=verify` | F3 **CONFIRMED**; health looks fine because only verify is visible |
| Latency by day | 6.5s (n=393) → 20s (quiet days) | Cold-start variance, not model death |
| Ollama (Mac TS) | 7b, 14b, vl:7b, nomic, llama3:8b **up** | Availability OK; VPS `127.0.0.1:11434` may be empty — workers use `100.117.118.47` |
| `ocr_quality` | **2,137** docs · **avg score 0.36** | Corpus OCR is weak on average; only doc-level score |
| Compounding | doc **958 → 667 facts** (2 verified / 665 inferred) | F7 concentration **CONFIRMED** |
| Short inferred | **~18.5k** statements length &lt;20 | Much of “strong” is atom shards (AMOUNT: lines), not deep reasoning |
| `proposed_facts` | pending 221 · contradiction_hold 14 · accepted 7 | Adjudication still backlog |
| Open contradictions | **45** | Backstops catching something |

**Meta-lesson applied:** the first narrow pass over-attributed the 86% mass to “7B harvest.” Live `created_by` shows **mechanical extraction outrunning verification**. Tier inversion on *LLM* paths remains real, but the **volume** problem is F2+F5 on **regex writers**, not only F1 on 7B.

---

### Ranked findings (most severe first)

#### R1 — Instrumentation blindness · F3 · **CRITICAL** · CONFIRMED
- **Site:** `inference_audit` + fleet Ollama callers  
- **Evidence:**  
  - *code:* only `verify_worker` + rare `model_router`/`classify` write audit; comprehend, brief_drafter, leo_service, reocr_*, legal_agent, case_synthesizer, harvest (N/A), etc. bypass  
  - *DB:* 7d audit = 100% `task_type=verify`  
  - *logs:* separate reocr/awareness files, not unified  
- **Scenario:** comprehend / OCR / free Leo degrades for a week; dashboards still green on verify  
- **Fix:** thin shared logger or force `model_router.call_model` for every generate; `task_type` ∈ {verify,extract,classify,reason,ocr_vision,synth,reply}  
- **Measure:** every timed unit appears in `SELECT created_by, task_type, count(*) … 24h`; alert on known timer with 0 rows  

#### R2 — Un-adjudicated dominance + miscalibrated “strong” · F2+F5 · **CRITICAL** · CONFIRMED
- **Site:** `harvest_facts` + `populate_tables_from_docs` → `matter_facts.inferred_strong` always  
- **Evidence:**  
  - *code:* both hard-code `provenance_level='inferred_strong'`; no weak band  
  - *DB:* 86% strong · **7 weak total** · writers above  
  - *sample:* repeated `AMOUNT: ₱35,000.00` shards from doc_populate  
- **Scenario:** operators/tools that don’t filter verified treat atom spam as knowledge; verify never catches up (948 vs 36k/7d)  
- **Fix:** (1) harvest single-hit → `inferred_weak` or side table; (2) rate-limit populate facts per doc; (3) product surfaces default to verified/publish only; (4) drain short-duplicate atoms  
- **Measure:** weekly `verified/(verified+inferred)` + % short statements + facts-per-source_doc P95  

#### R3 — OCR silent rewrite + no arithmetic + doc-level confidence only · F6+F5+F2 · **CRITICAL** · CONFIRMED
- **Site:** `reocr_local` / `reocr_gemini` / `write_ocr`  
- **Evidence:**  
  - *code:* `extracted_text` overwritten with no `[OCR: raw]`; accept = doc score ↑ only; no sum/area reconcile on general path (geometry path *does* close+area — positive control)  
  - *DB:* `ocr_quality` has score/chars/word_quality only; avg 0.36  
  - *sample:* drafts/ocr_pending_write flags; A77 doc 379 low score still underwrote many verified facts  
- **Scenario:** clean misread digit → excerpt-grounded → **verified** forever (A77 honest limit)  
- **Fix:** adoption chokepoint + Principle 9 lint; internal arithmetic hold for amounts/areas; keystone docs structured OCR; dual-pass hold on disagreement  
- **Measure:** reocr accepts with internal-arithmetic fail = 0; % verified facts from docs with score&lt;0.55  

#### R4 — Tier–stakes inversion on real LLM paths · F1 · **HIGH** · CONFIRMED
- **Site:** defaults vs `model_router` policy  
| Path | Default | Stakes |
|---|---|---|
| verify_worker, brief_drafter, case_memo, analyst, relevance, comprehend fallback | **7B** | corpus + counsel drafts |
| legal_agent, case_synthesizer, leo_service, proof, ombudsman | **14B** | synthesis / chat |
| reocr_local | **VL 7B** | keystone text |
| model_router declared | **14B reasoning** | almost unused |

- **Evidence:** code hardcodes × router TASK_QUALITY × audit only 7B verify  
- **Scenario:** 7B wrong-but-groundable claim becomes verified; 14B only polishes later  
- **Fix:** shadow A/B 7B vs 14B on ~20 real docs for verify + brief + keystone OCR; flip only with measured delta  
- **Measure:** disagreement rate names/dates/amounts/courses; never flip on vibes  

#### R5 — Live emission can ship model text without enforce-mode A79 · F6 · **HIGH** · CONFIRMED
- **Site:** Telegram `llm.handle` + `leo_service.generate_reply` + shadow `apply_comms_role_clamp`  
- **Evidence:**  
  - *code:* A79 returns output **unchanged** (shadow); TG free path skips clamp + often human projection; `gate_error` returns **raw candidate**; outward_guard fail-open allow  
  - *tests:* `shadow_never_blocks` floors the non-bite  
- **Scenario:** fluent wrong reply lands on phone before hearing — operator catches, not gate (matches prior “clueless” class)  
- **Fix:** one chokepoint (CAM/process) for all live sends; A79 enforce after soak; never return unremediated candidate on gate_error  
- **Measure:** negative tests: free TG path cannot send without clamp+gate; count live sends without via label  

#### R6 — Unscoped RAG in playbook synthesizer · F8 · **HIGH** · CONFIRMED
- **Site:** `case_synthesizer` `rag.retrieve(query)` **without `ids`**  
- **Evidence:** code path global; docket path correctly passes ids; `rag_local` has no client column in filter  
- **Scenario:** MWK memo pulls Paracale chunks → cross-client contamination in counsel prose  
- **Fix:** fail closed if retrieve without matter/client/`ids` for synthesis  
- **Measure:** two-client plant (rollback) — zero foreign chunks in synth context  

#### R7 — Entity keystone multi-client AUTO merge · F6/F9 · **HIGH** · CONFIRMED (logic)
- **Site:** `entity_resolve` `protected_present → auto` even when `len(clients)>1`  
- **Evidence:** code; daily cross-client timer applies auto; docs claim stricter than code  
- **Scenario:** keystone name + OCR twin other client → fused identity  
- **Fix:** AUTO only single-client; keystone only picks survivor inside one client  
- **Measure:** `--scan` count of multi-client AUTO groups → 0  

#### R8 — Gate floors incomplete · F6 · **MEDIUM–HIGH** · CONFIRMED
- **Site:** V11 null-owner **shadow log**; V4 NULL owner pass; truth_negotiator challenger **stub-agrees** without Anthropic key; **legal_agent skips A70** while brief/dossier enforce  
- **Evidence:** code + A77/A78 workorder history  
- **Scenario:** ownerless/thin counsel memo ships; challenger never refutes  
- **Fix:** V11 soak→block; wire A70 into legal_agent/case_memo; don’t trust negotiator “verified” when challenger stubbed  
- **Measure:** block-mode soak report; % counsel synth with A70 pass  

#### R9 — Compounding from single weak source · F7 · **MEDIUM** · CONFIRMED
- **Site:** harvest/populate → many facts per doc  
- **Evidence:** doc 958 = 667 facts / 2 verified; OCR avg weak  
- **Scenario:** one bad re-OCR underwrites a matter’s graph  
- **Fix:** cap inferred density per doc; dual-source or human for keystone amounts/dates; re-OCR demotion path  
- **Measure:** top-20 docs by fact count with ocr_score and verified ratio  

#### R10 — Prompt / doctrine drift · F4 · **MEDIUM** · CONFIRMED (partial)
- **Site:** per-script PROMPTs; `model_router` SYSTEM_PROMPTS mostly unused; ops docs still call “comprehend” the fact front door  
- **Evidence:** code inventory + F-A2 architecture drift  
- **Fix:** versioned prompt files; ops labels match `created_by` census  
- **Measure:** prompt hash column on audit; doc/code grep for stale “comprehend harvests facts” claims  

#### Positive controls (keep)
- **Excerpt gate** (`excerpt_grounded` + V3) — mechanical, OCR-robust normalize, real anti-fabrication  
- **classify_document_type** — only clean model_router + shadow-commit pattern (clone this)  
- **geometry_consensus** — closure/compactness/area; multi-doc corroboration  
- **brief_drafter / case_dossier verified filter + A70** on some paths  
- **Verify health** — 0 fail/24h-class availability; fallback to Gemini worked  

---

### Failure taxonomy coverage

| Class | Result this pass |
|---|---|
| F1 Tier–stakes | CONFIRMED (LLM paths) |
| F2 Un-adjudicated | CONFIRMED (regex mass + debt) |
| F3 Invisible | CONFIRMED |
| F4 Prompt drift | CONFIRMED partial |
| F5 Calibration | CONFIRMED (always-strong + weak≈0) |
| F6 Gate bypass | CONFIRMED (OCR tags, A79 shadow, TG, V11, A70 uneven) |
| F7 Compounding | CONFIRMED (doc 958 class) |
| F8 Retrieval | CONFIRMED (playbook RAG) |
| F9 Human-in-loop | CONFIRMED (auto-verify OCR-true wrongs; entity auto) |

---

### What stayed dark (§4.8 completeness critic) — next audit

1. **Golden set** — re-extract ~20 operator-attested docs; accuracy meter does not exist yet  
2. **7B vs 14B shadow A/B** — not run ($0 local; needs scheduled pass)  
3. **Calibration sample** — human grade N random `inferred_strong` (frontier optional, budget-gated)  
4. **Adversarial plant** — wrong fact / cross-client cite in rolled-back txn to prove V3/V4/A5 bite live  
5. **Live entity AUTO multi-client rate** — logic confirmed; bite rate not scanned  
6. **Telegram live send sample** vs shadow outward logs  
7. **Whether residual n8n reply brain** still fires on any channel  
8. **Comprehend title-status error rate** vs chain ground truth  
9. **reocr_log engine distribution** last 30d (accept/reject by local vs gemini)  

---

### Recommended operator sequence (additive, no nuke)

| Priority | Action | Cost | Risk |
|---|---|---|---|
| **P0** | Telemetry wrap all generate → `inference_audit` (closes permanent blindness) | $0 eng | Low |
| **P0** | Product/read surfaces: verified + publish only (don’t “fix” 86% in UI) | $0 | Low |
| **P1** | Harvest/populate: stop always-strong; cap atoms; weak tier or side table | $0 | Med (throughput) |
| **P1** | OCR write chokepoint + Principle 9 lint + arithmetic hold where possible | $0–eng | Med |
| **P1** | Fail-closed RAG scope on synthesizer | $0 | Low |
| **P2** | Entity AUTO cross-client hole | $0 | Low |
| **P2** | Shadow A/B then consider 14B on verify/brief/keystone OCR | $0 local | Med if flipped blind |
| **P2** | A79 enforce + single send chokepoint after soak | policy | High if early |
| **P3** | V11 block soak; A70 on legal_agent; golden set + calibration sample | mixed | — |

**Do not:** flip all defaults to 14B without A/B; resurrect truth_qa LLM-judge; blame “the model is down” (it isn’t).

---

### Parallel workflow notes

- Finders: OCR, extract/entity/geometry, verify/gates/synth, emission/router — all completed.  
- Adversarial parent pass: **refuted** seed claim “7B LLM produced the 35k/7d spike” → **doc_populate+harvest mechanical**; kept tier inversion as separate F1.  
- Anything single-lens only is marked PLAUSIBLE above; multi-lens items are CONFIRMED.

*End close-out 2026-07-19.*
