# Corpus Scan: Guidance for a LandTek Field Protocol on Squatters / Informal Settlers (2026-10-28)

Internal, for Jonathan. Research input to the protocol, not the protocol itself. Nothing served, filed,
printed or sent. Every item points to its source in the record. Anything not in the record is UNKNOWN.

## 1. What already exists (the raw material)

| # | Source | What it gives the protocol |
|---|---|---|
| S1 | `case_work/MWK-001/SQUATTER_ENGAGEMENT_RIGHTS_SCHEME.md` (19 Jul 2026) | Core doctrine: segment first; every contact both offers and asserts; tolerance withdrawn = Rule 70 predicate; reservation-of-rights wording; offer ladder (lease / buy / vacate / suit). |
| S2 | `case_work/MWK-001/HOUSE_TO_HOUSE_OCCUPANT_SURVEY_2026-10_DRAFT.md` | The field form, one record per structure (9 fields), and the rule "field captures, desk classifies". |
| S3 | `case_work/MWK-001/CENSUS_WORKLIST_T32917_2026-09.md` | Parcel roster with paper leads; 6-point field-confirm checklist; the unmapped ~4.2 ha on T-32917. |
| S4 | `case_work/MWK-001/DRAFT_pay_to_stay_demand.md` | Pay-to-stay instrument (compensation, NOT a lease) on Patricia's 1/3 under Art. 487; rate floor ~0.5%/mo of assessor MV [EST]; collection runs through `v_mwk_reimbursement`. |
| S5 | `case_work/MWK-001/DRAFT_squatter_demand_and_ejectment.md` | Demand+offer+reservation letter and Rule 70 complaint template (T-52537 pilot); vehicle choice UD vs publiciana; KP non-resident exemption [confirm w/ counsel]. |
| S6 | `case_work/MWK-001/T4497_IMPROVEMENTS_LEVER.md` | Bad-faith builder (Arts. 449-452, 526) + PD 1096 no-permit route; evidence pack ranked; six honest caveats (below). |
| S7 | `case_work/Paracale-001/DEMAND_TO_VACATE_VITO_CRUZ_ALL_OCCUPANTS.md` (Paracale client, method only) | The only written SERVICE procedure in the record: serve each adult, capture names on the receiving copy, refusal handling, post + photograph, witness/barangay escort. |
| S8 | `case_work/Paracale-001/MANILA_EJECTMENT_BRIEF_OF_FACTS.md` §6 (method only) | Katarungang Pambarangay in practice: a captain can stall the CFA; admin case against the captain; non-resident plaintiff exemption. |
| S9 | `case_work/MWK-001/BARANGAY_UNO_MEETING_BRIEF_2026-10_DRAFT.md` | How to work a barangay as ally: get / give list, UPL line (no legal advice to the barangay), CV26360 harassment-narrative caution. |
| S10 | `case_work/LandTek-Corp/FIELD_APP_DESIGN_2026-10.md` + `field_app/` (MVP code exists, NOT deployed) | Capture tool: GPS + photo + offline queue; writes only `field_survey_records`; never writes `map_parcels`; no fabricated GPS. |
| S11 | `jurisprudence/DRAFT_Altarejos_v_Bautista_GR247009_2024-02-26.md` (DRAFT, not ingested) | SC 2024: mayor cannot summarily evict outside UDHA §§27-28; only the Building Official declares a structure illegal/dangerous; ejectment needs a court. |
| S12 | `jurisprudence/DRAFT_Alangdeo_v_City_Mayor_of_Baguio_GR206423_2015-07-01.md` (DRAFT) | Same line: no summary demolition by the executive; due process. |
| S13 | `jurisprudence/DRAFT_NOTE_mixed_zone_ejectment_2026-10-26.md` | Zoning is not an eviction ground; no on-point SC case found [UNCERTAIN]. |
| S14 | `case_work/MWK-001/PILOT_T52537_RULE95_PACKAGE.md` | Occupied-parcel reality: "clean title does not mean vacant"; recover-then-sell vs sell-subject-to-occupancy. |

