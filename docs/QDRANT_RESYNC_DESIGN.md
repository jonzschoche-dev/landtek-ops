# Qdrant Re-Sync & Embedder Unification — DESIGN DRAFT (shadow-first; pending review)

> **STATUS: DRAFT — design only, NO execution, NO production writes to Qdrant.** For review against ontology
> alignment, safety, and minimum-effective-moves before any build. Approved direction (Option A, adjusted):
> re-sync the EXISTING `landtek_documents` from the Postgres system-of-record; unify the embedder to the local
> `bge-small-en-v1.5` (384d); keep `rag_local`/pgvector as the offline fallback. Postgres stays SoR.

## 0. Parity findings (grounded 2026-07-08) — why this is a rebuild, not a patch
| Metric | Value |
|---|---|
| Qdrant `landtek_documents` | 2,355 chunks · 1,489 docs · **768d** · frozen **2026-05-10** |
| Postgres embeddable (text ≥50) | 1,492 docs |
| Missing from Qdrant / Extra | **3** / 0 (coverage is near-complete) |
| Chunks with empty `case_file` | **1,428** (60%) |
| Docs with **stale** `case_file` / `document_type` payload | **1,073** / **893** |
| Paracale-71 classified: in Qdrant / correct `document_type` | 71 / **0** |
| Re-OCR'd docs with **stale vectors** | **31** |

The vectors are 768d (Gemini) but we're unifying to 384d (local) — **Qdrant vector size is immutable per
collection**, so unification *requires a new collection*. Combined with 72% stale payload + 31 stale vectors,
the least-moves path is a **clean blue-green rebuild** from Postgres, not incremental patching.

## 1. Target architecture (roles, unchanged from the approved decision)
- **Postgres** — system of record + governance (A41–A43, client isolation). Untouched by this work.
- **Qdrant `landtek_documents_v2`** (NEW, 384d) — primary rich-payload, matter-filtered retrieval.
- **`rag_local`/pgvector** (384d, local) — offline fallback / graceful degradation. Kept as-is (no metadata).
- **One embedder** — local `bge-small-en-v1.5` (384d), identical to `rag_local` → the two stores hold the
  SAME vectors (Qdrant adds payload). $0, offline-sovereign, removes the Gemini-403 dependency that froze it.

## 2. Payload mapping (project from Postgres → Qdrant payload)
Per chunk, keyed to its doc. Fields sourced from the GOVERNED tables (not the weak `case_file` alone):
| Payload field | Source | Note |
|---|---|---|
| `doc_id_postgres` | `documents.id` | stable key |
| `chunk_index`,`total_chunks` | chunker | |
| `case_file` | `documents.case_file` | coarse label |
| **`matter_codes`** (array) | `document_matter_links.matter_code` | **fine-grained; the isolation filter (A5)** |
| `document_type` | `documents.document_type` | now current (incl. the 71 Paracale) |
| `doc_role` | `documents.doc_role` | intrinsic role |
| `document_date` | `documents.doc_date`/best date | for time filters |
| `parties`,`reference_numbers` | `matter_facts` (typed) | optional enrich; skip if absent |
| `has_provenance` | `documents.model_used IS NOT NULL` | lets retrieval prefer connected docs (NOT a gate write) |
| `text` | chunk text | for display/snippet |
| `synced_at` | run timestamp | currency marker (replaces the frozen `ingested_at`) |

**Isolation rule (A5):** matter-scoped retrieval filters on `matter_codes` (fine) — a query for one client's
matter can never surface another client's chunk. `case_file` alone is too coarse to isolate `PAR-*` sub-matters.

## 3. Idempotent upsert strategy
- **Point id** = `uuid5(NS, f"{doc_id}-{chunk_index}")` (deterministic — re-runs overwrite, never duplicate;
  same pattern as `corpus_backfill`).
- **Per-doc delete-then-insert:** before upserting a doc's chunks, delete all points with
  `payload.doc_id_postgres == doc_id` — so a re-OCR'd doc with a different chunk count leaves no orphan stale
  chunks. Makes the sync safe to re-run and self-healing.
- **Incremental mode:** a `qdrant_sync_state(doc_id, text_hash, synced_at)` marker (or reuse `content_hash`);
  a doc re-syncs only if its `text_hash` or payload changed → cheap steady-state, full-rebuild on first run.

