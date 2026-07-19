# T-4497 Monetization Playbook — MWK-001 (Mary Worrick Keesey Estate)

**Track 3 of the four-lever profit engine — DISPOSITION / MONETIZATION.**
**Status:** INTERNAL work product. Nothing here is filed, sent, listed, or exposed. The outward endpoint (any buyer/broker/lessee outreach or listing) is LOCKED pending the operator's explicit go. Proposed SQL in §7 is draft-only — not executed.
**Prepared:** 2026-07-19 · Source of record: `T4497_LANDBANK_SQUATTER_LEDGER.md` (valuations, provenance) + live `property_assets` (title_status / possession / stage).
**Provenance legend (inherited, never upgraded):** `[V]` verified from a doc's own fields · `[I]` inferred / schedule-derived · `[U]` unknown.

---

## 0. The decision, up front

**Total ready-now realizable floor: ₱147,440 verified — plus ~₱7 M indicative.**
Read that honestly: exactly **one** parcel (T-52537) has a clean title AND a verified per-PIN tax-declaration value in the corpus. The rest of the "clean" set is clean-in-title but **un-valued** (T-49062, T-079-2021002127) or **valued only by area × schedule rate** (T-47655 ≈ ₱7 M `[I]`). So the estate's first real cash is small and deliberate.

**First parcel to transact: T-52537** (152 sqm, PIN 025-07-003-01-057). Not because it's valuable — it isn't — but because it is the only asset where clean title, a verified value, and a benign boundary (adjoining owner is co-heir Geraldine Hoppe, i.e. no adverse occupant) all line up. It is the **pilot that proves the conveyance pipeline end-to-end at trivial risk.**

**First income (lease) asset: PIN 025-07-001-01-006A** — 10,000 sqm INDUSTRIAL, ₱11.0 M assessor MV `[V]`. Highest-value single parcel, and the only one whose *use* (industrial) throws off rent without a sale. But it is **two gaps short of actionable** (governing title not nailed, occupant unknown), so it is first-income *by design intent*, not first-income *by readiness*.

**First material sale: T-48336** — 14,817 sqm, ~₱14 M indicative `[I]`. The largest developable clean parcel by the ledger — **but the live DB marks it `title_status='clouded'`, not clean** (see §1 discrepancy). Resolve that flag before treating it as the flagship sale.

**The single biggest thing standing between the estate and its first peso:** not a buyer, not a price — it is **estate authority to convey.** The land is held by "Heirs of MWK namely Hoppe, Zschoche, Keesey" (co-ownership), and MWK sits inside a guardianship matter. Even the clean pilot cannot pass registrable title until the authority to sign a deed is settled (all co-heirs' consent and/or guardianship-court approval; Patricia's broad apostilled SPA covers *records/RPT/outward filings* on the whole T-4497 estate but is **not** established here as authority to *alienate* a co-owned parcel). That question — flagged in §6 — gates the pilot itself.

---

## 1. Live-DB reconciliation (must read before pricing anything)

The valued set is grounded in the ledger. But `property_assets` (queried live 2026-07-19) diverges on two points that change readiness scoring — surfacing both rather than papering over them:

| Point | Ledger says | Live `property_assets` says | Playbook treatment |
|---|---|---|---|
| **T-48336 title status** | "active/clean … largest clean active parcel" (§2a, §5) | `PA-T-48336` → **`title_status='clouded'`** | Treat as **Near/Blocked, not Ready.** Do NOT price it as a clean sale until the clouded flag is reconciled (F-2 below). This is the difference between a ₱14 M "ready" asset and a gated one. |
| **Possession** | occupant UNKNOWN for ~28 parcels (gap G-1) | **`possession='contested'` on ALL 63 rows**, including the clean pilots | `contested` here is a table default, not a verified finding — but it means possession is *unproven*, which is itself the monetization blocker. No parcel is "occupant-cleared" on the record. |
| Clean set present | T-52537, T-47655, T-49062, T-079-2021002127 clean | Confirmed: `PA-T-52537`, `PA-T-47655`, `PA-T-49062`, `PA-T-079-2021002127` all `title_status='clean'` | The four-parcel clean core holds. |
| Industrial …-006A | ₱11.0 M industrial, governing title not nailed | **No `property_assets` row exists** (no asset_code) | Confirmed blocker: it cannot be staged until a governing title is linked and a `PA-` row created. |

