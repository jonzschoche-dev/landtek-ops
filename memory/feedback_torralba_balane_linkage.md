# Feedback rule: Torralba/Juntilla CA case IS linked to Balane

**Filed:** 2026-05-21 (Jonathan correction during deploy_244 review)

## What happened

During the deploy_244 LLM doc-classification run, the model flagged docs
581, 582, 583, 585 as `flag_unrelated` at **0.95 confidence each**. I
(Claude) initially accepted that classification at face value and wrote
a "misclassified docs" finding to `holes/finding_resolutions_misclassified.md`
proposing they be removed from MWK-001.

**Jonathan corrected this.** The Torralba/Juntilla CA petition (CA-G.R. SP
No. 181607, challenging RTC Daet Branch 41) is Balane-family litigation,
not unrelated precedent.

## The entity-graph evidence

The platform already has the evidence to prove the linkage; the LLM just
didn't have access to it. Cross-checking the entity table shows:

| Entity ID | Canonical name | Mentions | Significance |
|---|---|---|---|
| #2391 | **Princess Balane Torralba** | 25 | The hub — Balane family member married into Torralba surname |
| #3059 | Jomil Torralba | 21 | CA petitioner; Princess's relative |
| #8360 | Nelly H. Juntilla | 1 | CA co-petitioner |
| #3155 | Donata Mabeza King | 2 | CA respondent; "Mabeza" overlaps with transferee Arnel Mabeza |
| #2084 | Arniel Dating | 2 | RTC Branch 41 judge; same court as CV26360 |

Doc-text grep confirms: doc#581 has 30 "balane" mentions, doc#583 has 19.

## The platform lesson (north-star takeaway)

**High LLM confidence ≠ accuracy.** The 0.95-confidence
"flag_unrelated" verdict was wrong because the model didn't have the
entity-graph in front of it. The platform needs structural guards:

1. **Cross-check rule for `flag_unrelated` proposals**: before accepting,
   query whether any entity in the doc's `doc_entities` already appears
   in the keystone or transferee graphs of the supposed-"unrelated"
   client. If yes, downgrade to manual review.

2. **Family-surname spider rule**: any doc that names a person whose
   surname matches a registered transferee or principal should
   inherit the client's case_file by default, even if the principals
   aren't directly named.

3. **Same-court inheritance rule**: docs about RTC Branch 41 Daet
   (where CV26360 sits) get a presumption of MWK-CV26360 ancestry
   pending entity-graph confirmation.

## What was done in deploy_251

- docs 581, 582, 583, 585 → matter_code = MWK-CV26360
- resolutions 5, 10, 11, 13 → +MWK-CV26360 in affected_matter_codes
- 4 LLM proposals → status='superseded' with review note
- This memory rule filed
- truth_tests/test_torralba_linkage.py asserts Princess Balane Torralba
  remains the canonical hub (#2391) and the 4 docs stay attached to
  MWK-CV26360

## Open follow-up

The other 123 `flag_unrelated` proposals still sitting at status='proposed'
should be audited the same way — pull each doc's entity list and check
whether any keystone/transferee surname overlap exists before accepting
the LLM verdict. Track as a separate task; don't auto-apply.
