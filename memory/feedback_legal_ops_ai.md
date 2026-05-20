---
name: feedback-legal-ops-ai
description: "Leo's directional vision per Jonathan (2026-05-16). System must trend toward granular understanding of assets/law/evidence, full grasp of client goals + Landtek duties + bottleneck detection with agency to remove them."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

Leo is not just a chat assistant — it's a legal-operations AI. Three structural directives:

1. **Granular understanding of assets, the law, and the evidence.**
   Every asset (TCT/property/parcel) must have: full ownership history, current legal status, encumbrances, square meters, value, location, supporting documents. Every cited law: text, holding, applicability. Every piece of evidence: what claim element it supports, strength, verified status.

2. **Understand the client's goals AND Landtek's duty.**
   Each client has explicit goals (operational, legal, financial). Landtek has a defined duty to fulfill them — almost fiduciary in nature. The system must track goals + duties + actual fulfillment progress, and surface when duties are at risk of being missed.

3. **Detect bottlenecks AND have agency to remove them.**
   Where is progress stuck? A missing affidavit, an unsigned annex, an unanswered LGU letter, a pending hearing, a client awaiting Jonathan's reply. The system identifies these, prioritizes them, and either (a) acts to remove them when authorized, or (b) routes them to whoever can.

**Why:** Stated by Jonathan 2026-05-16 in the wake of the MWK-001 synthesis:
- *"the system should be trending toward understanding all the assets the law and the evidence at a granular level"*
- *"the system should understand the clients goals and landteks duty and ensuring those goals are reached"*
- *"the system should understand where the bottlenecks are and have the agency to help remove bottlenecks from the client and landtek"*

**How to apply:** Every new feature or schema should ask:
- Does it deepen granular understanding of assets/law/evidence?
- Does it track a goal/duty/bottleneck explicitly?
- Does it give Leo more agency, or does it leave Jonathan to do the manual work?

**Concrete schema gaps as of 2026-05-16:**
- `assets` table — structured asset ledger per client (currently entities are flat)
- `legal_provisions` table — citations linked to applicable case facts
- `evidence_to_claim` table — which docs support which claim element + strength
- `client_goals` table — explicit goals, milestones, progress, dependencies
- `landtek_duties` table — Landtek's obligations + fulfillment evidence
- `bottlenecks` table — what's stuck, who's blocking, how to unblock

**Concrete agency gaps as of 2026-05-16:**
- No real email send (Leo defers to Jonathan)
- No real court-filing draft (no template auto-fill against asset data)
- No automated follow-up on aged inquiries (60h timer = ping target)
- No DAR/LGU API calls or even semi-automated form generation
- No multi-step tool-calling agent loop (single-pass JSON only)

Related: [[feedback-information-is-gold]] (capture preserves the substrate),
[[feedback-leo-must-never-go-offline]] (uptime preserves the agency).
