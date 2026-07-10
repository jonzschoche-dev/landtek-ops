-- deploy_825_title_registry_leads.sql — add the reenrich unknown_titles LEADS to the titles registry,
-- each with a cited source doc + verbatim excerpt in provenance_notes. NO title_chain edges are created —
-- registry membership only; chain relationships stay a separate, verified-tier process.
-- Grades: 079-2021002126 enters 'verified' (the SAME doc-388 quote that already grounds T-52540's verified
-- cancelled-status row names it); all others 'inferred_strong' (mechanically excerpt-grounded, not human-verified).
-- A5: T-1722 is an INOCALLA title (source doc 634 is Paracale-001) → registered under Paracale-001, never MWK.
-- Idempotent: ON CONFLICT (tct_number, case_file) DO NOTHING (composite PK; never clobber an existing row).

BEGIN;

INSERT INTO titles (tct_number, case_file, registrant_name_raw, status, source_doc_id, provenance_level, provenance_notes, notes)
VALUES
('079-2021002126', 'MWK-001', 'Gloria H. Balane', 'contested', 388, 'verified',
 'doc 388 (final demand letter, 18 Aug 2025): "Transfer Certificate of Title No. T-52540 ... has been cancelled and that a new Transfer Certificate of Title No. 079-2021002126 has been illegally issued in the name of Gloria H. Balane." Same quote grounds T-52540''s verified cancelled status. Operator-confirmed: Balane holds ...126 (not ...127, which is the Hoppe family lot).',
 'THE contested Balane title in Civil Case 26-360 (Lot 2-X-6-I-4-C-1). Referenced by 61 corpus docs; was absent from the registry until the deploy_812 unknown-titles lead surfaced it.'),

('T-52416', 'MWK-001', 'Dolores Vela', 'active', 260, 'inferred_strong',
 'doc 260 (RD information request form): "T-49061(cancelled) Heirs of Mary Worrick ... T-52416 (Connected) Dolores Vela, 2-X-6-I-4-B, PSD 05-026197"',
 'RD-stated as connected to cancelled T-49061 (Heirs of MWK); holder Dolores Vela is one of the 20 named transferees. Connection claim NOT chain-verified.'),

('T-53602', 'MWK-001', 'Arnel Mabeza', 'active', 266, 'inferred_strong',
 'doc 266 (RD information request form): "T-52539 canceled Heirs of Mary Worrick ... T-53602 Arnel Mabeza (Connected), 2-X-6-I-4-A"',
 'RD-stated as connected to cancelled T-52539 (Heirs of MWK); holder Arnel Mabeza is one of the 20 named transferees. Connection claim NOT chain-verified.'),

('T-50192', 'MWK-001', NULL, 'unknown', 412, 'inferred_strong',
 'doc 412 IS a copy of the title itself: defendants'' "Exhibit 3 - TCT No. T-50192.pdf" filed with the Balane Answer in Civil Case 26-360.',
 'Defendants'' Exhibit 3. Face copy held in corpus; not yet heightened-OCR extracted; registrant TBD from face read.'),

('T-4501', 'MWK-001', NULL, 'unknown', 673, 'inferred_strong',
 'doc 673 (Just Compensation vol 3): "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494 which is located in Mercedes and San Vicente, Camarines Norte" + table "T-4501(T-30583"',
 'Just-compensation (CV-6839 context) title. Parenthetical pairing with T-30583 unverified.'),

('T-4502', 'MWK-001', NULL, 'unknown', 673, 'inferred_strong',
 'doc 673 (Just Compensation vol 3): "T-4502 (T-30681)" and "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494"',
 'Just-compensation (CV-6839 context) title. Parenthetical pairing with T-30681 unverified.'),

('T-4503', 'MWK-001', NULL, 'unknown', 673, 'inferred_strong',
 'doc 673 (Just Compensation vol 3): "T-4503 (T-30682)" and "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494"',
 'Just-compensation (CV-6839 context) title. Parenthetical pairing with T-30682 unverified.'),

('T-30682', 'MWK-001', NULL, 'unknown', 673, 'inferred_strong',
 'doc 673 (Just Compensation vol 3): appears as the parenthetical pair "T-4503 (T-30682)"',
 'Referenced by 15 corpus docs. Relationship to T-4503 unverified.'),

('T-4494', 'MWK-001', NULL, 'unknown', 673, 'inferred_strong',
 'doc 673 (Just Compensation vol 3): "under Transfer Certificates of Title Nos. T-4501, T-4502, T-4503 and T-4494 which is located in Mercedes and San Vicente, Camarines Norte"',
 'SEPARATE PROPERTY (Cabanbanan/San Vicente) — NOT a verified T-4497 derivative; treat as its own matter (standing CLAUDE.md guard). Registry membership only.'),

('079-2018001329', 'MWK-001', NULL, 'unknown', 358, 'inferred_strong',
 'doc 358 (2020-09-30 Request for Records, Mary Worrick Keesey): "including but not limited to T-2021002126, T-2021002127, and T-079-2018001329, which pertain to my family''s property"',
 'Named in a family records request alongside the contested ...2126/...2127 pair.'),

('079-2010000663', 'MWK-001', NULL, 'unknown', 1082, 'inferred_strong',
 'doc 1082 (Supplemental Affidavit and Manifestation 1378): RD annotation "TITLE IS PARTIALLY CANCELLED AND ISSUING IN LIEU THEREOF TCT number(s) 079-2010000663 — Atty. Emmanuel Enriquez Tuy, Registrar of Deeds"',
 'Issued-in-lieu title per a quoted RD partial-cancellation annotation; parent title TBD.'),

('T-1722', 'Paracale-001', 'Vicente Inocalla', 'unknown', 634, 'inferred_strong',
 'doc 634 (Calaburnay.pdf, Paracale-001): "Vicente Inocalla c/o Casper Inocalla | T-1722 / .4595"',
 'INOCALLA (Paracale-001) title — A5: registered under the Inocalla client, never MWK.')
ON CONFLICT (tct_number, case_file) DO NOTHING;

-- T-52540 → ...2126 cancellation linkage: the SAME verified doc-388 quote already in T-52540's
-- provenance_notes states it explicitly; record it on the row (no title_chain edge).
UPDATE titles SET cancelled_by_title = '079-2021002126',
                  updated_at = now()
 WHERE tct_number = 'T-52540' AND cancelled_by_title IS NULL AND verification_lock IS NULL;

COMMIT;

SELECT tct_number, case_file, registrant_name_raw, status, provenance_level, source_doc_id
  FROM titles WHERE tct_number IN ('079-2021002126','T-52416','T-53602','T-50192','T-4501','T-4502','T-4503','T-30682','T-4494','079-2018001329','079-2010000663','T-1722') ORDER BY tct_number;