**est_value is NULL on every clean row.** The valuations below come from the ledger's tax-dec reads, not from `property_assets` — W-1 (§7) proposes backfilling them.

---

## 2. Per-parcel playbook cards

### CARD A — T-52537 · THE CLEAN PILOT (transact first)

1. **Snapshot.** PIN 025-07-003-01-057 · TCT **T-52537** (clean, active — `PA-T-52537` confirms) · **152 sqm** · Residential · Barangay 3 (Mercedes town, Lot 2-X-4-E) · tax-dec **MV ₱147,440 / AV ₱11,800** `[V]` doc 232 + 295 · parent T-32916. Occupant: not adverse — **adjoining owner is co-heir G. Hoppe (self-bounded)** `[V]`; possession `contested` on the record but no named encroacher. ⚠ One open cross-signal: doc 30's Barangay-3 roll lists this ARP (003-00169) under "GAULIT, DELFIN & LUISA" — resolve before conveyance (ledger §2b).
2. **Disposition mode.** **Outright sale.** 152 sqm is too small to subdivide, wrong shape/scale for lease. A clean cash sale to a single buyer (likely a co-heir or the adjoining owner) is the whole point — it exercises deed → BIR (CGT/DST) → RD transfer → new title once, cheaply, to prove the pipeline.
3. **Price band.** Floor = assessor MV **₱147,440** `[V]`. Realistic band = floor × 2.0–3.5 → **≈ ₱295 k–₱515 k**, on the standard PH assumption that assessor schedule values run ~⅓–½ of market (stated assumption, NOT a comp — needs gap G-2 closed with a local BPO). Town-center residential in Mercedes poblacion sits at the higher multiple.
4. **Clearance gate (ordered).** (i) **Estate authority to convey** — the real gate; co-heir consents and/or guardianship-court approval to sign the deed. (ii) Resolve the **Gaulit roll cross-signal** on ARP 003-00169. (iii) Settle any RPT arrears on this PIN (fold into the ₱775,202 amnesty, doc 290) so a tax-clearance issues. (iv) Deed → CGT/DST → RD. Title itself is already clean — no litigation gate.
5. **Readiness: NEAR (1 true gate — estate authority).** Everything else is administrative. This is the closest thing to ready in the portfolio.

---

### CARD B — T-48336 · FIRST MATERIAL SALE (gate the flag first)

1. **Snapshot.** TCT **T-48336** · **14,817 sqm** · parent T-47656 · San Roque branch · linked ARP 001-00249 / …-00248 `[I]`. **Title status: ledger says clean; live `PA-T-48336` says `clouded`** — unreconciled (see §1). No verified per-PIN MV in corpus; **indicative ≈ ₱14 M** at the Barangay-1 schedule (~₱970/sqm) `[I]`. Occupant UNKNOWN `[U]` (gap G-1). Possession `contested`.
2. **Disposition mode.** **Subdivide-then-sell.** At ~1.5 ha this is the largest clean-lineage developable block; a single buyer at ₱14 M is a thin market in Mercedes, but subdivided residential lots sell faster and at a higher blended ₱/sqm. Secondary option: whole-block sale to a developer if one surfaces (held — no outreach).
3. **Price band.** Floor (indicative) **₱14 M** `[I]` — this is area × schedule, NOT a verified tax-dec MV; do not quote it as fact. Realistic band = floor × 2.0–3.0 subdivided → **≈ ₱28 M–₱42 M** gross, less subdivision/survey/transfer cost. **Hard-blocked on G-2** (real comps) before any number leaves the room.
4. **Clearance gate (ordered).** (i) **Reconcile the clean-vs-clouded flag** (F-2) — decides whether this is a sale or a litigation-gated asset. (ii) Occupant canvass (G-1). (iii) Estate authority. (iv) Subdivision plan + RD approval. (v) RPT clearance.
5. **Readiness: NEAR→BLOCKED (blocking item = title-status reconciliation).** If clouded holds, it drops behind the Balane branch gate.

---

### CARD C — T-47655 · SECOND CLEAN SALE

