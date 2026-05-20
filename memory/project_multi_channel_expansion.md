---
name: project-multi-channel-expansion
description: "Leo's brain (n8n workflow + leo_tools Flask + truth_negotiator + classify_*) is platform-agnostic. Telegram is the current adapter. Other channels (WhatsApp, Slack, email, web chat, SMS, voice, app) can be added by writing per-channel adapters that hit the same core APIs."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "can we launch leos brain into other platforms besides telegram?"**

Yes — Leo's intelligence is in three places, none of which are platform-specific:

1. **n8n workflow** ("Leos Workflow") — orchestration, AI Agent, tool nodes
2. **leo_tools Flask service** (port 8765) — /api/* endpoints anyone can call
3. **Database + classifiers + truth_negotiator + memory** — all reachable via Postgres + scripts

Telegram is a thin adapter that:
- Receives messages via webhook → posts to n8n's Telegram Trigger
- Sends responses via Telegram Bot API

**Platforms we can add (priority order for PH market):**

| Platform | Effort | Value | Notes |
|---|---|---|---|
| **WhatsApp Business API** | medium | ⭐⭐⭐⭐⭐ | PH primary messaging — most clients use it; need Meta verification + WABA provider (360dialog, Twilio, MessageBird) |
| **Web chat widget** | low | ⭐⭐⭐⭐ | Embed on landtek.com / client portal; useful for first-contact, lead capture |
| **Email reply bot** | low | ⭐⭐⭐⭐ | Leo replies to client emails directly; reuses existing Gmail integration |
| **SMS (Twilio/Globe/Smart)** | medium | ⭐⭐⭐ | Wide PH reach including non-smartphone users; cheaper than voice |
| **Voice (Twilio Voice + STT/TTS)** | high | ⭐⭐⭐ | Phone-based Leo — clients can call and converse with him |
| **Slack** | low | ⭐⭐⭐ | Landtek internal team ops, partner-firm collaboration |
| **iOS/Android app** | very high | ⭐⭐⭐⭐ | Branded LandTek app — investor pitch material |
| **Microsoft Teams** | low | ⭐⭐ | Enterprise client integration |
| **Public REST/GraphQL API** | low | ⭐⭐⭐⭐⭐ | Sells Leo as licensable product to other firms |

**Architecture pattern for adding a channel:**

1. **Inbound adapter** — webhook/poller that receives messages, normalizes to `{sender_id, sender_name, channel, text, timestamp, attachments}`, pushes to n8n via HTTP trigger.
2. **Channel routing table** — `channels {channel_name, webhook_url, auth_secret, default_locale}` and `channel_users {channel, channel_user_id, mapped_client_code, mapped_operator}`.
3. **Outbound adapter** — Leo's response normalized to channel-specific format (Telegram HTML / Slack mrkdwn / WhatsApp markdown / email HTML / SMS plain).
4. **Identity bridge** — same Jonathan-id reaches Leo across all channels; same client across email + WhatsApp.

**Recommended first add: WhatsApp Business API**
- 95%+ of PH clients use it
- WABA provider needed: 360dialog, Twilio, MessageBird, or Vonage
- Meta Business Verification (1-2 weeks)
- Then it's an inbound webhook + outbound API call — same pattern as Telegram

**For Leo's licensing play (firm_goal #4):**
A clean REST API (`/api/v1/leo/chat`, `/api/v1/leo/verify`, `/api/v1/leo/extract`) becomes the licensable product. Each licensed firm gets API keys + a quota.

**How to apply:**
- Treat all I/O as adapters — never put business logic in the Telegram path that doesn't also work via Flask /api/*.
- Build `channels` table now to formalize multi-channel routing.
- Prioritize WhatsApp + web widget + email for PH client reach; REST API for licensing.

Related: [[feedback-legal-ops-ai]] (agency = serving clients wherever they are),
[[feedback-leo-mission-agency]] (firm goal: licensable platform).
