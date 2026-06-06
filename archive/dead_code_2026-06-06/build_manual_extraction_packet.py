#!/usr/bin/env python3
"""Build the manual-extraction PDF packet for Jonathan.

Generates a PDF Jonathan can use to manually extract Tier-1 case-critical docs
(Titles, Deeds, SPAs/POAs, Affidavits for MWK-001 / Civil Case 26-360) using his
standalone Gemini account. The PDF contains: cover, per-type canonical schemas,
manifest tables, and a missing-file roster.

Schemas are versioned in extraction_contract so manual output flows straight
into the same pipeline as automated extraction.
"""
import json
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Preformatted, KeepTogether,
)

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
OUT = f"/root/landtek/drafts/manual_extraction_packet_{datetime.now().strftime('%Y-%m-%d')}.pdf"

# ──────────────────────────────────────────────────────────────────────────────
# CANONICAL SCHEMAS — same standard as tct_v3_canonical (status objects + quotes)
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_TCT = {
    "version": "tct_v3_canonical",
    "doc_classes": "TCT | OCT",
    "summary": "Already canonical and proven on 76 prior extractions. Source-of-truth schema lives at /root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt.",
    "fields": None,  # use existing canonical file
}

SCHEMA_DEED = {
    "version": "deed_v1_canonical",
    "doc_classes": "Deed of Absolute Sale | Deed of Conditional Sale | Deed of Donation | Deed of Quitclaim | Deed of Assignment | Extrajudicial Settlement",
    "fields": {
        "doc_class": "one of: DEED_OF_ABSOLUTE_SALE | DEED_OF_CONDITIONAL_SALE | DEED_OF_DONATION | DEED_OF_QUITCLAIM | DEED_OF_ASSIGNMENT | EXTRAJUDICIAL_SETTLEMENT | OTHER_DEED",
        "instrument_date": "{field_status, value: YYYY-MM-DD, source_quote, page_ref}",
        "consideration": {
            "amount_php": "{field_status, value: number (no commas), source_quote}",
            "amount_in_words": "{field_status, value: 'TWO MILLION PESOS', source_quote}",
            "payment_terms": "{field_status, value: 'paid in cash at signing'|'installment'|..., source_quote}",
        },
        "vendors_or_donors": "[{full_legal_name, civil_status, citizenship, complete_address, capacity: 'own_behalf'|'attorney_in_fact_for_X', authority_basis: 'SPA dated YYYY-MM-DD'|null, authority_instrument_ref, source_quote}]",
        "vendees_or_donees": "[same shape as vendors]",
        "subject_property": {
            "title_number": "{field_status, value: 'T-XXXX', source_quote}",
            "lot_and_plan": "{field_status, value: 'Lot 2-X-6, Psd-XXXX', source_quote}",
            "area_sqm": "{field_status, value: number, source_quote}",
            "location": {"barangay": "...", "municipality": "...", "province": "..."},
            "technical_description": "{field_status, value: full bearings+distances if present, source_quote}",
        },
        "terms_and_conditions": "[{clause_number, verbatim_text, source_quote}]",
        "notary_block": {
            "doc_no": "...", "page": "...", "book": "...", "series_year": "YYYY",
            "notary_name": "...", "notary_place": "...",
            "notary_commission_serial": "...", "notary_commission_expiry": "YYYY-MM-DD",
            "acknowledgment_quote": "BEFORE ME personally appeared...",
            "seal_visible": "bool", "signature_present": "bool",
            "source_quote": "Doc. No. ___; Page No. ___; Book No. ___; Series of ___",
        },
        "witnesses": "[{name, address, signature_present: bool}]",
        "registration_info": {
            "registered_with_rd": "bool",
            "pe_number": "PE-XXX or null",
            "date_presented": "YYYY-MM-DD",
            "registry_office": "...",
            "source_quote": "...",
        },
        "physical_condition": {"overall": "good|fair|poor", "torn_sections": "[]", "notes": "..."},
        "fraud_indicators": "[{type: 'erasure|alteration|overwriting|different_ink|inconsistent_handwriting|marginal_note|torn_section|unusual_stamp', location, description, source_quote, severity, confidence}]",
        "all_persons_mentioned": "[]",
        "all_dates_mentioned": "[]",
        "all_amounts_mentioned": "[]",
        "all_reference_numbers": "[]",
        "full_raw_text": "every word visible in reading order",
        "completeness_score": "0.0-1.0",
        "secondary_review_needed": "bool",
        "secondary_review_reason": "...",
    },
}

