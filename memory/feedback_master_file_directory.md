---
name: feedback-master-file-directory
description: "Leo must surface a master directory of all files — where each lives (Postgres / local / Drive), how it's accessed by which role (operator / client / external counsel / API consumer), and integrity status (extracted? hashed? linked to case?)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "we must see the master directory of files and understand how they will be accessed"**

Files live in four parallel locations:

| Location | Purpose | Access mode |
|---|---|---|
| **Postgres `documents` table** | Source-of-truth metadata index | Internal Leo operations + REST API |
| **Local `/root/landtek/uploads/`** | Files downloaded for OCR / processing | Internal scripts, batch jobs |
| **Google Drive** | Master file store, human-readable browse | Jonathan + service account; clients via shared folder |
| **Qdrant** | Vector index for semantic retrieval | Leo's RAG path |

**Per-doc fields that matter for access:**
- `documents.id` — Leo's internal pointer
- `documents.drive_file_id` — Google Drive ID (the canonical "real" file)
- `documents.content_hash` — sha256 for dedup + integrity check
- `documents.smart_filename` — human-readable name
- `documents.case_file` — case correlation (MWK-001 / Paracale-001 / etc.)
- `documents.extracted_text` — OCR'd text (presence = Leo can reason over it)

**Access patterns:**

1. **Leo (internal)**: queries `documents` table + reads `extracted_text`. Vector search via Qdrant.
2. **Jonathan (operator)**: Telegram slash `/file <id>` or direct Drive browse. Reads any doc.
3. **Approved clients**: Token-gated URLs (deploy_086) — sees only docs where `case_file = their_case`.
4. **External counsel** (after onboarding approval): same as client but with optional document-set scoping.
5. **API consumers** (licensable product): only metadata + extracted_text snippets via `/api/v1/leo/chat` — never raw file bytes.
6. **Audit**: `channel_messages` logs every file access request per channel_user.

**Required reports:**
- `/files` slash command — show per-case file inventory + integrity scorecard
- Per-case file directory PDF: every doc, where it lives, who can access, extraction status
- Daily file-audit job: flag docs missing drive_file_id / content_hash / extracted_text / case_file

**How to apply:**
1. Build `pdf_file_directory.py` — per-case master directory PDF.
2. Build `/files <case>` slash — per-case file inventory in Telegram.
3. Build `file_integrity_audit.py` — nightly job flagging drift (missing drive_id, hash, text, or case_file).
4. Reports always include integrity-percent figures so investors can see data discipline.

Related: [[feedback-information-is-gold]] (every file must be protected),
[[feedback-execution-status-required]] (each file's legal force),
[[feedback-title-asset-matter-linkage]] (files are anchors for matters).
