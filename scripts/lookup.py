#!/usr/bin/env python3
"""lookup.py — Universal "give me everything attached to X" query.

The deterministic answer to: "all data pertaining to Atty. Del Rosario" /
"all data on matter MWK-ARTA-1210" / "all data on TCT T-4497" / "all data
on doc#465".

No LLM in the path. Pure SQL composition. Falls back to text grep when
an entity isn't yet canonicalized in `entities` (e.g., Del Rosario before
the proposed_changes promotion lands).

Usage:
  python3 scripts/lookup.py --entity "Del Rosario"
  python3 scripts/lookup.py --entity 1348             # by entity id
  python3 scripts/lookup.py --matter MWK-ARTA-1210
  python3 scripts/lookup.py --title T-4497
  python3 scripts/lookup.py --doc 465
  python3 scripts/lookup.py --out drafts/dump_<id>.md  # write to file
"""
import argparse
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# ─── Helpers ────────────────────────────────────────────────────────────────

def all_rows(cur, sql, params=()):
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    return cur.fetchall()


def fmt_doc_row(d):
    """Compact one-line doc render."""
    cls = d.get("classification") or "?"
    dt = d.get("doc_date") or "?"
    fn = (d.get("smart_filename") or "(unnamed)")[:70]
    return f"doc#{d['id']:<4d} [{cls:<25.25s}] {dt}  {fn}"


def fmt_email_row(e):
    sender = e.get("from_name") or (e.get("from_addr") or "?")[:30]
    subj = (e.get("subject") or "(no subject)")[:90]
    dt = e.get("d") or "?"
    mc = ", ".join(e.get("matter_codes") or []) or "—"
    return f"gmail#{e['id']:<6d} {dt}  from={sender[:30]:<30s} [{mc}]  {subj}"


def fmt_res_row(r):
    forum = r.get("forum") or "?"
    disp = r.get("disposition") or "?"
    dt = r.get("resolution_date") or "?"
    mc = ", ".join(r.get("affected_matter_codes") or []) or "—"
    src = f"doc#{r['source_doc_id']}" if r.get("source_doc_id") else "—"
    return f"res#{r['id']:<4d} {dt}  forum={forum:<6s} disp={disp:<18s} [{mc}]  ({src})"


# ─── Entity lookup ──────────────────────────────────────────────────────────

def find_entity(cur, identifier):
    """Return entity dict or None. Handles id (int), canonical_name, alias."""
    if isinstance(identifier, str) and identifier.isdigit():
        identifier = int(identifier)
    if isinstance(identifier, int):
        rows = all_rows(cur, "SELECT * FROM entities WHERE id = %s", (identifier,))
        return rows[0] if rows else None
    # String: try exact canonical_name first, then alias, then fuzzy
    for sql, p in [
        ("SELECT * FROM entities WHERE canonical_name = %s LIMIT 1", (identifier,)),
        ("SELECT * FROM entities WHERE %s = ANY(aliases) LIMIT 1", (identifier,)),
        ("SELECT * FROM entities WHERE canonical_name ILIKE %s "
         "ORDER BY mentions_count DESC NULLS LAST LIMIT 1", (f"%{identifier}%",)),
    ]:
        rows = all_rows(cur, sql, p)
        if rows:
            return rows[0]
    return None


