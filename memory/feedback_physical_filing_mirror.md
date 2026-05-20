---
name: feedback-physical-filing-mirror
description: "The digital filing system must be organized such that a human can find any document even if the server is offline. The physical Landtek office filing cabinet will MIRROR the online structure exactly — same folder hierarchy, same per-folder INDEX manifest, same naming convention. File wisely."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "this system must be organized in a way that if the server shuts down a human can find what they need" — "we will have a physical filing system in the office that mirrors that of online, so file wisely"**

This is a survival-of-the-firm requirement. If Leo's database is unavailable, the physical files in the office must be findable by ANY paralegal/staff using:
  - Folder hierarchy (printable on tab dividers)
  - Per-folder INDEX manifests (CSV + PDF)
  - Canonical filenames already on each file

## Canonical hierarchy (mirrored physical + digital)

```
/root/landtek/uploads/                       ← LANDTEK file room
├── README.md                                ← human navigation guide (top-level)
├── 00-INDEX.csv                              ← top-level manifest
├── MWK-001 (Heirs of Mary Worrick Keesey)/  ← BINDER A
│   ├── 00-INDEX.csv                          ← case manifest
│   ├── 00-README.md                          ← case summary + matter list
│   ├── 01-Pleadings/                         ← BINDER TAB: Pleadings
│   │   ├── 00-INDEX.csv
│   │   ├── Civil-Case-26-360/
│   │   │   ├── 00-INDEX.csv
│   │   │   ├── 01-complaint/
│   │   │   ├── 02-answer/
│   │   │   ├── 03-replies-and-motions/
│   │   │   ├── 04-court-orders/
│   │   │   ├── 05-pretrial/
│   │   │   └── 06-trial-evidence/
│   │   ├── ARTA-2026-0423-1891/
│   │   │   ├── 01-complaint/
│   │   │   ├── 02-responses/
│   │   │   └── 03-DILG-referral/
│   │   └── Drafts-Pending-Filing/
│   │       ├── Ombudsman/
│   │       ├── Supreme-Court/
│   │       └── RTC/
│   ├── 02-Titles/                            ← BINDER TAB: Titles
│   │   ├── 00-INDEX.csv
│   │   ├── Active/
│   │   ├── Cancelled/
│   │   ├── Contested/
│   │   └── Lost-or-Damaged/
│   ├── 03-Tax-Declarations/                   ← BINDER TAB: Tax Decs
│   │   ├── 00-INDEX.csv  (links to assessor master list)
│   │   ├── 1990-2010-Historic/
│   │   ├── 2011-2025-Series/
│   │   └── 2026-Current/
│   ├── 04-Deeds-SPAs/                         ← BINDER TAB: Deeds & SPAs
│   │   ├── Donations/
│   │   ├── Sales/
│   │   └── Powers-of-Attorney/
│   ├── 05-Correspondence/                     ← BINDER TAB: Correspondence
│   │   ├── 00-INDEX.csv
│   │   ├── Atty-Barandon/
│   │   ├── Atty-Botor/
│   │   ├── LGU-Mercedes/
│   │   ├── Heirs/
│   │   ├── RD-Camarines-Norte/
│   │   └── Other/
│   ├── 06-Financial/                          ← BINDER TAB: Financial
│   │   ├── Bills/
│   │   ├── Receipts/
│   │   ├── Bank-Statements/
│   │   ├── Retainer-Agreements/
│   │   └── Settlement-Records/
│   └── 07-Affidavits-Witnesses/
│       ├── Plaintiff-side/
│       ├── Defendant-side/
│       └── Third-party/
├── Paracale-001 (Allan Inocalla)/           ← BINDER B
│   └── (same structure)
└── LANDTEK-FIRM/                             ← BINDER F
    ├── 01-Operations/
    │   ├── HR/
    │   ├── Office-Lease-and-Utilities/
    │   └── IT-Subscriptions/
    ├── 02-Financial/
    │   ├── Revenue/
    │   ├── Expenses/
    │   ├── Bank-Statements/
    │   └── Tax-and-Compliance/
    ├── 03-Marketing-and-BD/
    └── 04-Investor-Relations/
```

## Per-folder INDEX rules

Each folder contains a `00-INDEX.csv` with columns:
  `canonical_filename, doc_id, doc_date, type, execution_status, case_file, summary, drive_link, last_updated`

The INDEX is auto-regenerated nightly + on every new file ingestion. Printable as a PDF (`00-INDEX.pdf` for paper binders).

## The top-level README

A human can pick up README.md and navigate the entire system in < 1 minute. Lists:
  - All cases + binder letter assignments
  - Locator: "Need a 2023 RPT receipt for MWK-001? → BINDER A · TAB 03 · 2011-2025-Series · filename pattern MWK_2023-*_OR_*"
  - Emergency contacts (Atty Barandon, Atty Botor, courts, key clients)

## How to apply

1. Build `organize_filing_structure.py` — moves local files in /root/landtek/uploads/ into the hierarchy.
2. Build `regenerate_indexes.py` — produces 00-INDEX.csv + 00-INDEX.pdf at every level. Nightly cron.
3. Build `mirror_to_drive.py` — replicates the same hierarchy on Google Drive (Phase 2 when service-account write perms confirmed).
4. Generate top-level README.md auto-updated when new cases/matters open.
5. Every new file ingestion (Telegram, email, Drive sync) routes to its canonical folder by case + classification + date.

The standard: any paralegal walking into the office should find a 2014 tax dec for MWK-001 in under 60 seconds without touching a computer.

Related: [[feedback-filename-convention]], [[feedback-information-is-gold]],
[[feedback-master-file-directory]], [[feedback-leo-must-never-go-offline]].
