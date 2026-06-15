#!/usr/bin/env python3
"""cross_client_sentinel.py — the anti-conflation intelligence layer.

WHY THIS EXISTS (operator, 2026-06-15): "this can never happen again — it's the sign of a
dumb system. If there are names in multiple clients' corpuses the system must be intelligent
enough to understand WHY." A one-off cleanup is not a fix. This module makes the system
*understand* cross-client name overlap and *enforce* client separation so it can't silently
regress. It is deterministic and costs $0 (no LLM) — pure structure over what we already know.

It distinguishes the three things that actually happened:

  (1) LEGITIMATE overlap — a person genuinely appears in two clients' files for a reason:
      an appraiser hired by both (Virgilio Tuazon, "mentioned" in MWK + Paracale), or the
      operator acting as agent (Jonathan). The tell is ROLE: defining in ONE client, only
      incidental (witness/notary/appraiser/agent/mentioned) elsewhere. Places and laws
      (Camarines Norte, RA 8792) are typed location/legal_provision and ignored outright —
      geography and statute are shared by definition, never a conflation.

  (2) MIS-FILE — a document whose PARTIES belong to client B but is filed under client A
      (Inocalla litigation docs 513/525 filed under MWK). These had the foreign principals
      in their TEXT but were never extracted into doc_entities, so an entity-only guard is
      blind to them. The text scan catches them by name.

  (3) DRIFT — extraction re-spawns a consolidated entity under a new spelling, so the
      deploy_258 merge ("Allan Inocalla" #8091/#8147/#8320 -> #7983) silently came back.
      The canon now lives as data in _clients.CANON_ALIAS_MERGES and is re-applied here.

Detectors (all $0):
  --report        cross-client person/org classification + mis-file candidates + drift
  --apply-canon   re-apply CANON_ALIAS_MERGES (idempotent, FK-complete merge)
  --log           write findings to cross_client_flags (for the cockpit / daily digest)
  --json          machine-readable output

Importable surface (consumed by truth_tests/test_cross_client_integrity.py):
  drift_residual(cur)            -> [(survivor, alias_id, alias_name)]  (canon not applied)
  multi_defining_principals(cur) -> [(entity_id, name, {client: n})]    (excl. allowlist)
  misfile_candidates(cur)        -> [{doc_id, current, suggest, evidence}]

Runs on the VPS (psycopg2 + PG_DSN). Standing check via landtek-cross-client.timer.
"""
import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from case_theories._clients import (
    CLIENTS,
    CANON_ALIAS_MERGES,
    CROSS_CLIENT_PRINCIPAL_ALLOWLIST,
)

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Roles that DEFINE which client a document belongs to (the parties/subject), as opposed to
# incidental appearances (witness, notary, appraiser, agent, mentioned). Matched by substring
# against the (lowercased) free-form role string, so "opposing party" and "registered owner"
# both resolve. Anything not matching a defining token is treated as incidental — conservative:
# an unknown role never drives a re-file.
DEFINING_TOKENS = (
    "owner", "plaintiff", "defendant", "petitioner", "respondent", "complainant",
    "accused", "opposing", "transferee", "transferor", "vendor", "vendee", "buyer",
    "seller", "grantee", "grantor", "mortgagor", "mortgagee", "lessee", "lessor",
    "applicant", "claimant", "registrant", "declarant", "heir", "co-owner",
)

KNOWN_CLIENTS = {c["case_file"] for c in CLIENTS.values() if c.get("case_file")}
# Mis-file detection runs ONLY between the real representation clients. 'Owner' is Jonathan's
# personal/family bucket that references MWK people by design (passports, genealogy supporting
# the estate) — its overlap with MWK is expected, not conflation — so it's excluded as both
# source and target. The dangerous conflation is MWK <-> Paracale <-> NIBDC.
REAL_CLIENTS = {"MWK-001", "Paracale-001", "NIBDC-001"}
MISFILE_MIN_FOREIGN = 2   # need >=2 distinct foreign principals to vote a mis-file


def _name_tokens(name):
    return {t for t in re.findall(r"[a-z]+", (name or "").lower()) if len(t) >= 5}


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def role_is_defining(role):
    if not role:
        return False
    r = role.lower()
    return any(tok in r for tok in DEFINING_TOKENS)


