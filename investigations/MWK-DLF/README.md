# MWK-DLF-VOID — de la Fuente void-transfer recovery investigation

**Matter code:** `MWK-DLF-VOID` (sub-matter of MWK-001) · **Opened:** 2026-07-01 · **Status:** active / investigation
**Siblings:** `MWK-TCT4497` (RD administrative), `MWK-LGU-RECOVERY` (1995 Mercedes donation), Civil Case 26-360 (Balane — the in-suit test case).

This is the granular investigation into the transfers made off the MWK estate under the **limited,
negotiate-only, later-revoked de la Fuente Special Power of Attorney.** It has its own corpus,
mapping, and correspondence directive — all backed by the live database, not just these docs.

## The theory in one paragraph
Cesar M. de la Fuente held a **genuine** 1992 SPA from the three MWK heirs — but it was authority
**to *negotiate* a sale only, not to sell** (PE-170453). That authority **lapsed ~1995** (his own
tax payments on the estate stop then) and was **registrably revoked 15-Aug-2005**. Deeds of sale
nonetheless kept issuing across Lot 2-X-6 (T-32917) through 2021 — the 2016 deed built the Balane
chain (TCT 079-2021002126). The receipts were signed by **Salvador "Von" de la Fuente, who was never
named in the SPA.** The principal **never received a peso.** The Register of Deeds itself certifies
(doc:353) the underlying de la Fuente-era deeds are **not on file.** → the conveyances are void; the
derivative titles are cancellable; reconveyance is imprescriptible; the agent must account.

## Objective — Balane is the wedge, not the goal
The **goal is estate-wide recovery** of the T-32917 (Lot 2-X-6) branch conveyed under the void
de la Fuente authority. **Civil Case 26-360 (Balane) is the test case / wedge / evidence-builder** —
its lot is one C-1 sub-lot five subdivision levels below the mother title. It is central only as the
*strongest, already-filed vehicle* to establish the void-authority theory; it must not be mistaken
for the objective. When 26-360 has done its job, priority shifts to the dark cluster (~50,000 sqm)
and the Tier-2/3 lots — that is where the acreage and value actually sit.

## 26-360 scope & reach — what it can and cannot carry
Confirmed against the filed prayer (doc:446 / doc:424):
- ✅ **Right theory pleaded** — the Balane deed is attacked as void "for being entered into without
  the consent, authority and knowledge of the Plaintiff and the other co-owners" — i.e., the
  **estate-wide authority defect**, not a Balane-specific quirk.
- ✅ **Broader than the sliver** — the prayer asks to **reinstate TCT T-52540** (parent of both C-1
  Balane and C-2 Hoppe) to the heirs → recovers the whole 2-X-6-I-4-C parcel, plus ejectment + accounting.
- ❌ **But its reach is capped three ways:**
  1. **Parties** — only the Balane defendants (+ "Cesar de la Fuente" as deed signatory) are named. The
     other transferees (Santiago, Leaño, Dean, Capistrano, the cluster) are **not parties → no res
     judicata against them.** A win doesn't bind them.
  2. **Forum** — MTC Mercedes, **Summary Procedure**. A favorable ruling is a persuasive record, **not
     binding precedent** for the branch.
  3. **Relief** — voids only the Balane deed + T-52540 chain; it does not touch the other lots.

**Implication (analysis, for counsel):** estate-wide recovery needs a **separate, broader RTC action**
(declaration of nullity + reconveyance + accounting) that **names the de la Fuente side** (Cesar's
estate + Salvador "Von") **and all transferees**, and prays to void **all** de la Fuente conveyances
and cancel **all** derivative titles. 26-360's role is to prove the theory, build the record, recover
the C parent — and set up that broader action. This whole investigation is the preparation for it.
→ **Outline of that end-vehicle:** `RTC_COMPLAINT_OUTLINE.md` (parties, causes, global prayer, and the
procedural decisions counsel must resolve — incl. why it is blocked on identifying the Doe cluster).

