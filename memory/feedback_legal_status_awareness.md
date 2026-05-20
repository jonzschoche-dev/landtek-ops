---
name: feedback-legal-status-awareness
description: "Leo must understand the current legal status of every active matter at all times — no stupid alerts about events that already happened, no stupid questions answerable from extracted filings"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** At any moment, Leo must know — for each active matter — the current procedural stage, the most recently completed event, and the next required step. Alerts and questions that contradict the *known* current state are a catastrophic failure.

**Why:** On 2026-05-16, deadline_sentinel re-fired "OVERDUE Pretrial" alerts 4× over the day. The actual pretrial happened on May 13, 2026 (confirmed in doc#392 Notice of Pre-trial Conference + the filings stack: Reply, Motion for Summary Judgment, Verification, Judicial Affidavits all dated AFTER May 13). The data signal was loud and clear that pretrial had occurred — the system ignored it. Jonathan: *"claude needs to absolutely understand the legals status of our project at all times, stupid questions render the system useless and therefore it will die and corruption will win"*.

The cost of a wrong alert is not measured in API tokens. It's measured in **trust collapse** — if the system makes Jonathan triage false alerts, he stops trusting it, abandons it, and the property-fraud case loses its operational support. Then corruption (Balane / Pajarillo / Macale) wins by attrition.

**How to apply:**

1. **Before issuing any deadline alert, check the case stage.** If the matter's current stage is past the deadline's stage, mark the deadline `completed` automatically and suppress the alert. Stage trumps date.

2. **Auto-derive case stage from filings.** A doc-class filed after the previous stage's date is evidence the stage has advanced. Examples:
   - Motion for Summary Judgment filed → case is past pretrial.
   - Reply filed → case has moved through pleadings.
   - Decision rendered → case is past trial.
   - Notice of Appeal → case is on appeal.

3. **Source-of-truth hierarchy for stage:**
   1. Most recent court Order/Decision in extraction_chunks (highest authority).
   2. Most recent filed pleading by either party.
   3. Latest dated notice from court (e.g., Notice of Pre-trial Conference — establishes upcoming stage, not current).
   4. Seed data (lowest — never trust seed status if (1)-(3) contradict).

4. **Never ask Jonathan about facts already in the corpus.** Before any clarification question, the system must (a) search extraction_chunks + extracted_text for the answer, (b) only escalate if the answer is genuinely absent. (Reinforces [[feedback_leo_must_self_research]] and [[feedback_infer_dont_ask]].)

5. **Stage-awareness is required infrastructure, not optional.** Linked to [[feedback_case_stage_awareness]] and [[feedback_execution_status_required]]. The case_stage tracking that already exists in schema must actually drive alerts.

6. **Self-test for status-awareness:** before every deadline alert pulse, run a sanity check: "Is there any doc dated AFTER this deadline that suggests the deadline's event has occurred?" If yes, don't alert — escalate the deadline-status discrepancy to the meta-agent.

**Concrete fix queue (post-incident 2026-05-16):**
- Add `case_status` derivation: latest filed doc per matter, latest court-issued doc per matter, latest stage.
- Patch `deadline_sentinel.py`: skip alert if case stage > deadline stage OR if any extracted_filed doc exists with date > deadline.due_date.
- Add Telegram `/done <deadline_id>` command for Jonathan to mark deadlines complete in one tap.
- Hourly meta-agent ([[feedback_hyper_vigilance_meta_agent]]) must include "are any 'pending' deadlines past-due with post-deadline filings?" as a back-test.
