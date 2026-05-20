# PH Tier-One Accounting Gaps — Roadmap to Compliance

> Authored: 2026-05-20
> Status: spec / gap list
> Lands in: LEOLANDTEK_DEPLOYMENT_PLAN v1.5 (financial layer)
> Foundation already built: deploy_113 (accounts/transactions/monthly_overhead/value_extraction_events/asset_valuations/financial_projections/leo_operational_costs), deploy_113b (asset_risks + risk/valuation change events), deploy_115 (title_tax_links), deploy_121 (llm_calls), deploy_170 (tax_years/PIN/ARP arrays), deploy_171 (consideration_price + grantor/grantee/lot + subdivision_plan + area_sqm)

---

## Why this matters

Leo handles money on behalf of clients. PH legal/property practice operates under
strict **BIR (Bureau of Internal Revenue)** rules — Official Receipts vs. Sales
Invoices vs. Acknowledgment Receipts have different deductibility and tax
consequences. Misclassifying expenses can void client reimbursement and trigger
BIR penalties on Landtek. Tier-one Filipino accounting is non-negotiable before
paying clients onboard.

This document enumerates the gaps between the current schema and full PH compliance.

---

## What's already built

| Capability | Status |
|---|---|
| Double-entry-style `transactions` table with debit/credit, category, case_file, matter_code, source_doc_id | ✅ |
| `accounts` chart of accounts (revenue/expense/asset/liability/equity) per landtek + per-client | ✅ |
| `monthly_overhead` recurring overhead per owner/case/category | ✅ |
| `value_extraction_events` for realized value (sales/lease/settlement/recovery/eminent_domain/rent) with `landtek_share` for success fees | ✅ |
| `asset_valuations` PH 4-valuation framework: assessed/zonal/market_price/appraised/acquisition_cost | ✅ |
| `market_observations` (comparables, distressed, zonal, MLS, rumors) | ✅ |
| `financial_projections` (base/optimistic/pessimistic/runway scenarios) | ✅ |
| `leo_operational_costs` + `llm_calls` per-call cost log | ✅ |
| `documents.consideration_price + grantor_seller + grantee_buyer + lot_number + subdivision_plan + area_sqm` (deploy_171) | ✅ |
| `documents.tax_years + property_index_numbers + arp_numbers` (deploy_170) | ✅ |
| `title_tax_links` (TCT ↔ ARP) | ✅ |
| Financial report generators (`financial_report.py`, `pdf_financial_pack.py`) | ✅ |
| QuickBooks MCP connected (added 2026-05-20) | ✅ |

---

## What's still missing for tier-one Filipino accounting

### 1. BIR receipt-type taxonomy (existential)

PH BIR recognizes specific receipt types; misclassification kills deductibility.

| Receipt type | What it is | Deductible? |
|---|---|---|
| **OR** (Official Receipt) | Issued by service-provider after payment | ✅ Yes |
| **SI** (Sales Invoice) | Issued by seller for goods (not services) | ✅ Yes |
| **AR** (Acknowledgment Receipt) | Acknowledges money received, NOT for service rendered | ❌ No — not BIR-recognized for expense deduction |
| **PR** (Provisional Receipt) | Temporary acknowledgment pre-OR | ❌ No — must be replaced by OR |
| **Cash Slip / Order Slip** | Internal sales tracking | ❌ No |
| **Charge Invoice** | Credit invoice before payment | Becomes deductible when paired with OR/SI |

**Schema gap:** add `transactions.receipt_type` (enum: OR / SI / AR / PR / cash_slip / charge_invoice / none) and `transactions.receipt_doc_id` (FK to documents). Without this, every expense Landtek pays on a client's behalf is at risk of being non-reimbursable.

---

### 2. TIN (Taxpayer Identification Number) tracking

