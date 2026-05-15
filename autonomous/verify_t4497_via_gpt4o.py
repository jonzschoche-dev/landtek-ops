#!/usr/bin/env python3
"""GPT-4o per-doc extraction of T-4497 title-header fields.

The 10 T-4497-named docs already have extracted_text populated. Run a small
GPT-4o pass to extract the structured title-header per doc, aggregate via
majority vote, write verified rows into titles + chain_of_title +
extraction_chunks. Cost: ~$0.50.
"""
import os, json, psycopg2
from psycopg2.extras import Json
import openai
from collections import Counter

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
DB_DSN = "host=172.18.0.3 dbname=n8n user=n8n password=n8npassword"

oai = openai.OpenAI(api_key=OPENAI_API_KEY)

PROMPT = """You are extracting structured data from a Philippine TCT or related document.

The document is about TCT T-4497 (Heirs of Mary Worrick Keesey, mother title of
the MWK case file). Read the text and return STRICTLY valid JSON with these fields.
Use null when the text does not state the field. Do NOT guess.

{
  "is_t4497_titledoc": boolean (true only if this document IS the TCT T-4497 itself,
                                 false if it's a history note, survey, map, or other),
  "registrants": [list of named persons or entities the document says hold T-4497],
  "parent_title": "(LRC) Psd-... etc" or null,
  "registry_of_deeds": "Registry of Deeds for ..." or null,
  "issued_date": "YYYY-MM-DD" or null,
  "area_sqm": numeric or null,
  "location": "..." or null,
  "transferred_to_or_from": [list of historical owners mentioned — separate from current registrants],
  "evidence_quote": "verbatim ~50-char snippet from the source supporting the registrants field"
}

Text (first 4500 chars):
{text}
"""

