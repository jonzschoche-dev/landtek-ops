-- fix_cross_client_doc_links_deploy674.sql
-- WHY (2026-07-04): client_dependability.py surfaced a live, client-visible CLIENT-SEPARATION
-- breach — documents whose OWN documents.case_file belongs to one client were linked via
-- document_matter_links to ANOTHER client's matters and RENDERED on that client's matter-detail
-- page. 20 cross_client_doc FAILs (11 on MWK-001, 9 on Paracale-001) + 1 downstream leak.
--
-- Each of the 20 flagged (doc, foreign-matter) links was adjudicated PER-DOC against the verified
-- record (extracted text + the doc's own home matter). NOT a bulk delete. Two resolutions:
--   (A) LINK is wrong  -> DELETE the foreign link (the doc genuinely belongs to its case_file
--       client; a mis-tagged autolink pointed it at the other client's matter).
--   (B) case_file is wrong (a genuine mis-file, deploy_485 pattern) -> RE-FILE case_file so it
--       matches its true client; keep the correct link.
--
-- Idempotent + transactional. A verification SELECT is printed AFTER commit.
-- Reversible: the pre-run state is captured in scratchpad/before_snapshot.tsv.

\set ON_ERROR_STOP on
BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- (A) DELETE wrong cross-client links — doc belongs to its case_file client.
-- ─────────────────────────────────────────────────────────────────────────────
-- MWK-TCT4497 mis-links onto Paracale (Inocalla) documents (deploy_279 backfill artifact):
--   635 Vicente Inocalla Labo tax dec · 637 Allan Inocalla affidavit-of-loss OCT P-1616
--   (home: PAR-TCT1616) · 654 Inocalla birth/murder record (home: PAR-INOCALLA-MURDERS)
--   661 BP22 People v. Servidad affidavit of service (not MWK)
DELETE FROM document_matter_links WHERE doc_id=635  AND matter_code='MWK-TCT4497';
DELETE FROM document_matter_links WHERE doc_id=637  AND matter_code='MWK-TCT4497';
DELETE FROM document_matter_links WHERE doc_id=654  AND matter_code='MWK-TCT4497';
DELETE FROM document_matter_links WHERE doc_id=661  AND matter_code='MWK-TCT4497';
-- MWK-OP-PETITION mis-links onto Paracale documents:
--   668 Marilou Villafria Inocalla birth cert · 670 LRA registration form (cf=Paracale, no MWK content)
DELETE FROM document_matter_links WHERE doc_id=668  AND matter_code='MWK-OP-PETITION';
DELETE FROM document_matter_links WHERE doc_id=670  AND matter_code='MWK-OP-PETITION';
-- MWK-ESTATE mis-links onto Paracale/junk documents (photos + a screenplay, no MWK content):
--   931/940/941/955 images · 944 'Shatter.pdf' film logline (not an estate doc)
DELETE FROM document_matter_links WHERE doc_id=931  AND matter_code='MWK-ESTATE';
DELETE FROM document_matter_links WHERE doc_id=940  AND matter_code='MWK-ESTATE';
DELETE FROM document_matter_links WHERE doc_id=941  AND matter_code='MWK-ESTATE';
DELETE FROM document_matter_links WHERE doc_id=944  AND matter_code='MWK-ESTATE';
DELETE FROM document_matter_links WHERE doc_id=955  AND matter_code='MWK-ESTATE';
-- The MWK omnibus 'bible' (958) is a genuine MWK doc dual-linked into a Paracale matter — drop the
-- one Paracale link, keep its five MWK links:
DELETE FROM document_matter_links WHERE doc_id=958  AND matter_code='PAR-CV13-131220';
-- NIBDC 'Molina Recomendation' (1163) is an NIBDC doc dual-linked into Paracale — drop the Paracale
-- link, keep its NIBDC-APSA-000322 home:
DELETE FROM document_matter_links WHERE doc_id=1163 AND matter_code='PAR-CAPACUAN';

-- ─────────────────────────────────────────────────────────────────────────────
-- (B) RE-FILE genuine mis-files, then correct their links.
-- ─────────────────────────────────────────────────────────────────────────────
-- 1295 'Brgy Capacuan Business Clearance' (Senen V. Inocalla) is a Paracale document mis-cased as
-- MWK-001. Re-file to Paracale-001 — its PAR-CAPACUAN link is then correct (cf == matter client).
UPDATE documents SET case_file='Paracale-001' WHERE id=1295 AND case_file='MWK-001';

-- 1167/1169/1171/1175/1176/1180 are NIBDC APSA-000322 mining-application documents (NIBDC financials,
-- MGB submissions, posting certifications — the EXPA-000250-V bundle) mis-cased as MWK-001 and
-- mis-linked onto Paracale's PAR-CAPACUAN (and, for 1171/1176, onto MWK-OP-PETITION too). They belong
-- to neither proof client. Re-file to NIBDC-001, drop every MWK/Paracale link, and link to their true
-- home NIBDC-APSA-000322 (mirrors sibling doc 1163). This also removes the latent NIBDC-on-MWK render.
UPDATE documents SET case_file='NIBDC-001'
 WHERE id IN (1167,1169,1171,1175,1176,1180) AND case_file='MWK-001';

DELETE FROM document_matter_links
 WHERE doc_id IN (1167,1169,1171,1175,1176,1180)
   AND matter_code IN ('PAR-CAPACUAN','MWK-OP-PETITION');

INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
SELECT v.doc_id, 'NIBDC-APSA-000322', 'NIBDC-001', 'evidence', 'inferred_strong', 'deploy_674_separation_fix',
       'Re-homed from mis-cased MWK-001 / mis-linked PAR-CAPACUAN: NIBDC APSA-000322 record'
  FROM (VALUES (1167),(1169),(1171),(1175),(1176),(1180)) AS v(doc_id)
ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- (A2) Second batch — the same defect on 13 more documents that sat BELOW the
-- harness report's top-14 gap cutoff (MWK-001 alone carried 25 correctness fails).
-- All 13 are Inocalla/Paracale titles or NIBDC letters that an autolink over-linked
-- onto MWK matters (MWK-ESTATE / MWK-CV26360). A full-text scan confirmed 12 of them
-- carry ZERO MWK identifier (no Keesey/Worrick/T-4497/Balane/Mercedes) -> DELETE the
-- stray MWK link. 798/803 keep their real NIBDC homes.
DELETE FROM document_matter_links WHERE doc_id=461 AND matter_code='MWK-ESTATE';   -- NIBDC MGB request letter
DELETE FROM document_matter_links WHERE doc_id=636 AND matter_code='MWK-ESTATE';   -- Inocalla Labo Civil Case 4992
DELETE FROM document_matter_links WHERE doc_id=658 AND matter_code='MWK-CV26360';  -- Inocalla Lot 819 Labo TCT
DELETE FROM document_matter_links WHERE doc_id=659 AND matter_code='MWK-ESTATE';   -- Senen Inocalla TCT Labo
DELETE FROM document_matter_links WHERE doc_id=662 AND matter_code='MWK-ESTATE';   -- Inocalla (Vicente/Ante) appraisals
DELETE FROM document_matter_links WHERE doc_id=664 AND matter_code='MWK-ESTATE';   -- Cipriana Inocalla Paracale OR
DELETE FROM document_matter_links WHERE doc_id=665 AND matter_code='MWK-CV26360';  -- Paracale OCT
DELETE FROM document_matter_links WHERE doc_id=666 AND matter_code='MWK-CV26360';  -- Paracale free-patent OCT
DELETE FROM document_matter_links WHERE doc_id=798 AND matter_code='MWK-ESTATE';   -- NIBDC MGB doc request (keeps NIBDC-EXPA-000250)
DELETE FROM document_matter_links WHERE doc_id=803 AND matter_code='MWK-ESTATE';   -- NIBDC due-diligence auth (keeps NIBDC-APSA-000322)
DELETE FROM document_matter_links WHERE doc_id=804 AND matter_code='MWK-ESTATE';   -- 'Inocalla Estate' legal-proposal request
DELETE FROM document_matter_links WHERE doc_id=930 AND matter_code='MWK-ESTATE';   -- image, no MWK signal

-- 461 is an NIBDC document (NIBDC President's request for the EXPA-000322-V case file) mis-cased as
-- Paracale-001. Re-file to its true client so it can never leak onto Paracale later either.
UPDATE documents SET case_file='NIBDC-001' WHERE id=461 AND case_file='Paracale-001';

-- 815 is the ONE genuine mis-file in the batch: Jonathan Paul Zschoche's sworn AFFIDAVIT OF DENIAL in
-- ARTA Case CTN SL-2025-1008-0690 vs Engr. Erwin Balane, Municipal Engineer of Mercedes, re "TCT No.
-- 4497 / OCT No. 111, Barangay 1 Poblacion Mercedes" — unambiguously an MWK document (its MWK-ARTA/
-- MWK-CV26360 links are CORRECT). Re-file MWK-001; the links then match and the breach clears.
UPDATE documents SET case_file='MWK-001' WHERE id=815 AND case_file='Paracale-001';

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFY — every touched doc must now have ZERO link into a matter whose client
-- differs from the doc's case_file. Expect 0 rows.
-- ─────────────────────────────────────────────────────────────────────────────
SELECT d.id, d.case_file, l.matter_code, m.client_code
  FROM documents d
  JOIN document_matter_links l ON l.doc_id=d.id
  JOIN matters m ON m.matter_code=l.matter_code
 WHERE d.id IN (461,635,636,637,654,658,659,661,662,664,665,666,668,670,798,803,804,815,
                930,931,940,941,944,955,958,1163,1167,1169,1171,1175,1176,1180,1295)
   AND d.case_file IS NOT NULL AND d.case_file <> ''
   AND d.case_file <> 'Owner'
   AND m.client_code <> d.case_file
   AND d.case_file IN (SELECT client_code FROM clients
                        WHERE COALESCE(client_code,'') NOT IN ('','Owner','Archive','PENDING_TRIAGE'))
 ORDER BY d.id;
