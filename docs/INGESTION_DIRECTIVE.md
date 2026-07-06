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

## STAGE 1 — THE OCR LADDER (hardcoded; escalate only as needed)
1. **DocAI** (bulk, creditless) — the default engine. Proven good on the FB batch.
2. **Quality gate** (`scripts/ocr_quality.py`): if text is thin / garbled / low-score → escalate.
3. **Preprocess** (`scripts/ocr_preprocess.py --variants gray,blue,bw --dpi 450`):
   - `blue` = blue-channel isolation → for "UNOFFICIAL COPY IF NOT IN BLUE COLOR" security-ink titles/CTCs
   - `gray` = grayscale + autocontrast + unsharp → for **faded old typescript** (the winning variant on the 1992 Partition)
   - `bw` = adaptive threshold → Tesseract baseline
4. **Frontier-vision read (agent-in-loop, no key):** read the enhanced image; for a hard region, **crop + magnify** it (the royalty column only became legible cropped & 3× upscaled).
5. **RECONCILE against the document's own internal totals/structure.** This is the step that *beat the raw VLMs*: on the faded royalty %s, Qwen returned 106% and Gemini 101% because they guessed glyphs in isolation; preprocess + magnify + **reconcile-to-100%** produced the self-consistent read. Always sanity-check extracted numbers against a stated total.
6. **Physical original / macro phone photo** — ONLY for a court-certified digit that remains ribbon-broken after all the above.

**NEVER:** quote a fabricated/unreconciled digit in a filing · self-host a 72B VLM (empirically *worse* — confident hallucination without self-check — and won't run on the 32GB Mac) · rely on Gemini free-tier as a primary (chronic 429) · trust Drive's OCR for *existence* (it missed the 1985 Undertaking entirely).

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
