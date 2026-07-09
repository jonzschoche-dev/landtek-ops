#!/usr/bin/env python3
"""fleet_registry.py — reconcile the whole fleet into ONE enumerable roster (agent_registry).

The fleet is enumerated in three divergent places: agents.py (catalog), systemd timers (runtime), and
cron (runtime, incl. refresh_all's children). agents.py names only 7 of 37 live timers. This generator
takes RUNTIME as ground truth (systemd + cron), overlays agents.py metadata, assigns each agent a
governance tier (A61) + owner domain + heartbeat source, and upserts agent_registry. Anything running
but uncatalogued is surfaced (state/note), never hidden.

  python3 scripts/fleet_registry.py --sync     # reconcile ground truth -> agent_registry (run on VPS)
  python3 scripts/fleet_registry.py --health    # is each registered agent's heartbeat fresh?
  python3 scripts/fleet_registry.py --report     # the roster, grouped by tier x owner
"""
from __future__ import annotations
import os
import re
import sys
import subprocess
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
HERE = os.path.dirname(os.path.abspath(__file__))


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _norm(name: str) -> str:
    """Canonical agent_key: strip landtek- / .timer / .py, dashes -> underscores."""
    n = re.sub(r"^landtek-", "", name)
    n = re.sub(r"\.(timer|service|py|sh)$", "", n)
    return n.replace("-", "_")


# ── tier rules (A61), derived from SUPERVISION_DIRECTIVE §1/§7. Ordered; first match wins. ──
# T3 outward/irreversible · T2 writes-knowledge/proposes · T1 reversible-internal/report · else unset.
TIER_RULES = [
    (r"bridge|channel|outbound|email_bridge|viber|whatsapp|_send|filing_monitor", "T3"),  # egress/outward
    (r"reconcil|proposer|promote|verify_worker|analyst|entity_.*link|refresh_.*fact|"
     r"strateg|synthes|brief_draft|constitution|matter_", "T2"),                          # writes canon/proposes
    (r"sentinel|monitor|health|audit|verify|reocr|ocr|embed|backup|sync|digest|briefer|"
     r"steward|deadline|geometry|parcel|truth|ontology|cross_client|coordinator|"
     r"correspond|doc_triage|jurisprud|supervisor|inference", "T1"),                       # reversible/report
]

# ── owner rules — the 10 directive domains. Ordered; first match wins. ──
OWNER_RULES = [
    (r"verify|reocr|ocr|fact|entity|contradiction|backfill|embed|extract", "evidence"),
    (r"analyst|synthes|brief|cross_matter|strateg|plays|keystone", "legal-strategy"),
    (r"forum|filing|deadline|execution|arta|case_thread|court", "forums"),
    (r"ombudsman", "offense"),
    (r"email|telegram|channel|leo|digest|correspond|assistant|calendar|viber|whatsapp|briefer|comms", "comms"),
    (r"client|matter|onboard|readiness|dependab", "client-mgmt"),
    (r"revenue|invoice|cost|valuation|retainer|portfolio", "revenue"),
    (r"parcel|geometry|map|survey", "mapping"),
    (r"ship|product|package|bundle|render|proof|finalize|pdf", "product"),
    (r"supervisor|ontology|truth|cross_client|sentinel|holes|coverage|connection|"
     r"dossier_verify|inference|constitution|backup|disk|cron_health", "governance"),
]

# Phase-2 supervised scope (A59): deadline-bound or governed-data-mutating work routes through work_orders.
SUPERVISED_KEYS = {"reocr_sweep", "reocr_local_sweep", "ocr", "verify_worker", "reconciler",
                   "corpus_steward", "deadline_extractor", "execution_tracker", "filing_monitor"}


def _apply(rules, key, role):
    hay = f"{key} {role or ''}".lower()
    for pat, val in rules:
        if re.search(pat, hay):
            return val
    return None


