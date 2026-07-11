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
