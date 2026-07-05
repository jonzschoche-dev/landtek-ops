-- fix_autolink_client_separation_deploy674.sql
-- WHY (2026-07-04): document_autolink_matters() (trigger trg_documents_autolink) creates
-- reference links purely by TEXT-KEYWORD match — e.g. PAR-CAPACUAN <- '\yCapacuan\y'. That rule
-- is CLIENT-BLIND: an NIBDC mining document that merely mentions "Capacuan" gets auto-linked to
-- Paracale's PAR-CAPACUAN matter and rendered on Paracale's client portal. This is the SOURCE
-- that regenerates the cross-client breach fix_cross_client_doc_links_deploy674.sql cleans up:
-- re-filing docs 1176/1180 re-fired the trigger and immediately recreated the bad links.
--
-- ROOT FIX (write-side mirror of the render_matter_detail guard + client_dependability check):
-- refuse to auto-link a document to a matter of a DIFFERENT real client than the document's own
-- case_file. Same predicate everywhere: blank / 'Owner' / own-client / non-client-tag docs pass;
-- only a REAL other client (MWK-001 / Paracale-001 / NIBDC-001) crossing is blocked. Not a rebuild
-- — a guard clause added to the two INSERT sites of the existing function.

CREATE OR REPLACE FUNCTION public.document_autolink_matters()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
  pat_record RECORD;
