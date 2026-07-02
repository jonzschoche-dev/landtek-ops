-- Reproducible seed for the MWK-DLF-VOID investigation (matter + corpus + mapping + correspondence).
-- Applied live 2026-07-01. Run order matters (matter first). Idempotent per-section (DELETE then INSERT).
-- Run: docker exec -i n8n-postgres-1 psql -U n8n -d n8n < migrations/seed_MWK-DLF-VOID_investigation_2026-07-01.sql

-- ========== 1. MATTER ==========
INSERT INTO matters (matter_code, client_code, case_file, matter_type, title, description,
  court_or_agency, status, date_opened, lead_counsel, legal_theory, forum, factual_basis,
  subject_titles, respondent_entity_ids, plaintiff_entity_ids, current_stage, next_event,
  stage_notes, verification_status)
SELECT 'MWK-DLF-VOID', 'MWK-001', 'MWK-001', 'civil_recovery',
  'De la Fuente void-transfer recovery — T-4497 / T-32917 (Lot 2-X-6) estate',
  $d$Granular forensic investigation and recovery of MWK-estate lots conveyed under the limited, negotiate-only, later-revoked de la Fuente SPA. Sub-matter of MWK-001; sibling to MWK-TCT4497 (RD administrative) and MWK-LGU-RECOVERY (the 1995 Mercedes donation). Civil Case 26-360 (Balane) is the in-suit test case.$d$,
  'MTC Mercedes (CV 26-360) / RTC Camarines Norte / Registry of Deeds Camarines Norte',
  'active', '2026-07-01',
  'Atty. Bonifacio T. Barandon, Jr. (Barandon Law Offices, Daet)',
  $lt$Void agency conveyances: 1992 Munda SPA (PE-170453) was authority to NEGOTIATE only, not to sell (Arts. 1874/1878/1879; Cosmic Lumber; Alcantara v. Nido). Authority lapsed ~1995 and was registered-REVOKED 15-Aug-2005 (Arts. 1919-1921); deeds nonetheless issued through 2021. Salvador "Von" de la Fuente (never named in the SPA) signed the receipts. Principal received ZERO consideration -> no ratification. Remedies: declaration of nullity + cancellation of derivative titles + reconveyance (imprescriptible, Art. 1410; Tulauan) + accounting/turnover (Art. 1891; Domingo v. Domingo).$lt$,
  'MTC Mercedes / RTC Camarines Norte / Registry of Deeds Camarines Norte',
  $fb$Cesar M. de la Fuente held a genuine but negotiate-only SPA from the 3 MWK heirs (1992). It lapsed ~1995 (his own tax payments on the estate stop then) and was formally, registrably revoked 15-Aug-2005. Deeds of sale/confirmation kept issuing 1993-2021 across Lot 2-X-6 (T-32917); the 2016 deed built the Balane chain (TCT 079-2021002126). The RD certifies (doc:353) the underlying de la Fuente-era deeds are not on file. Patricia (principal) never received a peso.$fb$,
  '{T-4497,T-32917,T-52540,T-52536,079-2021002126,079-2021002127,T-33415,T-33776,T-34243,T-33686,T-33350,T-38838,T-47655,T-47656,T-47657,T-48336,T-69404,T-52354,T-147652}',
  '{1348,3469,15}', '{400,16,540}',
  'investigation_active',
  'Consolidated RD request: certified copies of T-47655/56/57/48336/69404 (holder ID) + non-availability cert for Dean (PE-214781) & Capistrano (PE-261974) deeds',
  $sn$Backed by drafts/branch2_recovery_roster_2026-07-01.md, drafts/delafuente_spa_recovery_analysis_2026-06-30.md, drafts/followup_tracker_complaint_and_ROD_2026-06-30.md, drafts/t4497_transaction_ledger_2026-06-30.md. Authorities: Cosmic Lumber (114311), Alcantara v Nido (165133), Tulauan v Mateo (248974), Domingo v Domingo (L-30573).$sn$,
  'verified'
WHERE NOT EXISTS (SELECT 1 FROM matters WHERE matter_code='MWK-DLF-VOID');
SELECT matter_code, matter_type, current_stage, array_length(subject_titles,1) AS titles FROM matters WHERE matter_code='MWK-DLF-VOID';

