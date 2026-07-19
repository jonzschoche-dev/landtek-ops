# Estate Expense & Reimbursement Engine — MWK (2026-07-19)

**Goal:** capture, substantiate, and total every peso Jonathan + Patricia advanced on the estate's behalf,
so it is (a) reimbursed **off the top** of estate proceeds before distribution, and (b) charged against the
**refusing co-owners' shares** (Gerry, Marcia) under Art. 488. Getting the money back and rebalancing the
3-way split are the same claim.

**Engine = the existing `legal_cost_actuals` table** (already has matter_code · category · amount_php ·
currency · incurred_date · paid · description · source · source_doc_id · recorded_by; currently 0 rows).
Do NOT build a parallel table. Add three fields, populate, and run the reimbursement view below.

---

## 1. Legal basis for recovery (why every logged peso comes back)
- **Art. 488 Civil Code** — "Each co-owner shall have a right to compel the other co-owners to contribute to
  the **expenses of preservation** of the thing … **and to the taxes.**" Gerry + Marcia refused to fund
  ("didn't want to put out any money") → **their 1/3 each of every preservation expense + tax is chargeable
  to their shares.** Patricia's own 1/3 is her contribution; the other **2/3 is recoverable.**
- **Rule 96 §8** — a guardian's **necessary expenses and compensation** are paid **from the estate before
  distribution** (once the guardianship is granted, Jonathan-as-guardian's expenses become a first charge).
- **Effect:** reimbursement is a **FIRST CHARGE on the proceeds** (CV 6839, sales, rentals) AND a **direct
  claim against Gerry's and Marcia's net shares.** It reduces what the refusers take, not what you do.

---

## 2. Expense categories (the ledger taxonomy)
| Category | Examples | Reimbursable basis |
|---|---|---|
| `professional_fees` | ABLAW/Botor (guardianship), Yuzon (CV6839 opinion), Dialogo (RD/CV6839) | Art. 488 preservation + Rule 96 |
| `docket_filing_fees` | Spec.Proc. 2680 filing, ARTA docket, future mandamus/RTC | Art. 488 preservation |
| `records_certification` | RD/Assessor CTCs, tax-dec copies, title certifications | Art. 488 preservation |
| `rpt_taxes` | the ₱775,202 amnesty settlement + annual RPT paid | **Art. 488 "and to the taxes"** (strongest) |
| `notarial_apostille` | the broad Patricia SPA apostille, verifications | Art. 488 preservation |
| `research_ocr` | vision-OCR, document recovery, investigation | necessary-expense (weaker; log w/ care) |
| `travel_admin` | PH trips, courier, printing/binding | necessary-expense (substantiate heavily) |

---

## 3. Per-share allocation model (Art. 488)
For each **preservation/tax** expense of amount `A`, paid by Jonathan/Patricia:
- Gerry owes **A/3**, Marcia owes **A/3**, Patricia's **A/3** is her own contribution.
- **Recoverable from the estate/refusers = 2A/3.**
Guardian (Rule 96) expenses incurred *after* appointment are recoverable **in full off the top** before the split.
Running totals per co-owner = the amount to net against Gerry's and Marcia's distributions.

---

## 4. THE RECORD ALREADY EXISTS — doc 777 (use it; do NOT reconstruct)

**`JPZ ADMIN STATEMENT OF EXPENSES updated.xlsx` (doc 777 `[V]`)** — prepared by **Colen N. Ibasco**, titled
*"Detailed Statement of Expenses (Incurred in the Recovery of Possession, Administration, and Protection of
Family Properties of the Heirs of Mary Worrick Keesey)"* — already Art.488-framed, dated from 2020, backed by
an **Index of Receipts (Annexes)**. It is the record of authority; the engine just ingests it.

**GRAND TOTAL: ₱2,005,405.92 `[V]`** (path: `/root/landtek/uploads/MWK-001/email_attachments/em420_JPZ_ADMIN_STATEMENT_OF_EXPENSES_updated.xlsx`; sibling docs 778/779, PDF doc 640).

| Cat | Category | Subtotal (₱) | Basis |
|---|---|---|---|
| A | Research, fact-finding, due diligence | 61,964.95 `[V]` | art488_preservation |
| B | Professional fees (incl. filing 6,124.76) | 231,124.76 `[V]` | art488_preservation |
| C | (legal/litigation — read from doc 777) | ~part of 601,956.60 | art488_preservation |
| D | Travel | 24,279.20 `[V]` | necessary (substantiate) |
| E | Government fees/charges | ~part of 601,956.60 | art488_preservation |
| F | **Taxes and assessments** | **1,086,080.41 `[V]`** | **art488_tax (strongest)** |
| G | Office and admin | ~part of 601,956.60 | necessary |
| **—** | **GRAND TOTAL** | **2,005,405.92 `[V]`** | |

*(C + E + G ≈ ₱601,956.60 combined — pull each exact subtotal from doc 777 when loading per-line.)*

**Population step:** ingest doc 777's category rows into `legal_cost_actuals` (matter MWK-001, source_doc_id=777,
paid_by='jonathan/patricia', reimburse_basis per column above), one row per category (or per line-item for the
receipt-backed ones). This is a clean import from an existing prepared statement — not a reconstruction.

