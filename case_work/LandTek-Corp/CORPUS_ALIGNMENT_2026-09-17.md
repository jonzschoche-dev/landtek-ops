# LandTek OPC formation — corpus alignment check (2026-09-17)

Every person, number and name in the filed SEC application, checked against the live corpus
(VPS `n8n` DB: `documents`, `entities`, `doc_entities`, `gmail_messages`, `matters`, `clients`,
`case_deadlines`, `landtek_obligations`). **Verified = a cited document with a quoted excerpt.**

**Status 2026-09-18 (supersedes the 2026-09-17 reading):** matter `LANDTEK-OPC-FORMATION` registered
(client `LANDTEK-CORP`, docket = the ESPARC reference). Read directly off the eSPARC status page on
2026-09-18: **LANDTEK PROPERTY SERVICES OPC — Status "Pending SEC Review", Date Submitted September 17,
2026, Ref. SEC260917-UOD7XXGI2MXEIGG.** The application was completed and submitted the same day it was
created, so the 5-calendar-day draft window (deadline id 14, due 22 Sep) is **satisfied and closed**; my
17 Sep reading of it as "still on draft" came from the 09:54 draft-created email and was overtaken by
events. New clock: **id 15, due 2026-09-28** — 7 working days for SEC review [HUMAN VERIFY the count].
Stockholder TIN and official-email verification both **done** by Jonathan on 17 Sep. §3 ruled closed by
Jonathan.

**Sequencing fact that matters:** per eSPARC's own stage list, eSAP authentication by the signatories is
triggered **after** SEC pre-approval — "An email/SMS notification will be sent to all signatories for the
authentication of documents." So nothing is pending with Justine or Kristine today. What they must finish
before that stage arrives is eSECURE **credentialing to ACTIVE**; the portal warns that all officers
authenticating documents must be "registered and credentialed in the eSECURE".

---

## 1. What the corpus CONFIRMS

| Item | Corpus status | Source |
|---|---|---|
| **Allan Villafria Inocalla** — exact legal name as written in the Articles | **VERIFIED** | entity #7983 (`provenance_level=verified`, 25 mentions). Independently corroborated on a 2026 government instrument: DTI Certificate of Business Name Registration, doc **13837** — "This certificate issued to **ALLAN VILLAFRIA INOCALLA** … valid from September 11, 2026 to September 11, 2031" |
| Allan is the Paracale/mining client, separate cluster | VERIFIED | all 25 Allan mentions sit in `Paracale-001`; `clients` row 8 = "Datu Allan Inocalla" |
| Patricia **Keesey** Zschoche spelling | VERIFIED | used as-is across MWK-001; see doc 1034 letterhead |
| Daet / Camarines Norte as the principal-office locality | consistent | Jonathan's own letterhead of record is "Dasmariñas St, Daet" (doc 1034) |

---

## 2. What the corpus does NOT confirm (operator-supplied only)

| Item | Status |
|---|---|
| **TIN 200-031-253-000** (the correction Allan is to make in eSECURE) | **ABSENT corpus-wide.** No TIN for Allan exists in any indexed document. The only Inocalla-adjacent TIN on file is 000-851-087-016, which belongs to **NIBDC** (docs 1183/1184) — a different entity; do not reuse it. Verify 200-031-253-000 against Allan's physical BIR ID before the correction email goes to `cprd_registration@sec.gov.ph`. |
| **Kristine Andaya Palado** (full name) | Not in the corpus under that full name. The corpus knows a **"Ms. Kristine Palado"** — see §3. |
| **Justine Mae Pabilonia Era** | Not in the corpus under that name. The corpus knows the **Pabilonia Era** family — see §3. |
| **"LandTek Property Services OPC"** as a name | Zero occurrences. The company name has never entered the corpus, so nothing in the stack (deadlines, obligations, clients, matters) is tracking the formation. |
| The Bagasbas Road office premises | 6 documents mention Bagasbas; **none** of them is a lease, tax declaration or ownership record for the office. The owner's-consent question is unanswerable from the record — it must come from Allan. |

---

## 3. Officer slate — RULED, closed

> **OPERATOR RULING 2026-09-17 (Jonathan): no conflict. The slate will be changed later.**
> This section is retained as a record of what the corpus contains, not as an open question.
> It is not a blocker on the 22 Sep clock and is not to be re-raised.

### 3.0 What the corpus contains (background)

The design's load-bearing assumption is that the Filipino principals are **genuinely independent of the
licensor**. The earlier instruction was explicit: *"Don't use yourself or Patricia. A nominee tied to the
licensor weakens the case that Allan truly owns the company."* The corpus shows both proposed officers are
one step removed from Jonathan — not from Allan.

### 3.1 Kristine Palado is already Jonathan's agent of record in MWK-001 — on a stamped public document

Doc **1034 / 1033**, "August 14 2025 Letter to Municipal Assessor" (MWK-001, doc_date 2025-08-14),
bearing the **Municipal Assessor's Office RECEIVED stamp** — i.e. it is in the LGU's own file and is
discoverable by any adverse party:

> "This letter will be delivered in person by **Ms. Kristine Palado, who is authorized to receive the
> requested documents on my behalf**."
> — signed *Jonathan Zschoche, Representative for Patricia Keesey Zschoche*

She is slated as **Treasurer + Alternate Nominee**. The Treasurer is the officer who certifies paid-in
capital and holds the company's money. On the public record she already holds a written authority from the
foreign licensor, in the very matter the opco is being formed to serve.

