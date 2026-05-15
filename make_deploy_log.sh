#!/usr/bin/env bash
# Master deploy log generator — joins 5 sources into a single chronological view.
#
# Sources:
#   1. /opt/cowork-bridge/repo/outbox/*.log    (cowork-bridge daemon deploys)
#   2. /root/landtek/apply_deploy_*.py          (in-place SQL/Python patches)
#   3. /root/landtek/snapshots/*.json           (pre-patch workflow JSON)
#   4. workflow_audit table                     (every workflow_entity change)
#
# Outputs:
#   /root/landtek/DEPLOY_LOG.md   — chronological markdown table for humans
#   /root/landtek/DEPLOY_LOG.csv  — machine-readable
#
# Run anytime to regenerate. No state preserved between runs.

set -uo pipefail

OUT_MD=/root/landtek/DEPLOY_LOG.md
OUT_CSV=/root/landtek/DEPLOY_LOG.csv

# Build CSV first, then convert to MD
python3 - <<'PY' > "$OUT_CSV"
import os, re, csv, sys, glob, subprocess
from datetime import datetime
from pathlib import Path

rows = []

# ── Source 1: cowork-bridge outbox ──────────────────────────────────────────
# Filenames look like: 20260515T002407Z_034_proactive_investigation_rule.log
for log_path in glob.glob("/opt/cowork-bridge/repo/outbox/*.log"):
    fn = os.path.basename(log_path)
    m = re.match(r'(\d{8}T\d{6}Z)_(\d+)_(.+)\.log$', fn)
    if not m:
        continue
    ts_str, deploy_id, name = m.group(1), m.group(2), m.group(3)
    ts_iso = f"{ts_str[0:4]}-{ts_str[4:6]}-{ts_str[6:8]}T{ts_str[9:11]}:{ts_str[11:13]}:{ts_str[13:15]}Z"
    # Extract exit code from log
    exit_code = ""
    try:
        with open(log_path) as f:
            content = f.read()
        m_exit = re.search(r'exit_code:\s+(\d+)', content)
        if m_exit:
            exit_code = m_exit.group(1)
    except Exception:
        pass
    status = "success" if exit_code == "0" else ("error" if exit_code else "?")
    rows.append({
        "timestamp": ts_iso,
        "deploy_id": deploy_id,
        "type": "cowork",
        "name": name.replace('_', ' '),
        "status": status,
        "source_path": log_path,
        "details": "",
    })

# ── Source 2: in-place apply_deploy_*.py ────────────────────────────────────
for py_path in sorted(glob.glob("/root/landtek/apply_deploy_*.py")):
    fn = os.path.basename(py_path)
    m = re.match(r'apply_deploy_(\w+)\.py$', fn)
    if not m:
        continue
    deploy_id = m.group(1)
    # mtime as the deploy timestamp (closest signal)
    mtime = datetime.utcfromtimestamp(os.path.getmtime(py_path))
    ts_iso = mtime.strftime("%Y-%m-%dT%H:%M:%SZ")
    # First line of docstring as the summary
    summary = ""
    try:
        with open(py_path) as f:
            content = f.read()
        m_ds = re.search(r'"""(.+?)\n', content, re.DOTALL)
        if m_ds:
            summary = m_ds.group(1).strip()
    except Exception:
        pass
    rows.append({
        "timestamp": ts_iso,
        "deploy_id": deploy_id,
        "type": "in-place",
        "name": summary[:80],
        "status": "applied",
        "source_path": py_path,
        "details": "",
    })

# ── Source 3: snapshots (pre-patch state) ───────────────────────────────────
for snap_path in sorted(glob.glob("/root/landtek/snapshots/*.json")):
    fn = os.path.basename(snap_path)
    m = re.match(r'leos_workflow_pre_(\w+)_(\d{8}T\d{6}Z)\.json$', fn)
    if not m:
        continue
    deploy_id, ts_str = m.group(1), m.group(2)
    ts_iso = f"{ts_str[0:4]}-{ts_str[4:6]}-{ts_str[6:8]}T{ts_str[9:11]}:{ts_str[11:13]}:{ts_str[13:15]}Z"
    size_kb = os.path.getsize(snap_path) // 1024
    rows.append({
        "timestamp": ts_iso,
        "deploy_id": deploy_id,
        "type": "snapshot",
        "name": f"pre-deploy {deploy_id} workflow JSON ({size_kb} KB)",
        "status": "saved",
        "source_path": snap_path,
        "details": "",
    })

