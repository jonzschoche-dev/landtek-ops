#!/usr/bin/env python3
"""extract_fact_fields.py — Tier-1 free decomposition of matter_facts → fact_fields.

Derived, rebuildable, never SoR. Hinges:
  1) value is a VERBATIM substring of statement|excerpt (span-checked)
  2) provenance_level is INHERITED from the parent fact (never promoted)

Number deciphering is DELICATE (kinds must not cross-contaminate):
  ctn       — ARTA / SL case tracking numbers (never e-title fragments)
  tct       — Transfer Certificate of Title
  oct       — Original Certificate of Title
  e_title   — LRA electronic title serials (079-YYYY……)
  tax_dec   — ARP / TD / tax declaration numbers
  docket    — Civil Case / CV / G.R.
  date, amount, doc_ref, forum, survey — supporting

  python3 scripts/extract_fact_fields.py --go
  python3 scripts/extract_fact_fields.py --rebuild --go
"""
from __future__ import annotations

import argparse
import os
import re
from typing import Callable

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


# ─── helpers ───────────────────────────────────────────────────────────────

def _find_span(hay: str, needle: str):
    if not needle:
        return None
    i = hay.find(needle)
    if i >= 0:
        return i, i + len(needle)
    i = hay.lower().find(needle.lower())
    if i >= 0:
        return i, i + len(needle)
    return None


def _overlaps(claimed: list[tuple[int, int]], start: int, end: int) -> bool:
    for a, b in claimed:
        if start < b and end > a:
            return True
    return False


def _valid_mmdd(mmdd: str) -> bool:
    """True if 4-digit string is a plausible MMDD (01–12 / 01–31)."""
    if not re.fullmatch(r"\d{4}", mmdd):
        return False
    mm, dd = int(mmdd[:2]), int(mmdd[2:])
    return 1 <= mm <= 12 and 1 <= dd <= 31


def _norm_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


# ─── delicate number extractors (label-first, then strict shape) ────────────
# Each returns list of (kind, raw_span, value_norm) with spans from the match.

def _extract_e_titles(text: str) -> list[tuple[str, str, str]]:
    """LRA e-title: 079-YYYYNNNNNN (10+ digits after province code)."""
    out = []
    for m in re.finditer(r"\b(0\d{2}-\d{10,12})\b", text):
        raw = m.group(1)
        out.append(("e_title", raw, raw))
    return out


def _extract_oct(text: str) -> list[tuple[str, str, str]]:
    out = []
    # Labeled OCT only — never invent from bare numbers
    pats = [
        r"\bOriginal\s+Certificate\s+of\s+Title\s+No\.?\s*([A-Z]?-?\d{2,7}(?:-\d+)*)\b",
        r"\bOCT\s*(?:No\.?|#|:)?\s*([A-Z]?-?\d{2,7}(?:-\d+)*)\b",
    ]
    for pat in pats:
        for m in re.finditer(pat, text, re.I):
            num = m.group(1).upper().lstrip("-")
            raw = m.group(0)
            norm = f"OCT-{num}" if not num.startswith("OCT") else num
            out.append(("oct", raw, norm))
    return out


def _extract_tct(text: str) -> list[tuple[str, str, str]]:
    out = []

    def _accept_num(num: str, labeled: bool) -> str | None:
        num = num.upper().replace(" ", "").lstrip("TCT").lstrip("-:")
        if re.match(r"0\d{2}-\d{10,}", num):
            return num  # e-title serial on a transfer title
        if num.startswith("T-"):
            digits = num[2:].replace("-", "")
        else:
            digits = num.replace("-", "")
            num = f"T-{num}"
        # bare T-079 / T-100 are too short / province-like — need label or ≥4 digits
        if not labeled and len(re.sub(r"\D", "", digits)) < 4:
            return None
        if len(re.sub(r"\D", "", digits)) < 2:
            return None
        return num if num.startswith("T-") else f"T-{num}"

    labeled_pats = [
        r"\bTransfer\s+Certificate\s+of\s+Title\s+No\.?\s*((?:T-)?\d{2,7}(?:-\d+)*|0\d{2}-\d{10,12})\b",
        r"\bTCT\s*(?:No\.?|#|:)?\s*((?:T-)?\d{2,7}(?:-\d+)*|0\d{2}-\d{10,12})\b",
    ]
    for pat in labeled_pats:
        for m in re.finditer(pat, text, re.I):
            raw = m.group(0)
            norm = _accept_num(m.group(1), labeled=True)
            if norm:
                out.append(("tct", raw, norm))
    # bare T-32911 / T-4497 — ≥4 digit body only (not T-079 province noise)
    for m in re.finditer(r"\b(T-\d{4,7}(?:-\d+)*)\b", text, re.I):
        raw = m.group(0)
        norm = _accept_num(m.group(1), labeled=False)
        if norm:
            out.append(("tct", raw, norm))
    return out


