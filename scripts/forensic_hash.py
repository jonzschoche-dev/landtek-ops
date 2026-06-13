#!/usr/bin/env python3
"""forensic_hash.py — creditless forensic primitives for the corpus (Pillar 6).

For each document with local bytes it computes:
  - content SHA-256        — exact-duplicate + tamper-evidence anchor
  - perceptual hash (aHash)— near-duplicate / re-scan / crop detection (64-bit)
  - EXIF (images)          — camera, EDITING SOFTWARE, capture time, GPS — the signals
                             that flag a "scan" that is really a screenshot or an edited
                             image (directly relevant to the Balane/de-la-Fuente forgery angle)

Then it groups near-duplicates by Hamming distance on the aHash. NO LLM — pure Python.
Signature-validation (vision/LLM) layers on later; this is the deterministic substrate +
the tamper/dup audit chain.

Deps are graceful: PIL (Pillow) and PyMuPDF (fitz) are used if present; the module degrades
to content-hash-only if neither is installed.

  python3 forensic_hash.py --doc 388          # analyze one doc, print findings
  python3 forensic_hash.py --sweep 200         # analyze up to N un-analyzed docs -> forensic_findings
  python3 forensic_hash.py --dups              # show near-duplicate groups
"""
from __future__ import annotations
import hashlib
import json
import os
import sys

import psycopg2
import psycopg2.extras

try:
    from PIL import Image, ExifTags
    _HAVE_PIL = True
except Exception:
    _HAVE_PIL = False
try:
    import fitz  # PyMuPDF — render first PDF page for hashing
    _HAVE_FITZ = True
except Exception:
    _HAVE_FITZ = False

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
_EXIF_TAGS = {v: k for k, v in (ExifTags.TAGS.items() if _HAVE_PIL else {})}


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS forensic_findings (
        doc_id int PRIMARY KEY, sha256 text, ahash bigint, exif jsonb,
        flags text[], analyzed_at timestamptz DEFAULT now())""")


def _pil_from(path):
    """Return a PIL grayscale image for an image file OR the first page of a PDF."""
    if not _HAVE_PIL:
        return None
    low = path.lower()
    if low.endswith((".pdf",)) or (_HAVE_FITZ and _is_pdf(path)):
        if not _HAVE_FITZ:
            return None
        d = fitz.open(path)
        if d.page_count == 0:
            return None
        pix = d[0].get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)
    try:
        return Image.open(path).convert("L")
    except Exception:
        return None


def _is_pdf(path):
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False


def ahash(img, n=8):
    """64-bit average hash from a PIL grayscale image."""
    small = img.resize((n, n))
    px = list(small.tobytes())   # 'L' mode → one byte per pixel; avoids the getdata deprecation
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p >= avg:
            bits |= (1 << i)
    # store as signed bigint range
    return bits - (1 << 63)


def hamming(a, b):
    return bin((a + (1 << 63)) ^ (b + (1 << 63))).count("1")


def exif_of(path):
    if not _HAVE_PIL:
        return {}
    try:
        img = Image.open(path)
        raw = getattr(img, "_getexif", lambda: None)() or {}
    except Exception:
        return {}
    out = {}
    for tag, val in raw.items():
        name = ExifTags.TAGS.get(tag, str(tag))
        if name in ("Make", "Model", "Software", "DateTime", "DateTimeOriginal", "GPSInfo"):
            out[name] = str(val)[:120]
    return out


def analyze_doc(cur, doc_id, path):
    flags = []
    sha = None
    try:
        with open(path, "rb") as f:
            data = f.read()
        sha = hashlib.sha256(data).hexdigest()
    except Exception:
        flags.append("no_bytes")
    ah = None
    img = _pil_from(path) if sha else None
    if img is not None:
        try:
            ah = ahash(img)
        except Exception:
            flags.append("hash_fail")
    ex = exif_of(path) if (sha and not _is_pdf(path)) else {}
    if ex.get("Software"):
        flags.append("has_editing_software")   # e.g. Photoshop/GIMP on a "scan" = review
    cur.execute("""INSERT INTO forensic_findings (doc_id, sha256, ahash, exif, flags)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (doc_id) DO UPDATE SET sha256=EXCLUDED.sha256, ahash=EXCLUDED.ahash,
            exif=EXCLUDED.exif, flags=EXCLUDED.flags, analyzed_at=now()""",
        (doc_id, sha, ah, json.dumps(ex), flags))
    return {"doc_id": doc_id, "sha256": (sha or "")[:16], "ahash": ah, "exif": ex, "flags": flags}


def sweep(limit=200):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor); ensure(cur)
    cur.execute("""SELECT id, file_path FROM documents
        WHERE coalesce(file_path,'')<>'' AND id NOT IN (SELECT doc_id FROM forensic_findings)
        ORDER BY id LIMIT %s""", (limit,))
    rows = cur.fetchall(); n = 0
    for r in rows:
        analyze_doc(cur, r["id"], r["file_path"]); n += 1
    cur.close(); c.close()
    print(f"[forensic] analyzed {n} docs (PIL={_HAVE_PIL}, fitz={_HAVE_FITZ})")


def dup_groups(max_dist=4):
    c = _conn(); cur = c.cursor(); cur.execute(
        "SELECT doc_id, ahash FROM forensic_findings WHERE ahash IS NOT NULL")
    rows = cur.fetchall(); cur.close(); c.close()
    seen, groups = set(), []
    for i, (d1, h1) in enumerate(rows):
        if d1 in seen:
            continue
        grp = [d1]
        for d2, h2 in rows[i + 1:]:
            if d2 not in seen and hamming(h1, h2) <= max_dist:
                grp.append(d2); seen.add(d2)
        if len(grp) > 1:
            groups.append(grp); seen.add(d1)
    for g in groups:
        print(f"  near-dup group (≤{max_dist} bits): docs {g}")
    print(f"[forensic] {len(groups)} near-duplicate group(s) among {len(rows)} hashed docs")


if __name__ == "__main__":
    a = sys.argv
    if "--sweep" in a:
        sweep(int(a[a.index("--sweep") + 1]) if len(a) > a.index("--sweep") + 1 else 200)
    elif "--dups" in a:
        dup_groups()
    elif "--doc" in a:
        did = int(a[a.index("--doc") + 1])
        c = _conn(); cur = c.cursor(); ensure(cur)
        cur.execute("SELECT file_path FROM documents WHERE id=%s", (did,))
        row = cur.fetchone()
        fp = row[0] if row else None
        result = analyze_doc(cur, did, fp) if fp else {"error": "no file_path for doc"}
        cur.close(); c.close()
        print(json.dumps(result, indent=2))
    else:
        print(__doc__)
