# Inocalla Estate — Title / Holdings Inventory (Paracale-001)

> **Matter:** Paracale-001 (Inocalla estate, Paracale / Jose Panganiban, Camarines Norte)
> **Source:** holdings/title-inventory table in corpus docs **520 / 634 / 669**; clean copy **confirmed by operator (Jonathan) 2026-06-13** (the corpus OCR had scrambled the "Registered Owner" column — see note below).
> **Recorded:** 15 rows inserted into `titles` (case_file=`Paracale-001`) at `provenance_level='inferred_strong'` — a summary table, not the individual certificates. **Upgrade a row to `verified` when its actual certificate is pulled + quoted.**
> **Authored:** 2026-06-13.

---

## ⭐ The answer: the 23-ha lot titled to Jesus

**Lot #6 — Title No. P-1617 — JESUS INOCALLA — 23.4356 hectares — Lot 8, Psu-143364 (Amd.).**

This is a **sole** title in Jesus Inocalla's name (patent-series). It is distinct from Lot #1 (T-3897, 23.0935 ha) which is registered to **Vicente Inocalla** and only *partition-awarded* to Cipriana/Vicente Jr./Jesus jointly. So Jesus has:
- **a sole title — P-1617, 23.4356 ha** (Lot 6), and
- **a ⅓ partition share** of T-3897, 23.0935 ha (Lot 1).

---

## Full inventory (15 lots)

| # | Survey No. | Registered Owner | Title # | Area (has.) |
|---|---|---|---|---|
| 1 | Lot 1, Psu-152027 | Vicente Inocalla (Vicente Jr., Cipriana, Jesus) | T-3897 | 23.0935 |
| 2 | Lot 1, Psu-152156 | Beatriz Villafria (Marilou & Allan) | T-3424 | 22.5178 |
| 3 | Lot 2-B (LRC) Psd-56979 | Vicente Inocalla, Sr. (Herbert & Senen) | T-5656 | 19.7727 |
| 4 | Lot 2, Psu-14364 | **DBP** / (Casper Inocalla) | T-20754 | 10.2928 |
| 5 | Lot 9-A, Psd-05-012242 | Marilou Inocalla | T-29841 | 2.3513 |
| **6** | **Lot 8, Psu-143364 Amd.** | **JESUS INOCALLA** | **P-1617** | **23.4356** |
| 7 | Lot 6, Psu-143364 | Vicente Inocalla | ARP No. 021-0312 *(tax dec, not a title)* | 18.0003 |
| 8 | Lot 10, Psu-143364 | **DBP** / (Casper Inocalla) | T-20756 | 18.9591 |
| 9 | Lot 5, Psu-143363 Amd. | **DBP** / (Casper Inocalla) | T-20757 | 23.5845 |
| 10 | H-128572 | **DBP** / (Casper Inocalla) | T-20755 | 11.1486 |
| 11 | Lot 4, Psu-143364 | Allan Inocalla | P-1616 | 15.2069 |
| 12 | Lot 7, Psu-143364 Amd. | Vicente Inocalla, Jr. | P-1516 | 22.8024 |
| 13 | Lot 1, Psu-143364 Amd. | Cipriana Inocalla | P-1615 | 23.0238 |
| 14 | H-44920 | Vicente Inocalla / (Senen Inocalla) | T-2194 | 13.3690 |
| 15 | Lot 3, Psu-143364 | Beatriz Villafria / (Herbert Inocalla) | T-4185 | 11.3042 |

Total ≈ 254.7 has. (header on the source page reads "…1,547" — likely a sub-total/ref, not the full area).

## Observations

- **Patent titles to the individual heirs** (P-series): **P-1617 Jesus**, P-1616 Allan, P-1615 Cipriana, P-1516 Vicente Jr. These are the lots held in single heir names.
- **Four lots are under DBP** (Development Bank of the Philippines) — T-20754/20755/20756/20757, ~64 has. combined, associated with Casper Inocalla. **This is a mortgage/foreclosure exposure worth running down** (who redeemed, current status).
- **Lot 7** carries only an **ARP/tax-declaration number (021-0312)**, not a Torrens title — weaker tenure.
- The partition (**Civil Case B-5625**, Judicial Partition, doc 510) and the 2006/2021 Manila litigation concern overlapping parcels; cross-reference before relying on any single source.

## ⚠ Why this was missed earlier (and the limitation it exposes)

This exact table **is in the corpus** (docs 520/634/669), but the scan's **"Registered Owner" column OCR'd to garbage**. Searches could read the Title column (`…P-1617…`) and Area column (`…23.4356…`) but could not align "Jesus Inocalla" to row 6 — so "is there a title in Jesus's name?" returned a false negative. **Lesson: a table whose key column is OCR-illegible can hide a fact that's plainly present.** Flag low-confidence column alignment instead of concluding absence.

## Gaps / next

1. **Pull the standalone P-1617 certificate** — not ingested. Needed to (a) upgrade Lot 6 to `verified`, (b) confirm the **exact location** (operator says **Jose Panganiban**; the Psu-143364 series elsewhere maps to Calaburnay/Paracale — the certificate settles it), and (c) confirm current lifecycle status.
2. **Re-OCR this inventory table** properly (heightened/vision) so the owner column is captured and the system stops missing it.
3. **MGB / mineral layer** — corpus holds a 2026 NIBDC→MGB request for the **EXPA 000322-V** case file (doc 798, Jonathan authorized to receive). If an MGB certification lists Lot 6 under Jesus on the *mineral* side, bind it to P-1617 here.
4. **DBP lots** — pull T-20754/55/56/57 status (redemption/foreclosure).

*Work product for Paracale-001, grounded 2026-06-13. Inventory rows are `inferred_strong` (operator-confirmed summary); individual certificates are the verification upgrade.*
