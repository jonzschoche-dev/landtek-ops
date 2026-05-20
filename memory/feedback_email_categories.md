---
name: feedback-email-categories
description: "Jonathan's email inbox carries multiple categories that Leo must auto-classify and file appropriately: legal correspondence → case docs; bills/invoices → financial expense ledger + recurring overhead; receipts → transactions; personal/marketing → skip. Each category has its own downstream destination."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan (2026-05-16): "i also hav bills going to that email"**

So Leo's Gmail watcher must classify each inbound message into at least these buckets, and route each to the right place:

| Category | Detection signals | Downstream action |
|---|---|---|
| `legal_correspondence` | Counsel/court/agency sender, case# / TCT / docket in subject/body, attachments are pleadings | `documents` row + case_file via case_keywords; attach to gmail_messages.document_id |
| `bill` (unpaid) | "invoice", "bill", "statement", "amount due", "payment due by", vendor (PLDT, Globe, Meralco, AWS, Anthropic, GoDaddy, etc.) | `pending_bills` row + flag for monthly_overhead if recurring |
| `receipt` (post-payment) | "payment received", "receipt", "OR No.", "transaction confirmed", "your subscription was renewed" | `transactions` row (debit) + link to source_email_id |
| `bank_statement` | Bank issuer (BPI, BDO, RCBC, Security Bank), monthly statement | parse balance changes; flag for AR reconciliation |
| `client_inquiry` | from a non-internal address asking about services / status | route into onboarding state machine via /api/channel/email |
| `system_alert` | GitHub, AWS, Anthropic, DigitalOcean operational alerts | log only, no action unless severity high |
| `personal` | Family/friends, non-work | skip but log |
| `promotional` | Newsletters, marketing | skip + label |

**Per-category schema needs:**

1. `gmail_messages.category` — enum text
2. `gmail_messages.classification_confidence` real
3. `gmail_messages.bill_metadata` jsonb (vendor, amount, currency, due_date, account_no, billing_period, is_recurring)
4. `gmail_messages.receipt_metadata` jsonb (or_no, amount, paid_to, paid_date)
5. New table `pending_bills` (id, gmail_message_id, vendor, amount_due, due_date, status, paid_via_tx_id)
6. Add `source_email_id` column to `transactions` and `monthly_overhead`

**Bill → monthly_overhead promotion:**

When the same vendor sends ≥2 bills in 60 days, classify as recurring. Auto-create/update `monthly_overhead` row with `source_email_ids[]` and average amount. This is how Landtek's REAL monthly burn replaces placeholder estimates.

**Bill → transactions promotion:**

When a "receipt" email confirms payment for a previously-flagged "bill", link them: `pending_bills.paid_via_tx_id` ← the matching transaction.

**Telegram digest changes:**

Daily digest must include:
- New bills (with due date) — operator action: pay/dispute/file
- New receipts (confirms what's already been paid)
- New legal correspondence (attaches to active matters)

**How to apply:**

1. Build `gmail_watcher.py` with category classifier (regex + Haiku for ambiguous).
2. ALTER schema for category + bill/receipt metadata + source_email_id.
3. New table `pending_bills` + cron job to surface due-this-week bills.
4. systemd timer every 15 min for the watcher.
5. Update `/finance` and `pdf_financial_pack.py` to include "Pending bills" + "Bills paid this period" sections.

Related: [[feedback-financial-planning-layer]], [[feedback-financial-urgency]], [[feedback-leo-mission-agency]] (Leo proactively flags bills before due).
