---
name: feedback-legacy-bot-decommission
description: "Legacy autonomous bots/timers/Leo n8n workflow that bypassed the inquiry queue spammed Jonathan's Telegram with hallucinations and repetitive findings; all decommissioned 2026-05-17"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Only the consolidated meta-agent + tg-dispatcher + queue may send to Jonathan's Telegram. Any new service that needs to surface info MUST enqueue via `tg_inquiry_queue` — direct `tg_send_raw` is reserved for explicit user-requested reports (slash commands, on-demand digests). Identical findings from cycle to cycle must NOT re-fire.

**Why:** Jonathan 2026-05-17 showed actual Telegram output: 8+ messages of noise including
  • 4 identical hourly `systems-analyzer.timer` digests with same findings
  • Leo n8n workflow (active=t, isArchived=f despite CLAUDE.md claiming "HARD-DISABLED") hallucinating answer interpretations ("Don Qi asked about settlement conference June 2" — fabricated)
  • Repetitive bot-style chat responses bypassing the atomic-inquiry queue

**Decommissioned 2026-05-17 (services + timers stopped and disabled):**
- `leos workflow` (n8n id vSDQv1vfn6627bnA) — set active=false, isArchived=true, n8n container restarted
- `systems-analyzer.timer` — superseded by meta-agent (which uses the consolidated queue)
- `landtek-orchestrator.timer` — legacy autonomous cycle
- `landtek-proactive.timer` — legacy
- `landtek-continuous.timer` — legacy
- `leo-watchdog.timer` — was auto-restarting Leo on failure (the loop closer)
- `landtek-digest.timer` — superseded by `daily-digest.timer` (running daily_strategic_digest)
- `landtek-verify.timer` — legacy
- `landtek-conflict.timer` — legacy

**Preserved (active, consolidated):**
- `tg-dispatcher.service` (continuous, 45s) — sole authorized outbound Telegram path
- `meta-agent.timer` (hourly) — 26 invariants → ONE consolidated gap_digest into queue
- `auto-promoter.timer` (2h) — orphan matter promotion
- `deadline-sentinel.timer` (15m) — stage-aware deadline + atomic intake firing
- `gmail-watcher.timer` (15m) — INBOX + SENT two-stream pull
- `drive-sync.timer` (30m) — md5 fast-path
- `client-history-scan.timer` (30m) — append-only ledger
- `daily-digest.timer` (7AM Manila) — daily strategic digest
- `improvement-agent.timer` (Mon/Wed/Fri/Sun 22:00) — codebase audit

**How to apply going forward:**

1. **No new direct-Telegram paths.** Any new generator that needs to notify must:
   - INSERT into tg_inquiry_queue with appropriate kind + priority
   - Or use tg_send_raw ONLY for synchronous responses to user slash commands
   - NEVER fire on a timer directly to Telegram

2. **Dedup repeated findings.** Meta-agent already does this via `notes = 'digest:<sorted invariant IDs>'` so identical failure-sets don't double-queue. Any new audit-style cron must follow the same pattern.

3. **CLAUDE.md "Leo hard-disabled" updated.** The prior assertion (May 12) was correct in intent but stale — Leo workflow had been re-enabled at some point. Verified disabled today; if it ever needs to be reactivated, only under explicit instruction with hallucination guardrails fully audited.

4. **goal_accelerator.py** still has a direct `requests.post` to Telegram path; needs queue migration (next deploy).

5. **Audit before adding any new timer.** Verify it doesn't duplicate meta-agent / auto-promoter / deadline-sentinel functionality. Consolidation > sprawl.

**Linked memories:**
- [[feedback_telegram_inquiry_queue]] — ONE active inquiry at a time
- [[feedback_atomic_inquiry_with_followups]] — one atomic question per fire
- [[feedback_output_no_hallucination_discipline]] — hallucinations are existential
- [[feedback_classify_by_subject_not_by_actor]] — Leo workflow was inferring user-intent without subject anchors
