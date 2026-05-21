# Finding: 21 resolutions tied to misclassified source docs

After deploy_243 (resolution-matter regex backfill), 4 resolutions linked cleanly
to `MWK-CV6839`. The remaining 21 are blocked by upstream doc-classification
problems, not by gaps in the regex.

## Breakdown of the 21

| Bucket | Source docs | Pattern |
|---|---|---|
| Inocalla family civil cases (RTC Manila Branches 15/16) | 630, 643, 653, 522, 511, 516, 650, 502, 503, 504, 501, 534 | Paracale-001 or no case_file. UNRELATED to MWK; some live under Paracale-001 by accident. |
| Torralba & Juntilla v. Daet RTC (CA petitions) | 581, 582, 583, 585, 513 | tagged MWK-001 but appears to be tangential/precedent — NOT a Zschoche matter. |
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
