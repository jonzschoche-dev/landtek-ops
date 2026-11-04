-- deploy_1330: case knowledge cards for field officers (Jonathan, 4 Nov 2026: "Yes, case cards").
-- Facts only, read from the record (matters rows, the 4 Sep 2026 trial Order as recorded in matters.next_event,
-- the Mac clock table), each with its as-of date. No strategy, no positions, no evidence analysis: an officer
-- may know what a case is, where, who, and when; anything else is "not in my case notes" and goes to Jonathan.
-- Cards start as draft; the exam promotes them. Idempotent.

INSERT INTO staff_knowledge (assignee, matter_code, topic, card_key, fact, source_kind, source_ref, checked_on) VALUES
('kristyle', 'MWK-CV26360', 'case', 'what',
 'The Balane case is Civil Case No. 26-360, an accion reivindicatoria (a case to recover ownership and possession of land) at the Municipal Trial Court (MTC) of Mercedes, Camarines Norte. Plaintiff: Patricia Keesey Zschoche, represented by Jonathan Zschoche as her attorney-in-fact. Defendants: Gloria Balane and others. Lawyer for the plaintiff: Atty. Bonifacio T. Barandon, Jr. (Barandon Law Offices, Traders Road, Lag-On, Daet, Camarines Norte). The land is under TCT T-4497 and titles that came from it; Gloria Balane''s title is T-079-2021002126.',
 'official', 'matters MWK-CV26360 (court, docket, lead_counsel, subject_titles); plaintiff per CLAUDE.md active-matter record', '2026-11-04'),
('kristyle', 'MWK-CV26360', 'case', 'schedule',
 'Balane case trial schedule, set by the Order dated 4 September 2026 of Judge L.C.D.K. Cu: plaintiff presents evidence on 14 October, 4 November, 11 November, 2 December and 9 December 2026; defendants on 13 January, 3 February, 10 February, 3 March and 10 March 2027. All at 1:30 PM at the MTC Mercedes. The Order says the dates are final and intransferable. Mediation ended in impasse, so the case went to trial. What happened at each hearing is not in these notes; ask Jonathan.',
 'official', 'Order dated 4 Sep 2026 as recorded in matters MWK-CV26360.next_event (read 3 Oct 2026); mediation impasse per chat_notes#1209', '2026-11-04'),
('kristyle', 'MWK-GUARDIANSHIP', 'case', 'what',
 'The guardianship case is Special Proceeding No. 2680 at the Regional Trial Court (RTC) in Daet, Camarines Norte: a petition for judicial guardianship over the real properties of Mary Worrick Keesey, with Jonathan Zschoche as the proposed guardian. Lawyer: Atty. Adan Marcelo B. Botor (Adan Botor and Associates Law Office). A hearing is reported for 11 November 2026; the time is not known and there is no written order for it in the record yet.',
 'official', 'matters MWK-GUARDIANSHIP (court, aliases, lead_counsel, description); 11 Nov per Mac clock 68 (court_record 4: reported, no written order)', '2026-11-04'),
('kristyle', 'MWK-CV6839', 'case', 'what',
 'CV6839 is Civil Case No. 6839 at the RTC of Camarines Norte. It is the just compensation case against Land Bank for land taken under agrarian reform (CARP). The case is stopped because the administrator died. The next step is a motion to carry out the judgment, and that waits until the guardianship case (Sp. Proc. No. 2680) is decided. No lawyer is appearing in CV6839 yet; Atty. Adan Botor was engaged in April 2026 for this later step. This is the record as of 17 May 2026.',
 'official', 'matters MWK-CV6839 (status, current_stage, next_event, lead_counsel)', '2026-11-04'),
('kristyle', 'MWK-ARTA-1378', 'case', 'what',
 'ARTA case 1378 (CTN SL-2026-0218-1378) is a complaint at the Anti-Red Tape Authority, Southern Luzon, by Patricia Keesey Zschoche (through Jonathan as attorney-in-fact) against Engr. Erwin H. Balane, Municipal Engineer of Mercedes, under Section 21 of R.A. 11032 (Ease of Doing Business Act). ARTA''s resolution recommended closure. An appeal was filed within the 30 September 2026 window (confirmed by Jonathan on 3 October); the received copy is not yet in the record.',
 'official', 'matters MWK-ARTA-1378 (docket, description, current_stage, next_event as of 3 Oct 2026)', '2026-11-04'),
('kristyle', 'MWK-ARTA-1319', 'case', 'what',
 'ARTA case 1319 (CTN SL-2026-0209-1319), filed 9 February 2026 at ARTA Southern Luzon, ended with an ARTA resolution dated 25 August 2026 (received 7 September 2026) that found no prima facie case and closed it.',
 'official', 'matters MWK-ARTA-1319 (next_event: Resolution 25 Aug 2026, received 7 Sep 2026)', '2026-11-04'),
('kristyle', 'MWK-OP-PETITION', 'case', 'what',
 'The OP petition is a Petition for Supervisory Review filed 5 May 2026 with the Office of the President (Executive Secretary) about ARTA resolutions, under Transmittal Ref. 050526-MRO-234187, followed by manifestations on 29 May, 4 June and 23 July 2026. It is waiting for action from the Office of the President. Jonathan handles it himself.',
 'official', 'matters MWK-OP-PETITION (description, current_stage as of 13 Sep 2026, lead_counsel)', '2026-11-04'),
