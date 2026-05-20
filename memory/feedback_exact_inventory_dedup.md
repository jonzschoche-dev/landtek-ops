---
name: feedback-exact-inventory-dedup
description: "Leo must maintain an exact, exhaustive inventory of every document AND continuously detect duplicates. Duplicate detection uses content_hash (sha256) for exact-match, plus heuristic same-filename+same-case + size+filename-similarity for near-duplicates."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "we need an exact inventory of all the documents and we must be able to know when there are duplicates"**

Two demands:

**1. Exact, exhaustive inventory**

Every document Leo tracks must appear in a single authoritative manifest with:
- documents.id, canonical_filename, smart_filename (original sender name)
- case_file, classification, doc_date, execution_status
- size_bytes, text_length, content_hash (sha256)
- drive_file_id, drive_link, local_path
- created_at, last_seen_at, duplicate_count
- "where it is" — DB / local / Drive / Qdrant indexed

Output formats:
- CSV (analytical / Excel-ready)
- PDF (review-ready, per case)
- Telegram digest (top-level counts + per-case breakdown)

**2. Duplicate detection**

Three duplicate tiers:

| Tier | Detection rule | Action |
|---|---|---|
| **exact** | Same `content_hash` (sha256 of bytes) | Mark as duplicate, increment duplicate_count, link via supersedes_id/related_to_doc_id |
| **near** | Same `(smart_filename, case_file)` + content_hash NULL or different but file_size ratio 0.9-1.1 | Surface for manual review; quarantine candidates |
| **content-similar** | Same canonical_filename pattern (case+date+type+detail) but different IDs | Flag — likely re-ingestion or different OCR pass of same source |

Run nightly via `dedupe_audit.py`. Surface results in:
- `/dedupe` slash command — Telegram digest of duplicate groups
- Master file directory PDF — "duplicates flagged" section

When duplicates found:
- KEEP the row with: best extraction (longest text), most metadata (case_file, exec_status), or most-recently-updated.
- MARK the others as duplicate (`status='duplicate'`, set `supersedes_id`).
- NEVER delete — per [[feedback-information-is-gold]], rows are flagged not removed.
- Drive de-dup is Phase 2 (requires service-account write perms verification).

**Implementation order:**

1. Build `apply_canonical_filenames.py` — gives every doc a canonical name (deploy 118-A).
2. Build `file_inventory.py` — exhaustive CSV + PDF + Telegram digest (deploy 118-B).
3. Build `dedupe_audit.py` — exact + near + content-similar tiers (deploy 118-C).
4. Wire `/inventory <case>` and `/dedupe` slash commands.
5. Nightly cron: dedupe_audit + flag in `audit_events` table.

Related: [[feedback-filename-convention]], [[feedback-master-file-directory]],
[[feedback-information-is-gold]].
