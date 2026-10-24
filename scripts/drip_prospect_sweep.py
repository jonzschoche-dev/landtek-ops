#!/usr/bin/env python3
"""drip_prospect_sweep.py — sweep the WHOLE MWK corpus for prospects (Jonathan, 23 Oct 2026: "these tables must be
expansive and the whole corpus needs to be swept for prospects for MWK issues, administrative etc").

Deterministic harvesters ($0, re-runnable; upsert on dedupe_key, never delete):
  H1 to_obtain      every "to obtain / TO-OBTAIN" item in the MWK desk files (case_work/**.md)
  H2 matter_step    each active MWK matter's recorded next event
  H3 office_asks_us an office e-mail asking US for something (fee, requirements, acknowledgment) with no later reply
  H4 contradiction  open contradictions on MWK matters (the drip never picks a value)
  H5 accountability ombudsman_candidates for MWK (legal desk; HELD for the defense stage per memory)
  H6 transferee     the 20 named transferees / occupants (counsel route for CV 26-360 defendants)
  H7 deadline       pending case_deadlines
  H8 custodian      a custodian in the map whose record type no ladder has asked for yet
Lanes: drip (a follow-up the drip may carry) · legal_desk (a position for Jonathan) · counsel · hold.
Score = kind weight x matter weight (case_work/DRIP_PRIORITIES.json) / 10, + deadline proximity.

  python3 scripts/drip_prospect_sweep.py [--dry-run]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime

import psycopg2
import psycopg2.extras

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from drip_board import load_priorities  # noqa: E402

from _pgdsn import dsn as _pgdsn  # noqa: E402
DSN = _pgdsn("172.18.0.3:5432" if os.path.isdir("/root/landtek") else "127.0.0.1:15432")
CLIENT = "MWK-001"
NOT_MWK = re.compile(r"(?i)paracale|nibdc|inocalla|landtek-corp|capacuan|gracesen|vito.cruz|\.bak|archive/")
TO_OBTAIN = re.compile(r"(?i)\bto[- ]obtain\b")
RECORD_RX = re.compile(r"(?i)certified|\bCTC\b|certification|registry of deeds|\bRD\b|assessor|treasurer|\bDENR\b|CENRO|PENRO|"
                       r"LMB|\bPSA\b|civil registr|\bBIR\b|\beCAR\b|clerk of court|\bOCC\b|notarial|plan\b|Psd-|tax declaration|"
                       r"\bARP\b|\bTD\b|resolution no|ordinance|building permit|\bOBO\b|\bMEO\b|barangay|\bDAR\b|land ?bank")
TIMELINE_RX = re.compile(r"^\s*(\d{1,2} \w{3,9} \d{4}|\d{4}-\d{2}-\d{2}|[QSGT]\d+[:.]?\s)")
KIND_WEIGHT = {"office_asks_us": 70, "deadline": 60, "to_obtain": 50, "matter_step": 45, "contradiction": 40,
               "custodian": 30, "accountability": 20, "transferee": 15}
COUNSEL_RX = re.compile(r"(?i)subpoena|motion|pleading|court order|formal offer|judicial affidavit|testif|\btrial\b|hearing")
NARRATIVE_RX = re.compile(r"(?i)\b(able|unable|order|failed|sought|tried|managed|seeking)\s+to\s+obtain\b|\bto obtain (a|an|the) (copy|certified copy) of the\b.{0,20}$")
MARKED_RX = re.compile(r"(?i)\[to-obtain\]|\bTO[- ]OBTAIN\b|\(to obtain\b|\bto[- ]obtain\s*[:=—-]|pivotal to-obtain|\bto-obtain\b")
HEADING_RX = re.compile(r"(?i)^\s*(#+|\*\*|\d+(\.\d+)*\s).{0,60}\b(to obtain|gaps)\b")
BULLET_RX = re.compile(r"^\s*([-*+]|\d+[.)]|\|)\s+\S")
POSITION_RX = re.compile(r"(?i)decide|decision|strategy|position|whether to|choose|appeal|complaint against")
ASK_RX = re.compile(r"(?i)\b(please|kindly)\s+(pay|submit|send|provide|acknowledge|present|comply)|\bresearch fee\b|"
                    r"\bcertification fee\b|\brequirements?\b.{0,40}\b(submit|comply|present)")


def key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).lower().encode()).hexdigest()[:24]


def matter_from_path(path):
    p = path.replace("\\", "/")
    for pat, m in ((r"CV26360|26-360", "MWK-CV26360"), (r"SP2680|GUARDIANSHIP", "MWK-GUARDIANSHIP"),
                   (r"CV6839|6839", "MWK-CV6839"), (r"MWK-ARTA-(\d+)", None), (r"LGU|COMPOUND|ROAD.?LOT", "MWK-LGU-RECOVERY"),
                   (r"DLF|DELA.?FUENTE|DE.LA.FUENTE", "MWK-DLF-VOID"), (r"OP_|OP-PETITION|OP_1321", "MWK-OP-PETITION")):
        m_ = re.search(pat, p, re.I)
        if m_:
            return m if m else f"MWK-ARTA-{m_.group(1)}"
    return "MWK-001"


def clean(line):
    t = re.sub(r"[*_`#>|]+", " ", line)
    t = re.sub(r"\[(to-obtain|TO-OBTAIN)\]", "", t)
    return re.sub(r"\s+", " ", t).strip(" -:·")


def h1_to_obtain():
    out = []
    for f in glob.glob(os.path.join(REPO, "case_work", "**", "*.md"), recursive=True):
        rel = os.path.relpath(f, REPO)
        if NOT_MWK.search(rel):
            continue
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().splitlines()
        except OSError:
            continue
        under = 0   # bullets under a "records to obtain / gaps" heading are prospects too
        for i, line in enumerate(lines, 1):
            if HEADING_RX.search(line) and len(clean(line)) < 70:
                under = 30
                continue
            if under and (line.lstrip().startswith("#") or (line.strip() == "" and under < 28)):
                under = 0 if line.lstrip().startswith("#") else under
            is_bullet = under > 0 and BULLET_RX.search(line) and not re.match(r"^\s*\|[-: |]+\|?\s*$", line)
            if under:
                under -= 1
            if not (is_bullet or (TO_OBTAIN.search(line) and MARKED_RX.search(line))):
                continue
            nxt = lines[i] if i < len(lines) else ""
            if re.match(r"^\s*\|[-: |]+\|?\s*$", nxt):   # a table's header row, not an item
                continue
            if NARRATIVE_RX.search(line) or len(line.strip()) < 12:
                continue
            t = clean(line)
            if NOT_MWK.search(t) or len(t) < 15:
                continue
            lane = "counsel" if (COUNSEL_RX.search(t) or "CV26360_COMPLETE" in rel) else "drip"
            out.append(dict(matter_code=matter_from_path(rel), kind="to_obtain", title=t[:200], detail=t[:1200],
                            lane=lane, source_kind="file", source_ref=f"{rel}:{i}", excerpt=line.strip()[:500],
                            dedupe_key=key("to_obtain", re.sub(r"[^a-z0-9]+", " ", t.lower())[:160])))
    return out


def h2_matter_step(cur):
    cur.execute("""SELECT matter_code, title, current_stage, next_event, next_deadline FROM matters
                    WHERE (matter_code LIKE 'MWK%%' OR client_code='MWK-001')
                      AND coalesce(status,'') NOT IN ('closed','archived','merged','out_of_scope','pending_triage')
                      AND coalesce(next_event,'') <> ''""")
    out = []
    for r in cur.fetchall():
        t = f"{r['matter_code']}: {r['next_event']}"
        out.append(dict(matter_code=r["matter_code"], kind="matter_step", title=t[:200], detail=t[:1500],
                        lane="legal_desk" if POSITION_RX.search(r["next_event"]) else "drip", source_kind="table",
                        source_ref=f"matters:{r['matter_code']}", excerpt=(r["current_stage"] or "")[:300],
                        dedupe_key=key("matter_step", r["matter_code"], r["next_event"][:200]),
                        _deadline=r["next_deadline"]))
    return out


def h3_office_asks_us(cur):
    cur.execute("""SELECT g.id, g.from_addr, g.subject, g.received_at, left(coalesce(g.body_plain,''), 3000) body, e.doc_id
                     FROM gmail_messages g LEFT JOIN email_documents e ON e.message_id=g.message_id AND e.role='body'
                    WHERE g.case_file LIKE 'MWK%%' AND g.received_at > now() - interval '150 days'
                      AND g.from_addr !~* '(zschoche|hayuma)'""")
    out = []
    for g in cur.fetchall():
        body = re.split(r"\n\s*(On .{0,80}wrote:|From: )", g["body"] or "")[0]
        m = ASK_RX.search(body)
        if not m:
            continue
        frm = (re.findall(r"[\w.+-]+@[\w.-]+", g["from_addr"] or "") or [""])[0].lower()
        cur.execute("""SELECT 1 FROM gmail_messages WHERE from_addr ~* '(zschoche|hayuma)' AND received_at > %s
                        AND (to_addrs::text ILIKE %s OR cc_addrs::text ILIKE %s) LIMIT 1""",
                    (g["received_at"], f"%{frm}%", f"%{frm}%"))
        answered = bool(cur.fetchone())
        s = max(0, m.start() - 120)
        out.append(dict(matter_code="MWK-001", kind="office_asks_us",
                        title=f"{frm} asks us: {(g['subject'] or '')[:120]}" + (" (we wrote back since)" if answered else ""),
                        detail=body[s:s + 700], office=frm, lane="drip", source_kind="gmail",
                        source_ref=f"gmail_messages:{g['id']}", excerpt=body[s:s + 300],
                        evidence_doc_ids=[g["doc_id"]] if g["doc_id"] else [],
                        dedupe_key=key("office_asks_us", g["id"]), _answered=answered))
    return out


def h4_contradiction(cur):
    cur.execute("""SELECT matter_code, event, kind, values, fact_ids, status, created_at FROM contradictions
                    WHERE matter_code LIKE 'MWK%%' AND coalesce(status,'open') ~* 'open'""")
    out = []
    for r in cur.fetchall():
        t = f"{r['matter_code']}: {r['kind'] or 'contradiction'} — {str(r['event'] or '')[:150]}"
        out.append(dict(matter_code=r["matter_code"], kind="contradiction", title=t[:200],
                        detail=json.dumps(r["values"], default=str)[:1500], lane="legal_desk", source_kind="table",
                        source_ref=f"contradictions:{r['matter_code']}:{r['created_at']:%Y-%m-%d}",
                        dedupe_key=key("contradiction", r["matter_code"], r["event"], json.dumps(r["values"], default=str)[:300])))
    return out


def h5_accountability(cur):
    cur.execute("""SELECT id, official, office, violation_code, statute, forum, status, score, rationale FROM ombudsman_candidates
                    WHERE (client_code LIKE 'MWK%%' OR client_code IS NULL) AND coalesce(status,'') !~* '(closed|dismissed|rejected)'""")
    out = []
    for r in cur.fetchall():
        t = f"{r['official'] or '?'} ({r['office'] or '?'}): {r['violation_code'] or ''} {r['statute'] or ''} → {r['forum'] or ''}"
        out.append(dict(matter_code="MWK-001", kind="accountability", title=t[:200], detail=(r["rationale"] or "")[:1500],
                        office=r["office"], lane="legal_desk", source_kind="table", source_ref=f"ombudsman_candidates:{r['id']}",
                        dedupe_key=key("accountability", r["id"])))
    return out


def h6_transferee(cur):
    cur.execute("SELECT id, canonical_name, accion_status, current_possession, action_needed FROM transferees")
    out = []
    for r in cur.fetchall():
        name = r["canonical_name"] or "?"
        balane = re.search(r"(?i)balane|torralba", name)
        t = f"Transferee/occupant {name}" + (f": {r['action_needed']}" if r["action_needed"] else "")
        out.append(dict(matter_code="MWK-CV26360" if balane else "MWK-TCT4497", kind="transferee", title=t[:200],
                        detail=f"accion: {r['accion_status'] or '-'}; possession: {r['current_possession'] or '-'}",
                        lane="counsel" if balane else "hold", source_kind="table", source_ref=f"transferees:{r['id']}",
                        dedupe_key=key("transferee", r["id"])))
    return out


def h7_deadline(cur):
    cur.execute("""SELECT id, case_file, title, due_date FROM case_deadlines
                    WHERE coalesce(status,'') NOT IN ('done','completed','cancelled','superseded')
                      AND due_date >= current_date - 7 AND (case_file LIKE 'MWK%%')""")
    return [dict(matter_code=r["case_file"], kind="deadline", title=f"{r['due_date']}: {r['title']}"[:200], lane="legal_desk",
                 source_kind="table", source_ref=f"case_deadlines:{r['id']}", dedupe_key=key("deadline", r["id"]),
                 _deadline=r["due_date"]) for r in cur.fetchall()]


def h8_custodian(cur):
    cur.execute("""SELECT c.record_type, c.custodian, c.basis FROM drip_custodian c
                    WHERE NOT EXISTS (SELECT 1 FROM step_plan s WHERE s.record_type = c.record_type)""")
    return [dict(matter_code="MWK-001", kind="custodian", title=f"Not yet asked: {r['record_type']} from {r['custodian']}"[:200],
                 detail=r["basis"], office=r["custodian"], lane="drip", source_kind="table",
                 source_ref=f"drip_custodian:{r['record_type']}", dedupe_key=key("custodian", r["record_type"]))
            for r in cur.fetchall()]


def score(p, weights):
    w = weights.get(p["matter_code"], weights.get("MWK-ARTA" if (p["matter_code"] or "").startswith(("MWK-ARTA", "MWK-OMB", "MWK-OP")) else "MWK-001", 5))
    s = KIND_WEIGHT.get(p["kind"], 30) * w / 10
    d = p.get("_deadline")
    if d:
        if isinstance(d, str):
            d = datetime.strptime(d[:10], "%Y-%m-%d").date()
        days = (d - date.today()).days
        s += max(0, 30 - days) / 2 if days >= 0 else 0
    if p.get("_answered"):
        s -= 25
    if p["kind"] == "to_obtain":
        if RECORD_RX.search(p["title"]):
            s += 15          # a concrete record from a named custodian: what the drip can actually ask for
        if TIMELINE_RX.search(p["title"]):
            s -= 20          # a dated narrative line under a gaps heading, rarely an ask by itself
    return round(max(s, 0), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    weights = {k: v.get("weight", 5) for k, v in load_priorities().get("matters", {}).items()}
    found = h1_to_obtain() + h2_matter_step(cur) + h3_office_asks_us(cur) + h4_contradiction(cur) + \
        h5_accountability(cur) + h6_transferee(cur) + h7_deadline(cur) + h8_custodian(cur)
    seen, new, upd = set(), 0, 0
    for p in found:
        if p["dedupe_key"] in seen:
            continue
        seen.add(p["dedupe_key"])
        sc = score(p, weights)
        cur.execute("""INSERT INTO drip_prospect (client_code, matter_code, kind, title, detail, office, lane, score, source_kind,
                              source_ref, excerpt, evidence_doc_ids, dedupe_key)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (dedupe_key) DO UPDATE SET score=EXCLUDED.score, last_seen=now(),
                              title=EXCLUDED.title, detail=EXCLUDED.detail,
                              lane=CASE WHEN drip_prospect.decided_at IS NULL AND drip_prospect.decision_note IS NULL
                                        THEN EXCLUDED.lane ELSE drip_prospect.lane END
                       RETURNING (xmax = 0) AS inserted""",
                    (CLIENT, p["matter_code"], p["kind"], p["title"], p.get("detail"), p.get("office"), p["lane"], sc,
                     p["source_kind"], p["source_ref"], p.get("excerpt"), p.get("evidence_doc_ids") or [], p["dedupe_key"]))
        if cur.fetchone()["inserted"]:
            new += 1
        else:
            upd += 1
    if a.dry_run:
        c.rollback()
    else:
        c.commit()
    by = {}
    for p in found:
        by.setdefault((p["kind"], p["lane"]), 0)
        by[(p["kind"], p["lane"])] += 1
    print(f"prospects found {len(seen)} (new {new}, refreshed {upd}){' — DRY RUN' if a.dry_run else ''}")
    for (k, l), n in sorted(by.items(), key=lambda x: -x[1]):
        print(f"  {k:<15} {l:<11} {n}")


if __name__ == "__main__":
    main()