---

## 5. Draft SQL — DO NOT EXECUTE (operator review; .bak; idempotent)
```sql
-- 5a. Extend the engine for reimbursement tracking
ALTER TABLE legal_cost_actuals ADD COLUMN IF NOT EXISTS paid_by text;              -- 'jonathan'|'patricia'|'estate'
ALTER TABLE legal_cost_actuals ADD COLUMN IF NOT EXISTS reimbursable boolean DEFAULT true;
ALTER TABLE legal_cost_actuals ADD COLUMN IF NOT EXISTS reimburse_basis text;      -- 'art488_preservation'|'art488_tax'|'rule96_guardian'|'necessary'
ALTER TABLE legal_cost_actuals ADD COLUMN IF NOT EXISTS or_ref text;               -- official receipt / invoice no (substantiation)

-- 5b. Seed the one verified row (repeat per expense after reading invoices)
INSERT INTO legal_cost_actuals
  (matter_code, category, amount_php, currency, incurred_date, paid, description,
   source, source_doc_id, paid_by, reimbursable, reimburse_basis, recorded_by)
VALUES
  ('MWK-001','rpt_taxes', 775202.00, 'PHP', '2023-09-01', true,
   'RPT amnesty settlement, Heirs of MWK estate parcels (RA 7160 Sec.270)',
   'doc', 290, 'patricia', true, 'art488_tax', 'engine-2026-07-19')
ON CONFLICT DO NOTHING;

-- 5c. Reimbursement view — running total + per-refuser share (2/3 recoverable on preservation/tax)
CREATE OR REPLACE VIEW v_mwk_reimbursement AS
SELECT
  matter_code,
  sum(amount_php) FILTER (WHERE reimbursable)                              AS total_advanced,
  sum(amount_php) FILTER (WHERE reimburse_basis IN ('art488_preservation','art488_tax')) AS preservation_taxes,
  round(sum(amount_php) FILTER (WHERE reimburse_basis IN ('art488_preservation','art488_tax'))/3,2) AS gerry_owes,
  round(sum(amount_php) FILTER (WHERE reimburse_basis IN ('art488_preservation','art488_tax'))/3,2) AS marcia_owes,
  sum(amount_php) FILTER (WHERE reimburse_basis='rule96_guardian')        AS guardian_off_top
FROM legal_cost_actuals
WHERE matter_code='MWK-001'
GROUP BY matter_code;
```

---

## 6. Execute & track — the operating loop
1. **Log every expense** as it happens → one `legal_cost_actuals` row (amount, date, category, `paid_by`, `reimburse_basis`, `or_ref`, `source_doc_id`). A 6-line `add_expense.py` wrapper or a Leo `/expense` command can do this; until then, INSERT per §5b.
2. **Substantiate** — attach the OR/invoice (`source_doc_id`); unsubstantiated advances are weak in an accounting.
3. **Report** — `SELECT * FROM v_mwk_reimbursement` gives total advanced + what Gerry/Marcia each owe + the guardian off-top figure, any time.
4. **Recover** — at CV 6839 collection / first sale, the guardian's accounting (Rule 96) claims reimbursement **off the top**; Gerry's and Marcia's shares are **net of their Art. 488 contributions**.

## 6-bis. Payment sources & the substantiation layer (`ingest_transactions.py`)
Expenses flow through: **Robinhood** (most card spend) · **BofA → GCash** (transfers funding PH spend) ·
**cash**. These records are the **proof-of-payment** that substantiates Colen's statement (the Index of
Receipts) — essential for a reimbursement accounting. **The engine ingests EXPORTS, never live accounts**
(no credential access — see safety boundary):
1. Export CSV from each app (Robinhood / BofA / GCash).
2. `ingest_transactions.py --source robinhood --file rh.csv` → auto-maps date/amount/description into the
   `expense_intake_raw` staging table (idempotent by dedup_key; holds EVERYTHING for reconciliation).
3. `--classify` → first-pass tags rows hitting estate/PH keywords (assessor, RD, BIR, Mercedes, RPT, atty,
   GCash…); review the rest by hand (`UPDATE expense_intake_raw SET estate=true/false WHERE id=…`).
4. `--promote` → moves confirmed estate rows into `legal_cost_actuals` (reimbursable).
- **Cash** has no export trail → relies on receipts/ORs (Colen's Annexes).
- **Reconciliation:** staging totals (estate-tagged) should tie to Colen's statement categories; gaps = a
  missing receipt or an unclaimed advance. This is how the payment records and the statement cross-verify.
- **Security:** `expense_intake_raw` is internal DB only; financial-account data is never exposed outward.

## 7. How this plugs into the revenue map
Reimbursement is a **first charge** applied to every proceeds stream (CV 6839, rent, sales, offense recoveries)
BEFORE the 3-way split — and a **reducer on the refusers' net**. Add a "less: reimbursable advances (first
charge)" line to any distribution calc. Ledger of record: `legal_cost_actuals` / `v_mwk_reimbursement`.

*Internal — draft SQL not executed; amounts to be substantiated from receipts before any accounting is filed.*
