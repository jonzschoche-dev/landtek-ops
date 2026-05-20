#!/usr/bin/env python3
"""doc_classifier — Haiku tool-call that classifies an uploaded document
into structured fields, given OCR text plus contextual hints (active matters,
recent uploads in the last 15 minutes).

Returns {kind, case_file_guess, matter_code_guess, doc_date, key_fact,
vendor_or_party, amount_php, parties, confidence, needs_human_question}.

Used by tg_dispatcher.handle_uploaded_image to:
  - Set documents.case_file / .classification / .doc_date_norm at insert
    time instead of the old hardcoded 'MWK-001' default.
  - Log client_history canonical-bible event with the right attribution.
  - Generate an educated follow-up question Leo can ask to confirm or
    correct the classification.
"""
import json
import os
import sys

sys.path.insert(0, "/root/landtek")
try:
    with open("/root/landtek/.env") as f:
        for line in f:
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ.setdefault("ANTHROPIC_API_KEY", line.strip().split("=", 1)[1])
except FileNotFoundError:
    pass

from llm_billing import anthropic_tool_call


CLASSIFIER_SYSTEM = """You classify documents uploaded to a Philippine property-litigation operations system.

The operator is Jonathan Zschoche (LandTek Ops). The active clients are:
  - MWK-001 (Patricia Keesey Zschoche estate, US, mother of operator) — Civil Case No. 26-360 vs Gloria Balane et al., plus ARTA-* administrative cases
  - Paracale-001 (Paracale gold mining matters) — PAR-INOCALLA, PAR-CAPACUAN, PAR-GOLDEN-SAND, PAR-* generally
  - Owner (LandTek company operations, expenses not tied to a specific client matter)

Your job: given OCR'd text from one uploaded document, plus a list of currently-active matters and any recent uploads in the last 15 minutes (which may be from the same meeting/batch), classify the document.

Output via the emit_classification tool. Rules:
  - kind: pick the BEST single-label tag. If it's clearly not on the enum list, use 'unknown'.
  - case_file_guess: null if unclear. NEVER guess — being silent ('null') is correct when the doc could be from any client. The operator will tell you.
  - matter_code_guess: only if the doc clearly references a specific matter (e.g. quotes a docket number, mentions a party that's unique to one matter, was uploaded immediately after another doc that was classified to that matter). Null otherwise.
  - doc_date: YYYY-MM-DD if a date is printed on the document. NOT the upload date. Null if no date is visible/parseable.
  - key_fact: one short clause summarizing what this document is/says (≤180 chars). Concrete, not generic.
  - vendor_or_party: the vendor (if receipt), counterparty (if legal doc), sender (if letter/email). Null if unknown.
  - amount_php: amount in pesos if this is a financial document. Null otherwise.
  - parties: array of person/entity names mentioned (≤5 names). Empty array if none.
  - confidence: 0.0-1.0 — how confident you are in case_file_guess + matter_code_guess. Drop below 0.5 if either is null or uncertain.
  - needs_human_question: if you're unsure about something a human would clarify in 5 seconds, write ONE short question (≤120 chars). Empty string if confident.

DO NOT:
  - Invent matter codes that aren't on the active list.
  - Default to MWK-001 when the doc looks like it could be Paracale or general.
  - Treat receipts as MWK by default — Jonathan's recent uploads include heavy Paracale/Inocalla activity.
  - Output structured fields you can't see on the document. Use null."""


CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "receipt", "tct_title", "tax_declaration", "deed", "spa",
                "court_order", "court_filing", "pleading", "letter",
                "email_screenshot", "id_document", "photo_evidence",
                "screenshot_other", "map_or_survey", "contract", "unknown",
            ],
        },
        "case_file_guess": {
            "type": ["string", "null"],
            "description": "MWK-001 / Paracale-001 / Owner / null if unclear",
        },
        "matter_code_guess": {
            "type": ["string", "null"],
            "description": "Specific matter_code from the active list, or null",
        },
        "doc_date": {
            "type": ["string", "null"],
            "description": "YYYY-MM-DD if printed on the doc, else null",
        },
        "key_fact": {
            "type": "string",
            "maxLength": 200,
        },
        "vendor_or_party": {
            "type": ["string", "null"],
            "maxLength": 120,
        },
        "amount_php": {
            "type": ["number", "null"],
            "minimum": 0,
        },
        "parties": {
            "type": "array",
            "items": {"type": "string", "maxLength": 120},
            "maxItems": 5,
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "needs_human_question": {
            "type": "string",
            "maxLength": 150,
        },
    },
    "required": ["kind", "key_fact", "confidence", "needs_human_question"],
}


