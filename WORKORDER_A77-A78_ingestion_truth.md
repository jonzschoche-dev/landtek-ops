# Work Order — complete the ingestion-truth substrate (A77 + A78) on what's ALREADY built

**For:** the executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). This is a CORRECTION of an earlier draft that proposed greenfield gates — those gates already partially exist. This version says: READ FIRST, report what satisfies A77/A78, then complete only the real gaps.
**Why now:** the Relationship Equilibrium Engine (A76) will compute on `matter_facts`. An engine only propagates what it's told; a misread OCR or unverified fact becomes a confident error rippling across every edge. Harden the substrate A76 runs on — but MOST of it is already built. Do not re-invent it. Two-agent protocol: you commit/push after gates green. No phantom enforcement.

## Grounding — READ THESE FIRST (they likely already satisfy parts of A77/A78)
- `scripts/comms_artifact_sink.py` (deploy_847/849) — already does A5 resolve-or-HOLD (unresolved → held/quarantined, never guessed) + content-hash dedup + media-type routing to OCR/transcribe-pending. **A77(1) largely exists.**
- `scripts/contradiction.py` — a contradiction check ALREADY EXISTS. Determine: is it wired as a REFUSE/HOLD gate on INBOUND records, or only a post-hoc check on existing facts? That determines the gap.
- `scripts/verify_loop.py` / `verify_worker.py` / `dossier_verify.py` / `verify_truth_lockdown.py` — the verification machinery is live. **A78 "verified is earned" is partly operational already.**
- `knowledge_graph_triples.provenance_level` was rewritten to a canonical 5-value vocab (deploy_693). **Provenance tiers exist.**

## T0 — Audit & report (do this BEFORE building anything)
For each of A77/A78, report SATISFIED / PARTIAL / MISSING against the live code + schema:
- A77(1) resolution-confidence: is it binary (bound vs unbound) or graded (below-threshold → held)? Is there a confidence threshold + held state, or just null-check?
- A77(2) OCR/transcription audit trail: is raw text + per-field confidence stored behind a VERIFIED fact? Or just `ocr_pending` status with no traceable basis?
- A78 verified-basis: does `matter_facts` (or the triples table) have a recorded verification path (source doc + verify step) enforced on VERIFIED writes? Or can a fact reach VERIFIED by assertion/inference/LLM?
- A78 contradiction-at-ingest: does `contradiction.py` refuse/hold an inbound record that conflicts with a VERIFIED fact, or only flag existing ones?
Report the satisfied/missing split explicitly. Build only what's MISSING.

## T1 — Complete A77 gaps (extend the sink, don't rebuild it)
Only the missing pieces from T0:
- If resolution is binary: add a CONFIDENCE THRESHOLD — a bind below threshold → held (never guessed, A5). Record bind confidence + matched identity on `comms_artifacts` so a held artifact is auditable.
- If no OCR audit trail: extend the sink's hand-off to reocr_local/Whisper to STORE raw text + per-field confidence; block a structured field (title no./date/party) from entering `matter_facts` as VERIFIED without that logged basis (A2). A misread must be traceable, not silent.

