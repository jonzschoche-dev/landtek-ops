#!/usr/bin/env python3
"""doc_classification — Canonical doc classification path (consolidated 2026-05-21).

Single source of truth for the Haiku-based doc classifier. Used by:
  - migrations/apply_deploy_244_doc_classification.py  (batch backfill CLI)
  - tg_dispatcher.handle_uploaded_image                (inline per-upload triage)

Both paths produce rows in the same doc_classification_proposals table so the
existing review + auto-apply infrastructure (deploy_250) works for both batch
and inline classifications.

Consolidation per Landtek mandate:
  - Reads client config from case_theories._clients (no hardcoded MWK lists).
  - Writes to doc_classification_proposals (no parallel schemas).
  - Per-client onboarding via the registry; the prompt adapts.
  - Multi-agent-safe (idempotent upsert; supersedes prior 'proposed' rows).

Pre-consolidation: there were TWO classifiers — apply_deploy_244 wrote to
doc_classification_proposals; doc_classifier.py (now removed) wrote into
tg_inquiry_queue.notes JSON. The fork caused duplicate per-doc Haiku calls
and made the auto-apply runner blind to Telegram uploads.
"""
import json
import os
import re
import sys

sys.path.insert(0, "/root/landtek")
from case_theories._clients import get as get_client


# ──────────────────────────────────────────────────────────────────────────
# Prompt construction (lifted from apply_deploy_244, kept verbatim so the
# batch and inline paths produce comparable proposals).
# ──────────────────────────────────────────────────────────────────────────

def build_prompt(client_config, matter_rows):
    """Build a system prompt that lists valid matters + rules for this client."""
    matter_lines = []
    for mr in matter_rows:
        desc = mr.get("title") or mr.get("description") or mr.get("matter_type") or ""
        mc = mr["matter_code"] if isinstance(mr, dict) else mr[0]
        matter_lines.append(f"  {mc:<25s}  {desc[:80]}")
    matters_text = "\n".join(matter_lines)

    cv_map = client_config.get("civil_case_mappings") or {}
    cv_lines = "\n".join(f"  CV {k} -> {v}" for k, v in cv_map.items())

    arta_prefix = client_config.get("arta_ctn_prefix_to_matter", "")
    ghost = ", ".join(client_config.get("ghost_titles", []))
    op_root = client_config.get("operative_root", "")

    MWK_CHAIN_TITLES = (
        "T-4497 (mother), T-32916, T-32917, T-31298, T-38838, T-47655, "
        "T-47656, T-47657, T-48335, T-48336, T-49037, T-49060, T-49061, "
        "T-49062, T-52354, T-52536, T-52537, T-52538, T-52539, T-52540, "
        "T-079-2021002127 (Balane defendant title, 2021 from cancelled T-52540)"
    )
    MWK_NOT_IN_CHAIN = "T-30683 (Manguisoc Mercedes — SEPARATE property), T-4494 (Cabanbanan San Vicente — SEPARATE)"

    return f"""You are classifying a Philippine legal document for the {client_config['label']} client (client_id={client_config['client_id']}).

VALID MATTERS for {client_config['client_id']} (proposed_matter_code MUST be one of these or null):
{matters_text}

CIVIL CASE MAPPINGS:
{cv_lines or "  (none)"}

ARTA CTN RULE: CTN-SL-YYYY-NNNN-NNNN suffix → matter_code = "{arta_prefix}<4-digit suffix>".

TITLE CHAIN (operative root = {op_root}; ghost = {ghost}):
  IN CHAIN (these titles ARE part of {client_config['client_id']}'s case):
    {MWK_CHAIN_TITLES}
  NOT IN CHAIN (do NOT classify these as MWK chain — they are separate properties):
    {MWK_NOT_IN_CHAIN}

A doc about an IN-CHAIN title that doesn't tie to a specific litigation matter
should be action="assign_matter" with matter_code="MWK-TCT4497" (chain-verification matter)
OR "MWK-ESTATE" (estate-broad), whichever fits better.

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


# ──────────────────────────────────────────────────────────────────────────
# Single-doc classification (used by both batch CLI and inline upload path).
# ──────────────────────────────────────────────────────────────────────────

def classify_doc(client, system_prompt, doc_id, filename, text):
    """One Haiku call. Returns parsed JSON dict or None on failure."""
    from llm_billing import anthropic_call
    user_msg = f"DOC #{doc_id}\nFilename: {filename or '(none)'}\n\nText (first 5000 chars):\n{(text or '')[:5000]}"
    msg = anthropic_call(
        client,
        called_from="doc_classification",
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


def fetch_matters(cur, client_config):
    cur.execute("""
        SELECT matter_code, matter_type, title, description
          FROM matters
         WHERE matter_code LIKE %s
         ORDER BY matter_code
    """, (client_config["matter_prefix"] + "%",))
    return cur.fetchall()


def upsert_proposal(cur, doc_id, current, proposal, client_id):
    """Insert a 'proposed' row; supersede any prior 'proposed' for the same doc.
    Returns the new proposal_id."""
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
        RETURNING id
    """, (
        doc_id,
        current.get("case_file") if isinstance(current, dict) else None,
        current.get("matter_code") if isinstance(current, dict) else None,
        proposal.get("case_file"),
        proposal.get("matter_code"),
        proposal["action"],
        float(proposal.get("confidence", 0)),
        proposal.get("reasoning"),
        (proposal.get("source_quote") or "")[:500],
        client_id,
    ))
    row = cur.fetchone()
    return row[0] if not isinstance(row, dict) else row["id"]


