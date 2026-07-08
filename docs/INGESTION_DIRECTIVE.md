# INGESTION DIRECTIVE — Corpus OCR & Knowledge-Connection Pipeline

> **Purpose:** every document that enters a matter's corpus becomes a **fully-connected, high-fidelity, cited knowledge node — automatically and repeatably.** This codifies what the 2026-07-06 OCR bake-off + connectivity audit proved, so we never rediscover it.
> **Runs ON THE VPS** (Mac can't reach DB/creds). The one exception — the frontier-vision OCR step — is **agent-in-the-loop and needs no external key** (the agent *is* the frontier VLM).
> **Owner note:** coordinate with the VPS/cowork side, which owns the deploy_686 ingest sweeps.

---

## DEFINITION OF "DONE" (one document is fully ingested when it has ALL of:)
1. **Best-obtainable text** (via the OCR ladder — Stage 1)
2. Correct **`case_file` + matter/sub-matter links** (client-separated)
3. **Resolved entities** (people/orgs/titles, deduped)
4. **Harvested facts** in `matter_facts`, provenance-tiered + cited
5. A **vector embedding** (searchable in RAG)
6. **Tracker-baselined** (`paracale_corpus_watch.py`)

A corpus is "genuinely connected" when **every doc clears all six** — measured per-matter (see Dashboard).

---

## STAGE 0 — INTAKE & TRIAGE
- **Channels:** Drive sweep (`ingest_drive_folder.py` / `ingest_paracale_drive.py`), Telegram→Drive, Gmail ingest, scanner.
- **Force-tag `case_file` at intake** — never auto-classify across clients (client-separation invariant; ontology V4 guards it).
- **⚠ TRIAGE before embedding — do NOT embed noise.** The FB-export lesson: 513 photos, only 172 were documents. Rule: keyword-sweep via **Google's OCR index** (free) to separate document-photos from personal/family photos → ingest documents, **archive the rest** (a vision drip only for the OCR-missed remainder). Never let 300 vacation photos into the knowledge base.

## STAGE 1 — THE OCR LADDER (automatic · conditional · fail-closed)

**Automatic trigger — the remediation predicate.** A doc is remediation-eligible when it HAS a source
image AND its text is unusable, measured mechanically (no human in the loop to decide *whether*):
- **no usable text:** `text_length < 50` (extraction empty/failed), **OR**
- **garbled text:** `ocr_quality.flagged` = true (`score < 0.30` with a source present).

Clean docs (`score ≥ 0.30` and `text_length ≥ 50`) are **NEVER preprocessed** — enhancing a clean page
wastes work and can degrade it. Preprocessing fires **only** on the eligible set. This is the whole point:
preprocessing becomes a regular automatic step, gated by a measurable quality condition.

**Order of operations (per eligible doc — the operative):**
1. **Baseline read** — DocAI (bulk, creditless) / local Tesseract as the doc arrives. If it clears the gate
   (`score ≥ 0.30`), STOP — no remediation.
2. **Quality gate** (`scripts/ocr_quality.py --scan --go`): re-score; if flagged → escalate to (3).
3. **Conditional preprocess** (`scripts/ocr_preprocess.py --variants gray,blue,bw --dpi 450`) — render the
   source page(s) into the three enhanced variants. **Pass `--dpi 450` explicitly** — the tool *defaults to
   300*; the operative runs at 450. Variant roles (unchanged, validated):
   - `gray` = grayscale + autocontrast + unsharp + light denoise → **faded old typescript** (tried **first**;
     the validated winner on the 1992 Partition — `blue` over-thins faded ink into fragments)
   - `blue` = blue-channel isolation → **only** for "UNOFFICIAL COPY IF NOT IN BLUE COLOR" security-ink titles/CTCs
   - `bw`   = adaptive threshold → Tesseract fallback
4. **Vision/OCR read of the ENHANCED image** (OCR-ladder engine, within quota; frontier-vision is
   agent-in-loop, no key). Read `gray` first; escalate to `blue` for blue-security-ink docs, `bw` last. For a
   hard region, **crop + magnify** (~3×) before reading (the royalty column only became legible cropped & upscaled).
5. **RECONCILE against the doc's own internal totals/structure** — the step that *beat the raw VLMs* (Qwen
   returned 106%, Gemini 101% guessing glyphs in isolation; preprocess + magnify + reconcile-to-100% produced
   the self-consistent read). If the doc states a total, verify the extracted line-items sum to it; on
   mismatch, **flag — do not trust the digit.**
