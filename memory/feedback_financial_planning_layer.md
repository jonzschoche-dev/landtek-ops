---
name: feedback-financial-planning-layer
description: "Leo must run accounting + financial planning for both clients and Landtek firm. Top-tier financial reports are the channel for attracting outside investment and demonstrating Landtek's ability to maximize property value extraction."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "we must also build a robust financial planning scheme accounting, expenditures, monthly overhead for the clients and landtek, we must create a financial precedence that drives our products and our clients property value extraction to the highest levels, this is why our ability to generate reports must be top tier therefore having the capability to install confidence in outside investment and attract capital"**

This is a strategic layer that runs alongside the truth/status/agency layers. Tracks money in the same evidence-grade way Leo tracks legal facts.

**Two ledgers, both audited:**

1. **Client ledger** — per client, per matter:
   - Inflows: retainers, milestone fees, settlement proceeds, recovered rents
   - Outflows: filing fees, sheriff fees, notary fees, transport, photocopying, expert witnesses
   - Monthly overhead allocations
   - Property-value extraction events (sale proceeds, lease income, eminent-domain compensation)

2. **Landtek firm ledger** — across all matters:
   - Revenue (retainers, success fees, advisory fees, future product revenue)
   - Operating expenses (server costs, software, rent, salaries)
   - Monthly overhead per active matter
   - Cash flow projections
   - Investment-ready P&L + balance sheet

**Why this drives investment attraction:**
- Outside investors fund firms they can verify. Truth-graded financial reports demonstrate operational excellence beyond legal capability.
- Demonstrating Leo can simultaneously manage evidence + finance proves the platform scales beyond one law firm — making Landtek/Leo a licensable product.
- Property-value extraction metrics show ROI per matter, which is the language capital speaks.

**How to apply:**

1. New schema: `accounts`, `transactions`, `monthly_overhead`, `value_extraction_events`, `financial_projections`.
2. Same provenance rules: every transaction needs a source document (OR, invoice, bank statement) before being citable.
3. `truth_negotiator` extends to financial claims: "Landtek collected X PHP from MWK-001" must cite the OR doc.
4. New report types: client cash-flow statement, firm P&L, ROI per matter, valuation memo per property.
5. Goal_accelerator considers financial bottlenecks (unpaid retainers, overhead overruns) alongside legal bottlenecks.
6. PDF reports add a "Financial Posture" section that's investor-grade.

**Order:** ship after deploy_111 + 112 are validated. Probably deploy_113-115:
- 113-A: schema + ingestion (categorize tax docs, ORs, bank entries from existing 118 tax-doc corpus)
- 113-B: monthly accounting rollups + projections
- 113-C: investor-grade reports

Related: [[feedback-reports-are-the-measure]] (investor-grade is the new ceiling),
[[feedback-leo-mission-agency]] (firm agenda includes attracting capital),
[[feedback-execution-status-required]] (ORs/invoices are themselves docs with execution status).
