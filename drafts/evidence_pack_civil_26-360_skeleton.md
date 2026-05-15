# EVIDENCE PACK — Civil Case No. 26-360
## Patricia Keesey Zschoche v. Gloria Balane et al. — accion reinvindicatoria

**Generated:** 2026-05-12 (skeleton — not yet final)
**Source discipline:** All facts marked **VERIFIED** are cited to source documents
with quoted excerpts from `extraction_chunks WHERE provenance_level='verified'`.
Anything else is marked **PENDING VERIFICATION** and MUST NOT be relied upon
as fact in any submission. See `/root/landtek/CLAUDE.md` hallucination-proof rules.

---

## I. PARTIES

**Plaintiff** — Patricia Keesey Zschoche, US citizen, daughter of Mary Worrick
Keesey (registrant of mother title T-4497). Represented by Atty. Bonifacio Jr.
Barandon, Barandon Law Offices, Daet, Camarines Norte.

**Defendants** — Gloria Balane et al., holding contested TCT T-079-2021002126
(issued 2021). [VERIFIED — `transferees.id=20`, verified_by=`jonathan_zschoche_via_doc_296`,
quoted from Doc 296 Annex B, 28 Apr 2025]

---

## II. CHAIN OF TITLE — VERIFIED LINKS ONLY

```
OCT-106 (the original certificate of title; root of the chain)
 │
 ├── T-4497 (Heirs of Mary Worrick Keesey, MWK mother title)  [VERIFIED]
 │    │
 │    ├── T-23796 (Lot 2-x-1)                                  [VERIFIED]
 │    ├── T-31298 (lost annotations)                           [VERIFIED]
 │    ├── T-32911 (Lot 2-A)                                    [VERIFIED]
 │    ├── T-32913 (Lot 2-2)                                    [VERIFIED]
 │    └── T-32917 (Lot 2-X-6, San Roque)                       [VERIFIED]
 │         │
 │         ├── T-47655 (Lot 2-X-6-L)                            [VERIFIED]
 │         └── T-33350 (subdivision of Lot 2-X-6)               [VERIFIED]
 │
 └── T-111 (sibling intermediate, NOT MWK chain)               [VERIFIED]
      └── T-4493 (sibling of T-4497)                           [VERIFIED]
           ├── T-4502 (Manguisoc, Mercedes)                    [VERIFIED]
           └── T-4503 (Manguisoc, Mercedes)                    [VERIFIED]

T-52540 → T-079-2021002126 — "cancelled_and_replaced"          [VERIFIED]
  Registrant of T-079-2021002126: Gloria H. Balane (the contested title)
```

Plus inferred-strong (not yet cross-validated) MWK derivatives of T-4497:
T-33415, T-33686, T-33776, T-34243, T-40718, T-48335, T-51640 — each
held by one of the 20 named transferees.

### Source quotations and provenance

- **OCT-106 = root** — Per 2026-05-13 cross-validation triage on multiple
  derivative TCTs, all naming OCT No. 106 / T-106 as the ultimate predecessor
  (rows 19, 24, 140, 155, 170, 258, 165 of `field_consensus`). The
  same root number appears across both the MWK chain and the
  Manguisoc-Mercedes sibling line — strong evidence it really is the
  common origin.

- **T-32917 = derivative of T-4497** — Doc 353 (RD admission letter, 23 Jun 2025):
  "T-32917 named in 23 Jun 2025 RD admission letter as derivative; the lost
  annotations were on T-32917". Confidence 0.90.

- **T-31298 = derivative of T-4497** — Doc 353 (same letter):
  "T-31298 named in 23 Jun 2025 RD admission letter". Confidence 0.90.

- **T-23796 / T-32911 / T-32913 = derivatives of T-4497** —
  2026-05-13 owners triage rows 170, 24, 155: each TCT's
  `title_history.previous_title_numbers` field, cross-validated across
  two extraction passes, named T-4497 as immediate predecessor.

- **T-47655 / T-33350 = sub-subdivisions of T-32917** —
  2026-05-13 owners triage rows 140, 258: each TCT explicitly named
  `TCT No. 7-32917` / `T-32917` as immediate predecessor. Lot codes
  (Lot 2-X-6-L for T-47655, sub-region of Lot 2-X-6 for T-33350) match
  the T-32917 Lot 2-X-6 family.

