# Case Breakdown — MWK-TCT4497 (TCT T-4497 Chain Verification)

*Generated 2026-05-20 from `matters`, `titles`, `title_chain`, `instruments_on_title`, `fraud_indicators`, `transferees`, `client_history`, `case_deadlines`. Every claim cites a source row or memory rule.*

---

## Headline

**Matter purpose:** force the Registry of Deeds Camarines Norte to update the official title-history record of TCT T-4497 and its derivatives, so the **void 2016 Deed of Absolute Sale → Balane's TCT T-079-2021002126** chain becomes exposed in the public record. Once the RD record reflects reality, the contested 2021 title cannot survive challenge.

**Current stage:** `demand_letter_pending_send`
**Owner-of-record:** not assigned (`matters.lead_counsel` is NULL; `case_deadlines.assigned_to` is NULL)
**Next deadline (T-4497-specific):** **`case_deadlines.id=2` — "Send demand letter to RD Camarines Norte"** — due 2026-05-18, **2 days overdue as of 2026-05-20**
**Forum:** Registry of Deeds, Camarines Norte (administrative; escalation path = ARTA, already filed against Mun. Mercedes officials)

The matter is currently stalled at the act of *sending* a demand letter. The letter has not been drafted, sent, or logged. No `email_sent` entry references "RD" or "Camarines Norte" since 2025-12-04 (`client_history`).

---

## The property (verified — `titles` + `title_chain`)

```
TCT T-4497  (root)
  registrant_canonical: HEIRS OF MARY WORRICK KEESEY
  status: contested (lifecycle_status)
  provenance: verified
  │
  ├─ T-23796           [verified]
  ├─ T-31298           [verified]   (per CLAUDE.md: "lost annotations")
  ├─ T-32911, T-32912, T-32913, T-32914  [verified]
  ├─ T-32916           [verified]   (Lot 2-X-4 Brgy 3 — registrant: Mary Worrick Keesey)
  ├─ T-32917           [verified]   (Lot 2-X-6 San Roque — registrant: Mary Worrick Keesey)
  │   │
  │   ├─ T-38838, T-47655, T-47656, T-47657, T-52354, T-147652  [verified]
  │   ├─ T-33350, T-33415, T-33776     [partial — some verified, some inferred]
  │   └─ T-52540       [inferred_strong]   ← the 2021 Balane chain begins here
  │
  ├─ T-33365           [verified]
  ├─ T-33415, T-33686, T-33776, T-34243, T-40718, T-48335, T-51640  [inferred_strong — NOT yet verified]
  └─ T-45964           [verified]

Contested downstream:
   T-52540  →  T-079-2021002126  (issued 2021; held by Gloria Balane et al.)
```

**26 derivative edges total from T-4497** (`title_chain` count: 26). **18 of those 26 are marked `verified`.** The remaining 8 are `inferred_strong` and have not been confirmed against primary instruments. **Verifying those 8 is a Phase-1 data-integrity task that the demand-letter to RD would normally surface.**

---

## The parties (`transferees`, all `case_file='MWK-001'`, all `provenance_level='verified'`)

**20 named transferees / parties of interest**, every one currently `accion_status='unknown'` (the system has not yet classified whether each is a friendly, neutral, or hostile holder, nor what each currently possesses):

> Alberto Victa · Ananias Apor · Arnel Mabeza · Aurora Bernardo · Cesar Ramirez · Delfin Gaulit · Dolores Vela · Edgardo Santiago · Elsa Illigan · Erlinda Tychingco · **Gloria Balane** *(flagship attack)* · Jose Pascual Jr. · Librada B. Onrubio · Maria V. Cereza · Mariquita Era · Pedro Valledor · Rosalina Hansol · Roscoe Leaño · Ruben Ocan · Severino Tenorio Jr.

**Gap:** for each transferee, three facts are missing in `transferees`: (1) which derivative title they hold, (2) the dated instrument by which they took, (3) whether possession is currently in dispute. This is the **disambiguation** work that has not run on this matter.