Every PH counterparty has a TIN. Required for:
- BIR Form 2307 (Creditable Tax Withheld at Source)
- SAWT (Summary Alphalist of Withholding Tax)
- SLSP (Summary List of Sales and Purchases) — for VAT-registered
- QAP (Quarterly Alphalist of Payees)

**Schema gap:**
```sql
ALTER TABLE entities
  ADD COLUMN IF NOT EXISTS tin text,
  ADD COLUMN IF NOT EXISTS vat_registered boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS vat_number text,
  ADD COLUMN IF NOT EXISTS bir_rdo text;  -- Revenue District Office

CREATE INDEX IF NOT EXISTS entities_tin_idx ON entities(tin) WHERE tin IS NOT NULL;
```

---

### 3. Tax taxonomy per transaction

The existing `category` field is too coarse. PH transactions carry multiple tax dimensions:

**Schema gap:** add to `transactions`:
- `vat_amount numeric(14,2)` — input VAT (for purchases) or output VAT (for sales)
- `vat_rate numeric(5,4)` — typically 0.12 (12%); 0.00 if VAT-exempt; null if non-VAT
- `withholding_tax_amount numeric(14,2)` — EWT withheld
- `withholding_tax_rate numeric(5,4)` — e.g., 0.05 for professional fees, 0.02 for rentals, etc.
- `dst_amount numeric(14,2)` — Documentary Stamp Tax (for deeds, mortgages, leases)
- `cgt_amount numeric(14,2)` — Capital Gains Tax (6% on property sales for individuals)
- `transfer_tax_amount numeric(14,2)` — LGU transfer tax (varies by city)
- `tax_period text` — 'YYYY-MM' or 'YYYY-QN' or 'YYYY'

**Categories should expand to PH-specific:**
- `legal_fee_acceptance`, `legal_fee_retainer`, `legal_fee_appearance`, `legal_fee_success`, `legal_fee_contingency`
- `filing_fee_rtc`, `filing_fee_mtc`, `filing_fee_court_of_appeals`, `filing_fee_supreme_court`
- `filing_fee_rd` (Registry of Deeds), `filing_fee_bir`, `filing_fee_lgu`, `filing_fee_arta`
- `notarial_fee`
- `dst_payment`, `cgt_payment`, `transfer_tax_payment`, `rpt_payment`, `vat_payment`, `ewt_remittance`
- `courier_lbc`, `courier_jrs`, `courier_2go`, `courier_phlpost`
- `transportation_jeepney`, `transportation_taxi`, `transportation_grab`, `transportation_fuel`
- `paralegal_time`, `legal_research_time`
- `meals_client`, `meals_courthouse`
- `lodging_provincial`
- `professional_services_consultant`, `professional_services_appraiser`, `professional_services_surveyor`, `professional_services_investigator`
- `bond_premium`, `subpoena_witness_fee`

---

### 4. PH Books of Accounts (BIR-required)

Every PH-registered business must maintain these books (registered with BIR):

| Book | What it tracks | View name |
|---|---|---|
| Cash Receipts Journal (CRJ) | All cash in | `view_cash_receipts_journal` |
| Cash Disbursements Journal (CDJ) | All cash out | `view_cash_disbursements_journal` |
| General Journal (GJ) | Non-cash entries (adjustments, depreciation, accruals) | `view_general_journal` |
| General Ledger (GL) | Balances per account | `view_general_ledger` |
| Sales Journal (SJ) — *VAT-registered only* | All sales w/ VAT detail | `view_sales_journal` |
| Purchase Journal (PJ) — *VAT-registered only* | All purchases w/ VAT detail | `view_purchase_journal` |

**Implementation:** SQL views derived from `transactions`. Each view sorted chronologically with running balance.

For loose-leaf books-of-accounts approval (preferred over manual), Landtek would need to file BIR Form 1900 once.

---

### 5. BIR form generators

Annual + quarterly + monthly filings. Each form is a derived report from the books:

