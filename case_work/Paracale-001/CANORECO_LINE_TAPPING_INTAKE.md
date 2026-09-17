# CANORECO Line-Tapping & Unauthorized Poles — Intake & Document Procurement Spine

**Matter:** Paracale-001 (Allan Inocalla) — keep strictly separated from MWK per client-separation invariant.
**Status:** INTAKE — zero documentary support in corpus as of 2026-08-19 (checked: `documents`, `channel_messages`; CANORECO appears only incidentally in docs 1285/651).
**One-sentence position:** If Allan funded the line extension as the customer, PH law lets CANORECO tap additional customers onto those poles — but every peso of revenue from those taps legally accelerates a refund CANORECO owes Allan, and poles planted on his land without a right-of-way agreement are uncompensated occupation; both claims live or die on procuring the payment records and the coop's engineering/as-built records.

---

## 1. How the law actually works (the "did CANORECO need to pay Allan?" answer)

### 1a. Customer-funded line extensions — VERIFIED against primary text

**Magna Carta for Residential Electricity Consumers (ERC, 2004), Article 14** — verbatim key passages
(source: Supreme Court e-library, elibrary.judiciary.gov.ph/thebookshelf/showdocs/11/39112, fetched 2026-08-19):

> "A consumer located within thirty (30) meters from the distribution utilities' existing secondary low
> voltage lines, has the right to an extension of lines or installation of additional facilities, other
> than a service drop, **at the expense of the utility** … However, if a prospective customer is beyond
> the said distance, or his demand load requires that the utility extend lines and facilities, **the
> customer may initially fund the necessary expenditures.**
>
> To recover his aforementioned expenditures, the customer may either demand the issuance of a **notes
> payable** from the distribution utility or **refund at the rate of twenty-five (25) percent of the
> gross distribution revenue derived for the calendar year**, or, if available, the **purchase of
> preferred shares**.
>
> **Revenue derived from additional customers tapped directly to the poles and facilities so extended
> shall be considered in determining the revenues derived from the extension of facilities.**
>
> … all concerned utilities shall furnish the Commission a **semi-annual report** of the names of
> customers who made the aforementioned cash advances, the amount of the cash advance and the mode of refund."

