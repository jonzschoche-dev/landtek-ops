---
name: log-event-before-inferring-p0
description: "P0 — Every event (meeting, upload, call, filing, anything) is logged to client_history FIRST with whatever facts are stated. Only THEN does LEO inquire — slowly, atomically — about details. NEVER infer rich proposals before the event has been captured and basic facts confirmed by the operator."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**P0 — Events are first-class data. Log first. Inquire atomically. Infer only after confirmation.**

The flow must always be:

1. **Event happens** (a meeting reference, a file upload, a phone call, a court appearance, an email arrives) → LEO observes it.
2. **Log the event IMMEDIATELY** in `client_history` with whatever facts are stated. Provenance = `chat-stated` or `chat-stated-with-evidence` (if a doc is attached). Source = the originating `chat_notes` row or `gmail_messages` row. **Do this before any inference is attempted.**
3. **Inquire atomically** — ONE question at a time, per `feedback_atomic_inquiry_with_followups`. "Who was at this meeting?" → wait for answer → "What was discussed?" → wait → "Action items?" → wait → "Which matter does this connect to?" → wait. Never fire a wall of inferred proposals.
4. **Each answer becomes a structured update to the event row** — refining who/what/when/where/why fields.
5. **Inference is allowed ONLY after enough facts are confirmed** — and even then, frame it as "proposed, pending confirm" not as established fact.

**Why this rule exists (concrete incident, 2026-05-20):**

Jonathan uploaded a photo + typed: *"All from my meeting with Maribel"* and *"For Inocalla estate gold mining"*. The correct system response would have been:

> 📌 *Event logged: Meeting with Maribel (Inocalla estate gold mining context). Photo received as evidence. Three questions to capture this properly — answering one at a time:*
> *1. Maribel's full name + role + organization (NIBDC)?*

Instead, the system:
- Silently failed on the image handler (`ON CONFLICT` bug) — Maribel meeting was NEVER logged
- Fired 7 long inferred proposals about unrelated existing Paracale matters
- Fired 4 firm-level accelerator picks on top of that
- Each was a 400-word wall of text with proposed summaries / opposing parties / venues / next moves — all *inferred from the corpus*, none asked

Result: Jonathan's verbatim feedback: *"super long winded impossible to follow"* + *"any event should be logged in our canononical bible histroy of events and telegram should have slowly inquireed on what the meeting was about and not inferred"*.

This is the most important UX failure of the project. The system was BEING SMART instead of LISTENING. Self-research and synthesis are valuable AFTER the event is captured — never as the first move.

**How to apply (mechanical, not procedural):**

1. **Every inbound file or chat-stated event → instant `client_history` insert** with whatever is known. Provenance `chat-stated`; refine as facts arrive.

2. **The `forensic_new_doc_trigger` + `paracale_intake_research` pattern is BANNED for events whose context is unknown.** Both of those fire long inferred proposals on docs whose meaning hasn't been stated. They run only when:
   - A `chat_notes` entry establishes the context for the doc, OR
   - The operator explicitly invokes `/forensic <matter>` for a matter where they know the context.

3. **Atomic-intake pattern must replace bulk-inference pattern.** When LEO doesn't know what an upload is about, it asks ONE question: *"What's this?"* — answers stack the facts. Per `[[feedback_atomic_inquiry_with_followups]]`.

4. **Never run goal_accelerator picks while an intake conversation is active.** When `tg_inquiry_queue` has any row with `status='active'` from a `source_table` in {`paracale_intake_research`, `legal_intake`, anything tagged "in conversation"}, the goal_accelerator's daily picks pause.

5. **The intake message format must be brief.** Maximum: one sentence frame + one question + reply options. No proposed summary / opposing party / venue / next move inferences in the intake itself. Save those for AFTER confirmation.

6. **Inference outputs must be visually + linguistically marked as inference**, never as fact. "Proposed based on corpus inference — confirm or correct" not "Matter is X. Opposing party is Y." Use italics, dimmer voice, and explicit "INFERRED PROPOSAL" framing.

**The two-question test for any LEO output to Jonathan or any client:**
- *Did I just LOG the event before asking anything?*
- *Am I asking ONE thing, or dumping inferences they have to wade through?*

If either is no — do not send. Refactor first.

**Related rules:**
- `[[feedback_atomic_inquiry_with_followups]]` — one question at a time
- `[[feedback_facts_in_chat_are_first_class]]` — facts encode immediately
- `[[feedback_no_premature_reports]]` — foundation before output
- `[[feedback_leo_must_self_research]]` — self-research is the BACKING for proposed answers, not a substitute for asking

This rule supersedes all bulk-intake patterns (`paracale_intake_research`, `forensic_new_doc_trigger`'s suggest-flow). They must be refactored to comply.

## P0 ADDENDUM — Telegram concision

Jonathan, 2026-05-20, verbatim: *"Leo's conduct on telegram needs to be concise these long winded texts are useless."*

**Hard limits per Telegram outbound:**

| Message kind | Max chars | Allowed structure |
|---|---|---|
| Intake question | 400 | Heading line · one question · reply options. No proposed summary, no opposing-party guess, no rationale block. |
| Status ack | 200 | One sentence + one optional next-step. |
| Deadline alert | 500 | Title · due date · owner · one-line context. |
| Goal-accelerator pick | 500 | Pick line + impact + 1-line rationale. Cap to 3 picks max per fire. |
| Comms-health alert (ops) | 800 | Findings only, no analysis. |
| Pre-delivery audited brief / memo / report | unlimited | Must have passed Opus pre-delivery audit; delivered as PDF attachment with brief caption (≤300 chars). |
| Anything not in the above table | 400 default cap | Reject longer; truncate + add "[reply /more for detail]". |

**Enforcement (mechanical):**
- `comms.comms_send()` adds a soft pre-flight check: if `len(text) > limit_for_kind` and the message is going to Telegram, warn ops and ask "shorten before send?" rather than auto-send.
- Future state: a `concision_audit` function that scores readability + asks Haiku to compress before send.
- Wall-of-text intakes (the May 20 Paracale dump pattern) are forbidden.

**Test for compliance:** if Jonathan would skim past the message rather than read it, the message has failed. Reasonable rule of thumb: one screen height on his phone, max.
