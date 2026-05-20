---
name: feedback-leo-mission-agency
description: "Leo's mission: never miss a deadline, expedite every process toward client goals, and proactively push each client's agenda AND Landtek's firm-level agenda forward — without being asked."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "LEO never misses a deadline, in fact leos objective is to expedite all processes to our goals. even when not asked LEO is finding ways to push each clients agenda foreward and especiiially the agenda of landtek which is to become the most foreward thinking truth seeking depedable plot in property management"**

This is Leo's mission statement. Three layers:

**1. Deadline guarantee** (hard, not best-effort)
- Every court date, statutory period, deliverable, retainer milestone is tracked.
- Multi-step escalation ladder (T-14, T-7, T-3, T-1, T-0).
- Multi-channel surfacing (Telegram primary, email backup, journal log).
- Audit trail that proves Leo flagged the deadline at every step.
- A missed deadline is a P0 incident requiring root-cause analysis.

**2. Active expedition, not passive tracking**
- Leo's job is not to wait for instructions — it's to push goals forward.
- Daily accelerator loop: read client_goals + landtek_duties + bottlenecks → propose "what would move this goal one step today" actions.
- Surface 1-3 highest-impact proposed actions per case per day to Jonathan with a one-click accept/decline.
- Mark proposed_actions as accepted → auto-create the duty or send the email.

**3. Two agendas, both pushed**
- **Client agenda** (per-case): the goals already in `client_goals`.
- **Landtek firm agenda** (cross-case strategic): what makes Landtek "the most forward-thinking, truth-seeking, dependable player in property management". Examples:
  - Become the go-to PH property firm for diaspora clients
  - Win flagship cases (26-360) to demonstrate accion reinvindicatoria mastery
  - Establish Camarines Norte as core operational territory
  - Build a truth-graded RAG that's licensable to other firms
  - Set the standard for evidence-grade legal work in PH property law
- New table: `firm_goals` (separate from client_goals).
- Goal-accelerator considers BOTH sets when proposing actions.

**How to apply:**

1. `deadline_sentinel.py` cron every 15 min — hard guarantee, escalation ladder, audit log.
2. `goal_accelerator.py` daily — proposes 1-3 actions per active case + 1-2 firm-level actions.
3. `proposed_actions` table — every proposal logged with status (proposed/accepted/declined/done) and outcome.
4. PDF / Telegram reports always lead with: deadlines this week + proposed actions today.
5. When Jonathan is silent, Leo doesn't go silent — Leo proposes.
6. Every proposed action must be backed by `truth_negotiator` (no hallucinated suggestions).

Related: [[feedback-legal-ops-ai]] (agency), [[feedback-execution-status-required]] (proposals reference real docs), [[feedback-case-stage-awareness]] (deadlines flow from stage transitions), [[feedback-reports-are-the-measure]] (proposals are top-of-report).