# ── (3) DRIFT — canon re-application ───────────────────────────────────────────────

# Every table.column that references entities.id (discovered 2026-06-15). The merge re-points
# all of them so a survivor never orphans a row. Scalar FKs -> UPDATE; int[] -> array_replace;
# doc_entities is (doc_id,entity_id,role) PK -> conflict-avoiding re-point then delete dupes.
_SCALAR_FKS = [
    ("document_entities", "entity_id"),
    ("entity_aliases", "entity_id"),
    ("entity_relationships", "from_entity_id"),
    ("entity_relationships", "to_entity_id"),
    ("titles", "registrant_entity_id"),
    ("transferees", "entity_id"),
    ("chat_notes", "related_entity_id"),
    ("actor_lifespan", "entity_id"),
    ("resolutions", "adjudicator_entity_id"),
    ("arta_cases", "adjudicator_entity_id"),
]
_ARRAY_FKS = [
    ("matters", "plaintiff_entity_ids"),
    ("matters", "respondent_entity_ids"),
    ("document_chunks", "entity_ids"),
]


def _table_exists(cur, table):
    cur.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",))
    return cur.fetchone()["t"] is not None


def merge_entities(cur, survivor, alias_id):
    """Fold alias_id into survivor across every FK. Idempotent; safe if alias_id is gone."""
    cur.execute("SELECT id, canonical_name, aliases FROM entities WHERE id IN %s",
                ((survivor, alias_id),))
    rows = {r["id"]: r for r in cur.fetchall()}
    if alias_id not in rows:
        return False  # already merged
    if survivor not in rows:
        raise RuntimeError(f"survivor entity {survivor} missing")
    alias_name = rows[alias_id]["canonical_name"]

    cur.execute("BEGIN")
    # Keystone entities carry a hard verification_lock — writes require an audited override.
    # An operator-directed canon merge (CANON_ALIAS_MERGES) is exactly the legitimate case:
    # we record actor + reason so the override is traceable, scoped LOCAL to this merge tx.
    cur.execute("SELECT set_config('app.truth_override', 'on', true)")
    cur.execute("SELECT set_config('app.truth_override_actor', 'manual_review', true)")
    cur.execute("SELECT set_config('app.truth_override_reason', %s, true)",
                (f"canon alias merge #{alias_id} -> #{survivor} (CANON_ALIAS_MERGES)",))
    # doc_entities: re-point non-colliding, then drop the rest
    cur.execute("""
        UPDATE doc_entities de SET entity_id=%s WHERE de.entity_id=%s
          AND NOT EXISTS (SELECT 1 FROM doc_entities x
                          WHERE x.doc_id=de.doc_id AND x.entity_id=%s AND x.role IS NOT DISTINCT FROM de.role)
    """, (survivor, alias_id, survivor))
    cur.execute("DELETE FROM doc_entities WHERE entity_id=%s", (alias_id,))
    # entities.canonical_id is a self-referential FK. Re-point everyone pointing at the alias
    # to the survivor; if the survivor itself pointed at the alias, null it (the survivor IS
    # the canonical now and can't point at a row we're about to delete).
    cur.execute("UPDATE entities SET canonical_id=%s WHERE canonical_id=%s AND id<>%s",
                (survivor, alias_id, survivor))
    cur.execute("UPDATE entities SET canonical_id=NULL WHERE id=%s AND canonical_id=%s",
                (survivor, alias_id))
    # scalar FKs
    for tbl, col in _SCALAR_FKS:
        if _table_exists(cur, tbl):
            cur.execute(f"UPDATE {tbl} SET {col}=%s WHERE {col}=%s", (survivor, alias_id))
    # array FKs
    for tbl, col in _ARRAY_FKS:
        if _table_exists(cur, tbl):
            cur.execute(
                f"UPDATE {tbl} SET {col}=array_replace({col}, %s, %s) WHERE %s = ANY({col})",
                (alias_id, survivor, alias_id))
    # fold the alias spelling into survivor.aliases, then delete the alias entity
    cur.execute("""
        UPDATE entities SET aliases =
          (SELECT array_agg(DISTINCT a) FROM unnest(coalesce(aliases,'{}') || ARRAY[%s]) a WHERE a IS NOT NULL)
        WHERE id=%s
    """, (alias_name, survivor))
    cur.execute("DELETE FROM entities WHERE id=%s", (alias_id,))
    cur.execute("COMMIT")
    return True


