---
name: feedback-asset-risk-analysis
description: "Every asset carries an internal risk profile that Leo continuously updates. Internal-only. Risk-corrected valuation + market observation → identifies depressed-value 'low hanging fruit' opportunities Landtek can capitalize on."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "there should be an accurate risk analyses with each assett that is kept internal so that we can be aware and eliminate those risks, eventually becoming an expert at createing low hanging fruit in the market, identifying it, first of all based on our learned risk assessment and known value"**

This is the strategic engine on top of asset_valuations. Three components:

**1. Per-asset risk profile (internal, never in client-facing reports unless authorized):**

Each asset (TCT/lot) carries an `asset_risks` row(s) capturing:
- `risk_type` — 'title_defect','adverse_claim','tax_delinquency','encroachment','ejectment_resistance','heir_dispute','spa_authority','market_illiquidity','zoning_change','natural_hazard','demographic_decay','road_access','utility_access','political','informal_settlers'
- `severity` — 'critical','high','medium','low'
- `likelihood_pct` — 0..100
- `expected_loss_php` — quantified exposure
- `mitigation_strategy` — what Landtek can do to neutralize
- `mitigation_status` — 'unaddressed','planning','in_progress','partial','eliminated'
- `learned_from` — case_file or doc_id that taught Leo this risk
- `evidence_doc_ids` — backing docs
- `internal_only` — boolean (default true)

**2. Risk-corrected valuation:**

Leo computes intrinsic_value = market_price_value − sum(severity-weighted expected losses).
When intrinsic >> actual market price asked → that's the depressed-value signal.

**3. Low-hanging fruit identification:**

When (intrinsic_value > 1.4 × actual_market_price) AND (mitigation_strategy is known)
AND (mitigation_cost < spread) → FLAG as opportunity.

Leo proactively surfaces these in reports — "we know how to eliminate the risk that's
depressing this asset's price; here's the buying play".

**Why this matters:**
- Landtek's competitive moat = its accumulated risk database. The more cases we work, the more risks we learn to identify and eliminate.
- Investors fund firms that can prove they spot opportunities others can't.
- Per Jonathan, this is the path from "law firm" to "property-value extraction expert".

**How to apply:**

Schema: add `asset_risks` table to deploy_113.
Engine: nightly job recomputes intrinsic_value per asset, flags opportunities.
Reports: investor-grade reports show the opportunity pipeline (asset, depressed price, known risk, mitigation cost, expected uplift).
Truth-grade: every risk citation requires source doc (or experience case_file).

Related: [[feedback-asset-valuation-layer]], [[feedback-financial-planning-layer]],
[[feedback-leo-mission-agency]] (proactively surfacing opportunities = agency).
