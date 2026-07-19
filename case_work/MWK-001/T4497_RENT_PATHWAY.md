# T-4497 Rent Pathway — the fastest route to the estate's first recurring peso (MWK-001)

**Track 3b of the profit engine — RECURRING INCOME (rent), the fast lane that runs *ahead* of the sale gate.**
**Status:** INTERNAL build only. Nothing here is filed, sent, listed, or offered to any occupant, tenant, agency, or third party. The outward step — sending any lease offer, attornment demand, or notice — is **LOCKED pending the operator's explicit go.** All SQL in §6 is draft-only; no DB rows were mutated (`est_income_monthly` reads 0 on all 63 rows live 2026-07-19).
**Prepared:** 2026-07-19 · Sources: `T4497_LANDBANK_SQUATTER_LEDGER.md` (parcels/values/occupancy), `T4497_MONETIZATION_PLAYBOOK.md` (authority-to-convey gate), `T4497_RECOVERY_DOSSIERS.md` (adverse holders), live `property_assets`, and the two consent-lane memories (broad apostilled Patricia SPA; MWK guardianship case-state).
**Provenance legend (inherited, never upgraded):** `[V]` verified from a doc's own fields · `[I]` inferred / schedule-derived · `[U]` unknown · `[HV]` human-verify · `[EST]` an explicitly stated estimate/assumption (never a fabricated comp).

---

## 0. The decision, up front

**Rent is the fastest income the estate can earn — and it clears a gate the sale pipeline cannot.** Selling a co-owned parcel needs *all three* heirs' shares (Patricia + Hoppe + Marcia), and Hoppe is a refusing holdout `[V]` (guardianship memory) — so every sale waits on the 07-27 guardianship reaching her 1/3. **A short lease does not.** A lease of one year or less is an **act of administration** (Civil Code Art. 1878(8), by negative implication — special power is required only to lease "for more than one year"), and administration of co-owned property is decided by the **majority of interest, not unanimity** (Art. 492). Patricia (1/3, via the broad apostilled SPA) + Marcia (1/3, via her POA lane) = **2/3 majority of interest** — which under Art. 492 **binds the whole co-ownership, including a dissenting or absent Hoppe, without her consent and without waiting for the guardianship.** That is why rent is the fast lane.

**Fastest parcel to a signed lease + first peso: T-47655** — 7,186 sqm, San Roque, **clean title confirmed live** (`PA-T-47655.title_status='clean'` `[V]`). It is the only parcel that combines (a) confirmed clean title, (b) enough area for a real ground/yard lease, and (c) no litigation gate. Indicative ground rent **≈ ₱21,000–₱52,000/mo `[EST]`** (0.4–0.6%/mo of an indicative ~₱7 M land value; needs a local rental comp, gap G-2). Its one cheap blocker is a **vacancy/occupant canvass** (G-1) — a day of field/barangay work.

**Highest-income asset (the prize, but two gaps back): PIN 025-07-001-01-006A** — 10,000 sqm **INDUSTRIAL**, assessor MV ₱11.0 M `[V]`. Indicative ground rent **≈ ₱88,000–₱165,000/mo `[EST]`** — but it has **no governing Keesey title nailed** and **no `property_assets` row**, and the occupant is unknown. First-income *by design intent*, not by readiness.

**Total indicative near-term monthly rent-roll FLOOR ≈ ₱160,000/mo, band to ~₱280,000/mo `[EST]`** — the leasable-now/near set (…-006A + industrial …-010A + T-47655 at low-end bands), *once the two industrial parcels' governing titles are nailed and vacancy confirmed.* The **immediately-signable floor** (T-47655 alone, the one clean-and-confirmed parcel) is **≈ ₱21,000–₱52,000/mo `[EST]`**. Everything here is an assessor-MV-derived estimate, not a comp.