BEGIN
  -- 1) Primary link from documents.matter_code (separation-guarded).
  IF NEW.matter_code IS NOT NULL AND NEW.matter_code NOT IN ('', 'UNCLASSIFIED', 'unknown', 'Unknown')
     AND (
          COALESCE(NEW.case_file,'') IN ('', 'Owner')
          OR NEW.case_file NOT IN (SELECT client_code FROM clients
                                    WHERE COALESCE(client_code,'') NOT IN ('','Owner','Archive','PENDING_TRIAGE'))
          OR NEW.case_file = (SELECT client_code FROM matters WHERE matter_code = NEW.matter_code)
     ) THEN
    INSERT INTO document_matter_links (doc_id, matter_code, case_file, relation_kind, provenance_level, linked_by, note)
    VALUES (NEW.id, NEW.matter_code, NEW.case_file, 'primary', 'verified', 'autolink_trigger',
            'Primary link from documents.matter_code')
    ON CONFLICT (doc_id, matter_code, relation_kind) DO UPDATE
      SET case_file = EXCLUDED.case_file, updated_at = now();
  END IF;

  -- 2) Reference links via regex patterns (deploy_280 expanded set), separation-guarded.
  IF NEW.extracted_text IS NOT NULL AND LENGTH(NEW.extracted_text) > 50 THEN
    FOR pat_record IN
      SELECT matter, pat FROM (VALUES
        ('MWK-ARTA-0690', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0690\M'),
        ('MWK-ARTA-0747', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0747\M'),
        ('MWK-ARTA-0792', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*0792\M'),
        ('MWK-ARTA-1210', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1210\M'),
        ('MWK-ARTA-1212', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1212\M'),
        ('MWK-ARTA-1319', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1319\M'),
        ('MWK-ARTA-1321', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1321\M'),
        ('MWK-ARTA-1378', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1378\M'),
        ('MWK-ARTA-1891', 'CTN[\s-]*SL[-\s]*\d{4}[-\s]*\d{4}[-\s]*1891\M'),
        ('MWK-CV26360', 'Civil\s+Case\s+(No\.?\s+)?26[-\s]?360'),
        ('MWK-CV6839', 'Civil\s+Case\s+(No\.?\s+)?6839'),
        ('PAR-CV13-131220', 'Civil\s+Case\s+(No\.?\s+)?13[-\s]?131220'),
        ('MWK-TCT4497', '\mT[-\s]?4497\M'),
        ('MWK-ESTATE', 'Mary\s+Worrick\s+Keesey'),
        ('PAR-CAPACUAN', '(Paracale\s+Gold\s+Partnership|Allan\s+Inocalla)'),
        ('MWK-CV26360', '\yBalane\y'),
        ('MWK-CV26360', '\yTorralba\y'),
        ('MWK-CV26360', '\yVicta\y'),
        ('MWK-CV26360', '\yApor\y'),
        ('MWK-CV26360', '\yMabeza\y'),
        ('MWK-CV26360', '\yBernardo\y'),
        ('MWK-CV26360', 'Cesar\s+Ramirez'),
        ('MWK-CV26360', '\yGaulit\y'),
        ('MWK-CV26360', 'Dolores\s+Vela'),
        ('MWK-CV26360', 'Edgardo\s+Santiago'),
        ('MWK-CV26360', 'Elsa\s+Illigan'),
        ('MWK-CV26360', '\yTychingco\y'),
        ('MWK-CV26360', 'Jose\s+Pascual'),
        ('MWK-CV26360', '\yOnrubio\y'),
        ('MWK-CV26360', 'Maria\s+V?\.?\s*Cereza'),
        ('MWK-CV26360', 'Mariquita\s+Era'),
        ('MWK-CV26360', 'Pedro\s+Valledor'),
        ('MWK-CV26360', 'Rosalina\s+Hansol'),
        ('MWK-CV26360', 'Roscoe\s+Lea(?:n|ñ)o'),
        ('MWK-CV26360', 'Ruben\s+Ocan'),
        ('MWK-CV26360', 'Severino\s+Tenorio'),
        ('MWK-CV26360', '\yBarandon\y'),
        ('MWK-CV26360', 'Donata\s+(?:M\.?\s*)?King'),
        ('MWK-CV26360', 'Cesar\s+(?:N\.?\s*)?de\s+la\s+Fuente'),
        ('MWK-ARTA-0747', 'Alexander\s+L\.?\s*Pajarillo'),
        ('MWK-ARTA-0747', 'Mayor\s+Pajarillo'),
        ('MWK-ARTA-0747', '\yPajarillo\y'),
        ('MWK-TCT4497', '\yT[-\s]?32916\y'),
        ('MWK-TCT4497', '\yT[-\s]?32917\y'),
        ('MWK-TCT4497', '\yT[-\s]?52540\y'),
        ('MWK-TCT4497', '\yT[-\s]?52536\y'),
        ('MWK-TCT4497', '\yT[-\s]?31298\y'),
        ('MWK-TCT4497', '\yT[-\s]?079-2021002127\y'),
        ('MWK-ESTATE', 'Patricia\s+Keesey\s+Zschoche'),
        ('MWK-ESTATE', 'Patricia\s+Zschoche'),
        ('PAR-CAPACUAN', '\yCapacuan\y'),
        ('PAR-CAPACUAN', '\bPGC\b'),
        ('PAR-CAPACUAN', 'Paracale\s+Gold\s+Consortium'),
        ('PAR-CAPACUAN', 'Chavit\s+Singson'),
        ('PAR-CAPACUAN', 'LCS\s+Group'),
        ('PAR-CAPACUAN', 'Satrap\s+Mining')
      ) AS p(matter, pat)
    LOOP
      -- SEPARATION GUARD (deploy_674): only auto-link when the target matter's client is NOT a
      -- different real client than this document's own case_file. Blocks the client-blind keyword
      -- crossing (e.g. an NIBDC-001 doc mentioning "Capacuan" -> Paracale's PAR-CAPACUAN).
      IF NEW.extracted_text ~* pat_record.pat
         AND (
              COALESCE(NEW.case_file,'') IN ('', 'Owner')
              OR NEW.case_file NOT IN (SELECT client_code FROM clients
                                        WHERE COALESCE(client_code,'') NOT IN ('','Owner','Archive','PENDING_TRIAGE'))
              OR NEW.case_file = (SELECT client_code FROM matters WHERE matter_code = pat_record.matter)
         ) THEN
        INSERT INTO document_matter_links (doc_id, matter_code, relation_kind, provenance_level, linked_by, note)
        VALUES (NEW.id, pat_record.matter, 'reference', 'inferred_strong', 'autolink_trigger',
                'Detected via text pattern: ' || pat_record.matter)
        ON CONFLICT (doc_id, matter_code, relation_kind) DO NOTHING;
      END IF;
    END LOOP;
  END IF;

  RETURN NEW;
END;
$function$;
