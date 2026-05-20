---
name: facts-in-chat-are-first-class-p0
description: "Every fact stated in chat (date, counsel, docket, court, party, matter) must result in at least one DB encoding (entity, document tag, matter row, deadline, calendar event). Failing to encode = the user has to repeat themselves."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**P0 — STRUCTURAL RULE.** Facts stated in chat are first-class data. Every fact mentioned by Jonathan or any authorized client in `chat_notes` MUST result in at least one DB encoding within 1 hour, or be explicitly logged as "stated but unencoded" with a follow-up inquiry.

**The fact taxonomy and required encodings:**

| Fact type in chat | Required encoding |
|---|---|
| A date (court date, deadline, meeting) | `case_deadlines` row OR `calendar_events` row |
| A counsel name | `entities.role` populated for that person + `matters.lead_counsel` populated if they own a matter |
| A docket / case number | `matters.docket_number` populated on the matching matter; if no matching matter, a new matter row created |
| A court / agency | `matters.court_or_agency` populated; if a parallel proceeding, new matter row |
| A party (plaintiff, defendant, witness) | `entities.role` and `affiliation` populated; if missing from entities, create them |
| A status update on a matter | `matters.current_stage` updated + `client_history` event written |
| A document reference ("we have a draft") | the file's existence verified in `documents`; if found, `documents.matter_code` populated; if absent, "missing-document" alert enqueued |

**Why this rule exists (concrete pattern, 2026-05-20):**

Jonathan stated repeatedly across multiple sessions:
- The guardianship petition exists (chat_notes #21, 25, 26, 27, 28, 33, 53, 54, 57, 58, 61, 65, 95 — 13+ entries)
- Atty. Botor is handling it (multiple references)
- The May 22 Naga meeting is about guardianship (chat_note #21)
- The petition was already drafted (chat_note #25)
- Doc 623 is the canonical draft (chat_note #61)

**None of these facts triggered any DB encoding.** No `matters.MWK-GUARDIANSHIP` row was created. No `documents.matter_code` was set. Atty. Botor remained role=NULL. The May 22 calendar event existed but wasn't linked to the guardianship proceeding.

Result: when LEO synthesized a case-strategy memo the next day, the entire guardianship track was invisible — even though Jonathan had stated all the facts. Founder verbatim: *"I've been repeating myself over and over to the system and we are still having issues."*

**How to apply (the dispatcher patch — Phase D infrastructure):**

When `tg_dispatcher.py` ingests a `chat_notes` row from an allowed inbound chat_id, immediately:

1. Run a lightweight Haiku call (`fact_extractor.py`, $0.001 per message) against the note's content
2. Output: structured fact list with proposed encodings (e.g., `[{type: "counsel", name: "Atty. Botor", proposed: "create entity OR populate role"}, {type: "deadline", title: "Guardianship Brief", proposed: "create case_deadlines row"}]`)
3. For each proposed encoding:
   - If the encoding is unambiguous (e.g., a date for an existing matter), APPLY it and write a `client_history` event noting the auto-encoding
   - If ambiguous (e.g., a new counsel for an unknown matter), enqueue a single `intake_item` to Jonathan: *"Don Qi said X. Should I create / link / update Y?"* with one-tap accept/decline
4. Track every fact-to-encoding in a new audit table `fact_encoding_log` so we can measure the rate of "stated but unencoded" facts and drive it to zero

**Behavioral standing rule (interim, before Phase D infrastructure ships):**

For any chat_notes entry that touches matters/parties/deadlines/counsel, LEO must perform a self-check at synthesis time:

- "Has every fact in the past 60 days of chat_notes resulted in a DB encoding?"
- If no → the synthesis is BLOCKED (per [[feedback_synthesis_must_cross_source]]) until the missing encodings are at least surfaced as inquiries

**Related rules:**
- [[feedback_synthesis_must_cross_source]] — the synthesis-side counterpart
- [[feedback_telegram_inquiry_queue]] — the one-at-a-time rule for surfacing encoding asks
- [[feedback_atomic_inquiry_with_followups]] — each encoding ask is one atomic question
- [[feedback_landtek_management_style]] — never wait; drive results

**Concrete sentinel addition (queued for Phase D shipping):**

Add to `comms_health_sentinel.py` (or a new `fact_encoding_sentinel.py`):

```
Every 15 min:
  Count chat_notes entries from past 7 days that mention proceedings/counsel/dates
    AND have no corresponding DB encoding
  If count > 5, fire an ops gap_alert: "N stated facts from chat have not been encoded into the DB. Run /encode-pending to walk through."
```
