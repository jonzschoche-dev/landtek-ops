-- deploy_813_title_registry_leads.sql — add the reenrich-surfaced high-value titles to the registry,
-- each with EARNED provenance (source doc + verbatim excerpt). NO title_chain edges are created — registry
-- entries only; chain relationships require their own verified evidence. Idempotent (NOT EXISTS guards).
-- Skipped as insufficient-evidence leads (excerpts are OCR garble): T-52416, T-53602.

BEGIN;

-- 1. 079-2021002126 — GLORIA BALANE'S ACTUAL CONTESTED TITLE (the flagship; referenced by 61 docs, absent
--    from the registry while ...2127 (Hoppe) was present). VERIFIED: doc 388 (18 Aug 2025) states verbatim:
--    "Transfer Certificate of Title No. T-52540 ... has been cancelled and that a new Transfer Certificate
--    of Title No. 079-2021002126 has been illegally issued in the name of Gloria H. Balane."
INSERT INTO titles (tct_number, case_file, registrant_name_raw, status, source_doc_id,
                    provenance_level, provenance_notes, lifecycle_status, notes)
SELECT '079-2021002126', 'MWK-001', 'Gloria H. Balane', 'contested', 388, 'verified',
       'Doc 388 (18 Aug 2025): "Transfer Certificate of Title No. T-52540 in the name of the real and lawful co-owners of the subject property has been cancelled and that a new Transfer Certificate of Title No. 079-2021002126 has been illegally issued in the name of Gloria H. Balane." Same citation as T-52540''s verified cancelled status.',
       'contested',
       'THE contested Balane title in MWK-CV26360 (Lot 2-X-6-I-4-C-1). Issued 2021 from cancelled T-52540. NB: ...2127 is Geraldine Hoppe''s — do not conflate. Surfaced by reenrich unknown_titles (61 citing docs, deploy_812).'
WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = '079-2021002126');

-- Record the cancellation on T-52540's side too — same doc-388 verified citation.
UPDATE titles SET cancelled_by_title = '079-2021002126',
                  updated_at = now()
 WHERE tct_number = 'T-52540' AND coalesce(cancelled_by_title,'') = '';

-- 2. T-50192 — a TCT the DEFENSE submitted as their Exhibit 3 in CV-26360 (doc 412, government-issued PDF).
INSERT INTO titles (tct_number, case_file, status, source_doc_id, provenance_level, provenance_notes, notes)
SELECT 'T-50192', 'MWK-001', 'unverified', 412, 'inferred_strong',
       'Doc 412 = Balane defense "Exhibit 3 - TCT No. T-50192.pdf" (Answer exhibit set, CV-26360); doc 958 chronology dates it August 15, 1999.',
       'Submitted by DEFENDANTS as Answer Exhibit 3 in MWK-CV26360 — opposition evidence; face not yet extracted. Surfaced by reenrich (14 citing docs).'
WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = 'T-50192');

-- 3. The doc-673 CARP/just-compensation family group — one verbatim passage names them together:
--    "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494 which is located in
--    Mercedes and San Vicente, Camarines Norte" + valuation table "T-4501(T-30583, T-4502 (T-30681),
--    T-4503 (T-30682)". Civil Case 6839 (just compensation / Landbank CARP) context.
--    SEPARATION NOTE: NOT T-4497 derivatives (San Vicente/Cabanbanan is a SEPARATE matter — standing rule).
INSERT INTO titles (tct_number, case_file, status, source_doc_id, provenance_level, provenance_notes, notes)
SELECT x.t, 'MWK-001', 'unverified', 673, 'inferred_strong',
       'Doc 673: "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494 which is located in Mercedes and San Vicente, Camarines Norte"; valuation table pairs T-4501(T-30583), T-4502(T-30681), T-4503(T-30682). CARP/just-compensation (Civil Case 6839) context.',
       'CARP/CV6839 family group. NOT a verified T-4497 derivative — Mercedes/San Vicente parcels are separate matters (standing separation rule); registry entry only, no chain edge.'
  FROM (VALUES ('T-4494'),('T-4501'),('T-4502'),('T-4503'),('T-30583'),('T-30682')) x(t)
 WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = x.t);

-- 4. 079-2018001329 — named as family property in our own RD request (doc 358): "...including but not
--    limited to T-2021002126, T-2021002127, and T-079-2018001329, which pertain to my family's property."
INSERT INTO titles (tct_number, case_file, status, source_doc_id, provenance_level, provenance_notes, notes)
SELECT '079-2018001329', 'MWK-001', 'unverified', 358, 'inferred_strong',
       'Doc 358 (RD records request): "including but not limited to T-2021002126, T-2021002127, and T-079-2018001329, which pertain to my family''s property."',
       'Claimed family-property title in the RD title-history thread; face not yet obtained. Surfaced by reenrich (10 citing docs).'
WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = '079-2018001329');

-- 5. 079-2010000663 — from an RD annotation on a held title (doc 1082): "TITLE IS PARTIALLY CANCELLED AND
--    ISSUING IN LIEU THEREOF TCT number(s) 079-2010000663 — Atty. Emmanuel Enriquez Tuy, Registrar of Deeds".
INSERT INTO titles (tct_number, case_file, status, source_doc_id, provenance_level, provenance_notes, notes)
SELECT '079-2010000663', 'MWK-001', 'unverified', 1082, 'inferred_strong',
       'Doc 1082 annotation: "TITLE IS PARTIALLY CANCELLED AND ISSUING IN LIEU THEREOF TCT number(s) 079-2010000663 — Atty. Emmanuel Enriquez Tuy, Registrar of Deeds."',
       'Derivative issued in lieu on partial cancellation per RD annotation; PARENT NOT RECORDED here (needs the annotated title''s face read) — no chain edge fabricated.'
WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = '079-2010000663');

-- 6. T-1722 — VICENTE INOCALLA's title (doc 634 ledger: "Vicente Inocalla c/o Casper Inocalla | T-1722").
--    PARACALE-001 CLIENT — registered under the correct client (A5); the engine's title matching is being
--    client-scoped in the same deploy so this cannot leak into MWK significance.
INSERT INTO titles (tct_number, case_file, status, source_doc_id, provenance_level, provenance_notes, notes)
SELECT 'T-1722', 'Paracale-001', 'unverified', 634, 'inferred_strong',
       'Doc 634 ledger row: "Vicente Inocalla c/o Casper Inocalla | T-1722 / .4595 A".',
       'Inocalla family title (Paracale-001 client — NOT MWK). Relates to PAR estate work; see PAR-TCT1616 matter for the family title thread.'
WHERE NOT EXISTS (SELECT 1 FROM titles WHERE tct_number = 'T-1722');

COMMIT;

SELECT tct_number, case_file, provenance_level, source_doc_id, status FROM titles
 WHERE tct_number IN ('079-2021002126','T-50192','T-4494','T-4501','T-4502','T-4503','T-30583','T-30682',
                      '079-2018001329','079-2010000663','T-1722') ORDER BY tct_number;