**The single blocking item before ANY lease can be offered:** **confirm that Marcia Ellen Keesey's POA authorizes leasing / acts of administration.** Patricia's SPA alone is a *minority* 1/3 — it can lease only Patricia's undivided share, not bind the whole parcel. Patricia SPA **+** Marcia POA = the 2/3 Art. 492 majority that makes a whole-parcel ≤1-year lease valid and binding on all co-owners today, pre-07-27. Until Marcia's POA scope is confirmed to reach leasing, no whole-parcel lease can validly go out. That confirmation is the gate.

---

## 1. The rent-pathway decision tree (per occupied parcel)

Three branches. The estate wins on all three — income on two, a fast recovery remedy on the third. **The doctrine that powers the tree = attornment: offering a lease to a current occupant is simultaneously an income act and a title-defense weapon.**

```
                       ┌─────────────────────────────────────────────┐
                       │  PARCEL  (Keesey-titled / tax-declared)      │
                       └───────────────────────┬─────────────────────┘
                                                │
                  ┌─────────────────────────────┼─────────────────────────────┐
                  │                             │                             │
          (A) VACANT / clean            (B) OCCUPIED — by a         (C) OCCUPIED — by a
              → lease to a NEW              TOLERATED / informal        TITLED ADVERSE holder
              tenant                        occupant                    (Balane, Vergara, Leaño…)
                  │                             │                             │
          ground/yard lease ≤1yr      offer lease (ATTORNMENT)      NOT a lease/detainer target →
          → recurring rent                 │                        accion reivindicatoria / publiciana
                                    ┌───────┴────────┐               (see RECOVERY_DOSSIERS; a titled
                                    │                │                claimant asserting ownership is
                              ACCEPTS           REFUSES               outside unlawful-detainer)
                                    │                │
                         becomes LESSEE →     UNLAWFUL DETAINER
                         (1) pays rent        (Rule 70, MTC summary):
                         (2) acknowledges      (1) eviction + (2) back-
                         estate's title →       rentals as reasonable
                         KILLS acquisitive      compensation. Faster than
                         prescription           accion publiciana.
```

**Branch A — vacant/clean → lease to a new tenant.**
A clean-title, unoccupied parcel is leased on a ≤1-year renewable ground/yard lease. Pure income. Legal basis: Art. 1878(8) (≤1yr = administration) + Art. 492 (2/3 majority authorizes it). No litigation gate. *This is where T-47655 sits.*

**Branch B — tolerated/informal occupant → offer lease (ATTORNMENT).** This is the core doctrine.
- **If accepted:** the occupant becomes a **lessee** and (1) starts paying rent — income — and (2) **acknowledges the estate's title.** A lessee holds *for* the lessor, never *adversely*: possession under a lease is not "in the concept of owner," so it can never ripen into ownership by acquisitive prescription (Arts. 540, 1118–1119; acts by mere tolerance/licence "shall not be available for the purposes of possession," Art. 1119). The tenant is further **estopped from denying the landlord's title** (Rules of Court, Rule 131 §2(b)). **One lease signature converts a creeping prescription risk into a paying, title-acknowledging tenant.**
- **If refused:** the occupant, having been on the land by the estate's tolerance and now refusing to pay or vacate on demand, is **unlawfully withholding possession → UNLAWFUL DETAINER** (Rules of Court, Rule 70), an **MTC summary-procedure** remedy that also awards **reasonable compensation for the use and occupation (back-rentals)** from the demand (or from entry, per the pleaded theory). This is materially **faster than accion publiciana/reivindicatoria** and must be filed **within one year of the last demand.** Filing is authorized by a **single co-owner** — *any one* co-owner may bring the ejectment action for the benefit of all (Art. 487) — so Patricia via the SPA can carry it even without Marcia.
- **Either way the estate wins:** rent, or a fast eviction-with-back-rent.

**Branch C — titled adverse holder → NOT this tree.**
An occupant who holds a Torrens title and asserts *ownership* (Balane and the seven dossier targets) cannot be offered a lease or sued in unlawful detainer — detainer presupposes a possession that began lawfully by contract or tolerance, which an adverse *owner-claimant*'s does not. These are the **reivindicatoria / quieting-of-title** targets in `T4497_RECOVERY_DOSSIERS.md`, Balane-gated where on the T-32917 branch. **Do not attempt attornment on a titled adverse claimant** — an offer to lease could be spun as recognition of *their* possession. Keep the two tracks separate.

