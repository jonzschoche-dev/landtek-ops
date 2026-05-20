---
name: feedback-hyper-vigilance-meta-agent
description: "Leo must NOT depend on Jonathan to spot its own gaps. A second AI node (the Systems Analyzer / meta-Leo) continuously audits the primary Leo for coverage drift, complacency, unverified claims, missed deadlines, and discipline breaches — and proactively surfaces remediations."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "why is there oversight of the complacency of the technology of this system, how do we create a back test that pushes our LEO to be hyper vigilant and efficient? can we get another ai node to be the systems analyzer and constantly assess the weak points and unverified issues so that we do not need to continuously remind the system to do what we set out to do"**

This is foundational. Leo cannot rely on Jonathan to spot Leo's own complacency.

## The architecture: two-AI-node design

**Node 1 — Leo (primary):** The agentic legal-ops AI doing the work — answering queries, generating reports, classifying docs, surfacing deadlines.

**Node 2 — Systems Analyzer (meta):** A SEPARATE AI agent whose ONLY job is to audit Leo himself. It does NOT do legal work. It checks:

| Audit dimension | Signal | Threshold for escalation |
|---|---|---|
| **Data freshness** | Days since last Gmail pull, Drive sync, etc. | >1 hour gap on any source |
| **Coverage** | % of corpus classified, case-correlated, exec-status tagged | <80% on any axis |
| **Verification discipline** | % of truth_negotiations passing back-test | <90% pass rate |
| **Deadline integrity** | Any deadline within 7 days lacking a sentinel alert | any |
| **Bottleneck staleness** | Bottlenecks open > 14 days with no mitigation progress | any |
| **Proposed-action acceptance** | % of goal_accelerator proposals accepted / declined vs ignored | <60% engagement |
| **Provenance drift** | Claims made in last 24h with verdict ≠ verified | any |
| **Filing-system integrity** | Files missing from STRUCTURED/, broken symlinks, stale indexes | any |
| **Onboarding queue** | Pending approvals > 4 hours old | any |
| **Cost drift** | Leo API spend deviation from baseline | >2σ |

## Back-testing

The analyzer maintains a `back_test_suite` table of KNOWN-CORRECT (claim, expected_verdict, expected_citation_doc_ids) triples. Every hour:
  1. Run each triple through truth_negotiator
  2. Compare actual vs expected
  3. If drift → alert + flag the negotiator for regression review

Seed truths include:
  - "Cesar de la Fuente is dead" → VERIFIED with doc 407 in evidence
  - "Civil Case 26-360 is at pretrial_pending stage" → VERIFIED (with caveats — challenger sees motions ongoing)
  - "ARTA Case CTN SL-2025-1021-0747 charges Mayor Pajarillo with R.A. 11032 violations" → VERIFIED with doc 384
  - "T-52540 was cancelled in 2021 via a deed executed by Cesar de la Fuente" → VERIFIED with docs 48, 233, 441

Each back-test pass logs to `back_test_runs`. Regression alerts go to Jonathan AND create a high-priority proposed_action to remediate.

## Behavioral changes for the primary Leo

1. Every cron tick, primary Leo BROADCASTS its run via `system_heartbeat` table — gmail-watcher, drive-sync, deadline-sentinel, goal-accelerator each emit a heartbeat row.
2. Analyzer reads heartbeats — missing or stale = complacency signal.
3. Analyzer issues `system_analyzer_findings` rows with severity, category, suggested fix.
4. Daily 'state of the system' digest to Jonathan: what was audited, what passed, what failed, what was auto-remediated.

## How to apply

1. Build `systems_analyzer.py` — Haiku-driven meta-agent.
2. Build `back_test_truth_negotiator.py` — regression suite.
3. Schema: `back_test_suite`, `back_test_runs`, `system_heartbeat`, `system_analyzer_findings`.
4. systemd timer every hour.
5. Daily digest at 7AM Manila.
6. Self-remediating: when analyzer finds a fixable issue (e.g., "Gmail not pulled in 2h"), it auto-triggers the fix via the same /api/email_pull endpoint Jonathan would use.

## Standard

Jonathan's interventions should NEVER be the only mechanism for catching system drift. Every gap he flags should already have been caught by the analyzer 1+ hour earlier.

Related: [[feedback-leo-must-be-proactive]], [[feedback-leo-must-never-go-offline]],
[[feedback-leo-mission-agency]], [[feedback-reports-are-the-measure]].
