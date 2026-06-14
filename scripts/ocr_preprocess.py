#!/usr/bin/env python3
"""ocr_preprocess.py — designer-lane module: prepare PDF pages for browser OCR.

Why this exists:
  Wave-1 OCR results (deploy-XXX-pending) showed that clean modern CTCs OCR at
  ~90% quality but old paper title CTCs degrade to 40-50% — names mangled,
  technical descriptions unusable. The PDFs themselves declare in their headers:
  "UNOFFICIAL COPY IF NOT IN BLUE COLOR" — i.e. the printed text is in blue ink
  as a security feature. Isolating the blue channel separates printed text from
  yellowed-paper background and from red/black cancellation stamps.

What this does:
  Given a doc_id (resolved against the OCR worklist) or an --input PDF path,
  rasterize each page at configurable DPI, then produce up to 3 preprocessed
  variants per page:

    blue : blue-channel isolated → cleanest printed-text image
           best for: Gemini browser OCR of body text + memorandum entries
    gray : full grayscale + autocontrast + unsharp + light denoise
           best for: Claude browser OCR of handwritten annotations + stamps
    bw   : adaptive binary threshold (Otsu approximation via Pillow)
           best for: Tesseract local OCR baseline

  Output: drafts/ocr_staging/<doc_id>/page_<NN>_<variant>.png

  Operator then uploads the relevant variant(s) to the browser engine of choice.

Usage:
  # Resolve doc 87 from OCR_WORKLIST.md, default DPI 300, all 3 variants
  python3 scripts/ocr_preprocess.py --doc 87

  # Single page, blue-only, higher DPI
  python3 scripts/ocr_preprocess.py --doc 87 --page 2 --variants blue --dpi 450

  # Bypass worklist, point at any PDF
  python3 scripts/ocr_preprocess.py --input "/path/to/file.pdf" --doc 87

  # Clean prior staging for a doc
  python3 scripts/ocr_preprocess.py --doc 87 --clean

Dependencies: fitz (PyMuPDF), PIL/Pillow, numpy — all already in landtek stack.
No OpenCV required.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# fitz / PIL / numpy are already in landtek (per §5A: Tesseract via PyMuPDF).
# We import lazily so --clean / --resolve modes still work without them.

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKLIST_PATH = REPO_ROOT / "case_work" / "OCR_WORKLIST.md"
STAGING_ROOT = REPO_ROOT / "drafts" / "ocr_staging"
DRIVE_BASE = Path(
    "/Users/jonathanzschoche/Library/CloudStorage/"
    "GoogleDrive-jonathan@hayuma.org/My Drive/LANDTEK "
)

VALID_VARIANTS = ("blue", "gray", "bw")


# ─── worklist resolution ─────────────────────────────────────────────────────


def resolve_doc_path(doc_id: int) -> Path | None:
    """Parse OCR_WORKLIST.md table rows, return the local PDF path for doc_id.

    Matches lines like:
      | 246 | 0.07 | 01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/Legal/SPA/SPA Cesar de la Fuente.pdf |
    Skips '⚠ NOT LOCAL' rows.
    """
    if not WORKLIST_PATH.is_file():
        return None
    pattern = re.compile(
        r"^\|\s*(\d+)\s*\|\s*[\d.]+\s*\|\s*(.+?)\s*\|\s*$"
    )
    for line in WORKLIST_PATH.read_text().splitlines():
        m = pattern.match(line)
        if not m:
            continue
        if int(m.group(1)) != doc_id:
            continue
        rel = m.group(2).strip()
        if rel.startswith("⚠") or "NOT LOCAL" in rel:
            return None
        return DRIVE_BASE / rel
    return None


# ─── preprocessing primitives ────────────────────────────────────────────────


def _np_to_pil(arr):
    from PIL import Image
    import numpy as np  # noqa: F401
    return Image.fromarray(arr.astype("uint8"))


def enhance_blue(pil_rgb):
    """Isolate the blue printed-text. Returns single-channel PIL image.

    Compute 'blueness' = max(0, B - mean(R,G)). Pixels that are predominantly blue
    (printed text on this title scan) become bright; yellowed paper and red/black
    annotations become dark. We INVERT so text appears dark on white background
    (standard OCR-friendly orientation).
    """
    import numpy as np
    from PIL import ImageOps
    r, g, b = pil_rgb.split()
    arr_r = np.array(r, dtype=np.int16)
    arr_g = np.array(g, dtype=np.int16)
    arr_b = np.array(b, dtype=np.int16)
    blueness = np.clip(arr_b - (arr_r + arr_g) // 2, 0, 255)
    # Invert: high blueness → dark text on white
    inv = 255 - blueness
    img = _np_to_pil(inv)
    # Boost contrast on the result so faded ink lifts off paper background
    return ImageOps.autocontrast(img, cutoff=2)


def enhance_gray(pil_rgb):
    """Full grayscale + autocontrast + unsharp + light denoise.

    Best for capturing annotations, stamps, and handwritten markings that the
    blue-isolation pass loses. Keeps everything but improves separability.
    """
    from PIL import ImageOps, ImageFilter
    gray = pil_rgb.convert("L")
    # Cutoff trims extreme outliers (specks, scanner glare) before stretching
    gray = ImageOps.autocontrast(gray, cutoff=1)
    # Gentle unsharp: keeps edges crisp without halo'ing scan noise
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=2))
    # Light denoise after sharpening (scanner-grain reduction)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray


def enhance_bw(pil_rgb):
    """Approximate Otsu binarization using Pillow + numpy (no OpenCV dependency).

    Output is a 1-bit-style 'L' image (white background, black text). Good for
    feeding Tesseract; less good for vision models that benefit from grayscale.
    """
    import numpy as np
    from PIL import ImageOps
    gray = pil_rgb.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=2)
    arr = np.array(gray)
    # Otsu via histogram (single-pass approximation)
    hist, _ = np.histogram(arr, bins=256, range=(0, 256))
    total = arr.size
    sum_total = np.dot(np.arange(256), hist)
    sumB = 0.0
    wB = 0
    max_var = 0.0
    threshold = 128
    for t in range(256):
        wB += hist[t]
        if wB == 0:
            continue
        wF = total - wB
        if wF == 0:
            break
        sumB += t * hist[t]
        mB = sumB / wB
        mF = (sum_total - sumB) / wF
        var = wB * wF * (mB - mF) ** 2
        if var > max_var:
            max_var = var
            threshold = t
    binary = (arr > threshold).astype("uint8") * 255
    return _np_to_pil(binary)


VARIANT_FN = {"blue": enhance_blue, "gray": enhance_gray, "bw": enhance_bw}


# ─── PDF rasterization ───────────────────────────────────────────────────────


def rasterize_pages(pdf_path: Path, dpi: int, only_page: int | None = None):
    """Yield (page_num_1indexed, PIL.Image RGB) for each page in the PDF."""
    import fitz
    from PIL import Image
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    doc = fitz.open(str(pdf_path))
    try:
        zoom = dpi / 72.0  # 72 DPI is PDF default
        matrix = fitz.Matrix(zoom, zoom)
        for i, page in enumerate(doc, start=1):
            if only_page is not None and i != only_page:
                continue
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mode = "RGB" if pix.n in (3, 4) else "L"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if img.mode != "RGB":
                img = img.convert("RGB")
            yield i, img
    finally:
        doc.close()


# ─── orchestration ───────────────────────────────────────────────────────────


def process_doc(
    doc_id: int,
    pdf_path: Path,
    variants: list[str],
    dpi: int,
    only_page: int | None,
) -> dict:
    """Process one doc into its staging folder. Returns a summary dict."""
    out_dir = STAGING_ROOT / str(doc_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    skipped_existing = []
    for page_num, pil_rgb in rasterize_pages(pdf_path, dpi=dpi, only_page=only_page):
        for v in variants:
            fname = f"page_{page_num:02d}_{v}.png"
            target = out_dir / fname
            if target.exists() and target.stat().st_size > 0:
                skipped_existing.append(fname)
                continue
            processed = VARIANT_FN[v](pil_rgb)
            processed.save(target, "PNG", optimize=True)
            written.append({"file": str(target.relative_to(REPO_ROOT)),
                            "size_kb": round(target.stat().st_size / 1024, 1)})
    # Drop a README in the staging folder telling the operator which variant to use
    readme = out_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            f"# Doc {doc_id} — preprocessed for OCR\n\n"
            f"Source: `{pdf_path}`\n"
            f"DPI: {dpi}\n"
            f"Variants: {', '.join(variants)}\n\n"
            "## Which variant to upload\n\n"
            "- **page_NN_blue.png** → Gemini Advanced browser. Cleanest for printed text "
            "(title body, technical description, memorandum entries that are clean type).\n"
            "- **page_NN_gray.png** → Claude browser (claude.ai). Better at handwritten "
            "annotations + cancellation stamps + rubber-stamp text.\n"
            "- **page_NN_bw.png** → Tesseract local. Highest-contrast binary; good as a "
            "structural baseline for cross-check.\n\n"
            "Upload ONE page per chat (operator note: multi-page upload in one chat tends "
            "to truncate). Run the same canonical OCR prompt from `reocr_gemini.PROMPT`.\n\n"
            "Results flow back via the existing `ocr_browser_adapter.py --write-ocr`.\n"
        )
    return {
        "doc_id": doc_id,
        "pdf": str(pdf_path),
        "out_dir": str(out_dir.relative_to(REPO_ROOT)),
        "written": written,
        "skipped_existing": skipped_existing,
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _print_json(obj):
    import json
    print(json.dumps(obj, indent=2, default=str))


def smoke_test():
    """Validate enhance_* functions on a synthetic blue-text image. No PDF needed.

    Generates a 600×400 white image with blue text + a red 'cancellation' stamp + a
    handwritten-style black scribble, then runs all three enhance functions and
    reports whether each variant produced plausible output (non-empty, expected
    intensity distribution). Lets you confirm the preprocessing pipeline works
    locally before pointing it at a real PDF.
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    # Build a fake CTC-style image: blue printed text + red stamp + black handwriting
    img = Image.new("RGB", (600, 400), (255, 252, 240))  # yellowed paper
    draw = ImageDraw.Draw(img)
    # Try to load a font; fall back to default
    try:
        font_big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except (OSError, IOError):
        font_big = ImageFont.load_default()
        font_sm = font_big
    # Blue printed text (the body)
    draw.text((30, 40), "TRANSFER CERTIFICATE OF TITLE No. T-47657", fill=(20, 30, 180), font=font_big)
    draw.text((30, 90), "REGISTRY OF DEEDS — Camarines Norte", fill=(20, 30, 180), font=font_sm)
    draw.text((30, 130), "Heirs of MARY WORRICK KEESEY", fill=(20, 30, 180), font=font_sm)
    draw.text((30, 170), "Area: 13,124 sq m", fill=(20, 30, 180), font=font_sm)
    # Red cancellation stamp (rotated text effect — just colored text)
    draw.text((350, 250), "CANCELLED", fill=(210, 30, 30), font=font_big)
    # Black "handwritten" annotation
    draw.text((30, 320), "Per file 1976-03-22", fill=(40, 40, 40), font=font_sm)

    results = {}
    for v, fn in VARIANT_FN.items():
        processed = fn(img)
        arr = np.array(processed.convert("L"))
        # "Dark pixels" = pixels below 128 = text/annotation candidates
        dark_count = int((arr < 128).sum())
        # "Mid-tone pixels" = 64-192, useful for gray-scale separation check
        mid_count = int(((arr >= 64) & (arr <= 192)).sum())
        results[v] = {
            "min": int(arr.min()),
            "max": int(arr.max()),
            "mean": round(float(arr.mean()), 1),
            "dark_pixels": dark_count,
            "mid_tone_pixels": mid_count,
            "unique_values": int(np.unique(arr).size),
            "spread_ok": int(arr.max()) - int(arr.min()) >= 100,
        }

    # Sanity expectations (permissive — synthetic image has sparse text):
    #   blue : isolates blue text → some dark pixels exist (text was found),
    #          AND suppresses red stamp + black handwriting (those become white)
    #   gray : captures everything → has more mid-tone pixels than blue
    #          (handwriting + paper texture introduces grays not just 0/255)
    #   bw   : binary → only 2 unique values (0 and 255)
    summary = {
        "blue_isolates_text": results["blue"]["dark_pixels"] > 100 and results["blue"]["spread_ok"],
        "gray_has_contrast":  results["gray"]["spread_ok"] and results["gray"]["dark_pixels"] > 100,
        "bw_is_binary":       results["bw"]["unique_values"] <= 2,
        "blue_suppresses_more_than_gray": results["blue"]["dark_pixels"] <= results["gray"]["dark_pixels"],
    }
    return {"per_variant": results, "summary": summary,
            "all_passed": all(summary.values())}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", type=int, help="document id from OCR_WORKLIST.md")
    ap.add_argument("--input", help="bypass worklist; explicit PDF path")
    ap.add_argument("--smoke-test", action="store_true",
                    help="run a synthetic-image sanity check on enhance_* functions; no PDF needed")
    ap.add_argument("--variants", default="blue,gray,bw",
                    help=f"comma-separated subset of {VALID_VARIANTS}")
    ap.add_argument("--dpi", type=int, default=300, help="rasterization DPI (default 300)")
    ap.add_argument("--page", type=int, default=None, help="process ONLY this page (1-indexed)")
    ap.add_argument("--clean", action="store_true",
                    help="delete staging/<doc_id> and exit (idempotent)")
    args = ap.parse_args()

    if args.smoke_test:
        result = smoke_test()
        _print_json(result)
        sys.exit(0 if result["all_passed"] else 1)

    if args.doc is None:
        _print_json({"error": "--doc is required (or use --smoke-test)"})
        sys.exit(2)

    out_dir = STAGING_ROOT / str(args.doc)

    if args.clean:
        if out_dir.exists():
            shutil.rmtree(out_dir)
            _print_json({"cleaned": str(out_dir.relative_to(REPO_ROOT))})
        else:
            _print_json({"cleaned": "(nothing to clean)"})
        return

    # Resolve PDF path
    if args.input:
        pdf_path = Path(args.input).expanduser()
    else:
        pdf_path = resolve_doc_path(args.doc)
        if pdf_path is None:
            _print_json({"error": f"doc {args.doc} not found in {WORKLIST_PATH.name} "
                                  "(or marked NOT LOCAL); pass --input"})
            sys.exit(2)
    if not pdf_path.is_file():
        _print_json({"error": f"PDF not found: {pdf_path}"})
        sys.exit(2)

    # Validate variants
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    bad = [v for v in variants if v not in VALID_VARIANTS]
    if bad:
        _print_json({"error": f"invalid variants: {bad}; valid={VALID_VARIANTS}"})
        sys.exit(2)

    result = process_doc(
        doc_id=args.doc,
        pdf_path=pdf_path,
        variants=variants,
        dpi=args.dpi,
        only_page=args.page,
    )
    _print_json(result)


if __name__ == "__main__":
    main()
