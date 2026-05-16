#!/usr/bin/env python3
"""OCR-tolerant pattern library — single source of truth for entity-extraction regex.

Per architecture review 2026-05-16: every script that extracts an identifier
(case number, TCT, PE number, date, peso amount) imports from here. No more
"I forgot the line break" bugs.

All patterns:
  • Tolerate whitespace including line breaks within identifiers (\\s+ not  ).
  • Tolerate dash variants (- –, em-dash, NBSP-hyphen).
  • Tolerate digit OCR errors when noted (e.g., '0' vs 'O', '1' vs 'l' vs 'I').
  • Normalize output via canonical functions.

Usage:
    from patterns import ARTA_CASE_PATTERN, normalize_arta_case, find_all_arta_cases
    matches = find_all_arta_cases(extracted_text)
    for m in matches:
        canonical = normalize_arta_case(m)
"""
import re

# ─── Whitespace / dash tolerance helpers ──────────────────────────────────
# Match any whitespace (incl. newline) or dash variant between tokens.
_SEP = r"[\s\-–— ]*"

# ─── ARTA case number ─────────────────────────────────────────────────────
# Canonical: CTN SL-YYYY-MMDD-NNNN  (e.g., CTN SL-2026-0218-1378)
# Tolerates: line break anywhere, missing dashes, no space after CTN.
ARTA_CASE_PATTERN = re.compile(
    rf"\bCTN{_SEP}SL{_SEP}(\d{{4}}){_SEP}(\d{{4}}){_SEP}(\d{{4}})\b",
    re.IGNORECASE,
)
# Sometimes appears as "NOR-CTN SL-..." for referral notices
ARTA_REFERRAL_PATTERN = re.compile(
    rf"\bNOR{_SEP}CTN{_SEP}SL{_SEP}(\d{{4}}){_SEP}(\d{{4}}){_SEP}(\d{{4}})\b",
    re.IGNORECASE,
)

def find_all_arta_cases(text: str) -> list[str]:
    """Return canonical 'CTN SL-YYYY-MMDD-NNNN' for every ARTA case in text."""
    if not text:
        return []
    seen = set()
    out = []
    for pat in (ARTA_CASE_PATTERN, ARTA_REFERRAL_PATTERN):
        for m in pat.finditer(text):
            canonical = f"CTN SL-{m.group(1)}-{m.group(2)}-{m.group(3)}"
            if canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
    return out

def normalize_arta_case(raw: str) -> str | None:
    """Coerce any ARTA case string to canonical form."""
    if not raw:
        return None
    m = re.fullmatch(rf"(NOR{_SEP})?CTN{_SEP}SL{_SEP}(\d{{4}}){_SEP}(\d{{4}}){_SEP}(\d{{4}})",
                     raw.strip(), re.IGNORECASE)
    if not m:
        return None
    return f"CTN SL-{m.group(2)}-{m.group(3)}-{m.group(4)}"

# ─── TCT / OCT title number ──────────────────────────────────────────────
# Canonical formats:
#   T-XXXX            (most TCTs)
#   T-XXXXXX          (post-2018 large series)
#   T-079-2021NNNNNN  (post-RA 11231 e-title series)
#   OCT-NNNN
TCT_PATTERN = re.compile(
    # Match either compound (NNN-NNNNNNNNNN) for post-2018 e-titles, or simple (NN-NNNNNNN) for legacy
    rf"\b(T|TCT|OCT){_SEP}(?:No\.?{_SEP})?(\d{{2,3}}{_SEP}-{_SEP}\d{{4,12}}|\d{{2,7}})\b",
    re.IGNORECASE,
)

def find_all_tct_numbers(text: str) -> list[str]:
    if not text:
        return []
    out = []
    seen = set()
    for m in TCT_PATTERN.finditer(text):
        # Strip whitespace but PRESERVE structural dashes (T-079-2021002126).
        num = re.sub(r"\s+", "", m.group(2))
        # Normalize dash variants to ASCII hyphen
        num = re.sub(r"[–—]", "-", num)
        canonical = f"T-{num}"
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out

# ─── PE number (Memorandum of Encumbrances Entry) ────────────────────────
# Canonical: PE-NNNNNN-NN-NN (e.g., PE-184535-167-20)
PE_PATTERN = re.compile(
    rf"\bPE{_SEP}-?{_SEP}(\d{{3,6}})(?:{_SEP}-?{_SEP}(\d{{1,4}}))?(?:{_SEP}-?{_SEP}(\d{{1,4}}))?\b",
    re.IGNORECASE,
)

# ─── Dates ───────────────────────────────────────────────────────────────
# Tolerates: "March 17, 1988", "17 March 1988", "03/17/1988", "1988-03-17",
#            "17-Mar-1988", "March 17 1988" (no comma).
_MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_ISO_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DATE_MDY_PATTERN = re.compile(rf"\b{_MONTHS}\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.IGNORECASE)
DATE_DMY_PATTERN = re.compile(rf"\b(\d{{1,2}})\s+{_MONTHS},?\s+(\d{{4}})\b", re.IGNORECASE)
DATE_SLASH_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")

# ─── Philippine peso amount ──────────────────────────────────────────────
# Tolerates ₱, P, PHP, Php, with commas, decimals optional.
PHP_AMOUNT_PATTERN = re.compile(
    r"(?:₱|PHP\s?|Php\s?|P\s?)\s*([\d,]+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# ─── Civil/Criminal docket numbers ───────────────────────────────────────
# CV-YYYY-NNN  or  Civil Case No. NN-NNN
CIVIL_CASE_PATTERN = re.compile(
    rf"(?:Civil{_SEP}Case{_SEP}(?:No\.?{_SEP})?|CV{_SEP}-?{_SEP})(\d{{2,4}}){_SEP}-?{_SEP}(\d{{2,5}})",
    re.IGNORECASE,
)

# ─── Person spelling variants (Cesar de la Fuente / Cesar de la Puente) ──
CESAR_VARIANTS_PATTERN = re.compile(
    r"\bCesar\s+[MN]?\.?\s*(?:dela|de\s+la)\s+[FP]uente\b",
    re.IGNORECASE,
)


# ─── Helpers ─────────────────────────────────────────────────────────────
def canonicalize_whitespace(s: str) -> str:
    """Collapse all whitespace (incl. newlines) to single spaces. For comparison only."""
    return re.sub(r"\s+", " ", s).strip()


if __name__ == "__main__":
    # Self-test against the known-tricky cases
    test_text = """
    ARTA Case No. CTN SL-2026-0218-
    1378  (Count) (Distinct from CTN SL-2025-1008-
    0690 & 1104-0792)

    Mary Worrick Keesey died March 17, 1988.
    T-4497, T-079-2021002126, PE-184535-167-20.
    Php 7,000.00 consideration. Civil Case No. 26-360.
    Cesar M. de la Puente vs. Cesar de la Fuente — spelling variants.
    """
    print("=== Self-test patterns.py ===")
    print("ARTA cases found:", find_all_arta_cases(test_text))
    print("TCTs found:", find_all_tct_numbers(test_text))
    print("Cesar variants:", CESAR_VARIANTS_PATTERN.findall(test_text))
    m = DATE_MDY_PATTERN.search(test_text)
    print(f"Date MDY: {m.group(0) if m else None}")
    print("Civil case:", CIVIL_CASE_PATTERN.findall(test_text))
