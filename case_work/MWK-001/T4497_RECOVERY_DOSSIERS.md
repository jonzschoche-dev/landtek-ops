> ⚠️ **MERGED INTO `MWK-DLF-VOID` (2026-07-19).** The authoritative recovery roster lives in
> `investigations/MWK-DLF/` (README tier map + `DOSSIER_MWK-DLF-VOID.md`), which ranks these same
> holders by deed-date-past-SPA-lapse (Tier 2 Dean/Capistrano post-lapse = strongest) and is more
> complete than these cards. Use that roster for recovery; this file is a subset kept for reference.
> Wiring to the profit layer: `investigations/MWK-DLF/PROFIT_LAYER_INDEX.md`.

# T-4497 Recovery Dossiers — extending the Balane playbook to the estate (MWK-001, Track 4)

**Scope:** The eight titled/occupied adverse holders on Keesey (Mary Worrick Keesey) land in Mercedes, Camarines Norte, plus the three government-occupied Barangay-5 parcels. Purpose: turn each into a **filing-ready recovery theory** backed by the estate's 30-year tax-declaration + RPT-payment possession spine, reusing the Balane void-chain legal architecture.
**Status:** INTERNAL counsel-grade ammunition ONLY. Nothing here is filed, sent, or exposed. No DB rows mutated. The operator + counsel decide and execute; this desk never files, sends, or contacts anyone.
**Prepared:** 2026-07-19 · Sources: the valued ledger (`T4497_LANDBANK_SQUATTER_LEDGER.md`), the Balane spine (`BALANE_EVIDENCE_SPINE.md`), and live corpus (`titles`, `title_chain`, `title_tax_links`, `transferees`, `documents`).
**Provenance legend:** `[V]` verified from a document's own fields (doc id cited) · `[I]` inferred (chain/co-occurrence) · `[U]` unknown / not in corpus · `[HV]` human-verify flag. The one iron rule: **only Balane's tax-dec collision is documentary. The other seven are title-chain theory until the G-3 Assessor pull lands.** Do not overstate.

---

## 0. DECISION-FIRST — the position, and what to do next

**The claim.** The Keesey estate holds an unbroken 30-year documentary record of ownership exercised and possession asserted in the concept of owner over the T-4497 / T-32917 land — tax declarations 1990→2024 `[V]` doc 49, RPT payments, and a 2023 amnesty settlement of ₱775,202 `[V]` doc 290. Against that spine sit eight titled adverse holders whose paper derives from the Keesey mother titles. **Balane is the proven template** (documented dueling tax declaration on the same PIN, now in suit as Civil Case 26-360). The other seven are the same structural claim awaiting one documentary step each.

**The decision due now:** which adverse holder becomes *the next Balane* — i.e., which one is worth the G-3 Assessor certified-copy pull first, so its collision converts from chain-theory to Balane-grade documentary proof and it can be worked up into a filing-ready accion reivindicatoria / publiciana.

**Ranked top-3 recovery targets (value × evidence-readiness × ripeness):**
1. **Elena Vergara (T-33350, 339 sqm, ex-T-32917 Lot 2-X-6).** The only non-Balane adverse holder with a **verified chain to T-32917** (`[V]` doc 312, the 1994 TCT itself) AND a **status='clouded'** live title (not cancelled). Same mother lot as Balane → rides the same de-clouding. Best-documented chain of the seven. *Next Balane.*
2. **Roscoe Leaño (T-33776, 1,295 sqm, ex-T-32917 Lot 2-X-6).** Verified T-32917 chain `[V]` doc 318 (a **2025** CTC — freshest paper in the set), largest area among the T-32917-branch adverse holders → highest value at stake on the Balane-gated branch. **Caveat: DB shows his title status='cancelled'** `[V]` — must verify what cancelled it before treating him as the current occupant (§3.3).
3. **Cesar S. Ramirez (T-40718, ex-T-4497 root).** Named in Gloria Balane's OWN judicial affidavit as another de la Fuente buyer (doc 1089 T39–T42) — a **corroboration bridge** that ties his purchase to the identical void-SPA mechanism and helps prove the *campaign* pattern across the 20 transferees. **Caveat: title status='cancelled'** `[V]` — verify (§3.4).

