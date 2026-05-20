---
name: feedback-first-principles-before-proposal
description: "Leo asks before proposing when confidence is low or matter context is stale or the user provides explicit fresh-context markers. Codifies the discipline shift from the 2026-05-20 Maribel-exchange critique: 'right now the model is worse than standalone Claude because it dumps stale RAG hits as confident proposals.'"
metadata: 
  node_type: memory
  type: feedback
  priority: P0
  originSessionId: cowork-2026-05-20
---

**Jonathan (2026-05-20): "as of now the model is not as good as a standalone ai chat with claude — it is confused and unable to work from first principles at the outset."**

Standalone Claude in a chat is smart because it **starts at zero** every time. It reasons from the question, not from accumulated baggage. When it doesn't know, it asks. When the user provides context, it integrates honestly. Confidence is calibrated.

Leo today is worse than that because of an **over-application of `feedback-leo-must-self-research`** combined with the n8n workflow's "proactive intelligence" framing. The result: Leo retrieves stale corpus hits and proposes confident narratives from them, even when its own internal confidence rating is 15-55%.

The 2026-05-20 Telegram exchange with Maribel meeting context was a 7-minute usability test. Leo dumped 7 matter proposals; 5 of 7 got corrected. The pattern was: stale RAG context + no fresh-context detection → confidently wrong proposals.

This rule is the keystone discipline that makes Leo trustworthy.

## Three new rules (operationalize)

### 1. Confidence floor: ≥ 80% to propose

If Leo's internal confidence on a proposed narrative is below 0.80, **do not propose**. Instead, ask one atomic question to raise confidence. The 15-55% confidence cases that wasted Jonathan's time on 5-20 should never have been proposed — they should have been:

> "I have weak context on PAR-CV13-131220 (confidence 0.55). What's the current situation?"

Implementation: gate proposal-render path in n8n on `confidence >= 0.80`. Below threshold → render an open question instead.

### 2. Stale-context detection: > 90 days since last update → assume stale

For each matter, check `MAX(updated_at)` across `case_intelligence_log + action_items + conversations + documents`. If > 90 days, treat existing corpus context as **stale**. Do not propose anything based on it. Ask the user first.

Implementation: add `matters.context_freshness_check_due` derived field. If stale + user touches matter → trigger atomic question, not proposal.

### 3. Fresh-context override: detect user-provided fresh markers, pause adjacent proposals

When the user provides explicit fresh context, the user's recency beats the corpus's age. Detect markers:

- "meeting with [name]"
- "I just learned"
- "today"
- "yesterday"
- "new info on"
- "from my call with"
- "fresh from"
- attached file dated within last 30 days

When detected: **pause proactive proposals for the next N matter-related cycles** (default 1 hour). Let the user inject the fresh context first. Then propose with it integrated.

Implementation: `comms.py` detects fresh markers → sets `conversation_context.fresh_context_until = NOW() + INTERVAL '1 hour'`. Goal accelerator + proactive nodes check this before firing.

## Atomic inquiry — not batch propose

When fresh context arrives covering multiple matters, **process one matter at a time** with the user as source of truth. Build the picture from them, then verify against corpus. This is the inversion of what Leo did on 5-20.

Good:
```
User: "Notes from meeting with Maribel for Inocalla estate gold mining."
Leo:  "Got it — 4 paragraphs detected. Want to walk me through matter by matter,
       or top 3 things first?"
User: "PAR-CV13-131220"
Leo:  "Current description says X. Your notes mention Y. Update to: ___?"
User: [confirms or corrects]
Leo:  ✓ matter row updated. case_intelligence_log#NNN written. Moving on.
```

Bad (what happened 5-20):
```
User: "All from my meeting with Maribel for Inocalla estate gold mining."
Leo:  [dumps 7 proposed narratives at confidence 15-55%, 5 of which are wrong]
```

## Self-research becomes a quiet tool, not a stream

`feedback-leo-must-self-research` still applies — but as a **TOOL Leo reaches for when needed**, not as the first move. The right ordering is:

1. **Hear the user** (or detect the incoming signal — email, photo, voice note)
2. **Is this fresh context?** If yes → atomic-question mode
3. **Is the matter context stale (> 90d)?** If yes → atomic-question mode regardless
4. **Is confidence ≥ 0.80?** If no → atomic-question mode
5. **Only if 2/3/4 all pass:** retrieve corpus + propose

Self-research happens in step 5 (and within step 1/4 silently — verifying user claims). Never in step 1 as the lead.

## Why this is P0

The 5-20 Maribel critique is more important than the ontology-as-truth work because: **if Leo can't decide when to ask vs. propose, no amount of clean data fixes the user experience.** Even a perfectly grounded ontology is unusable if Leo dumps stale narratives from it before the user has updated the picture.

This is the first principle that earns Leo the right to be in the loop at all.

## Test for v1.0 readiness

Re-run the 5-20 Maribel exchange against v1.0 Leo:

- Should reply within 2 lines
- Should NOT dump 7 proposals
- Should detect "meeting with Maribel" as fresh-context marker
- Should ask atomic-question or offer to walk matter-by-matter
- Confidence floor + freshness override + atomic inquiry all firing

If yes → discipline shift works. If no → keep refining.

Related: [[feedback-atomic-inquiry-with-followups]], [[feedback-infer-dont-ask]], [[feedback-leo-must-self-research]] (now subordinated to this rule), [[feedback-output-no-hallucination-discipline]] (this is a sibling — output guardrail; this rule is an input guardrail).