# ──────────────────────────────────────────────────────────────────────────
# Inline upload entry point (consumed by tg_dispatcher.handle_uploaded_image).
# ──────────────────────────────────────────────────────────────────────────

def classify_doc_inline(anthropic_client, cur, doc_id, filename, text,
                         current_case_file=None, current_matter_code=None,
                         client_id="MWK"):
    """Classify a single doc and persist the proposal. Returns
    {proposal_id, proposed_action, proposed_matter_code, proposed_case_file,
     confidence, reasoning, source_quote} — or None on failure."""
    client_config = get_client(client_id)
    if not client_config:
        return None
    matters = fetch_matters(cur, client_config)
    system_prompt = build_prompt(client_config, matters)
    proposal = classify_doc(anthropic_client, system_prompt, doc_id, filename, text)
    if not proposal or "action" not in proposal:
        return None
    if proposal["action"] not in ("assign_matter", "reclassify_case_file",
                                    "flag_unrelated", "keep_unscoped"):
        return None
    current = {"case_file": current_case_file, "matter_code": current_matter_code}
    proposal_id = upsert_proposal(cur, doc_id, current, proposal, client_id)
    return {
        "proposal_id": proposal_id,
        "proposed_action": proposal["action"],
        "proposed_matter_code": proposal.get("matter_code"),
        "proposed_case_file": proposal.get("case_file"),
        "confidence": float(proposal.get("confidence", 0)),
        "reasoning": proposal.get("reasoning", ""),
        "source_quote": (proposal.get("source_quote") or "")[:500],
    }


# ──────────────────────────────────────────────────────────────────────────
# Proposal application (used by Telegram /confirm reply handler).
# ──────────────────────────────────────────────────────────────────────────

def apply_proposal(cur, proposal_id, applied_by="telegram_confirm",
                    override_matter_code=None):
    """Apply a proposal: set documents.matter_code (and case_file if reclassify),
    flip status='applied'. If override_matter_code provided, use it instead of
    the proposal's proposed_matter_code (operator correction case).

    Returns (doc_id, applied_matter_code) or (None, None) if proposal not found.
    """
    cur.execute("""
        SELECT id, doc_id, proposed_matter_code, proposed_case_file,
               proposed_action, current_matter_code, current_case_file
          FROM doc_classification_proposals
         WHERE id = %s
    """, (proposal_id,))
    row = cur.fetchone()
    if not row:
        return None, None
    doc_id = row["doc_id"] if isinstance(row, dict) else row[1]
    applied_matter = override_matter_code or (
        row["proposed_matter_code"] if isinstance(row, dict) else row[2])
    applied_case_file = row["proposed_case_file"] if isinstance(row, dict) else row[3]
    action = row["proposed_action"] if isinstance(row, dict) else row[4]

    if applied_matter:
        cur.execute("UPDATE documents SET matter_code = %s WHERE id = %s",
                    (applied_matter, doc_id))
    if action == "reclassify_case_file" and applied_case_file:
        cur.execute("UPDATE documents SET case_file = %s WHERE id = %s",
                    (applied_case_file, doc_id))
    cur.execute("""
        UPDATE doc_classification_proposals
           SET status = 'applied',
               reviewed_at = now(),
               reviewed_by = %s,
               proposed_matter_code = COALESCE(%s, proposed_matter_code),
               review_notes = CASE WHEN %s IS NOT NULL
                                   THEN 'operator override via telegram'
                                   ELSE review_notes END
         WHERE id = %s
    """, (applied_by, override_matter_code, override_matter_code, proposal_id))
    return doc_id, applied_matter


def reject_proposal(cur, proposal_id, rejected_by="telegram_skip"):
    """Mark a proposal as rejected (e.g. operator typed /skip)."""
    cur.execute("""
        UPDATE doc_classification_proposals
           SET status = 'rejected',
               reviewed_at = now(),
               reviewed_by = %s
         WHERE id = %s
    """, (rejected_by, proposal_id))
