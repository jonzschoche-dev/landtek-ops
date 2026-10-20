# ⚠ 20 Oct 2026 (later): REFINED TO THE SLEEP DOCTRINE
Jonathan judged the Schedule packet "highly strategic and against the mandate" (noncombative; put them to sleep while the
record builds). **The outward piece is now `01_Routine_Request_Mayor_Compound_Record.md` →
`MWK-001_ROUTINE_REQUEST_COMPOUND_RECORD_DRAFT_8.5x13.pdf`** (5 pp: a 1-page letter + the SPA as Annex A).
It makes one small ask (a copy of the municipal record on the compound site, or a note that none is on file), offers
to cover the fee and collect, gives a polite 15-working-day reply period, and refers to our 15 May 2025 letter. It has
no amounts, no legal posture words, no statutes, no cc and no adverse annexes. Builder: `build_routine_letter.py`.
Strict lint: PASS. Held for Jonathan's go; not signed, printed or served.

**The Schedule packet below is now a LATER RUNG** (`HELD_LATER_RUNG/`). It moves only when the record (receipt + silence
+ courteous follow-ups) supports it, and only on its own go. Its trade-off: compensation accrues only from a demand
(Art. 1169), so each month it waits is ₱59,521.00 that can't be claimed later.

---

# Schedule of Reasonable Compensation, LGU Mercedes: HOLD NOTES (20 Oct 2026)

**Status: DRAFT, HELD for Jonathan's go.** Not signed, not printed, not served. Packet:
`MWK-001_SCHEDULE_LGU_PACKET_DRAFT_8.5x13.pdf` (18 pp; 14 pt; 8.5×13 in; every page marked DRAFT). Builder:
`build_schedule_packet.py`. Sources: `01_Cover_Letter_Mayor_Schedule.md`, `02_Schedule_of_Reasonable_Compensation.md`,
`source/A1–A5`.

## What it does
It starts the **₱59,521.00/month** compensation stream (rate decided by Jonathan, 20 Oct: Lot 401 at the LGU's 2023 ₱1,660/sq m; Lots 403/405 at ₱970/sq m) (`loss_line`: occupation_compensation, accruing from demand).
The stream runs from the **date of receipt**, and only once the stamped receiving copy is in the corpus
(corpus-proof rule → `drip_sweep.py --record-service <id> --proof-doc <doc>`). This is drip Rope 1 (the ask). The
4 Sep "kitchen-sink" damages demand (`DEMAND_LGU_COMPENSATION_DAMAGES_2026-09.md`: officials personally,
₱5M/₱5M, back rent ₱29.81M) **stays held** as the later counter-punch. Serving both would break the warm posture
(§7.6) and the stagger rule.

## Facts checked against the record (20 Oct)
| Statement | Source | Check |
|---|---|---|
| Lot 2-A, (LRA) Psd-221861, TCT T-32911 | doc 2539 (LRA CCV copy) | ✓ text |
| Lots 401/403/405 within Lot 2-A, total 8,706 sq m | doc 1070 (DENR LMS-25-550) | ✓ text ("8,706"; lot table) |
| ARP GR-2014-HH-07-005-00236: ₱943,810 / 973 sq m = ₱970/sq m | doc 152 | ✓ ARP no., 973, market value; 943,810 ÷ 973 = 970.00 |
| ₱970 × 6% ÷ 12 = ₱4.85 × 3,690 = ₱17,896.50; ₱1,660 × 6% ÷ 12 = ₱8.30 × 5,015 = ₱41,624.50; total ₱59,521.00 | arithmetic | ✓ |
| Lot areas 401 = 5,015, 403 = 2,187, 405 = 1,503 (8,705) | doc 1070 table (read from the scan) | ✓ |
| Lot 401 ARP GR-2023-II-07-005-00213, ₱8,324,900, 5,015 sq m, 27 Jul 2023 | doc 528 p.1 (read from the scan) | ✓ |
| "No instrument in the Municipality's favor is annotated on that title" | docs 2539, 17: no "donat…" in text | ✓ OCR text; **confirm on a fresh certified copy** |
| "our letter of 15 May 2025" | doc 365 (15 May 2025 packet incl. letter to the Mayor) | ✓ |

## Decisions for Jonathan before the go
1. **Rate: DECIDED 20 Oct (Jonathan).** Lot 401: 5,015 sq m × ₱8.30 = ₱41,624.50 (ARP GR-2023-II-07-005-00213, doc 528, ₱8,324,900 ÷ 5,015 = ₱1,660.00; signed by Abla, approved by Prov. Assessor Albos, 27 Jul 2023). Lots 403/405: 3,690 sq m × ₱4.85 = ₱17,896.50 (ARP …-00236, doc 152). **Total ₱59,521.00/mo**, priced lot by lot on the DENR cadastral areas (5,015 + 2,187 + 1,503 = 8,705). The title says 8,706, and the 1 sq m difference is why this is ₱5.85 below the ₱59,526.85 first quoted. Caution kept: the 2023 ARP declares the lot as *owned by* the Municipality, and its own footer says it 'should not be considered as title'. **Only page 1 of doc 528 is annexed (A-5).** The same scan carries a Deed of Donation by **Pedro Dilogo** (pp. 3–4), which stays out of the packet. It may be the LGU's claimed basis for some parcel; route it to the LGU-recovery / void-donation desk for reading [HUMAN VERIFY].
2. **Date and timing.** Fill the date. The stagger rule says don't land a new rung on the LGU cluster the same week
   as the DILG edition (due 25 Oct). Suggest serving the week of 26 Oct or later.
3. **Payment account.** Fill "[TO FILL]" in Schedule ¶5(c), or leave it as "to be designated on request".
4. **cc list.** The SB Presiding Officer (appropriation body) and MLGOO Guerrero (warm ally) are cc'd. Add or drop?
   Provincial/DILG RD stay out at Rope 1.
5. **Annex A-1** is an LRA *unofficial* e-copy (CCV). Fine as a reference. A certified true copy is stronger if
   it's ever contested.
6. **Co-owner authority.** Patricia (1/3 registered co-owner) issues it "for the benefit of the co-ownership" under
   the broad apostilled SPA. Any co-owner may act to protect the common property (Art. 487). Counsel is optional
   per standing rule; flag if you want Botor or Barandon to glance at it first.
7. **Signature.** Wet ink on the served originals. It isn't e-signed in the draft.

## Service plan (after the go)
Personal service at the Mayor's office with a receiving stamp, plus registered mail with a registry receipt.
cc copies served the same way. Photograph the stamps that day and ingest them that day. Then: `record_service` on a
new `office_obligation` row (LGU, Rope 1, `serves_objective_id` = MWK-LGU-RECOVERY). The `loss_line` start date is
the stamp date, and `start_proof_doc_id` is the stamped copy. The first monthly Statement of Account follows a month
after receipt.

## Drip lint (Stage 8 rules, run 20 Oct)
instigation ✓ · threat_early ✓ · characterization ✓ · cold_tone ✓ · internal_goal_leak ✓ · easy yes ✓ (meet,
we draft the lease, payment schedule) · gracious close ✓. Peso figures stated: ₱1,660.00, ₱8,324,900.00, ₱99.60, ₱8.30, ₱41,624.50 (doc 528); ₱970.00, ₱943,810.00, ₱58.20,
₱4.85, ₱17,896.50 (doc 152); ₱59,521.00 total. All trace to the two ARPs, the DENR areas (doc 1070) and arithmetic.
