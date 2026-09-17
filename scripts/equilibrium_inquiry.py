#!/usr/bin/env python3
"""equilibrium_inquiry.py — inquiry path: ROLE FIRST, then scoped lookup (no LLM).

  # List principals (first table)
  python3 scripts/equilibrium_inquiry.py --list-principals

  # Resolve a channel user, then answer from matter_brief / fact_fields
  python3 scripts/equilibrium_inquiry.py --channel-user 5992075757 --ask ctn
  python3 scripts/equilibrium_inquiry.py --principal-id 7 --matter MWK-OP-PETITION --ask headline
  python3 scripts/equilibrium_inquiry.py --role operator --client MWK-001 --matter MWK-OP-PETITION --ask ctn

Answers are short by construction from tables. Gate refuse/hold from role policy is respected.
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def list_principals(cur, limit=30):
    cur.execute(
        """
        SELECT principal_id, display_name, role, client_code, gate_default,
               dose_ceiling, authorized, bind_confidence
        FROM v_inquiry_principal
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    print(f"{'id':>4}  {'role':<12} {'gate':<8} {'dose':>4}  client       name")
    for r in rows:
        print(
            f"{r['principal_id']:>4}  {r['role'] or '?':<12} {r['gate_default'] or '?':<8} "
            f"{r['dose_ceiling'] if r['dose_ceiling'] is not None else '-':>4}  "
            f"{(r['client_code'] or '—'):<12} {(r['display_name'] or '')[:40]}"
        )
    print(f"[{len(rows)} principals — FIRST table = v_inquiry_principal]")


def resolve_principal(cur, principal_id=None, channel_user=None, role=None, client=None):
    if principal_id:
        cur.execute("SELECT * FROM v_inquiry_principal WHERE principal_id = %s", (principal_id,))
        return cur.fetchone()
    if channel_user:
        cur.execute(
            "SELECT * FROM v_inquiry_principal WHERE channel_user_id = %s ORDER BY principal_id DESC LIMIT 1",
            (str(channel_user),),
        )
        return cur.fetchone()
    # synthetic principal for CLI operator / tests
    if role or client:
        cur.execute("SELECT * FROM comms_role_policy WHERE role = %s", (role or "operator",))
        p = cur.fetchone() or {}
        return {
            "principal_id": None,
            "display_name": "cli",
            "role": role or "operator",
            "client_code": client,
            "gate_default": p.get("gate_default", "allow"),
            "dose_ceiling": p.get("dose_ceiling", 10),
            "disclosure_ceiling": p.get("disclosure_ceiling", "full"),
            "authorized": True,
            "bind_confidence": 1.0,
        }
    return None


def scoped_matters(cur, principal, matter_arg):
    """A5 wall: client_code from principal limits matters unless operator/internal/agent."""
    role = (principal.get("role") or "unknown").lower()
    client = principal.get("client_code")
    if matter_arg:
        # still enforce wall for non-internal roles
        if role in ("operator", "internal", "agent", "counsel") or not client:
            return [matter_arg]
        cur.execute(
            """
            SELECT matter_code FROM matters
            WHERE matter_code = %s
              AND (client_code = %s OR matter_code LIKE %s)
            """,
            (matter_arg, client, f"{client}%"),
        )
        # matters may use different client column — fallback allow if operator-ish
        row = cur.fetchone()
        if row:
            return [row["matter_code"]]
        # try document-linked client via matter only if matches prefix MWK for MWK-001
        if client and matter_arg.startswith(client.split("-")[0]):
            return [matter_arg]
        return []  # wall
    if role in ("operator", "internal", "agent"):
        cur.execute(
            """
            SELECT matter_code FROM matter_brief
            ORDER BY n_facts_verified DESC NULLS LAST LIMIT 20
            """
        )
        return [r["matter_code"] for r in cur.fetchall()]
    if not client:
        return []
    cur.execute(
        """
        SELECT matter_code FROM matter_brief
        WHERE matter_code LIKE %s OR matter_code LIKE %s
        ORDER BY n_facts_verified DESC NULLS LAST LIMIT 20
        """,
        (f"{client}%", f"{client.split('-')[0]}-%"),
    )
    return [r["matter_code"] for r in cur.fetchall()]


