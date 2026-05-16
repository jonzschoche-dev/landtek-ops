# LandTek File Storage Audit — 2026-05-16

Read-only investigation. Mapping where every uploaded file lives, identifying duplication, orphans, and proposing a consolidation strategy.

## 1. The four storage layers

| layer | location | count | size | role |
|---|---|---|---|---|
| **VPS filesystem** | `/root/landtek/uploads/` | 172 files | 805 MB | Working copy of files Telegram-uploaded to the bot |
| **Postgres `documents`** | n8n DB | 618 rows | 3 MB extracted_text | Canonical metadata + extracted text |
| **Qdrant embeddings** | `landtek_documents` collection | 942 points | — | Multi-chunk vector index for RAG |
| **Google Drive** | shared folder `1BMn...L8CP` | 864 PDFs + 168 GDocs + 202 folders | — | "Cold storage" + team access |
| (backups) | `/var/backups/landtek/` + B2 | mirrors of above | 818 MB | Disaster recovery |

## 2. Top findings

### 🚨 Waste & duplication

- **73 MB wasted on byte-identical duplicates.** Same 12.6 MB `RESOLUTION_NOC...PDF` exists **7 times** on disk under different test-prefix names.
- **9 test files** (`_test`, `_test_petition`, `_test_gemini`) clogging the production uploads dir. Should never have made it past staging.
- **Duplicate filenames in DB:**
  - `"Receipt"` × **12 rows** (147, 149, 153, 154, 156, 157, 160, 168, 179, 188, 215, 216)
  - `"Gloria Balane Fraud"` × 5
  - `"JONATHAN PETITION.docx"` × 3 (likely real re-uploads)
  - Several TCT PDFs × 2-3
- Existing schema has `content_hash` and `text_hash` columns — but no UNIQUE constraint is enforced, so dupes accumulate.

### 🚨 Orphans

- **20 documents** in DB have **neither** disk file **nor** Drive link — fully orphaned. Their extracted_text is the only artifact left.
- **446 DB rows** have a filename but no corresponding file on disk (mostly fine because 489 have drive_file_id, but ~57 may be lost).
- **183 rows** (30%) have no `extracted_text` at all — never went through OCR.
- **129 rows** have no `drive_file_id` — local-only, not backed up to team-visible Drive.

### 🚨 Drive ↔ DB asymmetry

- Drive has **864 PDFs** the service account can see.
- DB only links **489** of them.
- **~375 Drive PDFs are unindexed** in our system. Leo cannot answer questions about them.

### 🚨 Filesystem has zero organization

```
/root/landtek/uploads/
├── 324069_test_petition.docx
├── 327576_file_40.docx
├── 329325_file_41.PDF
├── 329803_RESOLUTION_test.PDF
├── ...                              (172 files, all in one flat dir)
└── scannerpro/                      (160 ScannerPro PDFs, only structured subdir)
```

Files are named `<PID>_<original_or_random>` — the PID prefix is the Python process ID at upload time. No client/case grouping. Compared to Drive which has the proper structure:

```
LANDTEK/
├── 00 - Overview & Dashboard
├── 01 - Clients
│   ├── Owner/{Legal,Finance,Projects}/
│   ├── Heirs of Mary Worrick - LTC-002/{...}/
│   └── Allan Inocalla - LTC-001/{...}/
├── 02 - Active Cases
├── 03 - Closed / Archived Cases
├── 04 - Templates & SOPs
├── 05 - Government Records & Programs
├── 06 - Legal & Compliance
├── 07 - Financials
├── 08 - Internal
├── 09 - AI Processing
├── 10 - Portals
├── Cowork-Bridge
├── ScannerPro
└── Drafts
```

### 🚨 Dead collections

- Qdrant `landtek_evidence`: **0 points** (created but never used)
- Qdrant `landtek_emails`: **0 points** (created but never used)
- 5 inactive workflows in n8n (`Demo: RAG in n8n`, `Import workflow`, `Landtek - Smartfiler`, `My workflow 2`, `Super Leo Agentic Tracking`)

### ⚠️ Unclassified

- **193 of 618 docs** have empty / `unknown` / `Unknown` case_file. Leo can't filter to them by client matter.

## 3. Proposed consolidation strategy

### Phase A — Cleanup (read-only audit → mostly-safe deletes)

1. Delete the 9 `*test*` files from `/root/landtek/uploads/` and their corresponding DB rows.
2. Dedupe disk: keep one copy of each byte-identical file (saves ~73 MB).
3. Drop the two empty Qdrant collections (`landtek_evidence`, `landtek_emails`).
4. Archive the 5 inactive n8n workflows to a `_inactive` JSON folder, then delete from n8n.

### Phase B — Adopt Drive's hierarchy as canonical

- Restructure `/root/landtek/uploads/` to match Drive: `uploads/<case_file>/<smart_filename>.pdf`. Map current flat files via DB lookups.
- Set a permanent rule: Telegram-uploaded files land in `uploads/<case_file>/`. The Drive sync uploads them to the matching Drive folder (already half-built via deploy_067).

### Phase C — Enforce dedup at write time

- Backfill `content_hash` (SHA-256 of binary) for all 618 docs.
- Backfill `text_hash` (SHA-256 of normalized extracted_text) for the 435 with text.
- Add `UNIQUE (case_file, content_hash)` constraint to prevent future re-uploads.
- Modify the Telegram upload pipeline: compute hash before writing → if exists, return existing doc_id instead of inserting.

### Phase D — Backfill the 375 unindexed Drive PDFs

- One-time script: walk Drive folders, for each PDF not in `documents`, insert a row + extract text + embed.
- Estimated cost: ~$2.50 in Gemini calls (375 × $0.006 average).

### Phase E — Resolve orphans

- 20 documents with neither disk file nor Drive link: review each, decide delete vs recover.
- 183 docs without extracted_text: re-OCR via Gemini PDF-native batch.

## 4. Estimated impact

| metric | now | after | delta |
|---|---|---|---|
| disk usage | 805 MB | ~732 MB | -73 MB |
| docs with full extraction | 435 (70%) | 618 (100%) | +183 |
| docs in Drive | 489 (79%) | 618 (100%) | +129 |
| docs Leo can answer about | 618 | ~993 (618 + 375 Drive backfill) | +60% retrieval surface |
| duplicate "Receipt" rows | 12 | 1 (or n if real distinct receipts) | -11 |
| unused Qdrant collections | 2 | 0 | — |

## 5. Recommended next steps (in order)

1. **Confirm** with Jonathan which phases to execute and at what cadence (each is a separate deploy).
2. **Phase A first** — pure cleanup, near-zero risk to Leo. ~30 min.
3. **Phase E (orphans)** — manual triage with Jonathan. ~30 min review.
4. **Phase C (dedup)** — adds constraint, modifies write path. Needs staging cycle. ~2 h.
5. **Phase B (hierarchy)** — biggest change, touches workflow + filesystem. Plan after C is stable. ~3 h.
6. **Phase D (Drive backfill)** — runs once Phase B is in place. ~$2.50 Gemini cost, runs overnight.

---

*Generated 2026-05-16 by file audit. Read with `cat /root/landtek/reports/file_audit_2026-05-16.md` or via the Files Dashboard.*