1. **Snapshot.** TCT **T-47655** (clean, active — `PA-T-47655` confirms) · **7,186 sqm** · San Roque, ex-**T-32917** · linked ARP 001-00248 `[I]`. No verified per-PIN MV; **indicative ≈ ₱7 M** `[I]`. Occupant UNKNOWN `[U]`. Possession `contested`.
2. **Disposition mode.** **Subdivide-then-sell** (0.72 ha residential), or whole-parcel sale. Same logic as T-48336 at half the scale.
3. **Price band.** Floor (indicative) **₱7 M** `[I]`; band × 2.0–3.0 → **≈ ₱14 M–₱21 M** subdivided. G-2-blocked for a real number.
4. **Clearance gate.** (i) Occupant canvass (G-1) — note it derives from T-32917, the Balane mother title; confirm this specific parcel is *not* inside a contested sub-lot. (ii) Estate authority. (iii) Subdivision + RD. (iv) RPT clearance. Title clean on the record.
5. **Readiness: NEAR (blocking item = occupant/possession proof).**

---

### CARD D — T-49062 · CLEAN, PATENT-DERIVED, UN-VALUED

1. **Snapshot.** TCT **T-49062** (clean, active — `PA-T-49062` confirms) · **area not captured** `[U]` · parent **P-2218 (a land patent)** `[V]` doc 40 chain · linked ARP 001-00248 `[I]`. **No area, no value in corpus.** Possession `contested`.
2. **Disposition mode.** Undetermined until area is known — a patent-derived clean title is attractive (clean lineage) but un-scoped. **Note the patent origin:** patent-derived land can carry a Commonwealth Act 141 **5-year non-alienation / repurchase restriction** from the patent date — confirm the patent is old enough that the restriction has lapsed before any sale. Likely lapsed (chain is decades old) but verify.
3. **Price band.** **Cannot band — area and MV both unknown.** Close G-4 (pull the tax dec) first.
4. **Clearance gate.** (i) Pull area + tax-dec value. (ii) Confirm CA-141 restriction lapsed. (iii) Estate authority. (iv) RPT clearance.
5. **Readiness: NEAR-but-unscoped (blocking item = missing area/value + patent-restriction check).**

---

### CARD E — T-079-2021002127 · CLEAN SIBLING OF THE BALANE LOT

1. **Snapshot.** TCT **079-2021002127** — the **clean sibling of Balane's contested …002126**; `PA-T-079-2021002127` = `title_status='clean'`. Parent T-52540. Linked ARP GR-2023-II-07-001-00256 `[I]`. **Area and MV not captured** `[U]`. Possession `contested`.
2. **Disposition mode.** **HOLD — do not treat as freely sellable despite the clean flag.** It sits on the exact T-52540 branch that the Balane suit (MWK-CV26360) is litigating. A "clean" registry status on a title one derivation away from the contested …126 is fragile: an adverse ruling or lis pendens could reach it. Sale-readiness here is *legally* gated even though the flag reads clean.
3. **Price band.** Un-valued — cannot band.
4. **Clearance gate.** (i) **Balane MWK-CV26360 outcome** — the controlling gate. (ii) Confirm no lis pendens / notice touches this title. (iii) Area + value. (iv) Estate authority.
5. **Readiness: BLOCKED (blocking item = Balane litigation on the sibling branch).**

---

### CARD F — PIN 025-07-001-01-006A · FIRST INCOME (INDUSTRIAL LEASE)