SCHEMA_SPA = {
    "version": "spa_v1_canonical",
    "doc_classes": "Special Power of Attorney | General Power of Attorney | Revocation of SPA | Substitution of Attorney-in-Fact",
    "fields": {
        "doc_class": "SPA | GPA | REVOCATION_OF_SPA | SUBSTITUTION | OTHER",
        "instrument_date": "{field_status, value: YYYY-MM-DD, source_quote}",
        "principal": {
            "full_legal_name": "{field_status, value, source_quote}",
            "civil_status": "...",
            "citizenship": "...",
            "complete_address": "...",
            "passport_or_id": "if foreign or stated",
            "source_quote": "...",
        },
        "attorney_in_fact": {
            "full_legal_name": "...",
            "relationship_to_principal": "spouse|child|sibling|niece/nephew|attorney|none|...",
            "complete_address": "...",
            "source_quote": "...",
        },
        "scope_of_authority": "[{power_clause_number, verbatim_text, source_quote}] — every specific power granted, verbatim",
        "subject_property": {
            "title_number": "{field_status, value, source_quote}",
            "lot_and_plan": "...",
            "area_sqm": "...",
            "location": {"barangay": "...", "municipality": "...", "province": "..."},
        },
        "effective_date": "{field_status, value: YYYY-MM-DD, source_quote}",
        "expiry_or_termination": {
            "stated_expiry": "{field_status, value: YYYY-MM-DD or 'no expiry stated', source_quote}",
            "termination_conditions": "[verbatim conditions if any]",
        },
        "is_revocation": "bool — true if this doc REVOKES an earlier SPA",
        "revocation_details": {
            "revokes_spa_dated": "YYYY-MM-DD",
            "revokes_spa_executed_by": "...",
            "revocation_grounds": "...",
            "source_quote": "...",
        },
        "executed_at_location": "...",
        "consularization_or_apostille": {
            "executed_abroad": "bool",
            "apostille_certificate": "if applicable",
            "consul_notary_details": "...",
            "source_quote": "...",
        },
        "notary_block": "same shape as deed_v1_canonical.notary_block",
        "witnesses": "[{name, address, signature_present: bool}]",
        "physical_condition": "...",
        "fraud_indicators": "[]",
        "full_raw_text": "every word visible in reading order",
        "completeness_score": "0.0-1.0",
        "secondary_review_needed": "bool",
        "secondary_review_reason": "...",
    },
    "case_critical_note": "For Civil Case 26-360: any SPA executed by Mary Worrick Keesey or her heirs is potentially the SPA-allegedly-revoked-in-2005 that Cesar de la Fuente cited in the 2016 Deed. Flag any such doc with secondary_review_needed=true.",
}

