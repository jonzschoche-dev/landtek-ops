# Cluster A — T-4497 Residential Estate: Verified Parcel Map (2026-07-19)

The **rock** of the spine: the closed, area-reconciled, provenance-graded map of the senior title
**TCT T-4497 = 139,132 sq m** (Lot 2, (LRC) Psd-12802, Poblacion, Mercedes; root OCT T-106). Every line is
graded `[V]` verified / `[I]` inferred / `[U]` unknown. **No move is made on an `[I]` or `[U]` line until it
is pulled to `[V]`.** This map is compiled from `titles` + `title_chain` (live corpus); the CTC pulls that
close the gaps are listed in §5.

## Spine invariant — TWO clusters, never summed
- **Cluster A (this map): T-4497 residential estate**, 139,132 sqm, root **OCT T-106**. Poblacion Mercedes.
- **Cluster B: agrarian**, four ~80-ha parcels (T-4502/4503/30681/30683), root **T-111** — the CV 6839 CARP /
  Manguisoc lands (a separate matter; own map). **A flat sum of all `titles` (3.58M sqm) is meaningless —
  parent/child double-counting across two roots. Reconcile only WITHIN a cluster's hierarchy.**

## §1 The verified root and its first subdivision
| Title | Area | Status | Prov | Role |
|---|---|---|---|---|
| **T-4497** | **139,132** | senior | **`[V]`** | the rock (Lot 2, Psd-12802) |
| ├ T-32917 | 85,149 | active | **`[V]`** | **Lot 2-X-6 hub** (the Balane + Leaño + Vergara branch) |
| ├ T-32916 | 14,416 | active | **`[V]`** | **Lot 2-X-4** (the T-52537 branch) — *parent link broken in DB → fix to T-4497* |
| ├ T-45964 | 2,034 | cancelled | `[I]` | direct child |
| ├ T-32913 | 1,022 | cancelled | `[I]` | direct child |
| ├ T-32911 | `[U]` (~8,706 per DENR) | clouded | `[I]` | **Lot 2-A, Barangay 5** (the govt-taking / cadastral parcel) |
| └ (no-area direct children — the adverse-holder lots, §3) | `[U]` | clouded/cancelled | `[I]` | Santiago/Tychingco/Pascual/Ramirez/Valledor |

## §2 Area reconciliation — CORRECTED (map is 97% closed; see T4497_BOUNDARY_INTELLIGENCE.md)
**Reconcile through the FIRST subdivision Psd-221861, not the later Psd-256008 titles.** The mapping pass
(2026-07-19) plotted all 24 Psd-221861 lots (doc 287), closure-gated:
- **ACCOUNTED: 134,984 sqm = 97.0%** — Lot 2-A (T-32911, 8,706) + Lots 2-B…2-X (126,278), each closing <0.5m
  and matching title area to <0.5%.
- **OPEN: ~4,148 sqm = 3.0%** — **Lot 2-G only** (the one Psd-221861 lot absent from the corpus). ← the sole
  area gap to close.
- **The earlier "26% gap" was an ARTIFACT** of reconciling through the messy `titles`/Psd-256008 layer — not
  a real hole. The estate map effectively closes.
- **Crown parcel: Lot 2-X = 106,918 sqm (76.9% of the estate), ONE contiguous Pacific-front block, plots
  clean** (36 calls, closure 0.047m, area to 0.01%). This is the monetization engine.
- **Still-dirty (deep hierarchy):** inside Lot 2-X, the *sub-lot* courses of **T-32916 (fails closure 47.8%)
  and T-32917 (4.76%)** are garbled-OCR and were NOT promoted → need vision re-OCR (§5). Balane's
  Lot 2-X-6-I-4-C-1 (2,587) plots clean + georeferenced.

## §3 Holder classification within the tree (who must be recovered from)
**Keesey-held (estate), to protect/monetize:** T-4497, T-32917, T-32916, T-38838, T-47655, T-52537, T-49062,
T-51641, T-46460, T-147652, T-32478, T-32912, T-32914, T-49060, T-49061.
**Adverse-held (recovery targets — void de la Fuente chain):**
| Title | Holder | Parent | Prov | Area |
|---|---|---|---|---|
| 079-2021002126 | Gloria Balane | T-52540←T-49061←T-32917 | `[V]` | 2,587 |
| T-33776 | Roscoe Leaño | T-32917 | `[I]` | 1,295 |
| T-33350 | Elena Vergara | T-32917 | `[I]` | 339 |
| T-33415 / T-33416 | Edgardo Santiago | T-4497 | `[I]` | `[U]` |
| T-48335 / T-33686 | Jose Pascual Jr. | T-4497 | `[I]` | `[U]` |
| T-40718 | Cesar S. Ramirez | T-4497 | `[I]` | `[U]` |
| T-51640 | Pedro Valledor | T-4497 | `[I]` | `[U]` |
| T-34243 | Erlinda Tychingco | T-4497 | `[I]` | `[U]` |
**RETAIN (family):** 079-2021002127 (Hoppe). **Govt-taking:** T-32911 / Lot 2-A (→ Cluster-A but the LGU/PNP
takings ride the taking-recovery spine).

## §4 Data-integrity issues to fix (infrastructure hardening)
1. **T-32916 parent link is NULL** — set to T-4497 (it is Lot 2-X-4 of Lot 2). 
2. **Typo/noise parents** in `titles` — `1-106`, `F-106`, `210-23`, `T-52917`, `T-32912-14`, `T-1` — OCR/entry
   noise; the true lineage of T-23796, T-46038, T-52538, T-36668, T-52536 is **uncertain** until cleaned.
3. **Only ~7 edges are `[V]`**; the rest `[I]`. Provenance must be earned from each CTC, not asserted.
4. **43 estate titles carry NO area** — the single biggest compilation gap.

## §5 CTC-pull worklist to CLOSE the map (over-prepare: know exactly what to obtain)
Ranked by how much of the 139,132 they close:
1. **T-32911 (Lot 2-A, Barangay 5)** — ~8,706 sqm; also the govt-taking parcel → double value.
2. **The 8 adverse-holder lots** (Santiago ×2, Pascual ×2, Ramirez, Valledor, Tychingco, + confirm Leaño/
   Vergara areas) — closes the recovery targets' areas AND feeds the nullity/back-rent figures.
3. **T-147652 + the uncaptured T-32917 sub-lots** — closes the ~11,022 sqm inside Lot 2-X-6.
4. **T-49062** (patent-derived, P-2218) — area for the clean-sale set.
5. **The 43 no-area titles** generally — RD certified copies.
Each pull upgrades its row `[I]/[U] → [V]`, fills the area, and confirms the true parent (fixing §4).

## §6 What this map lets us assert (only on `[V]` lines)
Once closed and verified, the estate can state to the sqm: *"Of the 139,132 sqm of T-4497, X sqm is
Keesey-held and clean, Y sqm is adverse-held under the void de la Fuente chain (named holders, named areas),
Z sqm is government-occupied, and 0 sqm is unaccounted."* That sentence — provable, closed, doc-grounded —
is the bulletproof foundation for every demand, ejectment, nullity, and sale. **We do not make it until the
gap is 0.**

*Internal spine layer — verified compilation. Field/records items are to be OBTAINED, never estimated-as-fact.*
