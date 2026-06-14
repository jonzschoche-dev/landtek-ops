# Evidence Collection List — Civil Case 26-360 (T-4497 recovery, 20 transferees)

> **Source:** generated from the truth-layer `evidence_action_list` view (transfer_doc_status →
> doc_requirements_law), 2026-06-14. **329 missing evidence items across the 20 transferees**
> (+50 on unlinked/placeholder transfers). Regenerate as documents are obtained.
> **Engine:** `SELECT * FROM evidence_action_list ORDER BY priority DESC;`

## The strategic frame — this list is OFFENSIVE, not homework

This is an **accion reivindicatoria**. These "missing documents" are the ones each **transferee/defendant**
would need to prove their transfer from the Keesey title was valid. They are **missing because the
transfers were never properly supported** — every one carries a consequence of `not_recordable`,
`voidable`, `tax_lien`, or `vulnerable_to_challenge`. So the move is twofold:

1. **Demand Certificates of No Record (CNR)** from the RD / BIR / LGU / DAR — a CNR *proving no CAR,
   no CGT payment, no DST, no registered deed exists* is affirmative proof the transfer is void
   (`not_recordable`). The absence IS the evidence.
2. **Obtain the few we can** (certified true copies that exist) to complete our own chain.

## What to obtain — by document type (the bulk of the 329)

Ordered by priority (5 = transfer-killing if absent). Each is missing for ~33 transfer instances.

| Pri | Missing document | Legal basis | Consequence if absent | Action |
|----|---|---|---|---|
| 5 | **Notarized Deed of Absolute Sale** | PD 1529 §53; Civil Code 1458-1623 | not_recordable | CTC from RD; if none → **demand CNR** |
| 5 | **BIR Certificate Authorizing Registration (CAR)** | NIRC §24(D); RR 12-2018 | not_recordable | Request BIR; if none → **CNR** |
| 5 | **Original Owner's Duplicate Copy of TCT** | PD 1529 §53 | not_recordable | RD; if none → CNR |
| 4 | Capital Gains Tax payment (6%) | NIRC §24(D)(1); RR 13-99 | tax_lien / voidable | BIR record; if none → **CNR** |
| 4 | Documentary Stamp Tax (BIR Form 2000) | NIRC §196; RR 13-2004 | tax_lien / voidable | BIR; if none → CNR |
| 4 | LGU Transfer Tax receipt | RA 7160 §135 | voidable | LGU Treasurer; if none → CNR |
| 4 | DAR Clearance (agricultural land) | RA 6657; DAR AO 1 s.2019 | voidable | DAR; if none → CNR |
| 3 | Real Property Tax clearance (to year of transfer) | RA 7160 §250 | tax_lien | LGU Treasurer |
| 2 | LGU Zoning / Locational Clearance | LGC §447 | vulnerable_to_challenge | LGU |
| 1 | Barangay Clearance | LGC §15 | vulnerable_to_challenge | Barangay |

**The priority-5 trio (Deed + CAR + Owner's Duplicate)** is the spine of the void argument: if a
transferee cannot produce these, their TCT was issued on a transfer that "cannot be recorded" —
i.e., it should never have issued. **CNRs on these three per transferee = the recovery case.**

## Where the gaps concentrate (per transferee)

| Transferee | Missing | Note |
|---|---|---|
| Jose Pascual Jr. | 30 | deepest gap (3 transfers tracked) |
| Cesar Ramirez · Pedro Valledor · Edgardo Santiago · Roscoe Leaño · Erlinda Tychingco · Maria V. Cereza | 20 each | 2 transfers each |
| Mariquita Era · Rosalina Hansol · Ruben Ocan · Severino Tenorio Jr. · Alberto Victa · Ananias Apor · Arnel Mabeza · Aurora Bernardo · Delfin Gaulit · Dolores Vela · Elsa Illigan · Librada B. Onrubio | 10 each | 1 transfer each |
| **Gloria Balane** | 9 | flagship — already worked in `BALANE_EVIDENCE_SPINE.md` (void 1992-SPA path) |
| (unlinked/placeholder transfers) | 50 | transfers not yet tied to a named transferee — link first |

## Recommended sequence
1. **CNR demand letters** to RD Daet + BIR RDO + LGU + DAR for the **priority-5 trio per transferee**, starting with **Balane** (live SJ), then the deepest gaps (Pascual, the 20s).
2. **Obtain the few real CTCs** that exist (e.g., the 2016 Balane deed, the P-1617 / 1992-SPA instruments) to close our own chain holes.
3. **Link the 50 placeholder transfers** to named transferees so their requirements populate.

*Drafting the actual CNR demand letters is the credit-gated step (Leo/Barandon); this list is the
deterministic worklist that drives it. Regenerate from `evidence_action_list` as items come in.*
