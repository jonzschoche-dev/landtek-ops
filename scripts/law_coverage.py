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


def main():
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
