#!/usr/bin/env python3
"""doc_discovery.py — resident agent: find & link operative documents for under-documented matters.

Whole matters are invisible to Leo because their papers were never linked (matter_code NULL) — the
parallel Civil-6922 / Criminal-9221, TCT-1616, the OP petition, etc. This scans the unlinked document
pool + the gmail corpus for each thin matter's distinctive docket signal and proposes links. It
AUTO-links only on a strong, low-false-positive signal (the full docket phrase present, or the docket
core in the filename, matching exactly ONE matter); anything weaker or ambiguous goes to
doc_link_candidates for review. Conservative by design — mis-linking is the cross-client-conflation
failure mode the sentinel exists to prevent. Newly linked docs flow into verify_loop's worklist, so
the local worker then builds the matter out automatically.

  python3 scripts/doc_discovery.py            # scan -> candidates (+ auto-link strong, single-matter)
  python3 scripts/doc_discovery.py --report    # show open candidates only
"""
import argparse
import re

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def signals(docket, title):
    """Return (strong_phrase_norm, core_token) from a matter's docket; core is the distinctive id."""
    d = docket or ""
    core = None
    for n in re.findall(r"\b(\d{3,6})\b", d):
        if re.fullmatch(r"(19|20)\d{2}", n):   # skip years (2026, 1992, …) — not distinctive
            continue
        core = n; break
    tm = re.search(r"\bT-?\s?(\d{3,6})\b", (d + " " + (title or "")), re.I)
    if tm and not re.fullmatch(r"(19|20)\d{2}", tm.group(1)):
        core = core or tm.group(1)
    return _norm(d), core


def scan(cur, apply_links):
    cur.execute("""SELECT matter_code, docket_number, title,
                   (SELECT count(*) FROM documents d WHERE d.matter_code=m.matter_code) ndocs
                   FROM matters m
                   WHERE m.matter_code NOT LIKE 'AUTO-%' AND m.matter_code NOT LIKE 'ARCHIVE-%'
                     AND (SELECT count(*) FROM documents d WHERE d.matter_code=m.matter_code) < 3""")
    targets = [r for r in cur.fetchall() if (r["docket_number"] or "")]
    # unlinked candidate pool
    cur.execute("""SELECT id, coalesce(original_filename,smart_filename,'') fn,
                   left(coalesce(extracted_text,''),20000) txt FROM documents WHERE matter_code IS NULL""")
    pool = cur.fetchall()
    cur.execute("""CREATE TABLE IF NOT EXISTS doc_link_candidates (
        doc_id int, matter_code text, confidence text, signal text, status text DEFAULT 'proposed',
        created_at timestamptz DEFAULT now(), UNIQUE(doc_id, matter_code))""")

    # build per-doc matches: {doc_id: [(matter, conf, signal)]}
    matches = {}
    for t in targets:
        phrase, core = signals(t["docket_number"], t["title"])
        if not core and len(phrase) < 8:
            continue
        for d in pool:
            fnn, txtn = _norm(d["fn"]), _norm(d["txt"])
            hay = fnn + " " + txtn
            conf = sig = None
            if len(phrase) >= 8 and phrase in hay:
                conf, sig = "high", f"docket phrase '{t['docket_number']}'"
            elif core and core in fnn:
                conf, sig = "high", f"docket #{core} in filename"
            elif core and core in txtn and re.search(r"civil case|criminal|crim|tct|oct|petition|t " + core, hay):
                conf, sig = "med", f"docket #{core} + case-type context"
            if conf:
                matches.setdefault(d["id"], []).append((t["matter_code"], conf, sig))

    linked = proposed = 0
    for doc_id, ms in matches.items():
        unambiguous = len(ms) == 1
        for matter, conf, sig in ms:
            auto = apply_links and conf == "high" and unambiguous
            status = "linked" if auto else "proposed"
            cur.execute("""INSERT INTO doc_link_candidates (doc_id,matter_code,confidence,signal,status)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT (doc_id,matter_code)
                DO UPDATE SET confidence=EXCLUDED.confidence, signal=EXCLUDED.signal""",
                (doc_id, matter, conf, sig + ("" if unambiguous else " [AMBIGUOUS: multi-matter]"), status))
            if auto:
                cur.execute("UPDATE documents SET matter_code=%s WHERE id=%s AND matter_code IS NULL",
                            (matter, doc_id))
                linked += cur.rowcount
            else:
                proposed += 1
    return linked, proposed


def report(cur):
    cur.execute("""SELECT matter_code, confidence, count(*) n FROM doc_link_candidates
                   WHERE status='proposed' GROUP BY 1,2 ORDER BY 1,2""")
    print("=" * 70); print("DOC-DISCOVERY — open link candidates (need review)"); print("=" * 70)
    for mc, conf, n in cur.fetchall():
        print(f"  {mc:24} {conf:5} {n} candidate doc(s)")
    cur.execute("SELECT count(*) FROM doc_link_candidates WHERE status='linked'")
    print(f"\nauto-linked (high-confidence, single-matter): {cur.fetchone()[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if not a.report:
        linked, proposed = scan(cur, apply_links=True)
        print(f"[doc-discovery] auto-linked {linked} docs · {proposed} proposed for review")
    report(c.cursor())


if __name__ == "__main__":
    main()
