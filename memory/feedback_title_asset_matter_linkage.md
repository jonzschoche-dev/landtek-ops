---
name: feedback-title-asset-matter-linkage
description: "Leo must resolve which physical lot each title/ARP refers to, which titles are active vs cancelled vs contested, and which titles are involved in active or forthcoming legal matters. The TCT-ARP-matter graph is the spine of the legal-financial-strategic engine."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "the system needs to be smart enough to detect which properties belong to which tax decs, which titles are active which titles are part of a forthcoming or active legal case"**

The legal-financial graph requires three linkages:

**1. TCT ↔ ARP ↔ Physical Lot**

A single physical lot typically has:
- A TCT/OCT number (registry side) — e.g., T-32917
- An ARP / Tax Declaration number (assessor side) — e.g., GR-2014-HH-07-001-00229
- A PIN (Property Index Number) — e.g., 025-07-001-01-042
- A PSD/LRC plan reference — e.g., PSD-05-026197

Tax declarations explicitly state "OCT/TCT No: ___" in their text. The resolver
must scan tax docs for these references and link ARP → TCT.

**2. Title lifecycle status**

Each title carries one of:
- `active` — currently in force
- `cancelled` — formally cancelled (per RD records)
- `superseded` — replaced by a derivative title (subdivided / consolidated)
- `contested` — subject of an active legal dispute (litigation pending)
- `lost` — annotations lost or title misplaced (T-31298 case)
- `void` — declared null by court

The `titles` table needs a `lifecycle_status` column. Derivable from
`title_transfers` (a transfer event means superseded for the source) + manual
override + court orders.

**3. Title ↔ Matter linkage**

A title can be subject to:
- An active legal case (e.g., T-079-2021002126 subject of Civil Case 26-360)
- A forthcoming filing (e.g., perjury complaint vs Salvador re T-32917 forgeries)
- An administrative proceeding (e.g., T-4497 ARTA-DILG complaint)
- An estate proceeding (e.g., intestate settlement of MWK assets)

A new `title_matter_links` table connects titles to matters with a relationship
type: `subject` (the title IS the litigation), `evidence` (the title backs claims),
`indirectly_affected` (could be affected by outcome), `forthcoming_subject`.

**Why this matters operationally:**

- Reports must show: "T-32917 is ACTIVE, subject of pending Civil Case 26-360 + forthcoming forgery action" — not just "T-32917 has market value X."
- truth_negotiator must distinguish cancelled titles when verifying claims about ownership.
- goal_accelerator should prioritize actions on titles in active cases over inert ones.
- Financial reports must aggregate values BY TCT (not by fragmented ARP) so investors see real per-asset totals.

**How to apply:**

1. Build `resolve_title_tax_links.py` — scans all tax-doc text + extraction metadata for TCT references, populates a new `title_tax_links` table.
2. Add `lifecycle_status` column to `titles`; backfill from `title_transfers`.
3. Build `title_matter_links` table + seeding script.
4. Reports + truth_negotiator use a unified view `asset_full_record` that joins title + ARP + lifecycle + matters.

Related: [[feedback-asset-valuation-layer]], [[feedback-asset-risk-analysis]],
[[feedback-case-stage-awareness]], [[feedback-legal-ops-ai]].
