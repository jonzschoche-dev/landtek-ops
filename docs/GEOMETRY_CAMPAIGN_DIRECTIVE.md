# GEOMETRY CAMPAIGN DIRECTIVE — ontology desk → mapping desk

**Date:** 2026-07-09 · **Pattern:** `GovernanceHandoff` (ONTOLOGY §2.12) · **Status:** ISSUED
**Operator order:** run the geometry campaign. This directive scopes it, names the governance rails,
and defines the V6 soak → block-flip that rides it.

---

## 1. Grounded starting state (verified live, 2026-07-09 ~21:30Z — do not re-derive)

| Piece | State |
|---|---|
| `parcel_courses` (CourseAssertion) | **83 rows** — extraction is producing per-source assertions w/ verbatim `raw_call` |
| `parcel_course_corrections` | 0 rows — correction CLI ready, unused |
| `parcels` (relative survey shapes) | **0 rows — correctly.** The deploy_819 gate refused T-4497's first build: the ring closed at 10.9m but disagreed with EVERY independent area source — a well-closed WRONG polygon. Closure + ≥1 independent area affirmation is the write bar; keep it |
| `map_parcels` | 1 (MWK-BALANE seed; `rough` tier; publish switch OFF) |
| V6 (geometry client-isolation, A9) | shadow (`log`), both arms, **0 findings all-time — but 0 traffic: the soak hasn't started until you write** |
| Ontology registration | **DONE (v0.31)** — CourseAssertion + CourseCorrection registered in §2.4; no action needed from you |

## 2. The campaign (your lane — sequenced by W5 evidentiary value)

1. **Extract** — sweep the ~54 MWK survey/title docs through `strip_plot_info` (per-lot segmentation,
   tie-line stripped from the ring) → `parcel_courses`. **Aug-12 priority order:** T-4497 family and the
   Balane chain (T-32917 → T-52540 → 079-2021002126) first; Paracale second.
2. **Consense** — `geometry_consensus.py` across independent title copies → corroborated / single-source /
   CONFLICT. **Every CONFLICT goes to the operator review+correct queue** (`parcel_course_corrections`,
   `provenance_level='operator'`) — never auto-resolve a conflict, never silently edit an assertion (A6).
3. **Write gated** — `parcels` rows ONLY through the deploy_819 gate (closure AND ≥1 independent area
   affirmation: titles register · stated per-copy area · plan corner counts). A held polygon is a finding,
   not a failure — log why it held.
4. **Georeference** — tie-point (BLLM monuments are present in the corpus) → `survey`-tier `map_parcels`
   rows. Never fabricate a coordinate; no tie point → stays `awaiting_plot` with NULL geometry.
5. **Report back** (close-out, in this file's §4): assertions by matter · corroborated/single/CONFLICT
   counts · parcels written vs held (with hold reasons) · georeferenced count · corrections applied.

## 3. Governance rails (the ontology desk's lane — honored, not re-litigated)

- **A9 / V6:** every `parcels`/`map_parcels` write carries the right `client_code` (writer forward-fills
  via `_client_of(matter_code)`). V6 shadow logs any cross-client write to `holes_findings` — **this
  campaign IS the V6 soak.** MWK and Paracale geometry in the same campaign is exactly the traffic that
  makes the soak meaningful.
- **A6:** corrections are provenance-tagged rows, raw assertions stay verbatim (`raw_call` is the excerpt).
- **A11 / no-external-exposure:** publish switch stays OFF. `token_client`/`internal_ops` surfaces only;
  no `published` status, no Earth/KML export. Client-visible rollout is a separate, held decision.
- **AreaAssertion:** any area figure that feeds legal output rides the provenance-locked `titles` path —
  a computed polygon area never silently overrides a title's stated area.
- **V6 block-flip (end of campaign):** when the campaign has written its MWK+Paracale waves with V6 at
  0 findings over REAL traffic, request the flip — the ontology desk executes it per the
  `ONTOLOGY_ALIGNMENT.md` §9 five-step checklist (pre-flight · rolled-back exception test · scope note ·
  desk verification via `ontology_check.py --enforcement`). Do not flip it yourself.

## 4. Close-out (mapping desk fills in; sign-off returns to the ontology desk)

*(pending)*