def _extract_tax_dec(text: str) -> list[tuple[str, str, str]]:
    """ARP / TD / tax declaration — require label + real number body."""
    out = []
    # ARP body: digits/hyphens/slashes only after label (stop before words like ASSESSED)
    for m in re.finditer(
        r"\bARP\s*(?:No\.?|NO\.?|#|:)?\s*([A-Z]{0,4}[-/]?\d[\dA-Z./-]{1,36})",
        text,
        re.I,
    ):
        body = m.group(1).strip().rstrip(".,;/")
        # cut trailing alpha garbage glued on (ASSESSED)
        body = re.split(r"(?i)(?<=\d)(?=[A-Z]{3,})", body)[0]
        body = body.rstrip("-./")
        if not re.search(r"\d{2,}", body):
            continue
        raw = m.group(0)[: m.start(1) - m.start() + len(body) + (m.start(1) - m.start())]
        # prefer exact labeled span from start to end of body
        raw = text[m.start() : m.start(1) + len(body)]
        out.append(("tax_dec", raw, f"ARP-{body.upper()}"))

    # TD No. 0157 / Tax Declaration No. …
    for m in re.finditer(
        r"\b(?:Tax\s+Declarations?|T\.?D\.?)\s*(?:No\.?|NO\.?|#|:)?\s*(\d[\dA-Z./-]{1,30})",
        text,
        re.I,
    ):
        body = m.group(1).strip().rstrip(".,;/")
        body = re.split(r"(?i)(?<=\d)(?=[A-Z]{3,})", body)[0].rstrip("-./")
        if not re.search(r"\d", body):
            continue
        raw = text[m.start() : m.start(1) + len(body)]
        out.append(("tax_dec", raw, f"TD-{body.upper()}"))
    return out


def _extract_ctn(text: str) -> list[tuple[str, str, str]]:
    """
    ARTA CTN / SL numbers only.
    Accept:
      - explicit CTN / SL- prefix forms
      - YYYY-MMDD-SEQ where MMDD is a real date (unlabeled ARTA style)
    Reject:
      - interiors of e-titles (079-2021002126 → fake 2021-002-126)
      - title serial fragments (YYYY-00x-…)
    """
    out = []

    # 1) Explicit labeled forms (highest confidence)
    for m in re.finditer(
        r"\bCTN\s*(?:No\.?|#|:)?\s*(SL[-\s]?)?(20\d{2})[-\s]?(\d{3,4})[-\s]?(\d{3,4})\b",
        text,
        re.I,
    ):
        y, mid, seq = m.group(2), m.group(3), m.group(4)
        raw = m.group(0)
        norm = f"{y}-{mid}-{seq}"
        out.append(("ctn", raw, norm))

    for m in re.finditer(
        r"\bSL[-\s]?(20\d{2})[-\s]?(\d{3,4})[-\s]?(\d{3,4})\b",
        text,
        re.I,
    ):
        y, mid, seq = m.group(1), m.group(2), m.group(3)
        raw = m.group(0)
        out.append(("ctn", raw, f"{y}-{mid}-{seq}"))

    # bare short after CTN: "CTN 0747" / "CTN: 0690"
    for m in re.finditer(r"\bCTN\s*(?:No\.?|#|:)?\s*(\d{3,4})\b", text, re.I):
        raw = m.group(0)
        out.append(("ctn", raw, m.group(1)))

    # 2) Unlabeled ARTA shape YYYY-MMDD-SEQ — only if MMDD valid AND not inside e-title
    for m in re.finditer(r"\b(20\d{2})-(\d{4})-(\d{3,4})\b", text):
        y, mid, seq = m.group(1), m.group(2), m.group(3)
        if not _valid_mmdd(mid):
            continue  # drops 2021-002-126 style title fragments
        # reject if this match sits inside an e-title token 079-…
        start = m.start()
        window = text[max(0, start - 4) : m.end() + 1]
        if re.search(r"0\d{2}-\d*" + re.escape(m.group(0).replace("-", "")[:6]), window.replace("-", "")):
            # crude: if preceded by 079- style
            pass
        # if character just before is digit or we're mid 079-2021…
        if start >= 4 and re.match(r"0\d{2}-", text[start - 4 : start]):
            continue
        if start > 0 and text[start - 1].isdigit():
            continue
        raw = m.group(0)
        out.append(("ctn", raw, f"{y}-{mid}-{seq}"))

    return out