| Form | Frequency | Source data | Output |
|---|---|---|---|
| **1701** / **1701A** | Annual ITR (individual / corporate) | Net income from GL + tax credits | PDF, BIR eFPS format |
| **1701Q** | Quarterly ITR | Same, by quarter | PDF |
| **2550M** / **2550Q** | Monthly / Quarterly VAT return | Output VAT − Input VAT (from SJ/PJ) | PDF |
| **1601-EQ** | Quarterly EWT remittance | All EWT withheld | PDF + alphalist |
| **2307** | Certificate of Creditable Tax Withheld | Per-payee withholding | PDF per payee |
| **2316** | Certificate of Compensation Payment | Per-employee compensation/tax | PDF per employee |
| **0605** | Annual registration fee | Fixed PHP 500 | PDF |
| **SAWT** | Summary Alphalist of Withholding Tax | All payees with EWT | CSV per BIR format |
| **SLSP** | Summary List of Sales and Purchases | All counterparties VAT-registered | CSV per BIR format |
| **QAP** | Quarterly Alphalist of Payees | All payees in quarter | CSV per BIR format |

**Implementation:** dedicated generator scripts (`bir_form_1701.py`, `bir_form_2550m.py`, etc.) that emit BIR-format PDFs + the required alphalists.

---

### 6. Client trust accounts (separation discipline)

When Landtek holds money **for** a client (e.g., advance for filing fees, settlement received pending disbursement), it's NOT Landtek revenue. It must be:
- Tracked in a separate account (account_type='liability', account_code starts 'CTA-')
- Reconciled when paid out (creates a `client_trust_disbursement` transaction)
- Reportable to the client at any moment

**Schema gap:** add `accounts.is_client_trust boolean DEFAULT false`. Filter trust accounts out of Landtek P&L. Add `view_client_trust_balance` per client.

---

### 7. Reimbursable client expense capture

The `+ Expense` workspace flow (v1.0) writes to a new view of `transactions` with these fields populated:
- `reimbursable boolean DEFAULT true` (already in spec)
- `reimbursed boolean DEFAULT false`
- `reimbursed_tx_id` (the transaction that reconciled it)
- `client_invoice_id` (when included in a billed invoice)
- `receipt_doc_id` (OR/SI evidence)
- `receipt_type` (OR/SI/AR/PR — must be OR or SI for reimbursability)

**Discipline rule:** if `receipt_type IN ('AR','PR','none','cash_slip')` then `reimbursable=false` automatically (with override flag for cases where client agrees to reimburse non-OR expenses).

---

### 8. USD/PHP exchange rate tracking

Diaspora clients (Patricia Zschoche US, future US/AU/CA heirs) pay in USD. Every USD transaction needs:
- BSP (Bangko Sentral ng Pilipinas) reference rate for the transaction date
- Converted PHP amount stored
- Original USD amount preserved

**Schema gap:**
```sql
CREATE TABLE IF NOT EXISTS bsp_reference_rates (
  rate_date date PRIMARY KEY,
  usd_php numeric(8,4) NOT NULL,
  source text DEFAULT 'BSP',  -- BSP | manual | bloomberg
  fetched_at timestamptz DEFAULT now()
);

ALTER TABLE transactions
  ADD COLUMN IF NOT EXISTS original_amount numeric(14,2),
  ADD COLUMN IF NOT EXISTS original_currency text DEFAULT 'PHP',
  ADD COLUMN IF NOT EXISTS exchange_rate numeric(10,6),
  ADD COLUMN IF NOT EXISTS rate_source text;
```

Daily cron pulls BSP rates: `pull_bsp_rates.py`.

---

### 9. PH receipt OCR

PH receipts have a specific format:
- OR number (e.g., "OR No. 1234567")
- TIN of issuer
- VAT registration status ("VAT Reg TIN: 123-456-789-000" or "Non-VAT Reg TIN")
- Date format DD-MM-YYYY (sometimes DD/MM/YYYY, sometimes Month DD, YYYY)
- Itemized lines
- Total + VAT breakdown (12% Output VAT)
- Authorization to Print (ATP) number — for receipts printed by accredited printer
- BIR Permit No.