**Collisions verified vs theory-only:** **1 verified (Balane), 7 theory-only.** Every non-Balane row lacks a pulled adverse tax declaration — confirmed live: `title_tax_links` returns **zero rows** for all seven `[V]` (2026-07-19 query). The chain-to-mother-title is `[V]` for Vergara and Leaño (docs 312/318) and `[I]` (inferred_strong, NULL-source) for the five T-4497-root holders.

**Single highest-ROI records request:** the **Assessor certified true copy of the current ARP + PIN for Elena Vergara's T-33350** (and, in the same trip, Leaño's T-33776). One counter visit converts the best-documented chain target into a Balane-grade collision. Full worklist in §6.

**Balane-gated vs stand-alone:** **Vergara and Leaño are Balane-gated** (same T-32917 / Lot 2-X-6 branch — a favorable 26-360 judgment de-clouds the branch wholesale). **The five T-4497-root holders (Ramirez, Pascual, Valledor, Santiago, Tychingco) are structurally parallel but NOT auto-unlocked** by a 26-360 win — each needs its own void-instrument proof (§7).

---

## 1. The reusable legal architecture (the Balane template)

Every card below maps to this spine, proven in the Balane SJ motion (doc 393) and the Balane spine §2a/§3:

- **Void-authority core (Prong A).** De la Fuente's **16 Mar 1992 SPA** (clean text doc 246) was a **special power of *limited object*** — authority to sell **only** to third persons holding Contracts to Sell from prior administrator **Ben Llamanzares**, after consultation. A sale outside that authorized class exceeds the mandate → **void** (Civil Code Arts. 1877–1878; *Bautista-Spille v. Nicorp*, G.R. 214057, 19 Oct 2015; *nemo dat quod non habet*). Good faith cannot cure a void sale. `[V]` doc 246.
- **Revocation backstop (Prong B).** The SPA was **revoked 15 Aug 2005** (published 2020) `[V]` docs 76, 79. A buyer dealing with an agent rather than the registered owner must "discover on her own peril" the fact and extent of authority (*Yoshizaki v. Joy Training Center*, G.R. 174978, 31 Jul 2013).
- **The possession spine (our affirmative case).** The estate's 30-year tax declarations + RPT ledger (doc 49) + 2023 amnesty (doc 290) prove *possession in the concept of owner* — the element that powers accion reivindicatoria / publiciana against a settler-with-paper.
- **The collision proof (what makes it documentary).** Balane's power comes from a **dueling tax declaration on the identical PIN 025-07-001-01-047** — Keesey (doc 238) vs Balane (doc 411), same lot, same survey. Replicating that overlap for each adverse holder (gap G-3) is what converts a chain theory into filing-ready ammunition.

**The critical open question per target (Prong A applicability):** Balane's void-SPA theory works because de la Fuente executed *her* 2016 deed under the 1992 SPA. For the other seven, **we do not yet hold each one's root conveyance** — so we cannot yet assert the *same* void-SPA defect for all. The chain to a Keesey mother title is verified/inferred; the *instrument that broke the chain* (a de la Fuente SPA-sale? an earlier fraudulent transfer? a double-titling?) is the per-target unknown. Gloria Balane's affidavit naming Ramirez and Hansol as fellow de la Fuente buyers (doc 1089 T39–T42) is our first bridge that the mechanism repeats — but it is her testimony, not the deeds. **Do not assert "void SPA" for a target whose root deed we have not read.**

---

## 2. Adverse-holder data table (live DB, 2026-07-19)

