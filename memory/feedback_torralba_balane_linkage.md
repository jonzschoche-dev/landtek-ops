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

---

## 2026-05-21 update — Donata King cascade (deploy_255)

Following user correction "the torralba is linked to 260360 Donata King etc",
investigation surfaced the full **Balane-Torralba-King-Mabeza-Hansol family
network** through Civil Case 8563 (RTC Daet Branch 41):

  Plaintiffs: Juntilla, Torralba, Cantor, Mendones, Escalante
  Defendants: Donata M. King, Francia Delos Santos, Joel I. Mabeza,
              Daniel E. Teope, Christine M. Opena

This is the underlying RTC case (DAMAGES / Malicious Prosecution) that became
CA-G.R. SP No. 181607 (Torralba/Juntilla v. Daet RTC).

### Hansol-Balane family intermarriage

Key finding from doc#406 (Philippine Consulate Toronto Acknowledgement, 2020-05-28):
the principal's full name is **"GLORIA HANSOL BALANE"** — middle name = surname
of transferee Rosalina M. Hansol. The Balane and Hansol families intermarried.
This means doc-classification rules can rely on either surname to identify
CV26360 evidence.

### 1913 SC chain primary

doc#568 = Supreme Court Decision G.R. No. 8678 (Dec 29, 1913): **"Marciana Moreno
De WORRICK u. Paulina, Valeriana, Lino, and Raymundo Gaco"**. This is primary
Worrick-family chain evidence from the year after T-111 was issued (1912).
Requested by Jonathan Paul Zschoche Jan 5, 2026 — it's been mis-tagged as
Paracale-001 for the entire database lifetime until now. Should be
MWK-TCT4497.

### Platform fix: `scripts/audit_case_file_assignments.py`

Generic deterministic audit script (NEW in deploy_255):
  - Builds each client's keystone surname set from the registry
  - Greps every doc in OTHER case_files for those surnames (word-boundary)
  - Reports docs with ≥N distinct surname hits → reassignment candidates

This is how Paracale-001 docs 406, 411, 568, 586 surfaced. Run it after
any client onboarding or major doc-ingest to catch case_file drift.

### Registry additions (deploy_255)

Added to MWK.keystone_entities:
  - donata_mabeza_king  = #3155  (Balane-family defendant, Civil 8563)
  - joel_i_mabeza       = #8367  (Mabeza-family defendant, Civil 8563)

Entity consolidation:
  - #8365 'Donata M. King' → canonical_id = #3155 'Donata Mabeza King'