SCHEMA_AFFIDAVIT = {
    "version": "affidavit_v1_canonical",
    "doc_classes": "Judicial Affidavit | Affidavit of Loss | Affidavit of Heirship | Affidavit of Adverse Claim | Affidavit-Complaint | Sworn Statement | Counter-Affidavit",
    "fields": {
        "doc_class": "JUDICIAL_AFFIDAVIT | AFFIDAVIT_OF_LOSS | AFFIDAVIT_OF_HEIRSHIP | AFFIDAVIT_OF_ADVERSE_CLAIM | AFFIDAVIT_COMPLAINT | SWORN_STATEMENT | COUNTER_AFFIDAVIT | OTHER_AFFIDAVIT",
        "affiant": {
            "full_legal_name": "{field_status, value, source_quote}",
            "age": "...",
            "civil_status": "...",
            "citizenship": "...",
            "complete_address": "...",
            "capacity_or_relationship_to_case": "plaintiff|defendant|witness|heir|representative|...",
            "id_presented": "passport/driver's license/etc. — if cited in jurat",
            "source_quote": "...",
        },
        "subject_matter": "{field_status, value: one-sentence summary of what is being attested to, source_quote}",
        "narrative_paragraphs": "[{paragraph_number, verbatim_text, key_facts_asserted: [], source_quote}] — full numbered paragraphs as written",
        "key_assertions": "[{assertion: 'Cesar de la Fuente is dead', supporting_paragraphs: [3,5], source_quote: 'Patay na po'}] — the punchlines, distilled",
        "named_persons": "[{name, role_in_narrative, source_quote}]",
        "named_documents": "[{document_description, date_if_given, role_in_narrative, source_quote}]",
        "named_dates_and_events": "[{date: YYYY-MM-DD, event_description, source_quote}]",
        "date_of_execution": "{field_status, value: YYYY-MM-DD, source_quote}",
        "place_of_execution": "...",
        "jurat_block": {
            "subscribed_and_sworn_date": "YYYY-MM-DD",
            "subscribed_before_notary_name": "...",
            "notary_doc_no": "...", "notary_page": "...", "notary_book": "...", "notary_series_year": "...",
            "notary_commission_serial": "...",
            "id_verified_quote": "...",
            "seal_visible": "bool", "signature_present": "bool",
            "source_quote": "SUBSCRIBED AND SWORN to before me this ___ day of ___...",
        },
        "is_judicial_affidavit": "bool",
        "judicial_affidavit_fields": {
            "case_number": "Civil Case No. 26-360, etc.",
            "court": "...",
            "case_title": "...",
            "for_party": "plaintiff|defendant",
            "qa_format": "bool — true if structured as Q1/S1, Q2/S2",
            "questions_and_answers": "[{q_number, question_verbatim, answer_verbatim, source_quote}]",
        },
        "attached_exhibits": "[{exhibit_label: 'Annex A', description, source_quote}]",
        "physical_condition": "...",
        "fraud_indicators": "[]",
        "full_raw_text": "every word visible in reading order",
        "completeness_score": "0.0-1.0",
        "secondary_review_needed": "bool",
        "secondary_review_reason": "...",
    },
    "case_critical_note": "For Civil Case 26-360: testimony about Cesar's death date, SPA revocation, signature genuineness, or possession of the contested lots is load-bearing. Extract Filipino-language testimony verbatim — do not translate.",
}

GEMINI_PROMPT_PREFIX = """You are reading a Philippine legal document. This is a forensic legal-evidence extraction for a Philippine property law case (Civil Case No. 26-360 Zschoche v. Balane, accion reinvindicatoria).

Extract EVERY fact that could matter for legal contestation, fraud detection, or evidence retrieval. The extraction runs ONCE — be exhaustive.

OUTPUT: valid JSON only — no markdown fences, no prose before or after.

EVERY field is a STATUS OBJECT in this shape:
  {"field_status": "extracted"|"not_present"|"illegible"|"partial"|"requires_heightened_ocr",
   "value": <the value>,
   "source_quote": "<verbatim text from the document>",
   "page_ref": "<page number / location on doc>"}

CRITICAL RULES:
1. NEVER guess. If a field is not on the document, return field_status="not_present".
2. EVERY extracted value MUST carry a verbatim source_quote from the document.
3. If a section is present but unreadable, return field_status="illegible" with a reason.
4. Filipino-language text is valid — extract verbatim, do not translate.
5. For names: capture EXACTLY as written (including middle initials, suffixes, spelling variants).
6. For dates: convert to YYYY-MM-DD in the value, but include the verbatim original in source_quote.
7. For amounts: capture as number in PHP in value, verbatim text (with currency notation) in source_quote.

SCHEMA:
"""

# ──────────────────────────────────────────────────────────────────────────────
# DATA PULL
# ──────────────────────────────────────────────────────────────────────────────

