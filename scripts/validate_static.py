#!/usr/bin/env python3
"""validate_static.py — Mode 1 of the lean simulator (deploy_337).

Structural verifications against the n8n workflow. ZERO LLM calls.

Checks:
  - Critical Rule blocks present in systemMessage (S1, S2, S3, S4, S5,
    S6, S7, S8, S9, S10, S11, S12, S13)
  - Context Builder loads required consts:
      TITLE_CHAIN_FACTS_TEXT, EVIDENCE_TRAIL_FACTS_TEXT,
      REALTIME_FLOW_TEXT, OBJECTIVES_TEXT, CLIENT_HISTORY_TEXT
  - chat_id sim-gate present on all 11 Telegram-send nodes (deploy_300)
  - Reply nodes have onError=continueRegularOutput (deploy_300)
  - n8n container healthy

Run on demand or after every deploy. Returns exit code 0 if all green,
non-zero with explicit failure list otherwise. Optionally pushes
violations via push_strict if --push flag given.

Cost: $0 (pure SQL + workflow JSON inspection).
"""
from __future__ import annotations
import argparse, json, os, sys, subprocess
from datetime import datetime, timezone
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID = "vSDQv1vfn6627bnA"

REQUIRED_RULES = [f"Rule S{i}" for i in range(1, 14)]
REQUIRED_CONSTS = [
    "TITLE_CHAIN_FACTS_TEXT",
    "EVIDENCE_TRAIL_FACTS_TEXT",
    "REALTIME_FLOW_TEXT",
    "OBJECTIVES_TEXT",
    "CLIENT_HISTORY_TEXT",
]
TELEGRAM_SEND_NODES = [
    "Reply to Client", "Reply to Jonathan", "Send to Target Contact",
    "Send Files Link to Recipient", "Ask Clarification",
    "Notify Jonathan of Resolution", "Confirm Context To Jonathan",
    "Notify File Location", "Send Onboarding Reply", "Send Slash Help",
    "Notify Jonathan Unauth",
]


def fetch_workflow():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return None
    return row[0]


def check_n8n_healthz():
    try:
        r = subprocess.run(["curl", "-sf", "http://localhost:5678/healthz"],
                          capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def validate(nodes) -> tuple[list[str], list[str]]:
    fails, passes = [], []
    agent = next((n for n in nodes if n.get("name") == "AI Agent"), None)
    if not agent:
        fails.append("CRITICAL: AI Agent node missing from workflow")
        return fails, passes
    sm = agent.get("parameters", {}).get("options", {}).get("systemMessage", "") or ""

    # Rule presence
    for rule in REQUIRED_RULES:
        if rule in sm:
            passes.append(f"rule_present:{rule}")
        else:
            fails.append(f"RULE MISSING: {rule} not in systemMessage")

    # Context Builder consts
    cb = next((n for n in nodes if n.get("name") == "Context Builder"), None)
    if not cb:
        fails.append("CRITICAL: Context Builder node missing")
    else:
        code = cb.get("parameters", {}).get("jsCode", "") or ""
        for c in REQUIRED_CONSTS:
            if f"const {c}" in code:
                passes.append(f"const_present:{c}")
            else:
                fails.append(f"CONST MISSING: const {c} not in Context Builder jsCode")
        # Sim-strip pattern (deploy_331/332/334)
        if "isSimulation" in code:
            passes.append("sim_strip_present")
        else:
            fails.append("SIM STRIP MISSING: isSimulation gate not in Context Builder")

    # Telegram send-node sim gates (deploy_300)
    # Look at the raw chatId / jsonBody value — n8n stores 999 as the
    # detection prefix (deploy_300), not 999000.
    for node_name in TELEGRAM_SEND_NODES:
        n = next((x for x in nodes if x.get("name") == node_name), None)
        if not n:
            continue
        params = n.get("parameters", {})
        candidates = [
            str(params.get("chatId", "")),
            str(params.get("jsonBody", "")),
            str(params.get("url", "")),
            str(params.get("text", "")),
        ]
        gate_found = any(
            ('startsWith("999")' in c) or ("startsWith('999')" in c)
            or ('startsWith("999000")' in c) or ("startsWith('999000')" in c)
            for c in candidates
        )
        if gate_found:
            passes.append(f"sim_gate:{node_name}")
        else:
            fails.append(f"SIM GATE MISSING on Telegram send node: {node_name}")
        if n.get("onError") != "continueRegularOutput":
            fails.append(f"onError MISSING: {node_name} not set to continueRegularOutput")
        else:
            passes.append(f"onError_ok:{node_name}")

    return fails, passes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="Push violations via tg_send")
    args = ap.parse_args()

    print(f"[validate_static] {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    if not check_n8n_healthz():
        print("  ✗ n8n container unhealthy / unreachable")
        sys.exit(1)
    nodes = fetch_workflow()
    if nodes is None:
        print("  ✗ workflow not in DB")
        sys.exit(2)

    fails, passes = validate(nodes)
    print(f"  passes: {len(passes)}")
    print(f"  fails:  {len(fails)}")
    for f in fails:
        print(f"    ✗ {f}")

    if fails and args.push:
        try:
            sys.path.insert(0, "/root/landtek/scripts")
            from report_publisher import push_strict
            headline = f"🚨 Static validation FAILED: {len(fails)} issue(s)"
            body = ["## Lean simulator — static validation failures", ""]
            for f in fails:
                body.append(f"- {f}")
            body.append("")
            body.append(f"Passes: {len(passes)}")
            push_strict(headline=headline, body_md="\n".join(body),
                        source="watchdog", slug=f"validate-{datetime.now(timezone.utc):%Y%m%d-%H%M}")
        except Exception as e:
            print(f"  push failed: {e}")

    sys.exit(0 if not fails else 3)


if __name__ == "__main__":
    main()
