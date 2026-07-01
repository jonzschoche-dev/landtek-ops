-- deploy_647_cv26360_aug12_grounding.sql  (STAGED — do NOT auto-apply; hand-reviewed by operator)
--
-- CONTEXT
--   The CV-26360 (MWK-CV26360) testimony/trial date of 2026-08-12 (Jonathan Zschoche
--   testifies as Patricia Keesey Zschoche's witness, MTC Mercedes, Camarines Norte,
--   Summary Procedure) is OPERATOR-ATTESTED as a real court-set date.
--
--   A live-source hunt (2026-07-01) for the grounding court order / notice of hearing /
--   subpoena FAILED to locate any such document:
--     * documents corpus: 0 rows mention "August 12" / "Aug 12" / "2026-08-12"
--     * gmail_messages (corpus): 0 rows; newest Barandon email is id 61858 (sent 2026-06-01),
--       which states "The Court is yet to rule on the matter."
--     * LIVE Gmail (jonzschoche@gmail.com, via gmail_client, readonly): searched Barandon
--       senders + phrase queries ("August 12", subpoena, testify, testimony, presentation of
--       witness, hearing set, continuation of trial, 26-360 + hearing/trial/notice) across the
--       ENTIRE mailbox and all mail after 2026/06/01 — 0 messages mention Aug 12 in subject or
--       body. Newest Barandon correspondence in the live box is also 2026-06-01.
--     * chat_notes: 0 rows mention Aug 12 / testify / trial date / subpoena.
--
--   CONCLUSION: the setting is NOT YET in any live source we can reach. The notice/order is
--   an EXTERNAL RECORD pending retrieval. Per discipline, we record the date as
--   OPERATOR-ATTESTED (its own tier), never dressed up as doc-verified. next_deadline stays
--   2026-08-12 (operator-confirmed correct). No fabricated citation is written.
--
-- WHAT THIS MIGRATION DOES
--   1. Rewrites matters.next_event so the provenance is HONEST inline (operator-attested,
--      notice pending ingest) instead of a bare assertion that reads as fact.
--   2. Logs the missing court order/notice as an OPEN record_gap so the live-source sweep
--      keeps hunting for it and auto-resolves when found.
--
--   It does NOT touch: next_deadline (2026-08-12, correct), surfaced_deadlines (operator is
--   separately clearing the phantom row 54 via deadlines.py), any _safe view, or any vector store.

BEGIN;

-- 1) Honest inline provenance on the matter's next_event.
UPDATE matters
SET next_event = 'Aug 12, 2026 — testify as Patricia Keesey Zschoche''s witness (CV-26360, '
               || 'MTC Mercedes, Camarines Norte, Summary Procedure); live SJ motion + Balane '
               || 'judicial-affidavit fight. [OPERATOR-ATTESTED: counsel''s PLANNED testimony '
               || 'date, NOT a written court order (operator-confirmed 2026-07-01); no grounding '
               || 'notice in corpus or live Gmail — Barandon''s newest email 2026-06-01 says the '
               || 'court had not yet ruled — see record_gaps ''CV-26360 Notice/Order setting '
               || '2026-08-12''. Not doc-verified.]',
    updated_at = now()
WHERE matter_code = 'MWK-CV26360';

-- 2) Log the pending external record so the sweep keeps looking (idempotent on reference).
INSERT INTO record_gaps (reference, matter_code, source_hint, status, note, created_at)
SELECT
    'CV-26360 Notice/Order setting 2026-08-12 testimony',
    'MWK-CV26360',
    'MTC Mercedes, Camarines Norte (mtc2mcd000@judiciary.gov.ph); likely forwarded by Atty. '
      || 'Bonifacio T. Barandon, Jr. (barandon_lawoffice@yahoo.com / '
      || 'barandonlawoffice.records@gmail.com) as a Notice of Hearing / Order / subpoena. '
      || 'Newest Barandon email in-box as of 2026-07-01 is 2026-06-01, pre-ruling.',
    'open',
    'Aug-12 testimony date is operator-attested/real but ungrounded: no document in corpus, '
      || 'gmail_messages, live Gmail, or chat_notes references it (hunt 2026-07-01). When the '
      || 'court notice/order arrives, ingest it, link to MWK-001/MWK-CV26360, quote the setting '
      || 'excerpt verbatim, flip this gap to resolved (found_message_id/found_doc_id), and '
      || 'upgrade matters.next_event provenance from operator-attested to verified [v:doc#].',
    now()
WHERE NOT EXISTS (
    SELECT 1 FROM record_gaps
    WHERE reference = 'CV-26360 Notice/Order setting 2026-08-12 testimony'
);

COMMIT;

-- POST-APPLY VERIFY (run manually):
--   SELECT matter_code, next_deadline, next_event FROM matters WHERE matter_code='MWK-CV26360';
--   SELECT reference, status, note FROM record_gaps WHERE matter_code='MWK-CV26360';