-- ========== 2. CORPUS ==========
DELETE FROM document_matter_links WHERE matter_code='MWK-DLF-VOID';
INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
SELECT v.doc_id, 'MWK-DLF-VOID', 'MWK-001', v.kind, 'verified', 'claude-investigation-build', '['||v.role||'] '||v.note
FROM (VALUES
  (39,'primary','title_face','T-4497 master CTC (13pp = the transaction ledger)'),
  (348,'chain_of_title','title_face','T-4497 CTC 2023-08-04'),(25,'chain_of_title','title_face','T-4497 CTC 2023-08-07'),
  (224,'chain_of_title','title_face','T-4497 CTC 2025-01-04'),(97,'chain_of_title','title_face','T-4497 1990 partial'),
  (329,'evidence','spa','1992 Munda SPA (negotiate-only) CTC'),(416,'evidence','spa','1992 Munda SPA — litigation Exhibit 7'),
  (38,'evidence','spa_inflated','2012 Cesar SPA recital — inflated authority, post-revocation'),
  (76,'evidence','revocation','Notice of Revocation — SPA revoked 15-Aug-2005'),
  (79,'evidence','revocation','RD confirmation: no conveyance used SPA on T-4497 post-2005'),
  (1134,'evidence','revocation','Cesar revocation (image)'),
  (353,'evidence','rd_certification','RD Certification of Non-Availability — 9 de la Fuente-era instruments not on file'),
  (1010,'evidence','admission','Salvador "Von" letter — admits de la Fuente administration/handling'),
  (92,'evidence','admission','2005 Hoppe email — principals never authorized/consented to Von'),
  (21,'chain_of_title','branch_hub','T-32917 (Lot 2-X-6) — the re-subdivided branch'),
  (427,'chain_of_title','contested','TCT 079-2021002126 (Gloria Balane) — complaint Exhibit C'),
  (368,'chain_of_title','family','TCT 079-2021002127 (Geraldine Hoppe, family sibling lot)'),
  (20,'chain_of_title','family','TCT 079-2021002127 CTC'),
  (48,'chain_of_title','contested','T-52540 cancelled (Balane predecessor)'),(96,'chain_of_title','contested','T-52540 certified copy'),
  (272,'chain_of_title','contested','T-52540'),(46,'chain_of_title','contested','T-52536 cancelled'),(323,'chain_of_title','contested','T-52536 heirs cancelled'),
  (315,'chain_of_title','target_t3','T-33415 Edgardo Santiago (RD no-record)'),(314,'chain_of_title','target_t3','T-33416/33415 Santiago 1992'),
  (318,'chain_of_title','target_t3','T-33776 Roscoe Leaño (RD no-record)'),(320,'chain_of_title','target_t3','T-33776 Leaño'),
  (321,'chain_of_title','target_t4','T-34243 Erlinda Tychingco'),(316,'chain_of_title','target_t4','T-33686 Jose Pascual Jr.'),
  (312,'chain_of_title','target_t4','T-33350 Elena Vergara'),(249,'chain_of_title','retain','T-38838 (Heirs of MWK — retain)'),
  (144,'chain_of_title','cluster','T-47655 (conjugal cluster — holder unresolved)'),
  (52,'chain_of_title','cluster','T-47656 (conjugal cluster)'),(309,'chain_of_title','cluster','T-47657 (conjugal cluster)'),
  (18,'chain_of_title','cluster','T-48336 (conjugal cluster)'),(325,'chain_of_title','cluster','T-52354 (holder unknown)'),
  (424,'evidence','pleading','COMPLAINT (accion reivindicatoria) — operative'),(425,'evidence','pleading','Complaint Exhibit A (notarized)'),
  (405,'evidence','pleading','Defendants Answer w/ affirmative defenses'),(771,'evidence','pleading','Plaintiff Reply — Salvador/no-authority'),
  (392,'evidence','pleading','Notice of Pre-trial Conference'),(423,'evidence','pleading','Court ORDER Civil Case 26-360')
) AS v(doc_id, kind, role, note)
WHERE EXISTS (SELECT 1 FROM documents d WHERE d.id=v.doc_id);
SELECT split_part(substring(note from '\[(.*?)\]'),']',1) role, count(*)
  FROM document_matter_links WHERE matter_code='MWK-DLF-VOID' GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) AS total FROM document_matter_links WHERE matter_code='MWK-DLF-VOID';

