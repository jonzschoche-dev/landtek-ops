---
name: feedback-filename-convention
description: Canonical filename convention for every LandTek file. Encodes case + date + type + identifying detail + leo-id so any file is interpretable at a glance and sortable chronologically per case.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "filenames must be clear creating a new naming system is fine"**

The corpus today has inconsistent names: Drive prefixes (<code>19c4...__Exhibit A.pdf</code>),
YYYY-MM-DD placeholders, <code>null_</code> prefixes, empty filenames. Future files
and on-rename of existing ones must follow the canonical pattern below.

## Pattern

```
{CASE}_{YYYY-MM-DD}_{TYPE}_{detail-slug}_{leo-id}.{ext}
```

- `{CASE}` — 2-5 letter case code: `MWK`, `PCL` (Paracale-001), `LT` (Landtek firm-level), `UNK`
- `{YYYY-MM-DD}` — doc date (from doc_date or extracted text); `unknown-date` if not yet known
- `{TYPE}` — uppercase short code from the registered taxonomy (see below)
- `{detail-slug}` — kebab-case identifier specific to the doc: TCT number, docket, party, exhibit letter, RPT-year, etc.
- `{leo-id}` — internal documents.id (zero-padded to 4 digits) — guarantees uniqueness
- `{ext}` — lowercase extension

## Type taxonomy

| Code | Meaning |
|---|---|
| `TCT` | Transfer Certificate of Title |
| `OCT` | Original Certificate of Title |
| `DEED` | Deed of Sale / Donation / Confirmation |
| `SPA` | Special Power of Attorney |
| `SPA-REVOKE` | Revocation of SPA |
| `AFF` | Affidavit |
| `JAFF` | Judicial Affidavit |
| `COMPL` | Complaint / Verified Complaint |
| `ANSW` | Answer (with counterclaim) |
| `REPLY` | Reply (post-Answer) |
| `MOT` | Motion (incl. summary judgment, dismiss) |
| `OPPOS` | Comment / Opposition |
| `NOTICE` | Notice (pre-trial, hearing, etc.) |
| `ORDER` | Court Order |
| `DECISION` | Court Decision |
| `RESOL` | Resolution |
| `MEMO` | Memorandum / Legal Memorandum / Position Paper |
| `TAXDEC` | Tax Declaration / ARP |
| `SOA` | Statement of Account |
| `OR` | Official Receipt |
| `RPT` | Real Property Tax payment record |
| `DEMAND` | Demand Letter |
| `LETTER` | Letter / Correspondence |
| `EMAIL` | Email (sent or received) |
| `EXHIBIT` | Exhibit / Annex |
| `BRIEF` | Pre-trial / appellate brief |
| `VERIF` | Verification (attached to pleading) |
| `COMPLI` | Compliance filing |
| `APPRAISAL` | Appraisal report |
| `MAP` | Survey plan / lot plan |
| `PETITION` | Petition (guardianship, intestate, certiorari) |
| `ARTA` | ARTA filing |
| `OTHER` | catch-all |

## Examples

```
MWK_2026-04-24_NOTICE_pretrial-26-360_0392.pdf
MWK_2016-09-29_DEED_balane-sale-T52540_0233.pdf
MWK_2005-08-15_SPA-REVOKE_dela-fuente_0076.pdf
MWK_unknown-date_JAFF_salvador-dela-fuente_0407.pdf
MWK_2025-10-01_COMPL_arta-pajarillo_0384.pdf
MWK_2014-06-23_TAXDEC_arp-001-00229_0059.pdf
MWK_2025-05-13_NOTICE_pretrial-26-360_0392.pdf
PCL_2024-08-12_MAP_inocalla-claim_0623.pdf
LT_2026-05-16_REPORT_financial-snapshot_0000.pdf
```

## Storage rules

- The canonical filename is stored in `documents.canonical_filename` (new column).
- Local file on disk uses the canonical name when re-saved.
- Drive file name should mirror canonical (rename action when the service account has perms).
- `smart_filename` is preserved as the original sender's name for audit; canonical is the display name.

## Rendering rules

- Reports + Telegram references show `canonical_filename` (clear).
- Provenance citations use both: `[V·F MWK_2026-04-24_NOTICE_pretrial-26-360_0392]` is the same as `[V·F doc#392]` — both unambiguous.

## Implementation order

1. ALTER documents ADD COLUMN canonical_filename.
2. `apply_canonical_filenames.py` — derive from existing metadata + classification + execution_status + extracted text.
3. On future ingest, compute canonical_filename at insert time.
4. Drive rename (Phase 2 — requires write perms verification).
5. Reports surface canonical_filename instead of smart_filename.

Related: [[feedback-information-is-gold]] (organized = protected),
[[feedback-master-file-directory]] (the directory must be readable).