6. **Re-score** the new read (`ocr_quality`).
7. **Accept ONLY on improvement (fail-closed).** Write the new text only if it scores **strictly better** than
   the prior read — never overwrite good text with worse. On accept, in ONE transaction: back up old text →
   write `extracted_text`/`text_length`/`ocr_used` → **record the read in `extraction_runs`
   (`doc_id, model, status='completed'`)** so `model_used` is **EARNED** from a real run (A42 — never fabricated
   to pass the gate) → re-score `ocr_quality` → re-embed (set `corpus_backfill_state.embedded = true`) → set
   `document_type`. These are exactly the 5 `ConnectivityGate` signals — so an accepted doc passes by construction.
8. **Gate + certify** — the `ocr_remediation` work-kind runs `supervisor.py::_connect_verify` (the 5 signals,
   A41/A43); court-critical docs then require `certify` (T3, human).
9. **Physical original / macro phone photo** — ONLY for a court-certified digit still ribbon-broken after all the above.

**Failure handling — no infinite loops, no silent holes.** If the enhanced read still scores `< 0.30` after
all variants, escalate the variant ladder (`gray → blue → bw → frontier crop+magnify`). If still failing, cap
attempts (**≤ 3**, like `corpus_backfill`) and mark the doc `remediation_exhausted` on the human worklist
(`case_work/OCR_WORKLIST.md`) — **NEVER** stamp `model_used`, **NEVER** pass the gate on a failed read. Gemini
429 leaves the doc untouched for retry (no partial write, no failure log).

**NEVER:** preprocess a clean page · overwrite better text with worse · fabricate/stamp `model_used` on a
failed or unreconciled read · quote an unreconciled digit in a filing · self-host a 72B VLM (empirically
*worse* — confident hallucination without self-check) · rely on Gemini free-tier as a primary (chronic 429) ·
trust Drive's OCR for a document's *existence* (it missed the 1985 Undertaking entirely).

> **Implementation status (2026-07-08) — BUILT · SHADOW · enable pending.** The automated re-OCR path
> (`reocr_gemini.py` on `landtek-reocr-sweep.timer`) now IMPLEMENTS this operative: conditional gray preprocess
> (`_page_png`) → vision read → **strict-improvement guard** (never regress good text) → atomic re-score
> `ocr_quality` + `document_type` + (only when all 5 signals hold) earn `model_used` via a real `extraction_runs`
> row — **A41-safe by construction**. It runs in **SHADOW**: `--stamp` is OFF on the timer, so no provenance is
> written until enabled. Governance guardrails are in place (deploy_767): the §3.5 sweep backfill is 4-signal-
> gated, and `truth_tests/test_provenance_earned_from_run.py` (A42) + `test_connected_document_count.py` (A41)
> gate every deploy/nightly. **Blockers to enabling:** (1) Gemini free-tier 429; (2) the pilot in MASTER_PLAN
> §6B W1. `corpus_backfill.py` (no-text path) still OCRs raw at dpi 120 and does not preprocess — a separate
> follow-on. Reconcile-to-totals remains agent-in-loop.

### ROLLOUT — enabling provenance stamping (shadow → pilot → enabled)

The Phase-1+2 capability is BUILT and SHADOW (`--stamp` off). Enable it **supervised-first — never a blanket
timer flip.** Every step has a monitoring window; any red truth_test or connectivity regression PAUSES the rollout.

