#!/usr/bin/env python3
"""
LeoLandTek Rich Metadata Ingestion Pipeline
Phase 1: Smart section-based chunking + full metadata for Qdrant

This replaces flat 400-word chunking with logical legal document sections
and attaches the rich metadata schema requested.

Usage:
    python leo_rich_metadata_ingestion.py --demo
    # or
    python leo_rich_metadata_ingestion.py /path/to/court_filing.pdf

Output: List of Qdrant-ready point payloads (vector embedding step added later)
"""

import pdfplumber
import re
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
import argparse
from datetime import datetime

# ============================================================
# 1. RICH METADATA EXTRACTION (Philippine Court Documents)
# ============================================================

def extract_rich_metadata(text: str, filename: str = "") -> Dict[str, Any]:
    """
    Extract structured metadata from Philippine legal documents.
    Covers RTC, CA, Supreme Court filings for property/land cases.
    """
    metadata = {
        "case_file": "",
        "document_type": "Court Filing",
        "document_date": "",
        "parties": [],
        "reference_numbers": [],
        "court": "",
        "chunk_section": "",
        "strategic_relevance": "",
        "source_file": Path(filename).name if filename else "unknown",
        "ingested_at": datetime.now().isoformat(),
        "jurisdiction": "Philippines"
    }

    text_lower = text.lower()

    # --- Case / Reference Number (CV-2026-360 style, G.R. No., etc.) ---
    ref_patterns = [
        r'(?i)(CV|SP|CA|G\.R\.|LRC|MC|AM)[- ]?(\d{4}[-]?\d+)',
        r'(?i)case no\.?\s*[:\-]?\s*([A-Z0-9\-]+)',
        r'(?i)docket no\.?\s*[:\-]?\s*([A-Z0-9\-]+)'
    ]
    for pattern in ref_patterns:
        match = re.search(pattern, text)
        if match:
            ref = match.group(0).strip()
            if ref not in metadata["reference_numbers"]:
                metadata["reference_numbers"].append(ref)
            if not metadata["case_file"]:
                metadata["case_file"] = ref
            break

    # --- Court / Branch ---
    court_patterns = [
        r'(?i)(Regional Trial Court|RTC)[^,\n]*Branch\s*\d+',
        r'(?i)(Court of Appeals|CA)[^,\n]*',
        r'(?i)(Supreme Court|SC)[^,\n]*',
        r'(?i)(Metropolitan Trial Court|MeTC|MTCC)[^,\n]*Branch\s*\d+'
    ]
    for pattern in court_patterns:
        match = re.search(pattern, text)
        if match:
            metadata["court"] = match.group(0).strip()
            break

    # --- Document Type (heuristic from content) ---
    if any(kw in text_lower for kw in ["prayer for relief", "wherefore, premises considered", "it is respectfully prayed"]):
        metadata["document_type"] = "Court Filing - Petition / Motion with Prayer"
    elif any(kw in text_lower for kw in ["contract of sale", "deed of absolute sale", "memorandum of agreement"]):
        metadata["document_type"] = "Contract / Deed"
    elif any(kw in text_lower for kw in ["complaint", "petition for review"]):
        metadata["document_type"] = "Complaint / Petition"
    elif "verification" in text_lower and "non-forum shopping" in text_lower:
        metadata["document_type"] = "Verification & Certification"
    elif "annex" in text_lower and ("a" in text_lower or "b" in text_lower):
        metadata["document_type"] = "Annex / Supporting Document"
    else:
        metadata["document_type"] = "Court Filing - General"

    # --- Date (multiple formats common in PH courts) ---
    date_patterns = [
        r'(\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{1,2}/\d{1,2}/\d{4})'
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metadata["document_date"] = match.group(0)
            break

    # --- Parties (Plaintiff v. Defendant / Petitioner v. Respondent) ---
    party_patterns = [
        r'([A-Z][A-Za-z\s\.\,\-]+?)\s+(v\.|versus|vs\.)\s+([A-Z][A-Za-z\s\.\,\-]+)',
        r'(?i)(heirs of [A-Za-z\s]+)',
        r'(?i)(gloria balane|heirs of keesey)'
    ]
    parties_found = set()
    for pattern in party_patterns:
        for match in re.finditer(pattern, text):
            if match.group(1):
                parties_found.add(match.group(1).strip())
            if len(match.groups()) > 2 and match.group(3):
                parties_found.add(match.group(3).strip())
    metadata["parties"] = sorted(list(parties_found))[:6]  # cap at 6

    # --- Strategic Relevance (default based on document type) ---
    if "prayer" in metadata["document_type"].lower():
        metadata["strategic_relevance"] = "Establishes basis for accion reinvindicatoria or specific performance"
    elif "statement of facts" in text_lower or "facts" in metadata.get("chunk_section", "").lower():
        metadata["strategic_relevance"] = "Factual foundation for ownership, possession, and heirship claims"
    elif "contract" in metadata["document_type"].lower():
        metadata["strategic_relevance"] = "Primary evidence of title transfer or lease agreement"
    else:
        metadata["strategic_relevance"] = "Key procedural or substantive document in land dispute"

    return metadata


# ============================================================
# 2. SMART CHUNKING BY LOGICAL LEGAL SECTIONS
# ============================================================

LEGAL_SECTION_MARKERS = [
    ("Caption / Title", r"(?i)^\s*(Republic of the Philippines|In the Matter of|Court of Appeals|Regional Trial Court|Supreme Court)"),
    ("Parties & Caption", r"(?i)^\s*(Petitioner|Respondent|Plaintiff|Defendant|Appellant|Appellee|Heirs of)"),
    ("Statement of Facts / Statement of the Case", r"(?i)^\s*(Statement of (the )?Facts|Statement of the Case|Nature of the Case)"),
    ("Statement of Issues / Assignment of Errors", r"(?i)^\s*(Issues?|Assignment of Errors?|Questions Presented)"),
    ("Arguments / Discussion", r"(?i)^\s*(Arguments?|Discussion|Reasons?)"),
    ("Prayer for Relief", r"(?i)^\s*(PRAYER|Wherefore, premises considered|It is respectfully prayed|RELIEF SOUGHT)"),
    ("Verification", r"(?i)^\s*(VERIFICATION|I, .*after being duly sworn|Verification and Certification)"),
    ("Non-Forum Shopping Certification", r"(?i)^\s*(CERTIFICATION|Non-Forum Shopping|Anti-Forum Shopping)"),
    ("Annexes / Exhibits", r"(?i)^\s*(ANNEX|EXHIBIT|Annex [A-Z]|Exhibit [A-Z])"),
    ("Decision / Resolution", r"(?i)^\s*(DECISION|RESOLUTION|ORDER|Judgment)"),
]

def chunk_by_legal_sections(text: str) -> List[Dict[str, str]]:
    """
    Split document into logical sections instead of fixed word count.
    Prevents splitting mid-clause in contracts or court filings.
    """
    if not text or len(text.strip()) < 50:
        return [{"section": "Full Document", "text": text.strip()}]

    chunks: List[Dict[str, str]] = []
    current_section = "Preamble / Introductory Paragraphs"
    current_text_lines: List[str] = []

    lines = text.splitlines(keepends=True)

    for line in lines:
        matched = False
        for section_name, pattern in LEGAL_SECTION_MARKERS:
            if re.match(pattern, line.strip()):
                # Save previous chunk
                if current_text_lines:
                    chunk_text = "".join(current_text_lines).strip()
                    if len(chunk_text) > 20:  # avoid tiny chunks
                        chunks.append({
                            "section": current_section,
                            "text": chunk_text
                        })
                current_section = section_name
                current_text_lines = [line]
                matched = True
                break

        if not matched:
            current_text_lines.append(line)

    # Final chunk
    if current_text_lines:
        chunk_text = "".join(current_text_lines).strip()
        if len(chunk_text) > 20:
            chunks.append({
                "section": current_section,
                "text": chunk_text
            })

    # If no sections detected, fall back to one big chunk
    if not chunks:
        chunks = [{"section": "Full Document", "text": text.strip()}]

    return chunks


# ============================================================
# 3. QDRANT PAYLOAD PREPARATION
# ============================================================

def prepare_qdrant_payloads(
    chunks: List[Dict[str, str]],
    base_metadata: Dict[str, Any],
    case_id: str = "unknown"
) -> List[Dict[str, Any]]:
    """
    Build Qdrant point payloads with rich metadata + section context.
    Vector embedding is added in the next pipeline stage (n8n or separate service).
    """
    payloads = []

    for idx, chunk in enumerate(chunks):
        payload = base_metadata.copy()
        payload["chunk_section"] = chunk["section"]
        payload["chunk_index"] = idx
        payload["chunk_length_chars"] = len(chunk["text"])
        payload["text"] = chunk["text"]  # the actual content for retrieval

        # Dynamic strategic_relevance per section
        section_lower = chunk["section"].lower()
        if "prayer" in section_lower:
            payload["strategic_relevance"] = (
                "Establishes the exact relief sought (accion reinvindicatoria, "
                "specific performance, or damages) — critical for case theory"
            )
        elif "statement of facts" in section_lower or "facts" in section_lower:
            payload["strategic_relevance"] = (
                "Core factual narrative supporting ownership, heirship, or prior possession"
            )
        elif "verification" in section_lower or "certification" in section_lower:
            payload["strategic_relevance"] = (
                "Procedural compliance document — used to challenge or uphold filing validity"
            )
        elif "annex" in section_lower or "exhibit" in section_lower:
            payload["strategic_relevance"] = (
                "Supporting evidence (titles, tax declarations, surveys) — often decisive in land cases"
            )
        elif "decision" in section_lower or "order" in section_lower:
            payload["strategic_relevance"] = (
                "Court ruling or interlocutory order — binding precedent or res judicata risk"
            )

        # Stable ID for upsert (case + section + index)
        point_id = f"{case_id}-{idx:03d}-{chunk['section'][:20].replace(' ', '_')}"

        payloads.append({
            "id": point_id,
            "payload": payload
            # "vector": [...]  # added by embedding service later
        })

    return payloads


# ============================================================
# 4. MAIN PIPELINE
# ============================================================

def ingest_document(pdf_path: str, case_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Full pipeline for one PDF: extract → chunk → enrich → Qdrant payloads."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"📄 Processing: {path.name}")

    # Extract text
    with pdfplumber.open(path) as pdf:
        full_text = "\n".join(
            page.extract_text() or "" for page in pdf.pages
        )

    # Metadata
    base_meta = extract_rich_metadata(full_text, str(path))
    if case_id:
        base_meta["case_file"] = case_id

    # Smart chunking
    chunks = chunk_by_legal_sections(full_text)
    print(f"   → {len(chunks)} logical sections identified")

    # Qdrant-ready payloads
    payloads = prepare_qdrant_payloads(chunks, base_meta, base_meta.get("case_file", "unknown"))

    return payloads


def demo_with_sample():
    """Demo using a realistic Philippine land case snippet (no external file needed)."""
    sample_text = """
Republic of the Philippines
Regional Trial Court
Branch 64, Quezon City

GLORIA BALANE,
Petitioner,

-versus-

HEIRS OF KEESY, represented by their attorney-in-fact,
Respondents.

CIVIL CASE NO. CV-2026-360

PETITION FOR REVIEW ON CERTIORARI

STATEMENT OF FACTS

1. Petitioner Gloria Balane is the registered owner of a parcel of land...

PRAYER

WHEREFORE, premises considered, it is respectfully prayed that this Honorable Court...

VERIFICATION

I, GLORIA BALANE, after being duly sworn...
"""

    print("🧪 Running DEMO with sample Philippine court filing text\n")

    base_meta = extract_rich_metadata(sample_text, "demo_court_filing.pdf")
    base_meta["case_file"] = "MWK-001"  # match user's example

    chunks = chunk_by_legal_sections(sample_text)
    payloads = prepare_qdrant_payloads(chunks, base_meta, "MWK-001")

    print("=== FIRST PAYLOAD (example of rich metadata) ===\n")
    print(json.dumps(payloads[0]["payload"], indent=2, ensure_ascii=False))

    print(f"\n✅ Total points prepared for Qdrant: {len(payloads)}")
    return payloads


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LeoLandTek Rich Metadata Ingestion")
    parser.add_argument("pdf", nargs="?", help="Path to PDF court document")
    parser.add_argument("--demo", action="store_true", help="Run with built-in sample text")
    parser.add_argument("--case-id", help="Override case file ID (e.g. MWK-001)")
    args = parser.parse_args()

    if args.demo or not args.pdf:
        demo_with_sample()
    else:
        try:
            payloads = ingest_document(args.pdf, args.case_id)
            print(f"\n✅ Prepared {len(payloads)} Qdrant points with rich metadata.")
            print("Next step: send to Qdrant upsert (or n8n workflow).")
            # Example: save to JSON for inspection
            out_file = Path(args.pdf).with_suffix(".qdrant_payloads.json")
            with open(out_file, "w") as f:
                json.dump(payloads, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved to {out_file}")
        except Exception as e:
            print(f"❌ Error: {e}")
            exit(1)
