"""title_chain_walker.py — Walk title chain meticulously, with canon overrides.

Consumes:
  - title_chain_canon.OPERATIVE_ROOTS / TRUNKS / GHOST_TITLES (canonical knowledge)
  - Postgres `title_chain` table (DB edges, with OCR-noise and missing intermediates)
  - Postgres `titles` table (per-title metadata when available)

Produces:
  - walk_ancestors(cur, title, matter)         — ordered list of edges from
                                                  `title` up toward operative root,
                                                  stopping at OPERATIVE_ROOTS,
                                                  skipping GHOST_TITLES.
  - render_chain_md(cur, title, matter)        — Markdown chain snippet for
                                                  evidence sections (per-claim).
  - chain_integrity_audit(cur, titles, matter) — gap report for a set of titles
                                                  (missing edges, NULL source_doc_id,
                                                  inferred_weak, ghost-as-parent).

Design principles:
  1. Canon trumps DB.  If canon says T-111 is the operative root for MWK-001
     and the DB has "OCT T-106 → T-4497", the walker reports T-4497 → T-111
     (via canon's `canonical_parent`) and flags the DB ghost-shortcut.
  2. Every edge surfaced is defensible.  Each step has (parent, child,
     provenance, source_doc_id_or_canon, notes) so the user can see WHERE the
     edge comes from.
  3. Ghost titles are never roots.  They are surfaced as "ghost reference"
     annotations on edges, never as the apparent ancestor.
"""

from title_chain_canon import (
    GHOST_TITLES,
    GHOST_ALIASES,
    OPERATIVE_ROOTS,
    TRUNKS,
    canonicalize_ghost,
    is_ghost,
    operative_root_for,
    trunk_metadata,
)


def _fetch_parents(cur, child_title, case_file=None):
    """Pull parent_title rows from title_chain for a given child.

    Includes subdivision_plan info via LEFT JOIN (deploy_219).
    """
    sql = """
        SELECT tc.parent_title, tc.provenance_level, tc.source_doc_id, tc.relationship,
               tc.subdivision_plan_id,
               sp.plan_ref AS plan_ref, sp.normalized_ref AS plan_normalized_ref
          FROM title_chain tc
          LEFT JOIN subdivision_plans sp ON sp.id = tc.subdivision_plan_id
         WHERE tc.child_title = %s
    """
    params = [child_title]
    if case_file:
        sql += " AND (tc.case_file = %s OR tc.case_file IS NULL)"
        params.append(case_file)
    cur.execute(sql, params)
    return cur.fetchall()


def walk_ancestors(cur, start_title, matter="MWK-001", max_depth=10):
    """Walk up the title chain from `start_title` toward the operative root.

    Returns a list of edge dicts: [{parent, child, provenance, source, notes}, ...]
    in order from start → root. Stops at OPERATIVE_ROOTS[matter]. Skips ghost
    parents (annotates them on the preceding edge's `notes` and continues using
    canonical_parent if known).
    """
    operative_root = operative_root_for(matter)
    chain = []
    seen = {start_title}
    current = start_title
    depth = 0

    while depth < max_depth:
        depth += 1

        # If current is the operative root, stop.
        if current == operative_root:
            return chain

        # If current is in TRUNKS with a canonical_parent, prefer that edge
        # over whatever the DB says — canon trumps DB ambiguity.
        trunk = trunk_metadata(current)
        if trunk and trunk.get("canonical_parent"):
            parent = trunk["canonical_parent"]
            chain.append({
                "parent": parent,
                "child": current,
                "provenance": "canon",
                "source": f"title_chain_canon.TRUNKS[{current!r}].canonical_parent",
                "notes": trunk.get("notes", ""),
            })
            if parent in seen:
                chain[-1]["notes"] += " (cycle detected; stopping)"
                return chain
            seen.add(parent)
            current = parent
            continue

        # Otherwise, consult title_chain DB.
        parents = _fetch_parents(cur, current, case_file=matter)
        if not parents:
            # No further ancestry recorded.
            return chain

        # Filter out ghost parents (or canonicalize and flag).
        real_parents = []
        ghost_refs = []
        for p in parents:
            pt = p["parent_title"]
            if is_ghost(pt):
                ghost_refs.append(canonicalize_ghost(pt) or pt)
            else:
                real_parents.append(p)

        if not real_parents:
            # Only ghost parents in DB — surface that finding.
            ghost_str = ", ".join(sorted(set(ghost_refs)))
            chain.append({
                "parent": None,
                "child": current,
                "provenance": "ghost_only",
                "source": "title_chain (all parent edges point to ghost titles)",
                "notes": f"DB has ghost parent(s): {ghost_str}. No real operative parent recorded — chain ends here.",
            })
            return chain

        # Prefer the highest-provenance parent, then earliest-id (deterministic).
        prov_order = {"verified": 0, "inferred_strong": 1, "inferred_corroborated": 2,
                      "inferred_weak": 3, None: 4}
        real_parents.sort(key=lambda r: (prov_order.get(r["provenance_level"], 5),
                                         r["parent_title"] or ""))
        chosen = real_parents[0]
        parent = chosen["parent_title"]
        notes_parts = []
        if ghost_refs:
            notes_parts.append(f"DB also had ghost-parent refs: {', '.join(sorted(set(ghost_refs)))}")
        if not chosen.get("source_doc_id"):
            notes_parts.append("source_doc_id is NULL — edge unverifiable from corpus")
        if len(real_parents) > 1:
            others = [r["parent_title"] for r in real_parents[1:]]
            notes_parts.append(f"DB had {len(real_parents)} candidate parents: also {others}")

        chain.append({
            "parent": parent,
            "child": current,
            "provenance": chosen.get("provenance_level") or "?",
            "source": f"title_chain row" + (f" doc#{chosen['source_doc_id']}" if chosen.get("source_doc_id") else " (no source doc)"),
            "subdivision_plan_ref": chosen.get("plan_normalized_ref") or chosen.get("plan_ref"),
            "notes": "; ".join(notes_parts),
        })

        if parent in seen:
            chain[-1]["notes"] += "; cycle detected, stopping"
            return chain
        seen.add(parent)
        current = parent

    chain.append({"parent": None, "child": current,
                  "provenance": "?", "source": "walker",
                  "notes": f"max_depth ({max_depth}) reached"})
    return chain