**Go / no-go gates (ALL must hold before advancing a step):**
- `truth_tests/run_all.py` green — esp. `connectivity.provenance_implies_all_5_signals` (A41),
  `provenance.earned_stamp_traces_to_run` (A42), `incorporation.view_reconciles_with_a41`.
- `python3 scripts/incorporation_status.py --check-regression` clean (connected ≥ high-water mark).
- On the pilot batch: accept-rate reasonable and the stamped docs verified truly 5/5.

**Sequence:**
1. **SHADOW (now).** Timer runs `reocr_gemini --sweep` with **no** `--stamp`: improves text/quality/type, logs
   `would-stamp`, writes no provenance. Watch `incorporation_status.py` + the nightly. (Live reads blocked on Gemini 429.)
2. **PILOT (supervised, per-doc).** When quota returns, enable via the `ocr_remediation` work-kind on a few
   keystone docs — `reocr_gemini.py --doc <id> --go --stamp` under the T3 chokepoint. After each: run the three
   truth_tests + `--check-regression`. Expect ~6 already-ready docs to move provenance 86 → ~92.
3. **EXPAND.** Only after a clean pilot, widen the supervised set. Add `--stamp` to `landtek-reocr-sweep.service`
   for volume **only** after several clean supervised rounds.
4. **ROLLBACK.** If a truth_test reddens or `--check-regression` fires: remove `--stamp` / `git revert` the
   enabling change. Text/quality/type writes are non-regressing (strict-improvement guard), so there is no data to undo.

**Grounded status (2026-07-08) + the O-pathway (zero-corruption) additions (deploy_771):**
- **All go/no-go gates currently GREEN:** `truth_tests/run_all.py` 94 pass (A41 `provenance_implies_all_5_signals`,
  A42 `earned_stamp_traces_to_run`, `incorporation.view_reconciles_with_a41`); `incorporation_status.py
  --check-regression` clean (connected **86 = high-water**); and **new Gate 4** — `ontology_check.py --shadow-status`
  shows V8 (and V5/V6/V7) at **0 findings**. Run all four before advancing any step.
- **Provenance is QUOTA-stuck at 86, not switch-stuck.** Verified 2026-07-08: **PILOT-READY = 0** — *no* doc has all
  4 deterministic signals + a completed `extraction_runs` row yet missing only the stamp. Earning a NEW stamp
  requires a *fresh* completed run = a live Gemini re-OCR. So the earlier "~6 ready docs → 92" estimate is
  superseded: the pilot cannot stamp anything until Gemini quota returns AND a supervised re-OCR produces the run.
  SHADOW keeps running (hourly `landtek-reocr-sweep`, active — text/quality/type only, no provenance).
- **V8 is the corruption tripwire — run the pilot UNDER V8 shadow.** V8 (`log`) already watches every
  `documents.model_used` write. During the supervised `--stamp` pilot, V8 must stay at **0** findings — a single
  `ONTOLOGY_PROVENANCE_UNEARNED` means the pipeline stamped *before* its `extraction_runs` row completed (a
  transaction-ordering corruption). **That finding is the circuit-breaker: pause the pilot immediately.**
- **Corrected flip order (the O-pathway):** do NOT flip V8→block before the pilot. Sequence: (a) run the supervised
  `--stamp` pilot with V8 in shadow; (b) confirm `--shadow-status` V8 = 0 across the whole pilot (the pipeline earns
  provenance correctly, in the right order); (c) THEN flip V8→block so the guard hard-rejects any future unearned
  stamp; (d) expand. V8-shadow *proves* the ordering is safe before V8-block *enforces* it — zero-corruption by
  construction.
