# COMM-AGENT-MAX — Shadow Soak & Matter-Disambiguation

**Status (2026-07-12):** soak LIVE (deploy_892); disambiguation resolver STUBBED + tested, not yet wired.

## The soak (Task 1)
The sentient web (L1 spine → L2 A76 propagate → L3 A79 clamp → L4 emission) is fully wired in **shadow**.
L4 (`comm_agent_max.handle_chat_event`) is **not inline-wired** to the live reply path (the working
leo_service/n8n flows are untouched), so a **driver** feeds it:

- `scripts/comm_agent_soak.py --tick` — drives NEW inbound `channel_messages` through `handle_chat_event`
  (SHADOW: emits nothing; writes `comm_agent_shadow` rows to `channel_audit` + `propagation_log`), then
  summarizes per-role. Idempotent via `comm_agent_soak_state` cursor. Read-only w.r.t. production.
- `landtek-comm-agent-soak.timer` — every 15 min. Summary → `notifications/comm_agent_soak_summary.txt`.
- `landtek-graph-refresh.timer` — every 30 min, refreshes `mv_relationship_graph_structural` (the
  materialized traversal surface; keeps ego queries at ~0.1–0.6s).

**Load-bearing invariant (checked every tick):** `would_clamp=True ⇒ next_action='hold_for_operator'`.
Any violation → `ontology_reject('A79_CLAMP_NOT_HELD', …)` into `holes_findings`. First tick: **0 violations**.

**First summary (24 inbound):** counterparty 3 / 100% clamp / held · client 7 / 0% clamp / would_send ·
counsel 3 · unresolved 9 fail-closed · internal 2. avg internal ego 1565 (client-bearing roles). CLEAN.

Read it: `python3 scripts/comm_agent_soak.py --status` or `cat notifications/comm_agent_soak_summary.txt`.

## Matter-disambiguation (Task 2 — designed, NOT wired)
Today a chat anchors to the client's **most fact-rich** matter (view `chat_context` edge). That's
client-correct but not matter-specific. `comm_agent_max.resolve_chat_matter(cur, msg_id, client)` is the
resolver ladder that fixes it:
1. **keyword** — message text vs the client's matter identifiers (`_matter_tokens`, e.g. `ARTA-1891`).
2. *(deferred)* sender's most-recent matter context (`propagation_log`/`leo_interactions` recency).
3. **fallback** — the biggest matter (today's behavior).

Proven by `truth_tests/test_matter_disambig.py` (3/3): a message naming a docket resolves to THAT matter,
generic text falls back. **Not wired into the graph anchor yet** — deliberately, to avoid mutating the
live traversal surface mid-soak. The post-soak increment replaces the view's biggest-matter `LATERAL`
with `resolve_chat_matter`'s output → smaller, context-exact ego.

## Post-soak decision
After 24–48h clean: review `comm_agent_shadow` aggregates (esp. how often `fallback_biggest` fires vs
`keyword` — the empirical case for disambiguation), then either land disambiguation or flip A79 enforce.

## Desk hand-off (ONTOLOGY.md A76 — not edited here)
A76 row: note the new `chat_context`/`chat_sender`/`in_matter` edges + the materialized structural graph
(`mv_relationship_graph_structural`, refreshed) as the internal traversal surface; matter-disambiguation
is the pending precision refinement; the output-disclosure-classification invariant remains pending.
