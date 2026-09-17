#!/usr/bin/env python3
"""Classify cached page text into civil-registry / identity document hits.

A page qualifies only on a STRONG title-line match (the form's own heading),
never on a passing mention like "date of death" inside a pleading.  PSA/LCR
"negative certifications" are captured too, but flagged NEGATIVE — they prove
a record is MISSING and must never be presented as the document itself.
"""
import json, re, sys

PAGES, OUT = sys.argv[1], sys.argv[2]

STRONG = [
    ("DEATH_CERT", [r"CERTIFICATE\s+OF\s+DEATH", r"CERTIFICATION\s+OF\s+DEATH",
                    r"FACTS\s+OF\s+DEATH", r"REGISTER\s+OF\s+DEATHS",
                    r"CIVIL\s+REGISTRY\s+FORM\s+2-?A", r"DEATH\s+AVAILABLE",
                    r"RECORD\s+OF\s+DEATH\s+OF", r"VITAL\s+STATISTICS\s+AGENCY"]),
    ("BIRTH_CERT", [r"CERTIFICATE\s+OF\s+LIVE\s+BIRTH", r"CERTIFICATE\s+OF\s+BIRTH",
                    r"BIRTH\s+CERTIFICATE", r"CERTIFICATION\s+OF\s+BIRTH",
                    r"FACTS\s+OF\s+BIRTHS?", r"REGISTER\s+OF\s+BIRTHS",
                    r"CIVIL\s+REGISTRY\s+FORM\s+1-?A", r"BIRTH\s+AVAILABLE",
                    r"RECORD\s+OF\s+BIRTH\s+OF", r"REPORT\s+OF\s+BIRTH",
                    r"CERTIFICADO\s+DE\s+NACIMIENTO", r"PAGREREHISTRO\s+NG\s+KAPAN",
                    r"DELAYED\s+REGISTRATION\s+OF\s+BIRTH"]),
    ("MARRIAGE_CERT", [r"CERTIFICATE\s+OF\s+MARRIAGE", r"MARRIAGE\s+CONTRACT",
                       r"CONTRACT\s+OF\s+MARRIAGE", r"FACTS\s+OF\s+MARRIAGE",
                       r"REGISTER\s+OF\s+MARRIAGES", r"RECORD\s+OF\s+MARRIAGE\s+OF"]),
    ("ID_PASSPORT", [r"\bPASSPORT\b", r"PASAPORTE", r"PASSEPORT"]),
    ("ID_DRIVER", [r"DRIVER'?S?\s+LICEN[SC]E", r"LAND\s+TRANSPORTATION\s+OFFICE"]),
    ("ID_UMID", [r"UNIFIED\s+MULTI-?PURPOSE", r"\bUMID\b"]),
    ("ID_PHILHEALTH", [r"PHILHEALTH", r"PHIL\s*HEALTH"]),
    ("ID_OTHER", [r"POSTAL\s+ID", r"VOTER'?S?\s+(ID|CERTIFICATION)", r"SENIOR\s+CITIZEN",
                  r"NBI\s+CLEARANCE", r"BARANGAY\s+ID", r"\bOSCA\b"]),
]
APPLICATION = re.compile(
    r"APPLICATION\s+FORM|REQUEST\s+FOR\s*:?\s*\[?\s*(BIRTH|DEATH|MARRIAGE)|"
    r"OWNER'?S\s+PERSONAL\s+INFORMATION|OFFICIAL\s+RECEIPT|ACCOUNTABLE\s+FORM|"
    r"NUMBER\s+OF\s+COPIES", re.I)
NEGATIVE = re.compile(r"NEGATIVE\s+CERTIFICATION|DO\s+NOT\s+HAVE\s+ANY\s+RECORD|"
                      r"NO\s+RECORD\s+OF\s+(BIRTH|DEATH|MARRIAGE)", re.I)

NAMES = ["SENEN", "BEATRIZ", "BEATRIS", "VICENTE", "ALLAN", "ALAN", "ALLEN", "FRANCISCO",
         "JESUS", "CASPER", "CIPRIANA", "MARILOU", "HERBERT", "MELVIN", "MELWYN",
         "ROBERT", "ELENA", "HELEN", "SHISHIR", "GERALDINE", "LIPRIAN", "JENIN"]
ALIAS = {"BEATRIS": "BEATRIZ", "ALAN": "ALLAN", "ALLEN": "ALLAN", "MELWYN": "MELVIN"}
# OCR mangles the surname badly on handwritten forms (INOCHILA, TNOCATLA), so
# match it loosely on the letter shapes that actually get confused.
SURNAME = re.compile(r"[IT1]N[O0][CGQ][AH4]?[LIT1][LIT1][A4]|INOCALA", re.I)

REGISTRY_RE = re.compile(r"REGISTRY\s*(?:NUMBER|N[O0]\.?)\s*[:\-]?\s*"
                         r"((?:19|20)\d{2}\s*[-–]\s*\d{1,5}|\d{1,5}\b)", re.I)
DATE_RE = re.compile(r"\b(\d{1,2}\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s*,?\s*(?:18|19|20)\d{2}"
                     r"|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?\s+\d{1,2}\s*,?\s*(?:18|19|20)\d{2})\b", re.I)
CIVIL = {"DEATH_CERT", "BIRTH_CERT", "MARRIAGE_CERT"}
# a civil-registry page must also show it came from a registry
ANCHOR = re.compile(r"CIVIL\s+REGISTRAR|CIVIL\s+REGISTRY|REGISTRY\s+N|MUNICIPAL\s+FORM|"
                    r"OCRG|PHILIPPINE\s+STATISTICS\s+AUTHORITY|NATIONAL\s+STATISTICS|"
                    r"\bPSA\b|\bNSO\b|VITAL\s+STATISTICS\s+AGENCY|REGISTRATION\s*N[O0]", re.I)

out = open(OUT, "w")
n_pages = n_hits = 0
for line in open(PAGES):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if "text" not in r:
        continue
    n_pages += 1
    up = " ".join(r["text"].upper().split())
    types = [label for label, pats in STRONG if any(re.search(p, up) for p in pats)]
    if set(types) & CIVIL and not ANCHOR.search(up):
        types = [t for t in types if t not in CIVIL]
    # The tree is the Inocalla client folder, so a registry form here belongs to
    # this family even when OCR mangles the surname ("TNOCATLA").  Bare IDs still
    # need the surname, or every third party's ID in the tree lands in the index.
    if not (set(types) & CIVIL) and not SURNAME.search(up):
        continue
    if not types:
        continue
    names = sorted({ALIAS.get(n, n) for n in NAMES if re.search(rf"\b{n}\b", up)})
    # a registry page with no family name at all is somebody else's record
    if (set(types) & CIVIL) and not names and not SURNAME.search(up):
        continue
    json.dump({
        "file": r["file"], "page": r["page"], "types": types, "names": names,
        "negative": bool(NEGATIVE.search(up)),
        "application_only": bool(APPLICATION.search(up)),
        "registry_no": [m.group(1) for m in REGISTRY_RE.finditer(up)][:3],
        "dates": [re.sub(r"\s+", " ", m.group(1)) for m in DATE_RE.finditer(up)][:6],
        "snippet": up[:500],
    }, out)
    out.write("\n")
    n_hits += 1
out.close()
print(f"pages scanned: {n_pages}   hit pages: {n_hits}")