def enum_systemd():
    out = subprocess.run(["systemctl", "list-timers", "landtek-*", "--all", "--no-pager"],
                         capture_output=True, text=True).stdout
    units = sorted(set(re.findall(r"landtek-[a-z0-9-]+\.timer", out)))
    rows = {}
    for u in units:
        k = _norm(u)
        rows[k] = {"agent_key": k, "layer": "systemd", "systemd_unit": u,
                   "heartbeat_source": f"systemd:{u}"}
    return rows


def enum_cron():
    out = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    rows = {}
    for line in out.splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        for scr in re.findall(r"scripts/([a-z_]+)\.(?:py|sh)", line):
            rows[scr] = {"agent_key": scr, "layer": "cron",
                         "heartbeat_source": f"cron:{scr}"}
    # refresh_all children (the hidden sub-fleet)
    try:
        with open(os.path.join(HERE, "refresh_all.py")) as f:
            body = f.read()
        for child in sorted(set(re.findall(r"refresh_[a-z_]+", body))):
            if child == "refresh_all":
                continue
            rows[child] = {"agent_key": child, "layer": "cron-child",
                           "heartbeat_source": "cron:refresh_all.py"}
    except Exception:
        pass
    return rows


def load_catalog():
    sys.path.insert(0, HERE)
    try:
        import agents
        cat = {}
        for row in agents.AGENTS:
            key, role, fuel, cadence, unit, status, notes = (list(row) + [None] * 7)[:7]
            cat[_norm(key)] = {"role": role, "fuel": fuel, "cadence": cadence,
                               "systemd_unit": (unit or None), "state_hint": status, "note": notes}
        return cat
    except Exception as e:
        print(f"[warn] could not import agents.py catalog: {e}")
        return {}


def sync():
    runtime = {}
    runtime.update(enum_systemd())
    for k, v in enum_cron().items():
        runtime.setdefault(k, v)
    catalog = load_catalog()

    merged = {}
    # 1) every runtime agent is a row (ground truth)
    for k, v in runtime.items():
        merged[k] = dict(v)
    # 2) overlay catalog metadata; catalog-only agents (on-demand tools) become rows too
    for k, c in catalog.items():
        r = merged.get(k, {"agent_key": k, "layer": "catalog-only", "heartbeat_source": "none"})
        r.setdefault("agent_key", k)
        r["role"] = c["role"]; r["fuel"] = c["fuel"]
        r.setdefault("cadence", c["cadence"])
        if c.get("systemd_unit") and not r.get("systemd_unit"):
            r["systemd_unit"] = c["systemd_unit"]
        merged[k] = r

    now = datetime.now(timezone.utc)
    conn = _conn(); cur = conn.cursor()
    for k, r in merged.items():
        role = r.get("role")
        tier = _apply(TIER_RULES, k, role) or "unset"
        owner = _apply(OWNER_RULES, k, role) or "unassigned"
        uncatalogued = role is None and r.get("layer") in ("systemd", "cron")
        note = ("RUNNING but not in agents.py catalog" if uncatalogued else r.get("note"))
        # A61: sync only ever assigns a PROVISIONAL tier (heuristic). It never grants autonomy, and it
        # must NOT stomp a human-granted tier back to the heuristic on re-sync — grants are preserved.
        cur.execute(
            """INSERT INTO agent_registry
                 (agent_key, display_name, role, tier, tier_status, fuel, owner, heartbeat_source,
                  systemd_unit, cadence, layer, supervised, state, note, seen_at, updated_at)
               VALUES (%s,%s,%s,%s,'provisional',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
               ON CONFLICT (agent_key) DO UPDATE SET
                 role=EXCLUDED.role, fuel=EXCLUDED.fuel, owner=EXCLUDED.owner,
                 heartbeat_source=EXCLUDED.heartbeat_source, systemd_unit=EXCLUDED.systemd_unit,
                 cadence=EXCLUDED.cadence, layer=EXCLUDED.layer, supervised=EXCLUDED.supervised,
                 note=EXCLUDED.note, seen_at=EXCLUDED.seen_at, updated_at=now(),
                 -- preserve a GRANTED tier; re-apply the heuristic only to still-provisional rows
                 tier = CASE WHEN agent_registry.tier_status='granted'
                             THEN agent_registry.tier ELSE EXCLUDED.tier END""",
            (k, k.replace("_", " "), role, tier, r.get("fuel"), owner,
             r.get("heartbeat_source", "none"), r.get("systemd_unit"), r.get("cadence"),
             r.get("layer", "catalog-only"), k in SUPERVISED_KEYS, "live", note, now),
        )
    # summary
    cur.execute("SELECT layer, count(*) FROM agent_registry GROUP BY layer ORDER BY layer")
    print("agent_registry synced:")
    for layer, n in cur.fetchall():
        print(f"  {layer:14s} {n}")
    cur.execute("SELECT count(*) FROM agent_registry WHERE note LIKE 'RUNNING but not%'")
    print(f"  uncatalogued-but-running: {cur.fetchone()[0]}")
    cur.execute("SELECT count(*) FROM agent_registry WHERE tier='unset'")
    print(f"  tier=unset (need review):  {cur.fetchone()[0]}")
    cur.close(); conn.close()


