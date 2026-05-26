# Feedback rule: MMK ≠ MWK — Michael Marcos Keon is NOT Mary Worrick Keesey

**Filed:** 2026-05-26 (Jonathan correction during the Singson investor meeting chat)

## What happened

During a Telegram session, Jonathan said:
> *"today we met with chavit Singson with Michael Marcos Keon and Allan Inocalla
> about investing in the mining property Allan has"*

Then uploaded 3 PDFs and said:
> *"these documents were all received [by] Mr. Singson and executed by Allan and MMK"*

Leo logged a chat_note (#156) interpreting **"MMK"** as **"MWK (Mary Worrick Keesey)"** — wrong.

Jonathan corrected: *"Wait a second this is for Allan Inocalla estate."*

## The rule

These two acronyms are NEVER interchangeable:

| Acronym | Who | Matter | Client |
|---|---|---|---|
| **MMK** | Michael Marcos Keon (person, Marcos-family relative, Allan Inocalla associate) | Paracale Gold Partnership (PAR-CAPACUAN) | **PAR (Paracale)** |
| **MWK** | Mary Worrick Keesey (deceased 1988, mother of Patricia Keesey Zschoche) | TCT T-4497 mother title; Civil Case 26-360 (Zschoche v. Balane) | **MWK (separate client)** |

The two are in **different clients**, **different matters**, **different countries of corporate origin**, **different decades**, and **different families**. Never auto-expand MMK to MWK or vice versa.

## How Leo should handle these acronyms going forward

1. **MMK in a sentence with Allan Inocalla / Singson / Paracale / mining → Michael Marcos Keon**
2. **MWK in a sentence with Patricia / Cesar / Balane / TCT T-4497 / 26-360 → Mary Worrick Keesey**
3. **If ambiguous → set `needs_clarification=true` and ask, do not guess.**
4. Never write the expanded form parenthetically unless an explicit source uses it.

## What deploy_275 did

- Reclassified doc#962 (Paracale Gold Partnership MoU to Singson) → Paracale-001 / PAR-CAPACUAN
- Reclassified doc#963 (Endorsement letter to Singson re: Allan) → Paracale-001 / PAR-CAPACUAN
- Created 4 new entities: Luis "Chavit" C. Singson, LCS Group of Companies, Satrap Mining, Michael Marcos Keon
- Rewrote chat_note #156 to remove the MWK conflation and explicitly call out the distinction

## Open follow-ups (deferred)

- Extend `case_theories/par_capacuan_tsx_listing.py` with a new section for the Singson investor thread + the Paracale Gold Partnership MoU as a counterparty offer
- Add MMK + Chavit Singson to PAR keystone_entities once the canonical IDs are stable
- Add a truth_test asserting the MMK ≠ MWK distinction
