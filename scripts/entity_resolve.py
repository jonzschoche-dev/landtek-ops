#!/usr/bin/env python3
"""entity_resolve.py — deterministic entity resolution: collapse OCR/spelling variants. $0, no LLM.

WHY (operator, 2026-06-15): the corpus has wholesale entity fragmentation from OCR — 30+ garbled
"Zschoche" spellings, ~29 Inocalla-family variants for ~12 real people. The cross-client sentinel
is robust without fixing this, but the duplicates pollute every count and re-spawn after each merge.
This resolver clusters person entities by a normalized name key and either auto-merges the provably-
same or proposes the rest for review. It is intentionally CONSERVATIVE: the danger is false-merging
two DIFFERENT people who share a name (a Paracale "Jose" and an MWK "Jose"), so cross-client and
fuzzy matches are never auto-applied — only surfaced.

Normalization (norm_key): lowercase, strip accents, drop honorifics (atty/datu/mr/dr/engr/rea...),
drop single-letter initials and <=2-char particles, but KEEP generational suffixes (jr/sr/ii/iii/iv)
because they distinguish father/son/namesake. The key is the sorted set of the remaining tokens.

Tiers:
  AUTO   — identical norm_key, all within ONE real client (or a protected keystone/operator is in the
           group). Provably the same person; merged via the sentinel's FK-complete merge.
  HOLD   — identical norm_key but spans >1 real client. Could be the same person OR a namesake
           collision across clients — never auto-merged; proposed for human eyes.
  FUZZY  — near key (subset, or difflib ratio >= 0.88, sharing a surname-length token). Proposed.

  --scan         read-only: show the cluster landscape (counts + samples per tier)
  --apply-auto   merge AUTO groups (survivor = keystone/operator if present, else most-linked)
  --propose      write HOLD + FUZZY to entity_merge_proposals (status pending) for review
  --accept S A   apply a single reviewed merge (alias A -> survivor S) with the audited override

Run on the VPS (psycopg2 + PG_DSN). Reuses cross_client_sentinel.merge_entities.
"""
import argparse
import difflib
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cross_client_sentinel import _conn, _cur, merge_entities          # FK-complete merge + lock override
from case_theories._clients import CLIENTS, CANON_ALIAS_MERGES, CROSS_CLIENT_PRINCIPAL_ALLOWLIST

REAL_CLIENTS = {"MWK-001", "Paracale-001", "NIBDC-001"}
# Only true personal/professional TITLES — never semantic words. "heirs"/"of"/"estate" are
# kept because "Heirs of Mary Worrick Keesey" (the estate-collective) is a DIFFERENT entity
# from "Mary Worrick Keesey" (the person) and must not collapse into her.
HONORIFICS = {"atty", "attorney", "datu", "mr", "mrs", "ms", "dr", "engr", "hon", "sir",
              "madam", "rea", "cpa", "esq"}
GEN = {"jr", "sr", "ii", "iii", "iv"}   # generational suffixes — KEEP, they distinguish people
FUZZY_RATIO = 0.88

# Entities that must always survive a merge, never be merged away (and never merged together).
KEYSTONE_IDS = set(CANON_ALIAS_MERGES) | set(CROSS_CLIENT_PRINCIPAL_ALLOWLIST)
for _c in CLIENTS.values():
    for _v in (_c.get("keystone_entities") or {}).values():
        if isinstance(_v, int):
            KEYSTONE_IDS.add(_v)


