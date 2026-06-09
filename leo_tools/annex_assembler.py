"""annex_assembler — turn an ORDERED list of exhibits into one filing-ready PDF.

Pure assembly engine (no resolution / no guessing): caller passes an ordered list
of {label, doc_id, desc}; this merges them with a labelled separator page before
each annex, converts image exhibits to pages, and flags anything it cannot merge
(e.g. .docx) instead of silently dropping it. Optional DRAFT watermark.

Uses PyMuPDF (fitz), which is already on the box. The byte-fetch is injected by
the caller (`fetch` callback) so this module stays free of DB/Drive coupling.
"""
from __future__ import annotations

import io
import fitz  # PyMuPDF

A4 = (595.0, 842.0)


def _separator(out, label, desc, draft):
    pg = out.new_page(width=A4[0], height=A4[1])
    pg.insert_text((72, 250), f"ANNEX {label}", fontsize=30, color=(0.1, 0.1, 0.1))
    if desc:
        # wrap the description loosely
        line, y = "", 295
        for word in str(desc).split():
            if len(line) + len(word) > 60:
                pg.insert_text((72, y), line, fontsize=13, color=(0.25, 0.25, 0.25))
                line, y = "", y + 20
            line += word + " "
        if line:
            pg.insert_text((72, y), line, fontsize=13, color=(0.25, 0.25, 0.25))
    return pg


def _watermark(out, text):
    for pg in out:
        pg.insert_text((36, A4[1] - 22), text, fontsize=8, color=(0.7, 0, 0))


def assemble(items, fetch, title="Annexes", draft=True):
    """items: ordered list of {label, doc_id, desc}.
    fetch(doc_id) -> (bytes, mime, name) or (None, None, name) if unavailable.
    Returns (pdf_bytes, manifest[list of per-annex dicts])."""
    out = fitz.open()
    manifest = []
    for it in items:
        label = it.get("label", "?")
        desc = it.get("desc", "")
        doc_id = it["doc_id"]
        _separator(out, label, desc, draft)
        entry = {"label": label, "doc_id": doc_id, "desc": desc}
        try:
            data, mime, name = fetch(doc_id)
        except Exception as e:
            data, mime, name = None, None, f"doc {doc_id}"
            entry["error"] = f"{type(e).__name__}: {e}"
        entry["name"] = name
        if not data:
            note = out.new_page(width=A4[0], height=A4[1])
            note.insert_text((72, 120), f"[Annex {label}: no digital copy available — attach manually]",
                             fontsize=12, color=(0.7, 0, 0))
            entry["status"] = "missing"
            manifest.append(entry)
            continue
        mime = mime or ""
        if "pdf" in mime:
            src = fitz.open(stream=data, filetype="pdf")
            entry["pages"] = src.page_count
            out.insert_pdf(src)
            src.close()
            entry["status"] = "merged"
        elif mime.startswith("image/"):
            img = fitz.open(stream=data, filetype=mime.split("/")[-1])
            pdfbytes = img.convert_to_pdf()
            img.close()
            src = fitz.open("pdf", pdfbytes)
            out.insert_pdf(src)
            src.close()
            entry["status"] = "merged-image"
        else:
            note = out.new_page(width=A4[0], height=A4[1])
            note.insert_text((72, 120),
                             f"[Annex {label}: {name} is {mime or 'non-PDF'} — attach separately]",
                             fontsize=12, color=(0.7, 0, 0))
            entry["status"] = "unmergeable"
            entry["mime"] = mime
        manifest.append(entry)

    if draft:
        _watermark(out, "DRAFT — verify annexes before filing")
    buf = out.tobytes()
    out.close()
    return buf, manifest
