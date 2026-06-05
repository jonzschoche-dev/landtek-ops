#!/usr/bin/env python3
"""leo_improvement_proposer.py — Opus drafts patches to make Leo smarter (deploy_305).

Every N hours (cron):
  1. Group last 24h of sim failures by fail_reason pattern.
  2. For the top K patterns (by run count), pull a sample of failing probes:
       - probe name
       - prompt text
       - expected substrings
       - forbidden substrings
       - Leo's actual reply (so Opus sees what went wrong)
  3. Fetch Leo's current AI Agent systemMessage.
  4. Call Opus with a structured prompt asking for a SPECIFIC patch
     (system_prompt_add or system_prompt_replace) that would fix the pattern,
     constrained to:
       - touching only the systemMessage,
       - including a JSON patch_payload that the apply script can execute,
       - declaring expected_impact in terms of which target probes will pass,
       - estimating the affected probe set.
  5. INSERT each proposal into leo_improvement_proposals (status='pending').
  6. Compute baseline_pass_rate for each proposal's target probes from last
     24h data and store it.
  7. Push a Telegram digest of the top 3 pending proposals to Jonathan.

Once a proposal is in the table, Jonathan reviews + applies via:
    python3 scripts/leo_proposal_apply.py <id>
After 30+ min, verify with:
    python3 scripts/leo_proposal_verify.py <id>
"""
from __future__ import annotations
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
from report_publisher import push_strict

DSN          = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
WORKFLOW_ID  = "vSDQv1vfn6627bnA"
JONATHAN     = "6513067717"
OPUS_MODEL   = "claude-opus-4-5-20251101"
OPUS_URL     = "https://api.anthropic.com/v1/messages"
OPUS_VER     = "2023-06-01"
OPUS_MAX_OUT = 8000

TOP_K_PATTERNS = 3        # how many fail patterns to address per run
PROBES_PER_PATTERN = 4    # how many sample probes per pattern fed to Opus


def fetch_leo_system_prompt(cur) -> str:
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    for n in nodes:
        if n.get("name") == "AI Agent":
            return (n.get("parameters", {})
                     .get("options", {})
                     .get("systemMessage", ""))
    return ""


def fail_pattern_key(reason: str) -> str:
    """Bucket fail_reason strings into pattern keys.
    Examples:
      "missing expected: ['allan', 'paracale', 'inocalla']" → "missing:authorized_user_recall"
      "contained forbidden: ['don qi']"                      → "forbidden:hallucinated_name"
      "no reply text captured"                               → "infra:no_reply"
    """
    r = (reason or "").lower()
    if "no reply text captured" in r:
        return "infra:no_reply"
    if "missing expected" in r:
        # First missing token as a coarse key.
        m = re.search(r"missing expected:\s*\['([^']+)'", r)
        if m:
            tok = m.group(1)
            if any(name in tok for name in ("allan","kristyle","datu","inocalla","paracale")):
                return "missing:authorized_user_recall"
            if any(name in tok for name in ("mwk","worrick","keesey")):
                return "missing:mwk_recall"
            if "not recognized" in r or "not authorized" in r:
                return "missing:unauth_phrasing"
            if any(t in tok for t in ("inferred","verified","provenance")):
                return "missing:provenance_marker"
            if any(t in tok for t in ("query_documents","cross_reference","cannot send")):
                return "missing:tool_call_or_honest_refusal"
            if "may" in tok or "june" in tok or "deadline" in tok:
                return "missing:deadline_recall"
        return "missing:other"
    if "contained forbidden" in r:
        return "forbidden:hallucination_or_leak"
    return f"other:{r[:30]}"


def gather_failure_buckets(cur, window: str = "24 hours"):
    cur.execute(f"""
        SELECT p.name, p.severity, p.definition, s.prompt_text, s.leo_reply_text,
               s.fail_reason, s.posted_at
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE s.passed = false
           AND s.posted_at > now() - interval '{window}'
         ORDER BY s.id DESC
    """)
    buckets = {}
    for r in cur.fetchall():
        key = fail_pattern_key(r["fail_reason"] or "")
        buckets.setdefault(key, []).append(r)
    return buckets


def baseline_pass_rate(cur, target_probes: list[str]) -> float | None:
    if not target_probes:
        return None
    cur.execute("""
        SELECT
          COUNT(*)::float AS total,
          COUNT(*) FILTER (WHERE passed)::float AS passes
          FROM leo_qa_sim_payloads s
          JOIN leo_qa_probes p ON p.id = s.probe_id
         WHERE p.name = ANY(%s)
           AND s.posted_at > now() - interval '24 hours'
    """, (target_probes,))
    r = cur.fetchone()
    if not r or not r["total"]:
        return None
    return round(r["passes"] / r["total"], 4)