1. **Snapshot.** PIN 025-07-001-01-006A · **10,000 sqm** · **INDUSTRIAL use** `[V]` · Barangay 1 (San Roque / V. Basit Extn) · tax-dec **MV ₱11,000,000 / AV ₱1,650,000** `[V]` docs 30 + 295. **Governing title NOT nailed** `[U]` — and **no `property_assets` row exists** for it. Occupant/possession **UNKNOWN** `[U]` — a monetization blocker, not a footnote.
2. **Disposition mode.** **Ground lease for income** — this is the estate's one genuine cash-flow asset. Industrial-zoned 1-ha near town is a warehouse/yard/laydown candidate; a ground lease keeps the asset on the estate books, throws off monthly rent, and sidesteps the estate-authority-to-*alienate* problem (leasing is a lesser act than selling). Sale is the fallback if title proves un-registrable.
3. **Price band (rent, not sale).** Indicative ground rent ≈ **1.0–1.5% of MV / month → ₱110 k–₱165 k/mo** as a PH commercial-ground-lease rule of thumb (stated assumption, needs a local rental comp — G-2 for lease rates). Sale floor if ever sold = ₱11.0 M `[V]` × market uplift.
4. **Clearance gate (ordered).** (i) **Nail the governing Keesey title** for this PIN — without a title there is nothing to lease. (ii) **Identify the occupant** — an unknown occupant on a 1-ha industrial parcel may already be using it (potential back-rent claim) or may be an encroacher (clear first). (iii) Create the `PA-006A` asset row. (iv) Estate authority to lease. (v) RPT clearance.
5. **Readiness: BLOCKED (blocking item = no governing title identified).** Highest value, furthest from actionable.

---

### CARD G — T-30683 · CARP RECEIVABLE (parallel non-sale track)

1. **Snapshot.** TCT **T-30683** (Manguisoc) · **~804,148 sqm / ~80.4 ha** · 4 heirs undivided · **Landbank CARP compensation claim 05-E0228-99-1544** `[V]` doc 374/notes · `PA-T-30683` = `clouded`. ⚠ **[HUMAN VERIFY]** — T-4497 derivative relationship NOT verified; Manguisoc is a distinct location. Treat as its own agrarian matter *within* MWK.
2. **Disposition mode.** **NOT a sale — a compensation-collection lever.** The land was taken under CARP; the money is a Landbank just-compensation receivable. Monetization = pursuing/valuing the claim, not conveying the parcel.
3. **Price band.** Landbank valuation of the claim is unknown in-corpus — do not fabricate an ₱/ha. The just-compensation figure is what the claim is worth; establishing it is the work.
4. **Clearance gate.** (i) Verify the CARP claim is live and un-paid. (ii) Confirm the estate's standing (4-heir undivided interest) and authority to collect. (iii) Establish the Landbank valuation / any pending DARAB or just-compensation case.
5. **Readiness: SEPARATE TRACK (agrarian receivable — runs parallel to the sale pipeline; blocking item = claim-status verification).**

---

## 3. Sequenced monetization plan

**First 90 days — prove the pipeline (low value, low risk):**
1. **T-52537 (Card A)** — run the clean pilot conveyance end-to-end. Value is trivial (₱147 k floor) by design; the deliverable is a *working, repeatable* deed→BIR→RD→new-title process and a cleared estate-authority path. Everything downstream reuses it.
2. In parallel (records/field work, no outward exposure): close **G-1** occupant canvass on the top Barangay-1 parcels and **G-2** BPO on the clean set, and pull area/value for **T-49062** (G-4).

**Next — first material cash + first income:**
3. **T-48336 (Card B)** — *after* reconciling the clouded flag (F-2); if it clears, subdivide-then-sell the 1.5 ha. First real money.
4. **T-47655 (Card C)** — second clean sale, same subdivision playbook.
5. **PIN …-006A (Card F)** — nail governing title, identify occupant, stand up a ground lease. First recurring income.

**Litigation-gated (hold until Balane ruling):**
6. **T-079-2021002127 (Card E)** and the entire T-32917 / T-52540 clouded branch — a favorable MWK-CV26360 judgment de-clouds this wholesale (see §4).

**Parallel, independent:**
7. **T-30683 CARP receivable (Card G)** — agrarian collection track; does not wait on any of the above.

---

## 4. Estate-level cash view

- **Ready-now realizable floor (verified numbers only): ₱147,440** — T-52537 alone is the only clean parcel with a verified per-PIN tax-dec MV. This is the honest floor.
- **Clean-set indicative floor (add area-derived `[I]`): ≈ ₱21 M** if T-48336 (₱14 M) *and* T-47655 (₱7 M) hold — but T-48336's clouded flag must clear first, so treat this as *potential*, not banked. Realistic sale-value band on that clean set (× 2–3, G-2-pending) ≈ **₱42 M–₱63 M**.
- **What a favorable Balane ruling unlocks:** the T-32917 / T-52540 branch de-clouds **wholesale** — T-38838 (32,448 sqm), T-51641, T-147652, the …-047 parcel, T-079-2021002127, and the rest of Lot 2-X-6. That single event is the **highest-leverage monetization catalyst in the portfolio**, converting a large clouded tranche of the ledger's ₱90.9 M assessed land bank into sellable inventory.
- **Parallel non-sale value:** the **T-30683 ~80 ha CARP receivable** (Landbank claim 05-E0228-99-1544) — a compensation collection independent of every sale gate.

