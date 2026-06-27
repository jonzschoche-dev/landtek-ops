#!/usr/bin/env python3
"""law_coverage.py — monitor the law library's coverage vs what the matters NEED, so the "source of truth
embedded in the law" stays complete. Reports, per needed provision, whether its text is in legal_chunks
(keyword-probed) and flags the gaps to embed. Also scans the playbooks for cited acts not yet embedded. $0.

  python3 scripts/law_coverage.py
"""
import glob
import os
import re
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=45", "root@100.85.203.58"]

# What the active matters need. Each: (label, why, probe-keywords [ALL present in one chunk], citation-scope).
NEEDED = [
    ("RA 11032 §21", "ARTA — the punishable acts (the records-refusal core)", ["Imposition of additional requirements"], ""),
    ("RA 7160 §472", "LGC — Municipal ASSESSOR: appointment, qualifications & DUTIES (assessment records, furnish)", ["assessor"], "7160"),
    ("RA 7160 §470", "LGC — Municipal TREASURER: appointment & DUTIES (custody of funds, collection, records)", ["proper management of the funds"], "7160"),
    ("RA 7160 §444", "LGC — Municipal MAYOR: powers & duties (ensure delivery of services; maintain/clear roads)", ["general supervision and control over all programs"], "7160"),
    ("RA 7160 §§201-207", "LGC — real-property assessment: assessment roll & tax declarations (the records sought)", ["assessment roll"], "7160"),
    ("RA 7160 §§60-67", "LGC — disciplinary grounds for local elective officials", ["disciplinary"], "7160"),
    ("RA 7160 §§25,29", "LGC — general supervision over LGUs (DILG)", ["general supervision"], "7160"),
    ("RA 3019 §3(e)/(f)", "Anti-Graft — undue injury / neglect", ["undue injury"], ""),
    ("RA 6713 §4(a)/§5", "Code of Conduct — public interest; act promptly", ["uphold the public interest"], ""),
    ("RA 6770 §24", "Ombudsman Act — preventive suspension", ["preventively suspend"], ""),
    ("PD 1445 §4/§103", "Govt Auditing Code — public-purpose / personal liability", ["solely for public purposes"], ""),
    ("RPC Arts 217/220", "Malversation / technical malversation", ["other than that for which"], ""),
    ("RA 9485", "Anti-Red Tape Act 2007 (RA 11032 predecessor)", ["Anti-Red Tape Act"], ""),
    ("Const. Art III §9", "Just compensation (inverse condemnation)", ["just compensation"], "Civil"),
    # ── officer duties: the BUILDING OFFICIAL (Engr. Balane) ──
    ("PD 1096 §203/§301", "National Building Code — BUILDING OFFICIAL duties; building permits & records (the Engineer cases' measure)", ["building official"], "1096"),
    # ── the Sangguniang Bayan's own rules ──
    ("RA 7160 §§446-447", "LGC — SANGGUNIANG BAYAN: composition & powers", ["sangguniang bayan"], "446"),
    ("RA 7160 §49", "LGC — presiding officer of the sanggunian (Vice-Mayor)", ["presiding officer"], "7160"),
    ("RA 7160 §50", "LGC — Sanggunian INTERNAL RULES OF PROCEDURE (how the SB must operate)", ["internal rules of procedure"], "7160"),
    # ── prevailing OVERSIGHT BODIES & their mandates over the office heads ──
    ("DILG oversight", "Oversight: DILG general supervision & discipline over LGUs/officials (RA 7160 §§25,29,60-67)", ["general supervision"], "7160"),
    ("DPWH / Building Official oversight", "Oversight: DPWH Secretary as Building Official + supervision of local building officials (PD 1096)", ["secretary of public works"], "1096"),
    ("Ombudsman oversight", "Oversight: the Ombudsman over all public officers (RA 6770)", ["preventively suspend"], ""),
    ("CSC oversight", "Oversight: Civil Service Commission over appointive/career officials (RACCS)", ["grave misconduct"], "RACCS"),
    ("COA oversight", "Oversight: Commission on Audit over public funds (PD 1445 personal liability)", ["personal liability"], "1445"),
    # ── the ACCOUNTANT + the BUDGET / DISBURSEMENT pipeline (the ₱2.6M spend) ──
    ("RA 7160 §474", "LGC — Municipal ACCOUNTANT: certify availability of funds, keep accounts, the disbursement record", ["accountant"], "7160"),
    ("RA 7160 fiscal §§305-354", "LGC — local fiscal administration: appropriations ordinance, budget, DISBURSEMENT pipeline", ["no money shall be disbursed"], "7160"),
    ("RA 9184 (procurement/BAC)", "Government Procurement Reform Act — the BAC & procurement pipeline (the ₱2.6M; Balane as BAC Chair)", ["bids and awards committee"], "9184"),
    # ── BARANGAY services & officials for property owners ──
    ("RA 7160 §389 (Punong Barangay)", "LGC — Punong Barangay duties; barangay clearances/certifications for residents & property owners", ["punong barangay"], "7160"),
    ("RA 7160 §§399-412 (Katarungang Pambarangay)", "LGC — barangay justice: Lupong Tagapamayapa conciliation (prerequisite to many property suits)", ["lupon"], "7160"),
    # ── the APPEAL / correction-path forum: the Office of the President ──
    ("AO 22 s.2011 (OP appeals)", "Office of the President — CURRENT appeal rules (repealed AO 18): 15-day period, P1,500 fee, stay, finality", ["appeal to the office of the president"], ""),
    ("OP review authority", "President's power of control (Const Art VII §17) — basis for supervisory review/corrective action over ARTA", ["control of all the executive"], ""),
]