def fetch_manifest():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, classification, smart_filename, drive_file_id, execution_status
          FROM documents
         WHERE case_file = 'MWK-001'
           AND id NOT IN (SELECT DISTINCT doc_id FROM extraction_chunks)
           AND classification IN (
               'Title (TCT/OCT)','Title','Title (TCT)',
               'Deed','Affidavit',
               'Special Power of Attorney','Power of Attorney'
           )
         ORDER BY classification, id
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def bucketize(rows):
    """Group rows by extraction tier. Each tier = (label, schema_key, doc_rows)."""
    buckets = {
        "Title (TCT/OCT)": [],
        "Deed": [],
        "Special Power of Attorney": [],
        "Power of Attorney": [],
        "Affidavit": [],
    }
    no_drive = []
    title_unqualified = []
    for r in rows:
        cls = r["classification"]
        if cls in ("Title", "Title (TCT)") and not r["drive_file_id"]:
            title_unqualified.append(r)
            continue
        if cls == "Title (TCT)":
            # treat as Title (TCT/OCT)
            cls_norm = "Title (TCT/OCT)"
        else:
            cls_norm = cls
        if not r["drive_file_id"]:
            no_drive.append(r)
            continue
        if cls_norm in buckets:
            buckets[cls_norm].append(r)
    return buckets, no_drive, title_unqualified


# ──────────────────────────────────────────────────────────────────────────────
# PDF GENERATION
# ──────────────────────────────────────────────────────────────────────────────

