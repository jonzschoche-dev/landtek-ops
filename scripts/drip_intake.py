#!/usr/bin/env python3
"""drip_intake.py — Drip v2 Stage 0 + Stage 1 + Stage 5 (agent_specs/005 §v2). $0, deterministic, NEVER sends.

Takes harvested officer/duty candidates (JSON, see the harvest brief), cross-references every row
against the repo and the DB (X1 matter/client · X2 instrument exists · X4 proof-of-receipt candidate ·
X6 email sourced · X7 already in registry · X8 counsel route), ranks them by the v2 daily-pick order
(money → sourced hard date → unblock count → admin-complaint ripeness), and loads them as draft_held
rows + escalation rungs.

DRY RUN BY DEFAULT: the inserts run inside a transaction that is ROLLED BACK, so DB constraints are
exercised for real but nothing persists. --apply commits.

Never sets served_at / due_at: a proof candidate is written to notes only. A clock starts solely via
drip_sweep.py --record-service <id> --proof-doc <documents.id> after a human confirms.

  python3 scripts/drip_intake.py --in a.json b.json [--repo .] [--out ranked.md] [--apply]
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import date

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
TODAY = date.today()
COUNSEL_ROUTE_RE = re.compile(r"\bbalane\b|torralba", re.I)   # CV 26-360 defendants → counsel only
RIPENESS_RANK = {"ripe": 2, "building": 1}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _surname(officer):
    toks = [t for t in re.split(r"[^A-Za-z]+", officer or "") if len(t) > 2 and t.lower() not in
            {"hon", "atty", "engr", "mayor", "the", "office", "and", "jr", "sr", "iii", "ceso", "rea"}]
    return toks[-1].lower() if toks else _norm(officer)


def load_candidates(paths):
    rows, seen = [], {}
    for p in paths:
        with open(p) as f:
            for r in json.load(f):
                r["_src_file"] = os.path.basename(p)
                key = (r.get("matter_code"), _norm(r.get("officer")), _norm(r.get("instrument_ref")))
                if key in seen:
                    seen[key].setdefault("_dupes", []).append(r["_src_file"])
                    continue
                seen[key] = r
                rows.append(r)
    return rows


def resolve_instrument(cur, repo, ref):
    """X2: the instrument must exist as a repo file, a corpus document, or an ingested e-mail.
    Accepts 'case_work/X: NAME' (registry style), any case_work/... path token, 'doc N', 'gmail N'.
    Returns a handle string, None (declared not built), or False (cited but unresolvable)."""
    if not ref:
        return None
    m = re.match(r"\s*(case_work/[^:]+):\s*([^\s—(]+)", ref)
    if m:
        hits = glob.glob(os.path.join(repo, m.group(1), "**", m.group(2) + "*"), recursive=True)
        if hits:
            return hits[0]
    for tok in re.findall(r"case_work/[^\s;,()]+", ref):
        tok = tok.rstrip(".")
        if os.path.exists(os.path.join(repo, tok)) or glob.glob(os.path.join(repo, tok) + "*"):
            return tok
    for n in re.findall(r"\bdocs? (\d{2,6})", ref):
        cur.execute("SELECT 1 FROM documents WHERE id=%s", (int(n),))
        if cur.fetchone():
            return f"doc {n}"
    for n in re.findall(r"\bgmail (\d{1,7})\b", ref):
        cur.execute("SELECT 1 FROM gmail_messages WHERE id=%s", (int(n),))
        if cur.fetchone():
            return f"gmail {n}"
    if re.search(r"none built|not built|to be drafted|no repo file", ref, re.I):
        return None
    return False


def check(cur, repo, r, registry):
    f = []                                   # findings (blocking + flags)
    # X1 — matter exists; client resolved
    # matter_code may hold a matter OR a client code (ONTOLOGY A5 note; registry rows 1–8 use 'MWK-001')
    cur.execute("""SELECT client_code FROM matters WHERE matter_code=%s
                   UNION ALL SELECT client_code FROM clients WHERE client_code=%s LIMIT 1""",
                (r.get("matter_code"), r.get("matter_code")))
    m = cur.fetchone()
    r["_client"] = m["client_code"] if m else None
    if not m:
        f.append("X1 BLOCK: matter_code is neither a matter nor a client")
    # X2 — our instrument exists
    inst = resolve_instrument(cur, repo, r.get("instrument_ref"))
    r["_instrument_ok"] = bool(inst)
    if inst is None:
        f.append("X2 note: instrument not built yet")
    elif inst is False:
        f.append("X2 BLOCK: instrument_ref does not resolve to a file")
    # X4 — proof candidate: same-client doc whose text contains the quoted excerpt
    r["_proof"] = "none"
    pid = r.get("proof_doc_id")
    if pid:
        cur.execute("SELECT id, matter_code, case_file, extracted_text FROM documents WHERE id=%s", (pid,))
        d = cur.fetchone()
        if not d:
            f.append(f"X4 BLOCK: proof doc {pid} not in corpus")
        else:
            cur.execute("SELECT client_code FROM matters WHERE matter_code=%s", (d["matter_code"],))
            dm = cur.fetchone()
            dclient = dm["client_code"] if dm else d["case_file"]
            if r["_client"] and dclient and dclient != r["_client"]:
                f.append(f"X4 BLOCK: proof doc {pid} belongs to client {dclient} (A5)")
            elif r.get("proof_excerpt") and _norm(r["proof_excerpt"])[:60] not in _norm(d["extracted_text"]):
                r["_proof"] = "candidate_unmatched"
                f.append(f"X4 flag: excerpt not found verbatim in doc {pid} [HUMAN VERIFY]")
            else:
                r["_proof"] = "candidate"
    # X6 — email must carry a source
    if r.get("email") and not r.get("email_source"):
        f.append("X6 flag: email without source — stripped")
        r["email"] = None
    # X7 — already in registry (same matter + surname)
    sn = _surname(r.get("officer"))
    hits = [g["id"] for g in registry if g["matter_code"] == r.get("matter_code") and _surname(g["officer"]) == sn]
    # A declared existing_id = same duty → enrich that row. A surname hit alone is NOT a duplicate:
    # the v1 splitting rule makes each duty its own row even for the same officer — flag it, still load.
    r["_existing"] = [r["existing_id"]] if r.get("existing_id") else []
    if r["_existing"]:
        f.append(f"X7 note: same duty as registry row {r['existing_id']} — enrich, don't duplicate")
    elif hits:
        f.append(f"X7 flag: same officer as registry row(s) {hits}, different duty — confirm not a duplicate")
    # X8 — counsel route
    gate = r.get("counsel_gate") or ""
    r["_state"] = "held_counsel_route" if (COUNSEL_ROUTE_RE.search(r.get("officer") or "")
                                           or "ONLY" in gate) else "draft_held"
    r["_findings"] = f
    r["_blocked"] = any("BLOCK" in x for x in f)
    return r


def score(r):
    # Only sourced money AT STAKE ranks (judgment, protested tax, paid-and-unrendered fee). Filing/
    # courier/application fees are costs — they never make an item "money-first".
    money = float(r.get("money_php") or 0) if (r.get("money_source") and r.get("money_kind") != "cost") else 0.0
    hd = r.get("hard_date") if r.get("hard_date_source") else None
    try:
        days = (date.fromisoformat(hd) - TODAY).days if hd else None
    except ValueError:
        days = None
    proximity = -days if days is not None and days >= 0 else (-9999 if days is None else -5000 + days)
    unblocks = len(r.get("unblocks") or [])
    ripe = RIPENESS_RANK.get((r.get("admin_complaint_ripeness") or "").split(":")[0].strip().lower(), 0)
    return (money, proximity, unblocks, ripe)


def load(cur, r):
    note = (r.get("notes") or "")
    if r["_proof"].startswith("candidate"):
        note += f" | PROOF CANDIDATE doc {r['proof_doc_id']} ({r['_proof']}) — NOT recorded; confirm via --record-service"
    if r.get("sent_or_filed"):
        note += f" | sent/filed {r['sent_or_filed']} per {r.get('sent_source')}"
    note += f" | intake v2 {TODAY} from {r['_src_file']}; sources: {', '.join(map(str, r.get('sources') or []))}"
    cur.execute("""INSERT INTO office_obligation (matter_code, officer, office, obligation, instrument_ref,
                     clock_rule, state, consequence_ref, counsel_gate, notes, email, email_confidence, email_source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT ON CONSTRAINT drip_dedup DO NOTHING RETURNING id""",
                (r["matter_code"], r["officer"], r.get("office"), r["obligation"][:500], r.get("instrument_ref"),
                 r.get("clock_rule"), r["_state"], r.get("consequence_ref"), r.get("counsel_gate"), note[:4000],
                 r.get("email"), "unverified" if r.get("email") else None, r.get("email_source")))
    row = cur.fetchone()
    if not row:
        return None
    for g in r.get("rungs") or []:
        cur.execute("""INSERT INTO escalation_rung (obligation_id, seq, office, officer, instrument_ref, statutory_basis)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (row["id"], g["seq"], g.get("office") or "—", g.get("officer"), g.get("instrument_ref"),
                     g.get("statutory_basis")))
    return row["id"]