| Holder | Title | DB title status | Area sqm | Chain to mother | Chain grade | Tax-dec collision | Transferee # |
|---|---|---|---|---|---|---|---|
| **Gloria Balane** | 079-2021002126 | (contested) | 2,587 | T-52540 ← T-49061 ← **T-32917** | `[V]` docs 288/50/272 | **VERIFIED** docs 238 vs 411 | #20 |
| **Elena Vergara** | T-33350 | **clouded** | 339 | **T-32917** (Lot 2-X-6) | `[V]` doc 312 (1994 TCT) | theory-only `[HV]` | **NOT a transferee** |
| **Roscoe Leaño** | T-33776 | **cancelled** `[HV]` | 1,295 | **T-32917** (Lot 2-X-6) | `[V]` doc 318 (2025 CTC) | theory-only `[HV]` | #17 |
| **Cesar S. Ramirez** | T-40718 | **cancelled** `[HV]` | — | **T-4497** (root) | `[I]` inferred_strong | theory-only `[HV]` | #5 |
| **Jose Pascual Jr.** | T-48335 + T-33686 | clouded | — | **T-4497** (root) | `[I]` inferred_strong | theory-only `[HV]` | #11 |
| **Pedro Valledor** | T-51640 | **cancelled** `[HV]` | — | **T-4497** (root) | `[I]` inferred_strong | theory-only `[HV]` | #15 |
| **Edgardo Santiago** | T-33415 + T-33416 | clouded | — | **T-4497** (root) | `[I]` inferred_strong | theory-only `[HV]` | #8 |
| **Erlinda Tychingco** | T-34243 | clouded | — | **T-4497** (root) | `[I]` inferred_strong | theory-only `[HV]` | #10 |

> **⚠ MATERIAL DB FINDING (banked 2026-07-19).** Three adverse titles — **T-33776 (Leaño), T-40718 (Ramirez), T-51640 (Valledor)** — carry their **own `status='cancelled'`** in `titles`, while `lifecycle_status='active'`. Per the ledger's F-1 finding, `status='cancelled'` is authoritative and `lifecycle_status` is a known mislabel. **A cancelled adverse title means one of two things, and we cannot tell which from the corpus:** (a) the parcel was *further* subdivided/transferred, so the *current* registered adverse holder is someone downstream of the named transferee — in which case the recovery defendant is not Ramirez/Leaño/Valledor but whoever holds the successor title; or (b) it is a chain-context artifact of the mislabel bug. **This is the FIRST thing to resolve per target — the current RD title trace (G-3 records request) answers it. Do NOT name a cancelled-title holder as defendant until the current owner-of-record is confirmed.**

---

## 3. Dossier cards

### 3.0 Gloria Balane (T-079-2021002126) — THE MODEL (do not re-litigate)

Already in suit (Civil Case 26-360). Collision **VERIFIED**: identical PIN 025-07-001-01-047 declared by Keesey (doc 238) and Balane (doc 411). Chain verified end-to-end (spine §3). Remedy: reivindicatoria + nullity of deed + cancellation of title + reinstate T-52540, pending SJ. **This card exists only as the template the seven below replicate.** All Balane work lives in `BALANE_EVIDENCE_SPINE.md` — do not duplicate or re-open it here.

---

### 3.1 Elena Vergara (T-33350, 339 sqm) — #1 target, "next Balane"