**Special case — GOVT-occupied parcels (Barangay 5).** Neither lease-to-new-tenant nor detainer: you cannot ordinarily eject the State from a public use. Lever = **reasonable compensation / back-rental / inverse condemnation** (money, not eviction), and possibly a **lease-in-place** if the agency will formalize. This is a **litigated receivable, not near-term cash** — treated in §2(iv).

---

## 2. Rent roll (target)

Grouped by readiness. Bands are **assessor-MV-derived estimates `[EST]`**, not comps — a stated ground-rent rule of thumb (industrial/commercial land ≈ **0.8–1.5% of assessor MV/mo**; residential/yard land ≈ **0.4–0.6%/mo**; agricultural nominal), consistent with the playbook's Card-F basis. Real bands require gap **G-2** (local rental comps / a broker's opinion). Never quote these outward as fact.

### (i) Clean / use-based — leasable now or near

| Parcel | Area sqm | Use | Assessor MV ₱ | Basis `[EST]` | Indicative rent/mo `[EST]` | Readiness / blocker |
|---|---|---|---|---|---|---|
| **T-47655** | 7,186 | Resid / yard | ~7 M `[I]` (no per-PIN MV in corpus) | 0.4–0.6% | **₱21,000–₱52,000** | **NEAR — clean title `[V]`; blocker = vacancy/occupant canvass (G-1)** |
| **PIN …-006A** | 10,000 | **Industrial** | 11,000,000 `[V]` | 0.8–1.5% | **₱88,000–₱165,000** | GATED — no governing title nailed `[U]`; no `PA-` row; occupant unknown |
| PIN …-010A | 4,651 | **Industrial** | 5,116,100 `[V]` | 0.8–1.5% | ₱41,000–₱77,000 | GATED — governing title/occupant unknown |
| T-48336 | 14,817 | Resid | ~14 M `[I]` | 0.4–0.6% | ₱56,000–₱84,000 | BLOCKED — ledger says clean, `property_assets` says `clouded` (F-2); reconcile first |
| T-52537 | 152 | Resid | 147,440 `[V]` | — | *trivial (~₱1–3k)* | Too small to lease — this is the **sale pilot**, not a rent asset |
| T-49062 | `[U]` | `[U]` | `[U]` | — | *cannot band* | Clean but un-scoped (area/value/patent-restriction unknown) |

*Agricultural (Barangay 19 — coconut/swamp).* PINs …-04-059 (13,181 sqm coconut), …-04-061 (swamp), …-04-062, …-03-001 — combined indicative rent **≈ ₱2,000–₱10,000/mo `[EST]`** (nominal ag ground/fixed rent). **⚠ CAUTION:** leasing agricultural land to a farmer can trigger **agricultural-tenancy security of tenure** (RA 3844 / RA 6657 agrarian-leasehold rules) — a tenant-farmer becomes hard to remove and the parcel can be drawn toward CARP coverage. Do **not** lease ag land as a share/tenant arrangement; if leased at all, a civil (non-agricultural) use lease with counsel review only. Low priority for rent.

### (ii) Occupied-by-unknown — need occupant ID first (tie to gap G-1)

The high-value Barangay-1 residential infill — …-004 (19,399 sqm, MV ₱18.8 M), …-006 (8,565, ₱8.3 M), …-012 (5,212, ₱4.97 M), …-008 (2,790, ₱2.7 M) — plus most of the ~28 parcels whose physical occupant the corpus does not record. **No lease or attornment can be aimed at a parcel until we know who (if anyone) stands on it.** These convert to Branch A (if vacant) or Branch B (if a tolerated occupant surfaces) **only after G-1 closes.** Indicative rent potential is large (these are the biggest residential blocks) but **un-actionable without the occupant canvass.**

### (iii) Occupied-by-adverse-holder — the attornment/detainer boundary

