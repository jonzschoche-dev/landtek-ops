---
name: synthesis-must-cross-source-p0
description: Before any case-output synthesis, cross-search ALL data sources for parallel proceedings the named matter doesn't capture. Anchoring on a single matter_code without cross-search has caused production misses (guardianship blind-spot 2026-05-20)
metadata:
  type: feedback
---

**P0 — STRUCTURAL RULE. Before any case memo, client history, case breakdown, brief, or strategy output:**

Synthesis MUST run an explicit cross-source pre-flight that scans the following BEFORE generating output. Anchoring on a single `matter_code` from the `matters` table is INSUFFICIENT and has produced false outputs.

Required pre-flight scans (none optional):

1. `documents` — search `extracted_text`, `classification`, `document_title`, `smart_filename`, `original_filename` for matter-relevant keywords (counsel names, parties, court names, related proceedings — "petition", "brief", "complaint", "motion", "guardianship", "estate", etc.)
2. `chat_notes` from past 90 days — search `content` and `summary` for any fact (date, counsel, docket, party, court) that doesn't have a corresponding entity/document/matter row
3. `gmail_messages` — search `subject` and `body_plain` for the same patterns
4. `entities` — search `canonical_name`, `aliases`, `role`, `affiliation` for actors related to the case who aren't tagged with role/affiliation for THIS matter
5. `client_history` — search `what_summary` for events not yet tagged to a `matter_code`
6. `calendar_events` — search `title`, `description` for meetings/hearings about parallel proceedings
7. `case_deadlines` — search `title`, `description` for deadlines on parallel proceedings without matter rows
8. `drafts/` directory on disk — search for filenames suggesting alternative drafts, parallel briefs, related petitions

**If any scan turns up evidence of a proceeding, counsel, document, or fact NOT represented as a `matters` row → the matter is missing from the spine.** The output MUST either: (a) include that proceeding in the synthesis, OR (b) BLOCK output and surface a "missing matter candidate" inquiry for the operator to confirm before proceeding.

**Why this rule exists (concrete incident, 2026-05-20):**

When generating a case-strategy memo for `MWK-CV26360`, LEO anchored on the `matters` row and queried only its direct relationships (title_chain, instruments_on_title, transferees, etc.). The memo missed:

- The `MWK-GUARDIANSHIP` special proceeding (parallel case under Atty. Adan Botor)
- 9 documents about the guardianship petition (DOC 621, 622, 623, 686, 723, 725, 727, 751, 802)
- 10+ `chat_notes` entries from May 15-16 stating the guardianship is in progress
- A gmail subject "Guardianship_Documents_Combined" sent April 8
- Atty. Botor as a second counsel (separate from Atty. Barandon for CV-26360)
- The fact that the May 22 Naga meeting agenda is about guardianship, not CV-26360
- The Guardianship Brief due to Atty. Botor

Result: a memo to the founder that asserted SPA-based authority as the live mechanism when court-supervised guardianship was the actual procedural path. Founder verbatim: *"how does LEO miss this?"* — because the guardianship has no `matters` row, so the synthesis was structurally blind.

**How to apply (mechanical, not procedural):**

1. The `synthesis_preflight.py` function runs at the top of every case-output script.
2. It performs the 8 scans above.
3. It produces a "discovered facts" set vs the "facts already represented in matter X" set.
4. If the symmetric difference is non-empty, output is BLOCKED and the diff is enqueued as an ops `gap_alert` for review.
5. After review (matter rows created, links established), the generator is re-run with a `--preflight-cleared <token>` flag.
6. Bypass requires explicit `--skip-preflight` and logs the bypass to `synthesis_audit_log`.

**Standing implication:**

Every new chat-stated fact must result in at least one DB encoding (entity update, document tag, matter row, deadline, calendar event). The dispatcher's job is to surface that encoding ask back to the operator (see [[feedback_facts_in_chat_are_first_class]]).