def apply_canon(cur, dry=False):
    """Re-apply CANON_ALIAS_MERGES. Returns list of (survivor, alias_id, alias_name) merged."""
    done = []
    for survivor, aliases in CANON_ALIAS_MERGES.items():
        for alias_id in aliases:
            cur.execute("SELECT canonical_name FROM entities WHERE id=%s", (alias_id,))
            row = cur.fetchone()
            if not row:
                continue  # already merged
            if dry:
                done.append((survivor, alias_id, row["canonical_name"]))
                continue
            if merge_entities(cur, survivor, alias_id):
                done.append((survivor, alias_id, row["canonical_name"]))
    return done


def drift_residual(cur):
    """Documented aliases that are STILL live entities (canon has drifted / not applied)."""
    return apply_canon(cur, dry=True)


# ── (1) cross-client classification ────────────────────────────────────────────────

def _entity_client_roles(cur):
    """{entity_id: {'name','type', clients:{case_file:{'def':n,'inc':n,'roles':set}}}}"""
    cur.execute("""
        SELECT e.id, e.canonical_name, e.type, d.case_file, de.role, count(*) AS n
        FROM doc_entities de
        JOIN documents d ON d.id=de.doc_id
        JOIN entities e ON e.id=de.entity_id
        WHERE e.type IN ('person','organization')
          AND d.case_file = ANY(%s)
        GROUP BY e.id, e.canonical_name, e.type, d.case_file, de.role
    """, (list(KNOWN_CLIENTS),))
    out = {}
    for r in cur.fetchall():
        e = out.setdefault(r["id"], {"name": r["canonical_name"], "type": r["type"], "clients": {}})
        cl = e["clients"].setdefault(r["case_file"], {"def": 0, "inc": 0, "roles": set()})
        if role_is_defining(r["role"]):
            cl["def"] += r["n"]
        else:
            cl["inc"] += r["n"]
        if r["role"]:
            cl["roles"].add(r["role"])
    return out


def classify_cross_client(cur):
    """Every person/org appearing across >1 client, with a WHY label."""
    ents = _entity_client_roles(cur)
    rows = []
    for eid, e in ents.items():
        if len(e["clients"]) < 2:
            continue
        defining_clients = [c for c, v in e["clients"].items() if v["def"] > 0]
        if eid in CROSS_CLIENT_PRINCIPAL_ALLOWLIST:
            label = "ALLOWLISTED"
        elif len(defining_clients) > 1:
            label = "CONFLATION_RISK"   # defining party in >1 client -> human review
        elif len(defining_clients) == 1:
            label = "EXPECTED"          # home = the defining client; incidental elsewhere
        else:
            label = "INCIDENTAL_ONLY"   # mentioned/witness in several; no client owns it
        rows.append({
            "entity_id": eid, "name": e["name"], "type": e["type"], "label": label,
            "home": defining_clients[0] if len(defining_clients) == 1 else None,
            "clients": {c: {"def": v["def"], "inc": v["inc"], "roles": sorted(v["roles"])}
                        for c, v in e["clients"].items()},
        })
    order = {"CONFLATION_RISK": 0, "INCIDENTAL_ONLY": 1, "EXPECTED": 2, "ALLOWLISTED": 3}
    rows.sort(key=lambda x: (order[x["label"]], -len(x["clients"])))
    return rows


def multi_defining_principals(cur):
    """CONFLATION_RISK rows only (for the truth test)."""
    return [(r["entity_id"], r["name"], {c: v["def"] for c, v in r["clients"].items()})
            for r in classify_cross_client(cur) if r["label"] == "CONFLATION_RISK"]


# ── (2) text-level mis-file detection ──────────────────────────────────────────────

