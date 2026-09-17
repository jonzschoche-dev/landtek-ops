# Road-lot donation on TCT T-32917 — deep dive (2026-09-09)

**One sentence:** the 1980 road-lot donation to the Municipality of Mercedes was **perfected** (public
instrument, acceptance inside the deed, donor alive, attorney-in-fact holding an express power to
donate the roads) but was **never consummated on the register** — only Road Lot 2 (1,726 sqm,
"Marcia Keesey Street") was ever annotated, on T-32917 in 1995; nothing was annotated on T-4497;
no title was ever issued to the Municipality; no area was ever deducted from the heirs' titles or
declarations. "Mary Worrick-Keesey Street" (Road Lot 6, 1,126 sqm) is **not** annotated anywhere.

Status: INTERNAL / NEEDS-COUNSEL on every legal conclusion. Built from the live corpus; every
fact below carries a doc-id. Page images of the title (p. 5) and the deed acknowledgment were
visually checked on 2026-09-09.

---

## 1. What the title actually says (VERIFIED — doc 21, CTC of T-32917 printed 4 Jan 2023, p. 5)

Three entries, all presented **8 Sep 1995, 4:45 p.m.**, all marked "(File under T-4497)":

| Entry | Instrument | What it covers | Notarial anchor |
|---|---|---|---|
| PE-188451-23-21 | DEED OF DONATION in favor of THE MUNICIPALITY OF MERCEDES | "the portion of land described in this title (**Road Lot 2**) with an area of **1,726 sq.m.**" | Doc. 246, Page 50, Book III, Series of 1980, NP Antonio Mago, **14 Apr 1980**, Mercedes |
| PE-188452-23-21 | RESOLUTION "approving Resolution No. 75-79 accepting **Road Lot 1 to 6**" | generic — no lot identified on this title | "issued by Municipal Secretary Christy Ratay on July 16, 1980" (see discrepancy D2) |
| PE-188453-23-21 | AFFIDAVIT OF CONFIRMATION "confirming the previous Deed of Donation … subject to all conditions" | no lot, no affiant named in the entry | Doc. 5008, Page 100, Book LXV, Series of 1995, NP Ernesto B. de Jesus, 7 Sep 1995, Daet |

The OCR text in the DB reads these as "PE-183451…"; the page image reads **PE-188451/188452/188453**,
which is also the sequence-consistent reading (the April 1995 entry is PE-184555). `instruments_on_title`
rows 22–24 already carry the correct numbers.

**What is NOT on any title:**
- **T-4497** (mother title): CTCs of 2023 and 2025 (docs 348, 39, 25, 224) carry **no donation entry
  at all**. The only Llamanzares entry is PE-96878-109-11, a *General* Power of Attorney presented
  16 Jun 1982. (Consistent with T4497_TAKING_RECOVERY_SPINE §1.)
- No TCT-type document in the corpus carries any other road-lot donation entry (docs 494/628 are the
  unrelated 1973 school-site donation on T-4185).
- No title exists in the name of the Municipality (`titles` table, all TCT docs).
- T-32917 has never been cancelled as to any road lot; the 1996–2003 "REQUEST for separate title"
  entries on T-32917 are for Lots 2-X-6-I, -E, -R, -G, -V — private buyers, never a road lot.

## 2. The contract (VERIFIED — docs 201, 300, 301 = three scans of one deed + SB excerpts)

**Deed of Absolute Donation.** Donor: Mary Worrick-Keesey, by attorney-in-fact **Benjamin
Llamanzares**. Donee: Municipality of Mercedes, by Mayor **Cezar V. Aguilar**. Executed and
acknowledged **14 April 1980** before Municipal Judge / Ex-Officio NP Antonio B. Mago, Reg. No. 246,
Page 50, Book III, Series of 1980. Eight parcels, all "portion of TCT No. 4497", donated "**only for the
purpose of constructing roads … effective 1975**", each "to be called as" a named street:

