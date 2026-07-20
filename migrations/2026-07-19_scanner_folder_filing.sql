-- 2026-07-19_scanner_folder_filing.sql — content-based filing of the unfiled scanner backlog.
-- The deterministic enricher left these NULL because they carry no in-text docket/title match; each was READ
-- and classified by CONTENT (cited below). CLIENT is the A5 boundary — assigned only where content is
-- unambiguous. Matter set where content clearly supports; left NULL (client-filed, matter-to-refine) otherwise.
-- Non-relatable → Archive; unreadable/unidentifiable → PENDING_TRIAGE (flag, never guessed onto a client).
-- Reversible: every row was case_file IS NULL before this (except 534=MWK-ESTATE, 553=MWK-TCT4497 matter kept).

BEGIN;

-- ── MWK-001 (Keesey / Zschoche estate) ──────────────────────────────────────
UPDATE documents SET case_file='MWK-001', matter_code='MWK-LGU-RECOVERY' WHERE id=534;  -- Mercedes Sangguniang Bayan minutes 1996 (Kgd. Ruben Ocan; the LGU land/road matter)
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ESTATE'       WHERE id=543;  -- Tax Declaration, owner "MARY WORRICK KEESEY c/o Benjamin Llamanzares", Mercedes
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ESTATE'       WHERE id=552;  -- Tax Declaration No.1781, "MARY WARRICK KEESER", Mercedes
UPDATE documents SET case_file='MWK-001'                                 WHERE id=553;  -- Tax Declaration No.5136, "Mary Worrick Keosay" (keeps existing matter MWK-TCT4497)
UPDATE documents SET case_file='MWK-001', matter_code='MWK-TCT4497'      WHERE id=563;  -- TCT No.111, "Transfer from No. T-106" (the MWK mother-title chain)
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ESTATE'       WHERE id=564;  -- SPA by "MARY WARRICK-KISSEY" appointing Benjamin (attorney-in-fact)
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ESTATE'       WHERE id=2489; -- ARTA feedback packet by Ian Paul Zschoche, AIF for Patricia Keesey Zschoche (Estate of MWK)
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ESTATE'       WHERE id=2844; -- Tax clearance certificate, "HRS. OF MARY WORRICK"
UPDATE documents SET case_file='MWK-001', matter_code='MWK-ARTA-1321'    WHERE id=1158; -- Reply Affidavit: ARTA Case CTN SL-2026-0209-1321, Jonathan Paul Zschoche v. Gemma P. Abla

-- ── Paracale-001 (Inocalla) ─────────────────────────────────────────────────
UPDATE documents SET case_file='Paracale-001'                           WHERE id IN (501,502,504,508);  -- SC G.R. No. 256997, Inocalla v. Inocalla (matter to confirm)
UPDATE documents SET case_file='Paracale-001', matter_code='PAR-INOCALLA-MURDERS' WHERE id=518;  -- Homicide reward poster: "WHO KILLED SENEN 'BETH' INOCALLA?" (LGU Paracale)
UPDATE documents SET case_file='Paracale-001'                           WHERE id=524;  -- Messenger screenshot re "eric inocalla" family dispute (matter to confirm)
UPDATE documents SET case_file='Paracale-001'                           WHERE id=1160; -- Truman College certificate for VICENTE L. INOCALLA (Inocalla personal record)
UPDATE documents SET case_file='Paracale-001'                           WHERE id=1159; -- CLOA (paired scan-batch w/ doc 1160 Inocalla) — FLAG: confirm not MWK-CARP
UPDATE documents SET case_file='Paracale-001'                           WHERE id=1161; -- "CARP Inocalla" CLOA, Registry of Deeds Cam. Norte — FLAG: confirm not MWK-CARP

-- ── NIBDC-001 (Northern Island Builders — mining; a SEPARATE client, A5) ─────
UPDATE documents SET case_file='NIBDC-001', matter_code='NIBDC-EXPA-000250' WHERE id IN (1162,1164,1165,1166,1168,1170,1173,1174,1181,1182,1184,1185);  -- EXPA-000250-V application set (MGB receipt, work programs, financials, page runs)
UPDATE documents SET case_file='NIBDC-001', matter_code='NIBDC-APSA-000322' WHERE id=1177;  -- Provincial GSO certification, Northern Island Builders, APSA No. 000322
UPDATE documents SET case_file='NIBDC-001'                                  WHERE id IN (1172,1179,1187);  -- MGB/DENR + Barangay Exciban mining correspondence (matter to confirm EXPA vs APSA)

-- ── Not case-relevant → Archive ─────────────────────────────────────────────
UPDATE documents SET case_file='Archive', matter_code='ARCHIVE-NOT-CASE-RELEVANT' WHERE id=477;  -- Philippine Racing Commission official contact letterhead (unrelated)

-- ── Flagged for review (unreadable / unidentifiable by content) → PENDING_TRIAGE ──
UPDATE documents SET case_file='PENDING_TRIAGE' WHERE id=519;  -- OCR reports a 4-person photo collage, not a land document
UPDATE documents SET case_file='PENDING_TRIAGE' WHERE id=523;  -- pure OCR garble (76 chars) — needs re-scan/re-OCR
UPDATE documents SET case_file='PENDING_TRIAGE' WHERE id=600;  -- bare ₱300 official receipt, no identifying party

COMMIT;

-- verify
SELECT coalesce(case_file,'(still NULL)') AS folder, count(*)
  FROM documents WHERE id IN (477,501,502,504,508,518,519,523,524,534,543,552,553,563,564,600,
                              2489,2844,1158,1159,1160,1161,1162,1164,1165,1166,1168,1170,1172,
                              1173,1174,1177,1179,1181,1182,1184,1185,1187)
  GROUP BY 1 ORDER BY 2 DESC;
