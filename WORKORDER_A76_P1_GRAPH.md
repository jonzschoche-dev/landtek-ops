# Work Order — build the unified relationship graph (A76 P1): populate fact_edges from live carriers

**For:** executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). Grounded in `docs/RELATIONSHIP_EQUILIBRIUM.md` (deploy_847 — already written, grounded against live DB; READ IT FIRST). The "other part" of the system: the bot ingests + the headless brain answers, but the RELATIONSHIP EQUILIBRIUM (every interaction ripples through the fact/person/obligation web) has no graph to compute on. `fact_edges` exists with 0 rows; the carriers are scattered real tables. Build P1: populate the unified graph. P2–P4 (propagation, contradiction-wiring, tuning) come later, on top of a full graph.

## T0 — Audit the carriers (READ docs/RELATIONSHIP_EQUILIBRIUM.md §3–4 first)
Report, per edge type, the live source + row count + whether it's already in `fact_edges`:
- fact→fact: `fact_edges` (0 rows — EMPTY, this is the gap)
- fact→keystone: `keystones` (3) + `cross_matter_links` (3)
- person→matter: `doc_entities` / `matters` role cols
- obligation→deadline: `surfaced_deadlines` + pulse spine (no `obligations` table — confirmed)
- channel_user→client: `channel_users.mapped_client_code` (11)
- message→document: comms_artifact_sink output links (script, not a table yet)
- reply→message: `channel_messages.reply_to_id` (intra-channel)
- contradiction: `contradictions` (44 — detected, A65 owns arrow-of-time)
Report what's MISSING vs what exists. Build only the missing linkage.

## T1 — Populate fact_edges (the unified store)
Backfill `fact_edges` from the carriers above (deterministic, idempotent, re-runnable):
- fact→fact provenance/support from `matter_facts` source links.
- fact→keystone from `keystones` + `cross_matter_links` (A14 `proof_doc_id`-gated).
- person→matter role edges from `doc_entities` / `matters`.
- message→document edges: promote the sink's links into a `fact_edges`-style (or a `message_document_links`) table so they're queryable, not just script-local.
- conversation-derived facts (deploy_846 §5 ConversationDerivedFact) → edges once A78 lands; for now log as candidates.
This gives the engine a real N-hop ego-network to recompute on. Idempotent: re-run skips existing edges (content-hash or (src,tgt,type) unique).

## T2 — Isolation is a hard constraint, not a parameter (A5)
On every edge written: refuse any edge that would cross a client boundary (src client ≠ tgt client). The graph is per-client; cross-client edges are NEVER weighted, only refused. Enforce in the write path (the same A5 wall the projection/sink already use).

## T3 — Truth-test (negative-tested)
`truth_tests/test_relationship_graph.py`:
- `fact_edges` populated after backfill (count > 0, matches carrier counts).
- A cross-client edge attempt → refused (negative-bite, A5).
- Idempotent: second backfill adds 0 duplicates.
Wire into `run_all.py`.

## T4 — Prove on real data, honestly
- Backfill against a matter with real facts (e.g. MWK-ARTA-1891, 91 verified) → report edge count, types, 0 cross-client leaks.
- Show one ego-network query: "give me the N-hop neighborhood of fact X" returns the expected related nodes.
- Report the honest gap: `fact_edges` is now FULL but PROPAGATION is not yet wired (P2) — the graph exists, the engine doesn't yet recompute on inbound. Name P2 as the next build.

## Guardrails
- Extend/populate `fact_edges` (schema exists) — do NOT invent a third graph store (kg_triples stays; unify INTO fact_edges, don't parallel it).
- Deterministic, idempotent, re-runnable. A5 hard constraint on every edge.
- $0, no LLM in the backfill. Reuse carrier tables; no fork.
- No phantom enforcement — A76 stays 🟡; this builds its P1 floor, negative-tested. Ontology desk promotes when truths green.

## Close-out
A59 work order to terminal state. T0 audit report verbatim. Final line: "unified graph populated (N edges, 0 cross-client); P2 propagation is the next build." Hand to the P2 prompt.

## Invocation
> Execute `WORKORDER_A76_P1_GRAPH.md` from `/root/landtek`. READ docs/RELATIONSHIP_EQUILIBRIUM.md first. P1 only: populate `fact_edges` from the live carriers (fact→fact, fact→keystone, person→matter, message→document, conversation-derived). Audit what exists vs missing (T0). A5 hard constraint — refuse cross-client edges. Idempotent backfill + truth-test. Do NOT build propagation (P2) or contradiction-wiring (P3) yet. $0. The unified graph is the missing organ the equilibrium computes on.