-- ========== 3. MAPPING ==========
-- PARTIES
DELETE FROM matter_parties WHERE matter_code='MWK-DLF-VOID';
INSERT INTO matter_parties (matter_code, entity_id, party_name, side, role, provenance_level, source_doc_id, source_excerpt) VALUES
 ('MWK-DLF-VOID',400,'Patricia Keesey Zschoche','plaintiff','principal (SPA grantor); received no proceeds','inferred_strong',329,'SPA grantor; principal in CV 26-360'),
 ('MWK-DLF-VOID',16,'Geraldine K. Hoppe','plaintiff','co-principal; also holds family lot TCT ...127','inferred_strong',329,'SPA grantor'),
 ('MWK-DLF-VOID',540,'Marcia Ellen Keesey','plaintiff','co-principal (SPA grantor)','inferred_strong',329,'SPA grantor'),
 ('MWK-DLF-VOID',1348,'Cesar M. de la Fuente','defendant','agent — negotiate-only 1992 SPA; deceased by 2020','inferred_strong',329,'named attorney-in-fact'),
 ('MWK-DLF-VOID',3469,'Salvador "Von" Osum Dela Fuente','defendant','son; NOT named in SPA; signed the receipts (alleged mastermind)','inferred_strong',771,'receipts signed by Salvador/Von, not Cesar'),
 ('MWK-DLF-VOID',15,'Gloria Balane','defendant','transferee — in-suit (TCT 079-2021002126, CV 26-360)','inferred_strong',427,'registered owner of ...126'),
 ('MWK-DLF-VOID',1229,'Edgardo Santiago','defendant','transferee (T-33415) — Tier 3, RD no-record deed','inferred_strong',353,'PE-172432 no record on file'),
 ('MWK-DLF-VOID',1209,'Roscoe Leaño','defendant','transferee (T-33776) — Tier 3, RD no-record deed','inferred_strong',353,'PE-174242 no record on file'),
 ('MWK-DLF-VOID',NULL,'Ruben P. Dean','defendant','transferee — Tier 2 (post-1995 deed PE-214781, 1997)','inferred_strong',21,'PE-214781 1997-11-26 Deed of Absolute Sale'),
 ('MWK-DLF-VOID',NULL,'Cristina B. Capistrano','defendant','transferee — Tier 2 (2003 deed PE-261974)','inferred_strong',21,'PE-261974 2003-01-23 Deed of Sale'),
 ('MWK-DLF-VOID',NULL,'Erlinda Tychingco','defendant','transferee (T-34243) — Tier 4','inferred_strong',321,'PE-176986 1994 deed'),
 ('MWK-DLF-VOID',NULL,'Jose Pascual Jr.','defendant','transferee (T-33686) — Tier 4','inferred_strong',316,'PE-173856 1994 deed'),
 ('MWK-DLF-VOID',NULL,'Municipality of Mercedes','third_party','LGU donee — 1995 donation (see MWK-LGU-RECOVERY)','inferred_strong',21,'PE-188451 1995 Deed of Donation');

-- CAUSES OF ACTION
DELETE FROM matter_causes WHERE matter_code='MWK-DLF-VOID';
INSERT INTO matter_causes (matter_code, cause, against_parties, basis, provenance_level, operative_doc_id, source_excerpt) VALUES
 ('MWK-DLF-VOID','Declaration of nullity of the de la Fuente deeds of sale (void — no written authority to SELL; SPA was negotiate-only)','Cesar & Salvador de la Fuente; all transferees','Civil Code Arts. 1874, 1878, 1879; Cosmic Lumber v CA (114311); Alcantara v Nido (165133)','inferred_strong',329,'SPA authorizes negotiation only'),
 ('MWK-DLF-VOID','All conveyances after 15-Aug-2005 void — agency terminated by registered revocation (and by agent death)','post-2005 transferees incl. Gloria Balane','Civil Code Arts. 1919-1921; registered Notice of Revocation','inferred_strong',76,'revoked 15-Aug-2005; post-date transactions void'),
 ('MWK-DLF-VOID','Cancellation of the derivative Torrens titles springing from the void deeds','current registrants of the T-32917 sub-lots','PD 1529 §107; Civil Code Art. 1409','inferred_strong',353,'underlying deeds not on file'),
 ('MWK-DLF-VOID','Reconveyance to the MWK estate (imprescriptible)','current holders','Civil Code Art. 1410; Heirs of Tulauan v Mateo (248974)','inferred_strong',353,'reconveyance on void deed does not prescribe'),
 ('MWK-DLF-VOID','Accounting & turnover of all sale proceeds (agent fiduciary duty; principal received nothing)','Cesar de la Fuente estate & Salvador de la Fuente','Civil Code Art. 1891; Domingo v Domingo (L-30573)','inferred_strong',1010,'agent must account & remit');

