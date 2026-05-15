"""LeoLandTek v4 Pass 1: per-page hybrid OCR + Document AI XML normalizer.

Pipeline per PDF:
  1. PyMuPDF extracts native text + layout per page.
  2. Pages with low alpha-ratio or text length get escalated to Document AI.
  3. Document AI's nested JSON is normalized into PageBlock objects with
     classified types (paragraph / table / list_item / signature_block /
     header / footer).
  4. Cross-page tables are detected and stitched in-place with a
     spans_pages attribute preserved on the merged block.
  5. Pages emit clean XML that Claude reads natively. Unreadable pages
     emit <unreadable/> so downstream passes can't hallucinate about them.
"""
from __future__ import annotations
import os, re, base64, hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import fitz  # PyMuPDF
import requests

from config import (
    DOCAI_URL, GOOGLE_CREDS,
    OCR_MIN_TEXT_LEN, OCR_MIN_ALPHA_RATIO,
    OCR_MIN_CONFIDENCE,
)


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------
@dataclass
class PageBlock:
    block_type: str   # paragraph | table | list_item | signature_block | header | footer
    page_number: int
    text: str
    bbox: Tuple[float, float, float, float]  # normalized 0-1: x0, y0, x1, y1
    confidence: float = 1.0
    table_data: Optional[List[List[str]]] = None
    table_has_header: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class Page:
    page_number: int
    width: float
    height: float
    blocks: List[PageBlock] = field(default_factory=list)
    text: str = ""
    confidence: float = 1.0
    extraction_method: str = ""        # pymupdf | docai
    needs_review: bool = False
    review_reason: str = ""


# ----------------------------------------------------------------------------
# Auth for Document AI
# ----------------------------------------------------------------------------
def _docai_token() -> str:
    import google.auth
    import google.auth.transport.requests
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_CREDS
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


# ----------------------------------------------------------------------------
# Block classification heuristics (used by both PyMuPDF and DocAI paths)
# ----------------------------------------------------------------------------
_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")
_DATE_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b")
_SIGNED_PATTERN = re.compile(r"(?i)\b(signed|signature|by\s*[:\-]|/s/|s/d|sgd\.)\b")
_LIST_PATTERN = re.compile(r"^\s*([•\-\*·]|\(?\d{1,3}\)?[\.\)]\s|[a-zA-Z]\)\s|\([a-zA-Z]\)\s)")


def _looks_like_signature(text: str, y0: float, y1: float) -> bool:
    if y0 < 0.45:
        return False
    if len(text) > 250 or len(text) < 5:
        return False
    has_signed = bool(_SIGNED_PATTERN.search(text))
    has_name_date = bool(_NAME_PATTERN.search(text)) and bool(_DATE_PATTERN.search(text))
    return has_signed or (has_name_date and y0 > 0.55)


def _looks_like_list_item(text: str) -> bool:
    return bool(_LIST_PATTERN.match(text))


def _classify_block(text: str, y0: float, y1: float) -> str:
    if y1 < 0.10:
        return "header"
    if y0 > 0.92:
        return "footer"
    if _looks_like_signature(text, y0, y1):
        return "signature_block"
    if _looks_like_list_item(text):
        return "list_item"
    return "paragraph"


def _is_readable(text: str) -> bool:
    if len(text) < OCR_MIN_TEXT_LEN:
        return False
    alpha = sum(1 for c in text if c.isalpha())
    return alpha / max(len(text), 1) >= OCR_MIN_ALPHA_RATIO


