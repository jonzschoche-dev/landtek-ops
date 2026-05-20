---
name: feedback-execution-status-required
description: Leo must distinguish documents by execution state — filed/notarized/executed have legal force; emails are proof of communication; drafts have no legal force. Citing a draft as fact is a hallucination.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6d129aad-aef2-4031-8003-fa0de0a89100
---

**Jonathan: "LEO should be able to decipher a filed and notarized or email that's been sent and a draft that's yet to be executed"** (2026-05-16, during truth-negotiator design discussion).

This is a first-class axis on every document. The schema column `documents.execution_status` already exists — was never populated. All 685 docs are NULL.

**The taxonomy Leo must apply:**

| status | legal effect | citation rule |
|---|---|---|
| `executed_notarized` | full legal force (notary stamp + Doc/Book/Page/Series block) | citable as fact |
| `executed_filed` | binding pleading; has court/agency filing stamp + docket | citable as fact |
| `executed_signed_only` | private signed instrument, no notarization | citable as fact (with caveat) |
| `government_issued` | TCT, OCT, tax receipt, court order, ARTA, RD certification | citable as fact |
| `email_sent` | proof of communication occurred at a timestamp | citable as fact-of-communication, NOT as truth-of-content |
| `email_received` | inbound communication | same as email_sent |
| `draft_unsigned` | no legal force; reflects intent only | NEVER cited as fact; only as "what was proposed" |
| `template` | blank form / boilerplate | NOT citable |
| `unknown` | not yet classified | NOT citable |

**Why:** A draft Deed of Sale is not a Deed of Sale. A draft Complaint is not a filing. Leo treating them the same is exactly the hallucination class Jonathan has flagged repeatedly. Mistaking a draft for an executed instrument could lead to advising on a transaction that legally never happened.

**How to apply:**

1. `truth_negotiator` must read `execution_status` for every cited document. Drafts cannot back a factual claim.
2. The output `[V]` tag should be extended: `[V·N]` notarized, `[V·F]` filed, `[V·E]` email, `[V·D]` draft-only (caveat shown).
3. Classification populates two fields:
   - `execution_status` (enum text)
   - `execution_metadata` jsonb — for notarized docs: `{notary, doc_no, book_no, page_no, series}`; for filed: `{court, docket_no, filing_date, stamp_seen}`; for emails: `{from, to, sent_at, subject}`.
4. Heuristic detectors get us 80%; Claude Haiku call confirms ambiguous ones.

Related: [[feedback-leo-must-self-research]], [[feedback-information-is-gold]].
