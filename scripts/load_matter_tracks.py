#!/usr/bin/env python3
"""load_matter_tracks.py — load the track inventory into matter_track / track_party and render the reference table.

DRY RUN BY DEFAULT: applies the DRAFT migration DDL + the inserts inside one transaction, reads the views,
writes the markdown reference, then ROLLS BACK. --apply commits (only after the migration has been approved
and applied for real; never run --apply against the DRAFT).

  python3 scripts/load_matter_tracks.py --in tracks.json --out case_work/MATTER_REFERENCE_2026-10-20.md [--with-ddl]
"""
import argparse
import json
import os
import re
from datetime import date

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# G1, conservative: only forums that can themselves impose a sanction/judgment are True; record-builders stay NULL
SANCTIONS = re.compile(r"civil service|csc|ombudsman|trial court|\bmtc\b|\brtc\b|regional trial|sandiganbayan", re.I)
PTYPE = [(re.compile(r"mandamus|ministerial|removes? deflect", re.I), "removes_deflect"),
         (re.compile(r"liabil|count|charge|complaint|sanction|grave misconduct|§\s*3", re.I), "personal_liability"),
         (re.compile(r"supervis|informed|attribut|named|on record|endorse|indorse", re.I), "attribution"),
         (re.compile(r"damages|compensation|interest|delay cost|meter", re.I), "prices_delay")]


def _d(v):
    return v if isinstance(v, str) and ISO.match(v) else None


def _ptype(text):
    for rx, t in PTYPE:
        if rx.search(text or ""):
            return t
    return "none"


STOP = {"hon", "atty", "engr", "mayor", "exec", "sec", "rd", "jr", "sr", "ceso", "iii", "rea", "dir", "governor", "gov", "the", "mun", "of"}


def _surname(name):
    toks = [t for t in re.split(r"[^A-Za-z]+", re.sub(r"\(.*?\)", "", name or "")) if len(t) > 2 and t.lower() not in STOP]
    return toks[-1].lower() if toks else (name or "").lower()


def canon_map(data):
    """Variant names ('Mayor Alexander L. Pajarillo', 'Hon. Alexander L. Pajarillo') → the officials-index name,
    keyed on surname within the same client. Ambiguous surnames are left as-is (never guessed)."""
    by = {}
    for o in data.get("officials", []):
        by.setdefault((o["client_code"], _surname(o["official"])), []).append(o["official"])
    return {k: v[0] for k, v in by.items() if len(v) == 1}


