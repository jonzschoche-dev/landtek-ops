#!/usr/bin/env python3
"""Extract text from an uploaded file (PDF / DOCX / images).

Called by the n8n 'Extract File Text' Code node.

Input:  stdin JSON {base64_data, original_filename, mime_type?}
Output: stdout JSON {extracted_text, char_count, status, local_path, mime_type}

Strategies by extension:
  .pdf  -> fitz (PyMuPDF) text layer. If <200 chars, fall back to Gemini Vision.
  .docx -> python-docx paragraph extraction.
  .txt  -> read as utf-8.
  .png/.jpg/.jpeg -> Gemini Vision.
  others -> 'unsupported' status, no text.
"""
import base64
import json
import os
import sys
import re
import tempfile
from pathlib import Path

UPLOADS_DIR = Path("/root/landtek/uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def extract_pdf(path: Path) -> str:
    import fitz
    doc = fitz.open(str(path))
    text = "\n".join(p.get_text() for p in doc)
    doc.close()
    return text.strip()


def extract_docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text and p.text.strip()]
    # Also pull text from tables
    for table in d.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text and cell.text.strip():
                    parts.append(cell.text.strip())
    return "\n".join(parts).strip()


def extract_image_gemini(path: Path) -> str:
    import google.generativeai as genai
    from dotenv import load_dotenv
    load_dotenv("/root/landtek/.env")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ""
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    with open(path, "rb") as f:
        data = f.read()
    img = {"mime_type": "image/jpeg" if str(path).lower().endswith(("jpg", "jpeg")) else "image/png",
           "data": data}
    resp = model.generate_content([
        "Extract ALL visible text from this image, preserving structure. Return text only, no commentary.",
        img,
    ])
    return resp.text.strip() if resp and resp.text else ""


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"status": "error", "error": "empty stdin"}))
        return
    try:
        data = json.loads(raw)
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"json parse: {e}"}))
        return

    b64 = data.get("base64_data") or ""
    original_filename = data.get("original_filename") or "uploaded_file"
    declared_mime = data.get("mime_type") or ""

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_filename)
    local_path = UPLOADS_DIR / f"{os.getpid()}_{safe_name}"
    try:
        binary = base64.b64decode(b64)
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"b64 decode: {e}"}))
        return
    local_path.write_bytes(binary)

    ext = local_path.suffix.lower()
    text = ""
    status = "ok"
    try:
        if ext == ".pdf":
            text = extract_pdf(local_path)
            if len(text) < 200:
                # Fallback: render page 1 + send to Gemini
                try:
                    text2 = extract_image_gemini(local_path)
                    if len(text2) > len(text):
                        text = text2
                        status = "ok_gemini_fallback"
                except Exception:
                    pass
        elif ext == ".docx":
            text = extract_docx(local_path)
        elif ext in (".txt", ".md", ".csv"):
            text = local_path.read_text(encoding="utf-8", errors="replace")
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            text = extract_image_gemini(local_path)
            status = "ok_gemini"
        else:
            status = f"unsupported_extension:{ext}"
    except Exception as e:
        status = f"extract_error:{type(e).__name__}: {e}"
        text = ""

    print(json.dumps({
        "extracted_text": text,
        "char_count": len(text),
        "status": status,
        "local_path": str(local_path),
        "mime_type": declared_mime or {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(ext, "application/octet-stream"),
    }))


if __name__ == "__main__":
    main()
