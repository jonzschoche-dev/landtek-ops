# T-4497 Land-Bank & Squatter Ledger — MWK-001 (Keesey / Mary Worrick Keesey Estate)

**Scope:** Mercedes, Camarines Norte parcels of the Mary Worrick Keesey estate.
**Purpose:** INTERNAL profit-intelligence roll — turn the estate's tax declarations into a valued, per-parcel ledger, name candidate occupants/settlers where knowable, and attach a recovery + monetization lever to each.
**Status:** Analysis only. Nothing here is filed, sent, or exposed. No DB rows were mutated; proposed SQL in §7 is draft-only.
**Prepared:** 2026-07-19 · Source of record: live corpus (139 tax docs in `documents`, `titles`, `title_tax_links`, `property_assets`, `transferees`).

**Provenance legend:** `[V]` verified = read directly from a document's own fields, doc id cited · `[I]` inferred = co-occurrence / pattern (incl. all `title_tax_links` confidence 0.75) · `[U]` unknown = not in corpus. OCR corrections tagged inline `[OCR: raw]`, uncertain reads `[?]`, human-check items `[HUMAN VERIFY]`.

---

## 1. Executive summary — the position

**The estate's own tax declarations value the declared Mercedes land bank at ≈ ₱90.9 M market value / ≈ ₱8.9 M assessed value across ~40 valued parcels `[V]`** (assessor's schedule value from the parcels' own RPA Form 1A fields; true sale/fair-market value is materially higher — see gap G-2). Coverage: ~40 of ~44 Keesey-declared parcels carry a full valuation; the remainder (four Barangay-20 / Barangay-19 parcels) have PIN-only records with no value in the corpus.

**The profit thesis in four sentences.** For 30+ years the Keesey heirs have carried tax declarations, paid/assessed real-property tax (RPT ledgers run 1990→2024 `[V]` doc 49), and in 2023 proposed a ₱775,202 amnesty settlement under RA 7160 `[V]` doc 290 — an unbroken paper trail of *ownership exercised and possession asserted in concept of owner*, which is precisely the evidence that powers accion publiciana / accion reivindicatoria to recover parcels held by settlers-with-paper. The single strongest fact in the corpus: **the identical assessor parcel PIN 025-07-001-01-047 / physical Lot 2-X-6-I-4-C-1 (2,587 sqm) is tax-declared BY BOTH the Keesey estate (via T-52540) AND by defendant Gloria Balane (via TCT 079-2021002126)** — a documented, dueling tax-declaration overlap that is the factual core of Civil Case 26-360 `[V]` docs 238 vs 411. Behind Balane sit at least seven more of the 20 named transferees holding derivative titles carved out of the Keesey mother titles T-4497 and T-32917 — the "illegal settlers with paper" — each a discrete recovery target. The near-term money is the clean-title subset (T-52537, T-47655, T-49062, T-079-2021002127) that is sellable/leasable the moment the controlling Balane litigation clears the cloud.

**Occupant knowledge.** Of ~40 valued Keesey parcels, **one has a documented adverse tax-declarant (Balane, PIN …-047)** `[V]`; **~8 collide by title-chain with named transferees** `[V from titles, I on the specific tax-dec]`; **three Barangay-5 parcels carry actual-use "GOVT"** suggesting government/road occupation `[V]`; **the physical occupant of the remaining ~28 parcels is UNKNOWN** — the corpus does not yet record who stands on them (gap G-1). We do not invent occupants.

**Headline data-integrity finding (fix before relying on `lifecycle_status`):** `titles.lifecycle_status='active'` currently mislabels titles whose own `status='cancelled'` — including the three ~80-ha giants T-4502, T-4503, T-30681. Treat `status='cancelled'` as authoritative (cancelled = chain context, NOT active estate). See §4 and §7 fix F-1.

---

## 2. (A) Active Keesey estate + tax declarations — the valued, recoverable core

**Definition applied:** titles WHERE `lifecycle_status='active'` AND `status IN ('active','clouded')` AND registrant is the Keesey heirs, PLUS their governing mother lots (T-32916/T-32917, flagged `superseded` but Keesey-registered). Tax-dec (ARP→PIN) links via `title_tax_links` are confidence 0.75 = **`[I]` inferred** unless noted `[V]`/`[0.8]`.

### 2a. Active Keesey titles (title layer)

