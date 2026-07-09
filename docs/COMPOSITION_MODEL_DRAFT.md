# Composition & Continuity Model — DESIGN DRAFT (2026-07-09 · pending review · nothing built)

> Design-only, for review before implementation (mirrors DOCUMENT_MODEL_DRAFT / QDRANT_RESYNC cadence). Goal:
> emailed filings + their threads + annexes-in-bundles become **findable, connected, and continuity-preserving**,
> by EXTENDING what already exists — not inventing parallel structures. Companion: `docs/DOCUMENT_MODEL_DRAFT.md`
> (ontology §2.17), `docs/LEGAL_FINDABILITY_COMPLETENESS_DIRECTIVE.md` (Priority 3), `docs/INGESTION_DIRECTIVE.md`.

## 0. What already exists (grounded 2026-07-09) — build ON this
| Layer | Table(s) | State |
|---|---|---|
| Curated narrative threads | `case_threads` (5, `thread_scope_sql`-driven) + `case_thread_documents` (211, role) | LIVE, auto-relinked |
| Correspondence timeline | `correspondence_events` (19: author/addressee/claimed vs received dates/delivery proof) | LIVE |
| Email↔doc linkage | `email_documents` (829: message_id·doc_id·role·filename) + `correspondence_links` (698, confidence) | LIVE (blend_emails / correspondence_matcher) |
| Email store | `gmail_messages` (778, +`account`, +`document_id` 1:1) | LIVE |
| Cleanup done | dropped 9 dead scaffolding tables (chat_hub ×6, conversation_context, instance_ai_threads/messages) | ✅ |

## 1. The four gaps (all the continuity problem reduces to these)
1. **Email BODIES are not corpus documents** — ~0 of 778 bodies are `documents`, so the cover email ("here's the
   Resolution — note the 15-day deadline") is unembedded/unfindable and can't be scoped into a thread.
2. **Two email→doc linkers** — legacy `email_documents` (many-to-many, role+filename) vs my newer
   `gmail_messages.document_id` (1:1). Redundant; must pick one canonical before extending.
3. **No sub-document part model** — a 13-page bundle is one row; "Annex A = pp.9–11 of bundle X" is unaddressable.
4. **No exhibit ordering/lettering** — `case_thread_documents` has `role` but no exhibit_label / order_seq / page span.

## 2. The design (ADDITIVE · shadow-first · A5-inherited · no `documents` ALTER)

**2.1 Reconcile the linker → `email_documents` is canonical.** It's the correct shape (an email has *many*
attachments, each a doc with a role). Deprecate `gmail_messages.document_id` to a denormalized cache; have
`extract_email_attachments.py` write `email_documents(message_id, doc_id, role='attachment', filename)` instead of
only the 1:1 column. Backfill the 420 existing links. One spine.

**2.2 Email body → a first-class document** (closes gap 1, the continuity core). For **case-relevant** emails
(case_file set — targeted, no personal-email flood), create a `documents` row: `document_type='Email'`,
`extracted_text = body_plain` (already text → skips OCR, straight to embed → findable), `ingest_source='gmail_body'`,
`case_file`/`matter_code` **inherited** (respecting the keyword-quality guards). Link via `email_documents(role='body')`.
Now body + attachments are siblings under one email, both searchable.

**2.3 Email-thread continuity = a retrieval VIEW, not a new table.** `gmail_messages.thread_id` already groups an
email conversation. A view `v_thread_continuity(doc_id → thread_id → sibling docs in time order)` lets retrieval,
from any attachment or body, surface *the whole thread* (narrative + exhibits, chronological). No schema — just the
join spine made first-class. (Distinct from `case_threads`, which are *curated litigation narratives*; a gmail thread
is the *raw conversation*. Both point at the same docs.)

**2.4 `document_parts` (NEW table) — sub-document page ranges** (closes gap 3): `document_parts(doc_id, part_index,
page_start, page_end, kind, label)`. Lets "Annex A = pp.9–11 of doc X" be a citable unit. Additive; populated later
(strip from bundle TOCs / manual). This is the ontology DOCUMENT_MODEL_DRAFT's `document_parts` — same concept, so
graduate it there.

**2.5 Exhibit composition — extend `case_thread_documents`** (closes gap 4): add `exhibit_label` (A, B, …),
`order_seq`, `part_id` (nullable → `document_parts` for a page-range exhibit). A "filing" = a `case_thread` whose
documents carry ordered exhibit labels. `case_bundle.py` then reads this to emit the normalized/stamped bound PDF
(Priority 4). Extends the existing table, no new `filing_exhibits` needed.

## 3. Client separation (A5) — enforced
Email-body-docs inherit `case_file`/`matter_code` from the correlated email; a document's matter = its **content**,
never an incidental mention ([[feedback-client-separation-place-keyword-leak]]); multi-client thread → the body-doc is
flagged, not auto-dual-assigned. The keyword-quality truth_tests (bare-geo + over-broad) gate the correlation feeding it.

## 4. Rollout (shadow → pilot → enable), each with `--dry`
1. **Linker reconcile** (2.1) — backfill `email_documents` from `gmail_messages.document_id`; verify parity; then flip
   `extract_email_attachments` to write it. Low-risk, reversible.
2. **Email-body ingest** (2.2) — `--dry` count + sample on case-relevant emails; then create the body-docs; they flow
   into the running OCR-skip→embed pipeline. Gate: A5 spot-check + truth_tests green.
3. **`v_thread_continuity` view** (2.3) — read-only; validate a doc→thread lookup (e.g. doc 1614 → its cover email).
4. **`document_parts` + exhibit fields** (2.4/2.5) — schema add (shadow, empty), then populate incrementally.

## 5. Safety / ontology alignment
Additive (new table `document_parts`, new columns on `case_thread_documents`, new `documents` rows, one view); no
`documents ALTER`; A41–A43 untouched (bodies are ordinary docs that flow the gate); rollback = drop the additions.
Reconcile with ontology `DOCUMENT_MODEL_DRAFT.md`: `document_parts` graduates there; `DocumentFiling` (storage location)
stays distinct from this (exhibit composition) — they are different axes. **Report for review before building.**

*Prepared 2026-07-09 (ingestion agent). Grounded in live tables; 9 dead scaffolding tables dropped this session.*