# ----------------------------------------------------------------------------
# PyMuPDF extraction
# ----------------------------------------------------------------------------
def extract_pymupdf(pdf_path: str) -> List[Page]:
    pages: List[Page] = []
    doc = fitz.open(pdf_path)
    try:
        for i, fitz_page in enumerate(doc):
            rect = fitz_page.rect
            page = Page(
                page_number=i + 1,
                width=rect.width,
                height=rect.height,
                extraction_method="pymupdf",
            )
            page.text = fitz_page.get_text("text") or ""
            structured = fitz_page.get_text("dict") or {"blocks": []}
            for block in structured.get("blocks", []):
                if block.get("type", 0) != 0:  # 0 = text block
                    continue
                line_texts = []
                for line in block.get("lines", []):
                    parts = [span.get("text", "") for span in line.get("spans", [])]
                    line_texts.append("".join(parts))
                block_text = "\n".join(t for t in line_texts if t).strip()
                if not block_text:
                    continue
                bbox = block.get("bbox", [0, 0, 0, 0])
                w, h = max(rect.width, 1), max(rect.height, 1)
                nx0, ny0, nx1, ny1 = bbox[0]/w, bbox[1]/h, bbox[2]/w, bbox[3]/h
                btype = _classify_block(block_text, ny0, ny1)
                page.blocks.append(PageBlock(
                    block_type=btype,
                    page_number=i + 1,
                    text=block_text,
                    bbox=(nx0, ny0, nx1, ny1),
                ))
            page.blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
            pages.append(page)
    finally:
        doc.close()
    return pages


# ----------------------------------------------------------------------------
# Document AI extraction + JSON normalizer
# ----------------------------------------------------------------------------
def _docai_text_from_layout(full_text: str, layout: dict) -> str:
    if not layout:
        return ""
    segments = (layout.get("textAnchor", {}) or {}).get("textSegments", []) or []
    out = []
    for seg in segments:
        s = int(seg.get("startIndex", 0) or 0)
        e = int(seg.get("endIndex", 0) or 0)
        out.append(full_text[s:e])
    return "".join(out)


def _docai_normalized_bbox(layout: dict) -> Tuple[float, float, float, float]:
    if not layout:
        return (0.0, 0.0, 0.0, 0.0)
    poly = layout.get("boundingPoly", {}) or {}
    verts = poly.get("normalizedVertices") or poly.get("vertices") or []
    if not verts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [float(v.get("x", 0) or 0) for v in verts]
    ys = [float(v.get("y", 0) or 0) for v in verts]
    return (min(xs), min(ys), max(xs), max(ys))


def _docai_extract_table(full_text: str, table: dict) -> Tuple[List[List[str]], bool]:
    rows: List[List[str]] = []
    has_header = False
    for header_row in table.get("headerRows", []) or []:
        has_header = True
        rows.append([
            _docai_text_from_layout(full_text, c.get("layout", {})).strip()
            for c in header_row.get("cells", []) or []
        ])
    for body_row in table.get("bodyRows", []) or []:
        rows.append([
            _docai_text_from_layout(full_text, c.get("layout", {})).strip()
            for c in body_row.get("cells", []) or []
        ])
    return rows, has_header


