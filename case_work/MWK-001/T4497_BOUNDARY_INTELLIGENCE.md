# T-4497 ESTATE — BOUNDARY INTELLIGENCE (geospatial layer)

**Matter:** MWK-001 · Cluster A (T-4497 residential estate, Poblacion, Mercedes, Camarines Norte)
**Compiled:** 2026-07-19 by the Mapping Agent · INTERNAL work product · **client map OFF** (no external exposure)
**Discipline:** No coordinate is fabricated. Un-georeferenced shapes are relative-meter (`parcels`); only
tie-point-anchored shapes reach `map_parcels`, and every one still carries the **rough / APPROXIMATE** tier.
Geometry is a LEAD to verify against the title chain, never an assertion.

Builds on `CLUSTER_A_T4497_PARCEL_MAP.md` and `T4497_TAKING_RECOVERY_SPINE.md`. Where this file
**changes** their numbers, it says so and shows the arithmetic.

---

## 0. HEADLINE — how much of the 139,132 sqm is geometrically accounted

**97.0% of the senior title is now geometrically accounted, closure-gated, and area-reconciled.**
Only **Lot 2-G (~4,148 sqm, 3.0%)** remains open — a single lot absent from the corpus.

This **supersedes the "26% gap"** in `CLUSTER_A_T4497_PARCEL_MAP.md` §2. That 26% was an artifact of
reconciling through the *later* Psd-256008 re-subdivision (which only re-cut Lot 2-X) using the `titles`
table. The correct closure runs through the **first** subdivision, **(LRA) Psd-221861** (doc 287), whose
23-of-24 lots are already loaded with survey-quality closure (<0.5 m each) and areas matching title to <0.5%.

| Layer | Plotted sqm | Title/stated sqm | Status |
|---|---|---|---|
| Lot 2-A = T-32911 (Barangay 5) | 8,703.7 | 8,706 | closure 0.081 m · match ✓ |
| Lots 2-B … 2-X (22 lots) | 126,257.2 | 126,278 | each closure <0.5 m · all match ✓ |
| **Loaded Psd-221861 subtotal** | **134,960.9** | **134,984** | **97.0% of 139,132** |
| Lot 2-G (only missing lot) | — | ~4,148 (residual) | **OPEN — not in corpus** |
| **Senior title T-4497 (Lot 2, Psd-12802)** | — | **139,132** | 1912 survey / 1934 tech desc |

**T-4497-over-PNP-patent overlap:** demonstrable **circumstantially**, not yet **measurable** — the patent's
own metes-and-bounds (Csd-05-019916-D) are not in the corpus (see §4a).

**Single highest-value boundary fact:** **Lot 2-X = 106,918 sqm (76.9% of the whole estate) is ONE
contiguous, sea-fronting block, and it plots clean** — 36 calls, closure 0.047 m, area matching title to
0.01%. Three-quarters of the estate's value sits in one geometry-verified coastal parcel. That is the
monetization engine, and its shape is already trustworthy.

---

## 1. Senior boundary (Task 1) — Lot 2, (LRC) Psd-12802

- **Stated:** 139,132 sqm, Lot 2, (LRC) Psd-12802; bounded **NE Pacific Ocean, SE Rafael Carranceja,
  SW Provincial (Daet–Mercedes) Road, NW Lot 1**; survey May 1972 / re-survey May 1975 (Geodetic Engr.
  Ernesto L. Verante), 1934-era technical descriptions. *(doc 104 header — area + survey dates VERIFIED)*
- **The senior perimeter itself is NOT cleanly extractable from the corpus:**
  - **Doc 104** (the Psd-12802 plan) — the metes-and-bounds body is OCR garbage (the corner table renders as
    the string "LOT 2 A B760 SQ M" repeated ~350×). Header good, boundary unusable. **→ vision re-OCR.**
  - **Doc 739** (ARTA-1319 complaint) — states the boundary *theory* but carries **no courses**.
  - **Doc 562** is labelled "T-4497" in `parcel_courses` (54 courses), but walking seg 1 gives
    **107,823 sqm at 0.51% closure** — that is **Lot 2-X, not the 139,132 senior perimeter** (data-integrity
    mislabel, see §6). The clean Lot 2-X already exists from doc 287 anyway.
- **Resolution:** the senior boundary is reconstructed as the **sum of its Psd-221861 children** (§0), which
  closes to 97%. The true four-corner senior polygon (for a single georeferenced estate outline) still needs
  a clean CTC of the 1934 technical description **or** a vision re-OCR of doc 104.

## 2. Subdivision hierarchy + plot-vs-title reconciliation (Task 2)

**Layer 1 — Psd-221861 (Lot 2 → Lots 2-A…2-X), doc 287, `inferred_corroborated`.** All 23 loaded lots pass
the closure gate and match title area; full per-lot table is in the live `parcels` table. This is the clean
spine. **Only Lot 2-G is missing.**