---

## 5. The authority + tax questions (flag, do not resolve)

**Estate authority — the gate on the first peso:**
- The parcels are held in **co-ownership** ("Heirs of MWK namely Hoppe, Zschoche, Keesey"), and MWK sits within a **guardianship matter**. A *sale* of a co-owned estate parcel needs either **all co-heirs' consent** or, to the extent MWK herself retains interest, **guardianship-court approval** to alienate.
- **Patricia's broad apostilled SPA** covers the whole T-4497 estate for **records / Assessor / RPT / outward filings** — it is the right instrument for the RPT-amnesty and records work, but it is **NOT established here as authority to *alienate*** a co-owned parcel. Do not assume the SPA closes the sale-authority gate.
- **Leasing** (Card F industrial) is a lesser act than selling and may clear on narrower authority — a reason the income asset can potentially move before the sale authority is fully settled.
- **Action:** confirm the exact conveyance authority (co-heir consents vs guardianship order) **before** the T-52537 pilot deed — this is the pilot's true gate.

**RPT-amnesty timing decision (flag):**
- The estate proposed a **₱775,202 amnesty settlement** under RA 7160 (doc 290/293), with a Sec-270 prescription argument.
- **The tension:** to *sell* a parcel you need a **tax clearance**, which means **settling that PIN's arrears** — so the parcels you monetize first must have their RPT paid. Against that, the amnesty/prescription argument suggests *letting prescription run* may extinguish part of the liability on parcels you're **not** selling.
- **Decision to put to the operator:** settle arrears **selectively on the parcels entering the sale/lease pipeline** (T-52537, then T-48336/T-47655/…-006A) to clear title, while preserving the prescription posture on the long-hold and litigation-gated parcels. Do not blanket-settle. Flag — do not resolve.

---

## 6. Open gaps that block dollars (from ledger §6, monetization view)

| Gap | Blocks which card | Cheapest close |
|---|---|---|
| **G-1** occupant unknown (~28 parcels) | B, C, F readiness; every possession claim | field canvass + barangay cert per PIN (prioritize Barangay-1 high-value) |
| **G-2** true market/lease value un-benchmarked | every price band in §2 | 3–5 local comps + one broker BPO (sale) / rental comp (lease) |
| **F-2** T-48336 clean-vs-clouded flag unreconciled | Card B mode + readiness | reconcile `titles.status` vs `property_assets.title_status` vs registry |
| Authority-to-alienate unsettled | Card A pilot itself | confirm co-heir consents / guardianship order scope |
| **G-4** T-49062 / …-006A missing area+value / title | Cards D, F | pull Assessor tax-dec + registry to nail governing title |

---

## 7. Proposed DB writes — DRAFT SQL ONLY (do NOT execute)

> Proposals only. Nothing run. Standing rule: `.bak` before overwrite · idempotent · re-read at write time · **upsert-style, never delete+reinsert**. Apply only after human verification of flagged rows. `est_value` is presently NULL on every MWK row; values below come from verified tax decs (assessor MV = a **floor**, not market — G-2).

