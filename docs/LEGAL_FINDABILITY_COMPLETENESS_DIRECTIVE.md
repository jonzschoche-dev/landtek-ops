# LEGAL_FINDABILITY_COMPLETENESS_DIRECTIVE.md

**Version**: 1.1 (status-reconciled to what actually shipped) · **Date**: 2026-07-09 · **Status**: Active
**Applies to**: Ingestion Agent + supporting agents · Companion: `docs/INGESTION_DIRECTIVE.md` (the runbook), `MASTER_PLAN.md`

> **⚠ STATUS RECONCILIATION (2026-07-09).** v1.0 listed Priorities 1 & 2 as "Not started." They are **DONE and
> operational** — corrected below. Do NOT rebuild `extract_email_attachments.py` (it exists at the repo root,
> was fixed, and produced the ARTA Resolution as doc 1614). The real next work is **Priority 3**.

## Objective
Make legal documents (emailed filings, resolutions, deeds, annexes) reliably findable and usable with minimal
manual intervention, while protecting client separation and data quality.

## Core Principle
**Finish and wire what already exists before building new architectural layers.** Prioritize work that directly
improves retrieval of real legal evidence.

## Prioritized Workstreams (current, reconciled)

| # | Workstream | Type | Status | Evidence / Next |
|---|---|---|---|---|
| 1 | Attachment → Document extractor | Finish/Wire | ✅ **DONE** | `extract_email_attachments.py` per-account fetch + `file_path` + `master_form`; `landtek-email-attachments.timer` (hourly). ARTA Resolution=doc 1614, Keesey SPA=1618/1619 (deploys 799–800) |
| 2 | Re-embed loop closure (de-garbled docs) | Finish/Wire | ✅ **DONE** | `rag_embed_local._restale()` evicts stale vectors of re-OCR'd docs; 41 refreshed (deploy_796) |
| 2b | OCR backlog drain | Finish/Wire | ✅ **DONE** | `reocr_local --sweep` (owned qwen2.5vl) + `landtek-reocr-local-sweep.timer` (20 min); crash guard (deploys 794–795) |
| 2c | Both-inbox ingestion | Finish/Wire | ✅ **DONE** | `gmail_watcher --account backup` (targeted) + `landtek-gmail-backup-sweep.timer` (3 h); the ARTA root cause (deploys 797–798) |
| 3 | `filing_exhibits` + `document_parts` | **New (architectural)** | 🔵 **Design only — START HERE** | The one genuinely-new spine: sub-document / page-range / exhibit-letter composition. `DocumentFiling` (held) is about storage location, NOT exhibit composition |
| 4 | Packaging (normalize 8.5×13 / stamp / bind) | Finish+Extend | 🟡 partial | `case_bundle.py` binds; add normalize/stamp + read/write a stored manifest |
| 5 | Preventive truth-tests & data guards | Ongoing | 🟢 substantially shipped | A41/A42/connectivity/incorporation + keyword-quality guards (bare-geo + over-broad, deploys 801/802) |

## Key Rules (Non-Negotiable)
- All work **shadow-first** and reversible; every script supports `--dry-run`/`--dry`.
- **Client separation (A5)** enforced in every component — inherit `case_file`/`matter_code`/`account` from parent
  records; a document's matter = **its content**, not an incidental mention in the carrier email; multi-client
  mention → **flag, never auto-dual-assign** (see [[feedback-client-separation-place-keyword-leak]]).
- Every time a bug class is fixed, add/strengthen a **truth_test** so it can't return silently.
- Do NOT start architectural work (#3) until 1–2 are operational — **they now are**, so #3 is unblocked.

## Immediate Next Task (Priority 3) — `filing_exhibits` + `document_parts`
The composition layer that was the one true architectural gap (annexes-in-bundles: "Annex A = pp.9–11 of PDF X").
Design first (shadow, additive, no `documents ALTER`): `filing_exhibits(filing_id, exhibit_label, doc_id, order_seq,
page_start, page_end)` + `document_parts(doc_id, part_index, page_start, page_end, kind)`; A5-inherited; `--dry-run`.
**Report the design for review before building** (mirror the DOCUMENT_MODEL_DRAFT / QDRANT_RESYNC review cadence).

## Governance
All changes pass existing truth_tests + any new ones. Report blockers/refinements back here. Keep changes minimal.
This directive is the findability/ingestion runbook companion to `docs/INGESTION_DIRECTIVE.md`; if the two drift,
consolidate rather than fork.