def lookup_entity(cur, identifier):
    """Return structured Markdown summary of everything attached to the entity."""
    lines = []
    e = find_entity(cur, identifier)

    if e:
        lines.append(f"# Entity: {e['canonical_name']}")
        lines.append("")
        lines.append(f"- **id:** {e['id']}")
        lines.append(f"- **type:** {e['type']}")
        lines.append(f"- **provenance:** {e.get('provenance_level')}")
        lines.append(f"- **mentions_count:** {e.get('mentions_count')}")
        if e.get("role"):
            lines.append(f"- **role:** {e['role']}")
        if e.get("affiliation"):
            lines.append(f"- **affiliation:** {e['affiliation']}")
        aliases = e.get("aliases") or []
        if aliases:
            lines.append(f"- **aliases ({len(aliases)}):** {', '.join(aliases[:12])}{'…' if len(aliases) > 12 else ''}")
        lines.append("")

        # Structured doc linkages via doc_entities
        docs = all_rows(cur, """
            SELECT d.id, d.smart_filename, d.classification, d.doc_date,
                   de.role, de.confidence, de.provenance_level
              FROM doc_entities de
              JOIN documents d ON d.id = de.doc_id
             WHERE de.entity_id = %s
             ORDER BY d.doc_date DESC NULLS LAST, d.id DESC
        """, (e["id"],))
        if docs:
            lines.append(f"## Documents linked via `doc_entities` ({len(docs)})")
            lines.append("")
            for d in docs[:50]:
                role = d.get("role") or "?"
                lines.append(f"- `{role}` · {fmt_doc_row(d)}")
            if len(docs) > 50:
                lines.append(f"- _… {len(docs) - 50} more (showing top 50 by date)_")
            lines.append("")
    else:
        lines.append(f"# Entity lookup: '{identifier}'")
        lines.append("")
        lines.append("_Entity not found in `entities` table. Falling back to text-grep over docs + emails._")
        lines.append("")
        lines.append("To structure this entity, propose it via `proposed_changes` then run "
                     "`scripts/promote_proposals.py review --table entities`.")
        lines.append("")

    # Build text-grep search terms
    search_terms = []
    if e:
        search_terms.append(e["canonical_name"])
        search_terms.extend(e.get("aliases") or [])
    else:
        search_terms.append(identifier)
    # Dedupe + filter
    search_terms = sorted(set(t for t in search_terms if t and len(t) >= 3))

    # Text-grep over docs
    if search_terms:
        like_clauses = " OR ".join(["extracted_text ILIKE %s"] * len(search_terms))
        params = tuple(f"%{t}%" for t in search_terms)
        grep_docs = all_rows(cur, f"""
            SELECT id, smart_filename, classification, doc_date, case_file
              FROM documents
             WHERE ({like_clauses})
                AND id NOT IN (
                    SELECT doc_id FROM doc_entities WHERE entity_id = %s
                )
             ORDER BY doc_date DESC NULLS LAST, id DESC
             LIMIT 50
        """, params + (e["id"] if e else -1,))
        if grep_docs:
            lines.append(f"## Documents found by text grep (not in `doc_entities`) ({len(grep_docs)})")
            lines.append("")
            for d in grep_docs:
                lines.append(f"- {fmt_doc_row(d)}")
            lines.append("")

        # Emails by grep
        em_clauses = " OR ".join(
            ["subject ILIKE %s", "body_plain ILIKE %s"] * len(search_terms)
        )
        em_params = []
        for t in search_terms:
            em_params.extend([f"%{t}%", f"%{t}%"])
        emails = all_rows(cur, f"""
            SELECT id, sent_at::date AS d, from_name, from_addr, subject, matter_codes
              FROM gmail_messages
             WHERE ({em_clauses})
             ORDER BY sent_at DESC NULLS LAST
             LIMIT 50
        """, tuple(em_params))
        if emails:
            lines.append(f"## Emails mentioning this entity ({len(emails)})")
            lines.append("")
            for em in emails:
                lines.append(f"- {fmt_email_row(em)}")
            lines.append("")

        # Resolutions where adjudicator_name_raw or notes mention
        res_clauses = " OR ".join(
            ["adjudicator_name_raw ILIKE %s", "disposition_summary ILIKE %s", "notes ILIKE %s"] * len(search_terms)
        )
        res_params = []
        for t in search_terms:
            res_params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])
        if e:
            res_clauses += " OR adjudicator_entity_id = %s"
            res_params.append(e["id"])
        ress = all_rows(cur, f"""
            SELECT id, resolution_date, forum, disposition, source_doc_id,
                   adjudicator_name_raw, affected_matter_codes,
                   LEFT(COALESCE(disposition_summary, ''), 60) AS summary
              FROM resolutions
             WHERE ({res_clauses})
             ORDER BY resolution_date DESC NULLS LAST
        """, tuple(res_params))
        if ress:
            lines.append(f"## Resolutions linked to this entity ({len(ress)})")
            lines.append("")
            for r in ress:
                lines.append(f"- {fmt_res_row(r)}")
            lines.append("")

    return "\n".join(lines)


# ─── Matter lookup ──────────────────────────────────────────────────────────

