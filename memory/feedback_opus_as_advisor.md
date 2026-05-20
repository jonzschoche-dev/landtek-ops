---
name: feedback-opus-as-advisor
description: "Opus 4.7 is the SENIOR STRATEGIC ADVISOR — sparingly invoked for case strategy, dispute resolution, and critical-doc drafting; never for routine extraction/verdict/classification work"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Claude Opus 4.7 is added to the tiering as the **senior strategic advisor** — invoked only for high-stakes reasoning where output quality justifies the ~10-20× cost over Sonnet. Never for routine work.

**Why:** Jonathan 2026-05-17: *"let's add opus as an advisor."*

The pricing cliff matters:
- Haiku 4.5: $0.80/M input · $4/M output — for 95% of pipeline volume
- Sonnet 4.6: $3/M input · $15/M output — verdict gates + daily synthesis
- **Opus 4.7: $15/M input · $75/M output** — SENIOR ADVISOR ONLY

**Sanctioned Opus use cases (only these):**

1. **Strategic synthesis** — case-level strategic memo for a matter at a major milestone. Inputs: matter metadata + recent 90d client_history + pending deadlines. Outputs: posture / leverage moves / risk / evidence gaps. **Frequency:** 1-3 calls per matter per month.

2. **Priority-dispute resolution** — when `case_deadlines.priority_consensus_state = 'disputed'` (Leo + Jonathan + client disagree), Opus weighs in with reasoned recommendation on which signal should prevail. **Frequency:** rare; manual trigger via `/opus-resolve <deadline_id>` or meta-agent escalation.

3. **Critical-doc drafting** — final-form drafting of demand letters, motions, judicial affidavits, settlement proposals where reasoning quality matters more than cost. **Frequency:** per major filing.

**Anti-patterns to avoid:**
- ✗ Opus for extraction tasks (Haiku's job)
- ✗ Opus for truth-negotiator verdicts (Sonnet's job)
- ✗ Opus for daily digest synthesis (Sonnet's job)
- ✗ Opus for routine intake / classification / dating
- ✗ Opus in autonomous loops (cost discipline forbids)

**Cost discipline:**
- Always use 1h ephemeral cache on the OPUS_SYSTEM prompt (~3K tokens of advisor framing → 90% cache discount on reads).
- Cap max_tokens at 1500-2000 for synthesis, 600 for dispute resolution.
- Per-call expected cost: $0.05-0.20.
- Daily Opus budget: ≤ $1.50.
- Track via `llm_calls.called_from='opus_advisor'`.

**Implementation (deploy_145):**
- `opus_advisor.py` — three subcommands: `strategic`, `resolve-dispute`, `draft`.
- All calls go through `llm_billing.anthropic_call` for cost-logging.
- System prompt cached at 1h TTL.
- Output goes to stdout; integrating into Telegram delivery is a follow-up.

**Linked memories:**
- [[feedback_cost_discipline]] — model tiering rules
- [[feedback_output_no_hallucination_discipline]] — Opus subject to same evidence-citation rules
- [[feedback_priority_consensus_required]] — Opus is the dispute-resolution party of last resort