def report():
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT tier, owner, count(*) n, count(*) FILTER (WHERE supervised) sup "
                "FROM agent_registry GROUP BY tier, owner ORDER BY tier, owner")
    print(f"{'TIER':6s} {'OWNER':16s} {'N':>3s} {'SUPERVISED':>10s}")
    for r in cur.fetchall():
        print(f"{r['tier']:6s} {r['owner']:16s} {r['n']:>3d} {r['sup']:>10d}")
    cur.close(); conn.close()


def health():
    """Is each agent's heartbeat fresh? systemd -> last-trigger; others -> reported, not checked yet."""
    conn = _conn(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT agent_key, systemd_unit, heartbeat_source FROM agent_registry "
                "WHERE layer='systemd' ORDER BY agent_key")
    stale = []
    for r in cur.fetchall():
        u = r["systemd_unit"]
        show = subprocess.run(["systemctl", "show", u, "-p", "LastTriggerUSec", "-p", "Result"],
                              capture_output=True, text=True).stdout
        last = "LastTriggerUSec=n/a" in show or "LastTriggerUSec=\n" in show
        if last:
            stale.append(r["agent_key"])
    print(f"systemd agents checked; never-triggered: {len(stale)}")
    if stale:
        print("  " + ", ".join(stale))
    cur.close(); conn.close()


def grant(agent_key, tier, evidence, by):
    """A61: RECORD a tier grant. A tier rises only via a metric gate + human sign-off, and the grant
    NAMES its metric evidence. No agent calls this on itself — it is an operator action."""
    if tier not in ("T0", "T1", "T2", "T3"):
        print("tier must be T0..T3"); return
    if not evidence or not by:
        print("A61 requires --evidence (the metric gate) AND --by (human sign-off)"); return
    conn = _conn(); cur = conn.cursor()
    cur.execute("SELECT tier, tier_status FROM agent_registry WHERE agent_key=%s", (agent_key,))
    row = cur.fetchone()
    if not row:
        print(f"unknown agent '{agent_key}' — run --sync first"); return
    cur.execute(
        "UPDATE agent_registry SET tier=%s, tier_status='granted', tier_evidence=%s, "
        "tier_signed_off_by=%s, tier_set_at=now(), updated_at=now() WHERE agent_key=%s",
        (tier, evidence, by, agent_key),
    )
    print(f"GRANTED {agent_key}: {row[0]}/{row[1]} -> {tier}/granted  (by {by}; evidence: {evidence})")
    cur.close(); conn.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--report"
    if mode == "--sync":
        sync()
    elif mode == "--health":
        health()
    elif mode == "--grant":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--grant", dest="_m")  # consume the mode flag
        ap.add_argument("agent"); ap.add_argument("tier")
        ap.add_argument("--evidence", required=True); ap.add_argument("--by", required=True)
        a = ap.parse_args()
        grant(a.agent, a.tier, a.evidence, a.by)
    else:
        report()