def per_doc_extract(doc_id, fname, text):
    snippet = (text or "")[:4500]
    resp = oai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user",
                   "content": PROMPT.replace("{text}", snippet)}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def main():
    conn = psycopg2.connect(DB_DSN); cur = conn.cursor()
    cur.execute("""
      SELECT id, original_filename, extracted_text
        FROM documents
       WHERE (original_filename ILIKE '%T-4497%' OR original_filename ILIKE '%4497%')
         AND extracted_text IS NOT NULL AND length(extracted_text) > 50
       ORDER BY id
    """)
    docs = cur.fetchall()
    print(f"Processing {len(docs)} T-4497 docs")

    results = []
    for doc_id, fname, text in docs:
        try:
            r = per_doc_extract(doc_id, fname, text)
        except Exception as e:
            print(f"  doc {doc_id}: ERROR {e}")
            continue
        r["_doc_id"] = doc_id
        r["_filename"] = fname
        results.append(r)
        reg = r.get("registrants") or []
        print(f"  doc {doc_id} ({fname[:50]}): isT4497Title={r.get('is_t4497_titledoc')}, "
              f"registrants={reg}")

    # Aggregate: only count registrants from docs flagged is_t4497_titledoc=True
    title_docs = [r for r in results if r.get("is_t4497_titledoc")]
    print(f"\n{len(title_docs)} docs identified as the TCT T-4497 itself")

    registrant_votes = Counter()
    for r in title_docs:
        for name in r.get("registrants") or []:
            registrant_votes[name.strip().upper()] += 1
    print(f"\nRegistrant vote tally (only T-4497 title docs):")
    for name, votes in registrant_votes.most_common():
        print(f"  {votes:2d} × {name}")

    # Aggregate other fields by majority
    def majority(field):
        c = Counter(((r.get(field) or '').strip() if isinstance(r.get(field), str) else r.get(field))
                    for r in title_docs if r.get(field))
        if not c: return None
        top, votes = c.most_common(1)[0]
        return top if votes >= 2 else None

    canonical = {
        "registrants": [name for name, v in registrant_votes.most_common() if v >= 2],
        "parent_title": majority("parent_title"),
        "registry_of_deeds": majority("registry_of_deeds"),
        "issued_date": majority("issued_date"),
        "area_sqm": majority("area_sqm"),
        "location": majority("location"),
    }
    print(f"\nCanonical (majority-voted):")
    print(json.dumps(canonical, indent=2, default=str))

    # Write to DB
    if canonical["registrants"]:
        first_doc = title_docs[0]["_doc_id"] if title_docs else None

        # UPDATE titles
        cur.execute("""
          UPDATE titles SET
            registrant_name_raw = %s,
            registrant_canonical = %s,
            parent_title = COALESCE(%s, parent_title),
            location = COALESCE(%s, location),
            area_sqm = COALESCE(%s::numeric, area_sqm),
            source_doc_id = COALESCE(%s, source_doc_id),
            provenance_level = 'verified',
            notes = COALESCE(notes, '') ||
                    ' | Verified 2026-05-14 via GPT-4o consensus across ' || %s::text || ' T-4497 docs.',
            updated_at = NOW()
          WHERE tct_number = 'T-4497'
        """, (
            ' | '.join(canonical["registrants"]),
            canonical["registrants"][0],   # canonical = first/primary registrant
            canonical["parent_title"],
            canonical["location"],
            (None if canonical["area_sqm"] is None else str(canonical["area_sqm"])),
            first_doc,
            len(title_docs)
        ))

        # INSERT chain_of_title rows
        for name in canonical["registrants"]:
            cur.execute("""
              INSERT INTO chain_of_title
                (tct_number, registrant_full_name, predecessor_title,
                 registration_date, source_chunk_id, provenance_level)
              VALUES ('T-4497', %s, %s, %s, NULL, 'verified')
              ON CONFLICT (tct_number, registrant_full_name, source_chunk_id)
              DO UPDATE SET provenance_level='verified'
            """, (name, canonical["parent_title"],
                  None if not canonical["issued_date"]
                  else canonical["issued_date"][:10]))

        # INSERT verified extraction_chunks (one per critical field)
        for field, value in [
            ("registered_owners", ' | '.join(canonical["registrants"])),
            ("parent_title", canonical["parent_title"]),
            ("registry_of_deeds_full", canonical["registry_of_deeds"]),
            ("area_sqm", canonical["area_sqm"]),
            ("location", canonical["location"]),
        ]:
            if value:
                cur.execute("""
                  INSERT INTO extraction_chunks
                    (doc_id, tct_number, chunk_type, field_name, field_status,
                     quote_text, structured_value, provenance_level, verified_by, verified_at)
                  VALUES (%s, 'T-4497', 'gpt4o_consensus', %s, 'extracted',
                          'GPT-4o consensus across T-4497 title docs',
                          %s, 'verified', 'gpt4o_majority_vote', NOW())
                  ON CONFLICT (doc_id, chunk_type, field_name)
                  DO UPDATE SET provenance_level='verified',
                                verified_by='gpt4o_majority_vote',
                                verified_at=NOW(),
                                structured_value=EXCLUDED.structured_value
                """, (first_doc, field, Json({"value": str(value),
                                              "vote_count": registrant_votes.most_common()[0][1]
                                                            if field == "registered_owners" else None,
                                              "n_docs_voted": len(title_docs)})))

        # Insert field_consensus rows for audit trail
        for field, value in [("registered_owners", ' | '.join(canonical["registrants"])),
                             ("parent_title", canonical["parent_title"]),
                             ("area_sqm", canonical["area_sqm"]),
                             ("registry_of_deeds_full", canonical["registry_of_deeds"])]:
            if value:
                cur.execute("""
                  INSERT INTO field_consensus
                    (doc_id, tct_number, field_name, pass1_value,
                     agreement, promoted_to_verified, decided_at)
                  VALUES (%s, 'T-4497', %s, %s, 'gpt4o_majority_vote', TRUE, NOW())
                  ON CONFLICT (doc_id, field_name) DO UPDATE
                    SET agreement = EXCLUDED.agreement,
                        promoted_to_verified = TRUE,
                        decided_at = NOW()
                """, (first_doc, field, str(value)))

        conn.commit()
        print(f"\nDB updated: titles + chain_of_title + extraction_chunks + field_consensus for T-4497")
    else:
        print("\nNo consensus registrants — DB unchanged")

    cur.close(); conn.close()


if __name__ == "__main__":
    main()