def classify_document(client, doc_id, ocr_text, active_matters=None, recent_uploads=None):
    """Run the classifier. Returns dict (may have 'error' key if call failed).

    active_matters: list of dicts with keys {matter_code, case_file, title}
    recent_uploads: list of dicts with keys {id, classification, case_file, key_fact}
    """
    matters_block = "(none provided)"
    if active_matters:
        lines = []
        for m in active_matters[:30]:
            mc = m.get("matter_code") if isinstance(m, dict) else m[0]
            cf = m.get("case_file") if isinstance(m, dict) else m[1]
            ti = m.get("title") if isinstance(m, dict) else (m[2] if len(m) > 2 else "")
            lines.append(f"  {mc}  ({cf}): {(ti or '')[:80]}")
        matters_block = "\n".join(lines)

    recent_block = "(none in last 15 min)"
    if recent_uploads:
        lines = []
        for r in recent_uploads[:5]:
            did = r.get("id") if isinstance(r, dict) else r[0]
            cls = r.get("classification") if isinstance(r, dict) else r[1]
            cf = r.get("case_file") if isinstance(r, dict) else r[2]
            kf = r.get("key_fact") if isinstance(r, dict) else (r[3] if len(r) > 3 else "")
            lines.append(f"  doc#{did}  {cls or '?'}  [{cf or '?'}]: {(kf or '')[:100]}")
        recent_block = "\n".join(lines)

    user_msg = (
        f"OCR'd text from upload doc#{doc_id} (truncated to 3000 chars):\n\n"
        f"```\n{(ocr_text or '')[:3000]}\n```\n\n"
        f"Active matters (matter_code, case_file, title):\n{matters_block}\n\n"
        f"Recent uploads in last 15 minutes (batch context):\n{recent_block}\n\n"
        f"Today's date: 2026-05-20.\n\n"
        f"Classify. Be conservative on case_file_guess — null is correct when "
        f"the doc could be from any client."
    )

    try:
        result = anthropic_tool_call(
            client,
            tool_name="emit_classification",
            tool_description="Emit structured classification of an uploaded document.",
            input_schema=CLASSIFICATION_SCHEMA,
            called_from="doc_classifier",
            purpose=f"classify_doc_{doc_id}",
            case_file="MWK-001",
            model="claude-haiku-4-5",
            max_tokens=700,
            system=CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        return result
    except Exception as e:
        return {
            "kind": "unknown",
            "case_file_guess": None,
            "matter_code_guess": None,
            "doc_date": None,
            "key_fact": f"(classifier failed: {str(e)[:120]})",
            "vendor_or_party": None,
            "amount_php": None,
            "parties": [],
            "confidence": 0.0,
            "needs_human_question": "Classifier errored — what is this document?",
            "error": str(e)[:200],
        }


def format_educated_followup(doc_id, classification, case_file_guess,
                              matter_code_guess, key_fact, vendor_or_party,
                              amount_php, doc_date, confidence,
                              needs_human_question):
    """Build the one-message educated follow-up question Leo asks after
    classifying an upload. Returns (composed_html, notes_json_str)."""
    # Compact header
    kind_label = (classification or "unknown").replace("_", " ")
    parts = [f"📷 <b>doc#{doc_id}</b> · {kind_label}"]
    if amount_php:
        parts.append(f"₱{amount_php:,.2f}")
    if doc_date:
        parts.append(doc_date)
    if vendor_or_party:
        parts.append(f"<i>{vendor_or_party[:50]}</i>")
    header = " · ".join(parts)

    body_lines = [header]
    if key_fact:
        body_lines.append(f"<i>{key_fact[:180]}</i>")

    if confidence >= 0.7 and matter_code_guess:
        body_lines.append(
            f"\n<b>Filing to:</b> <code>{matter_code_guess}</code> "
            f"(conf {confidence:.0%}). Reply <code>/confirm</code>, "
            f"a different matter_code, or <code>/skip</code>."
        )
    elif confidence >= 0.5 and case_file_guess:
        body_lines.append(
            f"\n<b>Client:</b> <code>{case_file_guess}</code> "
            f"(conf {confidence:.0%}). Which matter? Reply with a "
            f"matter_code, or <code>/skip</code>."
        )
    elif needs_human_question:
        body_lines.append(f"\n<b>?</b> {needs_human_question}")
    else:
        body_lines.append(
            "\nWhich client + matter? Reply with <code>case_file/matter_code</code> "
            "or <code>/skip</code>."
        )

    composed = "\n".join(body_lines)[:400]
    notes = json.dumps({
        "kind": "doc_classifier",
        "doc_id": doc_id,
        "classification": classification,
        "case_file_guess": case_file_guess,
        "matter_code_guess": matter_code_guess,
        "vendor_or_party": vendor_or_party,
        "amount_php": amount_php,
        "doc_date": doc_date,
        "confidence": confidence,
    })[:2000]
    return composed, notes
