#!/usr/bin/env python3
"""Page-level sweep for Inocalla civil-registry + identity documents.

Walks a folder tree of PDFs/images, reads each page (text layer first,
tesseract OCR fallback), and classifies pages that look like a birth
certificate, death certificate, marriage certificate or a government ID.
Emits one JSON record per hit page to stdout.
"""
import json, os, re, subprocess, sys, tempfile
from concurrent.futures import ProcessPoolExecutor

IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}

DOC_TYPES = [
    ("DEATH_CERT",    [r"CERTIFICATE\s+OF\s+DEATH", r"CERTIFICATION\s+OF\s+DEATH", r"CAUSES?\s+OF\s+DEATH"]),
    ("BIRTH_CERT",    [r"CERTIFICATE\s+OF\s+LIVE\s+BIRTH", r"CERTIFICATE\s+OF\s+BIRTH",
                       r"CERTIFICADO\s+DE\s+NACIMIENTO", r"PAGREREHISTRO\s+NG\s+KAPANGANAKAN",
                       r"REGISTRATION\s+OF\s+BIRTH"]),
    ("MARRIAGE_CERT", [r"CERTIFICATE\s+OF\s+MARRIAGE", r"MARRIAGE\s+CONTRACT", r"CONTRACT\s+OF\s+MARRIAGE"]),
    ("ID_PASSPORT",   [r"\bPASSPORT\b", r"PASAPORTE", r"PASSEPORT"]),
    ("ID_DRIVER",     [r"DRIVER'?S?\s+LICEN[SC]E", r"LAND\s+TRANSPORTATION\s+OFFICE"]),
    ("ID_UMID",       [r"UNIFIED\s+MULTI-?PURPOSE", r"\bUMID\b", r"\bGSIS\b", r"\bSSS\b"]),
    ("ID_PHILHEALTH", [r"PHILHEALTH", r"PHIL\s*HEALTH"]),
    ("ID_OTHER",      [r"POSTAL\s+ID", r"VOTER'?S?\s+(ID|CERTIFICATION)", r"SENIOR\s+CITIZEN",
                       r"NBI\s+CLEARANCE", r"TIN\s+ID", r"BARANGAY\s+ID"]),
]

# Known Inocalla family given names (from the partition agreement + case captions)
NAMES = ["SENEN", "BEATRIZ", "VICENTE", "ALLAN", "ALAN", "FRANCISCO", "JESUS", "CASPER",
         "CIPRIANA", "MARILOU", "HERBERT", "MELVIN", "MELWYN", "ROBERT", "ELENA", "HELEN",
         "SHISHIR", "MARY ANN", "GERALDINE", "LIPRIAN", "JENIN", "RAY"]

REGISTRY_RE = re.compile(r"(?:REGISTRY|REG\.?)\s*N[O0]\.?\s*[:\-]?\s*((?:19|20)\d{2}\s*[-–]\s*\d{1,5})", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+(?:18|19|20)\d{2})\b", re.I)


def classify(text):
    up = " ".join(text.upper().split())
    hits = []
    for label, pats in DOC_TYPES:
        for p in pats:
            if re.search(p, up):
                hits.append(label)
                break
    return hits, up


def page_record(path, page, text):
    hits, up = classify(text)
    if not hits:
        return None
    if "INOCALLA" not in up and "INOGALLA" not in up and "INOCALA" not in up:
        return None
    names = sorted({n for n in NAMES if n in up})
    return {
        "file": path,
        "page": page,
        "types": hits,
        "names": names,
        "registry_no": [m.group(1) for m in REGISTRY_RE.finditer(up)][:3],
        "dates": [m.group(1) for m in DATE_RE.finditer(up)][:6],
        "snippet": up[:400],
    }


def ocr_image(img):
    try:
        r = subprocess.run(["tesseract", img, "stdout", "-l", "eng"],
                           capture_output=True, text=True, timeout=120)
        return r.stdout
    except Exception:
        return ""


def do_pdf(path):
    out = []
    try:
        raw = subprocess.run(["pdftotext", "-layout", path, "-"],
                             capture_output=True, text=True, timeout=180).stdout
    except Exception:
        raw = ""
    pages = raw.split("\f")
    n = max(len(pages) - 1, 0)
    if n == 0:
        try:
            info = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=60).stdout
            m = re.search(r"Pages:\s+(\d+)", info)
            n = int(m.group(1)) if m else 0
        except Exception:
            n = 0
        pages = [""] * n
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            txt = pages[i] if i < len(pages) else ""
            if len(txt.strip()) < 120:
                stem = os.path.join(td, f"p{i+1}")
                try:
                    subprocess.run(["pdftoppm", "-r", "150", "-f", str(i + 1), "-l", str(i + 1),
                                    "-png", path, stem], capture_output=True, timeout=180)
                except Exception:
                    continue
                cand = [os.path.join(td, f) for f in os.listdir(td) if f.startswith(f"p{i+1}-") or f == f"p{i+1}.png"]
                for c in cand:
                    txt += "\n" + ocr_image(c)
                    os.remove(c)
            out.append({"file": path, "page": i + 1, "text": txt})
    return out


def do_image(path):
    return [{"file": path, "page": 1, "text": ocr_image(path)}]


def handle(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            return do_pdf(path)
        if ext in IMG_EXT:
            return do_image(path)
    except Exception as e:
        return [{"file": path, "error": str(e)}]
    return []


def main():
    roots = sys.argv[1:]
    files = []
    for root in roots:
        for dirpath, _, names in os.walk(root):
            for nm in names:
                ext = os.path.splitext(nm)[1].lower()
                if ext == ".pdf" or ext in IMG_EXT:
                    files.append(os.path.join(dirpath, nm))
    print(f"# scanning {len(files)} files", file=sys.stderr, flush=True)
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        for recs in ex.map(handle, files, chunksize=1):
            done += 1
            if done % 25 == 0:
                print(f"# {done}/{len(files)}", file=sys.stderr, flush=True)
            for r in recs:
                print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
