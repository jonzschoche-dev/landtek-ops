# Recovered data sweep, 24 Oct 2026

Files: Drive `_RECOVERED_2026-10-24/` (MWK, Paracale-Inocalla and Telegram_2026-06-07 kept in separate folders) plus `manifest.csv`.
Script: `scripts/recover_email_attachments.py`. It writes no DB rows; ingestion is a separate, matter-aware step.

## Why data went missing
1. **Gmail extractor v1 took PDFs only** (`extract_email_attachments.py`). Photos, screenshots and .docx attachments were counted, then dropped.
2. **The extractor skips emails with `case_file` NULL**, even when `matter_codes` is set.
3. **Telegram media:** `telegram_inbox.media_path` files were deleted from `vault_media/`, but `media_file_id` survives. Files can be re-downloaded through the Bot API `getFile`.
4. **Vault register:** CORR-007 through CORR-017 were logged as physical masters with no scan; CORR-015 had been bound to the wrong scan (doc 814).
5. **Chat bridges** (Messenger, WhatsApp, Viber) never stored media. Nothing is recoverable server-side; those files exist only on the phone.

## Results
- **Telegram:** 4 of 4 photos from 7 Jun 2026 recovered.
  - inbox 25 = CORR-007, the 21 Jun 2025 letter to Salvador signed "Received". Since replaced by Jonathan's full 2-page scan, doc 1002.
  - inbox 5 = the 10 Jun 2025 letter to Judge Dizon (CV 6839).
  - inbox 15 and 49 = the 1 Oct 2025 letter to Mayor Pajarillo.
- **Gmail:**
  - 543 candidate attachments (≥30 KB).
  - 429 were already in the corpus under another email (hash match). This includes Patricia's SPA (Fwd: spa, Jun 2026) and the DILG CamNorte response of 7 Sep 2026.
  - 58 newly saved: 44 in the MWK folder, 14 Paracale-Inocalla.
  - 8 are GONE from both mailboxes:
    - REPORT-OF-BIRTH-FILLED.pdf ×4 (18 May 2026)
    - image.png ×3 (ARTA-1891, May 2026)
    - the Milla interim suspension request (that one is in the corpus as doc 1240)
- **Of the MWK-folder files:**
  - About 25 are personal family photos (2016 to 2024, St Agnes, "Battle of Manila"). The bucket rule matched the family addresses; they are not case material.
  - Some are signature images and logos (DOF seal, Land Bank banner). The letters themselves are in the email bodies, already ingested.
  - Possibly case-relevant (review before ingesting):
    - em424: Colen Ibasco, "2023 bills tax payment receipts" (3 images)
    - em4078: receipt for consultation (Feb 2026)
    - em95599: RPT paid under protest, OR request screenshot (Jun 2026)
    - em109495, em117463, em119666, em130079: ABLAW billing and invoices AB-439, AB-463, AB-469 (MWK guardianship)
    - em147549: avaslaw (Agcaoili office), "List of pending documents", 2 screenshots (7 Oct 2026)
- **Paracale-Inocalla (keep separate):**
  - PARACALE GOLD CORPORATION.docx ×2
  - Sports Arnis rules, SAL1 Trainer, SApolicy, Revised Rules
  - Letter to Josua Ongcol
  - survey-map photo IMG_9786
  - poster images

## Not done (needs Jonathan's go)
- Ingesting the case-relevant files above into `documents` (matter assignment by content; Paracale stays Paracale).
- Fixing the extractor so v2 takes non-PDF attachments and `matter_codes`-only emails going forward (a product-hardener task).