## 4. The 1,428 empty-`case_file` chunks & the 22 no-text docs
- **Empty/stale payload → solved by the rebuild itself.** Every point is freshly projected from current
  Postgres, so `case_file`/`document_type`/`matter_codes` are correct by construction. No separate backfill.
- **22 no-text Paracale docs:** excluded (nothing to embed). The sync query filters `text ≥ 50`, so they are
  picked up automatically, incrementally, once OCR gives them text (the Gemini-gated pilot). No special case.

## 5. Embedder unification plan
- Runs **on the Mac** (fastembed `bge-small-en-v1.5` — the 1GB VPS can't hold the model, same constraint as
  `rag_local`). Reads doc text + payload fields from Postgres over the proven `ssh + docker-exec` channel;
  embeds locally (384d); upserts to Qdrant (external URL, reachable from Mac) with payload.
- **Vector parity with `rag_local`:** same model → identical vectors, so the two stores stay consistent;
  `rag_local` becomes a true pgvector mirror of Qdrant's vectors (minus payload). Reuse `rag_embed_local`'s
  chunker + model loader (single-source the chunking so both stores chunk identically).
- New collection created with `size=384, distance=Cosine`, HNSW + **payload indexes** on `matter_codes`,
  `case_file`, `document_type` (fast filtering).

## 6. Rollback / degradation (blue-green)
- **Build isolated:** `landtek_documents_v2` is built alongside the live `landtek_documents`; production reads
  are unaffected during the build (no in-place mutation). Abort = drop `_v2`, zero impact.
- **Cutover by alias:** point the retrieval alias/config from `landtek_documents` → `_v2` only after gates pass.
- **Instant rollback:** swap the alias back to the old 768d collection (retained ≥1 review cycle). Because the
  old collection is never mutated, rollback is a config flip.
- **Graceful degradation:** Qdrant is EXTERNAL → if unreachable, retrieval falls back to `rag_local`/pgvector
  (local, offline-sovereign). *Design requirement:* the retrieval client implements Qdrant→pgvector fallback
  (offline_audit must still pass — the stack reasons unplugged).
- **Pause switch:** a `STOP_QDRANT_SYNC` sentinel file (mirror of `STOP_STAMP`) halts the sync mid-run.

## 7. Go / no-go gates (ALL green before cutover; nothing before review)
1. This design reviewed + approved.
2. `_v2` point count ≈ expected (1,492 embeddable docs; ±the 3 currently-missing).
3. **Payload spot-check:** `case_file`/`document_type`/`matter_codes` correct on a sample incl. the 71 Paracale.
4. **Isolation test:** a `matter_codes='PAR-*'`-filtered query returns ONLY Paracale chunks — zero cross-client leak (A5).
5. Vector sanity: 384d cosine; a known query returns sensible neighbours; parity vs `rag_local` on a sample.
6. Offline-fallback verified: with Qdrant blocked, retrieval still answers from pgvector.
Only then: alias cutover. Old collection retained for rollback.

## 8. Ontology / safety alignment
- **A41–A43 untouched.** Qdrant is a *retrieval index*, not a connectivity-signal source — the gate reads
  `corpus_backfill_state.embedded`, not Qdrant. The sync writes NO `model_used`, stamps NO provenance, touches
  NO gate signal. V8 unaffected.
- **A5 client isolation** is *strengthened* — matter-filtered retrieval via `matter_codes` payload.
- **Offline-sovereignty** preserved — local embedder + pgvector fallback; Qdrant is a performance edge, not the spine.
- **Reversible / additive** — new collection, no mutation of the old, no Postgres schema change, no `documents ALTER`.

## 9. Proposed build sequence (post-approval, shadow→pilot→cutover)
1. `qdrant_sync.py` (Mac) — `--dry` (project payload + count, no writes) → review the projected payload.
2. `--build v2 --limit 50` — small pilot into `_v2`; run gates 3–5 on the pilot.
3. `--build v2` full → gates → **hold for cutover approval**.
4. Cutover (alias) → monitor → drop old collection after the rollback window.

*Prepared 2026-07-08 (ingestion agent). Companion: `docs/INGESTION_DIRECTIVE.md`, `MASTER_PLAN §6B`, `docs/DOCUMENT_MODEL_DRAFT.md` (§2.17). Parity script archived in session scratch.*