## Where everything lives (query the live DB — this is the source of truth)
```sql
-- the matter
SELECT * FROM matters WHERE matter_code='MWK-DLF-VOID';
-- the corpus (86 docs, role-tagged in note as [title_face]/[spa]/[revocation]/[rd_certification]/[admission]/[contested]/[target_t3]/[tax_dec]/[pleading]/...)
SELECT relation_kind, note FROM document_matter_links WHERE matter_code='MWK-DLF-VOID' ORDER BY note;
-- the mapping
SELECT * FROM matter_parties      WHERE matter_code='MWK-DLF-VOID';   -- 13 parties
SELECT * FROM matter_causes       WHERE matter_code='MWK-DLF-VOID';   -- 5 causes of action
SELECT * FROM title_matter_links  WHERE matter_code='MWK-DLF-VOID';   -- 17 titles
SELECT la.citation, la.holding FROM matter_authorities ma JOIN legal_authorities la ON la.id=ma.authority_id WHERE ma.matter_code='MWK-DLF-VOID';  -- 4 cases
-- the correspondence tracker + directive state
SELECT claimed_date, author, addressee, subject, delivery_status, gap_flag FROM correspondence_events WHERE matter_code='MWK-DLF-VOID' ORDER BY delivery_status, claimed_date;
```

## Analytical work products (drafts/)
- `drafts/t4497_transaction_ledger_2026-06-30.md` — every transaction on T-4497 (the title face)
- `drafts/delafuente_spa_recovery_analysis_2026-06-30.md` — SPA personality, termination-date theory, PH law
- `drafts/branch2_recovery_roster_2026-07-01.md` — the tiered recovery roster for the T-32917 branch
- `drafts/followup_tracker_complaint_and_ROD_2026-06-30.md` — complaint version chain + RD follow-up

## Granular map — the T-32917 (Lot 2-X-6, 85,149 sqm) branch

```
T-4497  (MWK mother title — full transaction ledger on the title face, doc:39)
  └─ T-32917  Lot 2-X-6  (de la Fuente Psd-256008 re-subdivision)
       ├─ T-52540 (cancelled) ─ 2016 deed ─▶ 079-2021002126  Gloria Balane   ◀ IN SUIT (CV 26-360)   [Tier 1]
       │                                     079-2021002127  Geraldine Hoppe  ◀ family (RETAIN)
       ├─ T-33415  Edgardo Santiago   ◀ Tier 3 (RD: no deed on file, PE-172432)
       ├─ T-33776  Roscoe Leaño       ◀ Tier 3 (RD: no deed on file, PE-174242)
       ├─ T-34243  Erlinda Tychingco  ◀ Tier 4 (1994 deed — scope theory)
       ├─ T-33686  Jose Pascual Jr.   ◀ Tier 4
       ├─ T-33350  Elena Vergara      ◀ Tier 4
       ├─ (portion) Ruben P. Dean     ◀ Tier 2 (1997 deed — post-lapse, PE-214781)
       ├─ (portion) Cristina Capistrano ◀ Tier 2 (2003 deed — post-lapse, PE-261974)
       ├─ (portion) Municipality of Mercedes ◀ 1995 donation → MWK-LGU-RECOVERY
       ├─ T-38838  Heirs of MWK       ◀ RETAIN (32,448 sqm, still estate)
       └─ T-47655 / T-47656 / T-47657 / T-48336 / T-69404  ◀ ⚠️ HOLDER UNRESOLVED (active: T-47655 7,186 + T-48336 14,817 + T-69404 ?; T-47656/47657 superseded — areas don't reconcile, need CTCs)
```

Recovery strength rises the later the deed sits past the SPA's end (1995 lapse → 2005 registered revocation).

## Open gaps (also tracked as `planned` correspondence)
1. **conjugal-partnership cluster** (T-47655/56/57/48336/69404) — both HOLDER and true area unresolved (OCR caught only the blank form; active parcels ≈ 22,000 sqm + T-69404, but the supersession/areas don't reconcile). Needs clean RD CTCs.
2. **Tier-2 primary deeds** (Dean 1997, Capistrano 2003) — not in corpus; RD request / non-availability cert.
3. **Von's 1995 tax-payment PDF** — corroborates the 1995 lapse; awaiting the file from Jonathan.
4. **Cesar's exact death date** — pins the agent-death termination ceiling (2021 acts = Salvador).

See `CORRESPONDENCE_DIRECTIVE.md` for the standing outbound-correspondence playbook.
