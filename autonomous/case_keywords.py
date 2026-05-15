"""case_keywords.py — structured extraction of case-classification keywords.

Source: the prose case-classification rules embedded in /root/landtek/ingest.py
(GPT-4o prompt) plus signals already documented in CLAUDE.md and surfaced
through the 2026-05-13 owners/lot_block_plan/previous_title_numbers triages.

Designed to be:
  - importable from any Python script (scannerpro_ingest, future classifiers,
    retrieval scripts, etc.) for deterministic keyword matching alongside or
    in place of LLM classification;
  - exportable to SQL via build_sql_regex() for use as a new case_scope rule.

Discipline: keywords here are positive signals ONLY. Add a string here when
it's a STRONG indicator that a document/title belongs to a specific case_file.
Don't add weak/ambiguous strings (e.g. "Mercedes" alone — it's the
municipality, present in BOTH cases). Reserve ambiguous terms for the
context-aware case_scope rules.
"""

CASE_KEYWORDS = {
    # ── Civil Case 26-360 / Heirs of Mary Worrick Keesey estate ────────────
    "MWK-001": {
        "people": [
            # The 3 core American co-owners + the mother
            "Mary Worrick Keesey", "Mary W. Keesey", "Heirs of Mary Worrick",
            "Geraldine K. Hoppe", "Geraldine Hoppe",
            "Patricia K. Zschoche", "Patricia Keesee Zschoche", "Patricia Zschoche",
            "Marcia Ellen Keesey", "Marcia Keesey",
            # Spouses (case-relevant for relationship context)
            "Guy Joseph Hoppe", "Edward John Zschoche",
            # Plaintiff representation
            "Atty. Bonifacio Jr. Barandon", "Barandon Law",
            # Plaintiff family
            "Jonathan Zschoche", "Jonathan Paul Zschoche",
            # Fraud-allegation principal
            "Cesar de la Fuente", "Cesar M. de la Fuente", "Cesar dela Fuente",
            # The 20 named transferees (defendants / parties of interest)
            "Gloria Balane", "Alberto Victa", "Ananias Apor", "Arnel Mabeza",
            "Aurora Bernardo", "Cesar Ramirez", "Delfin Gaulit", "Dolores Vela",
            "Edgardo Santiago", "Elsa Illigan", "Erlinda Tychingco",
            "Jose Pascual Jr.", "Librada B. Onrubio", "Maria V. Cereza",
            "Mariquita Era", "Pedro Valledor", "Rosalina Hansol",
            "Roscoe Leaño", "Roscoe Leano", "Ruben Ocan", "Severino Tenorio Jr.",
        ],
        "places": [
            "Mercedes, Camarines Norte",
            "San Roque", "San Roque, Mercedes", "Brgy. San Roque",
            "Daet, Camarines Norte",
            # Manguisoc / Mambungalon excluded — those are sibling-line locations
        ],
        "titles": [
            "T-4497", "TCT-4497", "TCT 4497", "TCT No. 4497",
            "T-32917", "T-32916", "T-31298", "T-52540",
            "T-079-2021002126", "T-079-2021002127", "079-2021002126", "079-2021002127",
            "OCT-106", "OCT No. 106",
            # Lot 2-X-6 sub-subdivisions per CLAUDE.md
            "T-38838", "T-47655", "T-47656", "T-47657", "T-48335", "T-48336",
            "T-49037", "T-49060", "T-49061", "T-49062",
            "T-52354", "T-52536", "T-52537", "T-52538", "T-52539",
            # Survey plan references that anchor MWK chain
            "Psd-256008", "(LRC) Psd-256008", "(LRA) Psd-256008",
            "Psd-051607-014971", "Psd-221861",
        ],
        "case_refs": [
            "Civil Case 26-360", "Civil Case No. 26-360", "26-360",
            "CV-2026-360",
            # Related regulatory matters (Thread 1 ↔ Thread 2/3/4)
            "NOR-CTN SL-2026-0423-1891",  # ARTA case number
        ],
        "concepts": [
            "accion reinvindicatoria",
            "MWK estate", "MWK-001",
            "land transfer fraud", "title fraud",
            "Special Power of Attorney revoked",
            "Register of Deeds, Camarines Norte", "RD Camarines Norte",
            "Heirs of MWK",
            "DILG Mercedes", "ARTA",
        ],
    },

    # ── Paracale-001 / Allan Inocalla mining + land matter ─────────────────
    "Paracale-001": {
        "people": [
            "Allan Inocalla", "Allan V. Inocalla",
        ],
        "places": [
            "Paracale, Camarines Norte", "Paracale",
            # MPSA / mining concession locality
        ],
        "titles": [
            # No specific TCTs listed in CLAUDE.md for this case yet
        ],
        "case_refs": [
            "Paracale-001", "LTC-001",
        ],
        "concepts": [
            "MPSA", "Mineral Production Sharing Agreement",
            "MGB", "Mines and Geosciences Bureau",
            "mining concession", "mining claim",
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────
# Convenience accessors
# ──────────────────────────────────────────────────────────────────────

def flat_keywords(case_file: str) -> list[str]:
    """All distinct keywords for a case_file, across all groups."""
    g = CASE_KEYWORDS.get(case_file, {})
    out = set()
    for group in ("people", "places", "titles", "case_refs", "concepts"):
        out.update(g.get(group, []))
    return sorted(out)


def all_keywords() -> dict[str, list[str]]:
    """Map of case_file → flat keyword list."""
    return {cf: flat_keywords(cf) for cf in CASE_KEYWORDS}


def match_case(text: str, *, min_hits: int = 2) -> tuple[str, int] | tuple[None, int]:
    """Return (case_file, hit_count) if text strongly matches one case,
    else (None, 0). Strong match = at least min_hits distinct keywords
    AND the leading case beats the runner-up by margin >= 2 hits.

    Use this for deterministic pre-classification BEFORE handing to an LLM.
    """
    if not text:
        return (None, 0)
    text_l = text.lower()
    scores: dict[str, int] = {}
    for cf, words in all_keywords().items():
        hits = sum(1 for w in words if w.lower() in text_l)
        scores[cf] = hits
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if ranked[0][1] < min_hits:
        return (None, 0)
    if len(ranked) > 1 and (ranked[0][1] - ranked[1][1]) < 2:
        return (None, ranked[0][1])  # too close to call
    return ranked[0]


def build_sql_regex(case_file: str) -> str:
    """Postgres-flavour regex alternation for use in `text ~* build_sql_regex(...)`."""
    import re
    words = flat_keywords(case_file)
    # word-boundary on both sides, escape regex metas
    escaped = [r'\m' + re.escape(w).replace(r'\ ', r'\s+') + r'\M' for w in words]
    return '|'.join(escaped)


# ──────────────────────────────────────────────────────────────────────
# determine_case_file — single source of truth for case correlation
# Any new-upload pipeline (ScannerPro, Gmail attachment, manual upload,
# evidence-pack input, RAG retrieval filtering) calls THIS.
# ──────────────────────────────────────────────────────────────────────

# Known senders → case_file (high-confidence). Append as discovered.
_GMAIL_FROM_TO_CASE = {
    "barandon_lawoffice@yahoo.com":              "MWK-001",
    "barandonlawoffice.records@gmail.com":       "MWK-001",
}


def determine_case_file(
    text: str | None = None,
    filename: str | None = None,
    gmail_subject: str | None = None,
    gmail_from: str | None = None,
    parties: list[str] | None = None,
    title_numbers: list[str] | None = None,
) -> dict:
    """
    Multi-signal case_file correlator.

    All arguments optional — pass whatever you have. Common shapes:
        determine_case_file(text=pdf_text, filename=file.name)
        determine_case_file(gmail_from=msg.from_addr, gmail_subject=msg.subject,
                            text=msg.body_plain)
        determine_case_file(filename=fn, title_numbers=['T-32917','T-52540'])

    Returns:
      {
        "case_file":  "MWK-001" | "Paracale-001" | "unknown",
        "confidence": float 0.0-1.0,
        "method":     "single_signal" | "composite" | "sender_map" | "unknown",
        "signals":    list of (signal_type, case_file, weight) tuples
      }

    Confidence is a rough scaling of total weighted hits; treat ≥0.5 as
    "confident enough to set case_file deterministically", <0.5 as "let
    the LLM classifier decide".
    """
    signals: list[tuple[str, str, int]] = []

    # 1. Known-sender lookup (highest single-signal weight)
    if gmail_from:
        for addr, cf in _GMAIL_FROM_TO_CASE.items():
            if addr.lower() in gmail_from.lower():
                signals.append(("gmail_from_known_sender", cf, 10))
                break

    # 2. Body-text keyword match (need ≥2 hits + 2-margin per match_case rule)
    if text:
        cf, hits = match_case(text, min_hits=2)
        if cf:
            signals.append(("text_keywords", cf, hits))

    # 3. Filename keyword match (looser threshold — filenames are short)
    if filename:
        cf, hits = match_case(filename, min_hits=1)
        if cf:
            signals.append(("filename_keywords", cf, hits + 1))  # filename bonus

    # 4. Gmail subject keyword match
    if gmail_subject:
        cf, hits = match_case(gmail_subject, min_hits=1)
        if cf:
            signals.append(("gmail_subject", cf, hits + 1))

    # 5. Title-number exact match (very strong if the doc cites a known TCT)
    if title_numbers:
        for cf, kw_groups in CASE_KEYWORDS.items():
            for tct in title_numbers:
                for known in kw_groups.get("titles", []):
                    if tct.strip().upper() == known.upper():
                        signals.append(("title_number_match", cf, 4))
                        break

    # 6. Named-parties match against case people list
    if parties:
        for cf, kw_groups in CASE_KEYWORDS.items():
            people = kw_groups.get("people", [])
            people_l = [p.lower() for p in people]
            for party in parties:
                pl = (party or "").lower()
                if pl and any(pl in pn or pn in pl for pn in people_l):
                    signals.append(("party_match", cf, 2))
                    break

    if not signals:
        return {"case_file": "unknown", "confidence": 0.0,
                "method": "unknown", "signals": []}

    # Vote-count per case_file
    votes: dict[str, int] = {}
    for _, cf, w in signals:
        votes[cf] = votes.get(cf, 0) + w
    top_case = max(votes, key=votes.get)
    top_score = votes[top_case]
    runner_up = max((s for c, s in votes.items() if c != top_case), default=0)

    # If the top is tied with runner-up, treat as ambiguous
    if top_score - runner_up < 2:
        return {"case_file": "unknown", "confidence": 0.0,
                "method": "ambiguous", "signals": signals}

    # Scale confidence: 1 strong sender signal ≈ 1.0; a single 2-hit
    # text match ≈ 0.4; composite of several signals climbs fast.
    confidence = min(1.0, top_score / 10.0)
    method = ("sender_map" if any(s[0] == "gmail_from_known_sender" for s in signals)
              else "composite" if len(signals) > 1
              else "single_signal")
    return {"case_file": top_case, "confidence": round(confidence, 2),
            "method": method, "signals": signals}


# ──────────────────────────────────────────────────────────────────────
# Self-test (run: python3 case_keywords.py)
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    summary = {cf: len(flat_keywords(cf)) for cf in CASE_KEYWORDS}
    print("Keyword counts per case_file:")
    for cf, n in summary.items():
        print(f"  {cf}: {n} distinct keywords")

    # Quick spot-checks
    samples = [
        ("Heirs of Mary Worrick Keesey filed accion reinvindicatoria against Gloria Balane in Civil Case 26-360",
         "MWK-001"),
        ("Allan Inocalla MPSA application for Paracale mining concession reviewed by MGB",
         "Paracale-001"),
        ("Random affidavit about a notary commission with no case context",
         None),
    ]
    print("\nmatch_case() self-test:")
    for text, expected in samples:
        got, hits = match_case(text)
        ok = "✓" if got == expected else "✗"
        print(f"  {ok} expected={expected!r} got={got!r} hits={hits}  | {text[:60]}…")

    print("\ndetermine_case_file() self-test (multi-signal):")
    composite_samples = [
        # text + filename → composite MWK
        {"text": "Re: pretrial Civil Case 26-360 Zschoche v Balane",
         "filename": "2026-05-08 Reply.pdf",
         "expected_case": "MWK-001"},
        # gmail sender alone (sender_map)
        {"gmail_from": "barandon_lawoffice@yahoo.com",
         "gmail_subject": "Compliance",
         "expected_case": "MWK-001"},
        # title-number only
        {"title_numbers": ["T-32917"], "filename": "scan.pdf",
         "expected_case": "MWK-001"},
        # Paracale composite
        {"text": "Allan Inocalla MPSA renewal at MGB Camarines Norte for Paracale mining",
         "filename": "MPSA_2026.pdf",
         "expected_case": "Paracale-001"},
        # ambiguous (Mercedes alone)
        {"text": "Municipality of Mercedes documents",
         "expected_case": "unknown"},
    ]
    for s in composite_samples:
        expected = s.pop("expected_case")
        result = determine_case_file(**s)
        ok = "✓" if result["case_file"] == expected else "✗"
        print(f"  {ok} expected={expected!r} got={result['case_file']!r} "
              f"conf={result['confidence']} method={result['method']}")
