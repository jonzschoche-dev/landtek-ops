-- Inocalla holdings / title inventory (Paracale-001)
-- Source: holdings-inventory table in docs 520/634/669; clean copy confirmed by operator 2026-06-13.
-- provenance_level = inferred_strong (summary table, not the individual certificates).
-- Upgrade a row to 'verified' when its actual certificate is pulled + quoted.
BEGIN;

INSERT INTO titles
  (tct_number, case_file, registrant_name_raw, registrant_canonical, area_sqm, location,
   source_doc_id, provenance_level, provenance_notes, notes)
VALUES
 ('T-3897','Paracale-001','Vicente Inocalla (Vicente Jr., Cipriana, Jesus Inocalla)','Vicente Inocalla', 230935,'Lot 1, Psu-152027',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Partition (CC B-5625) Parcel 7: San Rafael, Jose Panganiban; awarded Cipriana/Vicente Jr./Jesus in equal 1/3 proportion'),
 ('T-3424','Paracale-001','Beatriz Villafria (Marilou & Allan)','Beatriz Villafria', 225178,'Lot 1, Psu-152156',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Partition Parcel 2: San Rafael, Jose Panganiban; to Marilou & Allan'),
 ('T-5656','Paracale-001','Vicente Inocalla, Sr. (Herbert & Senen)','Vicente Inocalla Sr.', 197727,'Lot 2-B (LRC) Psd-56979',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Awarded Herbert & Senen'),
 ('T-20754','Paracale-001','DBP / (Casper Inocalla)','Development Bank of the Philippines', 102928,'Lot 2, Psu-14364',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','DBP-held (mortgage/foreclosure); assoc. Casper Inocalla'),
 ('T-29841','Paracale-001','Marilou Inocalla','Marilou Inocalla', 23513,'Lot 9-A, Psd-05-012242',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13',NULL),
 ('P-1617','Paracale-001','Jesus Inocalla','Jesus Inocalla', 234356,'Lot 8, Psu-143364 Amd.',634,'inferred_strong','Inocalla holdings inventory (Lot #6); operator-confirmed 2026-06-13. SOLE title in the name of Jesus Inocalla. Standalone P-1617 certificate NOT yet ingested — upgrade to verified on certificate.','THE 23-ha lot titled to Jesus Inocalla (23.4356 has). Patent-series title.'),
 ('ARP-021-0312','Paracale-001','Vicente Inocalla','Vicente Inocalla', 180003,'Lot 6, Psu-143364',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','ARP / tax declaration (NOT a Torrens title number)'),
 ('T-20756','Paracale-001','DBP / (Casper Inocalla)','Development Bank of the Philippines', 189591,'Lot 10, Psu-143364',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','DBP-held; assoc. Casper Inocalla'),
 ('T-20757','Paracale-001','DBP / (Casper Inocalla)','Development Bank of the Philippines', 235845,'Lot 5, Psu-143363 Amd.',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','DBP-held; assoc. Casper Inocalla'),
 ('T-20755','Paracale-001','DBP / (Casper Inocalla)','Development Bank of the Philippines', 111486,'H-128572',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','DBP-held; assoc. Casper Inocalla'),
 ('P-1616','Paracale-001','Allan Inocalla','Allan Inocalla', 152069,'Lot 4, Psu-143364',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Certificate in corpus (docs 633/639, TCT/OCT-1616)'),
 ('P-1516','Paracale-001','Vicente Inocalla, Jr.','Vicente Inocalla Jr.', 228024,'Lot 7, Psu-143364 Amd.',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13',NULL),
 ('P-1615','Paracale-001','Cipriana Inocalla','Cipriana Inocalla', 230238,'Lot 1, Psu-143364 Amd.',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13',NULL),
 ('T-2194','Paracale-001','Vicente Inocalla / (Senen Inocalla)','Vicente Inocalla', 133690,'H-44920',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Partition Parcel 12: awarded Senen'),
 ('T-4185','Paracale-001','Beatriz Villafria / (Herbert Inocalla)','Beatriz Villafria', 113042,'Lot 3, Psu-143364',634,'inferred_strong','Inocalla holdings inventory; operator-confirmed 2026-06-13','Partition Parcel 3: San Rafael, Jose Panganiban; awarded Herbert');

COMMIT;

-- verify
SELECT tct_number, registrant_canonical, round(area_sqm/10000.0,4) AS hectares, location
FROM titles WHERE case_file='Paracale-001' ORDER BY tct_number;
