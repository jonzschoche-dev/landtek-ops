---
name: feedback-information-is-gold
description: "Information uploaded to LandTek is gold — never lose it once it's been uploaded. Every doc must be protected, organized, and recoverable. Treat data integrity as primary requirement."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

Information is gold. Once anything is uploaded to LandTek (Telegram, Drive, email, manual import), it must be:
- **Protected** — captured to a durable store (Postgres documents + filesystem + backup), never silently dropped
- **Organized** — placed in a discoverable structure (Drive folder hierarchy, case_file scoping, indexed in DB)
- **Never lost** — once stored, the original file/data is preserved indefinitely. Deletions require explicit Jonathan approval and an audit trail.

**Why:** Stated by Jonathan 2026-05-16 during the file audit discussion: *"information is gold, we must protect it and organize it, and never lose it once its been uploaded this is critical."* The file audit revealed 20 fully-orphaned documents (no disk, no Drive) — those are data-loss events that should never recur.

**How to apply:**

When designing or modifying any ingestion / cleanup / migration code:

1. **Never delete without confirmation.** Any script that removes files, drops rows, or truncates extracted_text must:
   - Show what will be deleted BEFORE deleting
   - Get explicit Jonathan approval (or be running under a confirmed-by-user task)
   - Move to an `_archive/` location first when feasible, with full filename + content_hash preserved

2. **Default to capture.** When in doubt, save more not less. Better to have a duplicate row in documents than miss a real file. Dedup later via content_hash, not by skipping initial INSERT.

3. **Extraction failures are not deletions.** If Gemini OCR fails on a PDF, we keep the source PDF AND mark extracted_text=NULL — never delete the source.

4. **Drive sync is one-way capture.** Files uploaded via Telegram land on VPS first, then sync to Drive. Drive folders are NEVER authoritative for "was this file received" — VPS + Postgres are.

5. **Orphan recovery is high-priority.** The 20 fully-orphaned docs in documents (no disk, no Drive) need triage — try to recover from B2 backup, then mark as lost-with-extracted-text-only.

6. **Audit trail on every state change.** Any UPDATE / DELETE on documents must leave a trail (timestamps, who/what triggered it, prior values if relevant).

7. **No silent drops in pipelines.** If a Telegram upload arrives with no case_file, set case_file='UNCLASSIFIED' rather than skipping the row. If extraction fails, log a chat_note. Never let data fall through the cracks.

Phase A cleanup (deploy after 2026-05-16 file audit) deliberately preserved all non-test files. Phase B/C/D/E plans must preserve this discipline — backup-first, delete-last.

Related: [[feedback-leo-must-never-go-offline]] (Leo uptime ⊂ data integrity), [[feedback-no-invented-schemas]] (don't lose data via wrong schema assumptions).