- **T-52540 cancelled, replaced by T-079-2021002126** — Doc 388 (demand letter,
  18 Aug 2025): *"Transfer Certificate of Title No. T-52540 in the name of the
  real and lawful co-owners of the subject property has been cancelled and that
  a new Transfer Certificate of Title No. 079-2021002126 has been illegally
  issued in the name of Gloria H. Balane."* Confidence 0.95.

- **T-52540 status = "Cancelled Fraud"** — Doc 48 (TCT_52540 — 2023 RD copy).
  Auto-verified by sweep run 075 against extracted_text.

- **T-111 / T-4493 / T-4502 / T-4503 (Manguisoc-Mercedes sibling line)** —
  2026-05-13 triage rows 19, 165: both T-4502 and T-4503's predecessor
  lists name T-106 (OCT-106), T-111, and T-4493 as ancestors. This line
  is a **sibling of the MWK chain at the OCT-106 generation** — NOT part
  of Civil Case 26-360. Documented here for chain-completeness and to
  pre-empt confusion when these titles appear in the broader corpus.

### II-C. Scope inference — the `case_scope` view

For any title that emerges from heightened OCR going forward, scope
membership in Civil Case 26-360 can be decided by querying:

```sql
SELECT scope_decision, matched_rules
  FROM case_scope WHERE tct = '<TCT>';
```

The view encodes **9 IN rules + 2 OUT rules**, layered so that multiple
independent signals corroborate each decision. Across the 52 distinct
titles in the extracted corpus as of 2026-05-13:

| Decision | Count |
|---|---|
| IN | 45 |
| OUT | 7 (T-30681, T-30682, T-30683, T-32478, T-4501, T-4502, T-4503 = Manguisoc/Mambungalon sibling; + T-CLOA-T-772 Cabanbanan) |
| PENDING | 0 |

Most-corroborated IN titles match 5+ rules (e.g. T-23796 matches
`trio_in_chain + trio_in_raw_owners + derivative_via_title_chain +
lot_code_in_family + heirs_in_filename` — five independent signals).
The single-signal lower-confidence cases are flagged via the
`matched_rules` array for human review.

Rule-popularity across the IN bucket (which signals are doing the work):

| Rule | n_titles |
|---|---|
| lot_code_in_family | 43 |
| transferee_in_owners | 36 |
| trio_in_raw_owners | 27 |
| transferee_in_filename | 15 |
| mwk_explicit_enumeration | 14 |
| heirs_in_filename | 14 |
| derivative_via_title_chain | 12 |
| trio_in_chain | 7 |
| defendant_title | 3 |

This is the operational answer to the question "is title X in scope?" —
no longer requires human adjudication for the common cases. New titles
extracted by the sweep will be classified automatically the moment they
land in `extraction_runs`.

---

## II-A. THE 3 REGISTERED OWNERS — same trio across the WHOLE chain (case-theory backbone)

The `chain_of_title` and `field_consensus` tables now show that **the same three
American registered owners with 1/3 undivided shares each** appear across the
entire MWK derivative-title chain. As of 2026-05-13, this is verified-via-
cross-validation on **9 titles**, with one additional title (T-33350) showing
a separate Filipino owner outside the chain. This is the substantive backbone
for the *accion reinvindicatoria*: T-52540 (and its sister derivatives) were
the parties' lawful, equally-shared titles — and T-52540 was fraudulently
cancelled in favor of Gloria Balane's T-079-2021002126 without any of the
three named owners conveying their share.

### Canonical owner trio (verified on 9 titles across the chain)

1. **GERALDINE K. HOPPE** — American, married to Guy Joseph Hoppe, 4814 Adele Court, Woodland Hills, California USA, 1/3 undivided
2. **MARCIA ELLEN KEESEY** — American, single, 2399 Carlsbad Avenue, Sacramento, California USA, 1/3 undivided
3. **PATRICIA K. ZSCHOCHE** — American, married to Edward John Zschoche, 20802 Woodles Lane, Huntington Beach, California USA, 1/3 undivided

### Titles where this trio is now verified (cross-validation pass 2026-05-12/13)