| Title | Registrant | status / lifecycle | Area (title) sqm | Parent | Linked ARP tax dec | Notes |
|---|---|---|---|---|---|---|
| T-079-2021002127 | Heirs of MWK | active / active | — | T-52540 | ARP-GR-2023-II-07-001-00256 `[I]` | clean sibling of Balane's …126; **property_assets marks title_status='clean'** |
| T-47655 | Heirs of MWK | active / active | 7,186 | T-32917 | ARP-GR-2014-HH-07-001-00248 `[I]` | clean; sellable-now candidate |
| T-48336 | Heirs of MWK | active / active | 14,817 | T-47656 | ARP-001-00249 / …-00248 `[I]` | largest clean active parcel |
| T-49062 | Heirs of MWK | active / active | — | **P-2218 (patent)** | ARP-GR-2014-HH-07-001-00248 `[I]` | patent-derived; clean; see §3 note |
| T-52537 | Heirs of MWK | active / active | 152 | T-32916 | **ARP GR-2014-HH-07-003-00169 `[0.8]` → PIN 025-07-003-01-057 `[V]` doc 232** | clean; Lot 2-X-4-E; adjoining owner = co-heir G. Hoppe (self-bounded) |
| T-38838 | Mary Worrick Keesey | clouded / active | 32,448 | T-32917 | ARP-GR-2014-HH-07-001.00246 `[I]` | largest clouded active; San Roque |
| T-49061 | Heirs of MWK | clouded / superseded | 31,027 | T-10704 | — | mother of Balane branch (T-52540←T-49061) |
| T-51641 | Heirs of MWK | clouded / active | (296 per dec) | 1-106 | **ARP GR-2014-HH-07-001-00223 `[0.8]` → PIN 025-07-001-01-039 `[V]` docs 54, 30** | verified title↔PIN link |
| T-46460 | Heirs of MWK | clouded / active | — | — | ARP-GR-2014-HH-07-001-00248 `[I]` | |
| T-147652 | Heirs of MWK | clouded / active | — | T-32917 | — | |
| T-32478 | Heirs of MWK | clouded / active | — | T-111 | — | |
| T-32912 | Heirs of MWK | clouded / active | 1,395 | T-7106 | — | |
| T-32914 | Heirs of MWK | clouded / active | — | T-4497 | — | |
| T-49060 | Mary Worick `[OCR: Worrick]` | clouded / active | — | — | — | doc 241 |
| **T-32917** | Mary Worrick Keesey | active / **superseded** | **85,149** | T-4497 | ARP-GR-2014-HH-07-001.00246 `[I]` | **mother Lot 2-X-6 / San Roque** — governs the Balane + Leaño + Vergara branch |
| **T-32916** | Mary Worrick Keesey | active / **superseded** | **14,416** | — | — | **mother Lot 2-X-4 / Brgy 3** — governs T-52537 branch |
| T-47657 | Heirs of MWK | clouded / superseded | 13,124 | T-126 | — | |
| T-30683 | Mary Worrick Keesey | clouded / active | **804,148 (~80.4 ha)** | T-111 | see §3 (agrarian) | **[HUMAN VERIFY: T-4497 derivative relationship NOT verified — Manguisoc is a separate location]** |

### 2b. Per-PIN tax-declaration ledger (parcel layer — authoritative valuations)

Source: consolidated declaration bundle **doc 30** + the estate's own master property list **doc 295 (2023-10-01)** `[V]`, cross-checked against individual FAAS/declaration reads. All owners read as "Hrs. of Mary Worrick Keesey namely Geraldine K. Hoppe, Patricia K. Zschoche and Marcia Ellen Keesey `[OCR: Kessey]`" unless noted; Administrator historically "C/O Cesar de la Fuente" on the 2011/2014 series `[V]` doc 30. All values `[V]`.

**Barangay 1 (San Roque / Vicente Basit Extn) — PIN prefix 025-07-001-01**

