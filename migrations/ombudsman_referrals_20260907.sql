-- Reviewed-source reconciliation, not a schema/ontology change or a filing.
-- Originals visually reviewed: doc 3754 (ARTA endorsement + receiving stamp), doc 7697
-- (Ombudsman indorsement); doc 1195 is the separate CSC transmission.
-- All writes are atomic, idempotent and captured in the canonical truth_audit_log.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
DO $reconcile$
DECLARE
  new_matter constant text := 'MWK-OMB-IC-OC-JUL-26-1214';
  action_key constant text := 'ombudsman_referrals_20260907';
  before_snapshot jsonb;
  after_snapshot jsonb;
  n integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(action_key));
  IF EXISTS (SELECT 1 FROM truth_audit_log WHERE table_name='ombudsman_referral_reconciliation'
             AND row_pk->>'action'=action_key) THEN
    RAISE NOTICE 'Reconciliation already applied; no changes';
    RETURN;
  END IF;
  -- Repair the first run's audit-destination mistake without rerunning any case updates.
  -- Only this agent's exact snapshot is transferred, verified byte-for-byte, then removed.
  IF EXISTS (SELECT 1 FROM audit_log WHERE action=action_key AND actor='codex-user-authorized') THEN
    INSERT INTO truth_audit_log (table_name,row_pk,operation,before_state,after_state,app_actor,notes)
      SELECT 'ombudsman_referral_reconciliation',jsonb_build_object('action',action_key,'matter',new_matter),
        'UPDATE',before_state,after_state,actor,
        jsonb_build_object('retired_audit_id',id,'original_timestamp',created_at,'metadata',metadata,
          'correction','Moved from retired audit_log to canonical truth_audit_log; snapshot preserved intact')::text
      FROM audit_log WHERE action=action_key AND actor='codex-user-authorized';
    IF NOT EXISTS (SELECT 1 FROM audit_log old JOIN truth_audit_log canonical
        ON canonical.row_pk->>'action'=old.action
        WHERE old.action=action_key AND old.actor='codex-user-authorized'
          AND canonical.before_state=old.before_state AND canonical.after_state=old.after_state) THEN
      RAISE EXCEPTION 'Audit transfer verification failed';
    END IF;
    UPDATE matter_facts SET notes=replace(notes,'in audit_log action','in truth_audit_log action')
      WHERE source_kind='doc' AND source_id='7697' AND matter_code=new_matter
        AND notes LIKE '%' || action_key || '%';
    UPDATE ombudsman_candidates SET rationale=replace(rationale,'in audit_log action','in truth_audit_log action')
      WHERE id IN (2,4,6) AND client_code='MWK-001' AND rationale LIKE '%' || action_key || '%';
    DELETE FROM audit_log WHERE action=action_key AND actor='codex-user-authorized';
    RAISE NOTICE 'Audit snapshot preserved in canonical truth_audit_log; case updates not repeated';
    RETURN;
  END IF;
  PERFORM 1 FROM matters WHERE matter_code IN ('MWK-ARTA-1212','MWK-ARTA-1891') FOR UPDATE;
  PERFORM 1 FROM documents WHERE id IN (3754,7697,1195) FOR UPDATE;
  PERFORM 1 FROM gmail_messages WHERE id=125372 FOR UPDATE;
  PERFORM 1 FROM matter_facts WHERE source_kind='doc' AND source_id='7697' FOR UPDATE;
  PERFORM 1 FROM ombudsman_candidates WHERE id IN (2,4,6) FOR UPDATE;

  IF NOT EXISTS (SELECT 1 FROM documents WHERE id=3754 AND case_file='MWK-001'
     AND matter_code='MWK-ARTA-1212'
     AND content_hash='72d37d620a3a218a4c949e6423988b5952a03989030ccfecc4fcc33c86958dd7')
     OR NOT EXISTS (SELECT 1 FROM documents WHERE id=7697 AND case_file='MWK-001'
     AND matter_code IS NULL
     AND content_hash='5342ec42b870aa0d9e7ea2405625989cf7f91e07af82b63c02f95e2eff3cf4be')
     OR NOT EXISTS (SELECT 1 FROM documents WHERE id=1195 AND matter_code='MWK-ARTA-1891'
     AND extracted_text LIKE '%OAC-L Letter No. 270%') THEN
    RAISE EXCEPTION 'Source identity/state changed; re-review originals, do not force';
  END IF;
  IF (SELECT count(*) FROM matters WHERE client_code='MWK-001' AND (
      (matter_code='MWK-ARTA-1212' AND current_stage='complaint_filed_awaiting_response') OR
      (matter_code='MWK-ARTA-1891' AND current_stage='referred_to_csc_dilg_awaiting'))) <> 2
     OR EXISTS (SELECT 1 FROM matters WHERE matter_code=new_matter) THEN
    RAISE EXCEPTION 'Matter state changed; reconcile concurrent work first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM gmail_messages WHERE id=125372 AND client_code='MWK-001'
     AND message_id='1a05a75d40aba846' AND cardinality(COALESCE(matter_codes,'{}'))=0) THEN
    RAISE EXCEPTION 'Email ownership or routing changed; re-review';
  END IF;
  IF (SELECT count(*) FROM matter_facts WHERE source_kind='doc' AND source_id='7697') <> 6
     OR EXISTS (SELECT 1 FROM matter_facts WHERE source_kind='doc' AND source_id='7697'
                AND (matter_code<>'MWK-CV26360' OR claim_id IS NOT NULL OR created_by<>'verify_worker')) THEN
    RAISE EXCEPTION 'Fact ownership/dependencies changed; do not move automatically';
  END IF;
  IF (SELECT count(*) FROM ombudsman_candidates WHERE id IN (2,4,6)
      AND client_code='MWK-001' AND status='held_for_filing'
      AND provenance='operator' AND updated_at::date='2026-07-03') <> 3 THEN
    RAISE EXCEPTION 'Legacy candidate assessments changed; preserve newer review';
  END IF;

  SELECT jsonb_build_object(
    'matters',(SELECT jsonb_agg(to_jsonb(m)) FROM matters m WHERE matter_code IN ('MWK-ARTA-1212','MWK-ARTA-1891')),
    'document',(SELECT to_jsonb(d) - 'extracted_text' - 'analyst_memo' FROM documents d WHERE id=7697),
    'links',(SELECT jsonb_agg(to_jsonb(l)) FROM document_matter_links l WHERE doc_id=7697),
    'facts',(SELECT jsonb_agg(to_jsonb(f)) FROM matter_facts f WHERE source_kind='doc' AND source_id='7697'),
    'email_routing',(SELECT jsonb_build_object('id',id,'matter_codes',matter_codes,'relevance_status',relevance_status) FROM gmail_messages WHERE id=125372),
    'candidates',(SELECT jsonb_agg(to_jsonb(c)) FROM ombudsman_candidates c WHERE id IN (2,4,6))
  ) INTO before_snapshot;

  INSERT INTO matters (matter_code,client_code,case_file,matter_type,title,court_or_agency,
      docket_number,status,date_opened,forum,current_stage,next_event,stage_notes,stage_updated_at)
  VALUES (new_matter,'MWK-001','MWK-001','administrative',
      'Ombudsman IC-OC-JUL-26-1214 — Jonathan Paul Zschoche et al. v. Princess B. Torralba et al.',
      'Office of the Deputy Ombudsman for Luzon / CREMEB','IC-OC-JUL-26-1214','active',
      '2026-08-24','OMBUDSMAN','forwarded_to_luzon_for_appropriate_action',
      'Confirm CREMEB receipt, current processing stage and named respondents. Confirm whether this reference corresponds to ARTA-1212. Do not consolidate with CSC/ARTA-1891 without an explicit record.',
      'Source: doc:7697, first indorsement dated 24 August 2026; copy emailed 1 September 2026 (gmail:1a05a75d40aba846). Central Records forwards 111 pages and five extra copies for appropriate action. Date opened is earliest source-confirmed event, not a claimed original filing date. No preliminary-investigation order, finding of liability or response deadline established by this document. ARTA-1212 linkage is a hypothesis pending confirmation.',now());

  UPDATE documents SET matter_code=new_matter,updated_at=now() WHERE id=7697;
  -- Preserve the six assertions verbatim/provenance unchanged; correct only their matter assignment.
  UPDATE matter_facts SET matter_code=new_matter,updated_at=now(),
      notes=concat_ws(E'\n',notes,'2026-09-07 reviewed-source routing correction: doc:7697 is an Ombudsman indorsement, not a CV-26360 procedural event. Original assignment preserved in truth_audit_log action ombudsman_referrals_20260907.')
    WHERE source_kind='doc' AND source_id='7697';
  -- Delete only the observed automatic link. Other operator-authored links are never removed.
  DELETE FROM document_matter_links WHERE id=28199 AND doc_id=7697
    AND matter_code='MWK-CV26360' AND linked_by='autolink_trigger' AND relation_kind='reference';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n<>1 THEN RAISE EXCEPTION 'Expected automatic civil-case link changed'; END IF;
  INSERT INTO document_matter_links (doc_id,matter_code,case_file,relation_kind,provenance_level,linked_by,note)
    VALUES (7697,new_matter,'MWK-001','primary','verified','reviewed_source_reconciliation',
       'Exact reference and caption visually verified in the original indorsement; no ARTA-1212/1891 identity inferred')
    ON CONFLICT (doc_id,matter_code,relation_kind) DO UPDATE SET provenance_level='verified',
       linked_by=EXCLUDED.linked_by,note=EXCLUDED.note;
  UPDATE gmail_messages SET matter_codes=ARRAY[new_matter] WHERE id=125372;

  INSERT INTO case_stage_transitions (matter_code,case_file,from_stage,to_stage,transition_doc_id,notes,detected_by)
    SELECT matter_code,client_code,current_stage,
      CASE WHEN matter_code='MWK-ARTA-1212' THEN 'endorsed_to_ombudsman_receipt_confirmed'
           ELSE 'csc_to_ombudsman_transmitted_receipt_unconfirmed' END,
      CASE WHEN matter_code='MWK-ARTA-1212' THEN 3754 ELSE 1195 END,
      'Recorded 2026-09-07 from reviewed sources. Event dates: 1212 endorsement/OMB receiving stamp 29 July; 1891 CSC email transmission 24 June. No liability finding inferred.',
      'reviewed_source_reconciliation'
    FROM matters WHERE matter_code IN ('MWK-ARTA-1212','MWK-ARTA-1891');
  UPDATE matters SET current_stage='endorsed_to_ombudsman_receipt_confirmed',
      next_event='Follow up on ARTA-1212 endorsement received by Ombudsman 29 July 2026. Confirm whether IC-OC-JUL-26-1214 is its assigned reference and whether Tony Teope is included. Existing 22 July tracker date needs separate review; no new deadline is inferred.',
      stage_notes=concat_ws(E'\n',stage_notes,'2026-09-07 SOURCE UPDATE: doc:3754 expressly refers Princess B. Torralba under RA 6713 and Tony Teope under RA 3019 Sec.3(i); endorsed and receipt-stamped 29 July, copy emailed 31 July. These are allegations for appropriate action, not liability findings. doc:7697 may continue this track; cross-reference unconfirmed. Existing next_deadline preserved because its basis has not been reviewed.'),
      stage_updated_at=now(),updated_at=now() WHERE matter_code='MWK-ARTA-1212';
  UPDATE matters SET current_stage='csc_to_ombudsman_transmitted_receipt_unconfirmed',
      next_event='Confirm Ombudsman receipt and assigned reference for CSC OAC-L Letter 270 s.2026 / ARTA CTN SL-2026-0423-1891. Keep distinct from IC-OC-JUL-26-1214 unless expressly connected. DILG branch remains separately tracked.',
      next_deadline=CASE WHEN next_deadline='2026-07-24' THEN NULL ELSE next_deadline END,
      stage_notes=concat_ws(E'\n',stage_notes,'2026-09-07 SOURCE UPDATE: doc:1195 records CSC transmission on 24 June of OAC-L Letter 270 dated 23 June. No later OMB receipt/reference was found in the reviewed email search. Former 24 July date was an operator follow-up window, not an agency deadline; preserved in audit history and removed from the live next-deadline slot.'),
      stage_updated_at=now(),updated_at=now() WHERE matter_code='MWK-ARTA-1891';

  INSERT INTO correspondence_events (matter_code,author,addressee,subject,claimed_date,channel,
      delivery_status,received_date,gap_flag,proofs,all_verified)
  VALUES
    ('MWK-ARTA-1212','ARTA','Office of the Ombudsman','Endorsement of ARTA-1212','2026-07-29','physical_receiving_copy',
      'receiving_stamp_verified','2026-07-29','Assigned OMB reference and current processing stage need confirmation',
      '{"doc_id":3754,"gmail_message_id":"19fb5c3dbfa91c37","copy_emailed":"2026-07-31"}',false),
    (new_matter,'Ombudsman Central Records Division','Deputy Ombudsman for Luzon / CREMEB',
      '1st Indorsement IC-OC-JUL-26-1214','2026-08-24','email_copy',
      'copy_received','2026-09-01','Receiving bureau receipt, full respondent list and ARTA-1212 identity not yet confirmed',
      '{"doc_id":7697,"gmail_message_id":"1a05a75d40aba846","pages":111,"extra_copies":5}',false),
    ('MWK-ARTA-1891','CSC Office of Assistant Commissioner for Legal','Office of the Ombudsman',
      'Transmission of OAC-L Letter 270 s.2026','2026-06-23','email',
      'transmission_documented',NULL,'Ombudsman receipt and assigned reference unconfirmed',
      '{"doc_id":1195,"gmail_message_id":"19ef7753910d0042","transmitted":"2026-06-24"}',false);

  INSERT INTO ombudsman_candidates (client_code,official,office,capacity,matters,violation_code,
      statute,forum,elements,signals,status,strength,score,leverage,gaps,rationale,provenance)
  VALUES
    ('MWK-001','Tony Teope','Assistant to the Municipal Mayor, Mercedes (as identified by ARTA)',
      'unknown',ARRAY['MWK-ARTA-1212'],'ra3019_3i','R.A. 3019, Sec. 3(i)','OMBUDSMAN',
      '{"public_officer":{"state":"thin","label":"Verify appointment/capacity at the relevant time","handle":["doc:3754"]},"personal_material_interest":{"state":"missing","label":"Personal-gain or material interest in the identified transaction or act","handle":[]},"body_membership":{"state":"missing","label":"Membership of the body whose approval is required","handle":[]},"discretionary_approval":{"state":"missing","label":"Same act requires that body discretionary approval","handle":[]}}',
      '{"agency_referral":["doc:3754"],"referral_copy_email":["gmail:19fb5c3dbfa91c37"]}',
      'building',0,0,3,
      '["Review ARTA resolution doc:1614 and its annexes for the exact referred acts; referral is not element proof","Confirm the assigned Ombudsman reference and named respondents; doc:7697 linkage remains unconfirmed","Verify appointment, body membership, interest and discretionary-approval nexus separately","Human/counsel review required; no finding of guilt, probable cause or filing readiness is asserted"]',
      'AGENCY REFERRAL DOCUMENTED: doc:3754 expressly refers Tony Teope for alleged RA3019 Sec.3(i) violation; endorsement receipt-stamped 29 July 2026. Case theory and elements remain unverified.',
      'inferred_strong'),
    ('MWK-001','Princess B. Torralba','Councilor, Mercedes (as identified by ARTA)',
      'unknown',ARRAY['MWK-ARTA-1212'],'ra6713_unspecified','R.A. 6713 — subsection not specified in endorsement','OMBUDSMAN',
      '{"provision_and_elements":{"state":"missing","label":"Identify exact referred provision and test its elements","handle":["doc:3754"]}}',
      '{"agency_referral":["doc:3754"],"referral_copy_email":["gmail:19fb5c3dbfa91c37"]}',
      'building',0,0,3,
      '["Review ARTA resolution doc:1614 for exact provision and alleged acts","Confirm whether IC-OC-JUL-26-1214 corresponds to this referral; no consolidation inferred","Keep Councilor acts separate from private civil-defendant capacity","Human/counsel review required; referral is not a finding of liability"]',
      'AGENCY REFERRAL DOCUMENTED: doc:3754 expressly refers Princess B. Torralba for alleged RA6713 violation. The endorsement does not specify a subsection; none is invented.',
      'inferred_strong')
    ON CONFLICT (client_code,official,violation_code) DO NOTHING;

  UPDATE ombudsman_candidates SET status='building',provenance='inferred_strong',updated_at=now(),
      gaps=COALESCE(gaps,'[]') || '["Legacy July 3 AI-only held-for-filing label withdrawn on 2026-09-07; human/counsel approval was not established. Reassess using current agency records and source-specific attribution."]'::jsonb,
      rationale='LEGACY MACHINE ASSESSMENT — NOT HUMAN-VERIFIED. Prior held-for-filing/100-percent label is withdrawn, not a liability finding. Original assessment preserved in truth_audit_log action ombudsman_referrals_20260907.'
    WHERE id IN (2,4,6);

  IF EXISTS (SELECT 1 FROM document_matter_links WHERE doc_id=7697 AND matter_code='MWK-CV26360')
     OR EXISTS (SELECT 1 FROM matter_facts WHERE source_kind='doc' AND source_id='7697' AND matter_code<>new_matter)
     OR NOT EXISTS (SELECT 1 FROM gmail_messages WHERE id=125372 AND matter_codes=ARRAY[new_matter]) THEN
    RAISE EXCEPTION 'Routing postcondition failed; all changes rolled back';
  END IF;
  SELECT jsonb_build_object(
    'matters',(SELECT jsonb_agg(to_jsonb(m)) FROM matters m WHERE matter_code IN ('MWK-ARTA-1212','MWK-ARTA-1891',new_matter)),
    'links',(SELECT jsonb_agg(to_jsonb(l)) FROM document_matter_links l WHERE doc_id=7697),
    'fact_ids',(SELECT jsonb_agg(id) FROM matter_facts WHERE source_kind='doc' AND source_id='7697'),
    'candidates',(SELECT jsonb_agg(to_jsonb(c)) FROM ombudsman_candidates c WHERE id IN (2,4,6) OR
      (client_code='MWK-001' AND signals ? 'agency_referral'))
  ) INTO after_snapshot;
  INSERT INTO truth_audit_log (table_name,row_pk,operation,before_state,after_state,app_actor,notes)
    VALUES ('ombudsman_referral_reconciliation',jsonb_build_object('action',action_key,'matter',new_matter),
      'UPDATE',before_snapshot,after_snapshot,'codex-user-authorized',
      '{"authorization":"User: ok move it forward","source_documents":[3754,7697,1195],"ontology_changed":false,"sent_or_filed":false,"link_1212_to_1214":"unconfirmed; not asserted"}');
  RAISE NOTICE 'Ombudsman routing, procedural records and two agency-referred leads reconciled; nothing sent or filed';
END;
$reconcile$;
COMMIT;