Balane (079-2021002126) and the seven dossier targets (Vergara, Leaño, Ramirez, Pascual, Valledor, Santiago, Tychingco) are **titled owner-claimants → Branch C → NOT rent targets.** Recovery = reivindicatoria/quieting per `T4497_RECOVERY_DOSSIERS.md`. **Do not offer them leases.** (If G-1 ever reveals a *tolerated informal* occupant on a parcel — as opposed to a titled claimant — that occupant *is* a Branch-B attornment target; the distinction is titled-owner-claim vs. mere-tolerance.)

### (iv) The 3 GOVT parcels — back-rental / reasonable compensation (not ejectment, not near-cash)

| PIN | Area sqm | Use | MV ₱ | Lever |
|---|---|---|---|---|
| …-005-01-007 | 8,951 | GOVT | 8,682,470 `[V]` | reasonable compensation / inverse condemnation |
| …-005-01-008 | 973 | GOVT | 943,810 `[V]` | " |
| …-005-01-025 | 800 | GOVT | 776,000 `[V]` | " |

Combined MV **≈ ₱10.4 M `[V]`.** Notional reasonable-compensation-as-rent **≈ ₱50,000/mo `[EST]`** (≈0.5%/mo of MV) — but this is a **litigated receivable**, and the occupying agency is unidentified (`[HV]`). **Cross-hook:** these may be the same land in the Mercedes Ombudsman/expenditure matter (Res. 76-96, the LGU's 1996 admission it built on unacquired heirs' land) — resolve the overlap before choosing a forum. **Not a near-term cash line.**

**Rent-roll roll-up (near-term, `[EST]`):**
- **Signable this quarter (T-47655 alone): ₱21,000–₱52,000/mo.**
- **Near-term achievable once the two industrial titles are nailed + vacancy confirmed (…-006A + …-010A + T-47655): ≈ ₱150,000–₱280,000/mo.**
- **GOVT receivable (litigated, not cash): ≈ ₱50,000/mo notional — excluded from the cash floor.**
- **Big residential blocks (ii): large but occupant-gated — excluded until G-1.**

---

## 3. Authority + who-signs (the gating analysis)

**Co-ownership structure `[V]` (guardianship memory + title caption).** The registered owners are the **three Keesey heirs — Patricia K. Zschoche, Geraldine Keesey Hoppe, Marcia Ellen Keesey — each an undivided ~1/3.** Mary Worrick Keesey is the ancestor; the guardianship petition (Rule 92/93, RTC Daet) seeks authority over **Hoppe's and Marcia's** property interests, *not* MWK's — so MWK's interest is **not** the lease gate. The gate is reaching the *other two heirs'* shares.

**What authority a lease needs, by type:**

| Act | Nature | Consent required | Instrument available NOW | Clears pre-07-27? |
|---|---|---|---|---|
| **Lease ≤ 1 year** (whole parcel) | **Administration** (Art. 1878(8) neg. impl.) | **Majority of interest** (Art. 492) — *not* unanimity | Patricia SPA (1/3) **+ Marcia POA (1/3) = 2/3** → binds all incl. Hoppe | **YES** — if Marcia POA reaches leasing |
| Lease ≤ 1 year of Patricia's share only | Administration of an undivided share | Patricia alone | Broad apostilled SPA `[V]` | YES, but binds only 1/3 — messy for a whole-parcel tenant |
| **Unlawful detainer / ejectment** vs. a tolerated occupant | Recovery of possession | **Any ONE co-owner** may sue for all (Art. 487) | Patricia SPA alone suffices to authorize the filing | YES (filing is counsel-/operator-gated regardless) |
| Lease **> 1 year** | **Act of ownership** (Art. 1878(8) requires special power) | All shares / special authority per share | SPA reaches Patricia's share; Hoppe's needs guardianship | Hoppe's share **waits on 07-27** |
| **Sale / alienation** | Act of ownership | **All three shares** | SPA (Patricia) + Marcia POA (Marcia); **Hoppe = holdout** | **NO — waits on 07-27 guardianship** |