| PIN | ARP | Area sqm | Use | Market Value ₱ | Assessed ₱ | Occupant / status | Recovery lever | Monetization | Src doc |
|---|---|---|---|---|---|---|---|---|---|
| …-004 | 001-00268 | 19,399 | Residential | 18,817,030 | 1,505,360 | UNKNOWN `[U]` | tax-dec possession pack | large infill — subdivide/lease | 295, 30 |
| …-006A | 001-00006 | 10,000 | **Industrial** | 11,000,000 | 1,650,000 | UNKNOWN `[U]` | tax-dec possession pack | industrial lease/sale (highest value/use) | 30, 295 |
| …-006 | 001-00245 | 8,565 | Residential | 8,308,050 | 664,640 | UNKNOWN `[U]` | tax-dec possession pack | subdivide/sell | 295 |
| …-010A | 001-00129 | 4,651 | **Industrial** | 5,116,100 | 767,420 | UNKNOWN `[U]` | tax-dec possession pack | industrial lease | 30, 295 |
| …-012 | 001-00228 | 5,212 | Residential | 4,967,300 | 476,890 | UNKNOWN `[U]` | tax-dec possession pack | subdivide/sell | 295 |
| **…-047** | **001-00274 (Keesey, TCT T-52540 PT)** | **2,587** | Residential | **2,509,390** | 200,750 | **⚠ ADVERSE: also declared by GLORIA H. BALANE, ARP GR-2023-II-07-001-00256, MV 4,294,420, via TCT 079-2021002126** `[V]` docs 238 vs 411 | **THE Civil Case 26-360 parcel — quiet title / reivindicatoria** | gated on MWK-CV26360 | 238, 411 |
| …-008 | 001-00271 | 2,790 | Residential | 2,706,300 | 216,500 | UNKNOWN `[U]` | tax-dec possession pack | subdivide/sell | 295, 30 |
| …-051 | 001-00267 | 1,212 | Residential | 1,175,640 | 94,050 | UNKNOWN `[U]` | tax-dec possession pack | sell/lease | 30, 295 |
| …-003 | 001-00030 | 1,250 | Residential | 737,500 | 59,000 | UNKNOWN `[U]`; boundary "NE Pacific Ocean" (coastal) | tax-dec possession pack | coastal — resort/lease | 30 |
| …-017 | 001-00187 | 1,000 | Residential | 590,000 | 47,200 | UNKNOWN `[U]` (dec names Patricia Zschoche / Hoppe) | tax-dec possession pack | sell/lease | 30 |
| …-046 | 001-00244 | 469 | Residential | 454,930 | 36,390 | UNKNOWN `[U]` | tax-dec possession pack | sell | 295 |
| …-043 | 001-00230 | 327 | Residential | 317,190 | 25,380 | UNKNOWN `[U]` | tax-dec possession pack | sell | 30, 295 |
| …-039 | 001-00223 | 296 | Residential | 287,120 | 22,970 | UNKNOWN `[U]`; **TCT T-51641** `[V]` | tax-dec possession pack | sell | 54, 295 |
| …-052 | 001-00270 | 264 | Residential | 256,080 | 20,490 | UNKNOWN `[U]` | tax-dec possession pack | sell | 30, 295 |
| …-040 | 001-00226 | 186 | Residential | 180,420 | 14,430 | UNKNOWN `[U]` | tax-dec possession pack | sell | 295 |
| …-044 | 001-00237 | 186 | Residential | 180,420 | 14,430 | UNKNOWN `[U]` | tax-dec possession pack | sell | 295 |
| …-050 | 001-00264 | 165 | Residential | 160,050 | 12,800 | UNKNOWN `[U]` | tax-dec possession pack | sell | 30, 66 |
| …-049 | 001-00258 | 160 | Residential | 155,200 | 12,420 | UNKNOWN `[U]` | tax-dec possession pack | sell | 99, 295 |
| …-041 | 001-00227 | 157 | Residential | 152,290 | 12,180 | UNKNOWN `[U]` | tax-dec possession pack | sell | 30, 295 |
| …-042 | 001-00229 | 56 `[OCR: 53?]` | Residential | 54,320 | 4,350 | UNKNOWN `[U]` | tax-dec possession pack | sell | 295 |
| …-003A | 001-00249 `[?]` | — | — | — | 1,932,140 `[I OCR]` | UNKNOWN `[U]` | verify — value looks like a mis-read | — | 226 |

**Barangay 3 (Mercedes town / Lot 2-X-4) — PIN prefix 025-07-003**