| Deed ¶ | Road lot | Area (sqm) | Stipulated name |
|---|---|---|---|
| A | Road Lot 1 (Road II) | 1,178 | Helen Worrick Street |
| B | **Road Lot 2** (Road III) | **1,726** | **Marcia Keesey Street** ← the only lot annotated |
| C | Road Lot 3 (Road IV) | 1,606 | Patricia Keesey Street |
| D | Road Lot 4 (Road V) | 1,356 | Geraldine Keesey Street |
| E | Road Lot 5 (Road VI) | 1,266 | Elmer Worrick Street |
| F | **Road Lot 6** | **1,126** | **Mary Worrick-Keesey Street** ← NOT annotated |
| G | Road Lot 6-A (Road VII) | 1,266 | Don Estanislao Moreno Street |
| H | unnumbered (Mun. Bldg ↔ Central School) | 684 | Doña Marciana Moreno Street |
| | **Total** | **10,208** | |

**Acceptance.** Inside the deed: the Municipality "by virtue of its Resolution No. 75, series of 1979,
hereby receives and accepts this absolute donation" and the AIF "acknowledged the notification on such
acceptance." Res. 75-79 itself is **not in the corpus** as a standalone (the SB has refused the minutes;
1212 packet Annex G is the deed's acceptance clause). Atty. Botor was handed a copy at the 6 Apr 2026
CART hearing and read its date as **10 Sep 1979** (doc 751/753).

**Amendment.** SB **Resolution No. 103-86**, 16th Special Session, **16 Jul 1986**, certified by
Municipal Secretary Christy A. Ratay, Acting Mayor Archimedes O. Yanto presiding: recites that Res.
75-79 "accepted only Road Lot Nos. 1 to 6 with an area of 8,258 sq.m., omitting Road Lot 6-A and Doña
Moreno Street," that 75-79 "was promulgated in 1979 prior to execution of the Deed," amends 75-79 to
include Road Lot 6-A (1,266) and Doña Moreno St. (684), and restates the eight street names and the
1975 effectivity. (Page image checked.)

**Authority to donate (VERIFIED — doc 562, the crack that closes).** Power of Attorney executed by
Mary Worrick-Keesey **15 Jun 1976**, acknowledged 25 Jun 1976 before Municipal Judge / Ex-Officio NP
Naco (Doc. 474, Page 55), appointing Benjamin Llamanzares over the T-4497 Poblacion parcel, ¶1:
"… and likewise **to execute a Deed of Donation papers on the proposed Municipal Roads in favor of the
Municipal Government of Mercedes** for the same property below described." That is the *special* power
Art. 1878(5) requires. MWK died **17 Mar 1988** (docs 73, 165, 176) — alive at execution and acceptance.

## 3. Discrepancies to carry (do not paper over)

- **D1 — deed year.** The acknowledgment's year and "Series of 19__" are visibly **over-typed 1979 → 1980**;
  the cedulas cited are January 1979 and the typist mark reads "'79". The RD entry, the notarial series
  (Book III S-1980) and Res. 103-86 all say **14 Apr 1980**. Our outbound letters (docs 302, 379, 889,
  1266 and the 1212 open letters) say "April 1979" / "April 19, 1979". **Correct future filings to 14 Apr
  1980** and describe the over-typing neutrally if it is ever put in issue.
- **D2 — the "July 16, 1980" in PE-188452.** The SB excerpt registered is dated **16 Jul 1986** (Res.
  103-86). The RD entry says "July 16, 1980" and calls it a resolution "approving" 75-79. Treat the RD
  date as a registry error unless a separate 1980 certification surfaces; the 1212 record already states
  the 1986 date.
- **D3 — Road Lot 2 area.** Deed and RD: 1,726. Res. 103-86 typed list: 1,725/1,726 (OCR); 2023 title-tree
  note (doc 288): 1,724. Use **1,726** (deed + RD).
- **D4 — which subdivision lot is which road.** Plan **Psd-051607-014971** (the 1993 subdivision of Lot
  2-X-6) designates several sub-lots as "(Road Lot)": 2-X-6-J and, per neighbours' technical
  descriptions, 2-X-6-M/N and 2-X-6-O/Q (letters OCR-uncertain) — all running Delos Reyes Blvd ↔
  Provincial Road, i.e. the same geometry as the deed's roads. Only one mapping is on record: the 2023
  title-tree note (doc 288, operator work-product, not evidence) ties **Road Lot 2 = Lot 2-X-6-J (1,726)**.
  **Which Psd lot is Road Lot 6 / Mary Worrick-Keesey Street is unresolved.** TO-OBTAIN: the approved
  plan Psd-051607-014971 with lot areas (LRA/RD or DENR-LMS), then match 1,126 sqm.

