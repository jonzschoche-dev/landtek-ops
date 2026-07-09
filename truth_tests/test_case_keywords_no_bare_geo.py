#!/usr/bin/env python3
"""test_case_keywords_no_bare_geo.py — client-separation guard on the correlation config.

A matter keyword in `case_keywords` must be DISTINCTIVE (a proper name, docket, title number, org). A **bare
geographic / over-broad token** (a municipality, province, or generic place) collides across clients who share
geography and silently cross-files documents — the 2026-07-09 leak where bare "Paracale" mis-filed ~35 MWK/Keesey
docs into the Inocalla matter, and "Camarines Norte" (a province holding BOTH clients) was the same latent bug.

This asserts no `case_keywords` row IS a bare geographic token (exact, case-insensitive) — so re-adding one turns
the deploy + nightly RED with the offender named. Compound venues like "Mercedes, Camarines Norte" are fine (not a
bare token). To extend coverage, add tokens to BARE_GEO. Deterministic, read-only, creditless.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

# Bare geographic / over-broad tokens in the case geography that must NOT be a matter keyword.
BARE_GEO = {
    "paracale", "camarines norte", "camarines sur", "daet", "mercedes", "manila", "bicol", "luzon",
    "philippines", "pilipinas", "labo", "vinzons", "jose panganiban", "capacuan", "san vicente",
    "cabanbanan", "mambungalon", "manguisoc", "san roque", "barangay", "poblacion", "municipality",
    "province", "estate", "gold",
}


def no_bare_geographic_keywords(cur):
    """No case_keywords row may be a bare geographic/over-broad token (they collide across clients)."""
    cur.execute("SELECT case_file, keyword FROM case_keywords")
    bad = [(r["case_file"], r["keyword"]) for r in cur.fetchall()
           if (r["keyword"] or "").strip().lower() in BARE_GEO]
    if bad:
        raise TruthFailure(
            f"{len(bad)} bare geographic/over-broad keyword(s) in case_keywords — a place collides across "
            f"clients who share geography and cross-files their documents (the Paracale/Camarines-Norte leak): "
            + "; ".join(f"'{k}'→{c}" for c, k in bad)
            + ". A matter keyword must be DISTINCTIVE (proper name / docket / title-no / org), not a bare place. "
            + "Remove it or make it compound+specific (e.g. 'Mercedes, Camarines Norte').")
    print(f"      [case_keywords] no bare geographic keywords across {_count(cur)} matter keywords")


def _count(cur):
    cur.execute("SELECT count(*) AS n FROM case_keywords")
    return cur.fetchone()["n"]


def no_overbroad_keywords(cur):
    """DYNAMIC over-broad guard: a keyword that appears in far MORE other-matters' emails than its own is
    over-broad (an operator name like "Jonathan Zschoche" = 294 cross / 0 own; a generic agency "NCIP" = 64/4)
    and will cross-file on a weak signal. Catches names/agencies/places the static denylist above can't
    enumerate. Threshold: >10 cross-matter appearances AND cross > 5× in-matter."""
    cur.execute("""
        SELECT k.case_file, k.keyword,
          count(*) FILTER (WHERE g.case_file = k.case_file)                                AS in_m,
          count(*) FILTER (WHERE g.case_file <> k.case_file AND coalesce(g.case_file,'') <> '') AS cross_m
        FROM case_keywords k
        JOIN gmail_messages g
          ON position(lower(k.keyword) in lower(coalesce(g.subject,'')||' '||coalesce(g.body_plain,''))) > 0
        GROUP BY k.case_file, k.keyword
        HAVING count(*) FILTER (WHERE g.case_file <> k.case_file AND coalesce(g.case_file,'') <> '') > 10
           AND count(*) FILTER (WHERE g.case_file <> k.case_file AND coalesce(g.case_file,'') <> '')
               > 5 * greatest(count(*) FILTER (WHERE g.case_file = k.case_file), 1)
        ORDER BY cross_m DESC""")
    bad = cur.fetchall()
    if bad:
        raise TruthFailure(
            f"{len(bad)} over-broad keyword(s) in case_keywords — they appear in far more OTHER matters' emails "
            f"than their own (operator names / generic agencies / places), so they cross-file on a weak signal: "
            + "; ".join(f"'{r['keyword']}'→{r['case_file']} ({r['in_m']} own / {r['cross_m']} cross)" for r in bad)
            + ". Replace with a DISTINCTIVE term (specific name / docket / title-no) or remove.")
    print("      [case_keywords] no over-broad keywords (each appears mainly in its own matter)")


TESTS = [
    ("client_separation.case_keywords_no_bare_geo", no_bare_geographic_keywords),
    ("client_separation.case_keywords_not_overbroad", no_overbroad_keywords),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
