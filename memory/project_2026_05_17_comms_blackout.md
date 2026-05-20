---
name: 2026-05-17-comms-blackout-incident
description: Telegram inbound channel was cut off when n8n was decommissioned 2026-05-17; webhook never re-pointed; Don Qi and Jonathan replies silently dropped for ~48h
metadata: 
  node_type: memory
  type: project
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**INCIDENT 2026-05-17 → 2026-05-19 — Telegram communications blackout.**

When the legacy n8n Leo workflow was decommissioned on 2026-05-17 ([[feedback_legacy_bot_decommission]]), the Telegram bot's inbound webhook was NOT re-pointed away from the dead n8n endpoint `https://leo.hayuma.org/webhook/2fe01d2f-680c-47bd-86c6-7bb24893afb9/webhook`. Every reply from Don Qi (Administrator, telegram_id 8575986732) and Jonathan (Owner, 6513067717) was POST'd to a dead server and silently lost. No alerts fired because no one was monitoring the inbound side.

Compounding failure: `tg_inquiry_queue` had a P0 "one-active-at-a-time" rule, so a single inquiry sent at 05:58 UTC on 2026-05-19 got stuck `active` forever (no reply could arrive) and blocked every subsequent prompt for 8+ hours. ~5 high-priority items (daily digests, gap_alerts) backlogged behind it.

Don Qi as Administrator was uploading documents and asking questions during the blackout. He received zero acknowledgments or follow-ups. Jonathan only realized the blackout when he asked "when is Don Qi's next meeting" and discovered the lack of any system pings.

**Why:** Inbound and outbound were treated as separate concerns; the decommission checklist covered killing the n8n outbound spam but did not include re-routing the inbound webhook. The bot's webhook config lives in Telegram's servers, not in our repo, so it was invisible to grep + git diff.

**How to apply:**
- Any decommission of a service that owns a webhook MUST include either (a) repointing the webhook to the new consumer or (b) `setWebhook` to empty string to switch to polling, AS PART OF the decommission script
- BOTH inbound and outbound paths get a `comms_health` sentinel — never trust silent failure
- "Comms is up" requires: webhook URL is reachable OR polling consumer alive; AND last outbound sendMessage returned 200 within N minutes; AND a probe-reply round-trip works at least daily
- Inquiry queue's "one-active-at-a-time" rule must not block on a stale-active row — auto-expire `active` rows older than N hours (N=4 default) so the queue self-heals if a reply path breaks
- Any administrator-class contact (clients.role='Administrator') must be in the outbound recipient set for their case_file, not the hardcoded owner-only path that existed pre-2026-05-19

**Verbatim from Jonathan, 2026-05-19:** "how did this happen? this should never ever break the communicatrion was cut off. thats a huge failure catastrophic" and "we die when things like this happen". Treat comms-channel failures as P0 + business-critical going forward.
