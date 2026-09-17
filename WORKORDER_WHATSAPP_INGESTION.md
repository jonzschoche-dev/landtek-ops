# Work Order — WhatsApp Business: lossless media + conversation ingestion into the corpus

**For:** executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). Grounded against the live code: `scripts/whatsapp_channel_bridge.py` (outbound drain + token-gated, deploy-era), the live inbound webhook (`/api/channel/whatsapp`, push-based), and the proven `comms_artifact_sink.py` (deploy_847/849, media-type-agnostic, A5 resolve-or-hold). WhatsApp Business API is the chosen client-facing channel (legitimate, sink-ready, NOT a personal-number scrape).

## Goal
Regular, push-based ingestion of SPECIFIC client WhatsApp conversations + their media + extracted data into the corpus — client-isolated, lossless, zero manual filing. Must be possible and efficient: **webhook-push, not polling.** Messages arrive as sent; media downloads immediately (Cloud API media URL expires ~15 min, so download on receipt, not later).

## T0 — Ground the inbound path (READ FIRST)
- Locate the live `/api/channel/whatsapp` webhook handler (the inbound side — the bridge file only covers outbound `send()`). Read how it currently logs inbound `channel_messages` and whether it handles `messages[x].type == 'document'|'image'|'audio'|'video'` (the media payload carries a `media_id` + `media_url`/`id`, NOT the bytes).
- Confirm `WHATSAPP_PHONE_NUMBER_ID` + `WHATSAPP_API_TOKEN` are the env keys (bridge uses them). Token IS the external switch (A26) — provisioning opens the channel.
- Note: WhatsApp is **1:1 only** (Business API cannot read groups). Each client messages the business number individually; the coordinator resolves each `wa_id` → one client_code (A25). "Conversation" = the 1:1 thread per client.

## T1 — Wire media ingestion to the sink (mirror deploy_849's Messenger fix)
In the inbound webhook handler, for every inbound message carrying media (`media_id`):
1. Download bytes via Cloud API: `GET https://graph.facebook.com/v18.0/{media_id}?phone_number_id=...&access_token=...` → follow the `url` → stream bytes. **Do this on receipt** (URL is short-lived).
2. Resolve the sender's `wa_id` → `client_code` (`platform_coordinator.client_of`, A25 resolve-or-hold — never guess).
3. Hand `(raw_bytes, filename, mime, client_code, 'whatsapp', channel_message_id)` to `comms_artifact_sink.ingest_artifact` — exactly the Messenger pattern. Sink does dedup + OCR/transcribe-pending + ledger + A5 hold.
4. Fix the same drop-bug Messenger had: a media-only message (no text body) must NOT be skipped by a `if not text: continue` guard. `_log_inbound` must return the row id so the artifact links back.

## T2 — Conversation data → corpus (the "datea from those conversations" half)
Beyond media, extract structured DATA from the conversation text into the corpus:
- Dates/deadlines: route inbound text through `deadline_extractor` (proposed status, A68 — never promote historical prose to forward deadline). Feed the `surfaced_deadlines` / obligation spine.
- Facts: when A78 lands (verified-fact integrity), conversation-derived facts enter `matter_facts` with provenance `chat` (grounded-or-not-verified, per deploy_846 §5 ConversationDerivedFact). Until A78 is enforced, log conversation-derived candidates but do NOT promote to VERIFIED without basis.
- Identity: ensure each `wa_id` is resolved to a client_code (coordinator --resolve); unresolved → held, surfaced for operator assignment (the JJ pattern).
This is push-based: each inbound message triggers extraction, not a nightly crawl.

## T3 — Truth-test (negative-tested, like test_lossless_comms_intake.py)
`truth_tests/test_whatsapp_ingestion.py`:
- A media inbound message with a `media_id` → a `documents` row (or held/quarantined) — zero silently dropped. Mirror the Messenger 3/3.
- A `wa_id` with no client binding → held, no cross-client leak (A5).
- Negative-bite: inject a media message with no document row → RED.
Wire into `run_all.py`.

## T4 — Prove on real data, honestly
- After the token is provisioned (operator action — A26 switch), send a real WhatsApp from a test client (JJ) to the business number with a photo + a "deadline is July 30" text.
- Confirm: photo → `documents` (ingest_source=comms_whatsapp, processing_mode=ocr_pending) under JJ's client_code; text → deadline extracted (proposed); no drop; no cross-client.
- Report the false-negative risk: Cloud API media URL expiry (must download on receipt — confirm the handler does, not at poll time), and token-provisioning is operator-gated.

## Guardrails
- WhatsApp Business API ONLY — never a personal-number scrape (ToS/ban risk; explicitly out of scope).
- Push/webhook, not polling — download media on receipt (URL expiry).
- Reuse `comms_artifact_sink` (no fork) + `platform_coordinator.client_of` (A25) + `deadline_extractor` (A68). Mirror the Messenger adapter exactly.
- A5 resolve-or-hold, content-hash dedup, OCR/transcribe-pending, degrade→quarantine. $0/sovereign OCR (local Ollama).
- Token-gated + degrade-gracefully (bridge already is) — safe to run before provisioning; provisioning opens the channel.
- No phantom enforcement — ontology desk promotes A77/A78 when truths green.

## Close-out
A59 work order to terminal state. Report: the inbound webhook location found in T0, the media-download-on-receipt proof, the 3/3 truth-test, and the real-data proof (JJ photo + deadline). Final line: "WhatsApp Business ingests losslessly + extracts conversation data; client X's thread is now auto-filed, zero manual step."

## Invocation
> Execute `WORKORDER_WHATSAPP_INGESTION.md` from `/root/landtek`. Wire WhatsApp Business inbound (webhook) media → comms_artifact_sink (mirror Messenger deploy_849): download on receipt, resolve wa_id→client_code (A25), never drop. Extract conversation dates via deadline_extractor (A68), facts via A78 (chat, grounded-or-not). Truth-test 3/3 like Messenger. Push-based, NOT polling. Business API only — no personal scrape. Token-gated (A26). $0 OCR.