1. **Collision status:** **Theory-only** `[HV]`. No tax-dec pulled; `title_tax_links` empty. BUT chain is the best-documented of the seven: **T-33350 → T-32917 is `[V]` from doc 312, the 1994-09-22 TCT itself** (not a co-occurrence inference). Same mother lot (2-X-6) as Balane.
2. **Chain theory:** T-33350 (339 sqm) derives from **T-32917 (Lot 2-X-6, 85,149 sqm)**, the same Keesey mother lot that produced the Balane branch (T-32917 → … → T-52540 → …2126). Title status='clouded' (live, not cancelled) — the cleanest live adverse title in the set.
3. **Standing note (do not skip):** the ledger flags, and the DB confirms `[V]`, that **Vergara is NOT one of the 20 named transferees** (`registrant_transferee_id` is NULL). She holds Keesey-derived paper without being in the transferee campaign roster. This does **not** weaken the recovery — it means her acquisition route is a distinct `[HV]` question (independent buyer? earlier subdivision? a de la Fuente sale like the others?). Her root conveyance must be pulled to know whether Prong A (void SPA) even applies, or whether the defect is different (e.g., double-titling / fraudulent segregation).
4. **Remedy selection:** **Accion reivindicatoria** (recovery of ownership + cancellation of T-33350 + reinstatement of the Keesey title on Lot 2-X-6) if the estate is out of possession and the defect is a void root deed; **quieting of title** (Arts. 476–481) as the cleaner overlay if the collision is purely a competing paper cloud and the estate remains in possession. Choose after possession (G-1) and root-deed are known. Title issued 1994 → titled adverse holder for 30+ years → NOT forcible entry / unlawful detainer (those are 1-year summary remedies, long prescribed).
5. **Possession evidence:** estate tax decs on the T-32917 / Lot 2-X-6 parcels (the Barangay-1 San Roque schedule, doc 295) + RPT ledger doc 49 + amnesty doc 290. **The specific Keesey ARP that overlaps Vergara's 339 sqm is the missing piece** — pull it in the same G-3 trip.
6. **Ripeness gate:** *Jurisdiction* — small parcel, assessed value far below ₱400,000 → **MTC** exclusive original jurisdiction over the real action (RA 11576, eff. 2021; same reason 26-360 sits in MTC Mercedes). *Prescription* — a title/deed that is **void** is imprescriptible to attack; but if the theory is fraud (voidable), the 4-year clock and Torrens indefeasibility (1 year from issuance) bite — **the root-deed determines which**, so pull it. *Balane-dependency* — **Balane-GATED**: same T-32917 branch; a favorable 26-360 de-clouds the mother lot and strengthens every 2-X-6 recovery.
7. **The one document to pull:** **Assessor certified true copy of the current ARP + PIN for the parcel under T-33350 (Elena Vergara)** — the single highest-legal-ROI diligence lift in this entire dossier. It converts the best-documented chain into a Balane-grade documentary collision.

---

### 3.2 Roscoe Leaño (T-33776, 1,295 sqm) — #2 target

1. **Collision status:** **Theory-only** `[HV]`. Chain **T-33776 → T-32917 is `[V]` from doc 318, a 2025-05-22 CTC** — the freshest adverse-holder paper we hold. No tax-dec pulled.
2. **Chain theory:** T-33776 (1,295 sqm — largest of the T-32917-branch adverse holders) derives from **T-32917 (Lot 2-X-6)**. Same mother lot as Balane and Vergara. Transferee #17.
3. **⚠ Cancelled-title caveat (resolve first):** DB shows **T-33776 status='cancelled'** `[V]`. A 2025 CTC that reads "cancelled" suggests the parcel moved on — the current registered holder may be a successor, not Leaño. **The recovery defendant is whoever holds the live successor title; confirm via RD title trace before naming Leaño.**
4. **Remedy selection:** **Accion reivindicatoria + cancellation** on the T-32917 branch, defendant = current owner-of-record (per the cancellation caveat). Reivindicatoria over ejectment (long-titled, >1 yr).
5. **Possession evidence:** same T-32917 / Lot 2-X-6 estate tax-dec + RPT spine (docs 295, 49, 290); the overlapping Keesey ARP to be pulled alongside Leaño's.
6. **Ripeness gate:** MTC (assessed value < ₱400,000, RA 11576). Prescription = void-vs-voidable turns on the root deed. **Balane-GATED** (T-32917 branch).
7. **The one document to pull:** **RD Camarines Norte current title trace on T-33776** (what cancelled it, who holds the successor) **+ Assessor current ARP/PIN** for the 1,295-sqm parcel. Two-in-one because the cancellation must be resolved before the collision means anything.

---

### 3.3 Cesar S. Ramirez (T-40718) — #3 target, the corroboration bridge