def call_opus(system_text: str, user_text: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = json.dumps({
        "model": OPUS_MODEL,
        "max_tokens": OPUS_MAX_OUT,
        "system": system_text,
        "messages": [{"role": "user", "content": user_text}],
    }).encode()
    req = urllib.request.Request(
        OPUS_URL, data=body,
        headers={"x-api-key": api_key, "anthropic-version": OPUS_VER,
                 "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read())
    chunks = [c["text"] for c in payload.get("content", []) if c.get("type") == "text"]
    text = "\n".join(chunks).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def build_proposal_prompt(pattern_key: str, samples: list[dict],
                          current_system_prompt: str) -> str:
    sample_block = "\n\n".join(
        f"--- probe {i+1}: {s['name']}  (severity={s['severity']}) ---\n"
        f"PROMPT (what sim asked Leo):\n  {s['prompt_text']!r}\n"
        f"EXPECTED (what reply MUST contain):\n  {json.dumps(s['definition'].get('expected_substrings', []))}\n"
        f"FORBIDDEN (must NOT contain):\n  {json.dumps(s['definition'].get('forbidden_substrings', []))}\n"
        f"ACTUAL REPLY:\n  {(s['leo_reply_text'] or '(empty)')[:600]!r}\n"
        f"FAIL REASON: {s['fail_reason']!r}"
        for i, s in enumerate(samples)
    )
    return f"""You are proposing a precise patch to Leo's AI Agent system prompt
to fix a SPECIFIC, REPEATING failure pattern.

== FAILURE PATTERN KEY ==
{pattern_key}

== {len(samples)} REPRESENTATIVE FAILING PROBES ==

{sample_block}

== LEO'S CURRENT AI AGENT SYSTEM PROMPT (the thing you may patch) ==
{current_system_prompt[:24_000]}

== RULES FOR YOUR OUTPUT ==
1. Return STRICT JSON, a single object — no commentary, no code fences.
2. Fields:
   "failure_pattern"   — short label restating the pattern in plain words
   "target_probes"     — JSON array of probe names from above this patch should fix
   "patch_kind"        — exactly one of: "system_prompt_add" | "system_prompt_replace"
   "patch_target"      — null for now (system prompt is the only target this version)
   "patch_payload"     — object describing the edit:
       if patch_kind == "system_prompt_add":
         {{"append_text": "<the exact text to append to the systemMessage>"}}
       if patch_kind == "system_prompt_replace":
         {{"find_text": "<exact substring currently in the systemMessage>",
           "replace_text": "<replacement>"}}
   "patch_diff"        — a human-readable preview of the change, ≤ 1500 chars
   "rationale"         — 2-4 sentences explaining the root cause + why this patch fixes it
   "expected_impact"   — "should make N probes (names) start passing"
3. CONSTRAINTS:
   - The patch MUST be minimal and surgical. No more than ~30 lines of new text.
   - If patch_kind is "system_prompt_replace", find_text MUST exist verbatim in the
     current system prompt. Verify before emitting.
   - Don't break existing rules. Append new rules; replace only when fixing a wrong rule.
   - The patch must address the ROOT CAUSE, not just suppress symptoms.
   - If you cannot devise a high-confidence patch, return:
       {{"failure_pattern": "{pattern_key}",
         "patch_kind": "system_prompt_add",
         "patch_payload": {{"append_text": ""}},
         "patch_diff": "",
         "rationale": "No high-confidence patch identified.",
         "target_probes": [],
         "expected_impact": ""}}
4. Output ONLY the JSON object.
"""


def parse_proposal(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
    required = {"failure_pattern","target_probes","patch_kind",
                "patch_payload","patch_diff","rationale"}
    if not required.issubset(obj.keys()):
        return None
    if obj["patch_kind"] not in ("system_prompt_add", "system_prompt_replace"):
        return None
    if not isinstance(obj["target_probes"], list):
        return None
    if not isinstance(obj["patch_payload"], dict):
        return None
    # No-op proposals (empty append_text or empty find_text) are silently dropped.
    payload = obj["patch_payload"]
    if obj["patch_kind"] == "system_prompt_add":
        if not (payload.get("append_text") or "").strip():
            return None
    else:
        if not (payload.get("find_text") or "").strip():
            return None
    return obj


def insert_proposal(cur, prop: dict, baseline: float | None) -> int:
    cur.execute("""
        INSERT INTO leo_improvement_proposals
          (failure_pattern, target_probes, patch_kind, patch_target,
           patch_diff, patch_payload, rationale, expected_impact,
           baseline_pass_rate)
        VALUES (%s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s, %s)
        RETURNING id
    """, (
        prop["failure_pattern"],
        json.dumps(prop["target_probes"]),
        prop["patch_kind"],
        prop.get("patch_target"),
        prop["patch_diff"][:8000],
        json.dumps(prop["patch_payload"]),
        prop["rationale"],
        prop.get("expected_impact", ""),
        baseline,
    ))
    return cur.fetchone()["id"]


def telegram_digest(cur, top_n: int = 3):
    cur.execute(f"""
        SELECT id, failure_pattern, target_probes, rationale, expected_impact,
               baseline_pass_rate
          FROM leo_improvement_proposals
         WHERE status = 'pending'
         ORDER BY proposed_at DESC LIMIT {top_n}
    """)
    rows = cur.fetchall()
    if not rows:
        return 0
    n = len(rows)
    headline = f"✨ {n} new Opus proposal(s) for Leo — review queue"
    report = ["## Pending Leo Improvement Proposals", ""]
    for r in rows:
        baseline = (f"{int(100*r['baseline_pass_rate'])}%" if r['baseline_pass_rate'] is not None else "?")
        tgt_count = len(r['target_probes'] or [])
        report.append(f"### Proposal #{r['id']}")
        report.append(f"**Pattern**: {r['failure_pattern']}")
        report.append(f"**Baseline pass rate**: {baseline} (over {tgt_count} probes)")
        report.append(f"**Rationale**: {r['rationale']}")
        if r.get('expected_impact'):
            report.append(f"**Expected impact**: {r['expected_impact']}")
        report.append("")
        report.append("```bash")
        report.append(f"python3 scripts/leo_proposal_apply.py {r['id']} --dry  # preview")
        report.append(f"python3 scripts/leo_proposal_apply.py {r['id']}        # apply")
        report.append("```")
        report.append("")
    push_strict(
        headline=headline,
        body_md="
".join(report),
        source="watchdog",
        slug="leo-proposals-pending",
    )
    return n


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    buckets = gather_failure_buckets(cur, "24 hours")
    if not buckets:
        print("[proposer] no failures in 24h — nothing to propose", flush=True)
        return

    ordered = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)
    leo_prompt = fetch_leo_system_prompt(cur)
    if not leo_prompt:
        print("[proposer] could not read Leo's system prompt — aborting", flush=True)
        sys.exit(2)

    system_text = (
        "You are a precise, minimal-touch reviewer of an AI agent's system prompt. "
        "You output ONLY valid JSON. You propose surgical edits that fix the demonstrated "
        "failure WITHOUT breaking the agent's existing guarantees."
    )

    inserted = 0
    for pattern_key, samples in ordered[:TOP_K_PATTERNS]:
        # Dedupe by probe name; take up to PROBES_PER_PATTERN distinct probes.
        seen = set(); picked = []
        for s in samples:
            if s["name"] in seen: continue
            seen.add(s["name"]); picked.append(s)
            if len(picked) >= PROBES_PER_PATTERN: break

        prompt = build_proposal_prompt(pattern_key, picked, leo_prompt)
        try:
            raw = call_opus(system_text, prompt)
        except Exception as e:
            print(f"[proposer] Opus call failed for {pattern_key}: {e}", flush=True)
            continue
        prop = parse_proposal(raw)
        if not prop:
            print(f"[proposer] no usable proposal for {pattern_key}", flush=True)
            continue

        # Sanity-check find_text exists if replace
        if prop["patch_kind"] == "system_prompt_replace":
            if prop["patch_payload"]["find_text"] not in leo_prompt:
                print(f"[proposer] proposal {pattern_key} find_text not in prompt — skipping",
                      flush=True)
                continue

        baseline = baseline_pass_rate(cur, prop["target_probes"])
        pid = insert_proposal(cur, prop, baseline)
        inserted += 1
        print(f"[proposer] inserted proposal #{pid}  pattern={pattern_key}  "
              f"baseline={baseline}", flush=True)

    if inserted:
        n = telegram_digest(cur, top_n=min(3, inserted))
        print(f"[proposer] pushed digest to Jonathan ({n} proposals)", flush=True)
    else:
        print("[proposer] no proposals generated this run", flush=True)
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