def _table_to_markdown(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    width = len(header)
    def fmt_row(r):
        r = (r + [""] * width)[:width]
        return "| " + " | ".join(c.replace("\n", " ").replace("|", "/") for c in r) + " |"
    lines = [fmt_row(header), "|" + "|".join(["---"] * width) + "|"]
    for row in rows[1:]:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def extract_docai(pdf_path: str) -> List[Page]:
    with open(pdf_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()
    token = _docai_token()
    r = requests.post(
        DOCAI_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "rawDocument": {"content": content, "mimeType": "application/pdf"},
        },
        timeout=300,
    )
    r.raise_for_status()
    doc = r.json().get("document", {}) or {}
    full_text = doc.get("text", "") or ""
    pages: List[Page] = []
    for i, p in enumerate(doc.get("pages", []) or []):
        dim = p.get("dimension", {}) or {}
        page = Page(
            page_number=i + 1,
            width=float(dim.get("width", 0) or 0),
            height=float(dim.get("height", 0) or 0),
            extraction_method="docai",
        )
        for para in p.get("paragraphs", []) or []:
            text = _docai_text_from_layout(full_text, para.get("layout", {})).strip()
            if not text:
                continue
            bbox = _docai_normalized_bbox(para.get("layout", {}))
            conf = float((para.get("layout", {}) or {}).get("confidence", 1.0) or 1.0)
            btype = _classify_block(text, bbox[1], bbox[3])
            page.blocks.append(PageBlock(
                block_type=btype, page_number=i + 1, text=text,
                bbox=bbox, confidence=conf,
            ))
        for tbl in p.get("tables", []) or []:
            table_data, has_header = _docai_extract_table(full_text, tbl)
            if not table_data:
                continue
            bbox = _docai_normalized_bbox(tbl.get("layout", {}))
            conf = float((tbl.get("layout", {}) or {}).get("confidence", 1.0) or 1.0)
            page.blocks.append(PageBlock(
                block_type="table", page_number=i + 1,
                text=_table_to_markdown(table_data),
                bbox=bbox, confidence=conf,
                table_data=table_data, table_has_header=has_header,
            ))
        # Sort top-to-bottom, then left-to-right
        page.blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
        # Page-level confidence = mean block confidence
        if page.blocks:
            page.confidence = sum(b.confidence for b in page.blocks) / len(page.blocks)
        page.text = "\n\n".join(b.text for b in page.blocks)
        pages.append(page)
    return pages


# ----------------------------------------------------------------------------
# Hybrid extraction (the entrypoint)
# ----------------------------------------------------------------------------
def extract_hybrid(pdf_path: str) -> List[Page]:
    pm_pages = extract_pymupdf(pdf_path)
    need_ocr_idxs = [i for i, p in enumerate(pm_pages) if not _is_readable(p.text)]
    if not need_ocr_idxs:
        return pm_pages
    try:
        ocr_pages = extract_docai(pdf_path)
    except Exception as e:
        for i in need_ocr_idxs:
            pm_pages[i].needs_review = True
            pm_pages[i].review_reason = f"docai_error:{type(e).__name__}:{str(e)[:120]}"
            pm_pages[i].text = ""
            pm_pages[i].blocks = []
        return pm_pages
    for i in need_ocr_idxs:
        if i < len(ocr_pages):
            ocr_p = ocr_pages[i]
            if ocr_p.confidence < OCR_MIN_CONFIDENCE:
                ocr_p.needs_review = True
                ocr_p.review_reason = f"low_ocr_confidence_{ocr_p.confidence:.2f}"
            pm_pages[i] = ocr_p
        else:
            pm_pages[i].needs_review = True
            pm_pages[i].review_reason = "docai_returned_fewer_pages"
            pm_pages[i].text = ""
            pm_pages[i].blocks = []
    return pm_pages


# ----------------------------------------------------------------------------
# Cross-page table stitching
# ----------------------------------------------------------------------------
def stitch_cross_page_tables(pages: List[Page]) -> List[Page]:
    """Merge tables that visibly continue from one page to the next.

    Heuristic: previous page's last block is a table whose bottom_y > 0.85,
    and the next page's first block is a table whose top_y < 0.15 with the
    same column count and no header row. Merged in place; spans_pages
    metadata records the originating page range.
    """
    if len(pages) < 2:
        return pages
    out = pages
    for i in range(len(out) - 1):
        cur = out[i]
        nxt = out[i + 1]
        if not cur.blocks or not nxt.blocks:
            continue
        last = cur.blocks[-1]
        first = nxt.blocks[0]
        if last.block_type != "table" or first.block_type != "table":
            continue
        if last.bbox[3] < 0.85 or first.bbox[1] > 0.15:
            continue
        if not last.table_data or not first.table_data:
            continue
        cur_cols = len(last.table_data[0]) if last.table_data else 0
        nxt_cols = len(first.table_data[0]) if first.table_data else 0
        if cur_cols != nxt_cols or first.table_has_header:
            # Don't stitch automatically — flag as suspected continuation
            first.metadata["continuation_suspected"] = True
            first.metadata["prev_table_page"] = last.page_number
            continue
        # Stitch
        merged = last.table_data + first.table_data
        last.table_data = merged
        last.text = _table_to_markdown(merged)
        spans = last.metadata.get("spans_pages") or [last.page_number]
        spans.append(first.page_number)
        last.metadata["spans_pages"] = sorted(set(spans))
        # Remove the duplicate from next page
        nxt.blocks = nxt.blocks[1:]
    return out


# ----------------------------------------------------------------------------
# XML normalization
# ----------------------------------------------------------------------------
def _xml_path_for_block(page_num: int, body_index: int, btype: str) -> str:
    return f"page[{page_num}]/body/{btype}[{body_index}]"


def normalize_to_xml(pdf_path: str, pages: List[Page]) -> str:
    filename = Path(pdf_path).name
    parts = [
        f'<document filename="{xml_escape(filename)}" pages="{len(pages)}">'
    ]
    for page in pages:
        attrs = [
            f'n="{page.page_number}"',
            f'method="{xml_escape(page.extraction_method)}"',
            f'ocr_confidence="{page.confidence:.2f}"',
        ]
        if page.needs_review:
            attrs.append('status="needs_human_transcription"')
            attrs.append(f'reason="{xml_escape(page.review_reason)}"')
        parts.append(f'<page {" ".join(attrs)}>')
        if page.needs_review:
            parts.append('  <unreadable />')
            parts.append('</page>')
            continue
        headers = [b for b in page.blocks if b.block_type == "header"]
        footers = [b for b in page.blocks if b.block_type == "footer"]
        body    = [b for b in page.blocks if b.block_type not in ("header", "footer")]
        for h in headers:
            parts.append(f'  <header>{xml_escape(h.text)}</header>')
        if body:
            parts.append('  <body>')
            for idx, b in enumerate(body, 1):
                if b.block_type == "table":
                    extra = ""
                    spans = b.metadata.get("spans_pages")
                    if spans and len(spans) > 1:
                        extra += f' spans_pages="{spans[0]}-{spans[-1]}"'
                    if b.metadata.get("continuation_suspected"):
                        extra += f' continuation_suspected="true" prev_table_page="{b.metadata.get("prev_table_page","")}"'
                    parts.append(f'    <table{extra}>')
                    parts.append(b.text)  # already markdown
                    parts.append('    </table>')
                elif b.block_type == "list_item":
                    parts.append(f'    <list_item>{xml_escape(b.text)}</list_item>')
                elif b.block_type == "signature_block":
                    parts.append(f'    <signature_block>{xml_escape(b.text)}</signature_block>')
                else:
                    parts.append(f'    <paragraph>{xml_escape(b.text)}</paragraph>')
            parts.append('  </body>')
        for f in footers:
            parts.append(f'  <footer>{xml_escape(f.text)}</footer>')
        parts.append('</page>')
    parts.append('</document>')
    return "\n".join(parts)


# ----------------------------------------------------------------------------
# Public entrypoint
# ----------------------------------------------------------------------------
def pass1(pdf_path: str) -> dict:
    pages = extract_hybrid(pdf_path)
    pages = stitch_cross_page_tables(pages)
    xml = normalize_to_xml(pdf_path, pages)
    needs_review_pages = [p.page_number for p in pages if p.needs_review]
    avg_conf = sum(p.confidence for p in pages) / len(pages) if pages else 0.0
    method_counts = {}
    for p in pages:
        method_counts[p.extraction_method] = method_counts.get(p.extraction_method, 0) + 1
    block_counts = {}
    for p in pages:
        for b in p.blocks:
            block_counts[b.block_type] = block_counts.get(b.block_type, 0) + 1
    file_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()[:16]
    return {
        "pdf_path": pdf_path,
        "filename": Path(pdf_path).name,
        "file_hash": file_hash,
        "page_count": len(pages),
        "average_confidence": round(avg_conf, 3),
        "needs_review_pages": needs_review_pages,
        "extraction_method_counts": method_counts,
        "block_counts": block_counts,
        "pages": pages,
        "xml": xml,
    }