-- TITLE LINKS
DELETE FROM title_matter_links WHERE matter_code='MWK-DLF-VOID';
INSERT INTO title_matter_links (title_no, matter_code, relationship, notes) VALUES
 ('T-4497','MWK-DLF-VOID','subject','mother title — transaction ledger (doc:39)'),
 ('T-32917','MWK-DLF-VOID','subject','branch hub — Lot 2-X-6, de la Fuente re-subdivision'),
 ('T-52540','MWK-DLF-VOID','subject','Balane predecessor (cancelled)'),
 ('079-2021002126','MWK-DLF-VOID','subject','Gloria Balane — IN SUIT (CV 26-360)'),
 ('079-2021002127','MWK-DLF-VOID','subject','Geraldine Hoppe — family lot (retain)'),
 ('T-33415','MWK-DLF-VOID','subject','Santiago — Tier 3 (RD no-record deed)'),
 ('T-33776','MWK-DLF-VOID','subject','Leaño — Tier 3 (RD no-record deed)'),
 ('T-34243','MWK-DLF-VOID','subject','Tychingco — Tier 4 (1994 deed)'),
 ('T-33686','MWK-DLF-VOID','subject','Pascual — Tier 4 (1994 deed)'),
 ('T-33350','MWK-DLF-VOID','subject','Vergara — Tier 4'),
 ('T-38838','MWK-DLF-VOID','subject','Heirs of MWK — retain (32,448 sqm)'),
 ('T-47655','MWK-DLF-VOID','subject','conjugal cluster — holder UNRESOLVED (~50,000 sqm total)'),
 ('T-47656','MWK-DLF-VOID','subject','conjugal cluster'),
 ('T-47657','MWK-DLF-VOID','subject','conjugal cluster'),
 ('T-48336','MWK-DLF-VOID','subject','conjugal cluster'),
 ('T-69404','MWK-DLF-VOID','subject','conjugal cluster'),
 ('T-52354','MWK-DLF-VOID','subject','holder unknown');

-- AUTHORITIES (link the 4 verified cases to this matter)
DELETE FROM matter_authorities WHERE matter_code='MWK-DLF-VOID';
INSERT INTO matter_authorities (matter_code, authority_id, element_code, relevance, note, provenance_level)
SELECT 'MWK-DLF-VOID', la.id, e.element_code, e.relevance, e.note, 'inferred_strong'
FROM legal_authorities la JOIN (VALUES
  ('G.R. No. 114311 (Nov. 29, 1996)','agency_scope','negotiate ≠ sell; sale beyond SPA scope void ipso jure','core void-deed authority'),
  ('G.R. No. 165133 (Apr. 19, 2010)','art1874_written_authority','land sale by agent w/o written authority void; no ratification','core void-deed authority'),
  ('G.R. No. 248974 (Sept. 7, 2022)','reconveyance_imprescriptible','reconveyance on void deed imprescriptible','defeats prescription/laches'),
  ('G.R. No. L-30573 (Oct. 29, 1971)','agent_duty_account','agent must account/remit; forfeits compensation','anchors accounting claim')
) AS e(cite,element_code,relevance,note) ON la.citation=e.cite AND la.source='lawphil';

SELECT (SELECT count(*) FROM matter_parties WHERE matter_code='MWK-DLF-VOID')||' parties, '||
       (SELECT count(*) FROM matter_causes WHERE matter_code='MWK-DLF-VOID')||' causes, '||
       (SELECT count(*) FROM title_matter_links WHERE matter_code='MWK-DLF-VOID')||' titles, '||
       (SELECT count(*) FROM matter_authorities WHERE matter_code='MWK-DLF-VOID')||' authorities' AS mapping;

