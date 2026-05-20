---
name: feedback-priority-is-goal-weighted-not-date
description: "Deadline priority is determined by strategic weight × goal-link × consequence-of-default, NEVER by date-proximity alone; substantive events outrank administrative tasks even when administrative is sooner"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** Priority of a pending event is **strategic_weight × goal-link × consequence-of-default**, not date-proximity. A substantive event 14 days out (e.g., mediation, hearing, deposition) outranks an administrative task tomorrow (e.g., demand letter, document request, follow-up form).

**Why:** Jonathan 2026-05-17: *"the system is effectively deciding that the demand letter is a priority when it's not aligned with the highest priority concerns for Don Qi [the client]."*

Concrete failure: deadline_sentinel + daily_strategic_digest ranked the May 18 demand letter (T-1d, admin) above the June 2 Civil Case 26-360 mediation (T+16d, substantive). The mediation is THE event that determines whether the case settles in the client's favor; the demand letter is a procedural ask of the Registry of Deeds. Wrong ordering.

**Deadline weight tiers (highest → lowest):**

| Tier | deadline_type | Why |
|---|---|---|
| **P0 case-defining** | trial, judgment, decision, hearing, mediation, pretrial, deposition, oral_argument | The case's outcome turns on these |
| **P1 case-progressing** | motion_hearing, status_conference, pretrial_brief_due, judicial_affidavit_due | Move the case toward resolution |
| **P2 substantive prep** | exhibit_due, witness_subpoena, expert_report, settlement_conference (non-mediation) | Required to perform at P0/P1 events |
| **P3 procedural** | filing_fee, registration_fee, certification_request | Process compliance |
| **P4 administrative** | demand_letter_send, agency_followup, document_request | Useful but defer-able |
| **P5 housekeeping** | data_quality_audit, archive_cleanup | Internal |

**Implementation:**

1. **`case_deadlines.priority_tier`** column (P0-P5) — default derived from `deadline_type`. Manual override allowed.

2. **Daily digest "Today's leverage move":** ranking changes from `MIN(due_date)` to `(tier_rank × 1000) + days_until`. Lower wins. So a P0 mediation at T+16 (rank = 0×1000 + 16 = 16) beats a P4 demand letter at T+1 (rank = 4000 + 1 = 4001).

3. **Stage-aware sentinel:** when firing intakes, prefer P0/P1 deadlines first when multiple are within fire-window.

4. **Goal-link enforcement** (already a rule from [[feedback_landtek_management_style]] but not yet enforced): every deadline must reference the goal_id it advances. Goal weight × deadline tier compounds the ranking.

**Concrete 2026-05-17 example:**
- Demand letter to RD (deadline #2): tier=P4 administrative, T-1d → rank = 4001
- June 2 mediation (deadline #3): tier=P0 case-defining, T+16d → rank = 16
- **Mediation wins by 250×.** That's the right answer.

**Linked memories:**
- [[feedback_landtek_management_style]] — every event WHAT/WHEN/WHO/OUTCOME/GOAL_LINK
- [[feedback_legal_status_awareness]] — stage-aware processing
- [[feedback_atomic_inquiry_with_followups]] — no rushing; substantive > administrative