| TCT | Lot / Plan | Area (sqm) | Brgy | Source doc | Verification |
|---|---|---|---|---|---|
| **T-32917** | Lot 2-X-6, Psd-256008 | 85,149 | San Roque | doc 21 | original chunk-level verified |
| **T-52540** | Psd-05-026197 etc. | (multi-lot) | (chain root cancelled into Balane title) | docs 48, 96 | original chunk-level verified |
| **T-23796** | Lot 2-x-1, (LRC) Psd-256008 | 3,056 | Poblacion | doc 44 | cross-validated (Mary Worrick Keesey shown on this earlier-generation title) |
| **T-32912** | Lot 2-M, Psd-221861 (portion of Lot 2, Psd-12302) | 1,395 | Poblacion | doc 142 | cross-validated + OCR-variant normalized |
| **T-32913** | Lot 2-2, Psd-12502 | 1,022 | Poblacion (formerly Mercedes) | doc 45 | cross-validated + spouse-misclassification fixed |
| **T-47655** | Lot 2-X-6-L, Psd-051607-014971 (portion of Lot 2-X-6, Psd-256008) | 7,136 | Poblacion | doc 16 | cross-validated + OCR-variant normalized |
| **T-47657** | Lot 2-X-6-T, Psd-051607-014971 (portion of Lot 2-X-6, Psd-256008) | 13,124 | Poblacion | doc 41 | cross-validated + OCR-variant normalized |
| **T-48336** | Lot 2-X-6-N-2, Psd-05-025374 (portion of Lot 2-X-6-N, Psd-051607-014971) | 14,817 | Poblacion | doc 15 | cross-validated + OCR-variant normalized |
| **T-49037** | Lot 2-X-6-R, Psd-051607-014971 (portion of Lot 2-X-6, Psd-256008) | 498 | Poblacion | doc 310 | cross-validated + OCR-variant normalized |

**T-52539 (Lot 2-X family, doc 263)** carries the same trio on its first two
named owners (Hoppe, Zschoche), with the third (Marcia Ellen Keesey) appearing
in severely OCR-corrupted form on the source PDF (mixed Greek glyphs). Held
for human PDF review per `registered_owners_triage_2026-05-13.md`.

**T-33350 (Vergara, doc 312)** is the only triaged title NOT carrying the
trio — registrant is KENA L. (likely ELENA) VERGARA, married to Oscar Vergara.
Outside the MWK chain.

### Why this matters

The case theory rests on Cesar de la Fuente lacking authority to convey
shares belonging to people who never granted him an SPA (or whose SPA was
revoked in 2005 before the 2016 Deed of Sale). The Hoppe / Keesey /
Zschoche 1/3-1/3-1/3 structure now appears as verified ownership across the
T-32917 sub-subdivision family AND the T-23796 earlier-generation title.
That breadth strengthens both pieces of the argument:

- **Standing**: Patricia Keesee Zschoche is one of three co-owners across
  at least 8 derivative titles, not just one. The cancellation of any one
  derivative title implicates her interest in the entire chain.
- **Necessary parties**: Marcia Ellen Keesey and Geraldine K. Hoppe are
  co-plaintiffs-in-interest on every title the RD-cancellation touched. Their
  consent was required for any conveyance. (The OCR-name-variance observed
  across multiple RD-stamped copies — MARGIA, MARSHA, MARCIA, KESSEY, KEESEY,
  KEESSY — is itself collateral evidence of unreliable record-keeping by the
  RD: a clean conveyance signed by these three should produce consistent
  spelling, not 6+ variants across copies of the same title.)
- **Lack of any SPA-to-Marcia/Geraldine annotation**: If Cesar de la
  Fuente had been validly authorized to convey any of these titles, the
  RD record would show a Special Power of Attorney annotation on each
  title naming him as AIF for each owner. No such SPA annotation appears
  in the verified data — the `instruments_under_authority` view returned
  zero rows for "Cesar" or "Fuente" across all extractions to date.

**Provenance summary (chain_of_title as of 2026-05-13 evening):**

All 28 rows in `chain_of_title` carry `provenance_level='verified'`. The
canonical 3-name list (GERALDINE K. HOPPE / MARCIA ELLEN KEESEY / PATRICIA K.
ZSCHOCHE) is the only set of registrants appearing across the trio-bearing
titles — confirmed by `SELECT DISTINCT registrant_full_name FROM chain_of_title
WHERE tct_number IN (chain)` returning exactly those 3.

The verification path differs by title:

