#!/usr/bin/env python3
"""Deploy 117-B — Add /cashflow /pnl /valuation /pack to slash router."""
import json, argparse, time, sys
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

NEW_JS = r"""// Slash Command Router — deploy_117-B (with financial PDFs)
const msg = $('Telegram Trigger').first().json.message || {};
const text = String(msg.text || msg.caption || '').trim();
const senderId = String(msg.from?.id || '');
const JONATHAN = '6513067717';

let isSlash = false;
let command = null;
let args = '';
let endpoint = null;
let handlesInline = false;
let helpText = null;

const ALLOWED = {
  status:      { needsCase: false },
  digest:      { needsCase: false },
  report:      { needsCase: true,  defaultCase: 'MWK-001' },
  pdf_report:  { needsCase: true,  defaultCase: 'MWK-001' },
  cashflow:    { needsCase: true,  defaultCase: 'MWK-001' },
  pnl:         { needsCase: false },
  valuation:   { needsAsset: true },
  pack:        { needsCase: true,  defaultCase: 'MWK-001' },
  goals:       { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  duties:      { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  bottlenecks: { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  finance:     { needsCase: false },
  stage:       { needsCase: true,  defaultCase: 'MWK-CV26360', paramName: 'scope' },
  verify:      { needsClaim: true },
  approve:     { needsApproveArgs: true },
  deny:        { needsDenyArgs: true },
  block:       { needsDenyArgs: true },
  pending_approvals: { needsCase: false },
};

if (text.startsWith('/')) {
  isSlash = true;
  const m = text.match(/^\/(\w+)(?:\s+(.*))?$/);
  if (m) { command = m[1].toLowerCase(); args = (m[2] || '').trim(); }

  if (senderId !== JONATHAN && !['help'].includes(command)) {
    handlesInline = true;
    helpText = "Slash commands are operator-only.";
  } else if (command === 'help') {
    handlesInline = true;
    helpText =
      "Slash commands:\n" +
      "  /status                  system + cases summary\n" +
      "  /digest                  today's daily digest\n" +
      "  /report <case>           case intelligence brief\n" +
      "  /pdf_report <case>       PDF case brief\n" +
      "  /cashflow <case>         Cash Flow Statement PDF\n" +
      "  /pnl                     LandTek Firm P&L PDF\n" +
      "  /valuation <asset>       Per-asset valuation memo PDF\n" +
      "  /pack <case>             Bundled financial pack (cashflow + P&L + top valuations)\n" +
      "  /goals <case>            client goals\n" +
      "  /duties <case>           Landtek's duties\n" +
      "  /bottlenecks <case>      open bottlenecks\n" +
      "  /stage <matter>          procedural stage\n" +
      "  /verify <claim>          truth-check a claim\n" +
      "  /finance                 firm financial snapshot\n" +
      "  /pending_approvals       list pending onboarding users\n" +
      "  /approve <tg_id> <role>  approve a user\n" +
      "  /deny <tg_id> <reason>   decline politely\n" +
      "  /block <tg_id> <reason>  silent block\n" +
      "  /q <text>                query mode\n" +
      "  /help                    this list";
  } else if (command === 'q') {
    handlesInline = false;
  } else if (ALLOWED[command]) {
    handlesInline = true;
    const cfg = ALLOWED[command];
    if (cfg.needsClaim) {
      if (!args) helpText = "Usage: /verify <claim>";
      else endpoint = 'http://localhost:8765/api/verify?claim=' + encodeURIComponent(args) + '&send=1';
    } else if (cfg.needsAsset) {
      if (!args) helpText = "Usage: /valuation <asset> (e.g. /valuation T-32917)";
      else endpoint = 'http://localhost:8765/api/valuation?asset=' + encodeURIComponent(args);
    } else if (cfg.needsApproveArgs) {
      const parts = args.split(/\s+/);
      const tgId = parts[0] || ''; const role = parts[1] || 'prospect'; const caseArg = parts[2] || '';
      if (!tgId) helpText = "Usage: /approve <tg_id> <role: client|prospect|counsel|counterparty|partner> [case_file]";
      else endpoint = 'http://localhost:8765/api/approve_user?id=' + encodeURIComponent(tgId) + '&role=' + encodeURIComponent(role) + (caseArg ? ('&case=' + encodeURIComponent(caseArg)) : '');
    } else if (cfg.needsDenyArgs) {
      const m2 = args.match(/^(\S+)\s*(.*)$/);
      if (!m2) helpText = "Usage: /" + command + " <tg_id> <reason>";
      else {
        const tgId = m2[1]; const reason = m2[2] || '';
        endpoint = 'http://localhost:8765/api/' + (command === 'block' ? 'block_user' : 'deny_user') + '?id=' + encodeURIComponent(tgId) + '&reason=' + encodeURIComponent(reason);
      }
    } else if (cfg.needsCase) {
      const v = args || cfg.defaultCase;
      const pname = cfg.paramName || 'case';
      endpoint = 'http://localhost:8765/api/' + command + '?' + pname + '=' + encodeURIComponent(v) + '&send=1';
    } else {
      endpoint = 'http://localhost:8765/api/' + command + '?send=1';
    }
  } else {
    handlesInline = true;
    helpText = "Unknown slash command. Type /help for available commands.";
  }
}

return [{
  json: { ...$('Telegram Trigger').first().json,
    _slash_is_slash: isSlash, _slash_command: command, _slash_args: args,
    _slash_endpoint: endpoint, _slash_handles_inline: handlesInline,
    _slash_help_text: helpText,
  },
}];"""


def main():
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_117b_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")
    sr = next((n for n in nodes if n["name"] == "Slash Router"), None)
    sr["parameters"]["jsCode"] = NEW_JS
    print("  ✓ updated Slash Router with /cashflow /pnl /valuation /pack")
    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(wf_id, nodes=nodes, connections=conns)


if __name__ == "__main__":
    main()
