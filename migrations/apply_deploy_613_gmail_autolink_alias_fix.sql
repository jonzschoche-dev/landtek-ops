-- deploy_613 — fix gmail_autolink_matters() trigger: record-variable / table-alias collision.
--
-- BUG: the function declares `m RECORD;` (used in the `FOR m IN …` CTN-matcher loop), but the two
-- client-derivation queries lower down wrote `FROM matters m … m.client_code`. When a writer sets
-- gmail_messages.matter_codes to a NON-empty value, the `IF cardinality(matter_codes)=0` block is
-- skipped, so the record `m` is never assigned — and `m.client_code` then references an unassigned
-- record, raising `ObjectNotInPrerequisiteState: record "m" is not assigned yet`. This crashed EVERY
-- `UPDATE gmail_messages SET matter_codes` — silently killing email_briefer's reconcile + the
-- critical-email push, and the email→matter auto-linking generally.
--
-- FIX: rename the TABLE ALIAS m → mt in the two `matters` client-derivation subqueries only. Pure
-- alias rename, no logic change; the record variable `m` (the FOR loop) is untouched. Idempotent.
CREATE OR REPLACE FUNCTION public.gmail_autolink_matters()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    haystack TEXT;
    sender_lower TEXT;
    mc_set TEXT[] := ARRAY[]::TEXT[];
    candidate TEXT;
    suffix TEXT;
    m RECORD;
    valid_codes TEXT[];
    derived_client TEXT;
BEGIN
    haystack := COALESCE(NEW.from_addr,'') || ' ' || COALESCE(NEW.subject,'') || ' ' || COALESCE(NEW.body_plain,'');
    sender_lower := LOWER(COALESCE(NEW.from_addr,''));

    IF cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) = 0 THEN
        IF sender_lower LIKE '%barandon_lawoffice%' THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%colenacious%'        THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        IF sender_lower LIKE '%lourdestotanes%'     THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;

        FOR m IN
            SELECT (regexp_matches(haystack,
                    '\bCTN\s*s?\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b',
                    'gi'))[3] AS s
        LOOP
            suffix := m.s;
            IF length(suffix) = 3 THEN suffix := '0' || suffix; END IF;
            candidate := 'MWK-ARTA-' || suffix;
            IF NOT (candidate = ANY(mc_set)) THEN mc_set := array_append(mc_set, candidate); END IF;
        END LOOP;

        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*26-?360' THEN
            IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*6839' THEN
            IF NOT ('MWK-CV6839' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV6839'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*13-?131220' THEN
            IF NOT ('PAR-CV13-131220' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'PAR-CV13-131220'::text); END IF;
        END IF;
        IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*8563' THEN
            IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        END IF;

        IF cardinality(mc_set) > 0 THEN
            SELECT array_agg(DISTINCT mc) INTO valid_codes
              FROM unnest(mc_set) mc
             WHERE mc IN (SELECT matter_code FROM matters);
            IF cardinality(COALESCE(valid_codes, '{}'::text[])) > 0 THEN
                NEW.matter_codes := valid_codes;
                NEW.relevance_reasons := COALESCE(NEW.relevance_reasons, '{}'::text[])
                                         || ARRAY['deploy_356:trigger_autolink'];
            END IF;
        END IF;
    END IF;

    IF NEW.client_code IS NULL OR NEW.client_code = '' THEN
        IF NEW.case_file IS NOT NULL AND NEW.case_file <> '' THEN
            SELECT c.client_code INTO derived_client
              FROM clients c WHERE c.case_file = NEW.case_file LIMIT 1;
            IF derived_client IS NULL THEN
                SELECT DISTINCT mt.client_code INTO derived_client
                  FROM matters mt WHERE mt.case_file = NEW.case_file LIMIT 1;
            END IF;
        END IF;
        IF derived_client IS NULL AND cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
            SELECT DISTINCT mt.client_code INTO derived_client
              FROM matters mt
             WHERE mt.matter_code = ANY(NEW.matter_codes)
             LIMIT 1;
        END IF;
        IF derived_client IS NULL AND cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
            IF (NEW.matter_codes)[1] LIKE 'MWK-%' THEN derived_client := 'MWK-001'; END IF;
            IF (NEW.matter_codes)[1] LIKE 'PAR-%' THEN derived_client := 'Paracale-001'; END IF;
        END IF;
        IF derived_client IS NOT NULL THEN
            NEW.client_code := derived_client;
        END IF;
    END IF;

    IF NEW.assessment_id IS NOT NULL THEN
        NEW.relevance_status := 'assessed';
    ELSIF cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
        NEW.relevance_status := 'matter_linked';
    ELSIF NEW.client_code IS NOT NULL THEN
        NEW.relevance_status := 'client_only';
    ELSE
        NEW.relevance_status := 'unlinked';
    END IF;

    RETURN NEW;
END;
$function$;
