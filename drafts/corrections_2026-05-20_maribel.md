# Matter Corrections — 2026-05-20 Maribel Meeting (Inocalla estate gold mining)

> Captured by Cowork from 2026-05-20 Telegram exchange with @LeoLandtekBot.
> Authoritative source: Jonathan, in-chat corrections of Leo's matter proposals.
> Action: VPS Claude — on next session, update matter rows + write case_intelligence_log entries.

---

## Meeting context

- **Date:** 2026-05-20 (Jonathan's chat timestamp)
- **Meeting partner:** Maribel
- **Subject:** Inocalla estate gold mining matters
- **Client:** Paracale-001 (Allan V. Inocalla)
- **Capture mode:** photo upload (encountered ON CONFLICT image-handler bug — see § "Bugs surfaced" below)

---

## Corrections per matter

### PAR-CV13-131220 — DETACH from meeting context

- **Leo proposed:** Civil Case 13-131220 (Inocalla siblings vs. Vicente V. Inocalla Jr. heirs, RTC Manila Br 15, 2006 decision, 2021 SC entry of judgment, post-judgment enforcement)
- **Jonathan correction (verbatim):** "This has nothing to do with the legal case"
- **Action:** Leave existing matter description as-is. **Do not link this matter to the 2026-05-20 Maribel meeting.** It came up in Leo's RAG retrieval but is not part of the meeting subject.

---

### PAR-CASE-88750 — UPDATE to mineral rights

- **Leo proposed:** Family property dispute — Francisco V. Inocalla vs. Allan V. Inocalla et al., RTC Manila Br 16, 2006 case w/ 2013-14 motions
- **Jonathan correction (verbatim):** "This has to do with ongoing mineral rights disputes for the Inocalla estate that we are currently tracking and consulting the client"
- **Action:**
  - `matters.current_situation` = "Ongoing mineral rights dispute on Inocalla estate parcels — actively tracking + consulting client (Allan V. Inocalla)"
  - `matters.subject_category` = "mineral_rights_dispute" (not "family_property_dispute")
  - Re-tag any associated documents to reflect the mineral-rights nature
  - The 2006-2014 motions Leo retrieved may be irrelevant historical noise; confirm with Allan
- **Open question (for Jonathan):** Is this the same docket as Case 88750 (Francisco vs Allan), or a different/related proceeding that shares the case identifier in our system?

---

### PAR-CAPACUAN — CLIENT CONFIRMED = Allan Inocalla

- **Leo asked:** "Who is the firm's client in this matter—is it an Inocalla heir, Paracale Gold Corporation, or the Capacuan Miners Association?"
- **Jonathan answered:** "The client is Allan Inocalla"
- **Action:**
  - `matters.client_id` = Allan V. Inocalla (Paracale-001)
  - Resolve Open Question #1 (closed)
  - Capacuan Small-Scale Miners Association = adverse / counterparty (not client)
  - Paracale Gold Corporation = TBD (related entity? counterparty? collaborator? → ask Jonathan)

---

### PAR-VITO-CRUZ — MAJOR UPDATE: WON LAWSUIT, PENDING TITLE TRANSFER

- **Leo proposed:** 15% confidence, "Vito Cruz case — subject matter unknown, single source document, status indeterminate pending document analysis"
- **Jonathan correction (verbatim):** "Our client won a lawsuit vs his nephew who had taken over Vito Cruz it will soon be titled back to the estate"
- **Action:**
  - `matters.stage` = `won_judgment_pending_title_transfer`
  - `matters.current_situation` = "Client (Allan Inocalla) won a lawsuit against his nephew who had taken over the Vito Cruz property. Title transfer back to the Inocalla estate is pending."
  - `matters.opposing_party` = "Allan's nephew" (name TBD — see open questions below)
  - `matters.next_action` = "Monitor title-transfer execution at Registry of Deeds; ensure transfer completes"
  - Doc#646 (Vito Cruz Case.pdf) should be extracted on priority — likely contains the judgment
- **Open questions (for Jonathan):**
  - Name of nephew (Vicente "Ace" Inocalla III? — possibly the "Ace" from PAR-COMPLAINT-ACE)
  - Docket number of the won lawsuit
  - Court of decision
  - Date of judgment
  - Estimated title-transfer execution date

---

### PAR-GOLDEN-SAND — UPDATE to development plan, not dispute

- **Leo proposed:** 25% confidence, "Asset matter, unclear if advisory or dispute, opposing party unknown, possibly Primeland Destination Developer"
- **Jonathan correction (verbatim):** "This is a proposed development plan for one of the titles"
- **Action:**
  - `matters.engagement_type` = "transactional_advisory" (not "dispute_resolution")
  - `matters.current_situation` = "Proposed development plan for one of the Inocalla estate titles — Golden Sand Beach Residences proposal by Primeland Destination Developer (Aaron E. Mirasol, President) to Shishir Inocalla"
  - `matters.subject_title` — needs identification (which TCT/OCT does this proposed development cover?)
  - `matters.client_id` = Allan V. Inocalla (assumed — confirm)
  - Resolve Open Question #2 — engagement is transactional advice, not dispute

---

### PAR-TCT1616 — CLIENT INTEREST CLARIFIED = co-owner

- **Leo asked:** "What is the client's interest in the Inocalla estate title—are they a claimant, a buyer, a lender, or seeking to defend an existing interest?"
- **Jonathan answered:** "The client is a co owner in the estate"
- **Action:**
  - `matters.client_interest` = `co_owner_in_estate`
  - `matters.client_id` = Allan V. Inocalla
  - Open Question #1 closed
  - Doc#633 (TCT-1616.pdf) + Doc#639 (OCT/TCT1616.pdf) priority extraction to determine OCT vs. TCT status + chain

---

### PAR-COMPLAINT-ACE — MAJOR CORRECTION: nothing to do with ARTA

- **Leo proposed:** Complaint connected to ARTA matter — Pajarillo + Macale (Mercedes RPT refusal); Don Qi referral to CSC/DILG; Mary Worrick estate context
- **Jonathan correction (verbatim):** "Ace is for the Inocalla estate nothing to do with arta"
- **Critical defect identified:** Leo conflated the name "Ace" (an Inocalla nephew — possibly same person as the PAR-VITO-CRUZ adversary) with ARTA-related matters (Zschoche / Mercedes Mayor / MWK estate). This is a **cross-matter name disambiguation failure** — exactly the kind of bug that the v1.0 ontology-hardening + output_audit work is designed to eliminate.
- **Action:**
  - `matters.client_id` = Allan V. Inocalla (Paracale-001)
  - `matters.case_file` = `Paracale-001` (NOT `MWK-001`)
  - `matters.opposing_party` = "Ace" (an Inocalla nephew — likely Vicente Inocalla III "Ace")
  - `matters.subject` = Inocalla estate property control
  - **Remove all ARTA-0747 / Pajarillo / Macale / Mercedes RPT references** from this matter
  - **Remove all MWK-001 / Don Qi / Zschoche references** from this matter
  - Likely related to PAR-VITO-CRUZ (same nephew "Ace")
- **Cross-matter test case for v1.0:** When ontology hardening + output_audit ship, this exact disambiguation must be enforced — "Ace" appearing in a Paracale matter cannot pull MWK-001/ARTA context.

---

## Identity to resolve

- **Ace** — appears in PAR-COMPLAINT-ACE + likely PAR-VITO-CRUZ. Probably Vicente Inocalla III "Ace" (the nephew who took over Vito Cruz). Should be added to `entities` table with:
  - `canonical_name` = "Vicente Inocalla III"
  - `aliases` = ["Ace", "Vicente III", "Vicente de Leon Inocalla III"]
  - `role` = "adverse party — Inocalla estate"
  - `case_files` = ['Paracale-001']
  - Confirm with Jonathan whether "Vicente de Leon Inocalla III" from PAR-CV13-131220 is the same person (likely yes, given context)

---

## case_intelligence_log entry to write

```
case_file: 'Paracale-001'
source: 'meeting_notes_via_jonathan'
source_doc_id: NULL  (image upload failed due to ON CONFLICT bug)
intelligence_update: '
2026-05-20 — Meeting with Maribel covering Inocalla estate gold mining matters.

Updates by matter:
- PAR-CASE-88750: re-scoped to ongoing mineral rights dispute (was incorrectly framed as 2006 family property case)
- PAR-VITO-CRUZ: client won lawsuit vs nephew; title transfer to estate pending
- PAR-CAPACUAN: client confirmed = Allan Inocalla
- PAR-GOLDEN-SAND: re-classified as development-plan advisory (not dispute)
- PAR-TCT1616: client interest = co-owner in estate
- PAR-COMPLAINT-ACE: detached from ARTA (was incorrectly tagged); subject = Inocalla nephew "Ace"
- PAR-CV13-131220: not part of this meeting context

Cross-matter signal: "Ace" appears in multiple Paracale matters; likely Vicente Inocalla III.
Bug: image handler ON CONFLICT error blocked Maribel notes attachment — see issue tracker.
'
provenance_level: 'verified'
```

---

## Bugs surfaced

### Image handler ON CONFLICT bug

**Symptom:** When Jonathan uploaded a photo at 14:09 PM with caption "All from my meeting with Maribel — For Inocalla estate gold mining", Leo returned: `⚠️ Image handler error: there is no unique or exclusion constraint matching the ON CONFLICT specification`.

**Likely cause:** An `INSERT ... ON CONFLICT (X) DO ...` statement in the image-upload handler references a column or constraint that doesn't exist on the target table (probably `pending_docs`, `documents`, or `document_chunks`).

**Action:** VPS Claude — grep for "ON CONFLICT" in image-handler code paths:
- `tg_dispatcher.py`
- `index_attachments.py`
- `pull_gmail_attachments.py`
- `safe_ingest_wrapper.py`
- n8n_code_nodes (Telegram photo handler)

Compare ON CONFLICT clauses against actual table constraints in v4 schema. Fix the mismatch.

**Priority:** Immediate (v0.9 hotfix). This bug blocks meeting-attachment capture — exactly the use case the workspace v1.0 is designed to enable.

---

## What v1.0 must catch that wasn't caught here

This Maribel exchange is the regression-test set for v1.0:

| Defect 5-20 | v1.0 mechanism that prevents it |
|---|---|
| Leo dumped 7 proposals on stale RAG | `feedback_first_principles_before_proposal.md` — confidence floor ≥ 0.80 + stale-context detection + fresh-context override |
| Leo conflated "Ace" (Inocalla) with ARTA (Zschoche) | Ontology disambiguator + output_audit cross-matter integrity check |
| Image upload failed silently | `+ Evidence` / `+ Meeting note` flows in workspace v1.0 with explicit error UX |
| Corrections sit in chat log, never update matter rows | `+ Note` / `/correct` commands structurally update `matters.current_situation` + write `case_intelligence_log` |
| 5 of 7 matter descriptions were wrong | Update discipline + freshness-checked descriptions |

---

_End of corrections. VPS Claude — apply these on next session via the matter-update SQL path. Confirm completion by writing a follow-up `corrections_applied_*.md` log._
