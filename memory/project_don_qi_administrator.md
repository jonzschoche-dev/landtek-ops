---
name: don-qi-administrator-mwk-001
description: Don Qi Style is the Administrator of MWK-001 (Heirs of Mary Worrick Keesey estate); telegram_id 8575986732; authorized client contact
metadata: 
  node_type: memory
  type: project
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Don Qi Style (Telegram 8575986732) is the Administrator of the MWK-001 estate** (Heirs of Mary Worrick Keesey). Authorized to receive case communications and upload documents on behalf of the estate. Persisted in:
- `clients.id=9` — role='Administrator', primary_case_file='MWK-001', authorized=true
- `entities.id=2632` — canonical_name='Don Qi Style', role='Administrator', affiliation='Heirs of Mary Worrick Keesey (MWK-001)', provenance_level='verified'

**Why:** Jonathan confirmed verbally on 2026-05-19 after noting that Don Qi was receiving no Telegram messages or responses from Leo. The system was hardcoding all outbound to Jonathan's chat_id (6513067717), with no path to Don Qi — meaning the administrator was operating blind despite uploading documents and asking questions.

**How to apply:**
- Any outbound MWK-001 notification (new email arrives, new doc uploaded, court update, deadline reminder, request for context) should route to BOTH Jonathan AND Don Qi unless Jonathan specifies otherwise.
- When Don Qi uploads a file, Leo acknowledges to him (not just Jonathan) and asks his clarifying questions back to him.
- Don Qi's name in chat = canonical actor "Don Qi Style" (entity id 2632), NOT a Balane or other family-group member.
- See related: [[feedback_telegram_inquiry_queue]] (one-at-a-time rule now needs a per-recipient queue), [[feedback_legacy_bot_decommission]] (only meta-agent + tg-dispatcher may send — must be patched to read clients.telegram_id, not hardcode).

**Implications still TODO** (as of 2026-05-19):
- `gmail_watcher.py:26` and `tg_dispatcher.py:25` both hardcode Jonathan's chat_id; need patch to fan out by case_file → clients.telegram_id
- `tg_inquiry_queue` schema has no `recipient_telegram_id` column → "one active inquiry at a time" rule currently applies globally and would block per-administrator flow; needs per-recipient scoping
