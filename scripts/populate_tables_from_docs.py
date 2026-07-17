#!/usr/bin/env python3
"""populate_tables_from_docs.py — SERIOUS bulk table population from full document text.

Not a design note. One pass over every document with text:

  documents.extracted_text
    → document_fields          (typed: tct/oct/ctn/tax_dec/date/amount/…)
    → document_titles          (title mentions per doc)
    → matter_facts (inferred_strong, created_by=doc_populate) when matter-linked
    → matter_parties (inferred_strong) when party-like names extracted + matter-linked

Then rematerialize is a separate step (title_brief / matter_brief / fact_fields from facts).

  python3 scripts/populate_tables_from_docs.py --go
  python3 scripts/populate_tables_from_docs.py --go --limit 100
  python3 scripts/populate_tables_from_docs.py --go --rebuild   # wipe document_fields first

$0, no LLM. Verbatim span rule on every field.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_fact_fields import extract_from_text  # noqa: E402 — delicate number decoders
from party_name_gate import is_party_name  # noqa: E402 — shared NAME-shape gate

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Lightweight party patterns — only labeled roles (no free-name guessing).
# Keyword match is case-insensitive (scoped (?i:...)), but the NAME part is
# case-SENSITIVE: capitalized tokens with optional lowercase connectors. The
# old version ran the whole pattern under re.I, so [A-Z] matched any letter
# and 60 chars of prose became a "party" (64% junk — agent_sim finding).
RE_PARTY = re.compile(
    r"\b(?i:Plaintiffs?|Defendants?|Petitioners?|Respondents?|Complainants?|"
    r"Heirs?\s+of|Spouses|Attorney-in-Fact|represented\s+by)\s*[:,]?\s+"
    r"((?:(?:[A-Z][A-Za-z'\-]*\.?|of|the|de|del|dela|la|los)\s+){1,6}"
    r"[A-Z][A-Za-z'\-]*\.?)"
)

# Cap per doc so one megadoc does not explode rows
CAP_PER_KIND = 40


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _ensure(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS document_fields (
            id bigserial PRIMARY KEY,
            doc_id int NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            field_kind text NOT NULL,
            value_raw text NOT NULL,
            value_norm text NOT NULL,
            source_span text NOT NULL,
            char_start int,
            char_end int,
            extraction_method text NOT NULL DEFAULT 'regex',
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (doc_id, field_kind, value_norm)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS table_populate_log (
            id bigserial PRIMARY KEY,
            ran_at timestamptz NOT NULL DEFAULT now(),
            docs_scanned int,
            docs_with_hits int,
            fields_written int,
            titles_linked int,
            parties_written int,
            matter_facts_written int,
            notes text
        )
        """
    )