def lookup_matter(cur, matter_code):
    lines = []
    rows = all_rows(cur, "SELECT * FROM matters WHERE matter_code = %s", (matter_code,))
    if not rows:
        return f"_(matter `{matter_code}` not found)_"
    m = rows[0]
    lines.append(f"# Matter: {matter_code}")
    lines.append("")
    lines.append(f"- **type:** {m.get('matter_type')}")
    lines.append("")

    arta = all_rows(cur, "SELECT * FROM arta_cases WHERE matter_code = %s", (matter_code,))
    if arta:
        a = arta[0]
        lines.append("## ARTA case meta")
        lines.append("")
        lines.append(f"- **CTN:** {a['ctn_no']}")
        lines.append(f"- **Status:** {a['status']}")
        lines.append(f"- **Forum:** {a.get('forum') or '?'}")
        lines.append(f"- **Respondents:** {', '.join(a.get('respondents') or []) or '?'}")
        lines.append(f"- **Subject:** {a.get('subject_summary') or '?'}")
        lines.append(f"- **Last activity:** {a.get('last_activity')}")
        lines.append(f"- **Emails:** {a.get('email_count')} ({a.get('attachment_count')} attachments)")
        if a.get("adjudicator_entity_id"):
            adj = all_rows(cur, "SELECT canonical_name FROM entities WHERE id = %s",
                            (a["adjudicator_entity_id"],))
            if adj:
                lines.append(f"- **Adjudicator:** {adj[0]['canonical_name']}")
        lines.append("")

    docs = all_rows(cur, """
        SELECT id, smart_filename, classification, doc_date
          FROM documents WHERE matter_code = %s
         ORDER BY doc_date DESC NULLS LAST, id DESC
    """, (matter_code,))
    if docs:
        lines.append(f"## Documents tagged to this matter ({len(docs)})")
        lines.append("")
        for d in docs[:50]:
            lines.append(f"- {fmt_doc_row(d)}")
        if len(docs) > 50:
            lines.append(f"- _… {len(docs) - 50} more_")
        lines.append("")

    emails = all_rows(cur, """
        SELECT id, sent_at::date AS d, from_name, from_addr, subject, matter_codes
          FROM gmail_messages WHERE %s = ANY(matter_codes)
         ORDER BY sent_at DESC NULLS LAST
    """, (matter_code,))
    if emails:
        lines.append(f"## Emails on this matter ({len(emails)})")
        lines.append("")
        for em in emails[:60]:
            lines.append(f"- {fmt_email_row(em)}")
        if len(emails) > 60:
            lines.append(f"- _… {len(emails) - 60} more_")
        lines.append("")

    ress = all_rows(cur, """
        SELECT id, resolution_date, forum, disposition, source_doc_id,
               adjudicator_name_raw, affected_matter_codes
          FROM resolutions WHERE %s = ANY(affected_matter_codes)
         ORDER BY resolution_date DESC NULLS LAST
    """, (matter_code,))
    if ress:
        lines.append(f"## Resolutions affecting this matter ({len(ress)})")
        lines.append("")
        for r in ress:
            lines.append(f"- {fmt_res_row(r)}")
        lines.append("")

    return "\n".join(lines)


# ─── Title lookup ───────────────────────────────────────────────────────────

