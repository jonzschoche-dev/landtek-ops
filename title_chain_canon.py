"""title_chain_canon.py — Codified canonical trunk-title knowledge.

Source of truth for "which titles are the real operative anchors" — separate
from `title_chain` table data (which has OCR-driven noise, missing edges, and
suspect provenance). Chain walkers, evidence renderers, and case-theory
output should consult this module BEFORE walking DB edges.

Mirrors `memory/project_title_origins_mwk.md` § "Trunk & ghost title registry"
(authored by Jonathan, 2026-05-21).

Why this exists:
  The title_chain table has rows like:
    OCT T-106 → T-4497    (provenance=verified, source_doc_id=NULL)
    OCT T-106 → T-111     (provenance=inferred_weak, source_doc_id=NULL)
  Chronologically T-111 (1912) PREDATES OCT T-106 (1934), so the direct
  OCT T-106 → T-4497 edge is a flattened/shortcut artifact, not real lineage.
  Walking the chain naively defaults to OCT T-106 as the root — wrong.
  The system needs to know a priori that T-111 is the operative root and
  T-106 references are ghost.
"""

# Per-matter operative root titles. When a chain walker reaches one of these,
# it stops surfacing further ancestors (regardless of what DB edges claim).
OPERATIVE_ROOTS = {
    "MWK-001": "T-111",
}

# Trunk-title metadata. When a walker presents one of these in output, include
# the metadata so evidence is defensible without separate lookups.
TRUNKS = {
    "T-111": {
        "issued": "1912 (Jonathan-asserted; primary doc retrieval pending)",
        "owners_at_issuance": ["Mary Worrick", "Helen Worrick", "Alice Worrick"],
        "area": "26.9312 ha, Mercedes, Camarines Norte, bounded NE by Pacific Ocean",
        "source_of_assertion": "doc#279 1953 Deed-of-Donation recital + Jonathan's domain knowledge",
        "primary_doc_in_corpus": False,
        "operative_for": ["MWK-001"],
        "notes": "Earliest documented title in MWK chain. The 1953 donation to "
                 "Mercedes municipality references T-111 as the title-of-record.",
    },
    "T-4497": {
        "issued": "1964-06-02",
        "source_of_assertion": "doc#382 (government_issued, OCR-damaged)",
        "primary_doc_in_corpus": True,
        "operative_for": ["MWK-001"],
        "canonical_parent": "T-111",  # NOT recorded as an edge in title_chain
        "notes": "Mary's mother title — relationship to T-111 partition not yet "
                 "fully mapped in title_chain. Add edge T-111 → T-4497 when "
                 "source instrument is retrieved.",
    },
}

# Ghost titles — referenced widely in extractions but no operative document
# in corpus. Walkers should NEVER present these as operative roots.
GHOST_TITLES = {
    "OCT T-106": {
        "status": "ghost",
        "reason": (
            "Cross-cited in 5+ TCT extractions as 'originally registered'. "
            "Physical OCT document NOT in corpus. Chronologically POST-dates "
            "T-111 (1934 vs 1912), so 'OCT T-106 → T-4497' / 'OCT T-106 → T-111' "
            "edges in title_chain are likely OCR/extraction artifacts."
        ),
        "do_not_present_as_root": True,
        "real_operative_root": "T-111",
    },
}

# Common OCR / normalization variants that should canonicalize to OCT T-106.
# When a walker encounters one of these as a parent_title, treat it as a ghost.
GHOST_ALIASES = {
    "T-106": "OCT T-106",
    "1-106": "OCT T-106",  # OCR misread O as 1
    "F-106": "OCT T-106",  # OCR misread O as F
}


def canonicalize_ghost(title):
    """If title is a ghost-alias variant, return canonical ghost form. Else None."""
    if title in GHOST_ALIASES:
        return GHOST_ALIASES[title]
    if title in GHOST_TITLES:
        return title
    return None


def is_ghost(title):
    """True if title is a ghost (referenced but not anchored)."""
    return title in GHOST_TITLES or title in GHOST_ALIASES


def operative_root_for(matter_code):
    """Return the operative root title for a matter, or None if unspecified."""
    return OPERATIVE_ROOTS.get(matter_code)


def trunk_metadata(title):
    """Return trunk metadata dict if title is a known trunk, else None."""
    return TRUNKS.get(title)