**Does the broad SPA reach leasing?** Yes as to **Patricia's interest** — the broad apostilled Patricia→Jonathan SPA grants **"full authority / acts of dominion over the entire T-4497 estate"** `[V]` (broad-SPA memory), and leasing (administration *and* ownership acts) sits inside "acts of dominion." **What it does NOT do:** bind the *other two heirs'* shares. An SPA speaks only for its grantor's interest. So the SPA makes Patricia's 1/3 lease-able today; it does not, by itself, authorize a lease of the *whole* parcel.

**The mechanism that closes the whole parcel pre-07-27 (the key finding):** Under **Art. 492**, acts of administration and better enjoyment of co-owned property are decided by the **majority of the co-owners' interests**, and that resolution **binds the minority — including a dissenting or absent co-owner.** Patricia (1/3) + Marcia (1/3) = **2/3 = a controlling majority of interest.** A **≤1-year lease is an administration act.** Therefore **Patricia SPA + Marcia POA can validly lease a whole parcel now, binding Hoppe's 1/3 over her objection, with no guardianship and no Hoppe consent** — the exact holdout problem that stalls every *sale*. This is why leasing is the fast lane and selling is not.

**Sequence — what can be leased now vs. what waits on 07-27:**
- **NOW (pre-07-27), if Marcia POA is confirmed to reach leasing:** ≤1-year whole-parcel ground/yard leases on clean, confirmed-vacant parcels (T-47655 first), and attornment offers/detainer filings against tolerated occupants (Patricia SPA suffices for a detainer *filing* under Art. 487).
- **WAITS ON 07-27 (guardianship over Hoppe's share):** any **>1-year lease**, any **sale**, and any lease binding Hoppe's share where Marcia's POA is unavailable or too narrow (then guardianship supplies Hoppe's *and* provides court-blessed authority).
- **If Marcia POA is NOT confirmed:** fall back to leasing **Patricia's undivided share** (SPA), which is legally valid but commercially awkward (a tenant taking 1/3), or wait for guardianship. **This is why the Marcia-POA scope check is the single blocking item.**

**Guardrail — keep the lease inside "administration."** Draft every lease at **≤ 1 year, expressly renewable**, so it never crosses into the >1-year "act of ownership" that would need special authority per share (Art. 1878(8)). Annual renewals keep it in the Art. 492 majority-administration lane, and a tenant on successive ≤1-year leases **still cannot claim adverse possession** (still a lessee). Avoid any single term, or auto-renew clause, that reads as a disguised long lease.

---

## 4. Collection mechanics (the operational rent pipeline)