1. **Collision status:** **Theory-only** `[HV]`. Chain **T-40718 → T-4497 (root)** is `[I]` inferred_strong (NULL-source edge) — weaker than the Vergara/Leaño T-32917 edges. No tax-dec pulled; area unknown in corpus `[U]`.
2. **Chain theory:** derives from the **T-4497 root estate** (not the T-32917 sub-branch). **The unique asset here is testimonial corroboration:** Gloria Balane's own judicial affidavit names **Cesar Ramirez as another de la Fuente buyer** (doc 1089 T39–T42) — placing his acquisition inside the *same void-SPA mechanism*. That is our first direct bridge that the Balane defect repeats across transferees (the "campaign, not an isolated sale" pattern).
3. **⚠ Cancelled-title caveat:** DB shows **T-40718 status='cancelled'** `[V]` — resolve current owner-of-record before naming Ramirez as defendant.
4. **Remedy selection:** **Accion reivindicatoria + nullity of the de la Fuente deed** IF the root conveyance is a post-1992-SPA de la Fuente sale (which doc 1089 T39–T42 suggests but does not prove). This is the target where **Prong A (void SPA) is most likely to transplant cleanly** — but only once we hold Ramirez's actual root deed.
5. **Possession evidence:** T-4497 root-estate tax decs (doc 295 master list) + doc 49 + doc 290; overlapping ARP to pull.
6. **Ripeness gate:** MTC by assessed value (RA 11576) once area/value known. Prescription: if the deed is a void de la Fuente sale, imprescriptible. **Standalone, NOT Balane-auto-gated** (T-4497 root, not the T-32917 branch) — but a 26-360 win is powerful *persuasive* corroboration (same agent, same void SPA, judicially found).
7. **The one document to pull:** **Ramirez's root conveyance (the deed that put T-40718 in his name) from RD Camarines Norte** — because if it names de la Fuente as attorney-in-fact under the 1992 SPA, Ramirez becomes a near-copy of Balane and the doc 1089 testimony is corroborated documentarily. Plus current ARP/PIN and current title trace (cancelled-title caveat).

---

### 3.4 Jose Pascual Jr. (T-48335 + T-33686)

1. **Collision status:** Theory-only `[HV]`. Two titles in his name off the root; both `[I]` inferred_strong to T-4497. No tax-dec, no area in corpus.
2. **Chain theory:** T-48335 and T-33686 both derive from **T-4497 root**. Two-title footprint suggests a larger or split holding — potentially higher value once measured.
3. **Title status:** both 'clouded' (live) — no cancellation caveat. Cleaner than Ramirez/Leaño/Valledor on that axis.
4. **Remedy:** reivindicatoria + cancellation of both titles; consider a single action covering both parcels. Root deed unknown → Prong-A applicability unconfirmed.
5. **Possession evidence:** T-4497 root tax-dec spine (docs 295/49/290); overlapping ARPs to pull for both parcels.
6. **Ripeness:** MTC likely (RA 11576) pending assessed value. Prescription root-deed-dependent. Standalone (root branch).
7. **The one document to pull:** **Assessor current ARP/PIN for both T-48335 and T-33686 parcels** + the root conveyances. Two-parcel target = two collisions to document.

---

### 3.5 Pedro Valledor (T-51640)

1. **Collision status:** Theory-only `[HV]`. `[I]` inferred_strong to T-4497. No tax-dec, no area.
2. **Chain theory:** derives from **T-4497 root**.
3. **⚠ Cancelled-title caveat:** DB shows **T-51640 status='cancelled'** `[V]` — resolve current owner-of-record first.
4. **Remedy:** reivindicatoria + cancellation, defendant = current owner-of-record. Root deed unknown.
5. **Possession evidence:** root tax-dec spine; overlapping ARP to pull.
6. **Ripeness:** MTC likely (RA 11576). Prescription root-deed-dependent. Standalone.
7. **The one document to pull:** **RD current title trace on T-51640** (cancellation) **+ Assessor current ARP/PIN**.

---

### 3.6 Edgardo Santiago (T-33415 + T-33416)

1. **Collision status:** Theory-only `[HV]`. Two titles; T-33415 → T-4497 is `[I]` inferred_strong; T-33416 has **no parent edge in `title_chain`** `[V]` (edge absent) — so T-33416's Keesey derivation is **not yet established even by inference**. Do not assert T-33416 is Keesey-derived until a chain edge exists.
2. **Chain theory:** T-33415 off T-4497 root (inferred); T-33416 unlinked `[HV]`.
3. **Title status:** both 'clouded' (live) — no cancellation caveat.
4. **Remedy:** reivindicatoria + cancellation of T-33415; **hold T-33416** pending a chain link. Root deed unknown.
5. **Possession evidence:** root tax-dec spine; overlapping ARP to pull for T-33415.
6. **Ripeness:** MTC likely (RA 11576). Standalone. **Extra diligence gate:** establish T-33416's derivation before including it — a mis-joined parcel is a defense gift.
7. **The one document to pull:** **RD chain trace establishing whether T-33416 derives from a Keesey title**, plus current ARP/PIN for T-33415. Lowest-confidence chain of the set → most upstream diligence needed.