def answer(cur, principal, matters, ask: str) -> str:
    gate = (principal.get("gate_default") or "hold").lower()
    role = principal.get("role") or "unknown"
    if gate == "refuse":
        return f"[hold] role={role} is refuse — no auto answer (policy)."
    if gate == "hold" and role == "unknown":
        return f"[hold] identity/role unresolved — bind first (A5/A77)."
    if not matters:
        return f"[hold] no matters in scope for role={role} client={principal.get('client_code')}."

    ask = (ask or "headline").lower().strip()
    lines = []
    dose = int(principal.get("dose_ceiling") or 1)
    for mc in matters[: max(1, min(dose, 5))]:
        cur.execute("SELECT * FROM matter_brief WHERE matter_code = %s", (mc,))
        b = cur.fetchone()
        if not b:
            lines.append(f"{mc}: (no brief yet — run materialize_matter_brief)")
            continue
        if ask in ("headline", "status", "brief"):
            lines.append(b["headline"])
        elif ask in ("ctn", "ctns"):
            # cold answer: prefer verified fields only
            cur.execute(
                """
                SELECT DISTINCT value_norm FROM fact_fields
                WHERE matter_code = %s AND field_kind = 'ctn'
                  AND provenance_level = 'verified'
                ORDER BY 1
                """,
                (mc,),
            )
            v = [r["value_norm"] for r in cur.fetchall()]
            if not v:
                # show provisional but label
                cur.execute(
                    """
                    SELECT DISTINCT value_norm FROM fact_fields
                    WHERE matter_code = %s AND field_kind = 'ctn'
                    ORDER BY 1
                    """,
                    (mc,),
                )
                all_c = [r["value_norm"] for r in cur.fetchall()]
                if all_c:
                    lines.append(
                        f"{mc}: {len(all_c)} CTN(s) provisional — {', '.join(all_c)} "
                        f"(not all verified; {b['n_facts_verified']} verified facts on matter)"
                    )
                else:
                    lines.append(f"{mc}: 0 CTNs typed yet ({b['n_facts_verified']} verified facts)")
            else:
                lines.append(f"{mc}: {len(v)} CTNs: {', '.join(v)}")
        elif ask in ("tct", "tcts", "title"):
            t = b.get("tcts") or []
            lines.append(f"{mc}: {len(t)} TCT(s): {', '.join(t[:12])}" if t else f"{mc}: 0 TCTs typed")
        elif ask in ("oct", "octs"):
            rdy = b.get("readiness") or {}
            if isinstance(rdy, str):
                import json as _json
                try:
                    rdy = _json.loads(rdy)
                except Exception:
                    rdy = {}
            o = (rdy.get("octs") or rdy.get("numbers", {}).get("octs") or [])
            lines.append(f"{mc}: {len(o)} OCT(s): {', '.join(o[:12])}" if o else f"{mc}: 0 OCTs typed")
        elif ask in ("tax", "tax_dec", "arp", "td"):
            rdy = b.get("readiness") or {}
            if isinstance(rdy, str):
                import json as _json
                try:
                    rdy = _json.loads(rdy)
                except Exception:
                    rdy = {}
            td = (rdy.get("tax_decs") or rdy.get("numbers", {}).get("tax_decs") or [])
            lines.append(
                f"{mc}: {len(td)} tax dec(s): {', '.join(td[:12])}" if td else f"{mc}: 0 tax decs typed"
            )
        elif ask in ("numbers", "ids", "all_numbers"):
            # delicate pack: each kind labeled, never mixed
            cur.execute(
                """
                SELECT field_kind, array_agg(DISTINCT value_norm ORDER BY value_norm) vals
                FROM fact_fields
                WHERE matter_code = %s
                  AND field_kind IN ('ctn','tct','oct','e_title','tax_dec','docket','survey')
                  AND provenance_level = 'verified'
                GROUP BY 1 ORDER BY 1
                """,
                (mc,),
            )
            parts = []
            for row in cur.fetchall():
                vals = row["vals"] or []
                parts.append(f"{row['field_kind']}({len(vals)}): {', '.join(vals[:8])}")
            lines.append(f"{mc}: " + (" · ".join(parts) if parts else "no typed numbers (verified)"))
        elif ask in ("party", "parties"):
            p = b.get("parties") or []
            lines.append(f"{mc}: parties: {', '.join(p[:12])}" if p else f"{mc}: no parties in brief")
        elif ask in ("deadline", "next"):
            lines.append(f"{mc}: next deadline: {b.get('next_deadline') or '—'}")
        else:
            lines.append(b["headline"])
    # S14-ish: short by construction
    out = "\n".join(lines)
    if len(out) > 280 and (principal.get("projection_profile") == "human_safe"):
        out = out[:277] + "…"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-principals", action="store_true")
    ap.add_argument("--principal-id", type=int, default=None)
    ap.add_argument("--channel-user", default=None)
    ap.add_argument("--role", default=None, help="synthetic CLI principal role")
    ap.add_argument("--client", default=None)
    ap.add_argument("--matter", default=None)
    ap.add_argument("--ask", default="headline", help="headline|ctn|tct|oct|tax|numbers|parties|deadline|title")
    ap.add_argument("--title", default=None, help="title_key for property card lookup (e.g. T-4497)")
    a = ap.parse_args()

    c = _conn()
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if a.list_principals:
        list_principals(cur)
        return

    principal = resolve_principal(cur, a.principal_id, a.channel_user, a.role, a.client)
    if not principal:
        print("No principal resolved. Use --list-principals or --role operator --client MWK-001")
        sys.exit(2)

    print(
        f"[principal] role={principal.get('role')} gate={principal.get('gate_default')} "
        f"dose={principal.get('dose_ceiling')} client={principal.get('client_code')} "
        f"name={principal.get('display_name')}"
    )
    # Property / title card path (UI later reads title_brief the same way)
    if a.title or (a.ask or "").lower() in ("title", "property", "titles"):
        gate = (principal.get("gate_default") or "hold").lower()
        if gate == "refuse":
            print("---")
            print(f"[hold] role={principal.get('role')} refuse — no title card.")
            return
        if a.title:
            cur.execute(
                """
                SELECT headline, card, title_kind, n_source_docs, has_map_geometry,
                       tax_decs, related_matters, registrant_name, area_sqm
                FROM title_brief
                WHERE title_key = upper(regexp_replace(%s, '\\s+', '', 'g'))
                   OR display_no = %s
                LIMIT 1
                """,
                (a.title, a.title),
            )
            tb = cur.fetchone()
            print("---")
            if not tb:
                print(f"(no title_brief yet for {a.title} — run materialize_title_brief.py --go)")
            else:
                print(tb["headline"])
                print(
                    f"  kind={tb['title_kind']} docs={tb['n_source_docs']} "
                    f"map={tb['has_map_geometry']} tax={tb['tax_decs']} "
                    f"matters={tb['related_matters']}"
                )
        else:
            cur.execute(
                """
                SELECT title_key, headline, has_map_geometry, n_source_docs
                FROM title_brief
                WHERE (%s::text IS NULL OR client_code = %s OR case_file = %s)
                ORDER BY n_source_docs DESC NULLS LAST
                LIMIT 15
                """,
                (principal.get("client_code"), principal.get("client_code"), principal.get("client_code")),
            )
            print("--- titles (brief) ---")
            for r in cur.fetchall():
                print(f"  {r['title_key']:<22} docs={r['n_source_docs']:<3} map={r['has_map_geometry']}  {r['headline'][:70]}")
        cur.close()
        c.close()
        return

    matters = scoped_matters(cur, principal, a.matter)
    print(f"[scope] matters={matters[:10]}")
    print("---")
    print(answer(cur, principal, matters, a.ask))
    cur.close()
    c.close()


if __name__ == "__main__":
    main()