**Implementation:** `extract_ph_receipt.py` — Gemini Vision with PH receipt prompt. Extracts:
- `receipt_no`
- `issuer_tin`
- `issuer_name`
- `issuer_vat_status`
- `receipt_date`
- `line_items` (jsonb)
- `subtotal`
- `vat_amount`
- `total`
- `atp_no`
- `bir_permit_no`

Feeds directly into the `transactions` table as a fully-typed row.

---

### 10. Estate tax + donor's tax for property transactions

For matters involving MWK estate transfers (when titles eventually re-vest in the heirs), there's estate tax + donor's tax exposure:

- **Estate tax** (Republic Act 10963, TRAIN Law): 6% of net estate above PHP 5M standard deduction
- **Donor's tax**: 6% above PHP 250K per recipient per year
- **CGT on subsequent sales**: 6% of higher of zonal or fair-market value

**Implementation:** add `estate_tax_events` and `donor_tax_events` tables with title_no + tax_due + filed_date + paid_date. Tied into matter timeline for deadline-sentinel.

---

### 11. SEC compliance (if Landtek incorporates)

Currently Landtek operates as Jonathan-owned. If/when it becomes a corporation:
- Annual Audited Financial Statements (AFS) required (SEC + BIR)
- General Information Sheet (GIS) annual filing
- Quarterly Financial Reports for listed/reporting corps

Not a v1.5 problem — flag for v3.0+ when partner-firm + investor work begins.

---

## Build sequence (recommendation)

**Phase 1.5a (foundations) — 1 week:**
1. Schema additions (receipt_type, TIN, VAT/EWT/DST/CGT amounts, currency fields)
2. Backfill existing 166 transactions with PH-tier-one fields (categorize, mark reimbursability)
3. PH receipt OCR script
4. BSP rates daily cron + table

**Phase 1.5b (books + reports) — 1 week:**
5. The 6 books-of-accounts SQL views
6. Client trust account separation
7. Reimbursable-expense reconciliation flow

**Phase 1.5c (BIR forms) — 1 week:**
8. BIR Form 2307 generator (most-used for legal practice)
9. BIR Form 1701Q quarterly ITR
10. BIR Form 2550M monthly VAT (if Landtek becomes VAT-registered)
11. SAWT + SLSP + QAP alphalist generators

**Phase 1.5d (QuickBooks sync) — 3 days:**
12. QuickBooks MCP wiring — Landtek invoices originate in Leo, sync to QB for double-entry firm books
13. QB reconciliation flow when client pays back

---

## Open questions for Jonathan

1. **VAT registration status of Landtek today?** (Threshold: gross PHP 3M annual — below = non-VAT, 3% percentage tax instead. This determines whether VAT-related schema/forms are required.)
2. **Books of accounts type** — manual (paper), loose-leaf (printed), or computerized (BIR-approved system)? Computerized requires BIR pre-approval but is the right long-term answer for Leo.
3. **TIN of Landtek?** Of Jonathan? Of any business entity that bills clients?
4. **Tax accountant on retainer?** If yes, who — and would they want to review/approve the books-of-accounts and form generators before they're used?
5. **Current acceptance fee + retainer model** per client (so Leo can label existing transactions correctly during backfill)?
6. **Don Qi's role re: estate finance** — is he the disbursing officer, the receiving party, or both?

---

## Risk if we skip this

- Client expenses misclassified as non-deductible — Landtek can't bill back, and BIR audit exposure
- BIR penalties for late/incorrect form filing (PHP 1K-50K per form per period)
- Inability to satisfy due diligence from any partner firm, investor, or institutional client — they will ask for AFS + tax compliance proof
- Compliance fail-state during NPC registration prep (v2.0)
