-- deploy_NN: deadline / verified-date coverage on the two PROOF clients (MWK-001, Paracale-001)
-- Product-hardener pass, 2026-06-30. GROUNDED structured-date writes only — NO vector store.
-- Provenance discipline: verified = cited doc + excerpt. Operator-rule windows tagged [HUMAN VERIFY].
-- Client/matter separation absolute. Does NOT touch any Aug-12 case-critical safety path.
--
-- Change 1 (ALREADY APPLIED LIVE 2026-06-30 — included here for the audit trail / replay):
--   MWK-ARTA-1891 gets a grounded follow-up date.
--   GROUND: gmail#92366 (received 2026-06-24) — CSC "NOTICE OF REFERRAL" transmittal of
--   OAC-L Letter No. 270 s.2026 (dated 23 June 2026) onward-referring ARTA CTN SL-2026-0423-1891
--   to the OMB. Excerpt: "...transmit OAC-L Letter No. 270, s. 2026, dated 23 June 2026 relative
--   to the Referral Letter of ARTA Case with File/Reference no. ARTA CTN SL-2026-0423-1891."
--   The 30-day follow-up is an OPERATOR RULE (matter.next_event prose), not a statutory deadline,
--   so the label carries [HUMAN VERIFY]; referral 2026-06-24 + 30d = 2026-07-24.
UPDATE matters
SET next_deadline = DATE '2026-07-24',
    next_event = 'Follow up with CSC (Asst Comm Ronquillo) re ARTA CTN SL-2026-0423-1891 onward-referral to OMB (CSC NOTICE OF REFERRAL recv 2026-06-24, OAC-L Letter 270 s.2026). [HUMAN VERIFY] 30d operator follow-up window from referral; DILG escalation per case_thread #3 if no movement. Source: gmail#92366.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-ARTA-1891';

-- Change 2 (APPLIED LIVE 2026-06-30 — operator confirmed no held hearing notice; "yes to both"):
--   MWK-CV26360.next_deadline = 2026-08-01 was the DISCREDITED "Aug 1 pre-trial" date that
--   MASTER_PLAN/CLAUDE.md explicitly disclaim ("NOT the old Aug 1 pre-trial; pre-trial was
--   May 13, passed"). No corpus doc grounds an Aug-1 OR Aug-12 court setting (searched
--   gmail_messages + chat_notes + documents). The engine surfaced this stale date as the
--   ONLY future deadline for the flagship case = false confidence (silent-failure surface).
--   Honest fix: NULL the ungrounded date and mark the matter NEEDS-A-DATE until a real
--   hearing/trial notice lands, rather than assert Aug 1.
UPDATE matters
SET next_deadline = NULL,
    next_event = 'Trial pending — mediation impasse (chat_notes#1209, 2026-06-06). [HUMAN VERIFY] await court trial/hearing NOTICE; Aug-1 pre-trial date is DISCREDITED (pretrial was May 13, passed). No grounded court setting in corpus as of 2026-06-30.',
    stage_updated_at = now()
WHERE matter_code = 'MWK-CV26360';
