#!/usr/bin/env python3
"""ocr_quality.py — score extracted_text quality with a zero-API heuristic.

"Has text" != "readable". Faint old Philippine land scans produce text that passes a
length check but is garbage ("tho hoirs of Mnry Worriek", "l1l |||  rn~"). This scores
every doc's extracted_text 0..1 on word-likeness + clean-char ratio so the re-OCR sweep
only spends Gemini free-tier calls on the docs that actually need it (economy: don't
re-OCR text that's already clean). Pure-Python, instant, creditless.

  python3 ocr_quality.py --scan            # score all docs -> ocr_quality table (dry: no write unless --go)
  python3 ocr_quality.py --scan --go       # score + persist
  python3 ocr_quality.py --report          # distribution + how many fall below threshold
  python3 ocr_quality.py --doc 39          # score one doc, show the breakdown
"""
import os
import re
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
# below this score a doc is flagged for re-OCR
THRESHOLD = float(os.environ.get("OCR_QUALITY_THRESHOLD", "0.62"))
VOWELS = set("aeiouAEIOU")
_TOKEN = re.compile(r"\S+")
_LETTERS = re.compile(r"[A-Za-z]")
_4CONS = re.compile(r"[bcdfghjklmnpqrstvwxyzBCDFGHJKLMNPQRSTVWXYZ]{5,}")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def score_text(text):
    """Return (score 0..1, metrics dict). Higher = more readable."""
    text = text or ""
    n = len(text)
    if n < 50:
        return 0.0, {"reason": "too_short", "chars": n}
    # clean-char ratio: how much is letters/digits/space/common punct vs noise/replacement
    clean = sum(1 for ch in text if ch.isalnum() or ch in " \n\t.,;:'\"()-/&%#")
    clean_ratio = clean / n
    bad = text.count("�")  # unicode replacement char = decode/ocr failure
    bad_ratio = bad / n
    # word-likeness over ALPHA tokens only (digits/codes like T-4497, Psu-143364 are neutral)
    toks = _TOKEN.findall(text)
    alpha_toks = 0
    good_toks = 0
    for t in toks:
        letters = _LETTERS.findall(t)
        if len(letters) < 2:
            continue  # punctuation / single chars / pure numbers -> neutral
        alpha_toks += 1
        core = "".join(letters)
        has_vowel = any(c in VOWELS for c in core)
        no_long_consonant_run = not _4CONS.search(core)
        not_repeat = len(set(core.lower())) > 1
        reasonable_len = 2 <= len(t) <= 30
        if has_vowel and no_long_consonant_run and not_repeat and reasonable_len:
            good_toks += 1
    word_quality = (good_toks / alpha_toks) if alpha_toks else 0.0
    # composite: word quality dominated, discounted by dirty chars
    score = word_quality * clean_ratio * (1.0 - min(bad_ratio * 8, 0.6))
    return round(score, 4), {
        "chars": n, "alpha_tokens": alpha_toks, "good_tokens": good_toks,
        "word_quality": round(word_quality, 3), "clean_ratio": round(clean_ratio, 3),
        "bad_ratio": round(bad_ratio, 4),
    }


def _ensure_table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS ocr_quality (
        doc_id int PRIMARY KEY, score real, chars int, word_quality real,
        flagged boolean, scored_at timestamptz DEFAULT now())""")


def scan(go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure_table(cur)
    cur.execute("""SELECT id, extracted_text,
        (file_path IS NOT NULL OR drive_file_id IS NOT NULL) AS has_source
        FROM documents""")
    rows = cur.fetchall()
    flagged = scored = no_source = 0
    for r in rows:
        text = r["extracted_text"] or ""
        if len(text) < 50:
            # no real text — only a re-OCR target if we have bytes to render
            if not r["has_source"]:
                no_source += 1
                continue
            sc, m = 0.0, {"chars": len(text)}
        else:
            sc, m = score_text(text)
        flag = sc < THRESHOLD and r["has_source"]
        if flag:
            flagged += 1
        scored += 1
        if go:
            cur.execute("""INSERT INTO ocr_quality (doc_id, score, chars, word_quality, flagged, scored_at)
                VALUES (%s,%s,%s,%s,%s, now())
                ON CONFLICT (doc_id) DO UPDATE SET score=EXCLUDED.score, chars=EXCLUDED.chars,
                    word_quality=EXCLUDED.word_quality, flagged=EXCLUDED.flagged, scored_at=now()""",
                (r["id"], sc, m.get("chars", 0), m.get("word_quality", 0.0), flag))
    print(f"[ocr_quality] {'WROTE' if go else 'DRY'} scored={scored} flagged(<{THRESHOLD})={flagged} "
          f"no_text_no_source={no_source}")
    cur.close(); c.close()
    return flagged


def report():
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT count(*) FROM ocr_quality")
    total = cur.fetchone()[0]
    if not total:
        print("[ocr_quality] no scores yet — run --scan --go first"); cur.close(); c.close(); return
    print(f"[ocr_quality] {total} docs scored. Distribution:")
    for lo, hi in [(0.0, 0.2), (0.2, 0.4), (0.4, 0.62), (0.62, 0.8), (0.8, 1.01)]:
        cur.execute("SELECT count(*) FROM ocr_quality WHERE score>=%s AND score<%s", (lo, hi))
        n = cur.fetchone()[0]
        bar = "#" * min(n // 5, 50)
        tag = "  <- re-OCR" if hi <= THRESHOLD else ""
        print(f"  {lo:.2f}-{hi:.2f}: {n:4d} {bar}{tag}")
    cur.execute("SELECT count(*) FROM ocr_quality WHERE flagged")
    print(f"  => {cur.fetchone()[0]} flagged for re-OCR (score < {THRESHOLD})")
    print("  worst 12:")
    cur.execute("""SELECT q.doc_id, q.score, left(coalesce(d.original_filename,''),42)
        FROM ocr_quality q JOIN documents d ON d.id=q.doc_id
        WHERE q.flagged ORDER BY q.score ASC LIMIT 12""")
    for did, sc, name in cur.fetchall():
        print(f"    doc {did:4d}  score {sc:.3f}  {name}")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--doc" in a:
        did = int(a[a.index("--doc") + 1])
        c = _conn(); cur = c.cursor()
        cur.execute("SELECT extracted_text FROM documents WHERE id=%s", (did,))
        row = cur.fetchone(); cur.close(); c.close()
        if not row:
            print(f"no doc {did}"); sys.exit(1)
        sc, m = score_text(row[0] or "")
        print(f"doc {did}: score={sc}  flagged={sc < THRESHOLD}  {m}")
    elif "--report" in a:
        report()
    elif "--scan" in a:
        scan(go="--go" in a)
    else:
        print(__doc__)
