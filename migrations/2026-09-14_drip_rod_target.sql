-- The Drip — Register of Deeds as a drip target (operator decision 2026-09-14; address to follow).
--
-- The DUTY is not invented: it is row F-5 of case_work/MWK-001/RECORDS_RELEASE_SCHEDULE_2026-09.md
-- ("Certified true copies with all annotations … and RD certification that no donation/transfer to
-- the Municipality is annotated on T-4497 / T-32911", holder: Register of Deeds Camarines Norte,
-- basis P.D. 1529, status PARTIAL — the CTCs are in hand, the NEGATIVE CERTIFICATION is TO-REQUEST).
-- One duty, one clock, one ladder — the splitting rule.
--
-- ADDRESS: deliberately NULL. No RD address exists in the corpus or was sourceable on the open web
-- (phone (054) 721-0215, Metropark Village, Brgy. Magang, Daet). email_confidence='to_source' so a
-- staged draft shows "— to source —" rather than pretending an addressee is known.
BEGIN;

INSERT INTO office_obligation
  (matter_code, officer, office, obligation, instrument_ref, clock_rule, state,
   consequence_ref, counsel_gate, email, email_confidence, email_source, notes)
VALUES
  ('MWK-001','Register of Deeds','Registry of Deeds, Camarines Norte (Daet)',
   'Issue RD certification that NO donation, conveyance or transfer in favour of the Municipality of '
   'Mercedes is annotated on TCT T-4497 and TCT T-32911 (the negative certification) — the certified '
   'true copies with all annotations having already been furnished',
   'case_work/MWK-001: RECORDS_RELEASE_SCHEDULE_2026-09.md row F-5 (instrument to be drafted)',
   NULL,                                   -- no clock rule yet: nothing served, period to be set at drafting
   'draft_held',
   'Elevate to the LRA (see escalation_rung ladder)',
   'NEEDS-COUNSEL at trigger',
   NULL, 'to_source',
   'No RD email in corpus or open web as of 2026-09-14; phone (054) 721-0215, Metropark Village, '
   'Brgy. Magang, Daet. Operator to supply.',
   'STRATEGIC WEIGHT: a negative certification converts the Municipality''s donation claim from '
   '"disputed" to "unregistered on the face of the registry" — it pairs with the photocopy-is-not-a-'
   'title argument already made to DILG, and with the road-lot donation being perfected but never '
   'annotated on T-4497. The CTCs already in hand (T-4497 doc 348, T-32911 doc 2539) are the predicate.')
ON CONFLICT ON CONSTRAINT drip_dedup DO NOTHING;

-- Ladder: RD → LRA (its supervising authority) → Ombudsman. NB the RD does not answer to any LGU —
-- this ladder is deliberately separate from the municipal/provincial one.
INSERT INTO escalation_rung (obligation_id, seq, office, officer, email, email_confidence, email_source,
                             instrument_ref, statutory_basis, notes)
SELECT o.id, v.seq, v.office, v.officer, v.email, v.conf, v.src, v.instr, v.basis, v.note
  FROM office_obligation o,
  (VALUES
    (1,'Land Registration Authority — Office of the Administrator','LRA Administrator',NULL,'to_source',NULL,
     '(instrument to be drafted)',
     'P.D. 1529 — LRA administrative supervision over Registries of Deeds; consulta route where a '
     'Register of Deeds denies or doubts a registrable act',
     'NEEDS-COUNSEL-VERIFICATION: the precise section (supervision §6 / consulta §117) is asserted '
     'from general knowledge, NOT yet from an embedded copy of P.D. 1529 in the corpus — verify '
     'against the law library before this rung is served.'),
    (2,'Office of the Ombudsman','—',NULL,'unverified',NULL,
     '(rides the existing MWK Ombudsman track)',
     'Refusal to perform an official duty — RA 3019 §3(f) / RA 6713',
     'FORUM rung: counsel pulls. Only on a documented LRA-level default.')
  ) AS v(seq,office,officer,email,conf,src,instr,basis,note)
 WHERE o.officer='Register of Deeds'
ON CONFLICT (obligation_id, seq) DO NOTHING;

COMMIT;
