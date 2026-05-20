---
name: feedback-evolving-assessments
description: "Risk profiles and asset valuations are moving targets, not static snapshots. The system must detect staleness, re-evaluate on event triggers (new doc, court order, market shift), and version every assessment so changes over time are traceable."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "these risk assessments and value are moving targets so we must create a system that evolves as situations evolve"**

Risk + valuation are NEVER finalized — they are continuously revised. Schema and engine must reflect this.

**Three behaviors required:**

1. **Versioning** — every assessment is a row, not an update.
   - `asset_valuations` already uses snapshot_date (good).
   - `asset_risks` must use the same pattern: rows are immutable; new assessments insert new rows.
   - Reading "current" = latest row per (asset_title, risk_type).

2. **Staleness detection** — each assessment has `next_review_due`.
   - Default: 30 days for active matters, 90 days for stable assets.
   - Cron job nightly: flag assessments where `next_review_due < now()`.
   - Flagged ones surface in daily digest as "needs re-eval".

3. **Event-driven re-eval** — certain events automatically mark assessments stale:
   - New doc ingested for an asset → re-eval risks + valuation
   - Court order issued → re-eval procedural risk
   - Tax dec update → re-eval assessed_value
   - Market observation flagged → re-eval comparables
   - Heir dispute filing → re-eval heir_dispute risk
   - SPA executed/revoked → re-eval spa_authority risk

**Schema:**
- `asset_risks` is append-only, with `(asset_title, risk_type, assessed_at)` natural key
- `risk_change_events` — log of what triggered each re-eval (event_type, source_doc_id, old_severity, new_severity, delta_php)
- `valuation_change_events` — same pattern for valuations

**Reports:**
- Show the trajectory of an asset's value AND risk over time (charts).
- Highlight when something materially changed and what triggered it.
- This is part of demonstrating Landtek's edge: "we noticed the risk drop and acted within 48 hours."

**How to apply:**
- Add `next_review_due` to asset_valuations + asset_risks.
- Build `assessment_freshness_check.py` nightly cron.
- Build `event_trigger_dispatcher.py` that hooks into ingestion + classify_case_stage + new tax dec ingestion.
- Every re-eval becomes a `risk_change_events` row with provenance.

Related: [[feedback-asset-risk-analysis]], [[feedback-asset-valuation-layer]],
[[feedback-leo-mission-agency]] (agency includes spotting changes nobody asked about).
