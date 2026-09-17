#!/usr/bin/env python3
"""reconcile_title_ontology.py — attach fragmented title data onto the titles SoR + briefs.

Problem: parents live in title_chain, registrants in chain_of_title, areas on
titles/assets/parcels, facts in matter_facts — inventory/chat only saw thin columns.

This script PROMOTES existing stack evidence into canonical ontology fields
(without inventing):

  title_chain        → titles.parent_title  (and notes provenance)
  chain_of_title     → titles.parent_title + registrant_name_raw
  property_assets    → titles.area_sqm (if titles blank)
  parcels / assets   → area_sqm
  then materialize_title_brief so cards reflect the join

  python3 scripts/reconcile_title_ontology.py --client MWK-001
  python3 scripts/reconcile_title_ontology.py --client MWK-001 --go
  python3 scripts/reconcile_title_ontology.py --client MWK-001 --go --briefs

Does NOT invent status or cancel titles. Does NOT overwrite operator-fixed
out_of_scope / invalid. Prefer verified chain edges.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

_PROTECTED_STATUS = ("invalid", "alias", "out_of_scope")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").upper())


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


def _rank_prov(p: str) -> int:
    p = (p or "").lower()
    if p == "verified":
        return 0
    if p == "operator":
        return 1
    if p == "inferred_strong":
        return 2
    return 9


def load_chain_parents(cur) -> dict[str, tuple[str, str, int | None]]:
    """child_norm → (parent_display, provenance, source_doc_id) best edge."""
    cur.execute(
        """
        SELECT parent_title, child_title, provenance_level, source_doc_id
          FROM title_chain
         WHERE coalesce(parent_title,'') <> ''
           AND coalesce(child_title,'') <> ''
        """
    )
    best: dict[str, tuple] = {}
    for r in _as_dicts(cur):
        child = _norm(r["child_title"])
        parent = (r["parent_title"] or "").strip()
        if not child or not parent:
            continue
        # Prefer well-formed parents
        score = _rank_prov(r.get("provenance_level"))
        prev = best.get(child)
        if prev is None or score < prev[3]:
            best[child] = (parent, r.get("provenance_level") or "", r.get("source_doc_id"), score)
    # also chain_of_title.predecessor_title
    try:
        cur.execute(
            """
            SELECT tct_number, predecessor_title, provenance_level, registrant_full_name
              FROM chain_of_title
             WHERE coalesce(predecessor_title,'') <> ''
            """
        )
        for r in _as_dicts(cur):
            child = _norm(r["tct_number"])
            parent = (r["predecessor_title"] or "").strip()
            if not child or not parent:
                continue
            score = _rank_prov(r.get("provenance_level"))
            prev = best.get(child)
            if prev is None or score < prev[3]:
                best[child] = (parent, r.get("provenance_level") or "", None, score)
    except Exception as e:
        print(f"[reconcile] chain_of_title parents skip: {e}")
    return {k: (v[0], v[1], v[2]) for k, v in best.items()}


def load_chain_registrants(cur) -> dict[str, str]:
    """title_norm → best registrant name from chain_of_title."""
    out: dict[str, str] = {}
    try:
        cur.execute(
            """
            SELECT tct_number, registrant_full_name, provenance_level
              FROM chain_of_title
             WHERE coalesce(registrant_full_name,'') <> ''
            """
        )
        ranked: dict[str, tuple] = {}
        for r in _as_dicts(cur):
            k = _norm(r["tct_number"])
            name = re.sub(r"\s+", " ", (r["registrant_full_name"] or "").strip())
            if not k or len(name) < 3:
                continue
            # skip template OCR junk
            if "state the citizenship" in name.lower() or name.lower().startswith("the conjugal"):
                continue
            score = _rank_prov(r.get("provenance_level"))
            prev = ranked.get(k)
            if prev is None or score < prev[1]:
                ranked[k] = (name, score)
        out = {k: v[0] for k, v in ranked.items()}
    except Exception as e:
        print(f"[reconcile] registrants skip: {e}")
    return out


def load_areas_from_assets(cur, client: str) -> dict[str, float]:
    out = {}
    try:
        cur.execute(
            """
            SELECT title_ref, area_sqm FROM property_assets
             WHERE (client_code = %s OR case_file = %s)
               AND area_sqm IS NOT NULL AND area_sqm > 0
            """,
            (client, client),
        )
        for r in _as_dicts(cur):
            k = _norm(r["title_ref"])
            if k:
                out[k] = float(r["area_sqm"])
    except Exception as e:
        print(f"[reconcile] asset areas skip: {e}")
    return out


def reconcile_client(cur, conn, client: str, go: bool) -> dict:
    parents = load_chain_parents(cur)
    registrants = load_chain_registrants(cur)
    areas = load_areas_from_assets(cur, client)

    cur.execute(
        """
        SELECT tct_number, case_file, parent_title, area_sqm,
               registrant_name_raw, status, notes, verification_lock
          FROM titles
         WHERE case_file = %s OR case_file LIKE %s
        """,
        (client, client + "%"),
    )
    rows = _as_dicts(cur)

    stats = {
        "titles_seen": len(rows),
        "parent_filled": 0,
        "registrant_filled": 0,
        "area_filled": 0,
        "skipped_protected": 0,
        "locked_override": 0,
        "would": [],
    }

    pending_sql = []  # list of (sql, args)

    for r in rows:
        tct = r["tct_number"]
        st = (r.get("status") or "").lower()
        if st in _PROTECTED_STATUS:
            stats["skipped_protected"] += 1
            continue
        key = _norm(tct)
        updates = []
        args = []
        note_bits = []

        # parent
        if not (r.get("parent_title") or "").strip() and key in parents:
            p, prov, sdoc = parents[key]
            updates.append("parent_title = %s")
            args.append(p)
            note_bits.append(f"parent←chain({prov or '?'}" + (f",doc{sdoc}" if sdoc else "") + ")")
            stats["parent_filled"] += 1

        # registrant
        reg = (r.get("registrant_name_raw") or "").strip()
        junk = (not reg) or ("state the citizenship" in reg.lower()) or (
            reg.lower().startswith("the conjugal")
        )
        if junk and key in registrants:
            name = registrants[key][:200]
            # Three heirs of Mary Worrick Keesey are one party — prefer collective form
            low = name.lower()
            if re.search(
                r"geraldine|hoppe|patricia|zschoche|marcia|keesey|et al",
                low,
            ) and "heirs of mary" not in low:
                # Operator preference: HEIRS OF MARY WORRICK KEESEY (not Hoppe et al.)
                name = "HEIRS OF MARY WORRICK KEESEY"
            updates.append("registrant_name_raw = %s")
            args.append(name)
            updates.append("registrant_canonical = %s")
            args.append(name)
            note_bits.append("registrant←chain_of_title")
            stats["registrant_filled"] += 1

        # area
        if r.get("area_sqm") is None and key in areas:
            updates.append("area_sqm = %s")
            args.append(areas[key])
            note_bits.append("area←property_assets")
            stats["area_filled"] += 1

        if not updates:
            continue

        updates.append("notes = coalesce(notes,'') || %s")
        args.append(" | reconcile_title_ontology: " + "; ".join(note_bits))
        args.extend([tct, r["case_file"]])

        stats["would"].append({"tct": tct, "sets": note_bits, "locked": bool(r.get("verification_lock"))})
        if r.get("verification_lock"):
            stats["locked_override"] += 1

        pending_sql.append(
            (
                f"""
                UPDATE titles
                   SET {", ".join(updates)}
                 WHERE tct_number = %s AND case_file = %s
                """,
                args,
            )
        )

    if go and pending_sql:
        # hard-locked mother titles (e.g. T-4497) need same-transaction override
        conn.autocommit = False
        try:
            cur2 = conn.cursor()
            cur2.execute("BEGIN")
            cur2.execute("SET LOCAL app.truth_override = on")
            cur2.execute("SET LOCAL app.truth_override_actor = 'jonathan'")
            cur2.execute(
                "SET LOCAL app.truth_override_reason = %s",
                ("reconcile_title_ontology: promote title_chain/chain_of_title onto titles SoR",),
            )
            for sql, args in pending_sql:
                cur2.execute(sql, args)
            conn.commit()
            cur2.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--client", default="MWK-001")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--briefs", action="store_true", help="rematerialize title_brief after")
    a = ap.parse_args()

    c = _conn()
    cur = _cur(c)
    print(f"[reconcile] client={a.client} go={a.go}")
    stats = reconcile_client(cur, c, a.client, go=a.go)
    print(
        f"[reconcile] titles={stats['titles_seen']} "
        f"parent_filled={stats['parent_filled']} "
        f"registrant_filled={stats['registrant_filled']} "
        f"area_filled={stats['area_filled']} "
        f"skipped_protected={stats['skipped_protected']}"
    )
    for w in stats["would"][:25]:
        print(f"  {w['tct']}: {', '.join(w['sets'])}")
    if len(stats["would"]) > 25:
        print(f"  … +{len(stats['would'])-25} more")

    if a.go:
        # post-check
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE parent_title IS NOT NULL AND parent_title<>'') AS with_parent,
                   count(*) FILTER (WHERE area_sqm IS NOT NULL) AS with_area,
                   count(*) FILTER (WHERE coalesce(registrant_name_raw,'')<>''
                     AND registrant_name_raw NOT ILIKE '%%citizenship%%') AS with_reg,
                   count(*) AS total
              FROM titles WHERE case_file = %s
            """,
            (a.client,),
        )
        r = cur.fetchone()
        print(
            f"[reconcile] AFTER {a.client}: "
            f"parent={r['with_parent']}/{r['total']} "
            f"area={r['with_area']}/{r['total']} "
            f"registrant={r['with_reg']}/{r['total']}"
        )

    if a.go and a.briefs:
        print("[reconcile] materialize_title_brief --client …")
        subprocess.run(
            [sys.executable, "/root/landtek/scripts/materialize_title_brief.py",
             "--client", a.client, "--go"],
            check=False,
        )
        # keystone titles explicit
        for t in ("T-4497", "T-32911", "T-48336", "T-52540", "T-32916", "T-32917"):
            subprocess.run(
                [sys.executable, "/root/landtek/scripts/materialize_title_brief.py",
                 "--title", t, "--go"],
                check=False, capture_output=True,
            )
        print("[reconcile] briefs refreshed")

    cur.close()
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
