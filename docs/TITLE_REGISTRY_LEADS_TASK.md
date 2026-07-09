# TASK: Title-Registry Leads → Registry (standing procedure)

**Owner**: Ingestion agent · **Cadence**: after any reenrich run that surfaces new `unknown_titles` · **Status**: Active
**Origin**: deploy_812 surfaced the lead class; deploy_813 processed the first 11 (incl. **079-2021002126**, Balane's
actual contested title, previously ABSENT while Hoppe's …2127 was present — proof this pipeline finds real gaps).

## The loop (each lead earns its way in — never bulk-insert)
1. **Surface** — `SELECT lead, count(*) FROM documents, jsonb_array_elements_text(analyst_memo->'ingest_signals'->'unknown_titles') lead GROUP BY 1 ORDER BY 2 DESC;`
2. **Verify by excerpt** — pull the surrounding text from the strongest citing doc. The excerpt must read as a real
   title reference (issuer language, ledger row, annotation, caption). **OCR garble ≠ evidence → stays a lead.**
3. **Earn provenance** — insert with `source_doc_id` + verbatim excerpt in `provenance_notes`:
   - `verified` ONLY when the excerpt is a direct quoted statement of the title's existence/status (the …2126 bar).
   - `inferred_strong` for clean mechanical extraction from a grounded doc (the usual tier).
   - Set `case_file` to the title's OWN client (T-1722 → Paracale-001) — the engine scopes per-row since v4.
4. **Never fabricate relationships** — registry row only. NO `title_chain` edges, NO `parent_title`, NO
   `cancelled_by_title` unless the citing excerpt itself states it (doc 388 stated T-52540→…2126; that's the bar).
5. **Propagate** — `python3 scripts/reenrich.py --force --limit 2500 --quiet` (registry-only changes don't trip the
   text_hash gate; --force exists for exactly this). Confirm the lead moved unknown→title_hits.

## Current remaining leads (post-deploy_813)
| Lead | Docs | State |
|---|---|---|
| T-52416 | 5 | SKIPPED — doc 358 excerpt is form garble ("umber of Copies 0"); needs a better citing doc or the face |
| T-53602 | 5 | SKIPPED — no clean excerpt found; re-check after the OCR drain improves its citing docs |
| ~136-doc tail | various | lower-count leads; re-surface with the query above after each OCR/ingest wave |

## Guardrails (non-negotiable)
- A5: a lead cited only by another client's docs belongs to THAT client's case_file — check before insert.
- Separation rules stand: San Vicente/Cabanbanan (T-4494 group) and T-30683 are NOT T-4497 derivatives — registry
  entries carry the separation note, never a chain edge.
- MMK ≠ MWK; …2126 (Balane) ≠ …2127 (Hoppe).
- After insert, the truth_tests + `ontology_check.py` must stay green.
