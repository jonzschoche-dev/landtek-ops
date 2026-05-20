---
name: feedback-legal-act-validity-scrutiny
description: "Every claim of a legal act (donation, sale, conveyance, transfer, revocation, etc.) must be scrutinized for the validity components required by PH law; doc presence alone never equals fact"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** A document titled "Deed of X" does NOT, by itself, establish that the legal act X occurred validly. Leo must scrutinize each legal-act claim against the components PH law requires for validity — and surface what's present, what's absent, and what would upgrade the claim to evidentiary-grade.

**Why:** Jonathan, 2026-05-16: *"the system is hallucinating about the donation, it needs to be objective and understand the validity of a donation. A document or listing in itself cannot be construed as a donation. It must have sufficient backup data. This is an issue, all data needs to be scrutinized."*

I treated doc#279 (titled "Deed of Donation, 1953") as proof that a donation occurred. That's the same failure pattern as the May-13 pretrial bug — trusting a label without testing the underlying claim. A PH donation of real property requires multiple components ALL present for legal validity (Civil Code Arts. 745-749, 712, 1318); any missing component leaves the donation imperfect or void. Same logic applies to every other legal act in our corpus.

**How to apply — per-act-type validity rubrics:**

**DONATION of real property:**
- [ ] Public instrument (notarized, with notary block: doc/page/book/series)
- [ ] Acceptance by donee in SAME instrument or separate public instrument (Art. 749)
- [ ] If separate, donor must be notified of acceptance during their lifetime (Art. 749 para 2)
- [ ] Donor had capacity at execution (alive, of age, not interdicted, owned the property)
- [ ] Donee had legal personality to accept (e.g., for LGU — Sangguniang Bayan Resolution + Mayor's authority)
- [ ] Property is alienable
- [ ] Donor's Tax paid + BIR CAR (Certificate Authorizing Registration) issued
- [ ] Registration with the Registry of Deeds (binding against 3rd parties — Art. 709)
- [ ] Annotation/cancellation on the source title appropriate to the transfer
- [ ] Witnesses (2 minimum)
- [ ] No void cause (Art. 1318: consent, object, cause)

**DEED OF ABSOLUTE SALE of real property:**
- [ ] Public instrument
- [ ] Consideration (price) stated and paid (or installment terms)
- [ ] Notarization
- [ ] Seller's capacity + ownership at time of sale
- [ ] If through Attorney-in-Fact: SPA must exist, be valid at time of execution, and authorize the specific act
- [ ] Buyer's capacity (esp. foreign-ownership restrictions per Art. XII §7 Constitution)
- [ ] BIR CGT / DST paid + CAR
- [ ] Transfer tax paid (local)
- [ ] Registration with RD + new title issuance

**REVOCATION of SPA:**
- [ ] Executed in writing (Art. 1920 if SPA was written)
- [ ] Notarized
- [ ] Service / notice to the agent (Art. 1921 — if 3rd party deals in good faith without notice, revocation doesn't bind them)
- [ ] Annotation on the source authority instrument (if the original SPA was annotated)
- [ ] Capacity of revocator (alive, of sound mind)

**JUDICIAL FILING:**
- [ ] Filed-stamp from court Receiving Section (date + time)
- [ ] Docket number assigned
- [ ] Filing fee receipts
- [ ] Service on opposing party + proof of service

**TITLE TRANSFER (TCT-level):**
- [ ] Source instrument (deed/order/decree) verified valid (per its act-type rubric above)
- [ ] BIR CAR + Transfer Tax + Registration Fee paid
- [ ] New TCT issued + old TCT cancelled in RD's books
- [ ] Memorandum of Encumbrances annotation on the new title showing source
- [ ] No double-titling / overlapping title for the same parcel

**Implementation:**

1. Every legal-fact claim from Leo (in briefs, reports, posture documents, timelines) must include a **validity status block** — "ASSERTED in doc#X" or "VERIFIED across N components" — not a bare statement of fact.

2. Meta-agent invariant added: any matter that references a legal act (donation/sale/revocation) without the validity components having been audited gets flagged.

3. For the corpus already ingested, build a `legal_act_audit.py` that runs each rubric against the relevant docs and produces a validity scorecard per act.

4. Source-quote discipline (already in [[feedback_no_invented_schemas]] and the tct_v3_canonical contract) extends to every act: every component check must cite a doc + quote, not just doc presence.

**Examples I got wrong (2026-05-16 audit):**
- doc#279 "Deed of Donation" — treated as proof of donation. Actual scrutiny: has notary block + acceptance + signatures + witnesses, but registration + donor's tax + BIR CAR NOT visible in text. Need to find the RD entry annotation and BIR CAR to confirm the donation took effect.
- doc#329 "1992-03-19 Special Power of Attorney" — I haven't audited validity components yet.
- doc#409 (the 2016 Deed of Sale Cesar → Rosalina Hansol) — I haven't audited validity components yet. CRITICAL given this is the centerpiece of the void-instrument theory.

**Linked memories:**
- [[feedback_no_invented_schemas]] — every fact carries a provenance_level
- [[feedback_execution_status_required]] — drafts cannot be cited
- [[feedback_legal_status_awareness]] — stage trumps date; rigor over labels
- [[project_title_origins_mwk]] — the title chain, now requiring validity-component scrutiny
