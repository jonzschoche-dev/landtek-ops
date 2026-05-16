"""Bilingual (Filipino + English) keyword expansion for corpus search.

Has TWO modes per concept: HIGH-precision (unambiguous, rare-in-noise) vs full set.
High-precision Filipino terms ('patay', 'namatay') rarely appear in non-target context, so
they're worth 3-5x more than ambiguous English terms ('late' / 'died' in compounds).

Used by truth_negotiator, classify_execution_status, classify_case_stage,
self_research, and any module that searches the corpus for concepts.

Reason: PH judicial affidavits and pleadings often use Tagalog for
substantive testimony. English-only search misses facts (e.g., Cesar de la
Fuente death status buried in 'Patay na po' — missed by English regex).

Use:
    from bilingual_search import expand, sql_or_clauses
    patterns = expand('dead')
    clauses, params = sql_or_clauses('extracted_text', 'dead')
"""
import re

# Concept → HIGH-precision keyword set (low false-positive rate, rare in noise).
# These should be weighted MUCH more than the broader PAIRS set.
HIGH_PRECISION = {
    "dead":      ["patay", "namatay", "yumao", "namayapa", "sumakabilang-buhay",
                  "pumanaw", "deceased", "predeceased", "late Cesar", "late "],
    "alive":     ["nabubuhay", "buhay pa"],
    "signed":    ["nilagdaan", "lumagda", "pumirma"],
    "notarized": ["subscribed and sworn", "acknowledged before me", "notary public"],
    "sale":      ["deed of absolute sale", "kasulatan ng bilihan"],
    "revoked":   ["binawi", "kinansela", "pinawalang-bisa", "pinawalang bisa", "revoked the authority"],
    "complaint": ["isinampa ng reklamo", "verified complaint", "complaint-affidavit"],
}

# Concept → both-language keyword set
PAIRS = {
    "dead": [
        # English
        "dead", "deceased", "died", "death", "late", "passed away", "expired",
        "no longer with us", "predeceased",
        # Filipino / Tagalog / Bicolano
        "patay", "namatay", "yumao", "namayapa", "sumakabilang-buhay", "pumanaw",
        "namaalam", "naunang yumao", "patay na",
    ],
    "alive": [
        "alive", "living", "still living", "currently living",
        "buhay", "nabubuhay", "buhay pa",
    ],
    "signed": [
        "signed", "executed", "subscribed",
        "nilagdaan", "lumagda", "pumirma", "lagda", "lumalagda", "ipinilagda",
    ],
    "notarized": [
        "notarized", "notarial", "acknowledged before me", "subscribed and sworn",
        "binisita ng notaryo", "pinatibayan", "nilagdaan sa harap ng notaryo",
    ],
    "received": [
        "received", "got", "took receipt of",
        "natanggap", "tinanggap", "tinaggap",
    ],
    "sold": [
        "sold", "purchased", "transferred for value",
        "naipagbili", "ipinagbili", "binili", "binibili",
    ],
    "owner": [
        "owner", "registered owner", "title-holder",
        "may-ari", "mga may-ari", "ang may-ari",
    ],
    "land": [
        "land", "property", "real property", "parcel",
        "lupa", "lupain", "ari-arian", "lupang", "ari-ariang lupa", "lote",
    ],
    "heir": [
        "heir", "successor", "co-heir",
        "tagapagmana", "mga tagapagmana", "magmamana", "tagapagmana ng lupa",
    ],
    "father": ["father", "dad", "ama", "ang aking ama", "tatay"],
    "son":    ["son", "anak", "anak na lalaki"],
    "mother": ["mother", "mom", "ina", "ang aking ina", "nanay"],
    "witness": [
        "witness", "witnesses",
        "saksi", "tagasaksi", "mga saksi",
    ],
    "court": [
        "court", "tribunal",
        "hukuman", "korte", "ang korte",
    ],
    "filed": [
        "filed", "filing", "lodged",
        "isinampa", "isinumpa", "isinusumpa", "isumpa", "nakapagsampa",
    ],
    "revoked": [
        "revoked", "cancelled", "withdrew", "rescinded",
        "binawi", "kinansela", "pinawalang-bisa", "pinawalang bisa",
    ],
    "authority": [
        "authority", "power", "mandate", "right",
        "kapangyarihan", "awtoridad", "karapatan", "ipinagkaloob na karapatan",
    ],
    "sworn": [
        "sworn", "under oath", "duly sworn", "having been duly sworn",
        "sumumpa", "nakapanunumpa", "nanunumpa", "kasalukuyang sumusumpa",
    ],
    "true": [
        "true", "truthful", "veracity",
        "totoo", "katotohanan", "makatotohanan", "tama",
    ],
    "false": [
        "false", "untrue", "perjury",
        "huwad", "kasinungalingan", "sinungaling", "pagsisinungaling",
    ],
    "paid": [
        "paid", "settled", "remitted",
        "nagbayad", "binayaran", "binabayaran", "ipinagbayad",
    ],
    "tax": [
        "tax", "RPT", "real property tax", "assessment",
        "buwis", "buwis sa lupa", "buwis sa ari-arian",
    ],
    "sale": [
        "sale", "deed of absolute sale", "absolute sale",
        "bilihan", "pagbibili", "kasulatan ng bilihan",
    ],
    "donate": [
        "donation", "donate", "donated",
        "donasyon", "pagdodonate", "ipinagkaloob bilang donasyon",
    ],
    "complaint": [
        "complaint", "filing of complaint", "verified complaint",
        "reklamo", "isinampa ng reklamo", "demanda",
    ],
}