- **O-pathways — now BUILT (deploys 773/774/776):**
  1. **Pilot-time V8→P0 elevation (deploy_773/774).** `scripts/v8_provenance_p0_elevator.py` + a 3-min timer
     promote any open V8 `ONTOLOGY_PROVENANCE_UNEARNED` finding **info→P0** (so `holes.p0_pusher` pages) and drop a
     **PAUSE-THE-PILOT** note (naming the doc) into `notifications/pending.txt`. Dormant until a real finding.
  2. **Batch circuit-breaker (deploy_776).** `reocr_gemini --sweep` trips if accept-rate `< cb_rate` (default 34%)
     after `cb_min` docs (default 6) — reads not improving → stop, protect quota. Tune with `--cb-rate`/`--cb-min`.
  3. **Instant stamp off-ramp (deploy_776).** `touch /root/landtek/notifications/STOP_STAMP` → stamping degrades to
     **shadow** per-doc immediately (text/quality/type still improve); `rm` resumes. Fail-safe (unreadable path →
     off). No code/systemd edit, no data undo.

**Degradation matrix (what happens when a thing fails — all fail toward safety):**
| Condition | Behavior |
|---|---|
| Preprocess (gray) errors | `_page_png` fails **open** to the raw render — never loses the read |
| Gemini 429 / all combos quota'd | `QuotaExhausted` → sweep stops clean, doc left for retry (no partial write) |
| New read scores ≤ prior | **rejected** (strict-improvement guard) — prior text kept, nothing written |
| 4 deterministic signals not all present | provenance **withheld** (never a half-connected stamp) — A41 safe |
| Batch accept-rate < floor | **circuit-breaker** stops the sweep |
| Need to halt stamping NOW | **off-ramp** (`STOP_STAMP`) → degrade to shadow |
| Stamp-before-run (V8 finding) | **P0 page + PAUSE** (elevator) — the corruption tripwire |

**Supervised pilot procedure (per keystone doc, when quota returns):**
```
supervisor.py enqueue ocr_remediation --target doc:<id>     # opens the governed order
supervisor.py tick                                          # → 'remediate' handoff
reocr_gemini.py --doc <id> --go --stamp                     # THE atomic accept (earns provenance iff all 5 hold)
#   run the 4 gates:  truth_tests/run_all.py · incorporation_status.py --check-regression ·
#                     ontology_check.py --shadow-status (V8=0) · verify the doc is truly 5/5
supervisor.py complete <order_id> --result "remediated doc <id>"   # advance
supervisor.py tick                                          # → connect-verify (auto 5-signal gate) → certify (T3)
```
Any gate red / V8 finding / breaker trip → `touch STOP_STAMP`, stop, investigate; do NOT advance or expand.

## STAGE 2 — CONNECT (get the metadata in line)
Run in order (each feeds the next):
1. `scripts/routine_entity_doc_linker.py --max <N>` → populates **`doc_entities`** (entities per doc)
2. `scripts/entity_resolve.py --scan` then `--apply-auto` → **dedup/resolve** entities (ontology client-isolation blocks cross-client merges)
3. **`document_matter_links`** → link each doc to its matter/sub-matter (PAR-*, NIBDC-*)
4. `scripts/harvest_facts.py --matter <CODE> --go` → **`matter_facts`** (cited, provenance-tiered facts)
5. **Embed — LOCAL, creditless.** ⚠ The Gemini embedding endpoint is **403-forbidden** right now; use the **local Ollama embedder** (`rag_embed_local` — confirm exact invocation) → `extraction_chunks` + Qdrant. Do NOT block ingestion on the Gemini embed key.

## STAGE 3 — VERIFY & TRACK
- **Provenance write-gate:** OCR is a *finding aid, never the evidence*; `verified` = cited doc + quoted excerpt; legal output reads only `_safe` views; court filings use certified RD/PSA/court copies.
- **`scripts/paracale_corpus_watch.py --update`** → re-baseline + auto-flag new docs against the matter's open questions.
- **`scripts/ontology_check.py`** + `cross_client_sentinel` → catch drift and cross-client leaks.

---

## STANDING GATES (never skip)
| Gate | Rule |
|---|---|
| **Client separation** | force-tag `case_file` at intake; never merge entities/facts across clients |
| **Triage** | embed documents, not noise |
| **Provenance** | OCR ≠ evidence; verified = cited + excerpt; certified copies for court |
| **Reconcile** | cross-check extracted numbers vs the document's own totals before trusting |
| **Local-first** | prefer creditless local (DocAI, Ollama) — externals (Gemini/frontier API) are edges, not the spine |

