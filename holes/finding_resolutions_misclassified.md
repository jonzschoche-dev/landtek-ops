# Finding: 21 resolutions tied to misclassified source docs

After deploy_243 (resolution-matter regex backfill), 4 resolutions linked cleanly
to `MWK-CV6839`. The remaining 21 are blocked by upstream doc-classification
problems, not by gaps in the regex.

## Breakdown of the 21

| Bucket | Source docs | Pattern |
|---|---|---|
| Inocalla family civil cases (RTC Manila Branches 15/16) | 630, 643, 653, 522, 511, 516, 650, 502, 503, 504, 501, 534 | Paracale-001 or no case_file. UNRELATED to MWK; some live under Paracale-001 by accident. |
| ~~Torralba & Juntilla v. Daet RTC (CA petitions)~~ | ~~581, 582, 583, 585~~ | **CORRECTION 2026-05-21 (Jonathan): these ARE Balane-family litigation** — Princess Balane Torralba (entity #2391, 25 mentions) is the hub. Re-tagged to MWK-CV26360 in deploy_251. Doc 513 separated out as legitimately Inocalla. See `memory/feedback_torralba_balane_linkage.md`. |
| Sanggunian Bayan Resolution 26-96 (1996 MWK estate donation) | 577, 389, 534 | tagged MWK-001 correctly; is MWK-relevant but does not name a specific matter_code. Belongs to MWK-CORP or MWK-ESTATE if we add one. |
| SC NOTICES (generic) | 508, 504, 502, 503, 501 | no case_file. Need doc-classification pass to determine which matter each notice is from. |

## Required follow-ups

1. **deploy_244 (LLM doc classification)** — should propose:
   - Reclassify Inocalla docs into a Paracale matter once Paracale matters
     are registered (or delete if pure precedent).
   - Reclassify Torralba docs OUT of MWK-001 (they're unrelated CA precedent).
   - Either create `MWK-ESTATE` matter and link the 1996 Sanggunian resolution,
     or accept that some resolutions are estate-broad and not matter-scoped.

2. **Schema option (deferred)**: add `resolutions.scope` enum
   {`matter_specific`, `client_broad`, `unrelated`} so the chronicle can
   distinguish "ARTA ruling on MWK-ARTA-0001" from "1996 Sanggunian estate
   resolution affecting MWK broadly".

## Truth-discipline note

None of these 21 should be presented as MWK matter resolutions in legal output.
The chronicle and lookup pipelines currently filter by `affected_matter_codes`,
so they're already excluded from per-matter views. They appear only in
`show_client.py`'s headline count (`resolutions tracked: 6` for MWK after
deploy_243) which now reflects truth.

Recorded: 2026-05-21

## Post-245 adjudicator-coverage state

Adjudicator FK coverage: 1/27 resolutions after deploy_245.

| Resolution | adjudicator_name_raw | status |
|---|---|---|
| r#16 | "Gay Belen / Attorneys" | resolved → entity #4079 (Atty. Elaine Gay R. Belen) |
| r#3, r#14 | (none) | ARTA docs; tail-regex for Director sign-off failed — needs LLM extraction |
| r#17 | "Jaime Resoco" | not in entities; held pending source-grounding (no stub creation) |
| r#18, r#23 | (none) | Flagged: misclassified Yuzon legal memos |
| r#6, r#13, r#26, r#27 | "Jose Teodorico", "Karlo M. Dialogo", "Maria Eleanor" | held — depends on matter-linkage from deploy_244 batch first |

The deploy_244 LLM batch may surface that r#6/r#13/r#26/r#27 belong to other clients
(probably Inocalla family civil cases under Paracale-001). Once their matter scope is clarified,
a follow-up adjudicator-id pass can run.

---

## 2026-05-21 update — manual audit cascade fix

After Jonathan's "Torralba are linked to Balane" correction (deploy_251), I audited
the 72 surviving `flag_unrelated` proposals and found 9 more confirmed misses
where the LLM said unrelated at ≥0.85 confidence but the doc was actually MWK
litigation. Pattern: all had `doc_entities` empty (entity extraction never ran).

Built two-layer platform fix:
- **deploy_252** — entity-graph guard for proposals with doc_entities populated
- **deploy_253** — text-level fallback (case_file priority + extracted_text surname grep)
- **deploy_254** — manual assignment for the 9 confirmed misses
- **6 transferee keystones populated** in `case_theories/_clients.py`
  (alberto_victa #856, ananias_apor #859, rosalina_hansol #3411, roscoe_leano #1209,
   ruben_ocan #4474, severino_tenorio_jr #1554 — were all None previously)
- **regression test pinned** in `truth_tests/test_audit_closure.py`

Platform reliability lesson (now encoded in `memory/feedback_torralba_balane_linkage.md`):
> **High LLM confidence ≠ accuracy.** A 0.95-confidence flag_unrelated verdict from
> the model was wrong for ~13/72 (18%) of cases. The fix is structural — cross-check
> against the entity graph + extracted_text BEFORE accepting the verdict.