```sql
-- Preview current state before any write (re-read at write time):
SELECT asset_code, title_status, possession, area_sqm, est_value, stage
FROM property_assets
WHERE case_file='MWK-001'
  AND asset_code IN ('PA-T-52537','PA-T-47655','PA-T-49062','PA-T-079-2021002127','PA-T-48336');

-- ============================================================================
-- W-3  Stage + monetization_plan on the CLEAN PILOT (T-52537). Upsert-style.
--      Sets it to the head of the pipeline with the verified MV floor.
-- ============================================================================
-- UPDATE property_assets
--    SET stage = 'pilot_ready',
--        area_sqm = COALESCE(area_sqm, 152),
--        est_value = COALESCE(est_value, 147440),   -- assessor MV floor (docs 232/295); true sale value higher (G-2)
--        monetization_plan = COALESCE(monetization_plan,'')
--          || ' | 2026-07-19 Track-3: CLEAN PILOT — outright sale; band ~295k-515k (floor x2-3.5, G-2 pending);'
--          || ' gate = estate authority to convey + Gaulit roll cross-signal on ARP 003-00169; readiness NEAR'
--  WHERE asset_code='PA-T-52537' AND case_file='MWK-001';

-- ============================================================================
-- W-4  Stage the second clean sale (T-47655) — subdivide-then-sell.
-- ============================================================================
-- UPDATE property_assets
--    SET stage = 'clean_queue',
--        monetization_plan = COALESCE(monetization_plan,'')
--          || ' | 2026-07-19 Track-3: subdivide-then-sell 7,186 sqm; indicative floor ~7M [I] area x schedule;'
--          || ' band ~14M-21M subdivided (G-2 pending); gate = occupant proof (G-1) + estate authority; readiness NEAR'
--  WHERE asset_code='PA-T-47655' AND case_file='MWK-001';

-- ============================================================================
-- W-5  Flag T-48336 for title-status reconciliation (do NOT stage as clean sale
--      while property_assets.title_status='clouded' contradicts the ledger).
-- ============================================================================
-- UPDATE property_assets
--    SET monetization_plan = COALESCE(monetization_plan,'')
--          || ' | 2026-07-19 Track-3 FLAG F-2: ledger calls this clean/active but title_status=clouded here —'
--          || ' RECONCILE vs titles.status + registry before treating as material sale; indicative ~14M [I]; readiness NEAR->BLOCKED'
--  WHERE asset_code='PA-T-48336' AND case_file='MWK-001';

-- ============================================================================
-- W-6  Hold-flag the Balane-branch clean sibling (do not sell despite clean flag).
-- ============================================================================
-- UPDATE property_assets
--    SET stage = 'litigation_gated',
--        monetization_plan = COALESCE(monetization_plan,'')
--          || ' | 2026-07-19 Track-3: HOLD — clean sibling of Balane 079-2021002126; sale gated on MWK-CV26360;'
--          || ' verify no lis pendens; readiness BLOCKED'
--  WHERE asset_code='PA-T-079-2021002127' AND case_file='MWK-001';

-- ============================================================================
-- W-7  Industrial lease asset has NO property_assets row. Propose creating it
--      ONLY after a governing Keesey title is verified for PIN 025-07-001-01-006A.
--      (Left as a guarded proposal — do not insert an asset with no governing title.)
-- ============================================================================
-- INSERT INTO property_assets (asset_code, case_file, title_status, possession, area_sqm, est_value, stage, monetization_plan)
-- SELECT 'PA-PIN-025-07-001-01-006A','MWK-001','unknown','unknown',10000,11000000,'blocked',
--        '2026-07-19 Track-3: 10,000 sqm INDUSTRIAL, MV 11.0M [V] docs 30/295; FIRST-INCOME ground-lease candidate;'
--        || ' BLOCKED — governing Keesey title not yet nailed + occupant unknown; rent est ~110k-165k/mo [assumption, G-2]'
-- WHERE NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code='PA-PIN-025-07-001-01-006A');
```

---

## 8. Handoff — what closes the loop to the first peso

1. **Confirm estate authority to convey** (co-heir consents / guardianship order scope) — gates even the pilot.
2. **Run T-52537 pilot** deed→BIR→RD once, cheaply, to prove the pipeline.
3. **Reconcile T-48336's clean-vs-clouded flag** (F-2) — decides the flagship sale.
4. **Close G-1 (occupant) + G-2 (comps)** on the clean set — turns indicative floors into real bands.
5. **Nail the governing title for …-006A** — unlocks the first income asset.
6. Everything on the T-32917/T-52540 branch waits on **Balane MWK-CV26360**; **T-30683 CARP** collection runs in parallel.

*End of playbook. Internal work product — not for filing, listing, sending, or external exposure. Outward endpoint LOCKED pending operator go.*