## 4. Two donations — keep them apart (this is the answer to "what to make of a donation never perfected")

| | **Road lots (this file)** | **Municipal-Hall compound** (T4497_TAKING_RECOVERY_SPINE) |
|---|---|---|
| Instrument | Deed of Absolute Donation, 14 Apr 1980 | 1953 deed (docs 279/291, T-111 era) and an undated de la Fuente deed with acceptance left **blank** |
| Acceptance | in the deed, Res. 75-79; amended Res. 103-86 | none perfected; LGU's own Res. 76-96 (13 Mar 1996) calls acquisition "**proposed**" (doc 389) |
| Donor authority | express 1976 POA power to donate the roads (doc 562) | de la Fuente SPA (revoked 2005); 1953 signature disputed |
| Registration | Road Lot 2 only, T-32917, 1995 | none, anywhere |
| Title to donee | none | none ("Not yet po" — Atty. Tin, CART hearing 6 Apr 2026, doc 751) |
| LGU's own current words | "the road lots donated by Mary Worrick continue to be actively devoted to their intended public road purpose" (MLGOO Guerrero transmittal, doc 8303, Sep 2026) | "lawful claim" asserted, no instrument produced (DILG 2nd-indorsement state file) |
| Legal character | **perfected but unregistered and unsegregated** | **unperfected** — no transfer of ownership at all |

**Consequences of the compound being unperfected (NEEDS-COUNSEL):** a donation of real property is void
unless made and accepted in a public instrument (Art. 749); with no acceptance nothing passed (Art. 734).
The Municipality is a possessor without title; a registered Torrens title is imprescriptible against it
(Atty. Botor put exactly this to the LGU on 6 Apr 2026). Remedy = the RTC recovery track already
outlined (reconveyance / accion reivindicatoria + reasonable compensation), which this file does not
change.

**Consequences of the road lots being perfected but unregistered (NEEDS-COUNSEL):**
1. *Between heirs and Municipality* the donation is binding; ownership of the eight road lots passed
   on acceptance (Arts. 712, 734, 749). Registration is not a requisite of validity; an unregistered deed
   "shall operate only as a contract between the parties" (PD 1529 §51). The heirs cannot treat the roads
   as simply theirs.
2. *Against third parties* the unregistered portion (everything except Road Lot 2) does not bind
   purchasers of record — but the sub-lots are marked "(Road Lot)" on the approved plan and have been
   public roads since 1975, so no buyer can claim good faith. Low practical exposure.
3. *On the register* the heirs remain owners of record of the whole Lot 2-X-6 remainder, including every
   road lot. The Municipality cannot get a title without (a) a segregation plan and technical descriptions
   for each road lot (PD 1529 §58 — no transfer certificate for a portion until the plan is approved),
   (b) the owner's duplicate of T-32917 (§53), (c) BIR CAR / donor's-tax clearance and RPT clearance.
   **Every one of those runs through the heirs.** This is the leverage: the LGU's "SPA from all heirs"
   objection is *correct for a registration act* (Arts. 491/493) and *irrelevant to the naming demand*
   (Art. 487, any co-owner). Offer the LGU what it actually needs (confirmation + segregation, all heirs)
   in exchange for what the deed already obliges it to do (names, cleared roads) and what the assessment
   roll owes (below).
4. *Assessment roll.* Because nothing was deducted, the heirs' declarations still carry the road-lot ground
   (the 19,399-sqm parcel, doc 51, is bounded by "Road Lot 1"), and the heirs paid RPT on it in 2023–24
   (Treasurer, doc 378). Roads donated to an LGU are public dominion (Art. 420) and not taxable in the
   heirs' hands. TO-VERIFY: whether the declared areas include the 10,208 sqm; if so, a rectification +
   refund/credit claim belongs in the Assessor/BLGF lane, and it is an admission-forcing ask (the
   Municipality cannot both tax the heirs on the roads and call the roads its own).
