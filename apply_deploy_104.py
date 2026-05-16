#!/usr/bin/env python3
"""Deploy 104 — Verified-only retrieval mode + provenance tagging.

Per "we can only use verified data, hallucinations are not allowed":

A. Context Builder filters chat_notes + assets to allowed provenance levels:
   verified + inferred_corroborated (no inferred_strong or hallucinated).

B. EVERY entry passed to AI agentInput gets a provenance tag:
   [V] = verified (directly source-quote cited)
   [C] = inferred_corroborated (auto-promoted by mention count)
   [I] = inferred_strong (single-source LLM extraction)
   [U] = unverified (self-researched, no source check)

C. AI Agent prompt: cite the tag inline + adjust language by tier.
   Verified -> firm assertion. Corroborated -> "per our records" hedge.
   Inferred -> "appears to" / "we believe" hedge with caveat.
"""
import json, os, sys, argparse, time
sys.path.insert(0, "/root/landtek")
import psycopg2
from datetime import datetime, timezone

WF_NAME = "Leos Workflow"


# Updated SQL: only fetch verified + corroborated (drop inferred_strong)
FETCH_CHAT_NOTES_SQL = """(SELECT id, related_case AS case_file, topic, importance, summary,
        LEFT(content, 600) AS content_excerpt, created_at::text AS created_at,
        provenance_level
   FROM chat_notes
  WHERE related_case = (
    SELECT case_file FROM clients
     WHERE telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
     LIMIT 1
  )
   AND provenance_level IN ('verified', 'inferred_corroborated', 'inferred_strong')
  ORDER BY
    CASE provenance_level
      WHEN 'verified' THEN 1 WHEN 'inferred_corroborated' THEN 2
      WHEN 'inferred_strong' THEN 3 ELSE 4 END,
    importance DESC NULLS LAST, id DESC
  LIMIT 15)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::int, NULL::text, NULL::text, NULL::text, NULL::text;"""

FETCH_ASSETS_SQL = """(SELECT id, asset_type, canonical_id, case_file, area_sqm, current_status,
        current_holder, LEFT(notes, 300) AS notes_excerpt, provenance_level
   FROM assets
  WHERE case_file = (
    SELECT case_file FROM clients
     WHERE telegram_id = '{{ $('Telegram Trigger').first().json.message.from.id }}'::text
     LIMIT 1
  )
   AND provenance_level IN ('verified', 'inferred_corroborated', 'inferred_strong')
  ORDER BY
    CASE provenance_level
      WHEN 'verified' THEN 1 WHEN 'inferred_corroborated' THEN 2
      WHEN 'inferred_strong' THEN 3 ELSE 4 END,
    area_sqm DESC NULLS LAST, id DESC
  LIMIT 15)
UNION ALL SELECT NULL::int, NULL::text, NULL::text, NULL::text, NULL::real, NULL::text, NULL::text, NULL::text, NULL::text;"""


# Context Builder JS: change template to include provenance tags
CB_OLD_NOTES = """CASE NOTES (operator observations, evidence flags, prior decisions — use these to anchor your response in established context):
${caseNotes.length === 0 ? '(none for this case)' : caseNotes.slice(0,10).map(n => `[note:${n.id}] (${n.topic||'?'}, imp ${n.importance||'?'}): ${n.summary || (n.content_excerpt || '').slice(0,120)}`).join('\\n')}

CASE ASSETS (structured property ledger — refer by canonical_id when discussing):
${caseAssets.length === 0 ? '(none)' : caseAssets.slice(0,10).map(a => `${a.canonical_id} [${a.asset_type}, ${a.current_status||'?'}, area=${a.area_sqm||'?'}sqm, ${a.provenance_level}] ${a.notes_excerpt || ''}`).join('\\n')}"""

CB_NEW_NOTES = """CASE NOTES (operator observations, evidence flags, prior decisions — TIER-TAGGED):
${caseNotes.length === 0 ? '(none for this case)' : caseNotes.slice(0,10).map(n => {
  const tag = n.provenance_level === 'verified' ? '[V]' : n.provenance_level === 'inferred_corroborated' ? '[C]' : n.provenance_level === 'self_researched_unverified' ? '[U]' : '[I]';
  return `${tag} [note:${n.id}] (${n.topic||'?'}, imp ${n.importance||'?'}): ${n.summary || (n.content_excerpt || '').slice(0,120)}`;
}).join('\\n')}

CASE ASSETS (structured property ledger — TIER-TAGGED, refer by canonical_id):
${caseAssets.length === 0 ? '(none)' : caseAssets.slice(0,10).map(a => {
  const tag = a.provenance_level === 'verified' ? '[V]' : a.provenance_level === 'inferred_corroborated' ? '[C]' : '[I]';
  return `${tag} ${a.canonical_id} [${a.asset_type}, ${a.current_status||'?'}, area=${a.area_sqm||'?'}sqm] ${a.notes_excerpt || ''}`;
}).join('\\n')}"""


PROMPT_ANCHOR = "### CASE NOTES + CASE ASSETS in your input (added 2026-05-16 — deploy_102)"

