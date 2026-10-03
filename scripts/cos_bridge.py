#!/usr/bin/env python3
"""cos_bridge.py — CoS↔VPS awareness bridge into agent_registry + equilibrium spine.

Owns Layer A (Grok Bot seats from config/cos_fleet_roster.json) and Layer B (Claude subagents
from .claude/agents/*.md). Upserts into the EXISTING agent_registry table — no second roster.
Runtime layers (systemd / cron / catalog) stay owned by fleet_registry.py (Principle 10).

Equilibrium plug-in (A76 — every action should affect the stack): after a roster change,
`--pulse` records a shadow fleet_change into propagation_log (deploy_881) and a coverage note
into equilibrium_coverage_log (deploy_934). That is the same ledger equilibrium_propagate.py
writes; we do NOT fork a parallel brain. Full ego-network propagate needs a client-scoped seed
(fact/matter/chat) — fleet events are company-level, so we ledger the perturbation in SHADOW
and leave recipient projection to the emission plane. CoS actions that assign a bot, pause a
desk, or approve outward MUST also enqueue work_orders (and cue related subjects) — chat-only
memory is not a stack effect. See docs/RELATIONSHIP_EQUILIBRIUM.md + ops/COS_FLEET_AWARENESS.md.

VPS cadence (after fleet_registry --sync):
  python3 scripts/fleet_registry.py --sync
  python3 scripts/cos_bridge.py --sync --pulse

Mac-safe (no systemd required):
  python3 scripts/cos_bridge.py --snapshot          # always
  python3 scripts/cos_bridge.py --sync --pulse       # when PG_DSN reaches VPS Postgres
  python3 scripts/cos_bridge.py --report

Library hook:
  from cos_bridge import on_fleet_change
  on_fleet_change(cur, agent_key="grok:1378", event="assigned", detail={...})
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # allow --snapshot/--report from files without psycopg2
    psycopg2 = None
    psycopg2.extras = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ROSTER_PATH = ROOT / "config" / "cos_fleet_roster.json"
CLAUDE_AGENTS = ROOT / ".claude" / "agents"
SNAPSHOT_PATH = ROOT / "ops" / "COS_FLEET_AWARENESS.md"

# owner from agent name/title first (desc text often cross-mentions sibling agents)
CLAUDE_OWNER_BY_KEY = {
    "case-26360-strategist": "legal-strategy",
    "mapping-agent": "mapping",
    "ombudsman-hunter": "offense",
    "product-hardener": "product",
    "revenue-engineer": "revenue",
    "ship-packager": "product",
    "truth-qa-gate": "governance",
}
CLAUDE_OWNER_RULES = [  # fallback if a new .md appears
    (r"ombudsman", "offense"),
    (r"map(?:ping)?-?agent|parcel|geometry", "mapping"),
    (r"truth|qa-gate", "governance"),
    (r"strateg|26-?360|case-\d", "legal-strategy"),
    (r"revenue", "revenue"),
    (r"ship|packag|harden|product", "product"),
]


def _conn():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 required for DB modes")
    c = psycopg2.connect(DSN, connect_timeout=5)
    c.autocommit = True
    return c


def _now():
    return datetime.now(timezone.utc)


def _apply_owner(name: str, hay: str = "") -> str:
    if name in CLAUDE_OWNER_BY_KEY:
        return CLAUDE_OWNER_BY_KEY[name]
    h = f"{name} {hay}".lower()
    for pat, owner in CLAUDE_OWNER_RULES:
        if re.search(pat, h):
            return owner
    return "unassigned"


def load_roster():
    if not ROSTER_PATH.exists():
        print(f"[warn] missing {ROSTER_PATH}")
        return {"seats": [], "layer_notes": {}}
    return json.loads(ROSTER_PATH.read_text())


def scan_claude_agents():
    """Layer B: .claude/agents/*.md → rows (skip README)."""
    rows = []
    if not CLAUDE_AGENTS.is_dir():
        return rows
    for path in sorted(CLAUDE_AGENTS.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = {}
        body = text
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()
            body = m.group(2)
        name = fm.get("name") or path.stem
        desc = fm.get("description") or ""
        first = re.split(r"(?<=[.!?])\s+", desc)[0] if desc else ""
        if len(first) > 160:
            first = first[:157] + "..."
        bm = re.search(r"You are(?: the)? \*\*([^*]+)\*\*", body)
        title = (bm.group(1).strip() if bm else name.replace("-", " ").title())
        role = first or title
        rows.append({
            "agent_key": f"claude:{name}",
            "display_name": title,
            "role": role,
            "owner": _apply_owner(name, f"{desc} {title}"),
            "tier": "T0",
            "layer": "claude_subagent",
            "state": "live",
            "fuel": "human",
            "heartbeat_source": f"file:.claude/agents/{path.name}",
            "note": f"Claude subagent · source=.claude/agents/{path.name}",
        })
    return rows


def layer_a_rows(roster):
    rows = []
    for s in roster.get("seats") or []:
        ext = s.get("external_id")
        note = s.get("note") or ""
        if ext and ext not in note:
            note = (note + "; " if note else "") + f"Grok Bot UUID {ext}"
        rows.append({
            "agent_key": s["agent_key"],
            "display_name": s.get("display_name") or s["agent_key"],
            "role": s.get("role"),
            "owner": s.get("owner") or "unassigned",
            "tier": s.get("tier") or "T0",
            "layer": s.get("layer") or "grok_bot",
            "state": s.get("state") or "live",
            "fuel": s.get("fuel") or "human",
            "heartbeat_source": s.get("heartbeat_source") or "grok_bot:chat",
            "note": note,
            "external_id": ext,
        })
    return rows


def upsert_rows(cur, rows):
    """Upsert into agent_registry. Preserve GRANTED tiers (same A61 rule as fleet_registry)."""
    now = _now()
    n = 0
    for r in rows:
        cur.execute(
            """INSERT INTO agent_registry
                 (agent_key, display_name, role, tier, tier_status, fuel, owner, heartbeat_source,
                  systemd_unit, cadence, layer, supervised, state, note, seen_at, updated_at)
               VALUES (%s,%s,%s,%s,'provisional',%s,%s,%s,NULL,NULL,%s,false,%s,%s,%s,now())
               ON CONFLICT (agent_key) DO UPDATE SET
                 display_name=EXCLUDED.display_name,
                 role=EXCLUDED.role, fuel=EXCLUDED.fuel, owner=EXCLUDED.owner,
                 heartbeat_source=EXCLUDED.heartbeat_source,
                 layer=EXCLUDED.layer, state=EXCLUDED.state,
                 note=EXCLUDED.note, seen_at=EXCLUDED.seen_at, updated_at=now(),
                 tier = CASE WHEN agent_registry.tier_status='granted'
                             THEN agent_registry.tier ELSE EXCLUDED.tier END""",
            (r["agent_key"], r["display_name"], r.get("role"), r.get("tier") or "T0",
             r.get("fuel"), r.get("owner") or "unassigned",
             r.get("heartbeat_source") or "none",
             r.get("layer"), r.get("state") or "live", r.get("note"), now),
        )
        n += 1
    return n


def on_fleet_change(cur, agent_key: str, event: str, detail: dict | None = None,
                    mode: str = "shadow"):
    """Thin hook: ledger a fleet_change into the EXISTING A76 spine (propagation_log).

    Callable from cos_bridge --pulse or from future CoS tick code. Does not emit outward.
    seed_type='fleet' is company-scoped (client_code NULL); full ego propagate stays for
    fact/matter/chat seeds that resolve a client (A5).
    """
    detail = dict(detail or {})
    detail.setdefault("event", event)
    detail.setdefault("agent_key", agent_key)
    detail.setdefault("source", "cos_bridge")
    detail.setdefault("emits", False)
    detail.setdefault("stack_effect",
                      "ledger only — enqueue work_orders + cue subjects for real CoS actions")
    ref = f"cos_bridge:{event}:{agent_key}"
    cur.execute(
        """INSERT INTO propagation_log
             (interaction_ref, seed_type, seed_id, client_code, ego_hops, ego_nodes,
              contradictions_found, cascades_touched, cross_client_refused, mode, detail)
           VALUES (%s,'fleet',%s,NULL,0,0,0,0,0,%s,%s) RETURNING id""",
        (ref, str(agent_key), mode,
         psycopg2.extras.Json(detail) if psycopg2 else json.dumps(detail)),
    )
    row = cur.fetchone()
    log_id = row["id"] if isinstance(row, dict) else row[0]
    return {"log_id": log_id, "mode": mode, "seed_type": "fleet", "seed_id": agent_key,
            "event": event, "emitted": False}


def pulse_fleet(cur, rows, sync_ok: bool):
    """Record one batch fleet_change after sync (or file-only inventory) into equilibrium tables."""
    by_layer: dict[str, int] = {}
    keys = []
    for r in rows:
        by_layer[r["layer"]] = by_layer.get(r["layer"], 0) + 1
        keys.append(r["agent_key"])
    detail = {
        "event": "fleet_sync",
        "sync_ok": sync_ok,
        "counts_by_layer": by_layer,
        "agent_keys": keys,
        "n_agents": len(keys),
        "roster_path": str(ROSTER_PATH.relative_to(ROOT)),
        "hook": "on_fleet_change",
        "note": ("CoS/agent-registry change ledged for A76. Real actions (assign bot, pause "
                 "Discovery, approve outward) must also enqueue work_orders and cue related "
                 "subjects — not chat-only memory."),
    }
    result = on_fleet_change(cur, agent_key="fleet:cos_bridge", event="fleet_sync",
                             detail=detail, mode="shadow")
    # coverage meter ping — reuse equilibrium_coverage_log.notes (deploy_934)
    notes = (f"cos_bridge fleet_pulse: n={len(keys)} layers={by_layer} "
             f"propagation_log_id={result['log_id']} sync_ok={sync_ok}")
    try:
        cur.execute(
            """INSERT INTO equilibrium_coverage_log
                 (n_facts, n_facts_verified, n_facts_with_fields, typed_coverage_pct,
                  n_briefs, n_briefs_stale, notes)
               VALUES (NULL,NULL,NULL,NULL,NULL,NULL,%s) RETURNING id""",
            (notes,),
        )
        cov = cur.fetchone()
        result["coverage_log_id"] = cov["id"] if isinstance(cov, dict) else cov[0]
    except Exception as e:
        result["coverage_log_error"] = str(e)
    return result


def sync():
    roster = load_roster()
    rows = layer_a_rows(roster) + scan_claude_agents()
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    n = upsert_rows(cur, rows)
    cur.execute(
        "SELECT layer, count(*) n FROM agent_registry "
        "WHERE layer IN ('grok_bot','claude_subagent') GROUP BY layer ORDER BY layer"
    )
    print(f"cos_bridge synced {n} seats into agent_registry:")
    for r in cur.fetchall():
        print(f"  {r['layer']:16s} {r['n']}")
    cur.close()
    conn.close()
    return rows


def db_layer_counts():
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT layer, count(*) n FROM agent_registry GROUP BY layer ORDER BY layer")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def report(file_rows=None):
    file_rows = file_rows or (layer_a_rows(load_roster()) + scan_claude_agents())
    print("=== file inventory (A+B) ===")
    by = {}
    for r in file_rows:
        by[r["layer"]] = by.get(r["layer"], 0) + 1
    for layer, n in sorted(by.items()):
        print(f"  {layer:16s} {n}")
    print(f"  {'TOTAL':16s} {len(file_rows)}")
    try:
        db = db_layer_counts()
        print("=== agent_registry (DB) ===")
        for r in db:
            print(f"  {r['layer']:16s} {r['n']}")
    except Exception as e:
        print(f"=== agent_registry (DB) UNAVAILABLE: {e} ===")
        print("  VPS layers (systemd/cron/catalog) need: python3 scripts/fleet_registry.py --sync")
        print("  Then: python3 scripts/cos_bridge.py --sync --pulse")


def snapshot(file_rows=None, db_ok=None, db_rows=None, pulse_result=None):
    file_rows = file_rows or (layer_a_rows(load_roster()) + scan_claude_agents())
    roster = load_roster()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        from zoneinfo import ZoneInfo
        now = _now().astimezone(ZoneInfo("Asia/Manila")).strftime("%Y-%m-%d %H:%M PhST")
    except Exception:
        now = _now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    if db_ok is None:
        try:
            db_rows = db_layer_counts()
            db_ok = True
        except Exception as e:
            db_rows = []
            db_ok = False
            db_err = str(e)
    else:
        db_err = None if db_ok else "unreachable"

    lines = []
    lines.append("# CoS Fleet Awareness")
    lines.append("")
    lines.append(f"*Generated {now} by `scripts/cos_bridge.py --snapshot`.*")
    lines.append("")
    lines.append("Enumeration spine: **`agent_registry`** (deploy_810). "
                 "Cos owns `grok_bot` + `claude_subagent`; "
                 "`fleet_registry` owns systemd/cron/catalog. "
                 "Equilibrium: `--pulse` → `propagation_log` (seed_type=`fleet`, shadow) "
                 "+ `equilibrium_coverage_log` — see `docs/RELATIONSHIP_EQUILIBRIUM.md`.")
    lines.append("")
    lines.append("## Stack effect rule (Jonathan / CoS)")
    lines.append("")
    lines.append("Every CoS action must affect the stack, not chat memory alone:")
    lines.append("- **assign / pause / re-own a desk** → upsert agent_registry via cos_bridge "
                 "**and** enqueue a `work_orders` row (assignee = agent_key) + `--pulse`.")
    lines.append("- **approve outward** → existing outward gates (A21/A26/S14); still ledger "
                 "via pulse / propagation so related subjects get cued.")
    lines.append("- **Discovery / research desks** → cue related matters through work_orders; "
                 "do not rely on seat chat history as system of record.")
    lines.append("")

    # Layer A
    lines.append("## Layer A — grok_bot (Grok Bot seats)")
    lines.append("")
    a = [r for r in file_rows if r["layer"] == "grok_bot"]
    lines.append(f"| agent_key | display_name | owner | tier | note |")
    lines.append(f"|---|---|---|---|---|")
    for r in a:
        note = (r.get("note") or "").replace("|", "/")
        lines.append(f"| `{r['agent_key']}` | {r['display_name']} | {r['owner']} | "
                     f"{r['tier']} | {note[:80]} |")
    lines.append("")

    # Layer B
    lines.append("## Layer B — claude_subagent")
    lines.append("")
    b = [r for r in file_rows if r["layer"] == "claude_subagent"]
    lines.append(f"| agent_key | display_name | owner | role |")
    lines.append(f"|---|---|---|---|")
    for r in b:
        role = (r.get("role") or "").replace("|", "/")[:100]
        lines.append(f"| `{r['agent_key']}` | {r['display_name']} | {r['owner']} | {role} |")
    lines.append("")

    # VPS / DB layers
    lines.append("## Runtime layers — systemd / cron / catalog (fleet_registry)")
    lines.append("")
    if db_ok and db_rows:
        lines.append("| layer | count |")
        lines.append("|---|---|")
        for r in db_rows:
            lines.append(f"| `{r['layer']}` | {r['n']} |")
    else:
        lines.append(f"**DB unreachable from this host** ({db_err or 'n/a'}). "
                     "File inventory for A+B is above. "
                     "On VPS run `python3 scripts/fleet_registry.py --sync` then "
                     "`python3 scripts/cos_bridge.py --sync --pulse` to populate runtime "
                     "layers and ledger the fleet_change into the equilibrium spine.")
    lines.append("")

    if pulse_result:
        lines.append("## Last pulse (this run)")
        lines.append("")
        lines.append(f"- propagation_log id: `{pulse_result.get('log_id')}` "
                     f"(seed_type=fleet, mode={pulse_result.get('mode')})")
        if pulse_result.get("coverage_log_id"):
            lines.append(f"- equilibrium_coverage_log id: `{pulse_result['coverage_log_id']}`")
        lines.append("")

    lines.append("## Layer notes")
    lines.append("")
    for k, v in (roster.get("layer_notes") or {}).items():
        lines.append(f"- **{k}**: {v}")
    lines.append("")
    lines.append("## Commands")
    lines.append("")
    lines.append("```bash")
    lines.append("# Mac (awareness + file snapshot)")
    lines.append("python3 scripts/cos_bridge.py --snapshot")
    lines.append("python3 scripts/cos_bridge.py --report")
    lines.append("# VPS (DB + equilibrium ledger)")
    lines.append("docker exec -i n8n-postgres-1 psql -U n8n -d n8n "
                 "< migrations/deploy_980_cos_awareness_bridge.sql")
    lines.append("python3 scripts/fleet_registry.py --sync")
    lines.append("python3 scripts/cos_bridge.py --sync --pulse")
    lines.append("```")
    lines.append("")

    SNAPSHOT_PATH.write_text("\n".join(lines) + "\n")
    print(f"wrote {SNAPSHOT_PATH}")
    return SNAPSHOT_PATH


def main():
    ap = argparse.ArgumentParser(description="CoS↔VPS awareness bridge (agent_registry + A76 pulse)")
    ap.add_argument("--sync", action="store_true",
                    help="upsert Layer A (JSON) + Layer B (.claude/agents) into agent_registry")
    ap.add_argument("--snapshot", action="store_true",
                    help="write ops/COS_FLEET_AWARENESS.md")
    ap.add_argument("--report", action="store_true", help="print counts by layer")
    ap.add_argument("--pulse", action="store_true",
                    help="ledger fleet_change into propagation_log + equilibrium_coverage_log (shadow)")
    args = ap.parse_args()
    if not (args.sync or args.snapshot or args.report or args.pulse):
        ap.print_help()
        sys.exit(2)

    file_rows = layer_a_rows(load_roster()) + scan_claude_agents()
    synced_rows = None
    pulse_result = None
    db_ok = None
    db_rows = None

    if args.sync:
        try:
            synced_rows = sync()
            db_ok = True
        except Exception as e:
            print(f"[error] --sync failed: {e}")
            print("  Snapshot/report can still run from files. Apply deploy_980 on VPS if layer CHECK rejects.")
            db_ok = False

    if args.pulse:
        rows_for_pulse = synced_rows or file_rows
        try:
            conn = _conn()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            pulse_result = pulse_fleet(cur, rows_for_pulse, sync_ok=bool(args.sync and db_ok))
            print(f"pulse: propagation_log id={pulse_result.get('log_id')} "
                  f"coverage_log_id={pulse_result.get('coverage_log_id')} "
                  f"mode={pulse_result.get('mode')} (shadow — no outward emit)")
            cur.close()
            conn.close()
        except Exception as e:
            print(f"[error] --pulse failed (DB unreachable or missing tables): {e}")
            print("  On VPS ensure deploy_881 + deploy_934 applied, then re-run --pulse.")

    if args.report:
        report(file_rows=synced_rows or file_rows)

    if args.snapshot:
        snapshot(file_rows=synced_rows or file_rows, db_ok=db_ok, db_rows=db_rows,
                 pulse_result=pulse_result)


if __name__ == "__main__":
    main()
