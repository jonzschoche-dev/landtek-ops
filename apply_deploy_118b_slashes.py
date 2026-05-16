#!/usr/bin/env python3
"""Deploy 118-B — Add /files /inventory /dedupe /tax_decs to slash router."""
import json, sys, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

NEW_JS = r"""// Slash Command Router — deploy_118-B (with inventory + dedup + tax_decs)
const msg = $('Telegram Trigger').first().json.message || {};
const text = String(msg.text || msg.caption || '').trim();
const senderId = String(msg.from?.id || '');
const JONATHAN = '6513067717';

let isSlash = false; let command = null; let args = '';
let endpoint = null; let handlesInline = false; let helpText = null;

const ALLOWED = {
  status: {nC:false}, digest: {nC:false},
  report: {nC:true, dC:'MWK-001'}, pdf_report: {nC:true, dC:'MWK-001'},
  cashflow: {nC:true, dC:'MWK-001'}, pnl: {nC:false},
  valuation: {nA:true}, pack: {nC:true, dC:'MWK-001'},
  goals: {nC:true, dC:'MWK-001', pn:'case'}, duties: {nC:true, dC:'MWK-001', pn:'case'},
  bottlenecks: {nC:true, dC:'MWK-001', pn:'case'}, finance: {nC:false},
  stage: {nC:true, dC:'MWK-CV26360', pn:'scope'}, verify: {nL:true},
  approve: {nAp:true}, deny: {nD:true}, block: {nD:true},
  pending_approvals: {nC:false},
  files: {nC:true, dC:''}, inventory: {nC:true, dC:''}, dedupe: {nC:false},
  tax_decs: {nC:true, dC:'MWK-001'},
};

if (text.startsWith('/')) {
  isSlash = true;
  const m = text.match(/^\/(\w+)(?:\s+(.*))?$/);
  if (m) { command = m[1].toLowerCase(); args = (m[2] || '').trim(); }
  if (senderId !== JONATHAN && !['help'].includes(command)) {
    handlesInline = true; helpText = "Slash commands are operator-only.";
  } else if (command === 'help') {
    handlesInline = true;
    helpText =
      "Slash commands:\n" +
      "  /status                  system + cases summary\n" +
      "  /digest                  daily digest\n" +
      "  /report <case>           case brief\n" +
      "  /pdf_report <case>       PDF case brief\n" +
      "  /cashflow <case>         Cash Flow PDF\n" +
      "  /pnl                     Firm P&L PDF\n" +
      "  /valuation <asset>       Asset valuation memo\n" +
      "  /pack <case>             Bundled financial pack\n" +
      "  /tax_decs <case>         Active tax declarations roll-up\n" +
      "  /files                   Master file directory\n" +
      "  /inventory <case>        Per-case file inventory\n" +
      "  /dedupe                  Run dedup audit + digest\n" +
      "  /goals <case>            client goals\n" +
      "  /duties <case>           Landtek's duties\n" +
      "  /bottlenecks <case>      open bottlenecks\n" +
      "  /stage <matter>          procedural stage\n" +
      "  /verify <claim>          truth-check claim\n" +
      "  /finance                 firm snapshot\n" +
      "  /pending_approvals       pending onboardings\n" +
      "  /approve <tg_id> <role>  approve user\n" +
      "  /deny <tg_id> <reason>   decline user\n" +
      "  /block <tg_id> <reason>  silent block\n" +
      "  /q <text>                query mode\n" +
      "  /help                    this list";
  } else if (command === 'q') {
    handlesInline = false;
  } else if (ALLOWED[command]) {
    handlesInline = true;
    const cfg = ALLOWED[command];
    if (cfg.nL) {
      if (!args) helpText = "Usage: /verify <claim>";
      else endpoint = 'http://localhost:8765/api/verify?claim=' + encodeURIComponent(args) + '&send=1';
    } else if (cfg.nA) {
      if (!args) helpText = "Usage: /valuation <asset> (e.g. T-32917)";
      else endpoint = 'http://localhost:8765/api/valuation?asset=' + encodeURIComponent(args);
    } else if (cfg.nAp) {
      const parts = args.split(/\s+/); const tg = parts[0]; const role = parts[1] || 'prospect'; const c = parts[2] || '';
      if (!tg) helpText = "Usage: /approve <tg_id> <role> [case_file]";
      else endpoint = 'http://localhost:8765/api/approve_user?id=' + encodeURIComponent(tg) + '&role=' + encodeURIComponent(role) + (c ? ('&case=' + encodeURIComponent(c)) : '');
    } else if (cfg.nD) {
      const mm = args.match(/^(\S+)\s*(.*)$/);
      if (!mm) helpText = "Usage: /" + command + " <tg_id> <reason>";
      else {
        const tg = mm[1]; const r = mm[2] || '';
        endpoint = 'http://localhost:8765/api/' + (command === 'block' ? 'block_user' : 'deny_user') + '?id=' + encodeURIComponent(tg) + '&reason=' + encodeURIComponent(r);
      }
    } else if (cfg.nC) {
      const v = args || cfg.dC;
      const pn = cfg.pn || 'case';
      if (v) endpoint = 'http://localhost:8765/api/' + command + '?' + pn + '=' + encodeURIComponent(v) + '&send=1';
      else endpoint = 'http://localhost:8765/api/' + command + '?send=1';
    } else {
      endpoint = 'http://localhost:8765/api/' + command + '?send=1';
    }
  } else {
    handlesInline = true; helpText = "Unknown slash command. Type /help.";
  }
}
return [{ json: { ...$('Telegram Trigger').first().json,
  _slash_is_slash: isSlash, _slash_command: command, _slash_args: args,
  _slash_endpoint: endpoint, _slash_handles_inline: handlesInline, _slash_help_text: helpText, }}];"""


def main():
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword")
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_118b_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    sr = next((n for n in nodes if n["name"] == "Slash Router"), None)
    sr["parameters"]["jsCode"] = NEW_JS
    cur.close(); conn.close()
    from deploy_helpers import patch_workflow_dual
    patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    print("  ✓ Slash Router updated with /files /inventory /dedupe /tax_decs")


if __name__ == "__main__":
    main()
