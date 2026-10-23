#!/usr/bin/env python3
"""drip_board.py — one board of where every drip ladder stands, across ALL pending matters. $0, read-only, never sends.

Runs nightly ON THE VPS (landtek-drip-nightly.timer, 00:00 Manila). Why (23 Oct 2026): the drip was being worked from chat and markdown while the structured tables went stale
(step_plan untouched since 20 Oct, office_obligation since 14 Sep, no clock ever served) and the jonzschoche
mail feed was dead. Nobody could see the whole picture. This board rebuilds it every night from what is
actually recorded:
  · ladders     = step_plan ∪ drip_event ladders ∪ the case_work/DRIP_LADDERS_* folders
  · outbound    = drip_event 'sent' / 'dispatched'
  · receipt     = drip_event 'receipt' (stamp / signed copy) or an office acknowledgment e-mail
  · refusals    = drip_event 'field' marked REFUSED
  · office mail = gmail_messages from a ladder's addresses after our last send (fed by mailapp_bridge.py)
  · clock       = receipt + 15 working days (RA 6713 §5(a)); weekends, drip_nonworking_day and the
                  UNCERTAIN days below are skipped, so a lapse is never claimed early.

  python3 scripts/drip_board.py                 # writes case_work/DRIP_BOARD.md and prints the summary
  python3 scripts/drip_board.py --stdout        # print the whole board instead
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.extras

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSN = os.environ.get("PG_DSN") or ("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n" if os.path.isdir("/root/landtek")
                                   else "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n")
OUT = os.path.join(REPO, "case_work", "DRIP_BOARD.md")            # all clients — LOCAL ONLY, never ingested
OUT_DIR = os.path.join(REPO, "case_work", "DRIP_BOARDS")          # one per client — these go to the corpus
PERIOD = 15
# Days that may or may not be declared non-working; counted as non-working so a lapse is never claimed early.
UNCERTAIN_NONWORKING = {date(2026, 11, 2): "All Souls (annual proclamation)",
                        date(2026, 12, 24): "Christmas Eve (proclamation)",
                        date(2026, 12, 31): "Last day of the year (proclamation)"}
STATUTORY = {date(2026, 11, 30): "Bonifacio Day", date(2026, 12, 8): "Immaculate Conception",
             date(2026, 12, 25): "Christmas Day", date(2026, 12, 30): "Rizal Day"}
OURS = {"jonzschoche@gmail.com", "jonathan@hayuma.org"}
FOLDER_CLIENT = (("PAR-", "Paracale-001"), ("NIBDC-", "NIBDC-001"), ("SEC-", "LANDTEK-CORP"))


def at_date(d):
    """drip_event 'at' strings: '2026-10-20', '2026-10-20 17:06 PHT', '2026-10-21 16:35'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(d or ""))
    return datetime.strptime(m.group(1), "%Y-%m-%d").date() if m else None


def add_working_days(start, n, off):
    d, k = start, 0
    while k < n:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in off:
            k += 1
    return d


def working_days_between(a, b, off):
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in off:
            n += 1
    return n