def build_pdf(out_path):
    rows = fetch_manifest()
    buckets, no_drive, title_unqualified = bucketize(rows)

    doc = SimpleDocTemplate(
        out_path, pagesize=LETTER,
        topMargin=0.6*inch, bottomMargin=0.6*inch,
        leftMargin=0.6*inch, rightMargin=0.6*inch,
        title="Manual Extraction Packet — MWK-001 Tier 1",
        author="LandTek / Claude (auto-generated)",
    )
    styles = getSampleStyleSheet()
    H1 = styles["Heading1"]
    H2 = styles["Heading2"]
    H3 = styles["Heading3"]
    BODY = styles["BodyText"]
    SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, leading=10)
    CODE = ParagraphStyle("code", parent=BODY, fontName="Courier", fontSize=7.5, leading=9)
    LABEL = ParagraphStyle("label", parent=BODY, fontName="Helvetica-Bold", fontSize=10, leading=12, textColor=colors.HexColor("#1a3a6e"))

    story = []

    # ─── COVER ─────────────────────────────────────────────────────────────
    story.append(Paragraph("MANUAL EXTRACTION PACKET", H1))
    story.append(Paragraph("Tier 1 — Civil Case 26-360 Title-Chain Evidence", H2))
    story.append(Spacer(1, 0.15*inch))
    cover_facts = [
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M UTC")],
        ["Case file", "MWK-001 / Civil Case No. 26-360 (Zschoche v. Balane)"],
        ["Workflow", "Jonathan extracts manually via standalone Gemini → JSON output → DB insert → truth-negotiator validates 10% sample"],
        ["Scope", f"{sum(len(v) for v in buckets.values())} extractable docs across 4 doc types, all with Drive file access"],
        ["Schemas", "tct_v3_canonical (proven) + deed_v1_canonical + spa_v1_canonical + affidavit_v1_canonical (new)"],
        ["Order", "Recommended: Titles → Deeds → SPAs/POAs → Affidavits (same schema batched together preserves Gemini context)"],
    ]
    tbl = Table(cover_facts, colWidths=[1.4*inch, 5.4*inch])
    tbl.setStyle(TableStyle([
        ("FONT", (0,0), (0,-1), "Helvetica-Bold", 9),
        ("FONT", (1,0), (1,-1), "Helvetica", 9),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0,0), (0,-1), colors.HexColor("#f0f4fa")),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tbl)

    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("Per-type counts", H3))
    counts = []
    counts.append(["Doc Type", "Extractable", "Schema"])
    for label, schema_key in [
        ("Title (TCT/OCT)", "tct_v3_canonical"),
        ("Deed", "deed_v1_canonical"),
        ("Special Power of Attorney", "spa_v1_canonical"),
        ("Power of Attorney", "spa_v1_canonical"),
        ("Affidavit", "affidavit_v1_canonical"),
    ]:
        counts.append([label, str(len(buckets[label])), schema_key])
    counts.append(["", "", ""])
    counts.append(["Total extractable (with Drive file)", str(sum(len(v) for v in buckets.values())), ""])
    counts.append(["Docs missing Drive file (locate first)", str(len(no_drive) + len(title_unqualified)), ""])
    t = Table(counts, colWidths=[2.6*inch, 1.3*inch, 2.9*inch])
    t.setStyle(TableStyle([
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 9),
        ("FONT", (0,1), (-1,-1), "Helvetica", 9),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1a3a6e")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
        ("FONT", (0,-2), (-1,-1), "Helvetica-Bold", 9),
        ("BACKGROUND", (0,-1), (-1,-1), colors.HexColor("#fff5e6")),
    ]))
    story.append(t)

    story.append(Spacer(1, 0.25*inch))
    story.append(Paragraph("How to use this packet", H3))
    instructions = [
        "1. Pick a section. Do ALL docs of one type before switching — schema stays loaded in Gemini's context, quality stays high.",
        "2. Copy the section's Gemini prompt (verbatim) into your standalone Gemini chat.",
        "3. Upload ONE doc at a time. Paste the prompt before each upload if the session is long.",
        "4. Gemini returns JSON. Save each output as <code>/root/landtek/manual_extracts/&lt;doc_id&gt;.json</code> on the VPS (or paste back to Claude here).",
        "5. After each batch, Claude runs <code>truth_negotiator</code> on a 10% random sample to validate. Anomalies flagged for your eye.",
        "6. Once a batch passes validation, Claude ingests it as extraction_chunks (provenance_level = inferred_strong; promoted to <i>verified</i> only after source-quote SQL check passes).",
        "7. Check off completed docs on the manifest table (or tell Claude the doc_id range you finished).",
    ]
    for s in instructions:
        story.append(Paragraph(s, BODY))
        story.append(Spacer(1, 0.05*inch))

    story.append(PageBreak())

    # ─── PER-TYPE SECTIONS ──────────────────────────────────────────────────
    sections = [
        ("Title (TCT/OCT)", "tct_v3_canonical", SCHEMA_TCT),
        ("Deed", "deed_v1_canonical", SCHEMA_DEED),
        ("Special Power of Attorney", "spa_v1_canonical", SCHEMA_SPA),
        ("Power of Attorney", "spa_v1_canonical", SCHEMA_SPA),  # reuse SPA schema
        ("Affidavit", "affidavit_v1_canonical", SCHEMA_AFFIDAVIT),
    ]
    seen_schemas = set()
    for label, schema_key, schema in sections:
        docs = buckets[label]
        story.append(Paragraph(f"§ {label}", H1))
        story.append(Paragraph(f"<b>{len(docs)}</b> documents to extract  ·  Schema: <font face='Courier'>{schema_key}</font>", BODY))
        story.append(Spacer(1, 0.1*inch))

        # Schema (don't repeat if already shown — POA reuses SPA)
        if schema_key not in seen_schemas:
            seen_schemas.add(schema_key)
            story.append(Paragraph("Schema", H3))
            if schema_key == "tct_v3_canonical":
                with open("/root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt") as f:
                    tct_prompt = f.read()
                # Show only the schema portion (everything after "SCHEMA (")
                idx = tct_prompt.find("SCHEMA")
                snippet = tct_prompt[idx:] if idx >= 0 else tct_prompt
                story.append(Preformatted(snippet[:6000], CODE))
                story.append(Paragraph("<i>Full schema continues at /root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt</i>", SMALL))
            else:
                story.append(Preformatted(json.dumps(schema["fields"], indent=2), CODE))
                if "case_critical_note" in schema:
                    story.append(Spacer(1, 0.08*inch))
                    story.append(Paragraph(f"<b>Case-critical note:</b> {schema['case_critical_note']}", BODY))

            story.append(Spacer(1, 0.15*inch))
            story.append(Paragraph("Gemini prompt — copy this into your Gemini chat verbatim", H3))
            full_prompt = GEMINI_PROMPT_PREFIX + json.dumps(schema["fields"] if schema_key != "tct_v3_canonical" else "(see /root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt)", indent=2)
            story.append(Preformatted(full_prompt[:4500], CODE))

        # Manifest table
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(f"Manifest — {len(docs)} docs", H3))
        if not docs:
            story.append(Paragraph("<i>(no extractable docs in this bucket)</i>", BODY))
        else:
            manifest = [["☐", "doc_id", "filename", "drive_file_id", "exec_status"]]
            for r in docs:
                fname = (r["smart_filename"] or "")[:55]
                drive = (r["drive_file_id"] or "")[:18] + ("…" if r["drive_file_id"] and len(r["drive_file_id"]) > 18 else "")
                est = (r["execution_status"] or "?")[:12]
                manifest.append(["☐", str(r["id"]), fname, drive, est])
            t = Table(manifest, colWidths=[0.3*inch, 0.55*inch, 3.6*inch, 1.5*inch, 1.0*inch], repeatRows=1)
            t.setStyle(TableStyle([
                ("FONT", (0,0), (-1,0), "Helvetica-Bold", 8),
                ("FONT", (0,1), (-1,-1), "Helvetica", 7.5),
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1a3a6e")),
                ("TEXTCOLOR", (0,0), (-1,0), colors.white),
                ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#f7f9fc")]),
                ("LEFTPADDING", (0,0), (-1,-1), 3),
                ("RIGHTPADDING", (0,0), (-1,-1), 3),
                ("TOPPADDING", (0,0), (-1,-1), 2),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ]))
            story.append(t)

        story.append(PageBreak())

    # ─── MISSING-FILE ROSTER ────────────────────────────────────────────────
    story.append(Paragraph("Appendix — Docs without accessible Drive file", H1))
    story.append(Paragraph(
        "These documents are in the DB but have no <code>drive_file_id</code>. They cannot be extracted "
        "until the PDF is located (Drive, email attachment, or physical scan). Listed here so they "
        "aren't forgotten.", BODY))
    story.append(Spacer(1, 0.15*inch))
    missing_all = no_drive + title_unqualified
    if missing_all:
        rows_m = [["doc_id", "classification", "filename"]]
        for r in missing_all:
            rows_m.append([str(r["id"]), r["classification"] or "?", (r["smart_filename"] or "")[:75]])
        tm = Table(rows_m, colWidths=[0.6*inch, 1.7*inch, 4.7*inch], repeatRows=1)
        tm.setStyle(TableStyle([
            ("FONT", (0,0), (-1,0), "Helvetica-Bold", 8),
            ("FONT", (0,1), (-1,-1), "Helvetica", 7.5),
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#8b0000")),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("GRID", (0,0), (-1,-1), 0.25, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fff5f5")]),
        ]))
        story.append(tm)
    else:
        story.append(Paragraph("<i>(none — all extractable docs have Drive files)</i>", BODY))

    doc.build(story)
    print(f"PDF written to {out_path}")
    return out_path