Law already in the corpus (`legal_chunks`): RA 7279 full (27 chunks, incl. §§27-28 eviction procedure,
chunks 4829-4831), Rule 70, Civil Code full, PD 1096 full, PD 1529 full, RA 7160 full (§§408/412 KP),
RA 10173 Data Privacy full, Act 3815 RPC full.

## 2. Rules the corpus already agrees on (protocol backbone)

1. **Classify before you engage.** "You cannot engage what you haven't named" (S1). The field never
   classifies; the desk does (S2, S10).
2. **Three tracks** (S2, S3, S10 wording):
   A = holds a title/deed tracing to the de la Fuente chain -> nullity/reconveyance, NEVER pay-to-stay or lease.
   B = no title, informal -> pay-to-stay (compensation) or ejectment on Patricia's 1/3 (Art. 487).
   C = LGU / government occupant -> inverse condemnation + back-rental.
   Default rule: any deed/title tracing to de la Fuente = Type A even if a tax dec is also shown (S2).
3. **Every contact asserts and reserves.** Fixed wording: "without prejudice to, and with express reservation
   of, all the rights... and without any recognition of any right in you" (S1, S4, S5). Nothing said or
   accepted in the field may read as tolerance, consent or a lease.
4. **Pay-to-stay is not a lease.** Month-to-month, terminable on [15] days, "creates no lease and no tenancy";
   never framed as agricultural tenancy (RA 3844/6657 trap) (S4).
5. **Demand is the jurisdictional predicate.** Written demand to pay and vacate, with proof of receipt; the
   1-year UD clock runs from the LAST demand (S5, S7).
6. **Never self-help.** No demolition, padlocking or removal without a court order or a Building Official
   order with its own due process (S6 caveat 4; S11).
7. **UDHA screen per household.** Underprivileged-and-homeless occupants get RA 7279 due process and
   relocation; "professional squatters" (sufficient income for legitimate housing) are not shielded (S1, S11).
   The field must record capacity-to-pay indicators (S2 item 7).
8. **Rebut tolerance every visit.** The squatters' best counter is Art. 453 owner-knew-and-did-nothing
   (S6 caveat 2). Each documented visit, demand and certification is evidence of owner opposition.
9. **Scope the no-permit claim per structure.** Permits WERE issued on void titles in the titled
   subdivision (doc 959), so "no building permit" is only for informal structures (S6 §0.1).
10. **Barangay as ally, not client.** Share records and maps; no legal advice; don't direct their cases (S9).
11. **Every outward act is Jonathan-gated and counsel-executed** (all sources).

## 3. Field mechanics already in the record

- Per structure: barangay, map sheet/parcel label, GPS pin, date, surveyor; structure type, materials, area;
  occupant name, contact, household size; occupying since; how acquired; claimed basis with document number;
  building permit shown; capacity-to-pay indicators; barangay/health-worker certifier signature; photos (S2).
- Desk adds: matched sub-lot, track A/B/C (S2, S10).
- Service of a demand (S7): personal service on every adult present; each prints name and signs/dates the
  receiving copy; refusal = "refused, served by leaving copy" + date/time + witness; post one copy on the
  main door/gate and photograph it in place; keep one annotated copy per recipient; barangay or notary escort.
- Records to pull per structure (S6 §3): OBO certificate of no permit (already requested 24 Jan 2026, doc
  772, stonewalled); barangay certification of no owner consent; construction-dating proof (assessor
  improvement records are withheld, doc 2388); capacity-to-pay records.
- Entry point: on 27 Oct 2026 (Cerdon affidavit) all four barangays said they will help identify residents
  once given a boundary map (S2, S10). San Roque offered health-worker records (S2).

## 4. Conflicts and stale items to resolve before the protocol locks (CONFLICT for Jonathan)