5. *Conditions.* Two stipulations ride on the donation: use "only for the purpose of constructing roads"
   and the eight street names. Non-compliance (no naming ordinance in 46 years; Road Lot 6 obstructed by
   private structures — docs 379, 889; the LGU's Sep 2026 denial, doc 8303) opens Art. 764 / Art. 1191
   revocation in principle. Prescription is the live question: Art. 764 gives four years from
   non-compliance; jurisprudence treats onerous/modal donations under the law on contracts with a ten-year
   period (De Luna v. Abrigo; Dolar v. Barangay Lublub), and treats "build/use for X" stipulations as
   modes rather than suspensive conditions (Republic v. Silim; Central Philippine University v. CA). A
   revocation pleaded today over a 1980/1986 breach is a long shot; a **continuing-breach** theory
   (obstruction of Road Lot 6 as a present failure of the road purpose) is the arguable route. Counsel's
   call; do not assert revocation in outward letters.
6. *Mandamus caution.* Passing an ordinance is a legislative, discretionary act; courts do not mandamus
   a Sanggunian to legislate. "Ministerial duty" is rhetoric, not a cause of action. The enforceable
   framing is contractual: specific performance of the modal stipulation, or revocation with damages.
7. *Encroachments on Road Lot 6.* Two hats are available and they conflict: as *registered owners* the
   heirs can sue occupants directly (imprescriptible title) — but they would be asserting ownership of land
   they donated, which the LGU (not the occupant) could raise. As *donor* the heirs can demand the donee
   clear its road (LGC §444(b)(3)(vi)) and hold revocation in reserve. Recommended: donor hat first, with
   the LGU's own "actively devoted" sentence (doc 8303) as the admission that binds it to act.

## 5. Gaps — TO-OBTAIN

| # | Item | Why |
|---|---|---|
| 1 | SB Resolution 75-79, certified (**CORRECTED 2026-09-14: the SB released CTCs of 75-79, 103-86 and 76-96 on 16 Dec 2025, per gmail 96462, and Jonathan acknowledged receipt 11 Jan 2026. Find the picked-up copies and ingest them.** Botor also holds a copy) | the acceptance the deed relies on; its own date (10 Sep 1979?) |
| 2 | Approved plan Psd-051607-014971 with road-lot areas | map Road Lot 6 (1,126) to a Psd lot; needed for any segregation and for the encroachment case |
| 3 | The 7 Sep 1995 Affidavit of Confirmation (NP de Jesus, Doc 5008/LXV) | who confirmed, and why only Road Lot 2 was registered |
| 4 | Whoever holds the **owner's duplicate** of T-32917 | the registration leverage in §4.3 |
| 5 | Heirs' current tax declarations with areas (Assessor roll) | §4.4 — are the roads being taxed to the heirs |
| 6 | BIR: was a CAR ever issued for the 1980 donation | completes the validity rubric; LGU donee is exempt from donor's tax but a CAR is still the RD's gate |

## 6. Document index

| Doc | What |
|---|---|
| 21 | CTC T-32917 (4 Jan 2023), p. 5 — the three 1995 entries (image-verified) |
| 201 / 300 / 301 | Deed of Absolute Donation, 14 Apr 1980 + Res. 103-86 excerpt (three scans; 300/301 read the year correctly) |
| 562 | Power of Attorney, 15 Jun 1976 — express power to donate the municipal roads |
| 348, 39, 25, 224 | CTCs of T-4497 — no donation entry; Llamanzares GPA entry of 1982 |
| 389 | Res. 76-96 (13 Mar 1996) — compound acquisition "proposed" |
| 751 / 753 | Verbatim transcript, CART hearing 6 Apr 2026 — "Not yet po"; Res. 75-79 dated 10 Sep 1979 |
| 8303 | MLGOO Guerrero transmittal of the LGU reply (Sep 2026) — "actively devoted" |
| 288 | 2023 title-tree note — Road Lot 2 = Lot 2-X-6-J (operator work-product) |
| 23, 52, 307, 308, 319 | Derivative TCTs whose boundaries name Psd-051607-014971 "(Road Lot)" sub-lots |
| 51 | Provincial Assessor statement, 19,399-sqm parcel bounded by Road Lot 1 |
| 73, 165, 176 | MWK death 17 Mar 1988 |
| 302, 379, 889, 1266 | Our May/Sep/Oct 2025 letters and the 1212 packet (carry the 1979 date — correct going forward) |
