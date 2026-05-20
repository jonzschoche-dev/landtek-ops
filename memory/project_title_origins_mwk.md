---
name: project-title-origins-mwk
description: "Pre-T-4497 origin chain of MWK estate — OCT T-106 (1934), 3 Worrick sisters jointly held T-111, 1953 attempted-donation to Mercedes municipality (validity NOT fully verified), T-4497 issued 1964"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Re-audited 2026-05-16 after Jonathan corrected my hallucination on the 1953 donation. Every legal-act claim in this memory carries a VALIDITY STATUS, not bare "fact" assertions.**

```
~1903   Land Registration Act (Act 496) era. LRC Record No. 10784 originates.
  ↓
1912    TCT T-111 issued (Jonathan-asserted; physical title NOT in corpus)
        Joint owners (per doc#279 1953 recital): Mary Worrick, Helen Worrick, Alice Worrick
        — three sisters. Property 26.9312 ha in Mercedes, Camarines Norte,
        bounded NE by Pacific Ocean.
        [VALIDITY: asserted by Jonathan + recited in doc#279; primary T-111
         document MUST be retrieved from Registry of Deeds Camarines Norte]
  ↓  ?? (relationship to OCT T-106 unclear; see "Suspect chain edges" below)
  ↓
1934-10-23  OCT T-106 issued, Registry of Deeds Camarines Norte
            (cited in multiple TCT extractions as "originally registered")
            [VALIDITY: cross-cited in 5+ descendant TCT extractions; physical
             OCT document NOT in corpus]

  SUSPECT CHAIN EDGE: title_chain has "OCT T-106 → T-111" with NULL source_doc_id.
  But T-111 (1912) predates OCT T-106 (1934). The edge direction is likely an
  OCR-extraction-driven mistaken inference. Possibilities:
    a) T-111 is itself the OCT (numbering scheme of Act 496 pre-1934)
    b) Both T-111 and OCT T-106 are parallel branches from LRC Record 10784
    c) The OCT-T-106 references in extractions are themselves OCR errors for T-111
  → Action: retrieve both documents to verify.
  ↓
By 1953   Helen Worrick (one of the three sisters) DECEASED. Her widower
            Manuel Garrido and her three minor children (Dolores, Concepcion,
            Helen Garrido) inherit her share. Mary Worrick had married Francis
            Keesey by then ("Mary Worrick KEESY, married to Francis Keesey").
  ↓
1953-07-12  ATTEMPTED DONATION to Municipality of Mercedes
            [doc#279, "Deed of Donation"]
            Donors: Mary Worrick Kees(e)y + Manuel Garrido (as natural guardian
                    of minors Concepcion + Helen Garrido — heirs of Helen Worrick)
            Donee:  Municipal Government of Mercedes, accepting through Mayor
                    Gideon Evalla via Resolution No. 21, series of 1953
            Object: 8,951.22 sqm portion, "site of market and municipal building"
            Result-title: claimed to bear "Certificate of Title No. T-1111"
            VALIDITY AUDIT (per [[feedback_legal_act_validity_scrutiny]]):
              ✓ Public instrument referenced (notary block in text)
              ✓ Acceptance by donee in SAME instrument (Resolution 21 s.1953)
              ✓ Donor capacity (Mary as co-owner; Manuel as guardian)
              ✓ Donee personality (LGU with Mayor's signed acceptance)
              ✓ Object alienable (private land)
              ✓ Witnesses referenced
              ✓ Signatures referenced
              ✗ Registration with RD — NOT visible in text (gap)
              ✗ Donor's Tax / BIR CAR — NOT visible in text (gap)
              ✗ Annotation on source T-111 — unknown
              ✗ T-1111 actual title — not in corpus
            STATUS: act of donation was APPARENTLY EXECUTED, but
            perfection-against-third-parties UNVERIFIED. Need RD annotation
            on T-111 + BIR CAR + T-1111 itself to upgrade to verified.
  ↓
1964-06-02  TCT T-4497 issued
            [doc#382, heavy OCR damage but T-4497 + LRC Record visible]
            VALIDITY: government_issued execution_status; physical doc damaged.
            Relationship to T-111 / the 1953 donation: NOT YET MAPPED — needs
            investigation. T-4497 might subsume what remained of T-111 after
            the donation, or be a different parcel under same OCT.
  ↓
[16 first-level descendants under OCT T-106, including T-4497 — title_chain
 normalized 2026-05-16 from 4 spelling variants to canonical "OCT T-106"]
  ↓
1992-03-19  SPA executed in Los Angeles → Cesar de la Fuente as AIF
            [doc#329] — VALIDITY components not yet audited
1988-03-17  MWK death (testimonial only — death cert needed)
2005-08-15  SPA revoked (testimonial only — revocation instrument needed)
2016        Cesar executes Deed (post-revocation → void if revocation proves)
2021        T-52540 cancelled → T-079-2021002126 to Gloria Balane
```

**Family map (corrected):**
- Three **Worrick sisters**: **Mary Worrick** (m. Francis Keesey), **Helen Worrick** (m. Manuel Garrido — Helen ☆deceased pre-1953), **Alice Worrick** (status unknown by 1953)
- **Helen + Manuel Garrido's children** (Mary's nieces/nephew): Dolores, Concepcion, Helen Jr.
- Patricia Anne Keesey (Mary's daughter) born 1947-03-11 per doc#361 birth certificate
- Patricia, Geraldine, and Marcia Keesey are the three modern-day daughters of Mary Worrick Keesey

**Spelling variants:**
- 1950s: KEES**Y** (no extra E)
- Modern: KEESEY
- Corpus typo seen: KESSEY (extra S)

**Primary-evidence retrieval queue (re-prioritized 2026-05-17 after T-111/1912 correction):**
1. **TCT T-111 itself** (1912 issuance) — joint names of Mary/Helen/Alice Worrick — **TOP PRIORITY**, currently the root of our chain understanding
2. OCT T-106 actual document (or whatever the 1934-era issuance was) — Registry of Deeds Camarines Norte
3. **LRC Decree** under Record 10784 — Land Registration Authority Manila (pre-1934 if pre-T-111, or contemporaneous with T-111 1912)
4. **Pre-1912 instrument** by which the Worrick family acquired the 26.9312 ha parcel — Spanish-era / friar-lands / land patent
5. T-1111 (if it exists) — the 1953-donation result
6. RD annotation on T-111 referencing the 1953 donation
7. BIR CAR for the 1953 donation
8. MWK death certificate
9. 2005 SPA revocation instrument
10. The actual 2016 Deed Cesar → Rosalina Hansol

**How to apply:**
- ALL legal-act claims in any Leo output must carry a validity-status flag, not bare assertion. See [[feedback_legal_act_validity_scrutiny]].
- When generating timelines or briefs, the validity column belongs alongside the event.
- "ASSERTED in doc#X" ≠ "VERIFIED valid act". The user wants the system OBJECTIVE.