def _extract_docket(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(
        r"\bCivil\s+Case\s*(?:No\.?)?\s*[\d-]+\b"
        r"|\bCV[-\s]?\d{2,5}(?:-\d+)?\b"
        r"|\bG\.?R\.?\s*(?:No\.?)?\s*[\d-]+\b",
        text,
        re.I,
    ):
        raw = m.group(0)
        out.append(("docket", raw, _norm_spaces(raw)))
    return out


def _extract_mro_ref(text: str) -> list[tuple[str, str, str]]:
    """Malacañang Records Office / OP transmittal refs: YYYYMMDD-MRO-######."""
    out = []
    for m in re.finditer(r"\b(\d{6}-MRO-\d{4,8})\b", text, re.I):
        raw = m.group(1).upper()
        out.append(("mro_ref", raw, raw))
    # labeled "OP Transmittal Ref. …"
    for m in re.finditer(
        r"\bOP\s+Transmittal\s+Ref\.?\s*[:#]?\s*(\d{6}-MRO-\d{4,8})\b",
        text,
        re.I,
    ):
        raw = m.group(1).upper()
        out.append(("mro_ref", m.group(0)[:80], raw))
    return out


def _extract_survey(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(
        r"\b(?:Psd|Psu|Csd|Cad|LRC\s*Psd)[-\s]?\d{3,8}(?:-[A-Z0-9]+)?\b",
        text,
        re.I,
    ):
        raw = m.group(0)
        norm = re.sub(r"\s+", "", raw.upper()).replace("LRCPSD", "LRC-PSD")
        out.append(("survey", raw, norm))
    return out


def _extract_dates(text: str) -> list[tuple[str, str, str]]:
    out = []
    # Avoid matching "October" inside OCT confusion — month names only
    rx = re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+\d{1,2},?\s+\d{4}\b"
        r"|\b\d{4}-\d{2}-\d{2}\b"
        r"|\b\d{1,2}/\d{1,2}/\d{4}\b",
        re.I,
    )
    for m in rx.finditer(text):
        raw = m.group(0)
        out.append(("date", raw, _norm_spaces(raw)))
    return out


def _extract_amounts(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(
        r"(?:₱|PHP|Php)\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?"
        r"|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\s*(?:pesos|PHP)\b",
        text,
        re.I,
    ):
        raw = m.group(0)
        out.append(("amount", raw, _norm_spaces(raw)))
    return out


def _extract_doc_ref(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(r"\bdoc(?:ument)?\s*[:#]\s*(\d{2,5})\b", text, re.I):
        raw = m.group(0)
        out.append(("doc_ref", raw, f"doc:{m.group(1)}"))
    return out


def _extract_forum(text: str) -> list[tuple[str, str, str]]:
    out = []
    for m in re.finditer(
        r"\b(?:ARTA|Office of the President|Ombudsman|RTC|MTC|MeTC|"
        r"Court of Appeals|\bCA\b|Supreme Court|\bSC\b|"
        r"DAR|DARAB|LRA|DILG|CSC|Registry of Deeds|\bRD\b)\b",
        text,
        re.I,
    ):
        raw = m.group(0)
        norm = raw.upper() if len(raw) <= 6 else _norm_spaces(raw)
        out.append(("forum", raw, norm))
    return out


# Order matters for overlap: claim e-titles & labeled titles BEFORE ctn unlabeled
_EXTRACTORS: list[Callable[[str], list[tuple[str, str, str]]]] = [
    _extract_e_titles,
    _extract_oct,
    _extract_tct,
    _extract_tax_dec,
    _extract_mro_ref,
    _extract_ctn,
    _extract_docket,
    _extract_survey,
    _extract_dates,
    _extract_amounts,
    _extract_doc_ref,
    _extract_forum,
]


def extract_from_text(text: str) -> list[dict]:
    """Return fields; exclusive spans so numbers are not double-classified."""
    if not text:
        return []
    claimed: list[tuple[int, int]] = []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for extractor in _EXTRACTORS:
        for kind, raw, value_norm in extractor(text):
            raw = raw.strip()
            value_norm = str(value_norm).strip()[:200]
            if len(raw) < 2 or not value_norm:
                continue
            pos = _find_span(text, raw)
            if pos is None:
                continue
            start, end = pos
            # numbers: exclusive claim (titles must not also become CTNs)
            if kind in ("ctn", "tct", "oct", "e_title", "tax_dec", "docket", "survey", "mro_ref"):
                if _overlaps(claimed, start, end):
                    continue
                claimed.append((start, end))
            key = (kind, value_norm.lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "field_kind": kind,
                    "value_raw": raw[:300],
                    "value_norm": value_norm,
                    "char_start": start,
                    "char_end": end,
                    "source_span": raw[:300],
                }
            )
    return out


def run(matter: str | None, go: bool, rebuild: bool, limit: int | None):
    c = psycopg2.connect(DSN)
    # Rebuild must be ATOMIC: truncate + refill in ONE transaction, so a
    # killed/timed-out run rolls back instead of leaving the table gutted
    # (fact_fields was found at 16k/41k twice from interrupted rebuilds).
    c.autocommit = not (rebuild and go)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if rebuild and go:
        if matter:
            cur.execute("DELETE FROM fact_fields WHERE matter_code = %s", (matter,))
        else:
            cur.execute("TRUNCATE fact_fields RESTART IDENTITY")
        print(f"[extract] wiped fact_fields ({'matter ' + matter if matter else 'all'}) — txn open")

    sql = """
        SELECT id, matter_code, statement, excerpt, provenance_level
        FROM matter_facts
        WHERE (%s::text IS NULL OR matter_code = %s)
        ORDER BY id
    """
    params: list = [matter, matter]
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()

    n_facts = len(rows)
    n_with = 0
    n_fields = 0
    n_reject_span = 0

    for r in rows:
        text = (r["statement"] or "") + "\n" + (r["excerpt"] or "")
        fields = extract_from_text(text)
        if not fields:
            continue
        n_with += 1
        for f in fields:
            if _find_span(text, f["source_span"]) is None:
                n_reject_span += 1
                continue
            n_fields += 1
            if not go:
                continue
            cur.execute(
                """
                INSERT INTO fact_fields
                    (fact_id, matter_code, field_kind, value_raw, value_norm,
                     provenance_level, extraction_method, char_start, char_end, source_span)
                VALUES (%s,%s,%s,%s,%s,%s,'regex',%s,%s,%s)
                ON CONFLICT (fact_id, field_kind, value_norm) DO UPDATE SET
                    value_raw = EXCLUDED.value_raw,
                    source_span = EXCLUDED.source_span,
                    char_start = EXCLUDED.char_start,
                    char_end = EXCLUDED.char_end,
                    provenance_level = EXCLUDED.provenance_level
                """,
                (
                    r["id"],
                    r["matter_code"],
                    f["field_kind"],
                    f["value_raw"],
                    f["value_norm"],
                    r["provenance_level"] or "inferred_strong",
                    f["char_start"],
                    f["char_end"],
                    f["source_span"],
                ),
            )

    pct = (100.0 * n_with / n_facts) if n_facts else 0.0
    mode = "WROTE" if go else "DRY"
    print(
        f"[extract] {mode} facts={n_facts} with_fields={n_with} "
        f"typed_coverage={pct:.1f}% fields={n_fields} span_reject={n_reject_span}"
    )

    if go:
        cur.execute(
            """
            INSERT INTO equilibrium_coverage_log
                (n_facts, n_facts_verified, n_facts_with_fields, typed_coverage_pct, notes)
            SELECT
                count(*),
                count(*) FILTER (WHERE provenance_level = 'verified'),
                (SELECT count(DISTINCT fact_id) FROM fact_fields),
                CASE WHEN count(*) = 0 THEN 0
                     ELSE round(100.0 * (SELECT count(DISTINCT fact_id) FROM fact_fields)
                                / count(*), 2) END,
                'extract_fact_fields_delicate'
            FROM matter_facts
            """
        )
        cur.execute(
            """
            SELECT field_kind, count(*) n,
                   count(*) FILTER (WHERE provenance_level='verified') v
            FROM fact_fields GROUP BY 1 ORDER BY n DESC
            """
        )
        for row in cur.fetchall():
            print(f"  {row['field_kind']:<10} n={row['n']:<6} verified={row['v']}")

        # precision smoke: no e-title fragment as ctn
        cur.execute(
            """
            SELECT count(*) AS n FROM fact_fields
            WHERE field_kind = 'ctn'
              AND value_norm ~ '^[0-9]{4}-00[0-9]-'
            """
        )
        bad = cur.fetchone()["n"]
        print(f"  [precision] ctn_with_00x_middle (should be 0): {bad}")

    if not c.autocommit:
        c.commit()
        print("[extract] rebuild txn committed")
    cur.close()
    c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", default=None)
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    run(a.matter, a.go, a.rebuild, a.limit)


if __name__ == "__main__":
    main()