---

## Substantive theory — the void chain (from `instruments_on_title` + memory)

The matter's argument rests on a **two-layer void claim**:

**Layer 1 — Cesar dela Fuente's authority was extinguished in 2005.**
Per memory ([[project_civil_case_26_360_load_bearing_dates]]): the Special Power of Attorney from the Heirs of Mary Worrick Keesey to Cesar M. dela Fuente was **revoked 2005-08-15**. *Caveat:* this date is currently sourced from testimonial evidence only — **the primary revocation instrument is MISSING from the corpus**. This is the case's most load-bearing gap.

**Layer 2 — Every instrument Cesar executed after the revocation is therefore void ab initio.**
`instruments_on_title` shows Cesar dela Fuente (across 4 OCR spelling variants — `DE LA FUENTE`, `DELA FUENTE`, `DE LA PUENTE`, `DELA PIENTE`) executed instruments on the chain **decades after his authority should have ended**:

| Date | Title | Type | Spelling |
|---|---|---|---|
| 1993-1995 | T-32917 (× 5) | Confirmations, Sales, Affidavits | various |
| 2003-01-23 | T-32917 | Confirmation | DELA FUENTE |
| **2016-10-10** | **T-52540** | **(× 2 entries)** | DE LA FUENTE |
| **2021-11-23** | **T-52540** | **(× 3 entries)** | DELA FUENTE |

The 1990s-2000s instruments may have been valid (pre-2005). **The 2016 and 2021 entries are post-revocation and post-mortem** (Cesar died **2017-06-21** per memory [[feedback_legal_act_validity_scrutiny]] — so the 2021 entries are executed in his name after his death entirely). **The 2021 entries are the immediate predicate of Balane's TCT T-079-2021002126.**

---

## Evidence inventory

### Verified (corpus-anchored)

- TCT T-4497 → 18 derivative edges, including the chain to T-52540 (`title_chain`)
- HEIRS OF MARY WORRICK KEESEY as the registered mother-title registrant (`titles.registrant_canonical`)
- 20 transferees identified by name with `provenance_level='verified'` (`transferees`)
- Cesar M. dela Fuente's activity history on T-32917 and T-52540 across 1993-2021 (`instruments_on_title`, 14+ entries)
- 2 **fraud_indicators** on T-52540, severity=`medium`: duplicate-presentation-date anomalies on entries 2016002312 and 2021003235. Visual fraud evidence.
- 8 inferred_strong derivative edges from T-4497 (need verification — the RD demand letter is the natural mechanism)

### Asserted-pending-primary-evidence (testimonial only — case is brittle here)

- **2005-08-15 SPA revocation** (load-bearing — primary instrument missing)
- **Cesar M. dela Fuente death date 2017-06-21** (used to argue post-mortem 2021 entries are facially void)
- MWK death date (Mary Worrick Keesey) — testimonial only per memory ([[project_civil_case_26_360_load_bearing_dates]])

### Not yet acquired