| PIN | ARP | Area sqm | Use | Market Value ₱ | Assessed ₱ | Occupant / status | Src doc |
|---|---|---|---|---|---|---|---|
| …-01-021 | 003-00281 | 12,818 | Residential | 12,433,460 | 994,680 | UNKNOWN `[U]` | 295 |
| …-02-059 | 003-00243 | 5,731 | Residential | 5,559,070 | 444,730 | UNKNOWN `[U]` (declarant Elmer Worrick per doc 37) | 141, 37 |
| …-01-007 | 003-00035 | 1,537 | Residential | 1,490,890 | 119,270 | UNKNOWN `[U]` | 295 |
| …-01-018 | 003-00051 | 1,019 | Residential | 988,430 | 79,070 | UNKNOWN `[U]` | 295 |
| …-01-057 | 003-00169 | 152 | Residential | 147,440 | 11,800 | UNKNOWN `[U]`; **TCT T-52537 (clean active)** `[V]`; adjoining = co-heir Hoppe | 232, 295 |
| …-01-058 | 003-00264 | 126 | Residential | 122,220 | 9,780 | UNKNOWN `[U]` | 30, 295 |
| …-01-039 | 003-00146 | 22 | Residential | 21,340 | 1,710 | UNKNOWN `[U]` | 131, 295 |
| …-01-038 | 003-00145 | 10 | Residential | 9,700 | 780 | UNKNOWN `[U]` | 295 |