## REPEATABLE RUN ORDER (after any ingest sweep)
`ingest → triage → OCR ladder (flagged) → entity-link → entity-resolve → matter-link → harvest-facts → local-embed → watch --update`

---

## CONNECTIVITY DASHBOARD (measure per matter — target = 100% on each)
Per `case_file`: `% with text` · `% entity-linked` · `% matter-linked` · `% fact-harvested` · `% embedded`.

### Current state — Paracale-001 (2026-07-06)
- **301 docs**; text ✅ (298/301). **1,055 facts · 196 doc-links · 139 entities already exist** — the pipeline works; it just hasn't run on the newest material.
- **87 newly-ingested FB doc-photos:** text ✅ but **0 entities · 0 embeddings · only 35 matter-linked** → **run Stage 2 on them.**
- **325 docs need embedding** (Gemini embed 403 → use the local path).
- **OCR re-queue (`case_work/OCR_WORKLIST.md`) keystones:** 1992 Partition (docs 510/671 — done via frontier; royalty %s reconciled, a/b pending physical original); DBP/Undertaking photo-pages; any faded title CTCs.

### Immediate backlog actions
1. `routine_entity_doc_linker` + `entity_resolve` over the new FB docs.
2. `harvest_facts --matter <PAR sub-matters> --go`.
3. Local-embed the 325 unembedded docs.
4. `paracale_corpus_watch --update` to re-baseline.

---

## DIRECTIVE — Governance/Ontology layer → Ingestion layer (2026-07-08, deploy_772)

*(Handoff by directive, not self-edit — the mirror of §6B's "Handoff to the ontology layer." Governance owns
the invariants/validators/mechanical gates + the V8 flip decision; the ingestion layer owns the pipeline code
and the pilot execution. This block hands you the actionable items from the enablement plan (§ROLLOUT).)*

**Governed status (verified 2026-07-08).** SHADOW is clean and running; **all four go/no-go gates are GREEN**
(94 truth_tests · `--shadow-status` V8=0 · `--check-regression` 86=high-water · `--alignment` clean). The pilot
is correctly **Gemini-gated**, and provenance is **quota-stuck at 86, not switch-stuck**: **PILOT-READY = 0** —
no doc can be stamped without a *fresh* completed `extraction_runs` row. Nothing to enable until quota returns.

**Your action items (ingestion layer — these are yours to execute):**
1. **When Gemini quota returns — run the Phase-2 pilot, supervised, UNDER V8 shadow.** 1–3 keystone docs via the
   `ocr_remediation` work-kind: `reocr_gemini.py --doc <id> --go --stamp` under the T3 chokepoint. After **each**
   doc, run all four gates. Report the results **before** expanding — do not batch-run the pilot.
2. **Honor the O-pathway (zero-corruption).** During `--stamp`, V8 must stay at **0** findings. A single
   `ONTOLOGY_PROVENANCE_UNEARNED` means you stamped `model_used` *before* the `extraction_runs` row committed —
   a transaction-ordering corruption. **That finding is the circuit-breaker: PAUSE the pilot immediately** and fix
   the ordering (run/commit the extraction_runs row, THEN set model_used) before resuming.
3. **Build the per-batch accept-rate circuit-breaker** (pipeline code, yours): auto-PAUSE the sweep if a batch's
   accept-rate drops below a floor or errors spike — extends the per-doc strict-improvement guard to per-batch.
4. **Do NOT enable `--stamp` on `landtek-reocr-sweep` / in production** until a verified supervised pilot **and**
   explicit sign-off. Blanket timer-flip is out; supervised-first only.

**What governance (this layer) owns and will do — do NOT do these yourself:**
- **The V8 `log→block` flip.** You don't flip it; when your pilot is clean and `--shadow-status` shows V8=0
  across it, **request the flip** and governance executes it (V8-shadow proves the ordering *before* V8-block
  enforces it). Flipping block first would risk breaking a legitimate stamp — held on purpose.
