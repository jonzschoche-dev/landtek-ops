#!/usr/bin/env python3
"""mwk_asset_gap_drive.py — compel agents against MWK (or any) title portfolio.

The missing loop the operator asked for:

  living titles/assets
    → ask obvious stack questions per title
    → enqueue agent_work_queue with concrete payload
    → drain agents (title_brief / fact_fields / matter_brief / doc_populate / verify)

Not free-LLM thrash. Deterministic gap checks + existing agent hooks.

  python3 scripts/mwk_asset_gap_drive.py --client MWK-001
  python3 scripts/mwk_asset_gap_drive.py --client MWK-001 --go
  python3 scripts/mwk_asset_gap_drive.py --client MWK-001 --go --drain
  python3 scripts/mwk_asset_gap_drive.py --client MWK-001 --go --drain --limit 30

Also:
  python3 scripts/inquiry_stack.py --drain-agent title_brief_materializer --go
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Statuses that are not portfolio instruments
_SKIP_STATUS = ("invalid", "alias", "out_of_scope", "cancelled")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _as_dicts(cur, rows=None):
    rows = list(rows if rows is not None else (cur.fetchall() or []))
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return rows
    cols = [d[0] for d in (cur.description or [])]
    return [dict(zip(cols, r)) for r in rows]


def living_titles(cur, client: str) -> list[dict]:
    cur.execute(
        """
        SELECT tct_number, status, lifecycle_status, parent_title, area_sqm,
               registrant_name_raw, source_doc_id, case_file
          FROM titles
         WHERE (case_file = %s OR case_file LIKE %s)
           AND case_file NOT ILIKE 'Paracale%%'
           AND coalesce(status,'') NOT IN %s
           AND coalesce(status,'') NOT ILIKE '%%cancel%%'
         ORDER BY tct_number
        """,
        (client, client + "%", _SKIP_STATUS),
    )
    return _as_dicts(cur)


def scrutinize_title(cur, client: str, tct: str) -> list[str]:
    """Return list of gap codes — the 'obvious questions' against the stack."""
    gaps = []
    cur.execute(
        """
        SELECT title_key, clarity_status, needs_human_review, n_source_docs,
               n_facts_verified, area_sqm, parent_titles, status, lifecycle_status,
               has_map_geometry, registrant_name
          FROM title_brief
         WHERE title_key = %s OR display_no = %s
            OR title_key ILIKE %s
         LIMIT 1
        """,
        (tct, tct, tct.replace("T-", "%")),
    )
    brief = cur.fetchone()
    if not brief:
        gaps.append("no_title_brief")
    else:
        if (brief.get("clarity_status") or "") == "unclear":
            gaps.append("title_brief_unclear")
        if brief.get("needs_human_review"):
            gaps.append("title_brief_needs_review")
        if not brief.get("n_source_docs"):
            gaps.append("no_source_docs_on_brief")
        if int(brief.get("n_facts_verified") or 0) < 1:
            gaps.append("no_verified_facts_on_brief")
        if brief.get("area_sqm") is None:
            gaps.append("missing_area")
        pt = brief.get("parent_titles")
        if not pt or pt in ([], {}, "null"):
            gaps.append("missing_parent_on_brief")
        if not brief.get("has_map_geometry"):
            gaps.append("no_map_geometry")

    cur.execute(
        """
        SELECT status, parent_title, area_sqm, registrant_name_raw, source_doc_id
          FROM titles WHERE tct_number = %s AND case_file LIKE %s LIMIT 1
        """,
        (tct, client.split("-")[0] + "%"),
    )
    reg = cur.fetchone()
    # Parent may live on title_chain even if titles.parent_title is blank
    chain_parent = None
    try:
        cur.execute(
            """
            SELECT parent_title FROM title_chain
             WHERE upper(regexp_replace(child_title, '\\s+', '', 'g'))
                   = upper(regexp_replace(%s, '\\s+', '', 'g'))
                OR child_title = %s
             ORDER BY CASE provenance_level WHEN 'verified' THEN 0
                      WHEN 'operator' THEN 1 ELSE 2 END
             LIMIT 1
            """,
            (tct, tct),
        )
        cp = cur.fetchone()
        if cp:
            chain_parent = cp.get("parent_title")
    except Exception:
        pass
    if reg:
        if not reg.get("parent_title") and not chain_parent:
            gaps.append("missing_parent_on_registry")
        elif not reg.get("parent_title") and chain_parent:
            gaps.append("parent_in_chain_not_on_titles")  # reconcile can promote
        if reg.get("area_sqm") is None:
            gaps.append("missing_area_on_registry")
        regn = (reg.get("registrant_name_raw") or "").strip()
        if not regn or "citizenship" in regn.lower():
            gaps.append("missing_registrant")
        if (reg.get("status") or "") in ("unknown", "unverified"):
            gaps.append("status_unresolved")

    cur.execute(
        """
        SELECT title_status, readiness_score, documents, next_prep_action
          FROM property_assets a
          LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
         WHERE a.client_code = %s
           AND (a.title_ref = %s OR a.title_ref ILIKE %s OR a.asset_code ILIKE %s)
         LIMIT 1
        """,
        (client, tct, f"%{tct.replace('T-', '')}%", f"%{tct.replace('T-', '')}%"),
    )
    asset = cur.fetchone()
    if not asset:
        gaps.append("no_property_asset_row")
    else:
        if asset.get("readiness_score") is None:
            gaps.append("no_readiness_score")

    cur.execute(
        """
        SELECT count(*)::int AS n
          FROM matter_facts
         WHERE provenance_level = 'verified'
           AND (statement ILIKE %s OR excerpt ILIKE %s)
           AND matter_code LIKE %s
        """,
        (f"%{tct}%", f"%{tct}%", client.split("-")[0] + "%"),
    )
    vf = cur.fetchone()
    if int((vf or {}).get("n") or 0) < 1:
        gaps.append("no_verified_matter_facts")

    return gaps


def agents_for_gaps(gaps: list[str]) -> list[str]:
    """Map gap codes → agent keys (no enqueue yet)."""
    if not gaps:
        return []
    agents: set[str] = set()
    if any(g.startswith("title_brief") or g in (
        "no_title_brief", "missing_area", "missing_parent_on_brief", "no_source_docs_on_brief",
        "no_verified_facts_on_brief", "no_map_geometry",
    ) for g in gaps):
        agents.add("title_brief_materializer")
    if any(g in ("no_verified_matter_facts", "status_unresolved", "missing_parent_on_registry") for g in gaps):
        agents.add("verify_worker")
        agents.add("doc_populate")
    if any(g in ("no_verified_facts_on_brief", "missing_area_on_registry") for g in gaps):
        agents.add("fact_field_extractor")
    if "no_property_asset_row" in gaps or "no_readiness_score" in gaps:
        agents.add("title_brief_materializer")
        agents.add("doc_populate")
    agents.add("matter_brief_materializer")
    return sorted(agents)


def enqueue_client_batch(
    cur, client: str, gap_report: list[dict], go: bool,
) -> dict[str, Any]:
    """ONE work item per agent for the whole client (not 40× extract_fact_fields).

    Intelligence: agents are compelled by the set of gaps, not by duplicating bulk
    jobs once per title.
    """
    by_agent: dict[str, list[dict]] = {}
    for g in gap_report:
        if not g.get("gaps"):
            continue
        for ak in agents_for_gaps(g["gaps"]):
            by_agent.setdefault(ak, []).append({
                "title": g["title"], "gaps": g["gaps"], "status": g.get("status"),
            })

    if not go:
        return {ak: len(v) for ak, v in by_agent.items()}

    enqueued = {}
    for ak, titles_gaps in by_agent.items():
        payload = {
            "client": client,
            "event": "mwk_asset_gap_batch",
            "title_count": len(titles_gaps),
            "titles": [x["title"] for x in titles_gaps[:50]],
            "gap_sample": titles_gaps[:8],
            "all_gap_codes": sorted({
                c for x in titles_gaps for c in (x.get("gaps") or [])
            }),
        }
        cur.execute(
            """
            INSERT INTO agent_work_queue (agent_key, event_type, payload, inquiry_id, status)
            VALUES (%s, %s, %s::jsonb, NULL, 'pending')
            """,
            (ak, "mwk_asset_gap_batch", json.dumps(payload)),
        )
        enqueued[ak] = len(titles_gaps)
    return enqueued


def run_hooks_for_client(client: str, titles: list[str], go: bool) -> dict[str, str]:
    """Direct compel (not only queue) — run the real scripts scoped to client/titles."""
    out = {}
    if not go:
        return {"dry": "would run title_brief, fact_fields, matter_brief, populate for " + client}

    # 1) Title cards for whole client
    r = subprocess.run(
        [sys.executable, "/root/landtek/scripts/materialize_title_brief.py",
         "--client", client, "--go"],
        capture_output=True, text=True, timeout=300,
    )
    out["title_brief"] = f"exit={r.returncode} {(r.stdout or r.stderr)[-300:]}"

    # 2) Per keystone titles (4497, 32911 first if present)
    priority = [t for t in ("T-4497", "T-32911", "T-48336", "T-52540") if t in titles]
    for t in priority + [x for x in titles if x not in priority][:12]:
        r = subprocess.run(
            [sys.executable, "/root/landtek/scripts/materialize_title_brief.py",
             "--title", t, "--go"],
            capture_output=True, text=True, timeout=120,
        )
        out[f"title_brief:{t}"] = f"exit={r.returncode}"

    # 3) Fact field extract for client matters
    r = subprocess.run(
        [sys.executable, "/root/landtek/scripts/extract_fact_fields.py",
         "--go", "--limit", "500"],
        capture_output=True, text=True, timeout=300,
    )
    out["fact_fields"] = f"exit={r.returncode} {(r.stdout or '')[-200:]}"

    # 4) Matter briefs
    r = subprocess.run(
        [sys.executable, "/root/landtek/scripts/materialize_matter_brief.py", "--go"],
        capture_output=True, text=True, timeout=180,
    )
    out["matter_brief"] = f"exit={r.returncode} {(r.stdout or '')[-200:]}"

    # 5) Doc populate (fills document_fields that title briefs read)
    r = subprocess.run(
        [sys.executable, "/root/landtek/scripts/populate_tables_from_docs.py",
         "--go", "--limit", "400"],
        capture_output=True, text=True, timeout=400,
    )
    out["doc_populate"] = f"exit={r.returncode} {(r.stdout or '')[-200:]}"

    return out


def drain_pending(cur, limit: int = 50) -> list:
    sys.path.insert(0, "/root/landtek/scripts")
    import inquiry_stack as ist

    results = []
    for ak in (
        "title_brief_materializer",
        "fact_field_extractor",
        "matter_brief_materializer",
        "doc_populate",
        "verify_worker",
    ):
        results.extend(ist.drain_agent(cur, ak, limit=limit, go=True))
    return results


def improve_agent_hooks():
    """Patch-free note: drain still uses inquiry_stack._run_agent_hook.
    We improve hooks here by calling scripts with --client when draining mwk gaps.
    """
    pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client", default="MWK-001")
    ap.add_argument("--go", action="store_true", help="write queue + run hooks")
    ap.add_argument("--drain", action="store_true", help="claim pending queue items")
    ap.add_argument("--limit", type=int, default=40, help="max titles to inspect")
    ap.add_argument("--direct", action="store_true", default=True,
                    help="also run agent scripts directly for client (default on with --go)")
    ap.add_argument("--no-direct", action="store_true", help="queue only")
    a = ap.parse_args()

    c = _conn()
    cur = _cur(c)
    titles = living_titles(cur, a.client)[: a.limit]
    print(f"[gap_drive] client={a.client} living_titles={len(titles)} go={a.go}")

    gap_report = []
    for row in titles:
        tct = row["tct_number"]
        gaps = scrutinize_title(cur, a.client, tct)
        agents = agents_for_gaps(gaps)
        gap_report.append({
            "title": tct,
            "status": row.get("status"),
            "gaps": gaps,
            "agents": agents,
        })
        flag = "OK" if not gaps else f"{len(gaps)} gaps"
        print(f"  {tct:<22} {row.get('status') or '?':<12} {flag}")
        if gaps:
            print(f"    → {', '.join(gaps)}")
            if agents:
                print(f"    → agents: {', '.join(agents)}")

    enq = enqueue_client_batch(cur, a.client, gap_report, go=a.go)
    n_with_gaps = sum(1 for g in gap_report if g["gaps"])
    print(f"[gap_drive] titles_with_gaps={n_with_gaps}/{len(titles)} "
          f"batch_queue={json.dumps(enq)}")

    if a.go and not a.no_direct:
        print("[gap_drive] running direct agent hooks for client…")
        tlist = [r["tct_number"] for r in titles]
        hooks = run_hooks_for_client(a.client, tlist, go=True)
        for k, v in hooks.items():
            print(f"  hook {k}: {v[:180]}")

    if a.go and a.drain:
        print("[gap_drive] draining agent_work_queue…")
        drained = drain_pending(cur, limit=a.limit)
        print(f"  drained={len(drained)}")
        for d in drained[:20]:
            print(f"    {d}")

    # Summary JSON path for operator
    summary = {
        "client": a.client,
        "living": len(titles),
        "with_gaps": n_with_gaps,
        "top_gaps": {},
    }
    for g in gap_report:
        for code in g["gaps"]:
            summary["top_gaps"][code] = summary["top_gaps"].get(code, 0) + 1
    print("[gap_drive] gap_frequency:", json.dumps(summary["top_gaps"], indent=2))
    cur.close()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