def register_schemas_in_db():
    """Insert the three new canonical schemas into extraction_contract so they're versioned."""
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    for schema_key, fields, notes in [
        ("deed_v1_canonical", SCHEMA_DEED["fields"], "v1 CANONICAL Deed schema — applies to all conveyance instruments (sale, donation, quitclaim, assignment, EJS). Status objects per field, source_quote mandatory. Built for manual + automated extraction parity."),
        ("spa_v1_canonical", SCHEMA_SPA["fields"], "v1 CANONICAL SPA/POA schema — handles SPAs, GPAs, revocations, substitutions. Critical for Civil Case 26-360: tracks the SPA revoked in 2005 that Cesar cited in 2016 Deed."),
        ("affidavit_v1_canonical", SCHEMA_AFFIDAVIT["fields"], "v1 CANONICAL Affidavit schema — judicial affidavits, sworn statements, affidavits of loss/heirship/adverse claim. Extracts Q&A format for judicial affidavits; Filipino testimony preserved verbatim."),
    ]:
        cur.execute("""
            INSERT INTO extraction_contract (version, doc_class, required_fields, optional_fields, validation_rules, notes)
            VALUES (%s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (version) DO UPDATE
              SET required_fields = EXCLUDED.required_fields,
                  validation_rules = EXCLUDED.validation_rules,
                  notes = EXCLUDED.notes
        """, (
            schema_key,
            "Deed" if "deed" in schema_key else ("SPA" if "spa" in schema_key else "Affidavit"),
            json.dumps(list(fields.keys())),
            json.dumps([]),
            json.dumps({
                "field_status_enum": ["extracted", "not_present", "illegible", "partial", "requires_heightened_ocr"],
                "every_extracted_field_must_carry_source_quote": True,
                "must_emit_full_raw_text": True,
            }),
            notes,
        ))
    cur.close(); conn.close()
    print("Schemas registered in extraction_contract.")


if __name__ == "__main__":
    register_schemas_in_db()
    build_pdf(OUT)