- **Arming the pilot-time tripwire:** governance will elevate a V8 finding to a paging alert *while `--stamp` is
  enabled* (it's `info` today). Tell governance when you're about to start the pilot so the alert is armed first.
- The mechanical gates (`truth_tests`, `--invariants`, `--shadow-status`, `--check-regression`, `--alignment`)
  and the ontology invariants A41–A43 — do not edit `ONTOLOGY.md` or the validators; request changes by directive.

**Boundary.** You: `reocr_gemini.py`, `forensic_ocr_healer.py`, the sweep/timer, the §3.5 CONNECT path, the
circuit-breaker. Governance: `ontology_validator` (V1–V8), `truth_tests/`, `ontology_check.py`, `ONTOLOGY.md`,
the V8 flip. Full plan: `MASTER_PLAN.md` §6B + this file's §ROLLOUT.

---

## ARCHITECTURE DIRECTION — PROPOSED 2026-07-08 (pending review · NOT yet adopted · nothing built)

> Design-only, to review before any implementation. Grounding: the corpus is ALREADY a half-adopted
> signal model — 8 signal/provenance tables exist (`ocr_quality`, `corpus_backfill_state`, `extraction_runs`,
> `rag_local`, `doc_entities`, `document_matter_links`, `document_type_proposals`, `extraction_chunks`); only
> 3 of the 5 gate signals live as wide `documents` columns (`extracted_text`, `model_used`, `document_type`).
> So this is *consistency + extensibility*, not a rebuild.

**Three ADDITIVE, reversible moves (no migration of the working gate):**
1. **Formalize provenance & classification as first-class records (name what exists).** `extraction_runs`
   IS the `ProvenanceRecord` (A42 source); `documents.model_used` is its denormalized cache. Generalize
   `document_type_proposals` → `document_classifications` (doc_id · dimension type/role · value · method
   deterministic|llm|human · model · confidence · status) — every type/role gains an audit trail; the
   `document_type`/`doc_role` columns become caches of the accepted row.
2. **Extensible `document_signals` table (additive, shadow).** New/experimental/agentic signals write here
   (doc_id · signal_type · value · confidence · provenance_ref · source · is_current) with NO `ALTER TABLE`.
   The 5 CANONICAL gate signals STAY in their fast homes — the gate (`_connect_verify`) is untouched, A41
   unchanged. A `v_document_signals` view unions canonical + extended for one queryable surface.
3. **W3 embed unification (the one concrete fix worth doing first).** Single canonical flag =
   `corpus_backfill_state.embedded` (gate already reads it); make the Mac embedder set it when it writes
   `rag_local` → removes the 1492-vs-1489 divergence, prevents future drift.

**Design-only, HELD for approval (external-facing / not blocking connectivity):** `DocumentFiling`
(doc_id · front leo|gdrive · canonical_path/url · filed_name · checksum · status), `FilingRule` (naming +
folder convention, e.g. `<matter>/<doc_type>/<YYYY-MM-DD>_<title>_<docid>`), `DocumentInventory` (a view over
`documents` + filing + `drive_file_id` showing per-doc presence across digital/Drive/leo + a sync sentinel).
leo.hayuma.org is client-facing (see the "no external exposure until ready" rule); filing writes/renames are
outward + hard to reverse → design now, switch held.

**Safety:** all additive (new tables, no `documents` `ALTER`, no gate change); shadow-first; A41/A42/A43 + V8
untouched (gate reads the same canonical sources); rollback = DROP the new tables (nothing depends on them
until a separate, approval-gated flip). **Explicitly NOT proposed:** migrating the 5 gate signals into an EAV
table (query cost + migration risk, no near-term payoff). Least-moves; the Aug-12/provenance path stays primary.

---
*Prepared 2026-07-06. Companion: `case_work/Paracale-001/CORPUS_TRACKER.md`, `case_work/OCR_WORKLIST.md`. This is a technical pipeline runbook — not a strategic plan (see MASTER_PLAN.md for direction).*
