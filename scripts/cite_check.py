#!/usr/bin/env python3
"""cite_check.py — pre-flight: verify a draft's statutory citations against the embedded law library.

Catches the failure class that bit us repeatedly this session, mechanically and before filing:
  • a quoted passage attributed to the WRONG section/act (§21(b) vs §21(g));
  • a wrong section NUMBER cited for a proposition (§173 "Lien", §276 "Condonation");
  • citing a SUPERSEDED provision (§201, amended by RA 12001).

Two engines:
  1. QUOTE CHECK — every "quoted passage" → is that text in legal_chunks, and under which citation?
     (a quote not found = misquote/fabrication risk; a quote found under a different act = mis-attribution).
  2. SECTION REALITY — every cited "Section N / §N of <Act>" → show what that section ACTUALLY says
     (its title from the library), and flag if the section was amended by a later law.

NOT a substitute for counsel — a fast, mechanical pre-flight. Run before publish.
  python3 cite_check.py 1891_output/foo.md
"""
from __future__ import annotations
import os, re, sys
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# sections amended/affected by later laws — flag "verify current text"
AMENDED = {
    ("7160", "201"): "amended by RA 12001 (RPVARA 2024)",
    ("7160", "218"): "amended by RA 12001 (RPVARA 2024)",
    ("7160", "220"): "amended by RA 12001 (RPVARA 2024)",
    ("7160", "472"): "only §472(b)(8) amended by RA 12001 — confirm the cited subsection",
    ("7160", "19"):  "amended by RA 12001 (RPVARA 2024)",
    ("7160", "135"): "§135(a) amended by RA 12001",
    ("7160", "138"): "amended by RA 12001 (RPVARA 2024)",
}

ACT_RE = re.compile(r"(?:R\.?A\.?|Republic Act|P\.?D\.?|Presidential Decree|E\.?O\.?|Executive Order)\.?\s*(?:No\.?\s*)?(\d{2,5})", re.I)
# "Section 252", "Sec. 21", "§472(b)(4)" — capture number + optional subsection
CITE_RE = re.compile(r"(?:Section|Sec\.|§)\s*(\d+)((?:\([a-z0-9]+\))*)", re.I)


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", s.lower())).strip()


def _nearest_act(prefix):
    m = ACT_RE.findall(prefix)
    return m[-1] if m else None


def _act_near(flat, pos, w=170):
    """Act named within a window AROUND a position — handles '§21(b) of R.A. No. 11032' (act follows)."""
    m = ACT_RE.findall(flat[max(0, pos - w):pos + w])
    return m[-1] if m else None


def quote_check(cur, flat):
    quotes = [(m.start(), m.group(1)) for m in re.finditer(r'[\"“]([^\"”]{20,400})[\"”]', flat)]
    print(f"--- QUOTE CHECK ({len(quotes)} quoted passages) ---")
    flags = 0
    for pos, q in quotes:
        core = _norm(q)[:55]
        if len(core) < 15:
            continue
        act = _nearest_act(flat[max(0, pos - 240):pos])
        cur.execute("SELECT DISTINCT citation FROM legal_chunks "
                    "WHERE regexp_replace(lower(text),'[^a-z0-9 ]+',' ','g') LIKE %s LIMIT 4", ('%' + core + '%',))
        hits = [r[0] for r in cur.fetchall()]
        snippet = q[:58].replace("\n", " ")
        if not hits:
            print(f"  ✗ NOT IN LIBRARY (claimed RA {act or '?'}): \"{snippet}…\"")
            flags += 1
        elif act and not any(act in h for h in hits):
            print(f"  ⚠ MIS-ATTRIBUTED? claimed RA {act}, found in: {hits[0][:46]}")
            print(f"      \"{snippet}…\"")
            flags += 1
        else:
            shown = next((h for h in hits if act and act in h), hits[0])
            print(f"  ✓ verified in {shown[:46]}: \"{snippet}…\"")
    return flags


def section_reality(cur, flat):
    print("\n--- SECTION REALITY (what each cited section actually says) ---")
    seen, flags = set(), 0
    for m in CITE_RE.finditer(flat):
        num, sub = m.group(1), m.group(2)
        act = _act_near(flat, m.start())
        key = (act, num)
        if key in seen:
            continue
        seen.add(key)
        secpat = r'(?:Section|Sec\.?) ' + num + r'\.'
        cur.execute("SELECT regexp_replace(text,'\\s+',' ','g') FROM legal_chunks "
                    "WHERE (%s IS NULL OR citation ILIKE %s) AND text ~* %s LIMIT 1",
                    (act, '%' + (act or '') + '%', secpat))
        r = cur.fetchone()
        label = f"§{num}{sub or ''}" + (f" of RA/PD {act}" if act else "")
        if r:
            mm = re.search(secpat, r[0], re.I)
            title = r[0][mm.start():mm.start() + 95] if mm else r[0][:95]
            print(f"  • {label} → {title.strip()}…")
        else:
            print(f"  • {label} → (not located{' in RA/PD ' + act if act else ''} — verify)")
        if act and (act, num) in AMENDED:
            print(f"      ⚠ AMENDED: {AMENDED[(act, num)]}")
            flags += 1
    return flags


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: cite_check.py <draft.md>")
    txt = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
    flat = re.sub(r"[ \t]+", " ", txt)
    cur = psycopg2.connect(DSN).cursor()
    print(f"[cite_check] {os.path.basename(sys.argv[1])}\n")
    f = quote_check(cur, flat) + section_reality(cur, flat)
    print(f"\n[cite_check] {f} item(s) flagged — review before filing. (Mechanical pre-flight; not legal advice.)")


if __name__ == "__main__":
    main()
