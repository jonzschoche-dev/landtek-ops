#!/usr/bin/env python3
"""Deploy 244 — LLM doc classification proposals (PROPOSALS ONLY, no auto-apply).

Problem: 740 MWK-001-or-orphan docs have no matter_code, plus 21 misclassified
docs are causing resolution noise (Inocalla, Torralba CA petitions sitting in
MWK-001 wrongly). Regex (deploy_234) hit a ceiling; need light LLM triage.

Approach: ask Haiku to read each unclassified doc + a list of valid matters
(per client) and propose:
  - matter_code (or null)
  - case_file_correction (or null — flag if doc seems to belong to a different client)
  - action: assign_matter | reclassify_case_file | flag_unrelated | keep_unscoped
  - confidence (0..1)
  - reasoning (1-2 sentences with quoted span)

Output goes to doc_classification_proposals — REVIEWED, not auto-applied.

Cost: ~$0.30-$0.80 for Haiku across ~740 docs. Logged via llm_billing.

Usage:
  python3 migrations/apply_deploy_244_doc_classification.py --schema-only
  python3 migrations/apply_deploy_244_doc_classification.py --client MWK --limit 20
  python3 migrations/apply_deploy_244_doc_classification.py --client MWK --apply
"""
import argparse
import json
import os
import re
import sys

import anthropic
import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get, all_ids
from llm_billing import anthropic_call

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doc_classification_proposals (
    id                    SERIAL PRIMARY KEY,
    doc_id                INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    current_case_file     TEXT,
    current_matter_code   TEXT,
    proposed_case_file    TEXT,
    proposed_matter_code  TEXT,
    proposed_action       TEXT NOT NULL CHECK (proposed_action IN
                              ('assign_matter','reclassify_case_file','flag_unrelated','keep_unscoped')),
    confidence            NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    reasoning             TEXT,
    source_quote          TEXT,
    model                 TEXT NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
    client_id             TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'proposed'
                            CHECK (status IN ('proposed','approved','rejected','applied','superseded')),
    reviewed_at           TIMESTAMPTZ,
    reviewed_by           TEXT,
    review_notes          TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, status) DEFERRABLE INITIALLY DEFERRED
);
CREATE INDEX IF NOT EXISTS idx_doc_class_status ON doc_classification_proposals(status);
CREATE INDEX IF NOT EXISTS idx_doc_class_action ON doc_classification_proposals(proposed_action);
CREATE INDEX IF NOT EXISTS idx_doc_class_doc ON doc_classification_proposals(doc_id);
"""


def build_prompt(client_config, matter_rows):
    """Build a system prompt that lists valid matters + rules for this client."""
    matter_lines = []
    for mr in matter_rows:
        desc = mr.get("matter_caption") or mr.get("matter_type") or ""
        matter_lines.append(f"  {mr['matter_code']:<25s}  {desc[:80]}")
    matters_text = "\n".join(matter_lines)

    cv_map = client_config.get("civil_case_mappings") or {}
    cv_lines = "\n".join(f"  CV {k} -> {v}" for k, v in cv_map.items())

    arta_prefix = client_config.get("arta_ctn_prefix_to_matter", "")
    ghost = ", ".join(client_config.get("ghost_titles", []))
    op_root = client_config.get("operative_root", "")

    return f"""You are classifying a Philippine legal document for the {client_config['label']} client (client_id={client_config['client_id']}).

VALID MATTERS for {client_config['client_id']}:
{matters_text}

CIVIL CASE MAPPINGS:
{cv_lines or "  (none)"}

ARTA CTN RULE: CTN-SL-YYYY-NNNN-NNNN suffix → matter_code = "{arta_prefix}<4-digit suffix>".
TITLE CHAIN: operative root = {op_root}; ghost titles = {ghost}.

CLIENT'S CORE FACTS:
- Plaintiff/heir: Patricia Keesey Zschoche (heir of Mary Worrick Keesey)
- Adversary: Cesar de la Fuente (deceased 2017), Gloria Balane, Engr. Erwin Balane
- Counsel for client: Atty. Bonifacio Jr. Barandon (Barandon Law Offices, Daet)
- Mother title: TCT T-4497 (parent T-111, ghost OCT T-106)
- Properties: Brgy 3 Daet, San Roque, Mercedes-area subdivisions
- Forum: RTC Daet Branch (Civil Case 26-360), ARTA, RD Camarines Norte, CSC, OP

Read the document text and decide:

1. If the document IS about this client AND references one of the valid matters,
   set action="assign_matter" and proposed_matter_code=<that code>.

2. If the document mentions parties/places/titles that are NOT this client's
   (e.g., Inocalla family in Manila, Torralba & Juntilla v. Daet RTC criminal
   case, Paracale-specific names), set action="flag_unrelated" and
   proposed_case_file=<best guess like "Paracale-001" or null>.

3. If the document IS about this client but doesn't tie to a specific matter
   (e.g., a 1996 estate-broad Sanggunian resolution), set action="keep_unscoped"
   and proposed_matter_code=null.