---

### 3.7 Erlinda Tychingco (T-34243)

1. **Collision status:** Theory-only `[HV]`. `[I]` inferred_strong to T-4497. No tax-dec, no area.
2. **Chain theory:** derives from **T-4497 root**.
3. **Title status:** 'clouded' (live) — no cancellation caveat.
4. **Remedy:** reivindicatoria + cancellation. Root deed unknown.
5. **Possession evidence:** root tax-dec spine; overlapping ARP to pull.
6. **Ripeness:** MTC likely (RA 11576). Standalone.
7. **The one document to pull:** **Assessor current ARP/PIN for the T-34243 parcel** + root conveyance.

---

## 4. Ranked recovery-target list (value × evidence-readiness × ripeness)

| Rank | Target | Why ranked here | Evidence-readiness | Balane-gated? |
|---|---|---|---|---|
| **1** | **Elena Vergara (T-33350)** | Best-documented chain (`[V]` doc 312, live 'clouded' title, T-32917 branch); rides the Balane de-clouding | Highest — chain verified, only the tax-dec pull remains | **Yes** |
| **2** | **Roscoe Leaño (T-33776)** | Largest T-32917-branch area (1,295 sqm), fresh 2025 CTC `[V]` doc 318 | High chain, but cancelled-title caveat to clear | **Yes** |
| **3** | **Cesar S. Ramirez (T-40718)** | Testimonial bridge (doc 1089 T39–T42) = most likely clean Prong-A transplant; proves the campaign | Medium — inferred chain + cancelled-title caveat; root deed is the lever | No (persuasive only) |
| 4 | **Jose Pascual Jr. (T-48335 + T-33686)** | Two-parcel footprint = larger potential value; both live 'clouded' | Medium — inferred chain, two collisions to document | No |
| 5 | **Erlinda Tychingco (T-34243)** | Live 'clouded' title, clean on cancellation axis | Low-medium — inferred chain, no area/value yet | No |
| 6 | **Pedro Valledor (T-51640)** | Cancelled-title caveat drags ripeness; must find current holder | Low-medium | No |
| 7 | **Edgardo Santiago (T-33415 + T-33416)** | Lowest chain confidence — T-33416 has NO chain edge; risk of mis-joinder | Lowest — one parcel unlinked | No |

**The next Balane after Balane = Elena Vergara** — closest structural + documentary analog on the same mother lot, one Assessor pull from a Balane-grade collision.

*(Ranking honesty: values are relative, not absolute — five of seven have no area/value in corpus [U], so "value at stake" leans on the two measured parcels [Vergara 339, Leaño 1,295] and the T-32917 branch premium. G-2/G-3 closure will re-order 4–7.)*

---

## 5. The GOVT-occupation lever — a separate theory (three Barangay-5 parcels)

**Parcels** `[V]` (ledger §2b, actual-use "GOVT"): PIN 025-07-005-01-**007** (8,951 sqm, MV ₱8.68M, doc 151); …-**008** (973 sqm, MV ₱0.94M, doc 152); …-**025** (800 sqm, MV ₱0.78M, doc 150). Combined MV ≈ **₱10.4M** `[V]`.