def _deaccent(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def sig_tokens(name):
    s = _deaccent((name or "").lower())
    s = re.sub(r"'[^']*'", " ", s)          # drop quoted nicknames e.g. 'JJ Ildefonso Moreno'
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    out = []
    for t in s.split():
        if t in HONORIFICS:
            continue
        if t in GEN:
            out.append(t)
            continue
        if len(t) <= 2:                     # initials and short particles (de/la/del/y)
            continue
        out.append(t)
    return out


def norm_key(name):
    return tuple(sorted(set(sig_tokens(name))))


def _load_persons(cur):
    cur.execute("""
        SELECT e.id, e.canonical_name,
               (SELECT count(*) FROM doc_entities de WHERE de.entity_id=e.id) AS links,
               (SELECT mode() WITHIN GROUP (ORDER BY d.case_file)
                  FROM doc_entities de JOIN documents d ON d.id=de.doc_id
                 WHERE de.entity_id=e.id AND d.case_file = ANY(%s)) AS dom_client
        FROM entities e
        WHERE e.type='person' AND e.canonical_name IS NOT NULL
    """, (list(REAL_CLIENTS),))
    rows = []
    for r in cur.fetchall():
        k = norm_key(r["canonical_name"])
        if k:                                # skip names that normalize to nothing
            rows.append({"id": r["id"], "name": r["canonical_name"], "links": r["links"],
                         "dom": r["dom_client"], "key": k})
    return rows


def _pick_survivor(members):
    """Keystone/operator wins; else most-linked, lowest id. None if >1 protected (conflict)."""
    prot = [m for m in members if m["id"] in KEYSTONE_IDS]
    if len(prot) > 1:
        return None
    if prot:
        return prot[0]["id"]
    return max(members, key=lambda m: (m["links"], -m["id"]))["id"]


def cluster(cur):
    """Return {'auto': [...groups], 'hold': [...], 'fuzzy': [...pairs]}."""
    persons = _load_persons(cur)
    by_key = {}
    for p in persons:
        by_key.setdefault(p["key"], []).append(p)

    auto, hold, weak = [], [], []
    for key, members in by_key.items():
        if len(members) < 2:
            continue
        survivor = _pick_survivor(members)
        if survivor is None:
            continue                          # two protected entities collide -> leave alone
        real = {m["dom"] for m in members if m["dom"] in REAL_CLIENTS}
        protected_present = any(m["id"] in KEYSTONE_IDS for m in members)
        group = {"survivor": survivor, "members": members, "key": key,
                 "clients": sorted(c for c in real)}
        if len(key) < 2:
            weak.append(group)                # single-token (bare first/last name) -> too weak to act on
        elif len(real) <= 1 or protected_present:
            auto.append(group)
        else:
            hold.append(group)                # same name, different clients -> namesake risk

    # FUZZY: keys that aren't equal but are close. Compare singleton/representative keys only,
    # within the same dominant client, to keep it cheap and precise.
    singles = [p for p in persons if len(by_key[p["key"]]) == 1]
    by_client = {}
    for p in singles:
        by_client.setdefault(p["dom"], []).append(p)
    fuzzy = []
    seen = set()
    for cl, plist in by_client.items():
        if cl not in REAL_CLIENTS:
            continue
        for i in range(len(plist)):
            for j in range(i + 1, len(plist)):
                a, b = plist[i], plist[j]
                ka, kb = set(a["key"]), set(b["key"])
                if not (ka & kb):
                    continue
                subset = ka < kb or kb < ka
                ratio = difflib.SequenceMatcher(None, " ".join(a["key"]), " ".join(b["key"])).ratio()
                shared_surname = any(len(t) >= 4 for t in (ka & kb))
                if shared_surname and (subset or ratio >= FUZZY_RATIO):
                    pair = tuple(sorted((a["id"], b["id"])))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    surv = _pick_survivor([a, b])
                    if surv is None:
                        continue
                    other = b if surv == a["id"] else a
                    base = a if surv == a["id"] else b
                    fuzzy.append({"survivor": surv, "survivor_name": base["name"],
                                  "alias": other["id"], "alias_name": other["name"],
                                  "client": cl, "ratio": round(ratio, 2),
                                  "reason": "subset" if subset else f"ratio {ratio:.2f}"})
    return {"auto": auto, "hold": hold, "fuzzy": fuzzy, "weak": weak}


def _ensure_tables(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entity_merge_proposals (
            id serial PRIMARY KEY, survivor int, alias int,
            survivor_name text, alias_name text, tier text, score numeric, reason text,
            status text DEFAULT 'pending', created_at timestamptz DEFAULT now(),
            UNIQUE(survivor, alias))""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS entity_resolution_log (
            id serial PRIMARY KEY, survivor int, alias int, alias_name text,
            method text, created_at timestamptz DEFAULT now())""")


def apply_auto(cur):
    res = cluster(cur)
    _ensure_tables(cur)
    n = 0
    for g in res["auto"]:
        for m in g["members"]:
            if m["id"] == g["survivor"]:
                continue
            if merge_entities(cur, g["survivor"], m["id"]):
                cur.execute("INSERT INTO entity_resolution_log(survivor,alias,alias_name,method) "
                            "VALUES(%s,%s,%s,'auto_normkey')", (g["survivor"], m["id"], m["name"]))
                print(f"  merged #{m['id']} \"{m['name']}\" → #{g['survivor']}")
                n += 1
    print(f"[apply-auto] merged {n} variant(s) by exact normalized key")
    return n


def propose(cur):
    res = cluster(cur)
    _ensure_tables(cur)
    n = 0
    def _ins(surv, alias, sn, an, tier, score, reason):
        nonlocal n
        cur.execute("""INSERT INTO entity_merge_proposals(survivor,alias,survivor_name,alias_name,tier,score,reason)
                       VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (survivor,alias) DO NOTHING""",
                    (surv, alias, sn, an, tier, score, reason))
        n += cur.rowcount
    for g in res["hold"]:
        sn = next(m["name"] for m in g["members"] if m["id"] == g["survivor"])
        for m in g["members"]:
            if m["id"] != g["survivor"]:
                _ins(g["survivor"], m["id"], sn, m["name"], "hold_cross_client", None,
                     f"same name across clients {g['clients']}")
    for f in res["fuzzy"]:
        _ins(f["survivor"], f["alias"], f["survivor_name"], f["alias_name"], "fuzzy", f["ratio"], f["reason"])
    print(f"[propose] wrote {n} new proposal(s) to entity_merge_proposals (status=pending)")
    return n


def accept(cur, survivor, alias):
    if merge_entities(cur, survivor, alias):
        _ensure_tables(cur)
        cur.execute("INSERT INTO entity_resolution_log(survivor,alias,alias_name,method) "
                    "SELECT %s,%s,canonical_name,'accepted' FROM entities WHERE id=%s",
                    (survivor, alias, survivor))
        cur.execute("UPDATE entity_merge_proposals SET status='accepted' WHERE survivor=%s AND alias=%s",
                    (survivor, alias))
        print(f"[accept] merged #{alias} → #{survivor}")
    else:
        print(f"[accept] #{alias} already merged / not found")


def scan(cur):
    res = cluster(cur)
    a, h, f = res["auto"], res["hold"], res["fuzzy"]
    auto_merges = sum(len(g["members"]) - 1 for g in a)
    print("=" * 72)
    print("ENTITY RESOLUTION — variant clustering (deterministic, $0)")
    print("=" * 72)
    print(f"\nAUTO  — exact normalized key, single client ({len(a)} groups, {auto_merges} merges):")
    for g in sorted(a, key=lambda x: -len(x["members"]))[:18]:
        names = " | ".join(f"#{m['id']} {m['name']}({m['links']})" for m in
                           sorted(g["members"], key=lambda m: -m["links"]))
        print(f"    → #{g['survivor']} [{','.join(g['clients']) or '?'}]: {names}")
    if len(a) > 18:
        print(f"    … +{len(a) - 18} more groups")
    print(f"\nHOLD  — same name across >1 client, NOT auto-merged ({len(h)}):")
    for g in h[:12]:
        names = " | ".join(f"#{m['id']} {m['name']}[{m['dom']}]" for m in g["members"])
        print(f"    ? {names}")
    print(f"\nFUZZY — near-match proposals for review ({len(f)}):")
    for x in sorted(f, key=lambda z: -z["ratio"])[:18]:
        print(f"    ? #{x['alias']} \"{x['alias_name']}\" → #{x['survivor']} \"{x['survivor_name']}\" "
              f"[{x['client']}] ({x['reason']})")
    if len(f) > 18:
        print(f"    … +{len(f) - 18} more")
    print(f"\nWEAK  — single-token clusters (bare name; NOT acted on — too weak): {len(res['weak'])}")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply-auto", action="store_true")
    ap.add_argument("--propose", action="store_true")
    ap.add_argument("--accept", nargs=2, type=int, metavar=("SURVIVOR", "ALIAS"))
    a = ap.parse_args()
    c = _conn()
    cur = _cur(c)
    if a.apply_auto:
        apply_auto(cur)
    elif a.propose:
        propose(cur)
    elif a.accept:
        accept(cur, a.accept[0], a.accept[1])
    else:
        scan(cur)


if __name__ == "__main__":
    main()