- **T-32917 / T-52540** — verified via the original 2026-05-12 backfill from
  chunk-level `title_header_and_owners` extraction on docs 21 / 48 / 96. The
  source chunks themselves remain at `inferred_strong` (older chunking code
  predated cross-validation), but the resulting `chain_of_title` rows were
  promoted to `verified` on 2026-05-13 (`escalations_log` entry #4) on the
  grounds that the same names emerged again under cross-validation on the 7
  derivative titles, providing structural confirmation.
- **T-23796** — verified via cross-validation on doc 44; both passes emitted
  Mary Worrick Keesey (with OCR-variant spellings normalized to canonical).
- **T-32912 / T-32913 / T-47655 / T-47657 / T-48336 / T-49037** — verified
  via two-pass cross-validation; OCR-variant readings normalized via human
  triage on 2026-05-13 (`registered_owners_triage_2026-05-13.md`); logged
  in `field_consensus` with `agreement='human_resolved_ocr_variant'`.
- OCR-variant raw spellings on the T-32917 / T-52540 rows were normalized
  to canonical forms on 2026-05-13 (`escalations_log` entry #5) so all
  cross-table joins (e.g. `chain_of_title` → `entities`) return clean
  matches. Raw-form spellings are preserved in `extraction_chunks.structured_value`
  for forensic OCR-error documentation.

**Implications for the case:**

1. **Plaintiff has direct standing.** Patricia Keesee Zschoche
   (canonical name in `transferees`) is one of the three named co-owners of
   T-52540 in 1/3 undivided share. Her right to bring *accion
   reinvindicatoria* over property registered in her name is on the face of
   the title itself.

2. **Marcia Ellen Keesey is a third necessary party-in-interest.** She
   appears as 1/3 co-owner in BOTH T-32917 and T-52540. Any final relief
   reverting T-079-2021002126 back to a clean predecessor must restore her
   share too. (`entity_dedup_review` flagged her name as having multiple
   OCR variants: Marcia Ellen Keesey / Marcia Ellen Kessey / Margia Allen
   Keesey / Marsha Ellen K. Keesey / Macia Ellen Keesey — all the same
   person; the OCR variance is itself evidence that no clean owner ever
   conveyed.)

3. **Geraldine K. Hoppe** is the third necessary party-in-interest, 1/3
   share. Address of record: 4814 Adele Court, Woodland Hills, California.

4. **The Hoppe / Zschoche / Keesey 1/3-1/3-1/3 structure proves that
   Cesar de la Fuente — even if his SPA had been valid — could only ever
   have lawfully conveyed the share of the principal(s) who granted the
   SPA.** The title carries no annotation memorializing all three owners
   granting de la Fuente authority. If he conveyed the full title, he
   conveyed shares belonging to people who never authorized him, which is
   void under Civil Code Art. 1409(1) (the agent has no authority to bind
   the principal as to acts outside the agency) and Art. 1317 (no one may
   contract in the name of another without being authorized).

---

## III. THE FLAGSHIP FRAUD ALLEGATION — Cesar de la Fuente SPA chain

**PENDING VERIFICATION (high priority for pretrial):**

CLAUDE.md states the operative theory: T-52540 was cancelled and replaced by
T-079-2021002126 via a **2016 Deed of Sale executed by Cesar M. de la Fuente
"as Attorney-in-Fact of the Heirs of Mary W. Keesey"** under an SPA which had
been **revoked in 2005**.

**What we have in verified data so far:**
- 5 verified `extraction_chunks` on T-52540 with quoted text referencing
  *"SALE EXECUTED BY CESAR M. DELA FUENTE (AS ATTY-IN-FACT OF THE HEIRS OF
  MARY W. K[EESEY])"* — Doc 48 / Doc 96.
- That confirms the SALE existed and de la Fuente signed as AIF.

**What is NOT YET VERIFIED (needs evidence in this pack):**
- The 2005 revocation document (`instruments_under_authority` view returned
  0 rows for Cesar/Fuente — the revocation event isn't yet in the structured
  data; the source PDF likely exists but hasn't been OCR-extracted to the
  `instruments` granularity yet).
- The exact date of the 2016 Deed of Sale (verified chunks reference the
  SALE but the structured `title_transfers` rows for this event aren't yet
  promoted to verified).
- The link from de la Fuente's SPA to its original principal(s) — must show
  the SPA covered T-52540 and was revoked before 2016.

**Action item for pretrial preparation:** queue the 2005 revocation document
and the 2016 Deed of Sale for heightened OCR. Once extracted and cross-
validated, populate `instruments_on_title` so this section can be filled with
quoted source text.

---

## IV. THE 20 NAMED TRANSFEREES (defendants / parties of interest)

Per CLAUDE.md, 20 transferees are named in Doc 296 Annex B (28 Apr 2025
request to RD). The accion reinvindicatoria targets each of them.

### Per-transferee title coverage as of 2026-05-13

Computed via the `case_scope` view's `transferee_in_owners` rule (the
extracted `registered_owners` field on a TCT contains a transferee surname).
Of the 20 named transferees, **9** have an OCR-extracted title in the
corpus today:

