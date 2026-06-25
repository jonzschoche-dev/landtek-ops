#!/usr/bin/env python3
"""dossier_verify.py — the DILIGENCE GATE. Runs, automatically and every time, the checks a careful
paralegal does by reflex on a finished dossier — the checks whose ABSENCE is the only reason a human
paralegal still beats the stack. $0, deterministic. Exit 0 = clean, 1 = issues found (a gate before ship).

Checks:
  1. CITATION FIDELITY  — every statute cited in the prose is actually in the embedded law library
                          (catches a model citing law from memory that we never grounded).
  2. ACRONYM INVENTION  — an acronym (e.g. CART) given a parenthetical expansion that may be hallucinated.
  3. SOURCE INTEGRITY   — every document in the back index exists, is matter-linked, and is NOT a draft
                          that has a received/stamped twin (never cite the draft as evidence).
  4. NAME / ENTITY      — conflicting spellings of the key names (Keesey vs Keesee/Kassey; MWK vs MMK).

  python3 scripts/dossier_verify.py 1891_output/synth_v2.md [--matter MWK-001]
"""
import os
import re
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=40", "root@100.85.203.58"]


def _psql(sql):
    r = subprocess.run(SSH + ["docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A -F'|'"],
                       input=sql, capture_output=True, text=True, timeout=90)
    return r.stdout.strip()


def _embedded_acts():
    acts = set()
    for c in _psql("SELECT DISTINCT citation FROM legal_chunks;").splitlines():
        for n in re.findall(r"\b(\d{3,5})\b", c):
            acts.add(n)
        if "Penal" in c or "RPC" in c:
            acts.add("RPC")
    return acts


def _cited(text):
    found = {}
    for m in re.finditer(r"(?:R\.?\s?A\.?|Republic Act|P\.?\s?D\.?|Presidential Decree)\s*(?:No\.?\s*)?(\d{3,5})", text):
        found.setdefault(m.group(1), text[max(0, m.start() - 25):m.start() + 45].replace("\n", " ").strip())
    if re.search(r"\bRPC\b|Revised Penal Code|Art(?:icle)?\.?\s*2(?:1[789]|2[0-2])\b", text):
        found.setdefault("RPC", "Revised Penal Code")
    return found


def _index_ids(text):
    seg = text.split("## Document index", 1)
    return re.findall(r"/files/c/(\d+)", seg[-1]) if len(seg) > 1 else []


def verify_text(src, matter=None):
    """Return a list of structured issue dicts (cat + human msg + fields the self-heal loop acts on)."""
    issues = []

    # 1 — citation fidelity
    emb = _embedded_acts()
    for n, ctx in _cited(src).items():
        if n not in emb:
            issues.append({"cat": "CITATION", "act": n,
                           "msg": f"cites '{n}' but it is NOT in the embedded law library — ground it or remove (…{ctx}…)"})

    # 2 — acronym invention (only true domain acronyms; a CAPS surname like "ABLA (Municipal Assessor)" is not one)
    KNOWN = {"CART", "ARTA", "SPA", "LGU", "FOI", "DILG", "COA", "BAC", "OSCA", "RACCS",
             "TCT", "RPT", "RPC", "MTC", "RTC", "DENR", "LRA", "DAR", "SALN"}
    for m in re.finditer(r"\b([A-Z]{2,5})\b\s*\(([^)]{8,70})\)", src):
        if m.group(1) in KNOWN and not re.search(r"https?://", m.group(2)):
            issues.append({"cat": "ACRONYM", "acr": m.group(1), "exp": m.group(2),
                           "msg": f"'{m.group(1)}' expanded as '{m.group(2)}' — confirm this expansion is in the record, not invented"})

    # 3 — source integrity (exists · has text · not a draft with a received twin) + client-separation (matter family)
    ids = sorted(set(_index_ids(src)), key=int)
    if ids:
        idlist = ",".join(ids)
        rows = _psql(f"SELECT id, coalesce(version_chain_id::text,''), "
                     f"(extracted_text ~* 'received by|received:|stamp')::int, length(coalesce(extracted_text,'')), "
                     f"coalesce(matter_code,'') FROM documents WHERE id IN ({idlist});")
        seen = {}
        for line in rows.splitlines():
            p = line.split("|")
            if len(p) >= 5:
                seen[p[0]] = {"vchain": p[1], "stamped": p[2] == "1", "len": int(p[3] or 0), "codes": {p[4]} if p[4] else set()}
        for line in _psql(f"SELECT doc_id, string_agg(DISTINCT matter_code, ',') FROM document_matter_links "
                          f"WHERE doc_id IN ({idlist}) GROUP BY doc_id;").splitlines():
            p = line.split("|")
            if len(p) == 2 and p[0] in seen:
                seen[p[0]]["codes"] |= set(c for c in p[1].split(",") if c)
        for i in ids:
            if i not in seen:
                issues.append({"cat": "SOURCE", "doc_id": i, "kind": "missing",
                               "msg": f"indexed document {i} does not exist in the corpus"}); continue
            if seen[i]["len"] < 40:
                issues.append({"cat": "SOURCE", "doc_id": i, "kind": "notext",
                               "msg": f"indexed document {i} has no extracted text — cannot be evidence"})
            if seen[i]["vchain"] and seen[i]["vchain"] != i and not seen[i]["stamped"]:
                issues.append({"cat": "SOURCE", "doc_id": i, "kind": "draft", "twin": seen[i]["vchain"],
                               "msg": f"indexed document {i} looks like a DRAFT (chained to received copy {seen[i]['vchain']}) — cite the received copy"})
            if matter and seen[i]["codes"] and not any(c.upper().startswith(matter.upper()) for c in seen[i]["codes"]):
                issues.append({"cat": "MATTER", "doc_id": i, "codes": sorted(seen[i]["codes"]),
                               "msg": f"indexed document {i} belongs to {sorted(seen[i]['codes'])}, outside the {matter} family — client-separation check"})

    # 4 — name / entity consistency
    for variants, canon in [((r"Keesee\b", r"Kassey\b", r"Keesy\b"), "Keesey"), ((r"\bMMK\b",), "MWK")]:
        for v in variants:
            mm = re.search(v, src)
            if mm:
                issues.append({"cat": "NAME", "found": mm.group(0), "canon": canon,
                               "msg": f"found '{mm.group(0)}' — the verified form is '{canon}'; reconcile"})
    return issues


def verify(md, matter=None):
    return verify_text(open(md).read(), matter)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: dossier_verify.py dossier.md [--matter PREFIX]")
    md = sys.argv[1]
    matter = sys.argv[sys.argv.index("--matter") + 1] if "--matter" in sys.argv else None
    issues = verify(md, matter)
    print(f"=== DILIGENCE GATE — {os.path.basename(md)} ===")
    if not issues:
        print("✓ CLEAN — citation fidelity, sources, and names all check out.")
    else:
        by = {}
        for it in issues:
            by.setdefault(it["cat"], []).append(it["msg"])
        for cat in by:
            print(f"\n[{cat}] {len(by[cat])}")
            for m in by[cat]:
                print(f"  • {m}")
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
