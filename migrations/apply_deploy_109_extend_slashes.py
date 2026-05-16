#!/usr/bin/env python3
"""Deploy 109 — Extend slash router with /verify, /stage, /finance, /goals, /duties, /bottlenecks.

Updates the Slash Router code node from deploy_108. Generic dispatch: any
known /<command> maps to /api/<command>. Unknown slashes get the help text.

Run: python3 apply_deploy_109_extend_slashes.py --target prod
"""
import json, argparse, time, sys
sys.path.insert(0, "/root/landtek")
import psycopg2

NEW_JS = r"""// Slash Command Router — deploy_109 (extended)
// Generic dispatch: maps /command → /api/command for the allow-listed set.
//   /status /digest /report /help /q  (existing)
//   /verify /stage /finance /goals /duties /bottlenecks /pdf_report  (new)

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
  goals:       { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  duties:      { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  bottlenecks: { needsCase: true,  defaultCase: 'MWK-001', paramName: 'case' },
  finance:     { needsCase: false },
  stage:       { needsCase: true,  defaultCase: 'MWK-CV26360', paramName: 'scope' },
  verify:      { needsClaim: true },
};

if (text.startsWith('/')) {
  isSlash = true;
  const m = text.match(/^\/(\w+)(?:\s+(.*))?$/);
  if (m) {
    command = m[1].toLowerCase();
    args = (m[2] || '').trim();
  }

  if (senderId !== JONATHAN && !['help'].includes(command)) {
    handlesInline = true;
    helpText = "Slash commands are operator-only. If you need information, just ask me directly.";
  } else if (command === 'help') {
    handlesInline = true;
    helpText =
      "Slash commands:\n" +
      "  /status            system + cases summary\n" +
      "  /digest            today's daily digest\n" +
      "  /report <case>     case intelligence brief\n" +
      "  /pdf_report <case> PDF case brief\n" +
      "  /goals <case>      client goals for a case\n" +
      "  /duties <case>     Landtek's duties for a case\n" +
      "  /bottlenecks <case>  open bottlenecks for a case\n" +
      "  /stage <matter>    procedural stage of a matter\n" +
      "  /verify <claim>    fact-check a claim through truth_negotiator\n" +
      "  /finance           firm + Leo cost snapshot\n" +
      "  /q <text>          query mode (or just message me directly)\n" +
      "  /help              this list";
  } else if (command === 'q') {
    handlesInline = false;  // pass through to AI Agent with prefix stripped
  } else if (ALLOWED[command]) {
    handlesInline = true;
    const cfg = ALLOWED[command];
    if (cfg.needsClaim) {
      if (!args) {
        helpText = "Usage: /verify <claim text>\nExample: /verify Civil Case 26-360 is at pretrial pending";
      } else {
        endpoint = 'http://localhost:8765/api/verify?claim=' + encodeURIComponent(args) + '&send=1';
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
  json: {
    ...$('Telegram Trigger').first().json,
    _slash_is_slash: isSlash,
    _slash_command: command,
    _slash_args: args,
    _slash_endpoint: endpoint,
    _slash_handles_inline: handlesInline,
    _slash_help_text: helpText,
  },
}];"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], default="prod")
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") \
        if args.target == "prod" else \
        dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")

    from datetime import datetime, timezone
    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb, connections::jsonb FROM workflow_entity WHERE name='Leos Workflow'")
    wf_id, nodes, conns = cur.fetchone()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_109_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes, "connections": conns}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    sr = next((n for n in nodes if n["name"] == "Slash Router"), None)
    if not sr:
        sys.exit("FATAL: Slash Router node not found (run deploy_108 first)")
    sr["parameters"]["jsCode"] = NEW_JS
    print("  ✓ updated Slash Router jsCode")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes, connections=conns)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s',
                    (json.dumps(nodes), wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