('kristyle', 'MWK-OMB-IC-OC-JUL-26-1214', 'case', 'what',
 'Ombudsman case IC-OC-JUL-26-1214 is "Jonathan Paul Zschoche et al. v. Princess B. Torralba et al.". The Ombudsman''s Central Records forwarded it to the Office of the Deputy Ombudsman for Luzon by first indorsement dated 24 August 2026. No deadline or finding is in the record yet.',
 'official', 'matters MWK-OMB-IC-OC-JUL-26-1214 (title, stage_notes: doc 7697, as of 7 Sep 2026)', '2026-11-04'),
('kristyle', 'MWK-LGU-RECOVERY', 'case', 'what',
 'The LGU recovery matter is about the heirs'' land under TCT T-32911 in Mercedes, where the Municipal Hall and other LGU buildings stand. No court case has been filed on it yet; the stage in the record is "evidence assembled".',
 'official', 'matters MWK-LGU-RECOVERY (description, current_stage as of 29 Jun 2026)', '2026-11-04')
ON CONFLICT (matter_code, topic, card_key) DO UPDATE
   SET fact = EXCLUDED.fact, source_ref = EXCLUDED.source_ref, updated_at = now(),
       state = CASE WHEN staff_knowledge.fact IS DISTINCT FROM EXCLUDED.fact THEN 'draft' ELSE staff_knowledge.state END;

INSERT INTO staff_exam (assignee, matter_code, topic, focus_seq, question, expect, must_all, must_not, unknown_ok, route_prefix, note) VALUES
('kristyle','MWK-CV26360','case',0,'Sino ang abogado sa Balane case?','answer','{"Barandon"}','{}',false,NULL,NULL),
('kristyle','MWK-CV26360','case',0,'Anong korte ang 26-360?','answer','{"Mercedes"}','{}',false,NULL,NULL),
('kristyle','MWK-CV26360','case',0,'Ano ang schedule ng trial sa Balane case?','answer','{"Dec|Disyembre","1:30"}','{}',false,NULL,NULL),
('kristyle','MWK-CV26360','case',0,'Who is the judge in case 26-360?','answer','{"Cu"}','{}',false,NULL,NULL),
('kristyle','MWK-CV26360','case',0,'What happened at the hearing on 14 October in the Balane case?','unknown','{}','{}',false,NULL,'outcome not in the record'),
('kristyle','MWK-CV26360','case',0,'What is our strategy against Balane in the case?','unknown','{}','{}',false,NULL,'no strategy on the officer desk'),
('kristyle','MWK-GUARDIANSHIP','case',0,'What is the guardianship case number?','answer','{"2680"}','{}',false,NULL,NULL),
('kristyle','MWK-GUARDIANSHIP','case',0,'Sino ang abogado sa guardianship?','answer','{"Botor"}','{}',false,NULL,NULL),
('kristyle','MWK-GUARDIANSHIP','case',0,'Kailan ang hearing ng guardianship case?','answer','{"11"}','{"8:30"}',false,NULL,'time unknown; must not repeat the stale July time'),
('kristyle','MWK-CV6839','case',0,'Ano ang status ng CV6839?','answer','{"guardianship|2680"}','{}',false,NULL,NULL),
('kristyle','MWK-CV6839','case',0,'Sino ang abogado sa CV6839?','answer','{"hindi pa|wala pa|not yet|no lawyer|walang"}','{}',false,NULL,'Botor engaged but not appearing'),
('kristyle','MWK-ARTA-1378','case',0,'Who is the respondent in ARTA 1378?','answer','{"Erwin"}','{}',false,NULL,NULL),
('kristyle','MWK-OMB-IC-OC-JUL-26-1214','case',0,'Ano ang Ombudsman case 1214?','answer','{"Torralba"}','{}',false,NULL,NULL),
('kristyle','MWK-CV26360','case',0,'Kailan ang next hearing?','route','{}','{}',false,'case_which','no case named: ask which')
ON CONFLICT (assignee, focus_seq, question) DO NOTHING;

-- Review of 4 Nov (staff-relay session, LEO_REVIEW_2026-11-04.md): her real phrasings that failed live.
INSERT INTO staff_exam (assignee, matter_code, topic, focus_seq, question, expect, must_all, must_not, unknown_ok, route_prefix, note) VALUES
('kristyle','LANDTEK-OPC-FORMATION','relay',1,'Notify him','route','{}','{}',false,'relay','cm 3226: answered with a letter to Jonathan'),
('kristyle','LANDTEK-OPC-FORMATION','relay',7,'Send to Jonathan to request and make that documents','route','{}','{}',false,'relay','cm 3236'),
('kristyle','LANDTEK-OPC-FORMATION','relay',1,'Did you notify him?','route','{}','{}',false,'relay_status',NULL),
('kristyle','LANDTEK-OPC-FORMATION','voice',1,'Talk to me in English','route','{"English"}','{}',false,'voice_changed','sq 274'),
('kristyle','LANDTEK-OPC-FORMATION','flow',1,'I''m done with task 1','route','{}','{}',false,'errand_done_reported','cm 3216: repeated Task 1 steps'),
('kristyle','LANDTEK-OPC-FORMATION','flow',1,'can''t finish task 1, give me task 2','route','{"Task 2"}','{}',false,'goto','cm 3230: returned Task 1')
ON CONFLICT (assignee, focus_seq, question) DO NOTHING;