def lookup_title(cur, title):
    lines = []
    rows = all_rows(cur, "SELECT * FROM titles WHERE tct_number = %s", (title,))
    lines.append(f"# Title: `{title}`")
    lines.append("")
    if rows:
        t = rows[0]
        lines.append(f"- **registrant_canonical:** {t.get('registrant_canonical') or '?'}")
        lines.append(f"- **lifecycle_status:** {t.get('lifecycle_status') or '?'}")
        lines.append(f"- **area_sqm:** {t.get('area_sqm') or '?'}")
        lines.append("")
    else:
        lines.append("_(not in `titles` table)_")
        lines.append("")

    # Chain edges in/out
    edges_in = all_rows(cur, """
        SELECT parent_title, provenance_level, source_doc_id, subdivision_plan_id
          FROM title_chain WHERE child_title = %s
    """, (title,))
    edges_out = all_rows(cur, """
        SELECT child_title, provenance_level, source_doc_id, subdivision_plan_id
          FROM title_chain WHERE parent_title = %s
    """, (title,))
    if edges_in:
        lines.append(f"## Parent edges ({len(edges_in)})")
        for e in edges_in:
            src = f"doc#{e['source_doc_id']}" if e.get("source_doc_id") else "(no source)"
            plan = f"plan#{e['subdivision_plan_id']}" if e.get("subdivision_plan_id") else "(no plan)"
            lines.append(f"- ← `{e['parent_title']}` · {e['provenance_level']} · {src} · {plan}")
        lines.append("")
    if edges_out:
        lines.append(f"## Child edges ({len(edges_out)})")
        for e in edges_out:
            src = f"doc#{e['source_doc_id']}" if e.get("source_doc_id") else "(no source)"
            plan = f"plan#{e['subdivision_plan_id']}" if e.get("subdivision_plan_id") else "(no plan)"
            lines.append(f"- → `{e['child_title']}` · {e['provenance_level']} · {src} · {plan}")
        lines.append("")

    # Annotations on this title
    annos = all_rows(cur, """
        SELECT id, entry_date, instrument_type, executor_full_name, pe_number
          FROM instruments_on_title
         WHERE parent_tct_number = %s
         ORDER BY entry_date NULLS LAST
    """, (title,))
    if annos:
        lines.append(f"## Annotations on this title ({len(annos)})")
        lines.append("")
        for a in annos[:30]:
            lines.append(f"- {a.get('entry_date') or '?':10}  {a.get('instrument_type') or '?':<35.35s}  "
                         f"executor: {(a.get('executor_full_name') or '—')[:35]:<35s}  PE: {a.get('pe_number') or '—'}")
        lines.append("")

    # Docs mentioning this title (grep)
    docs = all_rows(cur, """
        SELECT id, smart_filename, classification, doc_date
          FROM documents WHERE extracted_text ILIKE %s OR smart_filename ILIKE %s
         ORDER BY doc_date DESC NULLS LAST LIMIT 30
    """, (f"%{title}%", f"%{title}%"))
    if docs:
        lines.append(f"## Documents mentioning this title (top 30)")
        lines.append("")
        for d in docs:
            lines.append(f"- {fmt_doc_row(d)}")
        lines.append("")

    return "\n".join(lines)


# ─── Doc lookup ─────────────────────────────────────────────────────────────

def lookup_doc(cur, doc_id):
    rows = all_rows(cur, "SELECT * FROM documents WHERE id = %s", (doc_id,))
    if not rows:
        return f"_(doc#{doc_id} not found)_"
    d = rows[0]
    lines = [f"# Document: doc#{doc_id}", ""]
    lines.append(f"- **filename:** {d.get('smart_filename')}")
    lines.append(f"- **classification:** {d.get('classification') or '?'}")
    lines.append(f"- **execution_status:** {d.get('execution_status') or '?'}")
    lines.append(f"- **doc_date:** {d.get('doc_date') or '?'}")
    lines.append(f"- **case_file:** {d.get('case_file') or '?'}")
    lines.append(f"- **matter_code:** {d.get('matter_code') or '?'}")
    lines.append(f"- **extracted_text length:** {len(d.get('extracted_text') or '')} chars")
    lines.append("")
    ents = all_rows(cur, """
        SELECT de.role, e.id, e.canonical_name, e.provenance_level
          FROM doc_entities de JOIN entities e ON e.id = de.entity_id
         WHERE de.doc_id = %s
         ORDER BY de.confidence DESC NULLS LAST, e.canonical_name
    """, (doc_id,))
    if ents:
        lines.append(f"## Entities mentioned ({len(ents)})")
        lines.append("")
        for en in ents:
            lines.append(f"- `{en['role']}` · #{en['id']} {en['canonical_name']} ({en['provenance_level']})")
        lines.append("")
    res = all_rows(cur, "SELECT * FROM resolutions WHERE source_doc_id = %s", (doc_id,))
    if res:
        lines.append(f"## Resolutions sourced from this doc ({len(res)})")
        lines.append("")
        for r in res:
            lines.append(f"- {fmt_res_row(r)}")
        lines.append("")
    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--entity", help="Entity name, alias, or id")
    g.add_argument("--matter", help="matter_code, e.g., MWK-ARTA-1210")
    g.add_argument("--title", help="TCT number, e.g., T-4497")
    g.add_argument("--doc", type=int, help="doc id, e.g., 465")
    ap.add_argument("--out", help="Write to file instead of stdout")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.entity:
        out = lookup_entity(cur, args.entity)
    elif args.matter:
        out = lookup_matter(cur, args.matter)
    elif args.title:
        out = lookup_title(cur, args.title)
    else:
        out = lookup_doc(cur, args.doc)

    cur.close()
    conn.close()

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out)
        print(f"Wrote {len(out.splitlines())} lines to {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