**Layer 2 — Psd-256008 (de la Fuente re-subdivision of Lot 2-X only):**
- **T-32916 = Lot 2-X-4 = 14,416** and **T-32917 = Lot 2-X-6 = 85,149** — both **`awaiting_plot`** in
  `map_parcels`. Courses DO exist in `parcel_courses` but **FAIL the closure gate**:
  - T-32917 (doc 21, 13 calls): computes 96,989 sqm at **4.76% closure** — 14% area error, does not close.
  - T-32916 (doc 265, 19 calls): computes 6,805 sqm at **47.8% closure** — grossly broken OCR.
  - **→ Neither promoted to `parcels` (discipline: dirty geometry is not plotted). Both need vision re-OCR.**
- 14,416 + 85,149 = 99,565 vs Lot 2-X 106,918 → **~7,353 sqm** in the other Lot 2-X-* lots.

**Layer 3 — down to Balane (Lot 2-X-6-I-4-C-1):**
- **Balane 079-2021002126 = 2,586.9 sqm** (title 2,587), **closure 0.01 m / 7 calls** — the proof parcel;
  **georeferenced (rough tier)** at ~14.11160 N, 123.00180 E. Clean.
- The intermediate chain (2-X-6 → …-I → …-I-4 → …-I-4-C → …-I-4-C-1) is **not** plotted between T-32917 and
  Balane — Balane was plotted from its own title's technical description (doc 410), not derived down the tree.

**Closed vs open ledger:** 134,984 sqm (97.0%) geometrically accounted; **4,148 sqm (Lot 2-G) open.** Inside
Lot 2-X, the deep hierarchy is only partially resolved (Balane + 4 sub-lots plotted; T-32916/T-32917 fail).

## 3. Encroachment / recovery map (Task 3)

Adverse-held lots (void de la Fuente chain), current geometry state:

| Holder | Title | Lot | Plot state | Plotted sqm | Title sqm | Note |
|---|---|---|---|---|---|---|
| **Gloria Balane** | 079-2021002126 | 2-X-6-I-4-C-1 | **georeferenced (rough)** | 2,586.9 | 2,587 | ✓ court-grade shape; 14.1116/123.0018 (W/road side of 2-X-6) |
| **Roscoe Leaño** | T-33776 | 2-X-6-H | rough plot **SUSPECT** | 299.8 | **1,295** | plot area contradicts title 4× — see flag below |
| Elena Vergara | T-33350 | (of 2-X-6) | awaiting_plot | — | 339 | needs CTC |
| Edgardo Santiago | T-33415 / T-33416 | (of 4497) | awaiting_plot | — | — | no area, no plot |
| Jose Pascual Jr. | T-48335 / T-33686 | (of 4497) | awaiting_plot | — | — | adjacent to govt-taking zone (doc 1070 shows Pascual by Cad Lot 401/402) |
| Cesar Ramirez | T-40718 | (of 4497) | awaiting_plot | — | — | no area, no plot |
| Pedro Valledor | T-51640 | (of 4497) | awaiting_plot | — | — | no area, no plot |
| Erlinda Tychingco | T-34243 | (of 4497) | awaiting_plot | — | — | no area, no plot |

**Only Balane is plotted + georeferenced to court grade.** Every other recovery target needs its CTC pulled
before it can be located on the ground.