def _psql(sql):
    r = subprocess.run(SSH + ["docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"],
                       input=sql, capture_output=True, text=True, timeout=120)
    return r.stdout.strip()


def _has(keywords, scope=""):
    conds = " AND ".join(f"text ILIKE '%{k}%'" for k in keywords)
    if scope:
        conds += f" AND citation ILIKE '%{scope}%'"
    return (_psql(f"SELECT count(*) FROM legal_chunks WHERE {conds};") or "0") != "0"


def cited_in_playbooks():
    cited = {}
    for f in glob.glob("playbooks/*.json"):
        for m in re.finditer(r"(?:R\.?A\.?|RA|P\.?D\.?|Republic Act|Presidential Decree)\s*(?:No\.?\s*)?(\d{3,5})", open(f).read()):
            cited.setdefault(m.group(1), set()).add(os.path.basename(f))
    return cited


# Major governing acts that should be present as FULL text (for in-house self-sufficiency).
FULL_CORPUS = [
    ("RA 386 — Civil Code", "386"), ("RA 7160 — Local Government Code", "7160 (Local"),
    ("1987 Constitution", "Constitution (full"), ("PD 1529 — Property Registration", "1529 (full"),
    ("CA 141 — Public Land Act", "CA 141"), ("PD 1445 — Auditing Code", "1445 (Gov"),
    ("RA 11032 — ARTA Act", "11032 — consolidated"), ("RA 3019 — Anti-Graft", "3019 (full"),
    ("RA 6770 — Ombudsman Act", "6770 (Ombudsman"), ("RA 6713 — Code of Conduct", "6713 (full"),
    ("2017 RACCS", "RACCS"), ("RA 9184 — Procurement", "9184 (Gov"),
    ("EO 292 — Administrative Code", "292 (Admin"), ("RPC — Revised Penal Code", "Penal"),
    ("PD 1096 — Building Code", "1096"), ("RA 6657 — CARL", "6657 (full"),
    ("Rules of Court", "Rules of Court"), ("RA 8424 — Tax Code (NIRC)", "8424"),
]


def corpus_inventory():
    print("=== FULL-TEXT CORPUS COMPLETENESS (in-house self-sufficiency) ===\n")
    full = partial = missing = 0
    for label, like in FULL_CORPUS:
        n = int(_psql(f"SELECT count(*) FROM legal_chunks WHERE citation ILIKE '%{like}%';") or "0")
        flag = "FULL    " if n >= 16 else ("partial " if n else "MISSING ")
        full += n >= 16; partial += 0 < n < 16; missing += n == 0
        print(f"  {flag} {n:>4} chunks  {label}")
    print(f"\n  {full} full · {partial} partial · {missing} missing  (of {len(FULL_CORPUS)} major acts)\n")


def main():
    if "--corpus" in sys.argv:
        corpus_inventory(); return
    print("=== LAW-LIBRARY COVERAGE MONITOR ===\n")
    embedded_acts = set()
    for c in _psql("SELECT DISTINCT citation FROM legal_chunks;").splitlines():
        for n in re.findall(r"\b(\d{3,5})\b", c):
            embedded_acts.add(n)
        if "Penal" in c or "RPC" in c:
            embedded_acts.add("RPC")

    print("Needed provisions — is the TEXT in the system?")
    missing = []
    for label, why, kws, scope in NEEDED:
        ok = _has(kws, scope)
        print(f"  {'✓ embedded ' if ok else '✗ MISSING   '}  {label:24s} — {why}")
        if not ok:
            missing.append((label, why))

    print("\nActs cited in playbooks but NOT embedded:")
    gaps = [(n, f) for n, f in cited_in_playbooks().items() if n not in embedded_acts]
    if gaps:
        for n, f in gaps:
            print(f"  ✗ RA/PD {n}  (cited in {', '.join(sorted(f))})")
    else:
        print("  (none — every act the playbooks cite is embedded)")

    print(f"\n→ {len(missing)} needed provision(s) to embed:")
    for label, why in missing:
        print(f"   • {label} — {why}")


if __name__ == "__main__":
    main()