def _party_discriminators(cur):
    """{case_file: {name_lower: entity_id}} — names of persons who are DEFINING PARTIES
    (owner / plaintiff / defendant / transferee / ...) in exactly ONE real client. A person
    who is only ever an official, notary, witness or 'mentioned' (incidental everywhere) is
    excluded — so the Register of Deeds who signs every client's titles, or an appraiser
    hired by two clients, never looks like a party. The allowlisted operator is excluded too.
    Persons defining in >1 real client are skipped here and surface as CONFLATION_RISK."""
    cur.execute("""
        SELECT e.id, e.canonical_name, e.aliases, d.case_file, de.role
        FROM doc_entities de
        JOIN documents d ON d.id=de.doc_id
        JOIN entities e ON e.id=de.entity_id
        WHERE e.type='person' AND d.case_file = ANY(%s)
    """, (list(REAL_CLIENTS),))
    party_rows = cur.fetchall()

    # operator allowlist, name-aware: build (first,last) token pairs so a garbled DUPLICATE
    # of the operator ("Jonathan Zschoche", "Jonathan P. Zschoche", the OCR-mangled middle-
    # name variants) is excluded too — not just the one canonical id. Entity resolution for
    # these OCR variants is a separate fuzzy/LLM pass; the sentinel must be robust without it.
    allow_pairs = []
    if CROSS_CLIENT_PRINCIPAL_ALLOWLIST:
        cur.execute("SELECT canonical_name FROM entities WHERE id = ANY(%s)",
                    (list(CROSS_CLIENT_PRINCIPAL_ALLOWLIST),))
        for r in cur.fetchall():
            big = [t for t in re.findall(r"[a-zá-úñ]+", (r["canonical_name"] or "").lower())
                   if len(t) >= 4]
            if len(big) >= 2:
                allow_pairs.append((big[0], big[-1]))

    def _is_operator(name):
        toks = _name_tokens(name)
        return any(a in toks and b in toks for a, b in allow_pairs)

    ent = {}
    for r in party_rows:
        e = ent.setdefault(r["id"], {"name": r["canonical_name"],
                                     "aliases": r["aliases"] or [], "def": {}})
        if role_is_defining(r["role"]):
            e["def"][r["case_file"]] = e["def"].get(r["case_file"], 0) + 1
    out = {}
    for eid, e in ent.items():
        if eid in CROSS_CLIENT_PRINCIPAL_ALLOWLIST or _is_operator(e["name"]):
            continue
        defc = {c: n for c, n in e["def"].items() if n > 0}
        if len(defc) != 1:           # not a party, or a party in >1 client (ambiguous)
            continue
        client = next(iter(defc))
        for nm in [e["name"]] + list(e["aliases"]):
            nm = (nm or "").strip()
            if len(nm) >= 8 and len(nm.split()) >= 2:
                out.setdefault(client, {})[nm.lower()] = eid
    return out


def misfile_candidates(cur):
    """Docs whose text names >=MISFILE_MIN_FOREIGN distinct PARTIES of ONE other real client
    and ZERO parties of their own filed client. Counts distinct entities (so two spellings of
    one person don't clear the bar). (The 513/525 Inocalla-litigation pattern.)"""
    disc = _party_discriminators(cur)
    if not disc:
        return []
    cur.execute("""
        SELECT id, case_file, lower(left(extracted_text, 30000)) AS txt
        FROM documents
        WHERE case_file = ANY(%s) AND extracted_text IS NOT NULL AND length(extracted_text) >= 40
    """, (list(REAL_CLIENTS),))
    out = []
    for r in cur.fetchall():
        txt, home = r["txt"], r["case_file"]
        hits = {}   # client -> {entity_ids}
        names_for = {}  # client -> {names seen} (for evidence)
        for client, name_map in disc.items():
            for nm, eid in name_map.items():
                if nm in txt:
                    hits.setdefault(client, set()).add(eid)
                    names_for.setdefault(client, set()).add(nm)
        home_hits = len(hits.get(home, set()))
        foreign = sorted(((c, ids) for c, ids in hits.items() if c != home),
                         key=lambda x: -len(x[1]))
        if home_hits == 0 and foreign and len(foreign[0][1]) >= MISFILE_MIN_FOREIGN:
            sc = foreign[0][0]
            out.append({"doc_id": r["id"], "current": home, "suggest": sc,
                        "evidence": sorted(names_for.get(sc, set()))[:6]})
    return out