def render(ranked, loaded, apply):
    out = [f"# Drip intake v2 — ranked targets ({TODAY}) — {'APPLIED' if apply else 'DRY RUN (rolled back)'}", "",
           "Order: money → sourced hard date → unblock count → admin-complaint ripeness. "
           "Proof = candidate only; no clock starts from this file.", "",
           "| # | Matter | Officer / office | Duty | Money ₱ | Hard date | Unblocks | Proof | Ripeness | State | Flags |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ranked, 1):
        flags = "; ".join(r["_findings"]) or "clean"
        out.append("| {} | {} | {} — {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, r["matter_code"], r["officer"], r.get("office") or "", (r["obligation"] or "")[:110].replace("|", "/"),
            f"{float(r['money_php']):,.0f}" if r.get("money_php") and r.get("money_source") and r.get("money_kind") != "cost" else "",
            r.get("hard_date") or "", len(r.get("unblocks") or []),
            f"doc {r['proof_doc_id']} ({r['_proof']})" if r["_proof"] != "none" else "—",
            (r.get("admin_complaint_ripeness") or "").split(":")[0],
            "BLOCKED" if r["_blocked"] else ("exists→enrich" if r["_existing"] else r["_state"]),
            flags.replace("|", "/")))
    out += ["", f"Loaded (would load) {len(loaded)} new rows; "
            f"{sum(1 for r in ranked if r['_existing'])} overlap existing rows; "
            f"{sum(1 for r in ranked if r['_blocked'])} blocked by cross-reference."]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--out")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, matter_code, officer FROM office_obligation")
    registry = cur.fetchall()

    rows = [check(cur, a.repo, r, registry) for r in load_candidates(a.inputs)]
    ranked = sorted(rows, key=score, reverse=True)
    loaded = []
    for r in ranked:
        if r["_blocked"] or r["_existing"]:
            continue
        cur.execute("SAVEPOINT s")
        try:
            oid = load(cur, r)
            cur.execute("RELEASE SAVEPOINT s")
            if oid:
                loaded.append(oid)
        except psycopg2.Error as e:
            cur.execute("ROLLBACK TO SAVEPOINT s")
            r["_findings"].append(f"DB BLOCK: {e.pgerror.strip().splitlines()[0] if e.pgerror else e}")
            r["_blocked"] = True
    if a.apply:
        cur.execute("INSERT INTO drip_event (kind, detail) VALUES ('intake_v2', %s)",
                    (json.dumps({"loaded": loaded, "inputs": a.inputs}),))
        conn.commit()
    else:
        conn.rollback()
    report = render(ranked, loaded, a.apply)
    if a.out:
        with open(a.out, "w") as f:
            f.write(report + "\n")
    print(report)


if __name__ == "__main__":
    sys.exit(main())