def emails_in(v):
    return {x.lower() for x in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", json.dumps(v))}


def build(cur, today):
    cur.execute("SELECT day FROM drip_nonworking_day")
    off = {r["day"] for r in cur.fetchall()} | set(UNCERTAIN_NONWORKING) | set(STATUTORY)

    L = defaultdict(lambda: {"client": None, "matter": set(), "steps": [], "addrs": set(), "office": set(), "sent": [],
                             "receipts": [], "refused": [], "replies": [], "notes": [], "states": set()})
    cur.execute("SELECT ladder, seq, client_code, matter_code, state, to_address, cc_addresses, the_ask FROM step_plan")
    for r in cur.fetchall():
        x = L[r["ladder"]]
        x["client"] = x["client"] or r["client_code"]
        x["matter"].add(r["matter_code"])
        x["states"].add(r["state"])
        for a in [r["to_address"], *(r["cc_addresses"] or [])]:
            if a:
                x["addrs"].add(a.lower())
        if r["to_address"]:
            x["office"].add(r["to_address"].lower())
    for f in glob.glob(os.path.join(REPO, "case_work", "DRIP_LADDERS_*", "*")):
        if os.path.isdir(f):
            name = os.path.basename(f)
            x = L[name]
            x["folder"] = os.path.relpath(f, REPO)
            if not x["client"]:
                x["client"] = next((c for p, c in FOLDER_CLIENT if name.startswith(p)), "MWK-001")
    cur.execute("""SELECT id, kind, created_at, detail FROM drip_event
                    WHERE kind IN ('sent','dispatched','receipt','reply','field','drafted') ORDER BY id""")
    for r in cur.fetchall():
        d = r["detail"] or {}
        lad = d.get("ladder") or d.get("track")
        if not lad:
            continue
        x = L[lad]
        when = at_date(d.get("at")) or r["created_at"].date()
        if r["kind"] in ("sent", "dispatched"):
            x["sent"].append((when, d.get("to") or d.get("channel") or "", r["id"]))
            for k in ("to", "cc"):
                x["addrs"] |= emails_in(d.get(k, "")) - OURS
            x["office"] |= emails_in(d.get("to", "")) - OURS
        elif r["kind"] == "receipt":
            x["receipts"].append((when, d.get("received_by") or d.get("proof") or d.get("note", "")[:60], r["id"]))
        elif r["kind"] == "reply":
            x["replies"].append((when, d.get("gist", "")[:140], d.get("next", ""), r["id"]))
            x["addrs"] |= emails_in(d.get("from", "")) - OURS
            x["office"] |= emails_in(d.get("from", "")) - OURS
        elif r["kind"] == "field":
            txt = json.dumps(d)
            if re.search(r"REFUSED|refused", txt) and not re.search(r"\bRECEIVED\b", txt):
                x["refused"].append((when, (d.get("note") or d.get("result") or d.get("outcome") or "")[:120], r["id"]))
        elif r["kind"] == "drafted":
            x["notes"].append(f"drafted {when}")
    # Our own outbound mail addressed TO a ladder's office counts as a send even if nobody logged it
    # (a cc to counsel on another office's request is not a send on counsel's ladder).
    for lad, x in L.items():
        if not x["office"]:
            continue
        cur.execute("""SELECT received_at FROM gmail_messages g
                        WHERE lower(substring(g.from_addr from '[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+')) = ANY(%s)
                          AND EXISTS (SELECT 1 FROM unnest(coalesce(g.to_addrs,'{}')) t
                                       WHERE lower(substring(t from '[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+')) = ANY(%s))
                          AND g.received_at > now() - interval '120 days'""",
                    (list(OURS), list(x["office"])))
        have = {s[0] for s in x["sent"]}
        for g in cur.fetchall():
            gd = (g["received_at"] + timedelta(hours=8)).date()
            if gd not in have:
                x["sent"].append((gd, "(from mail)", None))
                have.add(gd)
    # Office mail after our last send that the drip has not logged yet. Only the office the request went TO
    # counts (a cc'd lawyer's reply is not the office answering); same-day mail is ambiguous, so strictly later.
    for lad, x in L.items():
        if not x["office"] or not x["sent"]:
            continue
        last = max(s[0] for s in x["sent"])
        cur.execute("""SELECT received_at, from_addr, subject FROM gmail_messages
                        WHERE lower(substring(from_addr from '[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+')) = ANY(%s)
                          AND received_at >= %s ORDER BY received_at""",
                    (list(x["office"]), datetime.combine(last + timedelta(days=1), datetime.min.time()) - timedelta(hours=8)))
        logged = {r[0] for r in x["replies"]}
        for g in cur.fetchall():
            gd = (g["received_at"] + timedelta(hours=8)).date()   # UTC → PHT
            if gd not in logged:
                x.setdefault("unlogged", []).append((gd, g["from_addr"], (g["subject"] or "")[:90]))

    for lad, x in L.items():
        if not x["client"]:
            x["client"] = next((c for p, c in FOLDER_CLIENT if lad.startswith(p)), "MWK-001")
    rows = []
    for lad, x in L.items():
        if lad.startswith("TEST-"):
            continue
        last_sent = max(x["sent"])[0] if x["sent"] else None
        receipt = min((r for r in x["receipts"] if not last_sent or r[0] >= last_sent - timedelta(days=1)),
                      default=None)
        ack = None
        if not receipt and last_sent:
            acks = [r for r in x["replies"] if r[0] >= last_sent]   # any office reply proves receipt
            if acks:
                ack = min(acks)
        if not receipt and not ack and last_sent and x.get("unlogged"):
            first = min(g for g in x["unlogged"] if g[0] >= last_sent) if any(g[0] >= last_sent for g in x["unlogged"]) else None
            if first:
                ack = (first[0], "office e-mail (unlogged): " + first[2], None, None)
        proof = receipt or (ack and (ack[0], "acknowledged by e-mail: " + ack[1][:60], ack[3]))
        due = add_working_days(proof[0], PERIOD, off) if proof else None
        if x["refused"] and not proof:
            status = "REFUSED"
        elif x["replies"] and x["replies"][-1][0] >= (last_sent or date.min) and not re.search(
                r"(?i)acknowledg|forward|refer|will (look|get back|confer)|back (on )?monday", x["replies"][-1][1]):
            status = "ANSWERED: ACT"
        elif proof:
            status = "LAPSED" if due < today else "CLOCK RUNNING"
        elif last_sent:
            status = "SENT, NO PROOF"
        elif "drafted" in x["states"] or x["notes"]:
            status = "DRAFTED"
        elif "planned" in x["states"] or "approved" in x["states"]:
            status = "PLANNED"
        elif x["states"] and x["states"] <= {"skipped", "done"}:
            status = "SKIPPED"
        else:
            status = "FOLDER ONLY"
        rows.append({"ladder": lad, "client": x["client"] or "?", "matter": ",".join(sorted(m for m in x["matter"] if m)),
                     "status": status, "last_sent": last_sent, "proof": proof, "due": due,
                     "wd_left": working_days_between(today, due, off) if due and due >= today else None,
                     "last_reply": x["replies"][-1] if x["replies"] else None, "refused": x["refused"],
                     "unlogged": x.get("unlogged", []), "folder": x.get("folder")})
    return rows, off


ORDER = ["LAPSED", "ANSWERED: ACT", "REFUSED", "CLOCK RUNNING", "SENT, NO PROOF", "DRAFTED", "PLANNED",
         "FOLDER ONLY", "SKIPPED"]


def render(rows, today, client=None):
    by = defaultdict(list)
    for r in rows:
        by[r["status"]].append(r)
    out = [f"# Drip board{' — ' + client if client else ' — all clients (local only)'} — {today:%d %b %Y}",
           "",
           "Generated by `scripts/drip_board.py` (nightly). Read-only: nothing here is sent. Clocks = proof of receipt "
           "+ 15 working days (RA 6713 §5(a)); weekends, statutory holidays and uncertain proclamation days are skipped, "
           "so a lapse is never claimed early. Day math remains NEEDS-COUNSEL for any filing.",
           "",
           "| Status | Ladders |", "|---|---|"]
    for s in ORDER:
        if by[s]:
            out.append(f"| {s} | {len(by[s])} |")
    unl = [r for r in rows if r["unlogged"]]
    if unl:
        out += ["", "## Office mail not yet logged against its ladder", ""]
        for r in sorted(unl, key=lambda r: r["ladder"]):
            for g in r["unlogged"]:
                out.append(f"- **{r['ladder']}** · {g[0]:%d %b} · {g[1]} · {g[2]}")
    for s in ORDER:
        if not by[s]:
            continue
        out += ["", f"## {s} ({len(by[s])})", ""]
        if s in ("PLANNED", "FOLDER ONLY", "SKIPPED"):
            for client in sorted({r["client"] for r in by[s]}):
                names = ", ".join(sorted(r["ladder"] for r in by[s] if r["client"] == client))
                out.append(f"- {client}: {names}")
            continue
        out += ["| Ladder | Client | Last sent | Proof of receipt | Due | Working days left | Latest reply / note |",
                "|---|---|---|---|---|---|---|"]
        for r in sorted(by[s], key=lambda r: (r["due"] or date.max, r["ladder"])):
            proof = f"{r['proof'][0]:%d %b} {str(r['proof'][1])[:50]}" if r["proof"] else ""
            note = ""
            if r["last_reply"]:
                note = f"{r['last_reply'][0]:%d %b}: {r['last_reply'][1][:90]}"
            elif r["refused"]:
                note = f"{r['refused'][-1][0]:%d %b}: {r['refused'][-1][1][:90]}"
            out.append(f"| {r['ladder']} | {r['client']} | {r['last_sent']:%d %b}" if r["last_sent"] else
                       f"| {r['ladder']} | {r['client']} | ")
            out[-1] += (f" | {proof} | {r['due']:%d %b}" if r["due"] else f" | {proof} | ") + \
                f" | {'' if r['wd_left'] is None else r['wd_left']} | {note.replace('|', '/')} |"
    return "\n".join(out) + "\n"


def summary(rows, today):
    soon = [r for r in rows if r["status"] == "CLOCK RUNNING" and r["wd_left"] is not None and r["wd_left"] <= 3]
    lines = [f"Drip board {today:%d %b}: " + ", ".join(
        f"{sum(r['status'] == s for r in rows)} {s.lower()}" for s in ORDER if any(r["status"] == s for r in rows))]
    for r in sorted(rows, key=lambda r: r["ladder"]):
        if r["status"] in ("LAPSED", "ANSWERED: ACT") or r in soon or r["unlogged"]:
            tag = "unlogged office mail" if r["unlogged"] and r["status"] not in ("LAPSED", "ANSWERED: ACT") else r["status"]
            lines.append(f"  {tag:<22} {r['ladder']}" + (f" (due {r['due']:%d %b})" if r["due"] else ""))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    rows, _ = build(cur, today)
    md = render(rows, today)
    if a.stdout:
        print(md)
    else:
        with open(OUT, "w") as f:
            f.write(md)
        os.makedirs(OUT_DIR, exist_ok=True)
        for client in sorted({r["client"] for r in rows}):
            with open(os.path.join(OUT_DIR, f"DRIP_BOARD_{client}.md"), "w") as f:
                f.write(render([r for r in rows if r["client"] == client], today, client))
        print(summary(rows, today))
        print(f"board: {os.path.relpath(OUT, REPO)}")


if __name__ == "__main__":
    sys.exit(main())