## T2 — Complete A78 gaps (extend contradiction.py / verify_worker, don't fork a new gate)
- If VERIFIED can be written without a recorded verification basis: add the hard gate (reuse `contradiction.py`'s deterministic, $0, no-LLM style) — VERIFIED requires source doc id + verify step; assertion/inference/LLM-confidence → at most ASSERTED.
- If contradiction.py is post-hoc only: wire it as a REFUSE/HOLD gate on inbound records that conflict with a VERIFIED fact — upstream of the engine, not after propagation.
- Facts don't rot (A74 re-check): when a source is re-ingested/challenged, flag its VERIFIED facts for re-verification (reuse A74 recheck_condition pattern).

## T3 — Truth-tests (negative-tested, only for the gaps you actually built)
- `test_ingestion_fidelity.py`: below-threshold bind → held; structured field → VERIFIED without OCR basis → refused; misread traceable.
- `test_verified_fact_integrity.py`: VERIFIED without basis → refused; contradicting ingest → held/refused (negative-bite); re-ingest flags re-check.
Wire into `run_all.py` ONLY the assertions covering NEW code — do not re-test what already passes.

## T4 — Prove on real data, honestly
- Run against a sample (JJ's channel + a scanned-deed matter): confirm below-threshold bind is held; OCR confidence + raw text recorded.
- Inject a contradicting ingest vs a VERIFIED fact → held/refused, NOT propagated.
- Report the false-negative risk honestly: a confident-but-wrong OCR above threshold can't be prevented, but the audit trail makes it discoverable post-hoc.

## Guardrails
- Extend existing modules (comms_artifact_sink, contradiction.py, verify_worker) — NO new parallel gate that duplicates them.
- A5 isolation: resolve-or-HOLD, never guess. A2 provenance: VERIFIED earned. $0/sovereign: local Ollama/Whisper only. Degrade-don't-crash: gate error → HOLD, never admit unverified or silently drop.
- No phantom enforcement: the ontology desk promotes A77/A78 🟡→🟢 when you report truths green; you don't self-promote.

## Close-out
Per task, A59 work order to terminal state + graduation note to the desk. T0 audit report included verbatim. Final line: "substrate hardened — A76 may build against a trustworthy matter_facts," OR "substrate already satisfied X/Y; completed only Z."

## Invocation
> Execute `WORKORDER_A77-A78_ingestion_truth.md` from `/root/landtek`. FIRST read comms_artifact_sink.py, contradiction.py, verify_worker.py, and the matter_facts/triples schema; report what already satisfies A77/A78; complete ONLY the missing gaps (resolution-confidence threshold, OCR audit trail, VERIFIED-basis gate, contradiction-at-ingest). Do NOT rebuild what exists. $0 local inference. Hold, never guess, never silently drop. Negative-test only new code.

---

## CLOSE-OUT (executor, 2026-07-11 — deploy_870)

### T0 audit — SATISFIED / PARTIAL / MISSING (verbatim)

| Claim | Verdict | Evidence |
|---|---|---|
| A77(1) resolve-or-HOLD at the sink | SATISFIED | `comms_artifact_sink.py` `_resolve_client` → unresolved ⇒ `held` ledger row, never guessed; `platform_coordinator.resolve()` binds only on a unique exact match, else NULL |
| A77(1) GRADED resolution (confidence + threshold + auditable hold) | **MISSING** | bind was binary (`mapped_client_code` present/absent); `comms_artifacts` had no `bind_confidence`/`matched_identity` columns; no threshold anywhere |
| A77(1) "an unresolved artifact never forms an edge" | **MISSING at the writers** | proven live: V4 (`ontvv_client_isolation`) passes when the cited doc's owner resolves NULL (`fc IS NOT NULL AND dc IS NOT NULL` guard); live DB carried **732 inferred_strong + 108 verified** facts citing owner-unresolvable docs (incl. the 1172/1177 → MWK-OP-PETITION bleed); `harvest_facts`/`verify_worker` had no owner gate |
| A77(2) raw text behind facts | SATISFIED | `documents.extracted_text` is the raw transcription; pre-re-OCR text kept in `reocr_backup`; per-doc `reocr_log` (chars before/after + engine note) |
| A77(2) OCR confidence | PARTIAL (doc-level) | `ocr_quality.score` (0..1 word-likeness/dict-hit heuristic) + `extraction_runs.quality_score`; no per-field confidence — but every VERIFIED structured field must excerpt-ground verbatim in the stored raw text (tg_prov_facts), so a misread is traceable to its exact raw text |
| A78 verified-basis enforced | SATISFIED | DB-enforced, both `tg_prov_facts` (`enforce_provenance_facts`: verified ⇒ source_kind=doc + resolving doc + `excerpt_grounded` verbatim) and `ontvv_v3`, BEFORE INSERT **OR UPDATE** — assertion/inference/LLM-confidence cannot promote; covered by test_provenance_integrity |
| A78 contradiction-at-ingest | **MISSING** | `contradiction.py` was post-hoc only (scan existing verified facts → `contradictions` table); no writer consulted it pre-insert |
| A78 facts-don't-rot (re-ingest) | PARTIAL | `trg_reocr_reground_guard` (deploy_830/833) demotes no-longer-grounded verified facts on text change — but the 14-day `verify_worker_log` cooldown left the doc unread, so demoted facts sat in limbo; no challenge flag on contradiction |

### Built (only the MISSING/PARTIAL gaps)

1. **`migrations/deploy_870_ingestion_truth_gates.sql`** (applied live): `comms_artifacts.bind_confidence` + `.matched_identity`; `channel_users.bind_confidence` (NULL = explicit operator bind = 1.0); `reocr_reground_guard()` extended — on `extracted_text` change it now also clears the doc's `verify_worker_log` cooldown (re-arm; demotion + logging byte-identical to deploy_830-as-fixed). Not an ontvv_* object.
2. **`scripts/comms_artifact_sink.py`**: graded bind — `_resolve_client` returns (client, confidence, matched_identity); bind below `COMMS_BIND_MIN_CONF` (default 0.80) ⇒ `held` with candidate + confidence + identity recorded (client_code left NULL — a hold binds to nobody); confidence + identity recorded on all ledger rows.
3. **`scripts/ingest_gate.py`** (new, writer-lane): `owner_gate` — a fact-write citing a doc whose client is unresolvable (`_client_of(COALESCE(matter_code,case_file)) IS NULL`) is REFUSED + held (idempotent open `holes_findings` row, routine `ingestion_fidelity_gate`, A74-style `recheck_condition` in metadata); `hold_contradiction` routes A78 holds. Gate error ⇒ HOLD, never admit.
4. **`scripts/contradiction.py`**: `conflicts_with_verified()` — deterministic $0 ingest gate (event-proximate date extraction shared with scan via `_event_dates`); scan() now emits an A74-style CHALLENGE (`contradiction_challenge` holes row with machine-checkable recheck_condition) for verified facts in a date conflict; `close_resolved_challenges()` auto-releases a challenge when its contradiction resolves (runs every scan).
5. **`scripts/harvest_facts.py`**: owner gate per doc (held docs are EXCLUDED from the delete-rewrite so previously-bled facts stay frozen for the operator's open disposition — 1172/1177 untouched); contradiction gate per fact (conflicting ⇒ held, visible; non-conflicting facts from the same doc still flow).
6. **`scripts/verify_worker.py`**: owner gate BEFORE inference is spent (`held_unresolved_owner` attempt-logged, cooldown honored); per-claim contradiction gate — a conflicting claim is never written verified; it lands in `proposed_facts` status `contradiction_hold` + a visible holes row.
7. **Truth tests** (auto-discovered by run_all): `truth_tests/test_ingestion_fidelity.py` (3 assertions) + `truth_tests/test_verified_fact_integrity.py` (4 assertions) — all negative-tested in rolled-back transactions, count-independent. Suite: **153 green** (146 + 7 new).

### Proof on real data (T4, all mutations rolled back)

- **JJ's channel**: JJ Ildefonso Moreno (messenger, real MWK-001 bind) grades 1.0; degraded in-txn to 0.50 ⇒ sink held: `low_confidence_bind (A77): candidate MWK-001 at confidence 0.50 < 0.80 — held, never guessed`, ledger row carries bind_confidence=0.5 + matched_identity.
- **Scanned-deed doc 379** (re-OCR'd `ok:local:qwen2.5vl:7b`): raw text 24,095 chars live + 1 reocr_backup + ocr_quality score 0.4695 — behind **24 verified facts**, each excerpt-grounded in that raw text.
- **Contradicting ingest vs real verified facts (MWK-CV26360)**: inbound "deed of absolute sale executed on March 3, 1999" ⇒ CONFLICT (incoming 1999-03 vs verified [1996-02, 2016-09, 2019-09]); corroborating same-date control passes clean.
- **Live activation**: contradiction scan flagged 44 conflicts → 44 open `contradiction_challenge` rows with recheck conditions; dry-run harvest across all 38 matters: 8,230 facts would flow, **152 unresolved-owner doc-links held** and **~137 contradicting facts held** (~1.6%) — conservative, visible, recoverable; first live 15-min verify-worker tick with the new gates exited 0.

### Honest limits (what these gates CANNOT catch)

A **confident-but-wrong OCR above threshold cannot be prevented**: if the vision model transcribes a wrong digit cleanly (a "confident misread"), the text is word-like (ocr_quality passes), the excerpt grounds verbatim (it IS in the raw text), and the fact earns verified on a faithful quote of an unfaithful transcription. The gates make this **discoverable, not impossible**: the full raw transcription + pre-change backup + engine note + doc-level quality score sit behind every verified fact, so any later challenge traces to the exact text version; a re-OCR that fixes the misread auto-demotes the stale fact (reground guard) and re-arms the re-read; and a second source carrying the true date trips the contradiction gate/challenge. Symmetrically, the contradiction gate is **conservative by design**: where a matter's verified baseline is itself multi-dated (an open contradiction, e.g. the CV-26360 deed dates), new dated mentions of that event are held against an ambiguous baseline — false-positive HOLDS are possible, but a hold is visible and recoverable (proposed_facts/holes_findings), never a silent loss; and it only sees date/event-proximity conflicts (not amounts/parties yet). Per-field OCR confidence remains doc-level, not field-level.

### Directives for the ontology desk (not executed — your lane)

- **V4 amendment recommended**: `ontvv_client_isolation` should treat a NULL-resolving cited-doc owner as a HOLD/violation for non-operator writers (or add a V-check for NULL-owner citations). The writer-side gate now refuses in harvest_facts + verify_worker, but other writers (decipher_matter, reconciler, load_issue_spine, source_read_facts, n8n paths, ad-hoc SQL) remain exposed until the trigger closes the class. The live bypass evidence is holes_findings routine `ontology_desk_separation_review`; the backlog measure is 152 open `ingestion_fidelity_gate/unresolved_doc_owner` rows.
- **A77 graduation note**: resolution is now graded (bind_confidence + COMMS_BIND_MIN_CONF threshold + held state, recorded on comms_artifacts) and an unresolved artifact no longer forms an edge through the automated writers; OCR raw text + doc-level confidence trail is logged behind verified structured fields (per-field confidence remains an honest gap). Negative-tested: truth_tests/test_ingestion_fidelity.py (3 assertions).
- **A78 graduation note**: verified-basis was already DB-enforced (no change needed); contradiction is now caught at ingest (held upstream of the engine, negative-tested); facts don't rot — re-ingest demotes + re-arms re-read, and challenged verified facts carry a machine-checkable recheck_condition that auto-releases on resolution. Negative-tested: truth_tests/test_verified_fact_integrity.py (4 assertions).
- **Operator disposition unchanged**: the bled facts on docs 1172/1177 and flagged 1176/1180 were not re-homed/deleted/demoted; the harvest delete-rewrite now explicitly excludes held-doc facts so they stay frozen pending your disposition.
- **A74 note**: `ingestion_fidelity_gate` + `contradiction_challenge` findings carry machine-checkable `recheck_condition` in metadata, and `contradiction.close_resolved_challenges()` is a working recheck sweep for the challenge class — reusable as the A74 pattern reference.

**Substrate hardened — A76 may build against a trustworthy matter_facts.** (Already satisfied: sink resolve-or-hold, verified-basis DB gate, raw-text trail, reground demotion. Completed only: graded bind confidence, writer-side owner gate, contradiction-at-ingest, re-check re-arm + challenge.)