-- ========== 4. CORRESPONDENCE ==========
DELETE FROM correspondence_events WHERE matter_code='MWK-DLF-VOID';
INSERT INTO correspondence_events (matter_code, author, addressee, subject, claimed_date, channel, sent_to, delivery_status, received_date, gap_flag, proofs, all_verified) VALUES
-- HISTORICAL (grounded)
('MWK-DLF-VOID','Keesey Heirs','Register of Deeds, Camarines Norte','Notice of Revocation of Cesar de la Fuente SPA (eff. 15-Aug-2005)','2020-09-25','letter','RD Daet','answered','2020-09-30','CLOSED','["doc:76","doc:79"]',true),
('MWK-DLF-VOID','Jonathan Zschoche','Register of Deeds, Camarines Norte','Request: complete certified records on T-52540 + subsequent titles','2025-02-25','letter','RD Daet','sent',NULL,'NO T-52540-SPECIFIC ANSWER','["doc:357"]',false),
('MWK-DLF-VOID','Jonathan Zschoche','Register of Deeds, Camarines Norte','Request: transaction evidence for OCT-111 / TCT-4497','2025-04-29','letter','RD Daet','answered','2025-06-23','CLOSED','["doc:296","doc:297","doc:303"]',true),
('MWK-DLF-VOID','Jonathan Zschoche','Register of Deeds, Camarines Norte','RA 11032 follow-up on the 29-Apr request','2025-05-26','letter','RD Daet','answered','2025-06-23','CLOSED','["doc:333","doc:355"]',true),
('MWK-DLF-VOID','Register of Deeds, Camarines Norte','Jonathan Zschoche','CERTIFICATION: 9 de la Fuente-era instruments NOT on file (T-32917/T-31298)','2025-06-23','letter','Jonathan (inbound)','received','2025-06-23','KEY EVIDENCE — upgrade to sealed cert','["doc:353"]',true),
('MWK-DLF-VOID','Jonathan Zschoche','Mercedes Municipal Assessor (Gemma Abla)','Request: tax declaration / ARP GR-2023-II-07-001-00256 records','2025-05-27','letter','Mercedes Assessor','drafted_unsent',NULL,'NEVER SENT — finalize','["doc:332"]',false),
-- PLANNED CAMPAIGN (the directive)
('MWK-DLF-VOID','Counsel / Jonathan','Register of Deeds, Camarines Norte','Request formal SEALED Certification of Non-Availability for the 9 PE entries (upgrade doc:353 for court)',NULL,'letter','RD Daet','planned',NULL,'OUTSTANDING — priority 1','[]',false),
('MWK-DLF-VOID','Counsel / Jonathan','Register of Deeds, Camarines Norte','CONSOLIDATED: CTCs of T-47655/47656/47657/48336/69404 (identify ~50,000 sqm holder) + non-availability cert for Dean (PE-214781) & Capistrano (PE-261974) deeds',NULL,'letter','RD Daet','planned',NULL,'OUTSTANDING — priority 1 (unblocks the dark cluster)','[]',false),
('MWK-DLF-VOID','Counsel / Jonathan','Register of Deeds, Camarines Norte','Chaser: T-52540 certified annotations / non-availability (re 25-Feb-2025 unanswered)',NULL,'letter','RD Daet','planned',NULL,'OUTSTANDING — priority 2','[]',false),
('MWK-DLF-VOID','Jonathan Zschoche','RTC Daet — Office of the Clerk of Court (Genesis Ibasco)','Confirm retrieval of transaction documentation (re 27-May-2025 request)',NULL,'letter','RTC-OCC Daet','planned',NULL,'OUTSTANDING — priority 3','["doc:1019"]',false);
SELECT delivery_status, count(*) FROM correspondence_events WHERE matter_code='MWK-DLF-VOID' GROUP BY 1 ORDER BY 2 DESC;

-- ========== 5. TAX DECLARATIONS (added 2026-07-01; excludes contaminants doc:443 court-filing-fee, doc:75 Mambungalon separate property) ==========
INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
SELECT d.id, 'MWK-DLF-VOID', 'MWK-001', 'evidence', 'verified', 'claude-investigation-build',
  '[tax_dec] '||coalesce(d.doc_date_norm::text,'?')||' '||left(coalesce(d.smart_filename,d.document_title,d.original_filename),44)
FROM documents d
WHERE (d.smart_filename ~* 'tax_dec|tax_declaration|property_tax|assessment|tax_statement|property_declaration|real_property'
       OR d.document_type ~* 'tax_declaration|real_property_assessment')
  AND coalesce(d.case_file,'') NOT ILIKE '%ARTA%'
  AND d.id NOT IN (443, 75)  -- 443 = court filing-fee assessment; 75 = Mambungalon (separate property, not T-4497)
  AND NOT EXISTS (SELECT 1 FROM document_matter_links l WHERE l.doc_id=d.id AND l.matter_code='MWK-DLF-VOID');