def render_chain_md(cur, start_title, matter="MWK-001"):
    """Render the ancestral chain as a Markdown snippet for evidence prep."""
    chain = walk_ancestors(cur, start_title, matter)
    if not chain:
        return f"_No ancestral chain recorded for `{start_title}`._"

    lines = []
    lines.append(f"**Ancestral chain for `{start_title}`** "
                 f"(walked toward operative root `{operative_root_for(matter) or '?'}`):")
    lines.append("")
    lines.append("```")
    # Render: child → parent → grandparent → ... → root
    titles_in_chain = [chain[0]["child"]]
    for edge in chain:
        if edge["parent"]:
            titles_in_chain.append(edge["parent"])
    lines.append(" → ".join(titles_in_chain))
    lines.append("```")
    lines.append("")
    lines.append("Per-edge provenance:")
    lines.append("")
    lines.append("| Child | Parent | Provenance | Subdivision plan | Source | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for e in chain:
        parent_disp = e["parent"] or "_(none)_"
        notes_disp = (e.get("notes") or "").replace("|", "/")
        plan_ref = e.get("subdivision_plan_ref") or "—"
        lines.append(f"| `{e['child']}` | `{parent_disp}` | "
                     f"`{e['provenance']}` | `{plan_ref}` | {e['source']} | {notes_disp} |")

    # Add trunk metadata if the chain terminates at a known trunk
    root = chain[-1]["parent"] or chain[-1]["child"]
    tm = trunk_metadata(root)
    if tm:
        lines.append("")
        lines.append(f"**Root trunk metadata (`{root}`):**")
        lines.append("")
        for k, v in tm.items():
            if k == "notes":
                continue
            lines.append(f"- **{k}:** {v}")
        if tm.get("notes"):
            lines.append("")
            lines.append(f"> {tm['notes']}")
    return "\n".join(lines)


def render_annotations_md(cur, title, limit=15):
    """Render instruments_on_title rows for a title as a Markdown table.

    Surfaces the per-title annotation history (deeds, confirmations, affidavits,
    etc.) extracted into instruments_on_title — the operative legal-act record
    for what happened on this title.

    For mediation prep + cross-examination defense (deploy_220-B).
    """
    cur.execute("""
        SELECT id, entry_date, instrument_type, executor_full_name, pe_number,
               LEFT(COALESCE(acknowledgment_quote, source_quote_full, ''), 80) AS quote
          FROM instruments_on_title
         WHERE parent_tct_number = %s
         ORDER BY entry_date NULLS LAST, id
         LIMIT %s
    """, (title, limit))
    rows = cur.fetchall()
    if not rows:
        return (f"_No annotations extracted for `{title}` in `instruments_on_title`. "
                f"Either no encumbrances exist on this title, or the title's physical doc "
                f"needs heightened OCR extraction._")
    lines = []
    lines.append(f"**Annotations for `{title}`** ({len(rows)} extracted):")
    lines.append("")
    lines.append("| Entry date | Instrument type | Executor | PE # |")
    lines.append("|---|---|---|---|")
    for r in rows:
        date_str = str(r.get("entry_date") or "—")[:10]
        itype = (r.get("instrument_type") or "?")[:35]
        exec_n = (r.get("executor_full_name") or "—")[:40]
        pe = (r.get("pe_number") or "—")[:25]
        lines.append(f"| {date_str} | {itype} | {exec_n} | {pe} |")
    return "\n".join(lines)


def chain_integrity_audit(cur, titles, matter="MWK-001"):
    """For each title in `titles`, audit its chain and flag issues.

    Returns list of dicts: {title, chain_length, issues: [...]}.
    """
    audit = []
    for t in titles:
        chain = walk_ancestors(cur, t, matter)
        issues = []
        for e in chain:
            if e["provenance"] == "ghost_only":
                issues.append(f"chain ends in ghost-only references: {e.get('notes', '')}")
            if e["provenance"] in ("inferred_weak", "?"):
                issues.append(f"`{e['child']}` → `{e['parent']}` is `{e['provenance']}` provenance")
            if "source_doc_id is NULL" in (e.get("notes") or ""):
                issues.append(f"`{e['child']}` → `{e['parent']}` has no source doc")
            if e.get("parent") and not e.get("subdivision_plan_ref"):
                issues.append(f"`{e['child']}` → `{e['parent']}` has no linked subdivision plan")
        last = chain[-1] if chain else None
        if last and last.get("parent") and last["parent"] != operative_root_for(matter):
            issues.append(f"chain terminates at `{last['parent']}`, not operative root `{operative_root_for(matter)}`")
        audit.append({
            "title": t,
            "chain_length": len(chain),
            "issues": issues,
        })
    return audit


if __name__ == "__main__":
    # Smoke test: walk T-32917 and T-4497 from CLI.
    import sys
    import psycopg2
    import psycopg2.extras
    DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    titles = sys.argv[1:] if len(sys.argv) > 1 else ["T-32917", "T-4497", "T-52540", "T-079-2021002127"]
    for t in titles:
        print(render_chain_md(cur, t))
        print()
        print("=" * 72)
        print()
    cur.close(); conn.close()
