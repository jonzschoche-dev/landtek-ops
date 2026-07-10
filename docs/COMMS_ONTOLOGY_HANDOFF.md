# GovernanceHandoff → Ontology Desk — Communications Layer marker updates (post-deploy_823/824/827/828)

**From:** Fable (comms execution desk) · 2026-07-10
**To:** Ontology desk (ONTOLOGY.md is in-flight in your working tree — apply these with your next version bump; comms desk no longer edits the ontology layer per standing rule)
**Nothing here is enforcement** — all markers reflect state that is ALREADY live and verified on the DB.

## 1. A25 marker — Part 2 UNBLOCKED (the deploy_733-style blocker is resolved)

- `channel_users.entity_id` (FK→`entities`) is **live** (deploy_824 applied 2026-07-10) — the person-key
  the V7 spec §4 was blocked on.
- `v_ontology_channel_person_cross` (the A25(b) cross-channel detector) is **live and returns 0**.
- Five identities bound (grounded, not guessed): ARTA→entity 2362 · Loida E. Macale→39 ·
  Barandon Law Offices→2390 · Pamela Bianca Cruz→10327 (new, `inferred_strong`, envelope-grounded
  gmail 102550) · Jonathan email identity→operator. All four externals scoped `MWK-001`;
  roles honest (`counterparty` for agency/LGU, `counsel` for our-side lawyers); `authorized=false` kept.
- Suggested A25 marker text: 🟡 asserted/shadow → *"Part 1 validity live (V7 shadow); **Part 2 detector
  live** (`entity_id` deploy_824, person-cross view, 0 violations); trigger-enforcement still pending
  the V7 roadmap (log→…→block post-Aug-12)."*

## 2. UnifiedClientPersona re-point (conversation_context was DROPPED in deploy_804)

§2.14's UnifiedClientPersona row still names `conversation_context`/`conversation_chunks` as the
(dormant) cross-channel memory home — those tables no longer exist. Canonical homes now:
- **`v_comms_interactions`** (deploy_823) — every interaction, all channels, one view
  (channel_messages ∪ leo_interactions ∪ outbound_messages; 4,945 rows live).
- **`v_comms_relationship`** (deploy_823) — per-party rollup (first/last seen, channels used, volumes).
- `chat_notes` · `client_history` · `channel_users.entity_id` remain as-is.
Views-first per the greenlit decision; a thin projection table is a future call, not needed for the marker.

## 3. Register in coverage

New named objects for `ontology_check.py --coverage` awareness (views, not concept stores):
`v_comms_interactions` · `v_comms_relationship` · `v_ontology_channel_person_cross`. New guard (concept:
Truth&Reconciliation, §2.13-adjacent): `trg_reocr_reground_guard` on `documents` (deploy_830) — re-OCR
that un-grounds a verified fact now auto-demotes it to `inferred_strong` + logs `REOCR_UNGROUNDED_FACT_DEMOTED`.

## 4. For the record (comms desk actions already taken, truth-layer relevant)

- Onboarding templates de-falsified (deploy_828 cluster): "Landtek Law / property-law practice" →
  "LandTek, land & property services company"; "Atty. Jonathan Zschoche" → "Jonathan Zschoche";
  explicit "LandTek is not a law firm; litigation handled by engaged counsel (Atty. Barandon)".
  17 queued outbound rows carrying the old false claims quarantined (`superseded_bad_template`) —
  **nothing had sent** (external switch held throughout; A26 verified working).
- Messenger armed tokenless (adapter + drain + timer + channel row, active=false) — §2.14
  CommunicationChannel row: Messenger ○ not-built → 🟡 armed/tokenless.
