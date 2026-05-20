---
name: no-premature-reports-p0
description: "P0 — Until the legal-profitability foundation (legal_cost_actuals · legal_outcome_estimates · dominion_value_estimates) is populated with real, sourced inputs, the system MUST NOT auto-generate reports, dashboards, scores, or memos. Foundation > Output."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**P0 — Foundation precedes output. NO premature reports.**

Until the three legal-profitability foundation tables are populated with sourced inputs from counsel, the operator, or verifiable evidence, the system MUST NOT auto-generate any of the following:

- Strategic memos labeled as "ready" or "final"
- Dominion Readiness Scores, win-probability dashboards, financial forecasts
- Weekly client status digests claiming case progress
- Forensic-agent runs that synthesize analysis without surfaced gaps
- Any output that displays a number labeled "probability" or "value" without inline source attribution
- Any auto-generated PDF that asserts "the case is ready" / "filing is recommended" / "value at risk = ₱X"

Jonathan, verbatim 2026-05-20: *"important to not generate any premature reports anymore as they are still lacking, we need to continue to build the foundation."*

**Why this rule exists (pattern, not a single incident):**

Today (2026-05-20) the system generated multiple report-grade artifacts before the underlying inputs were sound:
- A 11K-char case breakdown that Opus called "HOLD AND REBUILD" because it was machine-extruded from database queries with no legal analysis
- A 26K-char strategy memo that needed 10 Opus findings to fix before being usable
- A forensic-agent analysis that surfaced 3 LETHAL findings the prior outputs had missed — meaning every prior output was wrong

Pattern: each output looked authoritative but rested on insufficiently-vetted inputs. The remedy is not "edit the outputs faster" — it's "stop producing them until inputs are real."

**How to apply:**

1. **Foundation tables are the gate.** Before any report referencing probability/value/recommendation can ship, the relevant rows in `legal_outcome_estimates` and `dominion_value_estimates` must exist with `source != 'leo-guess'`. If the data is `P = NULL — needs counsel input`, the output shows that text verbatim, not a fabricated number.

2. **Reports paused as of 2026-05-20:**
   - `forensic-weekly.timer` — disabled
   - `forensic-new-doc-trigger.timer` — disabled
   - `weekly-client-status.timer` — disabled
   - These re-enable only when (a) the foundation has counsel-sourced inputs for the matter the report covers, AND (b) Jonathan explicitly authorizes the re-enable.

3. **What's still allowed (foundation activities, not reports):**
   - Intake inquiries (`legal_intake.py cost|probability|value`)
   - The forensic agent's `surface_forensic_impact()` hook — creates NULL placeholders + counsel-adjust intakes, does NOT produce a report
   - The comms-health-sentinel + fact-extractor (intake, not output)
   - On-demand `/forensic <matter>` if Jonathan explicitly fires it (he is the operator; he can override)
   - Read-only status commands like `legal_intake.py status --matter X` — these display what data we have, including "0 entries" honestly

4. **The honesty principle applied:**
   - If the system would otherwise display a number it doesn't have sourced support for, it must instead display the placeholder string (`P = unknown — needs counsel input`, `Value = unknown — needs appraisal`, etc.) and queue an intake for the missing input.
   - Counsel-sourced probabilities supersede leo-sourced ones; the `supersedes_id` chain preserves the audit trail.

5. **Reactivation condition.** A report can be reactivated when:
   - The matter it covers has at least 2 active rows in `legal_outcome_estimates` with `source` matching pattern `Atty.%|counsel:%|appraisal:%`
   - The matter has at least 1 active row in `dominion_value_estimates` with basis ≠ "asserted"
   - Jonathan explicitly says "go" for that specific report

Related: [[feedback_facts_in_chat_are_first_class]] (input side); [[feedback_synthesis_must_cross_source]] (cross-source rigor); [[feedback_output_no_hallucination_discipline]] (the original anti-hallucination rule this refines).