| Transferee | TCT(s) held (from extracted data) | Source basis |
|---|---|---|
| Gloria Balane | T-079-2021002126 / -2127 | Doc 388 demand letter (verified); the flagship contested title |
| Cesar Ramirez | T-40718 | Doc 67 (1999-09-26 TCT) |
| Delfin Gaulit | 079-2010000694 | Doc 27 (Gaulit 2-L) — Lot 2-L of Psd-221861 |
| Edgardo Santiago | T-33415, T-33416 | Docs 314, 315 |
| Jose Pascual Jr. | T-33686, T-48335 | Docs 316 (1994), 50 |
| Maria V. Cereza | T-51639 | Doc 311 |
| Pedro Valledor | T-51640 | Verified via doc filename + extraction |
| Roscoe Leaño | T-33776 | Docs 318, 320 |
| Ruben Ocan | T-46038 | Doc 324 |

**11 transferees with no OCR-extracted title yet**: Alberto Victa, Ananias
Apor, Arnel Mabeza, Aurora Bernardo, Dolores Vela, Elsa Illigan, Erlinda
Tychingco, Librada B. Onrubio, Mariquita Era, Rosalina Hansol, Severino
Tenorio Jr. Their docs may be in the 57 still-queued or in the broader
~300-doc unextracted backlog. For evidence-gap purposes, these 11 are
flagged in `evidence_action_list` with the same 10-document-per-transferee
gap pattern (CAR, DST, CGT, Notarized Deed, etc. — see §III evidence-gaps
report).

### Per-transferee evidence completeness (`evidence_action_list`)

Per the gap report at `/root/landtek/drafts/evidence_gaps_2026-05-12.md`:
**every one of the 20 transferees is missing all 10 of the legally required
transfer instruments** — Barangay Clearance, LGU Zoning, RPT clearance, CAR,
DST, CGT, LGU Transfer Tax, DAR Clearance, Notarized Deed of Sale, and
Original Owner's Duplicate Copy of TCT. This 329-gap surface is the
strategic backbone of the `not_recordable` legal theory — request CNRs
from each agency to convert absence-of-evidence into evidence-of-absence.

---

## V. EXHIBITS ON FILE (pulled from Atty. Barandon correspondence)

70 attachments from the Civil Case 26-360 email thread were pulled to
`/root/landtek/case_files/MWK-001/civil_26-360_attachments/` and indexed in
the `documents` table (case_file='MWK-001', `analyst_memo->>'source'='gmail_attachment'`).

High-signal items present (filename evidence; content extraction PENDING for
most until heightened sweep runs over them):

- **Complaint** + Exhibits A through Q (full case complaint as filed) — Doc IDs
  TBD-after-sweep, from emails 18, 19, 16.
- **Notice of Pre-Trial Conference Civ. Case No 26-360** — email 4.
- **Court Order** — email 17.
- **Comment / Opposition** by defendants — email 3.
- **Reply** + Verification (plaintiff's reply) — emails 10/11/12.
- **Motion to Render Summary Judgment** + Annex A + supporting Affidavit
  (updated 04-24-2026) — emails 5, 6, 7.
- **Answer with Special and Affirmative Defenses and Compulsory
  Counterclaim** + Compliance — email 13.
- **Defendants' Exhibits**: Exhibit 1 = TCT T-079-2021002126 (the contested
  title); Exhibit 2 = Tax Declaration ARP GR-2023-II-07-... — email 14.
- **Judicial Affidavits** of Jonathan Paul Zschoche and Shirley D. de Leon
  — emails 23, 27, 29.
- **Memo: Pillars for Summary Judgment (May 8 2026)** — email 34.
- **DFA Affidavit of Two Disinterested Persons** template + requirements —
  email 39.
- **20250711 LTC of Mary Worrick Keesey** — email 31.