**ERC Guidelines implementing Art. 14** (Chapter IV, e-library showdocs/10/42252, fetched 2026-08-19):
- For **electric cooperatives**, extension costs are supposed to come from the coop's **Reinvestment Fund** (§2(d)).
- Reimbursement is released **"upon proper showing of documents which will prove payment of the cost of extension lines, such as the corresponding receipt, etc."** (§2(e)) — the receipts ARE the case.
- If the funding was **gratuitous** (a donation for someone else's benefit), no refund — so Allan's payment must be framed as customer-funded, never as a community donation.

**So the mechanics are:**
1. Tapping other customers onto Allan's funded line is **not illegal in itself** — the law contemplates it.
2. But those taps **feed the refund formula**: revenue from every tapped customer counts toward the 25%-of-gross-distribution-revenue annual refund owed to the funder.
3. The violation to allege is **CANORECO never set up any refund mode at all** (no notes payable, no revenue refund, no preferred shares) while monetizing his capital — and likely never reported his cash advance to ERC in the mandatory semi-annual report. Absence of his name in those reports is itself evidence.

**Scope caveat (TO VERIFY):** the Magna Carta covers *residential* consumers. If Allan's account is
commercial/agricultural (farm or mining site), the analogous advance-and-refund regime is in the
**DSOAR** (ERC Res. 01 s. 2006) as amended ~2012 to let **non-residential** consumers advance line costs
subject to DU refund. Same architecture; exact section numbers PENDING VERIFICATION before any demand cites them.

### 1b. Poles on Allan's land without consent — framework (not yet corpus-verified)

- A distribution coop needs a **right-of-way** — by written easement agreement (normally with compensation) or by expropriation. Poles planted with neither = unauthorized occupation under the Civil Code (easements are not acquired by just showing up).
- Electric coops hold **eminent-domain power** (PD 269 as amended by RA 10531), so the realistic endgame is **ROW compensation + damages**, not removal — but the uncompensated occupation is negotiation leverage.
- If any pole stands on titled Inocalla land, tie it to the parcel record / `map_parcels` geometry.

### 1c. Standing extras

- If Allan is a **member-consumer** of CANORECO (any member since it's a coop), he has member information rights under PD 269/RA 10531 — a lever for the records demand.
- ERC has consumer-complaint jurisdiction over the coop; **NEA** supervises coops and holds their engineering/loan records.

---

## 2. Document procurement checklist

### From Allan (first — everything else keys off this)
| # | Document | Proves |
|---|---|---|
| A1 | Official receipts / any payment record to CANORECO or contractors for line construction (poles, wire, labor, transformer) | He funded it; the refundable amount |
| A2 | Any written agreement / application for line extension with CANORECO (year, span covered) | Customer-funded (not gratuitous); scope of the extension |
| A3 | His CANORECO account: account number, name on account, customer class (residential/commercial), service address | Which refund regime applies (Magna Carta vs DSOAR) |
| A4 | CANORECO membership certificate / share (if any) | Member information rights |
| A5 | Photos + GPS pins of: each tap point, each new pole, the original line route | Where taps are; where power came from |
| A6 | Dates: when the line was built; when he first noticed taps/new poles | Timeline; prescription posture |
| A7 | Title/tax dec of the parcels the poles stand on | Poles-on-his-land claim |
| A8 | Names of the households/establishments now drawing from his line (if known) | The tapped-customer revenue base |

### From CANORECO (records demand — member/consumer request, then formal demand)
| # | Document | Proves |
|---|---|---|
| C1 | **As-built plans / staking sheets / single-line diagram** for the feeder segment serving Allan's area | Where the line originally came from, exactly what was built, and every tap made since |
| C2 | The line-extension file for Allan's application: cost estimate, billing, his payments | Their own record of his funding |
| C3 | **Service connection records of every customer tapped** to the extended segment (connection dates, account class) | The revenue base for the Art. 14 refund computation |
| C4 | Refund ledger: any notes payable / refund / preferred shares issued to Allan | Expect ZERO — the violation |
| C5 | Right-of-way easement agreements (or board resolutions) for the poles on Inocalla land | Expect none — the trespass claim |
| C6 | Reinvestment Fund utilization report for the years of the extension | Whether the coop charged Allan for what its own fund should have covered |

### From ERC
| # | Document | Proves |
|---|---|---|
| E1 | CANORECO's **semi-annual reports of customer cash advances** (Art. 14, last ¶) for the relevant years | Whether Allan's advance was ever reported; absence = concealment |
| E2 | Any CANORECO applications re Reinvestment Fund increases | Context for C6 |

### From NEA (supervisory)
| # | Document | Proves |
|---|---|---|
| N1 | CANORECO distribution-system maps / engineering audits for the barangay | Independent check on C1 |

### Field (LandTek can do without anyone's cooperation)
| # | Task | Output |
|---|---|---|
| F1 | Walk the line with Allan: photograph + GPS every pole and tap, note pole markings (coops stamp pole numbers/year) | Geo-tagged tap map → `map_parcels` overlay |
| F2 | Overlay pole/tap pins on Inocalla parcel geometry | Which poles are on titled land |

---

## 3. Questions for Allan (ask over existing channel, one at a time per S14 style)
1. What year did you pay for the line, and do you still have any receipts or the agreement?
2. Is the CANORECO account in your name, and is it billed as residential or commercial?
3. Roughly how many households/buildings are now connected off your line, and when did that start?
4. Are the new poles on your titled land? Which parcel?
5. Did CANORECO ever mention a refund, credit, or shares to you? Ever sign anything about right-of-way?

---

## 4. Gaps / risks
- **No corpus support yet** — everything above is framework; no fact here is provenance-verified.
- **Gratuitous-funding trap**: if the payment reads as a community donation, Art. 14 refund does not apply. Frame the evidence as customer-funded from the start.
- **Customer-class fork**: residential → Magna Carta Art. 14; non-residential → DSOAR (sections TO VERIFY).
- **Timing**: refund accrues per calendar year from tapped-customer revenue; older years may face prescription arguments — get dates early.
- **Don't cite section numbers of DSOAR/PD 269/RA 10531 in any outward demand until pulled from primary text** (Magna Carta Art. 14 and its Guidelines Ch. IV are now verified; the rest is not).

## 5. Next actions
| Owner | Action | When |
|---|---|---|
| Jonathan/LandTek | Send Allan the 5 intake questions (§3) | On go |
| LandTek | Draft CANORECO records demand (C1–C6) — member-request tone first, cite Art. 14 + Guidelines Ch. IV §2(e) | After A1–A3 |
| LandTek | Field GPS walk (F1–F2) once Allan confirms availability | After intake |
| LandTek | Verify DSOAR non-residential refund sections from primary text | Before any demand if account is commercial |
