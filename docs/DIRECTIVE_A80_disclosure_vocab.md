# DIRECTIVE — reconcile the A80 output-disclosure tier vs the A79 disclosure_ceiling vocabulary

**To:** the ontology / governance desk (owner of ONTOLOGY.md + the emission invariants).
**From:** the comms/emission desk, deploy_989. Source: the deploy_986 reasoning-layer audit, finding R5-T3.
**Status:** OPEN — blocks wiring the A80 tier into the A79 clamp. Do NOT self-mint; this is the desk's call.

## The gap (grounded)
The emission plane computes an output-disclosure **tier** for every candidate reply but never uses it to
gate. Two facts, both verified in code + live DB (2026-07-20):

1. `comm_agent_max.classify_output_disclosure()` returns
   `tier ∈ {contradiction, cross_matter_cascade, verified_fact, general}` and threads it into the clamp
   context as `disclosure_level`. `outward_guard._clamp_decision(policy, context)` **never reads
   `disclosure_level`.** It fires only on `policy.gate_default=='refuse'` or
   `policy.disclosure_ceiling=='none' AND context.contains_facts`.

2. The role policy's **ceiling** vocabulary is a different axis entirely. Live `v_comms_role_policy`:

   | role | disclosure_ceiling | gate_default |
   |---|---|---|
   | internal / operator / client | full | allow |
   | counsel | facts_plus_strategy | allow |
   | agent | machine_typed | allow |
   | counterparty / public | none | refuse |
   | unknown | none | hold |

So a `cross_matter_cascade` output addressed to a `client` (ceiling=`full`) is classified as sensitive but
passes unclamped, because the tier is on an axis the clamp can't see. The tier is a **gate that gates
nothing** (audit R5 defect #3).

## What is needed (the desk's decision, not the executor's)
A reconciled ordering that lets `_clamp_decision` compare an output tier against a role ceiling, e.g. a
monotone ranking on BOTH axes plus a rule "clamp when tier-rank > ceiling-rank". Concretely the desk must
rule on questions this executor must NOT answer unilaterally:

- Is `contradiction` / `cross_matter_cascade` an **absolute** clamp regardless of ceiling (a self-contradiction
  or a cross-matter cascade should probably never auto-emit to anyone but the operator)? If so it is a
  gate_default-style hard stop, not a ceiling comparison.
- Where do `verified_fact` and `general` sit relative to `none | machine_typed | facts_plus_strategy | full`?
- Is the mapping stored as data (a new `disclosure_tier_rank` / `disclosure_ceiling_rank` table, flip-gated
  like the other invariants) or hardcoded? Data is the desk's usual pattern.

## Proposed shape (for the desk to accept / amend / reject — NOT applied)
Add two small rank tables (or a single `disclosure_lattice` view), then have `_clamp_decision` add:
`clamp when tier is in the absolute-stop set, OR tier_rank(output) > ceiling_rank(role)`. The executor will
wire the comparison **only after** the desk publishes the reconciled lattice under a minted invariant
number (A80 is already the highest minted per docs/PROPERTY_DEVELOPMENT_SPINE.md — the desk assigns).

## Until this lands
The tier computation stays in place, marked advisory (annotated in `outward_guard._clamp_decision` and
`comm_agent_max`). It is intentionally NOT removed: it is the exact input the wiring will consume, and it
already populates the shadow audit. The clamp remains fail-closed on the two existing ceiling/gate signals.
No behaviour change was made to the tier under R5-T3.