def load(cur, data):
    canon = canon_map(data)
    appoint = {}
    for o in data.get("officials", []):
        ae = (o.get("appointive_or_elective") or "").lower()
        appoint[o["official"]] = True if ae.startswith("appointive") else (False if ae.startswith("elective") else None)
    for t in data["tracks"]:
        opened = t.get("opened")
        le = t.get("last_event") or {}
        if isinstance(le, str):
            le = {"what": le}
        notes = t.get("notes") or ""
        as_of = _d(t.get("status_as_of"))
        if not as_of:
            as_of = date.today().isoformat()
            notes = f"[status_as_of = harvest date] {notes}"
        cur.execute("""INSERT INTO matter_track (track_code, client_code, parent_matter_code, kind, forum, docket_or_ref,
                         our_role, true_status, status_as_of, status_source, opened_on, opened_source, last_event_on,
                         last_event, last_event_source, next_move, next_move_date, feeds_matters, counsel_gate,
                         can_sanction, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (t["track_code"], t["client_code"], t.get("parent_matter_code"), t["kind"], t["forum"],
                     t.get("docket_or_ref"), t.get("our_role"), t["true_status"], as_of,
                     t.get("status_source") or "[no source given]",
                     _d(opened.get("date")) if isinstance(opened, dict) else _d(opened),
                     json.dumps(opened, ensure_ascii=False) if isinstance(opened, dict) else opened,
                     _d(le.get("date")), le.get("what"), le.get("source"), t.get("next_move"),
                     _d(t.get("next_date")), t.get("feeds_matters") or [], t.get("counsel_gate"),
                     True if SANCTIONS.search(t["forum"]) else None, notes[:4000]))
        named = set()
        for p in t.get("pressure") or []:
            off = p.get("official")
            if not off:
                continue
            off = canon.get((t["client_code"], _surname(off)), off)
            named.add(off)
            role = "respondent" if any(off.split()[-1] in r for r in t.get("respondents_or_officials") or []) else "duty_holder"
            cur.execute("""INSERT INTO track_party (track_code, official, office, appointive, role, pressure_adds,
                             pressure_type, source) VALUES (%s,%s,NULL,%s,%s,%s,%s,%s)
                           ON CONFLICT (track_code, official, role) DO NOTHING""",
                        (t["track_code"], off, appoint.get(off), role, p.get("what") or "named", _ptype(p.get("what")),
                         t.get("status_source") or "tracks.json"))
    # officials whose track list names a track without an explicit pressure line
    for o in data.get("officials", []):
        for tc in o.get("tracks") or []:
            if o["official"] in [r["official"] for r in []]:
                pass
            cur.execute("""INSERT INTO track_party (track_code, official, office, appointive, role, pressure_adds, pressure_type, source)
                           SELECT %s,%s,%s,%s,'duty_holder','named on track (officials index)','none','tracks.json officials'
                            WHERE EXISTS (SELECT 1 FROM matter_track WHERE track_code=%s)
                              AND NOT EXISTS (SELECT 1 FROM track_party WHERE track_code=%s AND official=%s)""",
                        (tc, o["official"], o.get("office"), appoint.get(o["official"]), tc, tc, o["official"]))
        cur.execute("UPDATE track_party SET office=%s WHERE official=%s AND office IS NULL", (o.get("office"), o["official"]))


def render(cur, data):
    cur.execute("SELECT * FROM v_matter_reference ORDER BY client_code, parent_matter_code NULLS LAST, kind, track_code")
    rows = cur.fetchall()
    cur.execute("""SELECT * FROM v_official_pressure ORDER BY client_code, as_respondent_or_duty_holder DESC, tracks DESC""")
    off = cur.fetchall()
    ripe = {o["official"]: o.get("ripeness_summary") for o in data.get("officials", [])}
    out = [f"# Matter & track reference — all clients, judicial + administrative ({date.today()})", "",
           "INTERNAL. Built from `matter_track` / `track_party` (`migrations/DRAFT_drip_v2_fabric.sql` §6) in a "
           "**rolled-back dry run**: nothing is in the DB yet. Status = what the latest record shows; ⚠ = the DB "
           "says otherwise; 🆕 = the track has no matters row yet. Sources: `scratchpad tracks.json` → "
           "`scripts/load_matter_tracks.py`.", ""]
    client = None
    for r in rows:
        if r["client_code"] != client:
            client = r["client_code"]
            out += ["", f"## {client}", "",
                    "| Track | Matter | Kind | Forum · ref | Status (as of · source) | Last event | Next move | Officials | Sanctions? |",
                    "|---|---|---|---|---|---|---|---|---|"]
        flag = ("⚠ " if r["db_mismatch"] else "") + ("🆕 " if r["needs_matter_row"] else "")
        cell = lambda v: (str(v) if v not in (None, "") else "—").replace("|", "/").replace("\n", " ")
        out.append("| {}{} | {} | {} | {} · {} | {} ({} · {}) | {} {} | {}{} | {} | {} |".format(
            flag, r["track_code"], cell(r["parent_matter_code"]), r["kind"], cell(r["forum"])[:70],
            cell(r["docket_or_ref"])[:40], cell(r["true_status"])[:160], r["status_as_of"], cell(r["status_source"])[:60],
            cell(r["last_event_on"]), cell(r["last_event"])[:70], cell(r["next_move"])[:110],
            f" ({r['next_move_date']})" if r["next_move_date"] else "", cell(r["officials"])[:90],
            "yes" if r["can_sanction"] else "record-builder"))
    out += ["", "## Pressure accumulated per official (the rope)", "",
            "| Client | Official | Office | Tracks | As respondent/duty-holder | In sanctioning forums | Pressure types | Sanctioning forum | Ripeness |",
            "|---|---|---|---|---|---|---|---|---|"]
    for o in off:
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            o["client_code"], o["official"], (o["office"] or "—")[:50], o["tracks"], o["as_respondent_or_duty_holder"],
            o["in_sanctioning_forums"], ", ".join(o["pressure_types"] or []) or "—", o["sanctioning_forum"],
            (ripe.get(o["official"]) or "—").replace("|", "/")[:160]))
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--with-ddl", action="store_true", help="apply the DRAFT migration DDL inside the transaction")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    data = json.load(open(a.inp))
    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if a.with_ddl:
        ddl = open(os.path.join(os.path.dirname(__file__), "..", "migrations", "DRAFT_drip_v2_fabric.sql")).read()
        ddl = ddl.replace("BEGIN;", "", 1).rsplit("COMMIT;", 1)[0]
        cur.execute(ddl)
    load(cur, data)
    md = render(cur, data)
    with open(a.out, "w") as f:
        f.write(md)
    if a.apply and not a.with_ddl:
        conn.commit()
    else:
        conn.rollback()
    print(f"rendered {a.out}; {'COMMITTED' if (a.apply and not a.with_ddl) else 'rolled back'}")


if __name__ == "__main__":
    main()
