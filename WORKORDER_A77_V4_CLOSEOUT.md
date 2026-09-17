# Work Order — close the owner-gate class: V4 amendment + hold-sweep (A77 completion)

**For:** executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). Follows deploy_870 (A77/A78 hardened at the two main writers:
harvest_facts + verify_worker). Claude's close-out flagged the class is NOT yet closed: the writer
gate covers harvest_facts + verify_worker, but **decipher_matter / reconciler / load_issue_spine /
source_read_facts / n8n / ad-hoc SQL** still write facts without the owner gate. 152 open
`unresolved_doc_owner` rows are the backlog. This order closes the class + sweeps the held backlog.

## T0 — Inventory the exposed write paths (READ FIRST)
grep every writer of `matter_facts` / `kg_triples` / `knowledge_graph_triples` across the repo:
decipher_matter.py, reconciler*.py, load_issue_spine.py, source_read_facts.py, any n8n code node
that INSERTs facts, and ad-hoc SQL in migrations that writes verified facts. Report which already
consult `ingest_gate.owner_gate` (deploy_870) vs which bypass it. The goal: every non-operator fact
write passes the owner gate.

## T1 — V4 amendment (the desk's call, implement the recommendation)
deploy_870's close-out recommended: treat a NULL-resolving cited-doc owner as HOLD/violation for
non-operator writers (or add a NULL-owner V-check). Implement ONE of:
- (a) Extend `ontvv_v3` (or add `ontvv_v4`) so a fact citing a doc whose owner is unresolvable
  (the V4 `IS NOT NULL` pass on NULL owner is the loophole) → HOLD for non-operator writers.
  Operator writes may still resolve NULL (legacy/operator-attested facts).
- (b) Add a NULL-owner V-check (`ontvv_client_isolation` variant) covering the class.
Implement (a) if the trigger can distinguish writer role; else (b). Either way: non-operator writes
with unresolvable-doc-owner are refused at the DB, not just at harvest_facts.

## T2 — Wire the remaining writers through ingest_gate
For each path in T0 that bypasses the gate: route its fact writes through `ingest_gate.owner_gate`
+ `conflicts_with_verified()` (reuse deploy_870's modules — no fork). n8n code nodes that INSERT
facts must call the gate via a wrapper (or the V4 trigger covers them, preferred). Ad-hoc migration
SQL that writes verified facts must either resolve owners or be flagged.

## T3 — Hold-sweep of the 152 backlog
The 1172/1177 + 1176/1180 facts frozen by deploy_870 are READ-ONLY honored (not auto-mutated).
Sweep the 152 `unresolved_doc_owner` rows: for each, attempt owner resolution (coordinator.resolve
on the doc's cited client/matter); if resolvable → re-validate the held facts; if still unresolvable
→ keep held, surface to operator (a work_order / holes_findings) for manual disposition. Never
silently delete or re-home. Report the sweep result (X resolved, Y still held for operator).

## T4 — Truth-test (negative-tested, extend deploy_870's)
Add to `test_ingestion_fidelity.py`: a fact written via decipher_matter / reconciler (a formerly
exposed path) citing an unresolvable-doc-owner → refused/held (negative-bite). Confirm the 7
deploy_870 assertions still green. Wire into `run_all.py`.

## T5 — Prove on real data, honestly
Run the sweep on the live 152 backlog; report resolution rate. Confirm a formerly-exposed writer
(decipher_matter or reconciler) now refuses an unresolvable-owner fact in a dry run. Report the
false-positive surface (legit facts held by the stricter V4 — visible, recoverable).

## Guardrails
- Reuse deploy_870's `ingest_gate` + `contradiction.py` — no fork, no second gate.
- A5 isolation: owner-unresolvable ⇒ HOLD, never guess, never silently drop.
- Operator writes may still resolve NULL (legacy facts) — only NON-operator writes are gated harder.
- Read-only honored: frozen facts stay frozen; sweep surfaces, doesn't mutate.
- No phantom enforcement — ontology desk promotes A77 when truths green.

## Close-out
A59 work order to terminal state. T0 inventory report + sweep result. Final line: "owner-gate class
closed (all fact writers gated); N backlog resolved, M held for operator." Hand the hold-sweep
disposition to the operator.

## Invocation
> Execute `WORKORDER_A77_V4_CLOSEOUT.md` from `/root/landtek`. T0: inventory every matter_facts
> writer (decipher_matter/reconciler/load_issue_spine/source_read_facts/n8n/ad-hoc SQL). T1: V4
> amendment so NULL-resolving cited-doc owner HOLDs for non-operator writers. T2: wire all remaining
> writers through deploy_870 ingest_gate (no fork). T3: sweep the 152 unresolved_doc_owner rows,
> resolve-or-hold, never mutate frozen facts. T4: extend test_ingestion_fidelity negative-bite.
> $0. Closes the A77 owner-gate class end-to-end.
