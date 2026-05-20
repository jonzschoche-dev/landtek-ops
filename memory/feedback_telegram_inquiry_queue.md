---
name: feedback-telegram-inquiry-queue
description: "Telegram inquiries must be queued and asked ONE AT A TIME, in sequence, awaiting reply before firing the next — like a human assistant"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Leo (or any auto-fire path: deadline_sentinel, stage-intake, brief generator, manual prompts) must send at most ONE open inquiry at a time over Telegram. The next inquiry waits in queue until the current one is answered (or explicitly skipped / dismissed). Multiple parallel asks = cognitive overload = the human stops engaging.

**Why:** Jonathan, 2026-05-16: *"there should never be two messages sent by telegram as an inquiry at once they need to be answered one at a time and answered in sequence, this is the way a human works."*

A good legal assistant doesn't pepper the principal with five questions simultaneously. They ask one, wait, then ask the next. Conversation protocol matters. Today I violated this rule by firing the manual post-pretrial intake, the auto pre-intake for the May 18 demand letter, the daily brief digest, and the matters update — all separately, all asking for something. That's not assistance — that's noise.

**How to apply:**

1. **Single source of truth: `tg_inquiry_queue` table.** Schema:
   - id, kind (intake | brief | clarification | escalation), priority,
   - source_table (e.g., 'stage_intake_response'), source_id,
   - composed_message_html, composed_at, sent_at NULL, sent_message_id NULL,
   - status (queued | active | answered | skipped | superseded | expired)
   - response_text, responded_at

2. **At most one row at status='active' at any time.** Every fire path INSERTs at status='queued'. A single dispatcher (call it `tg_dispatcher.py`) wakes up every 1-2 min, checks if there's an 'active' row, and if not, promotes the next 'queued' row by priority + age.

3. **Send logic:**
   - Dispatcher pops the next queued item.
   - Sends the Telegram message, marks status='active', records sent_message_id.
   - Listens for replies (Telegram webhook OR poll updates API every 30s).
   - On reply: mark current active item as 'answered', store response_text, fire downstream side-effects (e.g., update stage_intake_response.items_received), then immediately promote the next queued item.

4. **Priority hierarchy:**
   - P0 (jump queue): legal-deadline OVERDUE-not-auto-completed alerts, security incidents.
   - P1: open intake from a deadline due in ≤3 days.
   - P2: daily brief, status updates.
   - P3: orphan-matter context requests.
   - P4: completeness audits.

5. **Coalescing:** Multiple inquiries about the same deadline/matter should be COMBINED into one message before queueing, not queued separately. Example: pre-intake + post-intake for the same matter = one combined ask.

6. **Aging:** A 'queued' item older than 48h gets promoted to 'expired' silently (not fired) and logged for review. Stale asks lose value.

7. **Anti-patterns to avoid:**
   - Sending the daily brief while an intake question is still unanswered → answer the open question first, brief waits.
   - Re-firing the same inquiry hourly → use the queue + active-row guard.
   - Including 5 separate "please reply about X" in one digest message → if it requires Jonathan to answer, it's an inquiry; if it's informational, it's a digest. They are different.

**Refactor queue (concrete):**
- `tg_inquiry_queue` schema (deploy_124 or similar).
- `tg_dispatcher.py` — runs on a 1-minute timer.
- Patch deadline_sentinel + stage-intake + daily-brief to INSERT into queue instead of calling `tg_send` directly.
- Add `/reply` and `/skip` Telegram command handlers so Jonathan can answer the active inquiry by tapping reply.

**Linked memories:**
- [[feedback_landtek_management_style]] — concise scheduling, not overwhelming barrage.
- [[feedback_reports_are_the_measure]] — clean output discipline.
- [[feedback_legal_status_awareness]] — stage-aware questions only.
