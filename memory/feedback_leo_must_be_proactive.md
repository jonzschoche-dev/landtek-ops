---
name: feedback-leo-must-be-proactive
description: "Leo must proactively pull data from connected sources (Gmail, Drive, n8n triggers) on a continuous schedule. Waiting for manual triggers is complacency — by definition Leo is missing data that's already available to it. Every data source must have an auto-pull cron + an auto-ingest pipeline."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "we should easily be able to know the status of the case what documents have been filed by the client or the respondent — why are we missing so much data already available to the system we need to do something about the complacency of the system"**

This is a direct critique. Acknowledge it: the system shipped scaffolds and waited for human triggers. That's complacent. By definition Leo was missing data that he could have pulled himself.

**Standard for every data source Leo can reach:**

| Source | Auto-pull cadence | Auto-ingest pipeline |
|---|---|---|
| Gmail | every 15 min | classify → case_file → if attachments, ingest each as document |
| Drive (LANDTEK shared folder) | every 30 min | diff against existing drive_file_ids, ingest new |
| n8n workflow inbound | real-time | already wired through Telegram trigger + channel adapters |
| Telegram file uploads | real-time | onboarding gate + /api/uploads endpoint |
| Court e-filing portals | TBD (no API yet) | manual upload + auto-classify |
| WhatsApp Business | real-time when WABA token added | inbound webhook → onboarding/AI |

**Per-case filing-side awareness:**

For every active matter, Leo must classify each filed document by FILING PARTY:
  - `plaintiff_filing` — filings by us (Patricia Zschoche via Jonathan)
  - `respondent_filing` — filings by the other side (Balane et al, Pajarillo, etc.)
  - `court_order` — court-issued orders/decisions
  - `evidence` — exhibits, attachments
  - `correspondence` — letters between counsel
  - `notice` — procedural notices

Stored in new `case_party_filings` table with: matter_code, doc_id, filing_party, filing_date, filing_type, role_in_case, next_response_due.

This enables `/case_status <matter>` to show: who filed what, when, what's pending, what we owe in response, what they owe in response.

**How to apply:**

1. Install gmail-watcher.timer (systemd, every 15 min) — running NOW, not "when triggered".
2. Install drive-sync.timer (every 30 min) for new Drive files.
3. Build extract_email_attachments.py — pull all 68 ARTA attachments + future inbound.
4. Build party_filing_classifier.py — for each doc in active matters, tag filing_party.
5. Build /case_status <matter> slash → shows per-party filing inventory + pending responses.
6. Daily review: report what was auto-ingested in the past 24h.

**Behavioral rule (permanent):**
When Leo recognizes a data source he can reach, the default is automated continuous pull. Manual-trigger-only is reserved for sources Jonathan explicitly designates as manual.

Related: [[feedback-leo-mission-agency]], [[feedback-information-is-gold]],
[[feedback-leo-must-never-go-offline]] (proactivity is part of operational excellence).
