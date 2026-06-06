#!/usr/bin/env python3
"""deploy_355 — ARTA autolink: CTN suffix only, not blanket CV-26360.

Removes litigationdivision@arta → MWK-CV26360 trigger rule.
Backfills matter_codes from CTN SL text; strips CV26360 unless 26-360 cited.
Fixes correspondence_links + client_history matter_code on affected gmail rows.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from correspondence_spine import (
    gmail_history_matter_code,
    sanitize_gmail_matter_codes,
)
from landtek_core import db

TRIGGER_SQL = r"""
CREATE OR REPLACE FUNCTION gmail_autolink_matters()
RETURNS TRIGGER AS $$
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
        IF sender_lower LIKE '%dilgcamarinesnorte%' THEN mc_set := array_append(mc_set, 'MWK-CV26360'::text); END IF;
        -- deploy_355: removed blanket litigationdivision@arta → CV26360
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
                                         || ARRAY['deploy_355:trigger_autolink'];
            END IF;
        END IF;
    END IF;

    IF NEW.client_code IS NULL OR NEW.client_code = '' THEN
        IF NEW.case_file IS NOT NULL AND NEW.case_file <> '' THEN
            SELECT c.client_code INTO derived_client
              FROM clients c WHERE c.case_file = NEW.case_file LIMIT 1;
            IF derived_client IS NULL THEN
                SELECT DISTINCT m.client_code INTO derived_client
                  FROM matters m WHERE m.case_file = NEW.case_file LIMIT 1;
            END IF;
        END IF;
        IF derived_client IS NULL AND cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
            SELECT DISTINCT m.client_code INTO derived_client
              FROM matters m
             WHERE m.matter_code = ANY(NEW.matter_codes)
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
$$ LANGUAGE plpgsql;
"""


def _sync_links(cur, gmail_id: int, matter_codes: list[str]) -> None:
    cur.execute(
        """
        DELETE FROM correspondence_links
         WHERE gmail_id = %s
           AND link_type = 'matter'
           AND link_key = 'MWK-CV26360'
           AND NOT ('MWK-CV26360' = ANY(%s::text[]))
        """,
        (gmail_id, matter_codes),
    )
    for mc in matter_codes:
        cur.execute(
            """
            INSERT INTO correspondence_links
              (gmail_id, link_type, link_key, relation, rationale, assessed_by)
            VALUES (%s, 'matter', %s, 'unclear',
                    'deploy_355: matter_codes sanitized from CTN / 26-360 mention', 'deploy_355')
            ON CONFLICT (gmail_id, link_type, link_key) DO NOTHING
            """,
            (gmail_id, mc),
        )


def _sync_client_history(cur, gmail_id: int, matter_codes: list[str], relevance_status: str) -> None:
    primary = gmail_history_matter_code(matter_codes)
    if not primary:
        return
    cur.execute(
        """
        UPDATE client_history
           SET matter_code = %s,
               citation_ref = regexp_replace(
                   citation_ref,
                   'matter=[^ ]+',
                   'matter=' || %s
               )
         WHERE source_table = 'gmail_messages'
           AND source_id = %s
        """,
        (primary, primary, str(gmail_id)),
    )


def main():
    fixed: list[tuple[int, list[str], list[str]]] = []

    with db() as cur:
        cur.execute(TRIGGER_SQL)

        cur.execute("SELECT matter_code FROM matters")
        valid = {r["matter_code"] for r in cur.fetchall()}

        cur.execute("""
            SELECT id, from_addr, subject, body_plain, matter_codes, relevance_status
              FROM gmail_messages
             WHERE 'MWK-CV26360' = ANY(matter_codes)
                OR from_addr ILIKE '%litigationdivision@arta%'
                OR subject ~* 'CTN\\s*SL'
             ORDER BY id
        """)
        rows = cur.fetchall()

        for row in rows:
            old = list(row["matter_codes"] or [])
            new = sanitize_gmail_matter_codes(
                from_addr=row["from_addr"],
                subject=row["subject"],
                body_plain=row["body_plain"],
                matter_codes=old,
                valid_matter_codes=valid,
            )
            if new == old:
                continue
            cur.execute(
                """
                UPDATE gmail_messages
                   SET matter_codes = %s::text[],
                       relevance_status = CASE
                         WHEN cardinality(%s::text[]) > 0 THEN 'matter_linked'
                         ELSE relevance_status
                       END
                 WHERE id = %s
                """,
                (new, new, row["id"]),
            )
            _sync_links(cur, row["id"], new)
            _sync_client_history(cur, row["id"], new, row["relevance_status"])
            fixed.append((row["id"], old, new))

        cur.execute("""
            INSERT INTO deploy_log (deploy_id, summary) VALUES (
              'deploy_355',
              'ARTA autolink fix: CTN suffix → MWK-ARTA-#### only; CV26360 when 26-360 cited. '
              'Stripped blanket litigationdivision@arta → CV26360 rule; backfilled matter_codes + links.'
            )
            ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """)

    print(f"✓ deploy_355: trigger updated; {len(fixed)} gmail row(s) sanitized")
    for gid, old, new in fixed:
        print(f"  gmail#{gid}: {old} → {new}")

    with db() as cur:
        cur.execute("""
            SELECT id, matter_codes FROM gmail_messages WHERE id = 38220
        """)
        r = cur.fetchone()
        print(f"  verify gmail#38220: {list(r['matter_codes'] or [])}")


if __name__ == "__main__":
    main()