# Reverse index: synonym → concept (for query interpretation)
SYNONYM_TO_CONCEPT = {}
for concept, words in PAIRS.items():
    for w in words:
        SYNONYM_TO_CONCEPT[w.lower()] = concept


def concept_of(word):
    """Given a word, return its concept (or the word itself if unknown)."""
    w = word.lower().strip()
    return SYNONYM_TO_CONCEPT.get(w, w)


def expand(concept_or_word):
    """Return the bilingual keyword set for a concept (or for the word's concept)."""
    key = concept_or_word.lower().strip()
    if key in PAIRS:
        return list(PAIRS[key])
    c = SYNONYM_TO_CONCEPT.get(key)
    if c:
        return list(PAIRS[c])
    return [key]  # unknown — return as-is


def expand_high_precision(concept_or_word):
    """Return only HIGH-precision keywords (rare-in-noise) for a concept."""
    key = concept_or_word.lower().strip()
    if key in HIGH_PRECISION:
        return list(HIGH_PRECISION[key])
    c = SYNONYM_TO_CONCEPT.get(key)
    if c and c in HIGH_PRECISION:
        return list(HIGH_PRECISION[c])
    return []


def sql_or_clauses(column, concept_or_word, prefix_wildcard=True, suffix_wildcard=True):
    """Build (sql_fragment, params) tuple for SQL ILIKE-OR pattern.

    e.g., sql_or_clauses('extracted_text', 'dead') →
      ('(extracted_text ILIKE %s OR extracted_text ILIKE %s OR ...)', ['%dead%','%deceased%',...])
    """
    patterns = expand(concept_or_word)
    fragments = []
    params = []
    for p in patterns:
        pat = p
        if prefix_wildcard: pat = "%" + pat
        if suffix_wildcard: pat = pat + "%"
        fragments.append(f"{column} ILIKE %s")
        params.append(pat)
    return f"({' OR '.join(fragments)})", params


def search_concepts_in_text(text):
    """Reverse: scan a text snippet and return which concepts hit (with the matched word)."""
    text_lower = text.lower()
    hits = {}
    for concept, words in PAIRS.items():
        for w in words:
            if w.lower() in text_lower:
                hits.setdefault(concept, []).append(w)
                break
    return hits


if __name__ == "__main__":
    # Self-test
    print("== expand('dead') ==")
    print(expand("dead"))
    print()
    print("== sql_or_clauses for 'signed' ==")
    sql, p = sql_or_clauses("extracted_text", "signed")
    print(sql)
    print(p)
    print()
    print("== concept of 'patay' ==")
    print(concept_of("patay"))
    print()
    print("== concepts hit in sample Filipino sentence ==")
    s = "Asan na ang iyong ama? Patay na po. Nilagdaan niya ang kasulatan ng bilihan bago siya namatay."
    print(s)
    print(search_concepts_in_text(s))