# ── flags table + digest ───────────────────────────────────────────────────────────

def ensure_flags_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cross_client_flags (
            id serial PRIMARY KEY,
            kind text NOT NULL,            -- 'misfile' | 'conflation_risk' | 'drift'
            ref text,                      -- doc_id or entity_id
            severity text DEFAULT 'warn',
            detail jsonb,
            status text DEFAULT 'open',
            created_at timestamptz DEFAULT now()
        )
    """)


def log_flags(cur, drift, conflation, misfiles):
    ensure_flags_table(cur)
    cur.execute("UPDATE cross_client_flags SET status='superseded' WHERE status='open'")
    for s, a, nm in drift:
        cur.execute("INSERT INTO cross_client_flags(kind,ref,severity,detail) VALUES('drift',%s,'error',%s)",
                    (str(a), json.dumps({"survivor": s, "alias_name": nm})))
    for eid, nm, clients in conflation:
        cur.execute("INSERT INTO cross_client_flags(kind,ref,severity,detail) VALUES('conflation_risk',%s,'error',%s)",
                    (str(eid), json.dumps({"name": nm, "defining_in": clients})))
    for m in misfiles:
        cur.execute("INSERT INTO cross_client_flags(kind,ref,severity,detail) VALUES('misfile',%s,'warn',%s)",
                    (str(m["doc_id"]), json.dumps(m)))


def report(cur, as_json=False):
    drift = drift_residual(cur)
    cc = classify_cross_client(cur)
    conflation = [r for r in cc if r["label"] == "CONFLATION_RISK"]
    misfiles = misfile_candidates(cur)
    if as_json:
        print(json.dumps({"drift": drift, "cross_client": cc, "misfiles": misfiles}, default=list))
        return drift, conflation, misfiles

    print("=" * 72)
    print("CROSS-CLIENT SENTINEL — anti-conflation report")
    print("=" * 72)
    print(f"\n[3] ENTITY DRIFT (documented canon NOT applied — {len(drift)}):")
    for s, a, nm in drift:
        print(f"    ✗ #{a} \"{nm}\" should be merged into #{s}  → run --apply-canon")
    if not drift:
        print("    ✓ canon fully applied (no drifted aliases)")

    print(f"\n[1] CROSS-CLIENT PERSONS/ORGS ({len(cc)} span >1 client):")
    for r in cc:
        cl = ", ".join(f"{c}(def{v['def']}/inc{v['inc']})" for c, v in r["clients"].items())
        tag = {"CONFLATION_RISK": "✗ RISK", "EXPECTED": "✓ ok",
               "INCIDENTAL_ONLY": "· inc", "ALLOWLISTED": "✓ allow"}[r["label"]]
        print(f"    {tag:8} #{r['entity_id']} {r['name']}  [{cl}]")

    print(f"\n[2] MIS-FILE CANDIDATES (parties point to another client — {len(misfiles)}):")
    for m in misfiles:
        print(f"    ✗ doc {m['doc_id']}: filed {m['current']} but parties are {m['suggest']} "
              f"({', '.join(m['evidence'][:3])})")
    if not misfiles:
        print("    ✓ no docs whose parties contradict their filing")
    print()
    return drift, conflation, misfiles


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--apply-canon", action="store_true")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    c = _conn()
    cur = _cur(c)

    if a.apply_canon:
        merged = apply_canon(cur, dry=False)
        if merged:
            for s, aid, nm in merged:
                print(f"  merged #{aid} \"{nm}\" → #{s}")
            print(f"[apply-canon] re-applied {len(merged)} alias merge(s)")
        else:
            print("[apply-canon] nothing to merge — canon already consistent")
        return

    drift, conflation, misfiles = report(cur, as_json=a.json)
    if a.log:
        log_flags(cur, drift, conflation, misfiles)
        print(f"[log] wrote {len(drift)+len(conflation)+len(misfiles)} flag(s) to cross_client_flags")


if __name__ == "__main__":
    main()
