#!/usr/bin/env python3
"""canonical_matter_dashboard.py — The "easily referenced" canonical view.

For any one matter (or all), emit a deterministic Markdown summary pulling
ONLY from structured tables. No LLM. No synthesis. Every fact has a source row.

Sections per matter:
  1. Header — matter_code, matter_type, key parties
  2. ARTA case meta (if applicable) — CTN, respondents, last activity, forum
  3. Resolutions timeline — every resolution affecting this matter (date, forum,
     disposition, source_doc#)
  4. Recent correspondence — last 10 emails linked to this matter
  5. Open deadlines (from case_deadlines if any)

Usage:
  python3 scripts/canonical_matter_dashboard.py --matter MWK-ARTA-1210
  python3 scripts/canonical_matter_dashboard.py --all
  python3 scripts/canonical_matter_dashboard.py --all --out drafts/canonical_dashboard.md

This is the structured-data answer to "canonical bible easily referenced."
LLM bibles (generate_case_bible.py) layer narrative ON TOP of this — keep that
separation visible by labeling outputs distinctly.
"""
import argparse
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def render_matter(cur, matter_code):
    """Build one matter's section."""
    lines = []
    cur.execute("SELECT * FROM matters WHERE matter_code = %s", (matter_code,))
    m = cur.fetchone()
    if not m:
        return f"_(matter `{matter_code}` not found)_"

    lines.append(f"## `{matter_code}` — {m.get('matter_type') or '?'}")
    lines.append("")

    # ARTA case meta
    cur.execute("""
        SELECT ctn_no, status, last_activity, forum, respondents, subject_summary,
               email_count, attachment_count, next_deadline, next_action,
               adjudicator_entity_id
          FROM arta_cases WHERE matter_code = %s
    """, (matter_code,))
    arta = cur.fetchone()
    if arta:
        lines.append("### ARTA case meta")
        lines.append("")
        lines.append(f"- **CTN:** {arta['ctn_no']}")
        lines.append(f"- **Status:** {arta['status']}")
        lines.append(f"- **Forum:** {arta['forum'] or '_(not set)_'}")
        respondents = arta.get("respondents") or []
        lines.append(f"- **Respondents:** {', '.join(respondents) if respondents else '_(not extracted)_'}")
        if arta.get("subject_summary"):
            lines.append(f"- **Subject:** {arta['subject_summary']}")
        lines.append(f"- **Last activity:** {arta['last_activity'] or '_(unknown)_'}")
        lines.append(f"- **Email/attachment counts:** {arta['email_count']} emails, {arta['attachment_count']} attachments")
        if arta.get("next_deadline"):
            lines.append(f"- **Next deadline:** {arta['next_deadline']} — {arta.get('next_action') or 'TBD'}")
        if arta.get("adjudicator_entity_id"):
            cur.execute("SELECT canonical_name, affiliation FROM entities WHERE id = %s",
                        (arta["adjudicator_entity_id"],))
            adj = cur.fetchone()
            if adj:
                lines.append(f"- **Adjudicator:** {adj['canonical_name']} ({adj.get('affiliation') or '?'})")
        else:
            lines.append(f"- **Adjudicator:** _(not yet linked — promote proposed entities first)_")
        lines.append("")

    # Resolutions timeline
    cur.execute("""
        SELECT id, resolution_date, forum, disposition, source_doc_id,
               adjudicator_name_raw,
               array_to_string(affected_ctn_nos, ', ') AS ctns,
               LEFT(COALESCE(disposition_summary, ''), 90) AS summary
          FROM resolutions
         WHERE %s = ANY(affected_matter_codes)
         ORDER BY resolution_date DESC NULLS LAST, id DESC
    """, (matter_code,))
    res_rows = cur.fetchall()
    if res_rows:
        lines.append("### Resolutions affecting this matter")
        lines.append("")
        lines.append("| Date | Forum | Disposition | Adjudicator | Source doc | CTNs |")
        lines.append("|---|---|---|---|---|---|")
        for r in res_rows:
            adj_raw = (r.get("adjudicator_name_raw") or "—")[:30]
            src = f"doc#{r['source_doc_id']}" if r["source_doc_id"] else "—"
            lines.append(f"| {r['resolution_date'] or '?'} | {r['forum'] or '?'} | "
                         f"`{r['disposition'] or '?'}` | {adj_raw} | {src} | {r['ctns'] or '—'} |")
        lines.append("")

    # Recent correspondence (last 10)
    cur.execute("""
        SELECT id, sent_at::date AS d, from_name, from_addr, LEFT(subject, 95) AS subj
          FROM gmail_messages
         WHERE %s = ANY(matter_codes)
         ORDER BY sent_at DESC NULLS LAST
         LIMIT 10
    """, (matter_code,))
    em_rows = cur.fetchall()
    if em_rows:
        lines.append("### Recent correspondence (last 10)")
        lines.append("")
        lines.append("| Date | From | Subject |")
        lines.append("|---|---|---|")
        for r in em_rows:
            sender = r["from_name"] or (r["from_addr"] or "?")[:25]
            lines.append(f"| {r['d'] or '?'} | {sender[:30]} | {r['subj'] or '—'} |")
        lines.append("")

    # Case deadlines (if table has rows for this matter)
    try:
        cur.execute("""
            SELECT due_date, deadline_type, status, COALESCE(notes, '') AS notes
              FROM case_deadlines
             WHERE matter_code = %s AND status != 'completed'
             ORDER BY due_date ASC
        """, (matter_code,))
        deadlines = cur.fetchall()
        if deadlines:
            lines.append("### Open deadlines")
            lines.append("")
            for d in deadlines:
                lines.append(f"- **{d['due_date']}** — {d['deadline_type']} (`{d['status']}`)"
                             + (f" — {d['notes'][:120]}" if d['notes'] else ""))
            lines.append("")
    except Exception:
        # case_deadlines may not have matter_code or may not exist with this shape
        pass

    # Coverage footer
    n_res = len(res_rows)
    lines.append(f"_Coverage: {n_res} resolution(s), {len(em_rows)} recent email(s)._")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--matter", help="Single matter_code")
    g.add_argument("--all", action="store_true", help="All matters (MWK + PAR)")
    ap.add_argument("--out", help="Write to file instead of stdout")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True  # so failed queries don't poison subsequent ones
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    out_parts = []
    out_parts.append(f"# Canonical matter dashboard")
    out_parts.append("")
    out_parts.append("_Structured-data view. No LLM in path — every fact pulled from "
                     "matters / arta_cases / resolutions / gmail_messages / case_deadlines._")
    out_parts.append("")

    if args.matter:
        out_parts.append(render_matter(cur, args.matter))
    else:
        cur.execute("""
            SELECT matter_code FROM matters
             WHERE matter_code LIKE 'MWK-%' OR matter_code LIKE 'PAR-%'
             ORDER BY matter_code
        """)
        for r in cur.fetchall():
            out_parts.append(render_matter(cur, r["matter_code"]))

    cur.close()
    conn.close()

    out = "\n".join(out_parts)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(out)
        print(f"Wrote {len(out.splitlines())} lines to {args.out}")
    else:
        print(out)


if __name__ == "__main__":
    main()
