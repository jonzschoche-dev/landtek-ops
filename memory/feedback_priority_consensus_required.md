---
name: feedback-priority-consensus-required
description: "Priority of any pending event must reach consensus across Leo + Jonathan + the client; Leo's job is to actively surface disagreements and drive to consensus, not silently pick"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Every active deadline / matter / pending event carries THREE priority signals — Leo's (inferred from rules), Jonathan's (professional judgment), and the client's (their stated concern). The canonical priority is the **consensus** across all three. When 2/3 agree but one dissents, Leo surfaces the disagreement via the inquiry queue. When 1/3 has spoken, Leo asks the missing parties before acting on Leo's inference alone.

**Why:** Jonathan 2026-05-17: *"Leo, the client and Jonathan should have consensus on what the highest priority issues are. Leo should look for consensus."*

The failure pattern: Leo unilaterally ranked the May 18 demand letter (admin) above the June 2 mediation (case-defining) because the demand letter's date was closer. Neither Jonathan nor Patricia ever confirmed that admin > substantive. Leo's inference contradicted the client's actual concern — and Leo acted on it.

**How to apply:**

1. **Three priority signals tracked per deadline / matter:**
   - `priority_leo` — Leo's tier inference (P0-P5) based on deadline_type, stage, and goal-linkage
   - `priority_jonathan` — set when Jonathan explicitly confirms or overrides via Telegram or notes
   - `priority_client` — set when the client (Patricia / Allan / future) explicitly states urgency in a chat or filing
   - `priority_consensus_state` — one of:
     - `leo_only` — only Leo has spoken; Leo must ask Jonathan + client
     - `jonathan_confirmed` — Jonathan agrees with Leo; client not heard
     - `client_confirmed` — client agrees with Leo; Jonathan not heard
     - `full_consensus` — all three aligned (canonical priority)
     - `disputed` — explicit disagreement on file; resolution required before action

2. **Driving consensus (Leo's active responsibility):**
   - On any new deadline: Leo's inference is logged as `priority_leo`. Status starts `leo_only`.
   - Within 24h of creation: Leo enqueues a TG inquiry to Jonathan asking "is this priority {tier} correct?" — atomic, one-question.
   - When Jonathan responds: `priority_jonathan` set, state moves to `jonathan_confirmed` or `disputed`.
   - Within 7d (or before the deadline approaches T-14): Leo asks the client a low-friction question (only if the client is reachable + the matter affects them directly).
   - When client responds: `priority_client` set, state advances.
   - All three aligned → `full_consensus`. Locked in until someone re-opens.

3. **Disagreement protocol:**
   - When two priorities disagree, surface BOTH in the digest and enqueue a one-shot consensus-ask: "Leo says P0 (case-defining mediation); your message implied P4 (administrative). Which is canonical?"
   - Do NOT silently average or pick. Surface the disagreement plainly.

4. **Anti-pattern:**
   - ✗ Daily digest leveraging "today's highest-priority move" without checking consensus state.
   - ✗ Marking a deadline complete based on Leo's inference alone when client hasn't confirmed it ever existed.
   - ✗ Ranking by date proximity (see [[feedback_priority_is_goal_weighted_not_date]]).

5. **Implementation queue:**
   - case_deadlines schema: priority_leo, priority_jonathan, priority_client, priority_consensus_state, priority_history (jsonb audit log).
   - matters schema: same fields at matter level for ROLE OF MATTER priority.
   - deadline_sentinel: only fires intakes / pre-event escalations on items in state ≥ `jonathan_confirmed`. For `leo_only` items, fire a CONSENSUS-ASK first.
   - daily_strategic_digest: surface consensus state on every event. "Today's leverage move" only considers items in `full_consensus` or `jonathan_confirmed`.
   - Telegram `/priority` slash command — Jonathan can confirm/override priority of any deadline by ID.

**Linked memories:**
- [[feedback_priority_is_goal_weighted_not_date]] — tier scheme
- [[feedback_landtek_management_style]] — every event carries goal-link
- [[feedback_atomic_inquiry_with_followups]] — consensus asks are atomic
- [[feedback_legal_status_awareness]] — substance > labels
- [[feedback_output_no_hallucination_discipline]] — never assume client consensus
