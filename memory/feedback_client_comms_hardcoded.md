---
name: client-comms-hardcoded-p0
description: "Client-comms channels must be hardcoded into every sender, not dynamically looked up — comms failures kill the business"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Client communications channels must be hardcoded directly into every outbound sender. No DB lookup, no env-file fallback, no webhook dependency, no n8n indirection. The list of recipient Telegram chat_ids for each case_file lives as a Python constant at the top of every sender script.**

**CRITICAL — audience separation:** Hardcoding the recipients is necessary but NOT sufficient. Every outbound message has an audience: `ops` (operator only — Jonathan), `client` (administrator/client only — Don Qi for MWK-001), or `both`. Default to `ops` when in doubt. Internal ops digests (meta-agent gap_alerts, daily accelerator picks, debug dumps, data-quality probes, gmail triage summaries) MUST NEVER reach a client. Verbatim from Jonathan 2026-05-19 after a gap_alert leaked to Don Qi: *"there should never be a message like this sent to our client."* The taxonomy lives in `/root/landtek/comms_recipients.py` (KIND_AUDIENCE dict) — every new inquiry `kind` must be classified before being sent.

Authoritative recipient table (hardcode this in every script that sends):

```python
# /root/landtek/comms_recipients.py — single source of truth, dirt-simple
MWK_001_RECIPIENTS = [
    ("Jonathan Zschoche", "6513067717"),  # Owner / Principal
    ("Don Qi Style",      "8575986732"),  # Administrator (MWK-001)
]
# When in doubt, send to BOTH. Never to neither.
```

Every sender (`tg_dispatcher`, `gmail_watcher`, `deadline_sentinel`, `goal_accelerator`, `meta_agent`, `daily_digest`, future channels) imports this constant. Even if the DB is down, the env file is corrupted, or the webhook is misconfigured, the hardcoded list still sends.

**Why:** On 2026-05-17 the legacy n8n was decommissioned, the bot's webhook silently stayed pointed at the dead endpoint, and BOTH the administrator (Don Qi) and the owner (Jonathan) received zero communications for ~48 hours. See [[2026-05-17-comms-blackout-incident]]. Jonathan's exact words: *"no one has time for these failures communications with clients need to be hard coded"* and *"we die when things like this happen"*. Comms failure = client trust collapse = revenue death.

**How to apply:**
- New client onboarded → first action: add their (name, telegram_id) tuple to `comms_recipients.py` as a Python constant. NOT just to the DB. The DB is a convenience; the constant is the contract.
- Every outbound sender must import the constant for the case_file it's about to send for. No dynamic lookup. No `SELECT telegram_id FROM clients WHERE ...`.
- Adding a new recipient is a code change → committed → visible in git diff → cannot be silently lost.
- Probe-pings (round-trip test sends) run hourly to every hardcoded recipient on every active case; an inbound ACK is required at least daily or a P0 alarm fires.
- Webhooks are forbidden for client-facing inbound. Use long-polling consumers that we own, can restart, and that fail loudly.
- Comms-channel health is a Tier-1 invariant in the meta-agent — equal weight to deadlines.
