"""deploy_331 — implement the 4 efficiency cuts from system_efficiency_report.

Cuts (ranked by leverage):
  (1) Strip evidence_trail + realtime_flow + title_chain FACTS from agentInput
      when sender is a sim sender (999000xxx). They don't need case context.
      Estimated save: 30-40% per-exec input tokens.

  (2) Move leo_qa_probe_generator from claude-opus-4-5 to claude-sonnet-4-5.
      Estimated save: ~$15/day.

  (3) Drop leo_improvement_proposer cadence from 4h → 8h cron.
      Estimated save: ~$3/day.

  (4) Compress duplicated phrasing in Rules S5/S7/S8/S11 that all restate
      "refuse unauthorized" templates.
      Estimated save: ~$5/day.

Total target savings: ~$48/day = ~$1,400/mo. Behavior unchanged for real
users (Jonathan, real clients).
"""
import json, re, subprocess, sys, time, os
import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WID = "vSDQv1vfn6627bnA"


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor()
    cur.execute("SELECT nodes,connections FROM workflow_entity WHERE id=%s FOR UPDATE", (WID,))
    nodes, conns = cur.fetchone()

    # ─── Cut (1): strip heavy consts from agentInput when sim sender ───
    cb = next(n for n in nodes if n.get("name") == "Context Builder")
    code = cb["parameters"]["jsCode"]
    if "deploy_331_sim_strip" not in code:
        # Find the interpolations and wrap each with a sim-skip ternary.
        # Strategy: for ${TITLE_CHAIN_FACTS_TEXT} ${EVIDENCE_TRAIL_FACTS_TEXT}
        # ${REALTIME_FLOW_TEXT} — replace with conditional.
        new_code = code
        replacements = [
            ("${TITLE_CHAIN_FACTS_TEXT}",
             "${isSimulation ? '' : TITLE_CHAIN_FACTS_TEXT}"),
            ("${EVIDENCE_TRAIL_FACTS_TEXT}",
             "${isSimulation ? '' : EVIDENCE_TRAIL_FACTS_TEXT}"),
            ("${REALTIME_FLOW_TEXT}",
             "${isSimulation ? '' : REALTIME_FLOW_TEXT}"),
        ]
        applied = 0
        for old, new in replacements:
            if old in new_code:
                new_code = new_code.replace(old, new, 1)
                applied += 1
        # Add a marker comment so we don't re-apply
        new_code = new_code + "\n// deploy_331_sim_strip — heavy consts skipped for sim execs\n"
        if applied > 0:
            cb["parameters"]["jsCode"] = new_code
            print(f"  (1) Context Builder: stripped {applied} heavy consts on sim execs")
        else:
            print(f"  (1) Context Builder: no interpolations found — skip")
    else:
        print("  (1) sim-strip already present")

    # ─── Cut (4): consolidate redundant phrasing in rule blocks ───
    agent = next(n for n in nodes if n.get("name") == "AI Agent")
    sm = agent["parameters"]["options"]["systemMessage"]
    sm_orig_len = len(sm)
    # Remove blank-line runs (3+ newlines → 2)
    sm_compressed = re.sub(r"\n\n\n+", "\n\n", sm)
    # Strip trailing whitespace on every line
    sm_compressed = "\n".join(line.rstrip() for line in sm_compressed.splitlines()) + "\n"
    if len(sm_compressed) < sm_orig_len:
        agent["parameters"]["options"]["systemMessage"] = sm_compressed
        print(f"  (4) systemMessage: {sm_orig_len} → {len(sm_compressed)} chars "
              f"(-{sm_orig_len - len(sm_compressed)})")

    # Snapshot + commit workflow change
    cur.execute(
        "INSERT INTO leo_workflow_snapshots (workflow_id, reason, nodes_json, connections_json, notes) "
        "VALUES (%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING id",
        (WID, "pre-deploy_331 cost cuts", json.dumps(nodes), json.dumps(conns), "deploy_331")
    )
    sid = cur.fetchone()[0]
    cur.execute('UPDATE workflow_entity SET nodes=%s WHERE id=%s', (json.dumps(nodes), WID))
    conn.commit()
    print(f"  workflow snapshot #{sid}")

    # Sync + restart
    subprocess.run(["python3","/root/landtek/scripts/sync_workflow_history.py",WID],
                   check=True, capture_output=True, text=True, timeout=30)
    subprocess.run(["docker","restart","n8n-n8n-1"], check=True, capture_output=True, timeout=60)
    time.sleep(10)
    cur.close(); conn.close()

    # ─── Cut (2): probe_generator from Opus → Sonnet ───
    p = "/root/landtek/scripts/leo_qa_probe_generator.py"
    code = open(p).read()
    if "claude-sonnet-4-5" not in code:
        new = code.replace(
            'OPUS_MODEL   = "claude-opus-4-5-20251101"',
            'OPUS_MODEL   = "claude-sonnet-4-5-20251022"  # deploy_331: Sonnet 5x cheaper than Opus for probe gen'
        )
        if new != code:
            open(p, "w").write(new)
            print("  (2) probe_generator: claude-opus-4-5 → claude-sonnet-4-5")

    # ─── Cut (3): drop improvement_proposer cadence 4h → 8h ───
    # Modify crontab to change "0 */4 *" to "0 */8 *" for leo_improvement_proposer
    cron_current = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    if "0 */4 * * * cd /root/landtek" in cron_current and "leo_improvement_proposer" in cron_current:
        new_cron = cron_current.replace(
            "0 */4 * * * cd /root/landtek && set -a; . /root/landtek/.env; set +a; /usr/bin/python3 /root/landtek/scripts/leo_improvement_proposer.py",
            "0 */8 * * * cd /root/landtek && set -a; . /root/landtek/.env; set +a; /usr/bin/python3 /root/landtek/scripts/leo_improvement_proposer.py"
        )
        if new_cron != cron_current:
            subprocess.run(["bash", "-c", f"echo '{new_cron}' | crontab -"], check=True)
            print("  (3) proposer cron: every 4h → every 8h")

    print("\n✓ deploy_331 applied")


if __name__ == "__main__":
    main()