**Second-order flag on the same surname:** **Margarita A. Palado is the Municipal Accountant of Mercedes**,
named in the 1996 Ad Hoc Committee resolution on the proposed acquisition of the heirs' land (docs 389, 534,
577, 751) — an LGU-side document in the `MWK-LGU-RECOVERY` matter (the void donation / ₱2.88M expenditure).
A shared surname is not a relationship, but in Mercedes this must be asked, not assumed.

### 3.2 Justine Mae Pabilonia Era is from a family Jonathan remits money to

Doc **1438** (Paracale-001) is a remittance record: **₱5,319.60 to "Jonah Liza Pabilonia Era"** for pickup
at BDO / Cebuana / LBC etc. Same double surname. The corpus does not state the relationship; what it does
show is that the Pabilonia Era household receives money from Jonathan.

She is slated as **Nominee + Corporate Secretary** — the officer who certifies corporate acts and who, on
Allan's death or incapacity, both *sends* the notice and *receives* it.

**Second-order flag on the same surname:** **Mariquita Era is one of the 20 named transferees** in the
T-4497 chain — an adverse party (entity #1262, verified, 10 mentions; docs 257, 288, 296, 297, 303).

### 3.3 Why this matters more than it looks

Anti-Dummy is not tested by whether the SEC accepts the filing — it accepts almost anything. It is tested
later, by an opponent's counsel, when LandTek's standing is challenged in a Mercedes proceeding. At that
point the question is: *who actually controls this company?* The answer the record currently supports is
"the foreigner's agent is its treasurer and the foreigner's dependents' family holds its secretary post."
That is the exact inference the structure was designed to avoid.

The single clean fix is available and cheap: **the two officer/nominee slots should be Allan's people, not
Jonathan's** — an adult child, a sibling, a long-time associate of Allan's. Nothing else in the structure
changes.

---

## 4. Cluster-separation check

- `AVI GOLD PROCESSING PLANT` (doc 13837) is a **DTI sole proprietorship registered to Allan personally on
  2026-09-11** — mining/processing, *not* in the OPC. That is correct under the separation rule, and it is
  now a documented fact the **conflict acknowledgment must name**, alongside the Paracale/PGC positions.
- No cross-contamination found: the OPC purpose clause (property services, no practice of law) does not
  reach the processing plant's line of business.

---

## 5. System-layer gaps (the formation is invisible to the stack)

1. ~~No matter, no client row.~~ **CLOSED 2026-09-17** — client `LANDTEK-CORP` ("LandTek Property Services
   OPC (in formation)", corporation, case_file `LandTek-Corp`) and matter **`LANDTEK-OPC-FORMATION`**
   (type `business`, forum "SEC (OneSEC / eSAP)", opened 2026-09-17, next_deadline 2026-09-22, owner
   jonathan) now exist. Deliberately its own code — **not** folded into `Paracale-001`/LTC-001 (Allan the
   client), MWK-001 or NIBDC-001, per the client-separation invariant.
2. ~~No deadline.~~ **CLOSED 2026-09-17** — `case_deadlines` **id 14**, due 2026-09-22, type `admin`,
   priority P1, owner jonathan, confidence **0.5** (the date is operator-supplied, not corpus-verified;
   the row says so and flags it `[HUMAN VERIFY]`). Two clocks now land on 22 Sep: id 13 (ARTA-1319 OP
   supervisory-review) and id 14 (SEC name reservation).
3. **No SEC document exists in the stack — but not for want of visibility.** Jonathan (2026-09-17):
   LandTek is essentially a **management company**; Allan is kept abreast through
   **shiraction2@gmail.com** and decisions are made jointly, in person at the office. So the SEC
   correspondence *is* seen — it simply never lands in an ingested mailbox. Searched both the
   `gmail_messages` mirror (current to 2026-09-17 02:59) and live **jonathan@hayuma.org**
   (`newer_than:30d`, sec.gov.ph / eSECURE / OneSEC / name reservation / eSAP): **zero hits in either**.
   Emails of record now on the matter: Allan = shiraction2@gmail.com (primary; also
   shishir@paracalegoldcorp.com), Jonathan = jonathan@hayuma.org.
   **Company mailbox:** **landtekopc@gmail.com** is now LandTek's own address and the mailbox of record
   for this matter (recorded on client `LANDTEK-CORP`).
   **Ingest path:** `gmail_messages` ingests two accounts today — jonathan@hayuma.org (825 msgs, live to
   2026-09-17 02:59) and jonzschoche@gmail.com (135, to 2026-09-15). **landtekopc@gmail.com is not
   ingested.** Cheapest fix is a forwarding rule landtekopc → jonathan@hayuma.org (no new OAuth token);
   the alternative is minting a third `GMAIL_REFRESH_TOKEN`. Either way the 22 Sep expiry then moves off
   operator-supplied (confidence 0.5) onto the document.
4. **The deliverables are off-repo.** Docs 01 / 02 / 06 (Articles, resolutions, post-approval kit) exist
   only as DOCX in the session that produced them — not in `landtek-ops` on this Mac, and not on the VPS.
   The repo layer here (`LANDTEK_FORMATION_PACKAGE.md`, `LANDTEK_COMPANY_SETUP_BLUEPRINT.md`,
   `OPERATIONALIZE/*`) is the **2026-09-16 planning layer and is now stale**: it still shows the company
   name, capital, royalty and signatory as open decisions, and names no officers.

---

*Verification record. Facts marked VERIFIED carry a cited document; everything else is flagged as
operator-supplied and PENDING VERIFICATION. Nothing filed or sent by this document.*