**AUDIT LEAD (surface, don't conclude):** the two rough plots at **299.81 sqm — T-33776 (Leaño) and
T-36668 (Lot 2-X-6-A) — are byte-identical shapes** (both from docs 319/320) and **both contradict their
title areas** (T-33776 title 1,295; T-36668 title 500). The plotted geometry almost certainly came from the
wrong / duplicated technical description. **Do not trust the Leaño location until a T-33776 CTC is plotted.**

## 4. Government-taking boundary proof (Task 4)

**(a) T-4497 over the PNP Special Patent (OCT 2018000090, Lot 402-B, Csd-05-019916-D).**
- **Not geometrically measurable yet — the patent's own metes-and-bounds are absent from the corpus.** No
  overlap sqm can be honestly stated.
- **But the overlap is circumstantially strong (doc 1070, DENR PENRO LMS-25-550, 26 Nov 2025):** DENR's own
  projection places **Keesey Lot 2-A (T-32911, 8,706 sqm) over Cad-118-D Lots 401 (5,015) + 403 (2,187) +
  405 (1,503)**. Cad Lot **402** sits **interleaved between 401 and 403** — i.e., the PNP's Lot **402-B is
  embedded inside the Keesey Lot 2-A cadastral footprint.** That is the spine's "already-titled → patent
  void" theory, shown spatially by the government's own map. **→ To quantify: obtain the Csd-05-019916-D plan
  + OCT 2018000090 file, plot both, measure.**

**(b) The 6,219 sqm Municipal-Hall block.** A portion of Lot 2 between **Don Estaneslao Moreno St (W)** and
**Doña Marciana Moreno St (E)**, fronting the **Provincial Road (S)** — the western/Barangay-5 edge, adjacent
to Lot 2-A. Described only in the **Deed of Donation Annex "A"** (photographed, ScannerPro folder, **not
ingested**). No discrete technical description exists to plot it. **→ Digitize the deed Annex "A" plan.**

**(c) Cadastral divergence (Psd-229480 vs Psd-221861).** DENR-admitted: the 1997 cadastral map
"inadvertently indicated" the lot as **Psd-229480 (a different province's plan)** when correct is
**Psd-221861** (doc 1070/739). **For Lot 2-A the AREA divergence is ~zero** — Cad Lots 401+403+405 = 8,705 ≈
Psd-221861 Lot 2-A = 8,706, so the cadastre re-covers the same ground under a wrong label. **The consequential
divergence is the eastern carve-out** (Lot 402-B to the PNP) and cannot be measured without (i) the patent
courses and (ii) a clean senior-boundary polygon. The divergence is real in *designation and site
attribution*, not (for 2-A) in *area*.

## 5. Value-feature map (Task 5) — the money layer

Estate frame: **NE Pacific Ocean (coastal frontage) · SW Provincial (Daet–Mercedes) Road (road frontage) ·
SE Carranceja · NW Lot 1.**

| Rank | Feature | Parcel(s) | Area | Value driver |
|---|---|---|---|---|
| **1** | **Coastal development block** | **Lot 2-X** | **106,918 sqm (77%)** | one contiguous sea-fronting 10.7-ha parcel; subdividable; geometry clean. The prize. |
| 2 | Road-frontage commercial strip | Psd-221861 Lots 2-B…2-W | ~19,340 sqm across 21 lots | SW Provincial-Road frontage (Barangay 3 / San Roque); retail/lease. |
| 3 | Recovery / just-compensation zone | Lot 2-A (T-32911) | 8,706 sqm | Barangay-5 govt-taking block (PNP patent + Municipal Hall) → back-rent / reconveyance value. |

- **Highest-value sub-parcels by location:** the sea-fronting northern/eastern portions of Lot 2-X. Per the
  Deed Annex "A", the sea-front on N, E and W is all "Heirs of Mary Worrick Keesey."
- **Exact frontage lengths (coastal metres, road metres) are NOT yet measurable** — the Psd-221861 lots are
  only **rough**-georeferenced (hand-placed on imagery); a **survey-tier** georeferenced senior outline is
  needed to state frontage to the metre. Directionally: coastal edge = NE face of Lot 2-X; road edge = SW
  face of the 2-B…2-W strip.

## 6. Honest gap list (Task 6)

**Vision re-OCR (courses too garbled to plot):**
1. **Doc 104** — Psd-12802 senior plan; boundary body is a repeated-string artifact. Blocks the true senior
   four-corner polygon.
2. **Doc 21 (T-32917 / Lot 2-X-6)** — closure 4.76%, area off 14%. Blocks the 85,149-sqm hub.
3. **Doc 265 (T-32916 / Lot 2-X-4)** — closure 47.8%. Blocks the 14,416-sqm branch.

**CTC / survey needed for clean bearings:**
4. **Lot 2-G** — the only missing Psd-221861 lot (~4,148 sqm); pulling it closes the senior title to ~100%.
5. **The 7 unplotted adverse-holder titles** — Vergara T-33350, Santiago T-33415/33416, Pascual
   T-48335/T-33686, Ramirez T-40718, Valledor T-51640, Tychingco T-34243 (and a corrective CTC for
   **Leaño T-33776** to resolve the 299.81-vs-1,295 conflict).
6. **Csd-05-019916-D + OCT 2018000090** (PNP patent) — the only way to *measure* the T-4497-over-patent
   overlap for §4a.
7. **Deed of Donation Annex "A"** — ingest/digitize to plot the 6,219-sqm Municipal-Hall block (§4b).

**Tie / control point needed to georeference (rough → survey tier):**
8. All current `map_parcels` shapes are **rough** (hand-placed). To reach **survey tier**, one real tie point
   is needed — the cleanest anchor is a **PRS92/BLLM monument tie in the technical descriptions** (the
   `survey_geometry` tie-line logic is built for this) **or** a single GPS-observed corner in the field.
   Balane already carries a rough georeference; promoting the estate to survey tier is one control point away.

**Field survey required for fully-verified boundaries:**
9. A **relocation survey by a licensed Geodetic Engineer** (DENR itself advised this in LMS-25-550) is the
   ultimate step to a court-certified, ortho-grade georeferenced estate — needed before any client map is
   ever switched on, and before frontage metres (§5) can be asserted.

**Data-integrity flags for the DB (not geometry-blocking):**
10. Doc 562 is **mislabelled "T-4497"** in `parcel_courses` (it is Lot 2-X, 107,823 sqm @ 0.51%).
11. `parcels` holds **duplicate rows** for the Psd-221861 lots (4× each, from repeated doc-287 ingest) — a
    de-dup pass is warranted so counts don't mislead.
12. `geometry_priority.note` is polluted with a repeated "activate_map_portfolio" string — cosmetic, but the
    worklist notes are currently unreadable.

---

*Provenance ledger: Psd-221861 geometry = `inferred_corroborated` (area cross-check passes, doc 287). All
`map_parcels` = **rough / APPROXIMATE**, no survey tier claimed. T-4497-over-patent overlap = **circumstantial
lead**, not a measured fact. Client map remains OFF.*
