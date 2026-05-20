---
name: feedback-leo-must-never-go-offline
description: Leo Telegram bot is business-critical and must never go offline. All n8n workflow changes require functional staging smoke test + post-deploy health monitoring + automatic rollback path.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

Leo (the Telegram bot at @LeoLandTekBot, n8n workflow `vSDQv1vfn6627bnA`) is a business killer if offline. Even brief outages are unacceptable.

**Why:** On 2026-05-15 at 23:11 UTC, deploy_072 (auth gate) was applied to prod with only structural staging validation (connection graph + SQL-by-hand). The newly-added Postgres nodes used `typeVersion: 2.4` with a parameter shape that triggered an internal n8n bug (`dbTime.getTime is not a function`). The error loop blocked workflow activation, which prevented the Telegram webhook from being registered with Telegram's servers. Jonathan's messages silently queued at Telegram (`pending_update_count > 0`) with nowhere to deliver. Leo appeared dead. Recovery required manual: workflow snapshot restore + n8n container restart + manual `setWebhook` call. Total downtime: ~10 minutes.

**How to apply:** For ANY change to the n8n workflow (`workflow_entity`, `workflow_history`, or webhook-touching code):

1. **MANDATORY real staging smoke test before prod** — not just structural validation:
   - Bring up `/root/landtek/staging` stack with latest pg_dump restore
   - Apply the patch to staging
   - Watch `docker logs --follow n8n-staging` for 30+ seconds; must see "Activated workflow" without error spam
   - Fire a synthetic Telegram-shaped webhook into staging n8n via the registered `webhook_entity.webhookPath`
   - Verify `execution_entity` shows status='success'
   - Only then promote to prod

2. **Pre-deploy snapshot is non-negotiable** — already done via `/root/landtek/snapshots/`. Confirm it exists before patching.

3. **Post-deploy health check (within 60s of prod apply)**:
   - Verify Telegram `getWebhookInfo.url` matches `https://leo.hayuma.org/webhook/<path>`
   - Verify `pending_update_count == 0`
   - Verify n8n container logs have no error spam in the last 60s
   - If ANY of these fail → immediately roll back from snapshot, don't troubleshoot in prod

4. **Auto-monitoring (planned: deploy_073)** — a watchdog that detects webhook unregistration + n8n error patterns + execution silence and pages Jonathan via Telegram.

5. **Bias toward not touching the prod workflow at all** when possible — out-of-band tools (the Flask service, the dashboard, the database) carry zero risk to Leo and should be preferred for new features.

**Inviolable:** never run `patch_workflow_dual()` against prod without completing steps 1-3 above. If staging is unavailable for any reason, the deploy waits.

Related: [[feedback-no-invented-schemas]] (don't guess n8n internals), [[feedback-infer-dont-ask]] (use the knowledge base, but not as a substitute for behavioral testing).
