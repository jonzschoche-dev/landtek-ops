# Coverage Audit — 2026-05-17

_Bible architecture, Layer C. Source-row → client_history coverage._


## Client: `Owner`
- **documents**: 1/6 in bible (17%) · no_date=5 · no_case_file=0 · **scanner_skipped=0**
- **transactions**: 2/2 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**

## Client: `Paracale-001`
- **documents**: 37/56 in bible (66%) · no_date=19 · no_case_file=0 · **scanner_skipped=0**
- **gmail_messages**: 29/29 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**
- **transactions**: 13/13 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**

## Client: `PENDING_TRIAGE`

## Client: `MWK-001`
- **documents**: 362/651 in bible (56%) · no_date=289 · no_case_file=0 · **scanner_skipped=0**
- **gmail_messages**: 285/285 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**
- **transactions**: 151/151 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**
- **case_deadlines**: 3/3 in bible (100%) · no_date=0 · no_case_file=0 · **scanner_skipped=0**
- **title_transfers**: 10/41 in bible (24%) · no_date=31 · no_case_file=0 · **scanner_skipped=0**

---
## Summary
- **Total missing rows:** 344
- **Upstream gaps** (no date / no case_file — extraction backlog): 344
- **Scanner-skipped** (real gaps — all upstream OK but bible empty): 0

✅ **No real scanner gaps.** All missing rows are upstream backlog (date or case_file extraction needed).

## Top backlog items (run date-extraction or case-file backfill next)
  - `MWK-001/documents#72` (upstream_no_date) — 1991_special_power_of_attorney.pdf
  - `MWK-001/documents#72` (upstream_no_date) — 1991_special_power_of_attorney.pdf
  - `MWK-001/documents#73` (upstream_no_date) — YYYY-MM-DD_heirs_of_mary_worrick_keesey_petition.pdf
  - `MWK-001/documents#73` (upstream_no_date) — YYYY-MM-DD_heirs_of_mary_worrick_keesey_petition.pdf
  - `MWK-001/documents#78` (upstream_no_date) — unknown_document.pdf
  - `MWK-001/documents#78` (upstream_no_date) — unknown_document.pdf
  - `MWK-001/documents#82` (upstream_no_date) — 1991-08-33_special_power_of_attorney.pdf
  - `MWK-001/documents#82` (upstream_no_date) — 1991-08-33_special_power_of_attorney.pdf
  - `MWK-001/documents#88` (upstream_no_date) — YYYY-MM-DD_TCT-4544_San_Vicente.pdf
  - `MWK-001/documents#88` (upstream_no_date) — YYYY-MM-DD_TCT-4544_San_Vicente.pdf
  - `MWK-001/documents#103` (upstream_no_date) — YYYY-MM-DD_TCT-4454_San_Vicente.pdf
  - `MWK-001/documents#103` (upstream_no_date) — YYYY-MM-DD_TCT-4454_San_Vicente.pdf
  - `MWK-001/documents#201` (upstream_no_date) — YYYY-MM-DD_deed_of_donation_mercedes_roads.pdf
  - `MWK-001/documents#201` (upstream_no_date) — YYYY-MM-DD_deed_of_donation_mercedes_roads.pdf
  - `MWK-001/documents#215` (upstream_no_date) — null_receipt.pdf
  - `MWK-001/documents#215` (upstream_no_date) — null_receipt.pdf
  - `MWK-001/documents#226` (upstream_no_date) — 2024_tax_declaration_Mary_Worrick_Keesey.pdf
  - `MWK-001/documents#226` (upstream_no_date) — 2024_tax_declaration_Mary_Worrick_Keesey.pdf
  - `MWK-001/documents#247` (upstream_no_date) — null_information_request_form.pdf
  - `MWK-001/documents#247` (upstream_no_date) — null_information_request_form.pdf