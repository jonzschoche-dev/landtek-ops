---
name: project-financial-urgency
description: "Financial tools are survival-critical (P0), not deferred. Leo's infrastructure has cost; the firm must manifest revenue to sustain it. Move financial-tools build to top of queue once truth_negotiator keystone is in place."
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "let build robust financial tools after all we are in business, we must manifest money to keep LEO alive"**

This is a priority signal, not just a feature request. Leo's operational continuity depends on the firm generating revenue. Financial tools are no longer "deploy_113 after 111+112 validate" — they should ship as soon as the truth_negotiator keystone is functional, before/alongside the agency loop.

**Why:** Leo runs on:
- Server costs (this VPS)
- LLM API spend (Anthropic, Gemini)
- Storage (Drive, Postgres, Qdrant)
- Engineering time (which costs money to compensate)

If the firm can't show ROI/revenue, the project becomes unsustainable. The financial tools' job is twofold:
1. Track Landtek's real revenue/cost picture (cash flow, burn, runway)
2. Generate investor-grade output that can attract outside capital

**Revised order:**

1. Finish truth_negotiator (deploy_111-C) — foundation for trustworthy financial figures
2. Lean deadline_sentinel (deploy_112-D) — minimal version covering case_deadlines
3. Pivot to deploy_113 financial layer:
   - Schema: accounts, transactions, monthly_overhead, value_extraction_events, asset_valuations
   - Backfill from existing 118 tax-doc corpus + Leo's actual API costs
   - Investor-grade reports: P&L, runway, ROI per matter, valuation memos per property

Defer to later: full goal_accelerator (deploy_112-E), workflow integration, drive ingestion sweep.

**How to apply:** When deciding next-task ordering, weight financial-tool readiness above feature breadth. A trustworthy P&L beats four more features.

Related: [[feedback-financial-planning-layer]], [[feedback-asset-valuation-layer]], [[feedback-leo-mission-agency]].
