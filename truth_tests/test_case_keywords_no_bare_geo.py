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


TESTS = [
    ("client_separation.case_keywords_no_bare_geo", no_bare_geographic_keywords),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
