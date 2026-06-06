# Holes routine B2 — Expected-Primary-Evidence audit (CC session)

You are running unattended on the LandTek VPS as a weekly hole-finding routine. Your job
is to identify, for each active matter, which PRIMARY documents we expect to have but
DON'T — and write those gaps as findings in the `holes_findings` table.

## What you have access to

- This repo at `/root/landtek` — read `CLAUDE.md` first if you haven't (SessionStart hook should have surfaced it).
- The LandTek Postgres (DSN already configured in env): tables `matters`, `documents`, `title_chain`, `transferees`, `doc_requirements_law`, `extraction_chunks`, `case_threads`.
- Anthropic API key in `/root/landtek/.env` (already loaded by the session).
- The `comms_send()` chokepoint in `comms.py` — do NOT use it; this is an internal audit, no comms.

## Background

LandTek represents Patricia Zschoche (MWK estate) + Allan Inocalla (Paracale) + others.
For each MATTER, the case theory determines which PRIMARY documents are load-bearing:

- **Accion reinvindicatoria over inherited title** (e.g. MWK-CV26360): needs death cert of decedent, SPA revocation instrument, certified true copies of mother + derivative titles, RD certifications of the title chain.
- **Estate administration**: needs death certs of all decedents, letters of administration, will (if any), inventory of estate.
- **ARTA admin complaint**: needs notarized complaint-affidavit, supporting affidavits, receipts of fee-overcollection if alleged.
- **Just-compensation suit** (e.g. Civil Case 6839): needs CARP coverage notice, NTP, just-compensation determination.

The set of expected primaries is matter-specific — your job is to reason about each.

## Your task

For each row in `matters WHERE status='active'`:

1. **Read the matter's current state**:
   ```sql
   SELECT matter_code, case_file, title, docket_number, current_stage, 
          next_event, next_deadline FROM matters WHERE matter_code = %s;
   ```
2. **Read what documents exist for this matter**:
   ```sql
   SELECT classification, execution_status, COUNT(*) as n, 
          ARRAY_AGG(DISTINCT smart_filename ORDER BY smart_filename LIMIT 5) as samples
     FROM documents WHERE case_file = %s
     GROUP BY classification, execution_status
     ORDER BY n DESC;
   ```
3. **Derive expected primaries** (use Sonnet judgment): given the matter type + stage, what PRIMARY documents (executed_notarized / executed_filed / government_issued, NOT drafts) should we expect?
4. **Compare**: which expected primaries are missing or only present as drafts?
5. **For each missing primary, INSERT a finding**:

```sql
INSERT INTO holes_findings (
    routine_name, routine_version, finding_id_hash,
    severity, hole_type, case_file, matter_code,
    description, suggested_fix, auto_remediable, metadata
) VALUES (
    'B2_expected_evidence', 'v1', 
    -- finding_id_hash: sha256(routine + matter_code + expected_doc_type)[:24]
    %s,
    'P2', 'evidence_gap', %s, %s,
    -- description: "Matter MWK-CV26360 missing expected primary: notarized 2005 SPA revocation instrument"
    %s,
    -- suggested_fix: where/how to acquire
    %s,
    false,
    %s::jsonb  -- metadata: {"expected_doc_type": "...", "case_stage": "..."}
);
```

Use the partial unique index — if the same gap already exists open, the INSERT will fail (gracefully). Catch and continue.

## Idempotency

`finding_id_hash` = sha256("B2_expected_evidence" + matter_code + expected_doc_type)[:24]. This way re-running won't duplicate. If a finding has been marked `remediated` or `dismissed` and the gap reappears, a fresh row will land.

## Cost discipline

- Use **Haiku 4.5** for the per-matter "what docs exist here" classification.
- Use **Sonnet 4.6** only for the per-matter "what should exist" derivation — that's the judgment-heavy part.
- Cap total session at ~150K input + ~30K output tokens. If you hit the cap, write a run record showing how many matters processed and exit cleanly.
- Run sequentially through matters, not in parallel.

## Exit criteria + run logging

When done (or capped), write ONE row to `holes_runs`:

```sql
INSERT INTO holes_runs (
    routine_name, routine_version, status, duration_ms,
    findings_count, p0_count, metadata
) VALUES (
    'B2_expected_evidence', 'v1', 
    'ok',  -- or 'degraded' if you hit cost cap, 'failed' if you errored
    %s, %s, 0,
    %s::jsonb  -- metadata: {"matters_processed": N, "total": M, "tokens_used_est": K}
);
```

Then exit. **Do not** send anything to Telegram — the daily `holes/digest.py` job will surface
your findings in the next Holes Report at 06:00 PHT.

## Common pitfalls to avoid

- **DON'T flag normal missing docs** — e.g., a pretrial-stage matter doesn't need trial transcripts yet. Match expected primaries to current_stage.
- **DON'T duplicate findings already known** — query first whether the same expected_doc_type for this matter is already open.
- **DON'T classify drafts as "present"** — `execution_status='draft_unsigned'` doesn't count as primary evidence.
- **DON'T touch documents on Drive or via the heightened_ocr queue** — read-only against the DB only.
- **DON'T invoke comms_send** — silent run, no Telegram.
- **DON'T speculate on legal theory** — if the matter's theory is unclear, emit an `info`-severity finding flagging the ambiguity instead of guessing.

## Start

Begin by reading `/root/landtek/CLAUDE.md` (if not already in context) and querying the active matters list. Then process each matter as described. Aim to finish in <30 min wall-clock.