PROMPT_ADDITION_TIERS = """### Provenance tiers — strict citation discipline (added 2026-05-16 — deploy_104)

EVERY case_note + case_asset entry in your input is now TAGGED with one of:

  [V] verified                 — directly cited to source doc with quoted excerpt
  [C] inferred_corroborated    — corroborated by ≥3 doc mentions, not yet quote-verified
  [I] inferred_strong          — single LLM extraction, ungrounded
  [U] self_researched_unverified — Leo's prior research, not yet human-confirmed

**Citation discipline by tier — INVIOLABLE**:

  [V] verified → firm assertion. "Per [V] note:54, the SPA was revoked Aug 15, 2005."

  [C] corroborated → hedged with "per our records" / "based on multiple docs".
      "Per [C] our records (note:94 + entity-cluster), Civil Case 6839 is at RTC Branch 40."

  [I] inferred_strong → REQUIRED hedge. "It appears that..." / "Based on a single extraction..."
      "Based on [I] a single extraction (note:62), Don Qi may be planning a Naga trip — needs confirmation."

  [U] unverified → MUST flag explicitly. "Leo's prior self-research (unverified) suggested X — pending your confirmation."
      Use sparingly. Prefer to suppress unverified content unless asked directly.

**Hallucination guard**: NEVER make a specific factual assertion (date, TCT number, party name, currency amount, docket) unless:
  - It appears in CLIENT PROFILE (clientRow.* fields)
  - OR It appears in a [V] or [C] tagged CASE NOTE / CASE ASSET
  - OR It appears in recent_documents extracted_excerpt
  - OR The current turn's input message contains it verbatim

If none of these apply, refuse with the verbatim template: "I have no verified source for that. The relevant fact may live in inferred_strong records that haven't been promoted, or in documents not yet extracted. Recommended: provide the source doc or confirm directly."

This is HARDER than prior rules. The old prompt allowed citing single-extraction notes. The new rule requires the assertion's source to be at least [C]-tier OR appear verbatim in the current turn.

For Rule C inquiry-to-relay (when relaying Jonathan's question to a client), this rule does NOT apply to the relayed_message text itself — that's Jonathan's wording. But your OWN summary back to Jonathan must follow tier discipline.

"""


def patch_node_sql(nodes, node_name, new_sql):
    n = next((x for x in nodes if x["name"] == node_name), None)
    if not n: return False
    n["parameters"]["query"] = new_sql
    return True


def patch_context_builder(node):
    js = node["parameters"]["jsCode"]
    if "TIER-TAGGED" in js:
        return False
    if CB_OLD_NOTES not in js:
        raise ValueError("CASE NOTES anchor not found in Context Builder")
    js = js.replace(CB_OLD_NOTES, CB_NEW_NOTES)
    node["parameters"]["jsCode"] = js
    return True


def patch_prompt(node):
    p = node["parameters"]["options"]["systemMessage"]
    if "Provenance tiers — strict citation discipline" in p:
        return False
    if PROMPT_ANCHOR not in p:
        raise ValueError("CASE NOTES anchor not found in prompt")
    p = p.replace(PROMPT_ANCHOR, PROMPT_ANCHOR + "\n\n" + PROMPT_ADDITION_TIERS + "\n")
    node["parameters"]["options"]["systemMessage"] = p
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["staging", "prod"], required=True)
    args = ap.parse_args()
    DSN = dict(host="172.18.0.3", port=5432, dbname="n8n", user="n8n", password="n8npassword") if args.target == "prod" else dict(host="127.0.0.1", port=5433, dbname="n8n", user="n8n", password="n8npassword")
    print(f"  target={args.target}")

    conn = psycopg2.connect(**DSN); cur = conn.cursor()
    cur.execute("SELECT id, nodes::jsonb FROM workflow_entity WHERE name=%s", (WF_NAME,))
    wf_id, nodes = cur.fetchone()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snap = f"/root/landtek/snapshots/leos_workflow_pre_104_{args.target}_{ts}.json"
    with open(snap, "w") as f:
        json.dump({"id": wf_id, "nodes": nodes}, f, indent=2)
    print(f"  ✓ snapshot: {snap}")

    if patch_node_sql(nodes, "Fetch Chat Notes", FETCH_CHAT_NOTES_SQL):
        print("  ✓ Fetch Chat Notes: now filters by provenance + returns level")
    if patch_node_sql(nodes, "Fetch Case Assets", FETCH_ASSETS_SQL):
        print("  ✓ Fetch Case Assets: now filters by provenance + returns level")

    cb = next((n for n in nodes if n["name"] == "Context Builder"), None)
    if cb and patch_context_builder(cb):
        print("  ✓ Context Builder: tags entries [V]/[C]/[I]/[U] inline")

    aia = next((n for n in nodes if n["name"] == "AI Agent"), None)
    if aia and patch_prompt(aia):
        print("  ✓ AI Agent prompt: tier discipline + hallucination guard")

    cur.close(); conn.close()
    if args.target == "prod":
        from deploy_helpers import patch_workflow_dual
        patch_workflow_dual(wf_id, nodes=nodes)
    else:
        conn = psycopg2.connect(**DSN); cur = conn.cursor()
        cur.execute('UPDATE workflow_entity SET nodes=%s::jsonb, "updatedAt"=now() WHERE id=%s', (json.dumps(nodes), wf_id))
        cur.execute("""UPDATE workflow_history SET nodes=%s::json WHERE "workflowId"=%s AND "createdAt"=(SELECT MAX("createdAt") FROM workflow_history WHERE "workflowId"=%s)""", (json.dumps(nodes), wf_id, wf_id))
        cur.execute('UPDATE workflow_entity SET active=false WHERE id=%s', (wf_id,))
        conn.commit(); time.sleep(2)
        cur.execute('UPDATE workflow_entity SET active=true WHERE id=%s', (wf_id,))
        conn.commit(); cur.close(); conn.close()
        print("  ✓ staging done")


if __name__ == "__main__":
    main()