⚠ **Gaulit cross-signal `[HUMAN VERIFY]`:** the Barangay-3 assessment roll inside doc 30 lists ARP 003-00169 (the T-52537 parcel's ARP) under declared owner "GAULIT, DELFIN & LUISA, SPS" in the alphabetical roll, while the FAAS (doc 232) and property list (doc 295) declare the same 003-00169 ARP / PIN …-057 to the Keesey heirs. Delfin Gaulit is transferee #6. This is either an OCR/roll artifact or a genuine competing declarant on a Keesey clean-title parcel — **do not assert; verify against the assessor's roll original.**

**Barangay 5 — PIN prefix 025-07-005-01**

| PIN | ARP | Area sqm | Use | Market Value ₱ | Assessed ₱ | Occupant / status | Src doc |
|---|---|---|---|---|---|---|---|
| …-007 | 005-00045 | 8,951 | **GOVT** | 8,682,470 | 694,600 | **candidate: government-occupied** `[V use]` `[HUMAN VERIFY occupant]` | 151 |
| …-008 | 005-00236 | 973 | **GOVT** | 943,810 | 75,510 | **candidate: government-occupied** | 152 |
| …-025 | 005-00220 | 800 | **GOVT** | 776,000 | 62,080 | **candidate: government-occupied** | 150 |
| …-009 | 005-00056 | 1,138 | Residential | 1,103,860 | 88,310 | UNKNOWN `[U]` | 295 |
| …-016 | 005-00067 | 231 | Residential | 224,070 | 17,930 | UNKNOWN `[U]` | 30 |
| …-024 | 005-00088 | 46 | Residential | 44,620 | 3,570 | UNKNOWN `[U]` | 134, 295 |

⚠ The three "GOVT" actual-use parcels imply a public body / road occupies Keesey land → distinct lever = expropriation-with-just-compensation claim or back-rental demand (not ejectment). **Verify the occupying agency.**

**Barangay 19 (Mambungalon — coconut / swamp, agricultural) — PIN prefix 025-07-019**

| PIN | ARP | Use | Market Value ₱ | Assessed ₱ | Occupant / status | Src doc |
|---|---|---|---|---|---|---|
| …-04-059 | 019-00204 | Coconut | 93,857.50 | 19,770 | UNKNOWN `[U]`; area 13,181 sqm `[V]` doc 49 | 30, 49 |
| …-04-061 | 019-00206 | Swamp `[OCR: Swanp]` | 115,075.97 | 23,020 | UNKNOWN `[U]` | 30, 49 |
| …-04-062 | 019-00207 | Coconut `[OCR: Caconut]` | 35,730 | 7,150 | UNKNOWN `[U]` | 30, 49 |
| …-03-001 | 019-00110 | Coconut `[OCR: Cocoru]` | (MV OCR-garbled) | 412,110 | UNKNOWN `[U]` | 30 |
| …-04-057 | 019-00202 | Coconut | (MV missing) | 830 | UNKNOWN `[U]` | 30, 49 |

**PIN-only / no-value records (corpus gap):** 025-07-020-03-004, …-03-044, …-04-001, …-04-002 (Barangay 20, from statement doc 121); 025-07-019-04-060, …-04-076 (doc 49); 025-07-005-01-062/064/067/079 (amnesty statements docs 538/544/545/547); 025-07-001-01-010 & …-048 (partial). No ARP/area/value captured — see gap G-4.

**Roll-up (verified tax-dec values):** Barangay 1 ≈ **₱58.1 M** MV / ₱5.86 M AV · Barangay 3 ≈ **₱20.8 M** MV / ₱1.66 M AV · Barangay 5 ≈ **₱11.8 M** MV / ₱0.94 M AV · Barangay 19 ≈ **₱0.24 M+** MV / ₱0.46 M AV. **Total ≈ ₱90.9 M market value / ≈ ₱8.9 M assessed value** across ~40 valued parcels. (AV is the RPT base; several individual AV cells in the raw OCR were garbled and were taken from the clean doc-295 master list.)

---

## 3. (B) Agrarian-reform component — verified vs mis-scoped

The operator flags agrarian reform (CLOA / EP / CARP / patent) as part of the active estate. Findings:

| Instrument | What it is | Keesey? | Verdict |
|---|---|---|---|
| **T-30683 (Manguisoc)** | ~80.4 ha; held by the 4 heirs in undivided interest; **Landbank CARP claim 05-E0228-99-1544** `[V]` doc 374/notes | **YES — Mary Worrick Keesey / 4 heirs** | **KEEP as the live agrarian asset.** This is a genuine CARP/Landbank compensation claim owned by the estate — a monetizable agrarian receivable, not a parcel to sell. `[HUMAN VERIFY: relationship to T-4497 unverified; Manguisoc is a distinct location — treat as its own agrarian matter within MWK]` |
| **T-49062** | Keesey active title whose **parent is P-2218, a Patent** `[V]` doc 40 chain | YES — Heirs of MWK | Patent-derived (land-grant lineage), clean, active. Note as patent origin; treat as an ordinary clean active parcel (§5). |
| **T-772 / T-CLOA-T-772** | **CLOA No. 00123801 under RA 6657**, issued by DAR, registered as TCA-772; parcel = **Cabanbanan, San Vicente** `[V]` doc 282 | **NO — awarded to an agrarian beneficiary, not the Keesey heirs; and San Vicente, not Mercedes** | **The `out_of_scope` / `not_mwk_heirs` flag is CORRECT for the T-4497 active estate.** It is a DAR award on the separate San Vicente/Cabanbanan land (the CV6839 family group). Not mis-scoped. `[HUMAN VERIFY only if the estate claims the underlying land was Keesey land taken under CARP — that would be a San Vicente matter, kept separate per the standing client-separation rule.]` |
| T-4494, T-4501, T-30583, T-30682 | "CARP / CV6839 family group" `[V]` notes doc 673 | Unverified; San Vicente | **Separate matter** (standing separation rule). Not part of the T-4497 Mercedes estate. Chain/context only. |

**Bottom line (B):** the only agrarian-reform item that is both Keesey and active is **T-30683's Landbank CARP compensation claim** (an ~80-ha receivable). The CLOA (T-772) is correctly out-of-scope — it is a beneficiary award on the separate San Vicente land. No mis-scoping to reverse; recommend adding a `lifecycle_notes` breadcrumb so the CLOA's out-of-scope status is not re-litigated each session.

---

## 4. (C) Adverse-holder collision map — the "settlers with paper"

These are `active`/`clouded` titles registered to **non-Keesey names that match the 20 transferees**, each derived from a Keesey mother title. The chain derivation (parent = Keesey title) is `[V]` from `titles`; the specific tax-declaration overlap is `[V]` only for Balane and otherwise **`[HUMAN VERIFY]`** (the 0.75 `title_tax_links` are co-occurrence noise — e.g. T-51641 spuriously "links" to ~40 ARPs because doc 30 is one big bundle).

| Adverse holder | Their title | Area sqm | Parent (Keesey mother) | Collides with (Keesey active asset) | Tax-dec collision | Transferee # |
|---|---|---|---|---|---|---|
| **Gloria Balane** | **079-2021002126** | 2,587 | T-52540 ← T-49061 ← … ← **T-32917** (Lot 2-X-6) | **Keesey T-52540 dec on PIN 025-07-001-01-047** | **VERIFIED overlap** `[V]` docs 238 vs 411 — same PIN, same Lot 2-X-6-I-4-C-1, same survey PSD-E2020005405/6 | #20 (lead defendant) |
| Roscoe Leaño `[OCR: Rosco Leano]` | T-33776 | 1,295 | **T-32917** | T-32917 mother (Lot 2-X-6, 85,149 sqm) | `[HUMAN VERIFY]` | #17 |
| Elena Vergara | T-33350 | 339 | **T-32917** | T-32917 mother | `[HUMAN VERIFY]` — **note: Vergara is NOT among the 20 named transferees** | — |
| Cesar S. Ramirez | T-40718 | — | **T-4497** (root) | T-4497 root estate | `[HUMAN VERIFY]` | #5 |
| Jose Pascual Jr. | T-48335 **and** T-33686 | — | **T-4497** | T-4497 root estate | `[HUMAN VERIFY]` | #11 |
| Pedro Valledor | T-51640 | — | **T-4497** | T-4497 root estate | `[HUMAN VERIFY]` | #15 |
| Edgardo Santiago | T-33415 **and** T-33416 | — | **T-4497** | T-4497 root estate | `[HUMAN VERIFY]` | #8 |
| Erlinda Tychingco | T-34243 | — | **T-4497** | T-4497 root estate | `[HUMAN VERIFY]` | #10 |

**Reading the map.** Balane is the proven, litigated tip (documented dueling tax dec). The other seven are titled adverse holders whose paper derives directly from the Keesey mother titles T-4497 (root) and T-32917 (Lot 2-X-6) — i.e., derivative titles the estate says should never have issued. Each derivation IS the recovery target. **The immediate diligence lift is to pull each adverse holder's current tax declaration (ARP + PIN) and confirm whether it sits on a Keesey PIN — replicating the Balane …-047 overlap. That converts each row from a title-chain theory into a Balane-grade documentary collision.**

---

## 5. Recovery-lever analysis (grouped) + near-term monetizable subset

**Lever (a) — tax-dec-backed accion publiciana / reivindicatoria vs a named settler.**
The estate's 30-year tax-declaration + RPT-payment trail is the possession/dominion spine. Ripe targets = the §4 adverse holders. Balane (…-047) is already in suit (26-360); the other seven become filing-ready once each one's tax dec is confirmed against a Keesey PIN.

**Lever (b) — parcels gated on the Balane MWK-CV26360 outcome.**
Every clouded Keesey parcel derived from T-32917 / T-52540 (…-047, T-38838, T-51641, T-147652, and the whole Lot 2-X-6 branch) is legally gated on the Balane ruling — a favorable 26-360 judgment de-clouds the branch wholesale. This is the single highest-leverage event in the portfolio.

**Lever (c) — clean-title parcels sellable/leasable NOW (title_status='clean' in property_assets).**
Confirmed clean & active: **T-52537** (152 sqm, PIN …-057, ₱147k MV), **T-47655** (7,186 sqm), **T-49062**, **T-079-2021002127**. (property_assets also flags T-772 / …2021002127-variant clean, but T-772 is the out-of-scope CLOA — exclude.)

**Near-term monetizable subset (rough, tax-dec MV — a floor, not market):**
- **T-48336 — 14,817 sqm, active/clean** → largest clean developable parcel. At the estate's own Barangay-1 schedule (~₱970/sqm) ≈ **₱14 M** indicative; true sale value higher. **Top monetizable-now.**
- **T-47655 — 7,186 sqm, active/clean** (San Roque, ex-T-32917) → ≈ **₱7 M** indicative. Subdivide/sell.
- **PIN 025-07-001-01-006A — 10,000 sqm INDUSTRIAL, ₱11.0 M MV `[V]`** → highest single valued parcel and industrial-use (lease income) — but occupant UNKNOWN and title link not yet nailed; confirm the governing Keesey title, then lease.
- **T-52537 — 152 sqm, clean** → small, clean, immediately conveyable (pilot sale to prove the clean-title pipeline end-to-end).
- **T-30683 CARP receivable (~80 ha)** → not a sale; pursue Landbank claim 05-E0228-99-1544 valuation/collection.

---

## 6. Data-gap punch list (ranked by profit impact)

| # | Gap | Blocks | Cheapest close |
|---|---|---|---|
| **G-1** | **Physical occupant unknown for ~28 of ~40 valued parcels.** Corpus records the declarant, not who stands on the land. | Every ejectment/publiciana lever (a) — no occupant = no defendant | **Field:** a one-day site canvass + barangay certification per PIN. $0-local cannot manufacture this — it is a field/records request. Prioritize the high-value Barangay-1 parcels (…-004, …-006A, …-006, …-012). |
| **G-2** | **True fair-market / sale value unknown.** Only the assessor's schedule MV (₱90.9 M) is in-corpus; sale value is materially higher and un-benchmarked. | Pricing every sale/lease; the ROI headline | **$0-local:** scrape 3-5 comparable Mercedes/San Roque listings; **field:** one local broker BPO. |
| **G-3** | **Adverse-holder tax decs not pulled (7 of 8).** Only Balane's ARP/PIN overlap is documented. | Upgrading §4 rows from title-theory to Balane-grade documentary collisions → filing-ready | **Records:** Assessor certified true copies of each adverse title's current ARP (₱ nominal per parcel). Highest legal ROI of the list. |
| **G-4** | **PIN-only parcels with no ARP/area/value** (Barangay 20 ×4, Barangay 19 ×2, Barangay 5 amnesty ×4). | Completing the land-bank valuation; ~4 parcels missing entirely | **$0-local:** re-OCR the statement-of-account docs (121, 538, 544, 545, 547) with vision model; **records:** Assessor tax-dec printouts. |
| **G-5** | **RPT arrears unstructured.** Per-year ledgers exist (doc 49 etc.) but aren't parsed into a per-PIN arrears table; only the ₱775,202 amnesty aggregate is clean `[V]` doc 290. | Quantifying the carrying-cost / amnesty-window decision per parcel | **$0-local:** parse the statement-of-account ledgers into `parcel_tax_declarations` (see §7). |
| **G-6** | **`title_tax_links` is 390/395 co-occurrence noise (0.75).** Only 5 links are 0.8; PIN column 100% empty. | Trustworthy title↔parcel joins across the whole ledger | **$0-local:** re-derive links from the FAAS/declaration docs where TCT + ARP + PIN appear in the same form (as done here for T-51641, T-52537, Balane); backfill `title_tax_links.pin`. |
| **G-7** | **`lifecycle_status` contradicts `status`** (active-labelled cancelled titles). | Any automated "active estate" query is currently wrong | Fix F-1 (§7). $0-local. |

---

## 7. Proposed DB writes — DRAFT SQL ONLY (do NOT execute; operator review)

> All statements below are proposals. Nothing has been run. Values sourced from the parcels' own tax decs (`[V]`); apply only after human verification of the flagged rows. Follows the standing rule: `.bak` / idempotent / re-read at write time.

```sql
-- ============================================================================
-- F-1  DATA-INTEGRITY FIX: lifecycle_status='active' must not hold status='cancelled'.
--      status='cancelled' is authoritative (cancelled = chain context, not active estate).
--      REVIEW the row list first; this is a proposal, not an auto-migration.
-- ============================================================================
-- Preview the contradiction set:
SELECT tct_number, status, lifecycle_status, area_sqm
FROM titles
WHERE case_file='MWK-001' AND lifecycle_status='active' AND status='cancelled';
-- Proposed correction (after review):
-- UPDATE titles SET lifecycle_status='chain_context',
--        lifecycle_notes = coalesce(lifecycle_notes||' | ','')
--          ||'2026-07-19: demoted from active — status=cancelled is authoritative (land-bank ledger F-1)'
--  WHERE case_file='MWK-001' AND lifecycle_status='active' AND status='cancelled';

-- Keep the CLOA out-of-scope decision from being re-litigated:
-- UPDATE titles SET lifecycle_notes = coalesce(lifecycle_notes||' | ','')
--   ||'2026-07-19: CONFIRMED out_of_scope — RA6657 CLOA #00123801, San Vicente/Cabanbanan beneficiary award, not Keesey-heir land (doc 282); separate from T-4497 Mercedes estate'
--  WHERE case_file='MWK-001' AND tct_number IN ('T-772','T-CLOA-T-772');

-- ============================================================================
-- W-1  Backfill property_assets valuations + area from verified tax decs.
--      est_value is presently NULL on ~61 of 63 MWK rows; area_sqm mostly NULL.
--      Match is by governing TCT where verified; otherwise leave for human link.
--      (assessor MARKET VALUE used as est_value floor — flag in monetization note.)
-- ============================================================================
-- Verified title <-> PIN <-> value rows (safe to propose):
--   T-52537  -> PIN 025-07-003-01-057, 152 sqm,  MV 147,440   (docs 232/295)  [V]
--   T-51641  -> PIN 025-07-001-01-039, 296 sqm,  MV 287,120   (docs 54/295)   [V/0.8]
-- Example (T-52537); repeat per verified row, upsert-style, never delete+reinsert:
-- UPDATE property_assets
--    SET area_sqm = 152,
--        est_value = 147440,          -- assessor MV floor; true sale value higher (gap G-2)
--        monetization_plan = monetization_plan||' | tax-dec MV floor 147,440 (doc 232/295); clean+active — sell-now pilot'
--  WHERE asset_code='PA-T-52537' AND case_file='MWK-001';

-- ============================================================================
-- W-2  Proposed structured table for the parcel/RPT layer the corpus lacks.
--      One row per PIN per ARP (declaration), plus a child arrears table.
--      Warranted: 40+ valued parcels currently live only in free-text OCR.
-- ============================================================================
-- CREATE TABLE IF NOT EXISTS parcel_tax_declarations (
--   id                serial PRIMARY KEY,
--   case_file         text NOT NULL DEFAULT 'MWK-001',
--   pin               text NOT NULL,                 -- assessor Property Index No (parcel key)
--   arp_no            text,                           -- Assessment of Real Property No
--   barangay          text,
--   declared_owner    text,
--   administrator     text,
--   linked_tct        text,                           -- governing title where known
--   area_sqm          numeric(15,2),
--   actual_use        text,                           -- residential/industrial/coconut/govt...
--   market_value      numeric(15,2),
--   assessed_value    numeric(15,2),
--   adjoining_owners  text,                           -- candidate occupants/encroachers
--   provenance_level  text NOT NULL DEFAULT 'verified',
--   source_doc_id     integer REFERENCES documents(id),
--   source_quote      text,
--   notes             text,
--   created_at        timestamptz DEFAULT now(),
--   UNIQUE (pin, arp_no)
-- );
-- CREATE TABLE IF NOT EXISTS parcel_rpt_ledger (
--   id            serial PRIMARY KEY,
--   pin           text NOT NULL,
--   tax_year      int  NOT NULL,
--   basic         numeric(12,2),
--   sef           numeric(12,2),
--   penalty       numeric(12,2),
--   total_due     numeric(12,2),
--   paid          boolean,
--   source_doc_id integer REFERENCES documents(id),
--   UNIQUE (pin, tax_year)
-- );
-- Seed example (verified from doc 411 — the Balane overlap, for the adverse map):
-- INSERT INTO parcel_tax_declarations
--   (pin, arp_no, barangay, declared_owner, linked_tct, area_sqm, actual_use,
--    market_value, assessed_value, provenance_level, source_doc_id, notes)
-- VALUES
--   ('025-07-001-01-047','GR-2023-II-07-001-00256','Barangay 1','GLORIA H. BALANE',
--    '079-2021002126', 2587, 'Residential', 4294420, 257670, 'verified', 411,
--    'ADVERSE declarant — same PIN as Keesey T-52540 dec ARP GR-2014-HH-07-001-00274 (doc 238); Civil Case 26-360')
-- ON CONFLICT (pin, arp_no) DO NOTHING;
```

---

## 8. Source-doc index (load-bearing)

- **doc 295** — 2023-10-01 master property list (authoritative per-PIN ARP/area/MV/AV table). Primary valuation source.
- **doc 30** — 2014-06-23 consolidated declaration bundle (multi-parcel RPA Form 1A + Barangay-3 assessment roll).
- **doc 238** — 2021-09-21 Keesey FAAS, PIN 025-07-001-01-047, TCT T-52540 (PT), Lot 2-X-6-I-4-C-1, MV 2,509,390 (CTC ex RD Cam. Norte). Half of the Balane overlap.
- **doc 411** — Balane's Exhibit 2 (Civil Case 26-360): PIN 025-07-001-01-047, TCT 079-2021002126, MV 4,294,420. Other half of the overlap.
- **doc 232** — 2025 FAAS, PIN 025-07-003-01-057, TCT T-52537, Lot 2-X-4-E, 192/152 sqm (clean active).
- **doc 49** — Statement of Account, per-PIN yearly RPT ledger 1990→2017+ (arrears trail).
- **doc 290 / 293** — 2023 tax-amnesty proposal (Patricia Zschoche): liability reduced to ₱775,202; Sec-270 RA 7160 prescription argument.
- **doc 282** — T-772 CLOA No. 00123801 (RA 6657, DAR), Cabanbanan/San Vicente — out-of-scope confirmation.
- **doc 428** — Exhibit D-to-D-1, Complaint, Civil Case 26-360 (litigation context for …-047).

*End of ledger. Internal work product — not for filing, sending, or external exposure.*
