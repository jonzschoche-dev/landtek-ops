#!/usr/bin/env python3
"""chronology.py — date-ordered evidence & submissions for a matter (the case timeline). $0.

Builds the chronology a lawyer actually needs: every dated EVENT (from the verified facts) and every
SUBMISSION/filing (from filing_alerts), in date order, each cited to its source. This is the backbone
of a Statement of Material Facts and of testimony prep — the solid, readable spine of a case.

  python3 scripts/chronology.py MWK-CV26360

`timeline(cur, mc)` returns the sorted entries so case_pdf and other outputs can reuse it.
"""
import re
import sys

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

_MON = {}
for _i, (_f, _a) in enumerate([("january", "jan"), ("february", "feb"), ("march", "mar"),
        ("april", "apr"), ("may", "may"), ("june", "jun"), ("july", "jul"), ("august", "aug"),
        ("september", "sep"), ("october", "oct"), ("november", "nov"), ("december", "dec")], 1):
    _MON[_f] = _i; _MON[_a] = _i
_MRE = "|".join(sorted(_MON, key=len, reverse=True))


def parse_dates(t):
    """Return [(sortkey (y,m,d), display)] for dates in text; prefers full dates over month-year."""
    tl = (t or "").lower()
    full = {}
    for m in re.finditer(rf"\b({_MRE})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})\b", tl):
        mo, d, y = _MON[m.group(1)], int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1900 <= y <= 2100:
            full[(y, mo, d)] = f"{y:04d}-{mo:02d}-{d:02d}"
    for m in re.finditer(rf"\b(\d{{1,2}})\s+({_MRE})\.?\s+(\d{{4}})\b", tl):
        d, mo, y = int(m.group(1)), _MON[m.group(2)], int(m.group(3))
        if 1 <= d <= 31 and 1900 <= y <= 2100:
            full[(y, mo, d)] = f"{y:04d}-{mo:02d}-{d:02d}"
    covered = {(y, mo) for (y, mo, _) in full}
    out = dict(full)
    for m in re.finditer(rf"\b({_MRE})\.?\s+(\d{{4}})\b", tl):
        mo, y = _MON[m.group(1)], int(m.group(2))
        if 1900 <= y <= 2100 and (y, mo) not in covered:
            out[(y, mo, 0)] = f"{y:04d}-{mo:02d}"
    return sorted(out.items())


def timeline(cur, mc):
    entries = []  # (sortkey, display, kind, text, source)
    cur.execute("""SELECT statement, source_id FROM matter_facts WHERE matter_code=%s
                   AND provenance_level='verified'""", (mc,))
    for stmt, src in cur.fetchall():
        ds = parse_dates(stmt)
        for key, disp in ds:
            entries.append((key, disp, "event", stmt, src))
    try:
        cur.execute("""SELECT received, subject, sender FROM filing_alerts WHERE matter_code=%s
                       AND received IS NOT NULL""", (mc,))
        for rec, subj, sender in cur.fetchall():
            key = (rec.year, rec.month, rec.day)
            entries.append((key, rec.isoformat(), "submission", f"{subj} (from {sender})", None))
    except psycopg2.Error:
        cur.connection.rollback()
    entries.sort(key=lambda e: e[0])
    return entries


def main():
    mc = sys.argv[1] if len(sys.argv) > 1 else "MWK-CV26360"
    c = psycopg2.connect(DSN); c.autocommit = True
    rows = timeline(c.cursor(), mc)
    print("=" * 86)
    print(f"CHRONOLOGY — {mc}  ({len(rows)} dated entries: events from verified facts + submissions)")
    print("=" * 86)
    for key, disp, kind, text, src in rows:
        tag = "📄" if kind == "event" else "⚖"
        cite = f" [doc:{src}]" if src else ""
        print(f"  {disp:11} {tag} {text[:96].strip()}{cite}")


if __name__ == "__main__":
    main()