- **Why a different lever:** if a public body / road occupies Keesey land, the remedy is **NOT ejectment** (you cannot ordinarily eject the State from a public use). The doctrine is **inverse condemnation / expropriation-with-just-compensation**: where government takes/occupies private land without expropriation, the owner may compel payment of just compensation (or recover back-rentals for the occupation period). Just compensation accrues from the time of taking; the owner's action to recover it does **not** prescribe in the way an ejectment does (*eminent-domain / inverse-condemnation line* — verify current controlling GR before counsel relies on it).
- **The gating step:** **identify the occupying agency.** "GOVT" in the actual-use field `[V]` does not name the occupant. Candidates: the Municipality of Mercedes (road/plaza/public building), DPWH (national road), a national agency, or a barangay facility. **Cross-hook to the Mercedes Ombudsman/expenditure matter** (memory `project-mercedes-ombudsman-expenditure`): the ₱2.88M Jimmy P. Lo expenditure on unacquired heirs' land + Resolution 76-96 (the LGU's 1996 admission it built on land it never acquired) may name or overlap these very parcels — **check whether the three Barangay-5 GOVT PINs are the LGU-occupied land in that matter before building a fresh just-compensation theory.** If they overlap, this lever and the Ombudsman lever are the same land from two angles: the expenditure/graft angle (against officers) and the just-compensation angle (against the LGU as a body).
- **Sequencing / blowback flag:** the just-compensation claim (money owed to the estate, civil) and the Ombudsman graft angle (officers spent public funds on land they never bought) point the same direction and do not conflict — but **run the records identification first**; do not pick a forum until the agency and the overlap with the Ombudsman matter are pinned. A premature just-compensation demand that mis-names the agency wastes the lever.
- **The one document to pull:** the **three Assessor FAAS/tax-dec originals (docs 150/151/152) plus a barangay/LGU certification of actual occupant** for PINs …-007/…-008/…-025 — to name the agency and date the taking.

---

## 6. G-3 records-request worklist (WORKLIST ONLY — operator/counsel executes; this desk does not send)

The exact certified copies to request, ordered by ROI. Each converts a theory row to documentary ammunition. **Nothing here is sent by this desk.**

