# LandTek commercialization fleet (`.claude/agents/`)

Claude Code subagents whose single mandate is **relentless product development → ship a
retainer-ready workspace → bring in money**. Decided 2026-06-30 by Jonathan ("develop the
product relentlessly"). Proof clients: **MWK-001** + **Paracale-001**. Money target (MASTER_PLAN
§4A): PHP 15–50k/mo retainer, $6–15/day burn, **>85% margin**.

These are role definitions only ($0 to exist) — invoke them with the `Agent` tool. They do NOT
replace the resident VPS agent fleet or the legal/case automation; they are the business-of-LandTek
layer that turns the built stack into a sellable product.

| Agent | Owns | Does NOT touch |
|---|---|---|
| **product-hardener** | reliability + correctness of what exists (deadlines, verified-fact coverage, daemon health, no silent failure) | new features, pricing |
| **ship-packager** | the client-VISIBLE surface (per-client cockpit, bound-PDF deliverable, onboarding, channels) | backend reliability, pricing |
| **revenue-engineer** | pricing, retainer packaging, per-client P&L + >85% margin proof, cost governance, GTM | product features |
| **truth-qa-gate** | adversarial gate on anything client-facing (hallucination, provenance, cross-matter leaks, citations) | building things |

## Orchestration (the main thread runs this)
Typical loop for a shippable increment:
1. **product-hardener** or **ship-packager** builds/hardens the increment.
2. **truth-qa-gate** gates any client-facing output — PASS or FAIL+fix-list. Never ship a FAIL.
3. **revenue-engineer** confirms it stays inside the cost/margin envelope and packages the value.
4. Update `MASTER_PLAN.md` (§4A build-status snapshot / §7 product decisions) in place — never fork a parallel plan doc.

## Shared non-negotiables (every agent enforces)
No hallucination · `_safe` views for client output · provenance sacred · client/matter separation
absolute · S14 Telegram comms · stay cheap (sim stays dead) · git discipline (deploy routine, never
`git add .`) · no financial execution (draft only; Jonathan moves money) · don't weaken Aug-12
case-critical safety paths for product velocity.
