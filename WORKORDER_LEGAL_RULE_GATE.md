# Work Order — tighten the uncited legal-rule gate (leo_answer_gate)

**For:** executor agent (VPS Claude, `/root/landtek` — you commit/push).
**From:** designer window (Mac). Triggered by a weak spot surfaced in the JJ cutover probe (deploy_857): the model asserted "Section 4, Rule 74" uncited and the gate only WARNED, not FAILED. An ungrounded legal assertion that ships with a warning is exactly the hallucination class A70/leo_answer_gate was built to stop. This closes it before any second channel flips to headless.

## T1 — Add a legal-rule regex to the ungrounded-assertion heuristic
In `scripts/leo_answer_gate.py`, the `FACT_SIGNAL_RE` / ungounded-assertion check (gate step 3) currently flags fact-signals but only *warns* on an uncited one. Add a `LEGAL_RULE_RE` that matches asserted legal authority:
- `Rule \d+` · `Section \d+` · `Art\.?\s*\d+` · `Rule \d+ of (the )?Rules of Court` · `§\s*\d+` · `Constitution (Art|Sec)\.?` etc.
Then: a sentence matching `LEGAL_RULE_RE` AND NOT carrying a `CITE_RE` doc citation → **FAIL** (not warn), same class as an uncited factual claim. Rationale: a legal rule is a factual/authority claim; shipped ungrounded it is the precise error the gate exists to block. Keep it heuristic — hedges (`HEDGE_RE`: "unknown", "not in the record", "I don't know") still suppress.

## T2 — Negative-test it
Extend `truth_tests/test_leo_service_spine.py` (or add to the gate's own test): a reply asserting "Section 4, Rule 74." with no `doc:` citation → verdict `fail` (negative-bite). A reply that cites the rule AND a resolvable `doc:N` → passes. Confirm the existing fabricated-cite + ungrounded-cascade bites still hold.

## T3 — Re-run the live proof
On the VPS: probe leo_service with the "Section 4, Rule 74" input again → assert gate now FAILs → remediate() strips it → no outward ship. Confirm the 07:00-batch / shadow path still 6/6 + new assertion green.

## Guardrails
- Edit ONLY `leo_answer_gate.py` (the governed, reusable module) — do NOT fork the check into leo_service.
- Heuristic, not parser-perfect; suppress on HEDGE_RE. Don't over-match plain numbers ("Rule of thumb" style false positives — review the regex against a sample of real replies).
- $0, no LLM in the gate. No phantom enforcement — the gate is already live; this only raises a warn→fail threshold on one pattern.

## Close-out
A59 work order to terminal state. Report: the regex, the negative-bite result, and that no second channel should flip until this is green. Final line names the next safe cutover channel.

## Invocation
> Execute `WORKORDER_LEGAL_RULE_GATE.md` from `/root/landtek`. Tighten leo_answer_gate: an asserted legal rule (Rule/Section/Art/§) with no doc: citation → FAIL not warn. Negative-test the bite. Re-prove on VPS. $0. This is the pre-broader-cutover safety floor.