1. **Lease offer in S1 is stale.** S1 still offers a "<=1-yr renewable lease" now. Later work (S4; harvest
   session 7cce09ee, approved) replaced it with compensation-for-occupation, with lease/buy only after the
   guardian (Rule 95) or co-owner majority (Art. 492). S1 was never updated.
2. **Tier numbering is inverted.** S1 uses Tier 1 = informal, Tier 2 = titled. S2/S3/S10 use Type A = titled,
   B = informal. Pick one (recommend A/B/C, it is what the app stores).
3. **Gaulit / T-52537 is classified both ways.** S4 and S5 treat Sps. Gaulit as an informal occupant (pay-to-stay
   pilot). S14 notes Delfin Gaulit is transferee #6 of the 20 named transferees. If his claim traces to de la
   Fuente, the S2 default makes him Type A and the pay-to-stay pilot letter would be the wrong instrument.
   Needs ground + paper check before anything is served.
4. **Track mix is inference.** "~90% titled Type A, ~10% Type B" comes from the mapping agent (inferred_weak,
   harvest 7cce09ee). "Ten squatter families on the lot ... double deals made by Salvador" is Jonathan's
   statement (harvest cd190a23); which lot is UNKNOWN.
5. **KP exemption is unconfirmed.** S5 relies on Patricia's US residence for the RA 7160 §408 exemption,
   marked [confirm w/ counsel].

## 5. Gaps: what the protocol needs that the corpus does NOT have

- **Field safety / conduct rules for the rep** (Kristyle): team size, escort, de-escalation, what to do if
  threatened, no-go conditions, check-in. Nothing in the record. UNKNOWN.
- **Script for what the rep says** at the door (Tagalog/Bikol), and what she must never say (no promises,
  no threats, no "you will be demolished"). Only the Paracale and T-52537 pay-or-quit letters exist
  (`MWK-001/PAY_OR_QUIT_TAGALOG/`), no spoken script.
- **Data privacy handling** of household data, photos and contact numbers. RA 10173 is in the corpus but no
  LandTek procedure applies it (consent line on the form, retention, access). UNKNOWN.
- **PNP / PCUP / LIAC coordination.** RA 7279 §27 names PNP and PCUP; no record of either for Mercedes.
- **UDHA IRR, RA 8368 (repeal of anti-squatting PD 772), Rule 39 §10(d) special order of demolition, and the
  current Rules on Summary Procedure** are NOT in `legal_chunks`. Needed before the protocol cites them.
- **Altarejos and Alangdeo are DRAFT, not ingested** (need Jonathan's go to ingest).
- **Pay-to-stay rate** basis is [EST]; no broker comp or zonal value pulled.
- **Field app** is built but not deployed; four design decisions are still open (device, photo storage,
  host, scope) per S10.

## 6. Suggested protocol skeleton (for discussion)

Phase 0 Prep: barangay boundary map + authorization letter naming the rep + form stack + app on phone.
Phase 1 Identify (barangay-assisted canvass): survey form per structure, no demand served, no classification
  in the field, reservation statement only if asked.
Phase 2 Desk: match to sub-lot, A/B/C, UDHA screen, records pull (OBO, barangay no-consent cert).
Phase 3 Instrument (Jonathan go + counsel): A -> nullity track letter; B -> pay-to-stay or demand to vacate;
  C -> LGU track. Service per S7 mechanics.
Phase 4 Clock (the drip): 15-day period from proof of receipt; payers logged to the ledger; refusers to
  Rule 70 within 1 year of last demand.
Phase 5 Enforcement: court or Building Official order only; RA 7279 §28 procedure where it applies.
Cross-cutting: safety rules, privacy rules, evidence chain (GPS, photo, signed receipt), anti-tolerance log.

*Internal research brief. Not legal advice; counsel reviews. Nothing outward without Jonathan's go.*
