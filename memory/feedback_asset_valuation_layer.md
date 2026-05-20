---
name: feedback-asset-valuation-layer
description: "Every title/asset must carry full financial state — tax dec, assessed value, zonal value, MPV, development plan tied to client goals + Landtek role. Reports must model buy/sell opportunities in depressed markets."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "we must create tables withour active tax decs, future investments, MPV assessed value zonal value etc.. look for ways that we will develop each title or assett, all must have a financial plan basedon goals of the client role of landtek, we should be able to establish depressed values in the market with our reports to model buying opportunities or selling opportunites"**

Extension of [[feedback-financial-planning-layer]] — the per-asset (per-title) financial state.

**Per-asset financial state (one row per title/lot per snapshot date):**

- `tax_dec_no` — current active tax declaration number
- `assessed_value` — city assessor's value (basis for RPT)
- `zonal_value` — BIR zonal value (basis for capital gains, donor's tax)
- `market_price_value` (MPV) — actual market valuation
- `appraised_value` — bank/independent appraiser, if available
- `acquisition_cost` — what client originally paid
- `current_use` — agricultural / residential / commercial / idle
- `highest_best_use` — what it COULD be (zoning permits, market demand)
- `liens_encumbrances` — mortgages, easements, adverse claims
- `tax_status` — current / delinquent / under-protest

**Per-asset development plan:**

- Goal (per client + per Landtek role)
- Timeline (short-term / mid / long)
- Required investments (improvement, titling cleanup, road access)
- Expected ROI
- Risk factors

**Market modeling:**

- Track depressed-value indicators: zonal > MPV (under-priced), distressed sale comparables, foreclosure filings nearby
- Flag buying opportunities: depressed-value + clean title + buyer interest
- Flag selling opportunities: appreciation + ready buyer + tax-efficient exit window
- Reports surface both, ranked by IRR / cap rate / strategic fit

**Required schema:**

- `asset_valuations` (one row per asset per snapshot — time-series)
- `asset_development_plans` (the playbook per asset)
- `market_observations` (comparables, distressed-sale signals)
- `valuation_sources` (which doc backed which figure — same provenance discipline)

**Why this drives investor attraction:**
Every valuation must be cited to a real document (tax dec, appraisal, BIR zonal table) — `truth_negotiator` extends to financial figures. Investors fund firms that demonstrate this rigor.

**How to apply:**

Slots into deploy_113-115 alongside the firm-level P&L work. Specifically:
- 113-A: financial schema (already scoped) + asset_valuations + market_observations
- 113-B: development plans engine
- 113-C: market modeling — depressed value flags + buy/sell opportunity reports

Related: [[feedback-financial-planning-layer]], [[feedback-legal-ops-ai]] (granular assets),
[[feedback-execution-status-required]] (tax decs / appraisals are docs too),
[[feedback-reports-are-the-measure]] (investment-grade output).