4. If the document's current case_file is wrong but you can identify the correct
   one (e.g., a doc tagged MWK-001 that's actually an Inocalla family case),
   set action="reclassify_case_file" and proposed_case_file=<correct value>.

Output JSON ONLY (no markdown, no prose):
{{"action": "assign_matter|reclassify_case_file|flag_unrelated|keep_unscoped",
  "matter_code": "MWK-... or null",
  "case_file": "MWK-001|Paracale-001|null",
  "confidence": 0.0-1.0,
  "reasoning": "1-2 sentences",
  "source_quote": "<short verbatim from doc text>"}}"""


def classify_doc(client, system_prompt, doc_id, filename, text):
    """One Haiku call. Returns parsed JSON or None."""
    user_msg = f"DOC #{doc_id}\nFilename: {filename or '(none)'}\n\nText (first 5000 chars):\n{(text or '')[:5000]}"
    msg = anthropic_call(
        client,
        called_from="doc_classifier",
        purpose="classify_for_matter",
        case_file="MWK-001",
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    out = msg.content[0].text.strip()
    out = re.sub(r"^```(?:json)?\s*|\s*```$", "", out)
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def fetch_unclassified_docs(cur, client_config, limit=None):
    """Pull docs that have no matter_code AND are either this client's case_file
    OR have no case_file at all (orphan candidates)."""
    sql = """
        SELECT id, smart_filename, case_file, matter_code, extracted_text
          FROM documents
         WHERE matter_code IS NULL
           AND (case_file = %s OR case_file IS NULL)
           AND COALESCE(LENGTH(extracted_text), 0) > 100
         ORDER BY id
    """
    params = [client_config["case_file"]]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    return cur.fetchall()


def fetch_matters(cur, client_config):
    cur.execute("""
        SELECT matter_code, matter_type, matter_caption
          FROM matters
         WHERE matter_code LIKE %s
         ORDER BY matter_code
    """, (client_config["matter_prefix"] + "%",))
    return cur.fetchall()


def upsert_proposal(cur, doc_id, current, proposal, client_id):
    """Insert a 'proposed' row; if one already exists with status='proposed',
    supersede it."""
    cur.execute("""
        UPDATE doc_classification_proposals
           SET status = 'superseded'
         WHERE doc_id = %s AND status = 'proposed'
    """, (doc_id,))
    cur.execute("""
        INSERT INTO doc_classification_proposals
            (doc_id, current_case_file, current_matter_code,
             proposed_case_file, proposed_matter_code, proposed_action,
             confidence, reasoning, source_quote, client_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        doc_id,
        current["case_file"],
        current["matter_code"],
        proposal.get("case_file"),
        proposal.get("matter_code"),
        proposal["action"],
        float(proposal.get("confidence", 0)),
        proposal.get("reasoning"),
        (proposal.get("source_quote") or "")[:500],
        client_id,
    ))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="MWK")
    ap.add_argument("--schema-only", action="store_true", help="Just create the table; don't run LLM")
    ap.add_argument("--limit", type=int, default=None, help="Cap docs processed (testing)")
    ap.add_argument("--apply", action="store_true",
                    help="Actually call Haiku + write proposals (without this, dry-run only)")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(f"Deploy 244 — doc classification proposals ({args.client})")
    print("=" * 60)

    # Always ensure schema exists
    cur.execute(SCHEMA_SQL)
    print("  ✓ doc_classification_proposals schema ensured")

    if args.schema_only:
        return

    client_config = get(args.client)
    matters = fetch_matters(cur, client_config)
    print(f"  {len(matters)} valid matters for {args.client}")

    docs = fetch_unclassified_docs(cur, client_config, limit=args.limit)
    print(f"  {len(docs)} unclassified docs to triage")

    if not args.apply:
        print("\n  (dry-run: not calling LLM. Pass --apply to actually classify.)")
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # fallback: try to load from .env
        envp = "/root/landtek/.env"
        if os.path.exists(envp):
            for line in open(envp):
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not api_key:
        print("  ✗ ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    client = anthropic.Anthropic(api_key=api_key)

    sys_prompt = build_prompt(client_config, matters)

    n_ok = 0
    n_fail = 0
    by_action = {}
    for d in docs:
        try:
            proposal = classify_doc(client, sys_prompt, d["id"], d["smart_filename"], d["extracted_text"])
        except Exception as e:
            print(f"    doc#{d['id']:>4d}  ✗ {type(e).__name__}: {e}")
            n_fail += 1
            continue
        if not proposal or "action" not in proposal:
            n_fail += 1
            print(f"    doc#{d['id']:>4d}  ✗ unparseable")
            continue
        action = proposal["action"]
        if action not in ("assign_matter","reclassify_case_file","flag_unrelated","keep_unscoped"):
            n_fail += 1
            print(f"    doc#{d['id']:>4d}  ✗ bad action: {action!r}")
            continue
        upsert_proposal(cur, d["id"], d, proposal, args.client)
        n_ok += 1
        by_action[action] = by_action.get(action, 0) + 1
        if n_ok % 25 == 0:
            print(f"    ...{n_ok}/{len(docs)} classified")

    print(f"\n  ✓ {n_ok} proposals written, {n_fail} failures")
    print("  By action:")
    for a, n in sorted(by_action.items(), key=lambda x: -x[1]):
        print(f"    {a:<22s}  {n}")
    print("\n  Review with: SELECT * FROM doc_classification_proposals WHERE status='proposed';")
    print("  Apply with:   scripts/review_doc_classification.py (TODO in follow-up deploy)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
