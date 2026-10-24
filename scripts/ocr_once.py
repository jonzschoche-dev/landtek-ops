"""Deterministic text extraction shared by court_record.py and backfill_sp2680.py.
PDF: pdftotext text layer first; OCR (pdftoppm + tesseract) only if no text layer.
Images: tesseract. No AI/LLM calls."""
import hashlib, os, subprocess, tempfile, glob

IMG_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.webp', '.bmp'}

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

def _run(cmd, timeout=180):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ''

def _tess(img):
    return _run(['tesseract', img, '-', '-l', 'eng', '--psm', '3'])

def extract_text(path, max_pages=8):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        txt = _run(['pdftotext', '-layout', '-l', str(max_pages), path, '-'])
        if len(txt.strip()) > 40:
            return txt, 'pdftotext'
        with tempfile.TemporaryDirectory() as d:
            _run(['pdftoppm', '-r', '200', '-l', str(max_pages), '-png', path, os.path.join(d, 'p')], 600)
            return '\n'.join(_tess(p) for p in sorted(glob.glob(os.path.join(d, 'p*.png')))), 'tesseract'
    if ext == '.heic':
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'x.png')
            _run(['sips', '-s', 'format', 'png', path, '--out', out])
            return (_tess(out) if os.path.exists(out) else ''), 'tesseract'
    if ext in IMG_EXT:
        return _tess(path), 'tesseract'
    if ext in {'.txt', '.md'}:
        return open(path, errors='replace').read(), 'plain'
    return '', 'none'