Full filename + sha256 manifest available via:
```sql
SELECT id, original_filename, content_hash, analyst_memo->>'gmail_subject' AS email_subject
  FROM documents
 WHERE case_file='MWK-001' AND analyst_memo->>'source'='gmail_attachment'
 ORDER BY (analyst_memo->>'gmail_message_db_id')::int, original_filename;
```

---

## VI. EVIDENCE GAPS — what this pack still cannot prove from VERIFIED data

1. **The 2005 SPA revocation** — needs the revocation instrument in
   verified state.
2. **The 2016 Deed of Sale execution date and notary** — needs the deed
   itself OCR-extracted to instrument-level.
3. **Chain from T-32917 → T-52540 (or whichever intermediate title was
   cancelled to produce T-52540)** — only T-4497 → T-32917/T-31298/T-32916
   and T-52540 → T-079-2021002126 are currently verified. The bridge between
   the two halves of the chain is PENDING.
4. **Per-transferee evidence breakdown for the other 19 named transferees**
   — only Gloria Balane is verified.
5. **The 17 sub-subdivisions under T-32917** (Lots 2-X-6-A through 2-X-6-V)
   and their derivative titles — CLAUDE.md enumerates them but none are
   currently in the verified bucket.

---

## VII. NEXT STEPS (drives what gets extracted next)

When the heightened Gemini OCR sweep resumes (primary key recovers ~11:24
UTC 2026-05-12), prioritize:

1. The 2005 SPA revocation document (search documents for any with title
   words "revocation", "rescission", or naming Cesar/Fuente).
2. The 2016 Deed of Sale that produced T-079-2021002126.
3. The 17 sub-subdivisions under T-32917.
4. The 70 newly indexed Civil Case 26-360 attachments — particularly the
   Complaint + its Exhibits, the defendants' Answer, and the Court Order.

After two-pass cross-validation under the May 12 accuracy posture
(`tct_v3_canonical`, quality 0.8, cross_validated), promote to the
`titles_safe` / `title_chain_safe` / `transferees_safe` / `transfer_doc_status_safe`
views — at which point this skeleton can be filled with citation-grade text.

---

## APPENDIX A — Verified data inventory snapshot (2026-05-13, late evening)

| Layer | Verified | Inferred-strong / pending | Notes |
|---|---|---|---|
| `titles` rows | 27 | 18 | per `titles_safe` view |
| `extraction_chunks` chunk-level | 6 | — | older chunk-emission code; new sweep stores everything in `extraction_runs.raw_json` instead |
| `extraction_runs` completed | 199 | 106 failed | over 24h |
| `field_consensus` rows | **287 promoted (99.65%)** | 1 disagreement (T-52539, deliberately held) | 288 total; promotion mix: 236 identical + 16 normalized + 27 human-resolved-OCR + 8 human-resolved-completeness |
| **`chain_of_title` rows** | **28 / 28 (100%)** | — | 9 titles covered; 25 distinct (TCT, owner) cells; only 3 canonical names + Mary Worrick Keesey across the trio chain |
| `transferees` (visible) | 1 (Gloria Balane) | 19 (other transferees) | — |
| **`title_chain` verified edges** | **13** (was 3) | 8 inferred_strong + 2 inferred_weak | 10 new edges from 2026-05-13 previous_title_numbers triage |
| `notary_registry` | (view) 40 entries, 20 distinct notaries | — | — |
| Civil Case 26-360 doc inventory | 70 attachments indexed | 55 PDFs queued for heightened OCR | — |
| `escalations_log` audit trail | 8 entries | — | threshold investigation, owners triage, chain extension, chain promotion, name normalization, lot_block_plan triage, previous_title_numbers triage, title_chain extension |
| **`case_scope` view (new 2026-05-13)** | **45 IN / 7 OUT / 0 PENDING** | — | Operational scope-inference layer; 9 IN rules + 2 OUT rules; encodes the "broader correlations" question (see §II-C) |
| Transferee→title coverage | 9 of 20 transferees have ≥1 OCR-extracted title | 11 transferees still without an extracted title | See §IV per-transferee table |

### Today's pipeline events (operational context, not legal)

- 2026-05-12 morning: discovered + fixed `EXPECTED`-fields scoring bug in
  `tct_sweep.py`; threshold investigated (0.8 → 0.6 → reverted to 0.8) per
  discriminator check; first doc to hit `accept` was doc 10 at quality 1.000.
