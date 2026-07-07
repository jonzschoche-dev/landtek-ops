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
*Prepared 2026-07-06. Companion: `case_work/Paracale-001/CORPUS_TRACKER.md`, `case_work/OCR_WORKLIST.md`. This is a technical pipeline runbook — not a strategic plan (see MASTER_PLAN.md for direction).*