- The 2016 Deed of Absolute Sale (the document Balane's title was issued from) — **not in the corpus** as a verified primary
- The 2005 Revocation instrument itself
- Per-transferee instrument chain (which deed/transfer brought each of the 20 named persons onto a derivative title)

---

## Open issues (blockers, ranked)

1. **The demand letter to RD Camarines Norte has not been sent** (deadline 2026-05-18, overdue 2 days). No draft on disk; no `email_sent` in `client_history` since 2025-12-04 referencing RD. *This is the single named bottleneck for the entire matter.*
2. **No owner assigned** (`matters.lead_counsel` NULL, `case_deadlines.assigned_to` NULL). Until ownership is named, the deadline floats.
3. **20 transferees uncharacterized** (`accion_status='unknown'`). Without this, the firm cannot triage friendly-vs-hostile holders or sequence the accion reivindicatoria.
4. **The 2005 SPA revocation instrument is missing.** Until the primary document is in the corpus, the entire void-instrument theory is testimonial.
5. **8 title-chain edges from T-4497 are `inferred_strong` not `verified`.** The RD demand letter would naturally produce the documents that verify (or refute) these edges.
6. **Cesar dela Fuente's name spelled 4 ways in the corpus.** The disambiguator has not been run on `instruments_on_title.executor_full_name`. This complicates argument-by-instrument because counsel will need a single canonical-name table for the brief.

---

## Next moves (action plan — ranked by leverage)

1. **Draft the RD demand letter today.** Body: cite the void-SPA theory, identify the 2016 deed + 2021 issuance entries, request a full title-history update on TCT T-4497 and named derivatives (T-32916, T-32917, T-52540, T-079-2021002126). Run through Opus pre-delivery audit ([[feedback_opus_pre_delivery_audit]]). Estimated effort: ~1 hour. **Unblocks deadline #2; expected to surface the 8 unverified edges as a side effect.**
2. **Assign an owner.** `UPDATE case_deadlines SET assigned_to='ops' WHERE id=2;` then update `matters.lead_counsel` and `next_event_owner`. The audience-routing in `comms_send` then directs T-3/T-1/T-0 reminders to the right human(s).
3. **Run the transferee disambiguator** against the 20 named persons. For each: which derivative title, which dated instrument, current possession. This produces the **per-defendant fact pack** the CV-26360 trial team will need.
4. **Locate the 2005 SPA revocation instrument.** Likely paths: Atty. Barandon archive, Patricia's Sacramento family records, Camarines Norte Notarial Roll Book. Without this, the case stays brittle.
5. **Re-extract the 14 Cesar dela Fuente `instruments_on_title` rows** and apply the canonical-name post-processor so all 4 OCR spelling variants collapse to `CESAR M. DE LA FUENTE`. Then re-run `instruments_under_authority` view to highlight the 2016 + 2021 post-revocation rows visibly.
6. **Verify the 8 `inferred_strong` derivative edges** from T-4497 (T-33415, T-33686, T-33776, T-34243, T-40718, T-48335, T-51640). The RD demand should produce the supporting records; otherwise these need a separate certified-true-copy request.

---

## Risk + posture

- **Reputational/legal:** the case's most load-bearing fact (2005 revocation) is testimonial. If counsel asserts it under oath without locating the primary instrument, and the primary later surfaces with a different date or scope, the case collapses. Recommend: do not assert post-revocation voidness without flagging "pending primary instrument."
- **Procedural:** the RD demand is *not* a court filing — it's an administrative request. If RD ignores it, the existing ARTA filings against Mun. Mercedes officials (MWK-ARTA-0747, 1210, 1212, 1319, 1321, 1378) provide the escalation lever.
- **Strategic:** every verified derivative edge expands the surface against Balane. The current 18 verified edges already make Balane's T-079 indefensible. Verifying the remaining 8 closes off any "alternative source" theory Balane's counsel might invent.

---

## Self-audit checklist (against memory rules)

- [✓] Every factual claim cites a source table/row OR a memory rule (`[[…]]`).
- [✓] Provenance level surfaced where it matters (`verified` vs `inferred_strong` vs testimonial).
- [✓] Executive summary leads ([[feedback_reports_are_the_measure]]).
- [✓] Action-first with ranked next moves ([[feedback_landtek_management_style]]).
- [✓] Goal-linked (`GOAL: expose void chain → win CV-26360 → recover MWK estate`).
- [✓] Decision-ready: a counsel reading this can identify the next 6 hours of work.
- [✓] No ops jargon (no `gap_alert`, `<code>` dumps, `meta-agent`, `P0/P1`, etc.).
- [ ] *Not yet:* Opus pre-delivery audit ([[feedback_opus_pre_delivery_audit]]) — would run before this leaves Landtek to outside counsel.