# ── Source 4: workflow_audit table ──────────────────────────────────────────
try:
    res = subprocess.run([
        "docker", "exec", "-i", "n8n-postgres-1",
        "psql", "-U", "n8n", "-d", "n8n", "-tAF", "|", "-c",
        """SELECT id, workflow_name,
                  to_char(changed_at, 'YYYY-MM-DD HH24:MI:SSZ'),
                  ai_agent_prompt_len, has_rule_a, has_rule_b,
                  has_strict_isolation, has_jonathan_clause,
                  insert_chat_note_cols, insert_cal_event_cols,
                  log_file_receipt_clean, log_conversation_has_raw,
                  log_leo_int_has_fallback,
                  COALESCE(change_application_name, '?')
             FROM workflow_audit
            WHERE workflow_name='Leos Workflow'
            ORDER BY id"""
    ], capture_output=True, text=True, timeout=10)
    for line in res.stdout.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 14:
            continue
        audit_id, wf, ts, plen, a, b, iso, jon, icn, ice, lfr, lcr, llif, src = parts[:14]
        # Compute regression flag
        flags = []
        if a == 't': flags.append("A")
        if b == 't': flags.append("B")
        if iso == 't': flags.append("Iso")
        if jon == 't': flags.append("Jon")
        rules_present = '+'.join(flags) if flags else "(no rules)"
        ts_iso = ts.replace(' ', 'T').replace('Z', '') + "Z"
        rows.append({
            "timestamp": ts_iso,
            "deploy_id": f"audit{audit_id}",
            "type": "audit",
            "name": f"prompt={plen} chars, rules={rules_present}, icn={icn}, ice={ice}",
            "status": "regression" if int(plen) < 12000 else "OK",
            "source_path": "workflow_audit",
            "details": f"src={src}",
        })
except Exception as e:
    print(f"# audit-table-fetch-failed: {e}", file=sys.stderr)

# Sort by timestamp ascending
rows.sort(key=lambda r: r["timestamp"])

writer = csv.DictWriter(sys.stdout, fieldnames=["timestamp", "deploy_id", "type", "status", "name", "source_path", "details"])
writer.writeheader()
for r in rows:
    writer.writerow(r)
PY

echo "wrote $OUT_CSV ($(wc -l < "$OUT_CSV") lines)" >&2

# Convert CSV to markdown table
python3 - <<PY
import csv
with open("$OUT_CSV") as f:
    rows = list(csv.DictReader(f))

with open("$OUT_MD", "w") as f:
    f.write(f"# LandTek Master Deploy Log\n\n")
    f.write(f"_Auto-generated by make_deploy_log.sh — {len(rows)} events_\n\n")
    f.write("Sources joined: cowork-bridge outbox + in-place patches + workflow snapshots + workflow_audit table\n\n")
    f.write("| When (UTC) | ID | Type | Status | Summary |\n")
    f.write("|---|---|---|---|---|\n")
    for r in rows:
        ts = r["timestamp"][:19].replace('T', ' ')
        name = r["name"].replace('|', '\\|')[:100]
        if r.get("details"):
            name += f"  _{r['details']}_"
        f.write(f"| {ts} | {r['deploy_id']} | {r['type']} | {r['status']} | {name} |\n")
PY

echo "wrote $OUT_MD"
echo
echo "═══ Summary by type ═══"
tail -n +2 "$OUT_CSV" | cut -d, -f3 | sort | uniq -c | sort -rn
echo
echo "═══ Last 10 entries ═══"
tail -10 "$OUT_MD"