**4.1 Lease template terms (internal spec — not a form to send).**
- **Term:** ≤ 12 months, expressly renewable by written agreement (stays in administration — §3 guardrail). No multi-year term, no automatic multi-year rollover.
- **Rent:** monthly, in PHP, due on a fixed day; set from the §2 band once G-2 firms it. State it as ground/land rent (lessor delivers land; improvements at lessee's cost and account).
- **RPT pass-through:** lessee pays or reimburses the annual real-property tax on the leased parcel for the term (turns the carrying cost into the tenant's cost — see 4.5). Estate retains the declaration.
- **Escalation:** fixed annual step (e.g., a stated %/yr `[EST]` — set with counsel), applied on renewal.
- **Security deposit + advance:** e.g., 2 months deposit + 1 month advance (standard PH practice; confirm).
- **Use / no-agrarian clause:** permitted use stated; **for any agricultural parcel, an express non-agricultural-use clause** and counsel review to avoid creating an agrarian leasehold (§2(i) caution).
- **Attornment / title-acknowledgment recital:** for a Branch-B (existing-occupant) lease, a clause by which the lessee acknowledges the estate's ownership and that possession is *under* the lease — the clause that locks in the prescription-defeating effect.
- **Signatories:** Jonathan as attorney-in-fact for Patricia (broad SPA) **and** for Marcia (POA) — the 2/3 majority (§3). Recite the Art. 492 majority-administration basis.
- **No outward step without operator go** (locked).

**4.2 Rent-roll ledger (propose two tables — draft SQL in §6).**
- `parcel_leases` — one row per lease: parcel/PIN, lessee, term start/end, monthly rent, deposit, escalation, RPT-pass-through flag, authority-basis note, status (draft/active/renewed/terminated), source SPA/POA refs. Idempotent upsert key on (pin, term_start).
- `rent_ledger` — one row per due period per lease: period, amount due, amount paid, paid date, OR (official receipt) number, arrears carry. Feeds the collection view.

**4.3 Receipting + tax.** Issue a **BIR-registered official receipt** per payment (the estate/attorney-in-fact must be a registered taxpayer for rental income). Flag for counsel/accountant: **rental income is subject to income tax**; a corporate/withholding-agent lessee will **withhold 5% expanded withholding tax** on the rent; **VAT applies if annual gross rent exceeds the VAT threshold** (else percentage tax). These are compliance items to stand up *before* the first receipt, not blockers to the lease itself.

**4.4 Payment channel.** Rent lands in a **single estate/in-trust account** controlled by the attorney-in-fact, with an **internal co-owner accounting**: because the lease binds all three 1/3 shares (Art. 492), each co-owner is entitled to her 1/3 of net rent (Art. 485 — fruits shared in proportion to shares). Hold Hoppe's 1/3 share in trust/accounting even though she did not consent — Art. 492 lets the majority *lease*, but the *fruits* still belong proportionally to all co-owners; keeping a clean per-share rent ledger forecloses a later Hoppe accounting attack.

**4.5 Rent services the carrying cost (the loop that pays for itself).** The estate carries an RPT liability — the 2023 amnesty proposal reduced it to **₱775,202** `[V]` doc 290. Direct the rent pipeline to **clear arrears on the parcels entering the rent/sale pipeline first** (selective settlement, per the playbook §5 amnesty-timing decision), using: (a) the **RPT pass-through** so the tenant carries the *going-forward* tax, and (b) **net rent** to pay down the *back* amnesty balance on that PIN — producing the tax clearance that in turn unlocks a future sale. Rent thus funds the clearance that de-risks the sale. Do **not** blanket-settle all arrears; preserve the prescription posture on long-hold, non-income parcels.

---

## 5. First-90-days sequence

**The single blocking item, before anything:** confirm **Marcia Ellen Keesey's POA authorizes leasing / acts of administration** (§0, §3). This is the gate on every whole-parcel lease. If confirmed, the 2/3 Art. 492 majority is live and leasing can proceed pre-07-27. Owner: operator + ABLAW (read Marcia's POA instrument; it is the Marcia consent-lane referenced in the guardianship memory).

**Days 1–15 — clear the gate + pick the parcel.**
1. **Confirm Marcia POA scope** (the blocking item). In parallel, confirm the **broad Patricia SPA** text reaches leasing (memory says "acts of dominion" — read the operative apostilled instrument, doc #950's executed twin, to be certain).
2. **Vacancy/occupant canvass on T-47655** (G-1) — one field/barangay trip: is it vacant (Branch A), tolerated-occupied (Branch B), or does a titled claimant sit on it (Branch C → drop it, pick the next clean parcel)? Cheapest single step that turns T-47655 from "clean title" into "leasable."

**Days 15–45 — the first lease.**
3. **T-47655 first ground lease.** If vacant → prepare a ≤1-year new-tenant ground lease (internal draft only; outward offer stays LOCKED pending operator go). If a tolerated occupant → prepare the **attornment** version (lease with title-acknowledgment recital). Signed under Patricia SPA + Marcia POA. **First recurring peso: ≈ ₱21,000–₱52,000/mo `[EST]`.**
4. Stand up the collection spine: create `parcel_leases` + `rent_ledger` (§6), the in-trust account, BIR receipting, and the per-share accounting.

**Days 45–90 — scale to the income prize.**
5. **Nail the governing Keesey title for PIN …-006A** (records/registry pull) and create its `PA-` row — this unlocks the **₱88k–₱165k/mo** industrial ground lease, the single biggest rent line. Same for …-010A.
6. **Close G-1 on the top Barangay-1 blocks** (…-004, …-006, …-012) to convert the large occupant-gated residential parcels into Branch-A/B rent targets.
7. **Reconcile T-48336's clean-vs-clouded flag** (F-2) — if it clears, add its ₱56k–₱84k/mo line.

**Why T-47655 is first:** it is the *only* parcel where clean title is already confirmed and no litigation gate applies — every other candidate is one more gap back (…-006A/…-010A need a title nailed; the big blocks need occupant ID; T-48336 needs a flag reconciled; T-52537 is too small to lease). T-47655's lone blocker (vacancy canvass) is the cheapest gap in the portfolio. First peso comes from the parcel with the fewest gates, not the highest value.

---

## 6. Draft SQL only (DO NOT EXECUTE — operator/counsel review)

> Proposals only. Nothing run. Standing rule: `.bak` before overwrite · idempotent · re-read at write time · **upsert-style, never delete+reinsert**. `est_income_monthly` reads **0 on all 63 MWK rows** live 2026-07-19 — these backfills replace that placeholder with a **stated assessor-MV-derived estimate** carrying its basis in the note. Apply only after G-2 firms the bands and the Marcia-POA gate is confirmed.

```sql
-- Re-read current state before any write:
SELECT asset_code, title_status, area_sqm, est_value, est_income_monthly, stage
FROM property_assets
WHERE case_file='MWK-001'
  AND asset_code IN ('PA-T-47655','PA-T-48336','PA-T-49062');

-- ============================================================================
-- R-1  Backfill est_income_monthly on the leasable-now clean parcel (T-47655).
--      Value is a LOW-END [EST] ground-rent floor, not a comp. Note carries basis.
-- ============================================================================
-- UPDATE property_assets
--    SET est_income_monthly = 21000,   -- [EST] 0.4%/mo x ~7M indic land value; band 21k-52k; G-2 pending
--        stage = 'rent_candidate',
--        note = COALESCE(note,'')
--          || ' | 2026-07-19 RENT: clean title; ground/yard lease <=1yr (admin, Art.492 majority);'
--          || ' income floor 21k-52k/mo [EST]; blocker = vacancy canvass (G-1); FASTEST first-peso parcel'
--  WHERE asset_code='PA-T-47655' AND case_file='MWK-001';

-- ============================================================================
-- R-2  Flag the industrial rent prize (no PA row exists for PIN ...-006A).
--      GUARDED insert — create ONLY after a governing Keesey title is verified.
-- ============================================================================
-- INSERT INTO property_assets
--   (asset_code, case_file, title_status, possession, area_sqm, est_value, est_income_monthly, stage, note)
-- SELECT 'PA-PIN-025-07-001-01-006A','MWK-001','unknown','unknown',10000,11000000,88000,'rent_blocked',
--        '2026-07-19 RENT: 10,000sqm INDUSTRIAL, MV 11.0M [V] docs 30/295; ground-lease prize;'
--        || ' income 88k-165k/mo [EST] 0.8-1.5%/mo MV; BLOCKED = no governing title nailed + occupant unknown'
-- WHERE NOT EXISTS (SELECT 1 FROM property_assets WHERE asset_code='PA-PIN-025-07-001-01-006A');
-- (Repeat for PIN ...-010A: 4,651sqm industrial, MV 5,116,100, est_income_monthly 41000 [EST].)

-- ============================================================================
-- R-3  parcel_leases — one row per lease (the rent-roll spine the corpus lacks).
-- ============================================================================
-- CREATE TABLE IF NOT EXISTS parcel_leases (
--   id                 serial PRIMARY KEY,
--   case_file          text NOT NULL DEFAULT 'MWK-001',
--   pin                text,                          -- assessor Property Index No
--   linked_tct         text,                          -- governing Keesey title
--   asset_code         text REFERENCES property_assets(asset_code),
--   lessee_name        text NOT NULL,
--   branch             text,                           -- 'A_new' | 'B_attornment' | 'C_excluded'
--   term_start         date NOT NULL,
--   term_months        int  NOT NULL CHECK (term_months <= 12),  -- <=1yr keeps it in administration
--   renewable          boolean DEFAULT true,
--   monthly_rent       numeric(12,2),
--   escalation_pct     numeric(5,2),
--   deposit_months     numeric(4,1),
--   rpt_passthrough    boolean DEFAULT true,
--   attornment_recital boolean DEFAULT false,          -- title-acknowledgment clause present
--   authority_basis    text,                           -- 'Patricia-SPA + Marcia-POA (Art.492 2/3)' etc.
--   spa_ref            text, poa_ref text,
--   status             text NOT NULL DEFAULT 'draft',  -- draft|active|renewed|terminated
--   provenance_level   text NOT NULL DEFAULT 'verified',
--   source_doc_id      integer REFERENCES documents(id),
--   notes              text,
--   created_at         timestamptz DEFAULT now(),
--   UNIQUE (pin, term_start)
-- );

-- ============================================================================
-- R-4  rent_ledger — one row per due period per lease (collection + arrears).
-- ============================================================================
-- CREATE TABLE IF NOT EXISTS rent_ledger (
--   id             serial PRIMARY KEY,
--   lease_id       integer NOT NULL REFERENCES parcel_leases(id),
--   period_month   date NOT NULL,                      -- first day of the rent month
--   amount_due     numeric(12,2) NOT NULL,
--   amount_paid    numeric(12,2) DEFAULT 0,
--   paid_date      date,
--   or_number      text,                               -- BIR official receipt no.
--   rpt_credit     numeric(12,2) DEFAULT 0,            -- portion applied to this PIN's RPT/amnesty
--   coowner_split_note text,                           -- per-share (Patricia/Marcia/Hoppe-in-trust) accounting
--   created_at     timestamptz DEFAULT now(),
--   UNIQUE (lease_id, period_month)
-- );
-- Optional view: rent_roll_live = active leases x current-month due/paid, per §4.2.
```

---

## 7. Honest ledger — income-ready vs. gated

**Income-ready path today (if the one gate clears):** a ≤1-year ground lease on **T-47655** (clean title `[V]`), authorized by **Patricia SPA + Marcia POA = 2/3 Art. 492 majority** — valid pre-07-27, binding Hoppe's share without her consent. Blocker = a **vacancy canvass** (G-1) and the **Marcia-POA scope confirmation** (the true gate).

**Gated / not-yet:** the industrial rent prize (…-006A/…-010A — governing title not nailed `[U]`); the big Barangay-1 residential blocks (occupant unknown, G-1); T-48336 (clean-vs-clouded flag, F-2); every **sale** (needs Hoppe's share → 07-27 guardianship); the GOVT receivable (agency unidentified, litigated); agricultural parcels (agrarian-tenancy caution).

**Not rent targets at all:** the titled adverse holders (Balane + 7) — reivindicatoria per `T4497_RECOVERY_DOSSIERS.md`, not attornment.

**The through-line:** rent is real and it is the *fastest* income the estate can earn, because Art. 492 lets a 2/3 majority lease over a holdout while a sale cannot. But the first peso is modest and gated on one confirmation — **Marcia's POA scope** — and one field step — **the T-47655 vacancy canvass.** Close those two and the estate can sign its first lease pre-07-27; nail the two industrial titles and the monthly rent roll steps up toward **₱150k–₱280k/mo `[EST]`.**

---

*Internal work product for MWK-001, rent track. Grounded in the ledger + playbook + dossiers + live `property_assets` + the two consent-lane memories. Nothing filed, sent, offered, or exposed. No occupant, tenant, agency, or third party contacted. All `[EST]`/`[I]`/`[U]`/`[HV]` items are not court-grade — upgrade before any use. The outward step (any lease offer / attornment demand / notice) is LOCKED pending the operator's explicit go. Not committed to git.*
