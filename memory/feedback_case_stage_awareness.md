---
name: feedback-case-stage-awareness
description: "Leo must know each case/complaint's current procedural stage and what comes next under PH civil procedure, so he can proactively remind Jonathan of next steps and looming deadlines."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan: "LEo should understand at what stage a current case or complaint is, so that is known and can remind of the next steps"** (2026-05-16).

This is a third axis (alongside provenance and execution-status). Every case/complaint in the corpus needs:
- **current_stage** — where the matter is in the procedural timeline
- **next_event** — the next required action (filing, hearing, response)
- **next_deadline** — when it's due
- **history** — stage transitions with the document that triggered each

**PH civil-procedure stages (RTC, applicable to Civil Case 26-360):**

1. `pre_filing` — investigation, demand letter, position papers being prepared
2. `complaint_filed` — Complaint stamped/filed; awaiting summons issuance
3. `summons_served` — summons served on defendants
4. `answer_period` — defendants have 30 days to answer (15 + 15 ext)
5. `answer_filed` — defendants have filed Answer with Compulsory Counterclaim
6. `pretrial_pending` — pretrial conference notice issued, awaiting date
7. `pretrial` — pretrial conference ongoing (mediation, JDR, marking of evidence)
8. `pretrial_order` — pretrial order issued, trial calendared
9. `trial_plaintiff_evidence` — plaintiff presenting evidence-in-chief
10. `trial_defendant_evidence` — defendant presenting evidence
11. `formal_offer` — parties filing formal offer of evidence
12. `memoranda` — parties filing memoranda
13. `decision_pending` — submitted for decision
14. `decision_rendered` — decision issued
15. `appeal_period` — 15 days to appeal
16. `appeal_pending` — Court of Appeals / SC
17. `final` — finality / execution
18. `dismissed` / `settled` / `withdrawn` — terminal states

**Civil Case 26-360 is currently at `pretrial_pending`** (pretrial notice received Apr 28, 2026; date to confirm via Barandon email).

**Why this matters:**
- Each stage has hard deadlines. Missing a pretrial = waiver of evidence. Missing answer period = default judgment.
- Each stage dictates what filings Leo should be expecting/looking for.
- Reports must lead with: "26-360 stage = pretrial_pending · next event = pretrial conference · next deadline = [date]".

**How to apply:**

1. Schema: `cases` (or `matters`) table with `current_stage`, `next_event`, `next_deadline`, `next_event_owner`, `stage_updated_at`.
2. History: `case_stage_transitions` rows {case, from_stage, to_stage, transition_doc_id, transitioned_at, notes}.
3. Detection: classify_execution_status + case_stage_classifier — every newly ingested filing nudges the stage forward.
4. Surfacing:
   - `/stage <case>` slash → current stage + next event + days remaining
   - `proactive_deadlines.py` cron → ping Jonathan when next_deadline is within 14d
   - PDF reports lead with the stage line
   - `truth_negotiator` won't answer "what's next on 26-360" without quoting from the latest stage-transition doc.

Related: [[feedback-execution-status-required]] (filings drive stage transitions),
[[feedback-reports-are-the-measure]] (stage is a top-of-report fact),
[[feedback-legal-ops-ai]] (procedural awareness = agency).
