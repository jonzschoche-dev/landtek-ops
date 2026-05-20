---
name: feedback-atomic-inquiry-with-followups
description: "Each intake sub-item is its own atomic inquiry; Leo asks one, may follow up multiple times until satisfied, then and only then advances to the next; do not rush facts"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Every multi-item intake is decomposed into atomic questions. Leo asks ONE atomic question, waits for the full answer, may ask multiple clarifying follow-ups until satisfied, THEN — and only then — advances to the next atomic question. Inquiries are not "closed" by partial answers. **We do not rush facts.**

**Why:** Jonathan 2026-05-17: *"important to note that the outputs and inquiries were multi-questioned and impossible for a human to answer efficiently — this process needs to be clarified. Each inquiry or clarification of Leo may involve multiple follow-ups; after the system is satisfied, in order to move forward, it's important to do so but only then. We cannot rush facts. Each one is relevant for reasons we may not know until later."*

Current intake mechanism violated this: I fired a 5-item checklist (e.g., "Send demand letter — prep" with 5 sub-items) in ONE Telegram message. A human cannot meaningfully answer 5 distinct factual prompts in one reply. The result: partial / skipped answers, intake items remain ambiguous forever.

**How to apply:**

1. **Atomic intake decomposition.** Each item in `stage_intake_template.checklist` becomes its own `tg_inquiry_queue` row (kind='intake_item'). The dispatcher fires them in order, ONE at a time.

2. **Per-question follow-up loop.** When Jonathan answers an atomic question, the system evaluates the answer:
   - SATISFIED → mark the item answered, advance to the next.
   - UNCLEAR / INCOMPLETE → enqueue a follow-up clarifier (also atomic). May repeat 2-3 times.
   - SKIPPED (Jonathan typed `/skip`) → mark skipped (not satisfied) but proceed.

3. **Satisfaction predicate.** A short Haiku call (~$0.001) evaluates: "Given the question + the answer, is the factual response complete? If not, what's the smallest follow-up question to fully extract the fact?" Output: `{satisfied: bool, follow_up: str | null}`.

4. **Do not advance with unsatisfied items.** An intake is `complete` only when ALL its atomic items are either `satisfied` or explicitly `skipped`. The deadline/matter it anchors does NOT advance stage until intake is complete.

5. **Preservation principle (every fact matters).** Even seemingly minor data points (e.g., the OR number of a receipt, the name of a court clerk, the exact stamp date) get preserved as separate atomic captures. We may not know later why a fact matters — capture every one with full provenance.

6. **Anti-patterns to retire:**
   - ✗ Sending a 5-item checklist in one Telegram message.
   - ✗ Closing an intake on a partial answer.
   - ✗ Asking "anything else relevant?" — vague catch-all questions get vague answers.
   - ✗ "I'll move on" before satisfied.

7. **Implementation queue:**
   - Refactor `deadline_sentinel.maybe_fire_intake()` to enqueue per-item rows (not one composed_html).
   - Build a `satisfaction_evaluator.py` (Haiku call) hooked into the dispatcher's answer-handling path.
   - Add a `tg_inquiry_queue.parent_id` column so follow-up rows link to the original question.
   - Add a state machine: pending → asked → answered → (satisfied OR follow_up_needed → asked) → satisfied / skipped.
   - Telegram message format per question: clear, one ask only, with the context of which intake/matter it belongs to.

**Linked memories:**
- [[feedback_telegram_inquiry_queue]] — ONE active inquiry at a time
- [[feedback_output_no_hallucination_discipline]] — every fact cited; rushing causes hallucinations
- [[feedback_stage_transition_intake]] — checklist structure (now atomized per this rule)
- [[feedback_legal_act_validity_scrutiny]] — components must be scrutinized one at a time