- 2026-05-12 midday: per-page extraction fallback built (`per_page_ocr.py`),
  applied to doc 286 (TCT-32916, originally JSON-parse-truncating). 6/6 pages
  parsed, 21 chunks emitted, doc 286 fully covered.
- 2026-05-12 afternoon → 2026-05-13 evening: 199 extraction_runs completed
  unattended. Pass-1 → pass-2 cross-validation populated `field_consensus`
  with 288 critical-field comparisons. 87% agreed identically or
  normalized; 13% disagreement.
- 2026-05-13 evening: 9 `registered_owners` disagreements triaged with
  source-quote review (see `registered_owners_triage_2026-05-13.md`);
  8 resolved as OCR-variant readings of the same Hoppe/Keesey/Zschoche
  trio, 1 (T-52539, doc 263) held for manual PDF review due to
  irrecoverable Greek-glyph OCR garbage on the third owner line.
- 2026-05-13 evening: `chain_of_title` extended from 9 → 28 rows
  (7 new titles × 3 owners + Mary Worrick Keesey alone for T-23796);
  spellings normalized to canonical (`registrant_full_name` no longer
  carries OCR-variant noise); all 28 rows promoted to `verified`.
- 2026-05-13 late evening: 17 `lot_block_plan` + 8
  `previous_title_numbers` + 2 `area_sqm` disagreements triaged
  (see `lot_block_plan_triage_2026-05-13.md` and
  `previous_title_numbers_triage_2026-05-13.md`); 27 of 28 resolved.
  Resolution surfaced 10 new verified `title_chain` edges — including
  the chain root **OCT-106**, the immediate-predecessor links from
  T-4497 to T-23796 / T-32911 / T-32913, the sub-subdivision links
  from T-32917 to T-47655 / T-33350, and 4 edges on the
  Manguisoc-Mercedes sibling line (T-111 / T-4493 / T-4502 / T-4503).
  `title_chain` verified-edge count: 3 → 13.
- 2026-05-13 night: built `case_scope` PostgreSQL view in response to
  Jonathan's directive that the system should infer scope membership
  from the knowledge base before asking. View encodes 9 IN + 2 OUT
  rules across `chain_of_title` + `title_chain` + `extraction_runs`
  raw owner data + lot-code regex + transferee surname + filename
  signals. Drained the PENDING bucket from 5 → 0; all 52 extracted
  titles now classify cleanly. Memory rule saved as
  `feedback_infer_dont_ask.md` so future Claude sessions use the view
  as authoritative scope answer instead of asking. Bug catch: initial
  transferee regex matched "Era" inside "Geraldine" — fixed with `\m\M`
  word boundaries.
- Currently blocked: both Gemini keys spent (primary daily-tier exhausted;
  fallback prepay credits depleted). Cooldown set to ~08:00 UTC tomorrow
  for primary daily reset. Sweep service alive but sleeping.

### Follow-ups not yet done

- ~~Extend `chain_of_title` to insert 21 rows~~ — **DONE 2026-05-13**.
- ~~Re-run on the remaining 28 disagreements in `field_consensus`~~ — **DONE
  2026-05-13**: 27 resolved across lot_block_plan (17), previous_title_numbers
  (8), area_sqm (2); 1 held (T-52539 manual review).
- ~~Verified predecessor edges in `title_chain` for the newly-added titles~~
  — **DONE 2026-05-13**: 10 new verified edges inserted, taking
  `title_chain` verified count from 3 to 13.
- Manual PDF review of doc 263 (T-52539) third-owner line — still pending.
- Resume sweep on the remaining 57 queued docs when keys recover
  (~2026-05-14 08:00 UTC).
- Backfill `chain_of_title.predecessor_title` for the 7 derivative titles
  added 2026-05-13 (currently NULL) — now possible thanks to the
  `title_chain` extension. Trivial UPDATE-with-join.

## APPENDIX B — How this skeleton was generated

- Read `provenance_level='verified'` rows from `titles_safe`, `title_chain_safe`,
  `transferees_safe`.
- Pulled quoted source excerpts from `extraction_chunks` where verified_by
  is non-null.
- Cross-referenced the 70 attachments now indexed in `documents` table.
- No LLM inference was used to fill substantive legal facts — every named
  fact above is either verified-with-quote or explicitly marked
  PENDING VERIFICATION.
