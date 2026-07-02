# Correspondence directive — MWK-DLF-VOID

Standing playbook for outbound correspondence in the de la Fuente void-transfer investigation.
Every letter is tracked in `correspondence_events` (matter_code `MWK-DLF-VOID`). This directive
governs **who we write, what we request, on what legal footing, the cadence, and the escalation.**

## Principles (non-negotiable)
1. **One purpose per letter.** Each letter makes one clean, specific request tied to one record.
2. **Cite the legal footing every time.** Records requests to a government office ride **RA 11032**
   (Ease of Doing Business) — name the section, set the statutory clock, and ask for a written action.
3. **Build the evidence, don't just chase it.** A refusal or a "no record on file" answer is *itself*
   evidence (see doc:353). Frame every request so that **either outcome helps** — production gives the
   deed; non-availability proves the void chain.
4. **Log before you send.** Add the planned letter to `correspondence_events` (delivery_status
   `planned`), then flip to `sent` with `claimed_date`, then `answered`/`late` with `received_date`.
   Never let a sent letter sit without a tracked next action.
5. **Preserve the 3 dates** (per the forensic-email discipline): borne date, claimed sent date, and
   the TRUE received date. Attach proofs (registry stamp, email receipt) in `proofs`.
6. **No double-tap to a busy office.** One request, one follow-up (RA 11032 §-cited), then escalate —
   don't send serial chasers that muddy the record.

## Recipients & their mandates
| Recipient | What they hold / owe | Footing |
|---|---|---|
| **Register of Deeds, Daet (Camarines Norte)** | title histories, the de la Fuente-era deeds, non-availability certifications | RA 11032; PD 1529 (CTC issuance) |
| **LRA, Quezon City** | escalation above RD; e-Serbisyo CTCs | RA 11032; PD 1529 |
| **Mercedes Municipal Assessor** | tax declarations / ARP records (ARP GR-2023-II-07-001-00256) | RA 11032; RA 7160 §§201-207, §472 |
| **RTC Daet — Office of the Clerk of Court** | case/transaction records (Genesis Ibasco) | RA 11032; court records rules |

## The standing request set (priority order)
Mirror of the `planned` rows in `correspondence_events`:

1. **[P1] RD — sealed Certification of Non-Availability** for the 9 de la Fuente-era PE entries that
   doc:353 already lists as "no record on file." Ask for the LRA-standard, signed & sealed form so it
   is a usable court exhibit. *(Upgrades a plain letter into evidence.)*
2. **[P1] RD — consolidated request** (the gap-closer): (a) certified true copies of
   **T-47655 / T-47656 / T-47657 / T-48336 / T-69404** to identify the ~50,000 sqm holder; and
   (b) certified copies **or** a non-availability certification for the **Dean (PE-214781)** and
   **Capistrano (PE-261974)** deeds. Either outcome advances the case.
3. **[P2] RD — T-52540 chaser.** The 25-Feb-2025 request for T-52540's certified annotations was never
   answered; re-ask under RA 11032, or request a non-availability cert for it too.
4. **[P3] RTC Daet Clerk of Court** — confirm whether the 27-May-2025 request (doc:1019) was retrieved.
5. **[drafted, unsent] Mercedes Assessor** — finalize and send the tax-declaration request (doc:332);
   it supports the complaint's prayer to cancel ARP GR-2023-II-07-001-00256.

## Cadence & escalation ladder
- **T+0** send (log `sent` + `claimed_date`).
- **T+15 working days** (RA 11032 complex-transaction window): if no written action, send ONE
  RA 11032 §21-cited follow-up (log a second event).
- **T+escalation:** unanswered RD → **LRA**; unanswered/refused LGU → **ARTA** (the MWK-ARTA cluster is
  the established referral path) → **DILG / Office of the President** as already mapped.
- Every escalation references the prior request's date + proof of delivery (the §21(e) lateness angle
  that already worked in the ARTA cluster).

## Definition of done (per letter)
A correspondence item is closed only when the `correspondence_events` row is `answered` with a
`received_date` and the response is linked as a `doc:` in the corpus (`document_matter_links`). A
"no record on file" answer closes the item **and** spawns a follow-on: request the sealed cert.