| # | From | Request | Serves | Priority |
|---|---|---|---|---|
| 1 | **Municipal Assessor, Mercedes** | Certified true copy — **current ARP + PIN for T-33350 (Elena Vergara)** | Makes the #1 target's collision documentary | **Highest** |
| 2 | **RD Camarines Norte + Assessor** | **T-33776 (Leaño)** current title trace (what cancelled it / current owner-of-record) **+ current ARP/PIN** | Clears the cancelled-title caveat + collision for #2 | High |
| 3 | **RD Camarines Norte** | **Root conveyance for T-40718 (Ramirez)** — the deed that put it in his name (does it name de la Fuente under the 1992 SPA?) **+ current title trace + ARP/PIN** | Tests the Prong-A transplant; corroborates doc 1089 T39–T42 | High |
| 4 | **Assessor + RD** | **T-48335 and T-33686 (Pascual)** — current ARP/PIN for both + root deeds | Two-parcel collision | Medium |
| 5 | **Assessor + RD** | **T-34243 (Tychingco)** current ARP/PIN + root deed | Collision for #5 | Medium |
| 6 | **RD + Assessor** | **T-51640 (Valledor)** current title trace (cancellation) + ARP/PIN | Current-holder + collision | Medium |
| 7 | **RD Camarines Norte** | **T-33415 chain trace + establish whether T-33416 derives from a Keesey title** + ARP/PIN for T-33415 | Fixes the lowest-confidence chain; avoids mis-joinder | Medium-low |
| 8 | **Assessor + LGU/Barangay 5** | FAAS originals docs 150/151/152 (PINs …005-01-007/008/025) **+ certification of actual government occupant** | Names the agency for the GOVT-occupation lever; cross-check vs Ombudsman matter | Parallel track |
| — | **All of the above** | For every target, the **matching Keesey ARP/PIN** that overlaps the adverse parcel (the "other half" of each collision, as doc 238 is to Balane's doc 411) | The overlap is what makes it a *dueling* declaration | Bundled with each request |

*Cost note: Assessor CTCs are nominal per parcel; a single counter visit to the Mercedes Assessor + RD Camarines Norte (Daet) can execute rows 1–8. Highest legal ROI of the entire recovery program (ledger gap G-3).*

---

## 7. Balane-gating map — what a favorable 26-360 unlocks vs what stands alone

**Auto-de-clouded by a favorable 26-360 judgment (T-32917 / Lot 2-X-6 branch):**
- **Elena Vergara (T-33350)** and **Roscoe Leaño (T-33776)** — same mother lot (T-32917, Lot 2-X-6). A ruling that the de la Fuente sales off this lot are void, and that the Keesey title reinstates, de-clouds the *branch* and hands these two a near-dispositive precedent on the identical chain and agent. **These wait for 26-360; do not file ahead of it.**
- Also on the branch but not adverse-held (clean Keesey parcels the ledger already tracks): T-38838, T-51641, T-147652, and the reinstatement of T-52540 itself — these become sellable/leasable once de-clouded (ledger lever (b)).

**Standalone — NOT auto-unlocked (T-4497 root branch):**
- **Ramirez (T-40718), Pascual (T-48335/T-33686), Valledor (T-51640), Santiago (T-33415), Tychingco (T-34243)** derive from the **T-4497 root**, not the T-32917 sub-branch. A 26-360 win is **strong persuasive corroboration** (same agent, same void 1992 SPA, judicially declared void) — especially for Ramirez (named in doc 1089 as a fellow de la Fuente buyer) — **but each still needs its own void-instrument proof**; the 26-360 judgment does not cancel their titles by operation.

**Sequencing recommendation (blowback-aware):**
1. **Hold the two Balane-gated targets (Vergara, Leaño) behind the 26-360 ruling.** Filing them before the SJ/Aug-12 outcome risks an adverse interlocutory finding on the shared T-32917 chain that the defense could import back into 26-360. Do the G-3 diligence now; file after a favorable ruling.
2. **The five T-4497-root targets can be worked up in parallel** (diligence, not filing) — but the highest-value *safe* move is to pull **Ramirez's root deed now**, because if it is a de la Fuente 1992-SPA sale, it (a) corroborates the Balane theory *inside* 26-360 as pattern evidence of a campaign, and (b) does so without creating a new forum that could generate adverse rulings. **Ramirez's deed is the one piece that feeds 26-360 rather than risking it.**
3. **GOVT-occupation lever runs on its own track** — gated only on agency identification and the Ombudsman-matter cross-check, independent of 26-360.

---

## 8. Honest ledger of what is verified vs to-obtain

**Verified `[V]`:** the eight titles exist and are in the corpus; Balane's tax-dec collision (docs 238/411); the chains T-33350→T-32917 (doc 312) and T-33776→T-32917 (doc 318); the three cancelled adverse-title statuses (T-33776/T-40718/T-51640); zero tax-dec links for all seven (live query); the three GOVT-use Barangay-5 parcels (docs 150/151/152); the estate possession spine (docs 49, 290, 295, 238); Vergara's non-transferee standing.

**To-obtain (the gaps that block filing):**
- **Every non-Balane tax-dec collision** (G-3) — 7 of 8 undocumented.
- **Every non-Balane root conveyance** — we cannot yet assert *which* defect (void SPA vs fraud vs double-titling) broke each chain, so Prong-A applicability is unconfirmed for all seven.
- **Current owner-of-record for the three cancelled adverse titles** — defendant identity is unresolved for Leaño/Ramirez/Valledor.
- **Area/assessed value for five of seven** — jurisdiction (MTC vs RTC) and value-at-stake ranking are provisional until measured (all currently read < ₱400,000 basis → MTC, but unconfirmed for the five with NULL area).
- **T-33416's Keesey derivation** — no chain edge; do not join it yet.
- **Occupying agency for the three GOVT parcels** — and whether they overlap the Mercedes Ombudsman/expenditure land.
- **Physical occupant of every adverse parcel** (G-1) — NULL `current_possession` for all seven; a defendant-in-possession is required for reivindicatoria/publiciana.

**The through-line:** the recovery program is real and structurally sound — the estate's possession spine is documented and the chains run to Keesey mother titles — but **only Balane is filing-ready today.** The other seven are one Assessor trip (G-3) and one RD root-deed pull away from the same posture. Vergara is first in line.

---

*Internal work product for MWK-001, Track 4. Grounded in corpus + the valued ledger + the Balane spine. Nothing filed, sent, or exposed. Items marked `[I]`/`[U]`/`[HV]` are not court-grade — upgrade before any use. This desk arms counsel; it does not act outward.*