def _parties_from_text(text: str) -> list[tuple[str, str, str]]:
    """Return (side, name, span)."""
    out = []
    seen = set()
    for m in RE_PARTY.finditer(text[:80000]):
        role = m.group(0).split()[0].lower()
        name = m.group(1).strip(" .,;:")
        name = re.sub(r"\s+", " ", name)[:120]
        if not is_party_name(name):
            continue
        side = "party"
        if "plaintiff" in role or "petitioner" in role or "complainant" in role:
            side = "plaintiff"
        elif "defendant" in role or "respondent" in role:
            side = "defendant"
        elif "heir" in role:
            side = "heir"
        key = (side, name.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((side, name, m.group(0)[:200]))
        if len(out) >= 15:
            break
    return out


def process_doc(cur, doc_id: int, text: str, matter_codes: list[str], go: bool) -> dict:
    stats = {"fields": 0, "titles": 0, "parties": 0, "facts": 0}
    if not text or len(text) < 80:
        return stats

    # 1) Typed fields from FULL text
    fields = extract_from_text(text)
    # cap per kind
    by_kind: dict[str, int] = {}
    kept = []
    for f in fields:
        k = f["field_kind"]
        by_kind[k] = by_kind.get(k, 0) + 1
        if by_kind[k] > CAP_PER_KIND:
            continue
        kept.append(f)

    if go:
        cur.execute("DELETE FROM document_fields WHERE doc_id = %s", (doc_id,))

    for f in kept:
        stats["fields"] += 1
        if not go:
            continue
        cur.execute(
            """
            INSERT INTO document_fields
                (doc_id, field_kind, value_raw, value_norm, source_span,
                 char_start, char_end, extraction_method)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'regex')
            ON CONFLICT (doc_id, field_kind, value_norm) DO UPDATE SET
                value_raw = EXCLUDED.value_raw,
                source_span = EXCLUDED.source_span,
                char_start = EXCLUDED.char_start,
                char_end = EXCLUDED.char_end
            """,
            (
                doc_id,
                f["field_kind"],
                f["value_raw"][:300],
                f["value_norm"][:200],
                f["source_span"][:300],
                f.get("char_start"),
                f.get("char_end"),
            ),
        )

        # 2) document_titles for title kinds
        if f["field_kind"] in ("tct", "oct", "e_title"):
            tno = f["value_norm"]
            if f["field_kind"] == "tct" and not tno.upper().startswith("T"):
                tno = f["value_norm"]
            stats["titles"] += 1
            try:
                cur.execute(
                    """
                    INSERT INTO document_titles (doc_id, tct_number, mentions, source)
                    VALUES (%s, %s, 1, 'doc_populate')
                    ON CONFLICT (doc_id, tct_number) DO UPDATE SET
                        mentions = document_titles.mentions + 1,
                        source = COALESCE(document_titles.source, 'doc_populate')
                    """,
                    (doc_id, tno[:80]),
                )
            except psycopg2.Error:
                pass

    # 3) Matter-linked: write atomic matter_facts (inferred_strong) so tables fill
    if matter_codes and go:
        # wipe prior doc_populate facts for this doc+matters (idempotent rewrite)
        for mc in matter_codes:
            cur.execute(
                """
                DELETE FROM matter_facts
                WHERE matter_code=%s AND source_kind='doc' AND source_id=%s
                  AND created_by='doc_populate'
                """,
                (mc, str(doc_id)),
            )
        for f in kept:
            if f["field_kind"] in ("forum",):  # low value as fact statement alone
                continue
            stmt = f"{f['field_kind'].upper()}: {f['value_norm']}"
            for mc in matter_codes[:6]:  # cap multi-link spam
                try:
                    cur.execute(
                        """
                        INSERT INTO matter_facts
                            (matter_code, statement, fact_kind, source_kind, source_id,
                             excerpt, provenance_level, created_by, created_at)
                        VALUES (%s,%s,%s,'doc',%s,%s,'inferred_strong','doc_populate', now())
                        """,
                        (
                            mc,
                            stmt[:500],
                            f["field_kind"],
                            str(doc_id),
                            f["source_span"][:400],
                        ),
                    )
                    stats["facts"] += 1
                except psycopg2.Error:
                    # provenance/unique/gate — skip, do not invent
                    pass

    # 4) Parties (labeled only) → matter_parties when linked
    parties = _parties_from_text(text)
    if matter_codes and go:
        for side, name, span in parties:
            for mc in matter_codes[:4]:
                try:
                    cur.execute(
                        """
                        SELECT id FROM matter_parties
                        WHERE matter_code=%s AND lower(party_name)=lower(%s) AND side=%s
                        LIMIT 1
                        """,
                        (mc, name, side),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(
                        """
                        INSERT INTO matter_parties
                            (matter_code, entity_id, party_name, side, role,
                             provenance_level, source_doc_id, source_excerpt)
                        VALUES (%s, NULL, %s, %s, %s, 'inferred_strong', %s, %s)
                        """,
                        (mc, name[:200], side, side, doc_id, span[:400]),
                    )
                    stats["parties"] += 1
                except psycopg2.Error:
                    pass

    return stats


def run(go: bool, rebuild: bool, limit: int | None, min_len: int):
    t0 = time.time()
    c = _conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)

    if rebuild and go:
        cur.execute("TRUNCATE document_fields RESTART IDENTITY")
        cur.execute(
            "DELETE FROM matter_facts WHERE created_by = 'doc_populate'"
        )
        print("[populate] wiped document_fields + matter_facts created_by=doc_populate")

    sql = """
        SELECT d.id,
               d.extracted_text,
               coalesce(array_agg(DISTINCT l.matter_code) FILTER (WHERE l.matter_code IS NOT NULL), '{}') AS matters
        FROM documents d
        LEFT JOIN document_matter_links l ON l.doc_id = d.id
        WHERE length(coalesce(d.extracted_text, '')) >= %s
        GROUP BY d.id
        ORDER BY d.id
    """
    params: list = [min_len]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()

    scanned = hits = fields = titles = parties = facts = 0
    for i, r in enumerate(rows, 1):
        scanned += 1
        text = r["extracted_text"] or ""
        matters = list(r["matters"] or [])
        st = process_doc(cur, int(r["id"]), text, matters, go)
        if st["fields"]:
            hits += 1
        fields += st["fields"]
        titles += st["titles"]
        parties += st["parties"]
        facts += st["facts"]
        if i % 200 == 0:
            print(f"  … {i}/{len(rows)} docs  fields+={fields} facts+={facts}", flush=True)

    mode = "WROTE" if go else "DRY"
    elapsed = time.time() - t0
    print(
        f"[populate] {mode} scanned={scanned} with_hits={hits} "
        f"document_fields={fields} title_links={titles} parties={parties} "
        f"matter_facts={facts} in {elapsed:.1f}s"
    )

    if go:
        cur.execute(
            """
            INSERT INTO table_populate_log
                (docs_scanned, docs_with_hits, fields_written, titles_linked,
                 parties_written, matter_facts_written, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (scanned, hits, fields, titles, parties, facts, "populate_tables_from_docs"),
        )
        cur.execute(
            """
            SELECT field_kind, count(*) n, count(DISTINCT doc_id) docs
            FROM document_fields GROUP BY 1 ORDER BY n DESC
            """
        )
        print("  document_fields by kind:")
        for row in cur.fetchall():
            print(f"    {row['field_kind']:<12} n={row['n']:<7} docs={row['docs']}")
        cur.execute("SELECT count(*) n FROM document_fields")
        print(f"  document_fields total rows: {cur.fetchone()['n']}")
        cur.execute("SELECT count(*) n FROM matter_facts WHERE created_by='doc_populate'")
        print(f"  matter_facts doc_populate: {cur.fetchone()['n']}")

    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser(description="Serious bulk table population from full doc text")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-len", type=int, default=200)
    a = ap.parse_args()
    run(a.go, a.rebuild, a.limit, a.min_len)


if __name__ == "__main__":
    main()
