#!/usr/bin/env python3
"""strategy_engine.py — the client-strategy layer above the matters (the "larger role").

Matters are instruments of a client's north-star objective. This layer makes the agent
strategy-aware: it sets the apex objective, scores each matter's leverage toward it, and
detects KEYSTONES — single outcomes that cascade across many matters. It then re-ranks the
offensive war room by *advancement of the north-star*, so the agent leads with the move that
moves the whole campaign, not just whichever matter happens to have a ready play. Creditless.

Keesey (MWK-001) north-star (operator-confirmed 2026-06-14):
  Recover + consolidate the T-4497 estate — restore the full derivative chain to the heirs,
  free of the fraudulent transfers, then settle/secure the estate.

  python3 strategy_engine.py --seed --go        # north-star goal + matter leverage + keystones
  python3 strategy_engine.py --board MWK-001     # the client campaign board (cascade-ranked)
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

NORTH_STAR = {
    "MWK-001": ("Recover + consolidate the Mary Worrick Keesey estate — restore the full T-4497 "
                "derivative chain to the heirs free of the fraudulent transfers; AND compel the "
                "occupiers (LGU Mercedes and the named transferees) to PAY OR BUY — full-value "
                "compensation, lease, or negotiated purchase for land they cannot title (the "
                "Mariano v. Naga outcome) — using COA / Ombudsman / ARTA Sec.21 legal pressure as the lever."),
}

# matter_code -> (leverage 1-5, contribution, why) toward the north-star
MWK_LEVERAGE = {
    "MWK-CV26360":    (5, "spearhead", "litigates the de la Fuente keystone — voids Balane + cascades to the chain"),
    "MWK-LGU-RECOVERY": (5, "spearhead", "litigates the LGU keystone — void donation + ₱2.88M spend → pay-or-buy (Naga); monetizes the occupation"),
    "MWK-TCT4497":    (4, "advances",  "forces the RD chain record correction; sits in the keystone cascade"),
    "MWK-ESTATE":     (4, "advances",  "consolidation + settlement umbrella for the recovered estate"),
    "MWK-CV6839":     (3, "funds",     "just-compensation recovery converts a taking into estate value"),
    "MWK-ARTA-1210":  (3, "pressure",  "COA fraud-audit pressure on the LGU spend — feeds the LGU keystone"),
    "MWK-ARTA-1378":  (3, "pressure",  "the ₱2.88M audit / BAC-chairman exposure — feeds the LGU keystone"),
    "MWK-GUARDIANSHIP": (3, "protects", "protects Marcia + secures authority to act for the estate"),
    "MWK-OP-PETITION": (2, "pressure", "supervisory escalation pressure on the bureaucracy"),
}

# keystone = a single outcome that cascades across matters
KEYSTONES = [
    {"case_file": "MWK-001",
     "label": "de la Fuente SPA declared void (revoked 2005-08-15, predating the 2016 deed)",
     "controlling_matter": "MWK-CV26360",
     "cascade_matters": ["MWK-TCT4497", "MWK-ESTATE"],
     "basis": "A void authority is inexistent ab initio (Civil Code 1409): every instrument executed "
              "under it falls — the 2016 deed, Balane's T-079-2021002127, and the derivative chain from "
              "T-52540 — and the same defect reaches the 20 transferees who derive through that authority.",
     "downstream_note": "+ opens the 20 named-transferee recoveries (evidence_action_list)"},
    {"case_file": "MWK-001",
     "label": "LGU's 1953 donation declared void + the ₱2.88M spend exposed (no signed instrument; council admits no donation)",
     "controlling_matter": "MWK-LGU-RECOVERY",
     "cascade_matters": ["MWK-ARTA-1210", "MWK-ARTA-1378", "MWK-ARTA-1212", "MWK-ESTATE"],
     "basis": "A donation of immovable is void without a signed public instrument (Civil Code 749); the LGU "
              "holds no original deed, and its own councilors admit (SB group chat, Dec 2024 — source Ibasco) "
              "the donation cannot be found while debating a loan to BUY the land. The ₱2,881,071.57 Brentmin "
              "rehabilitation (PhilGEPS NOA 25-Sep-2024, Sanggunian-funded) was spent on titled TCT T-32911 with "
              "knowledge of the defect — Mariano v. City of Naga compels recovery or full compensation/lease.",
     "downstream_note": "+ opens the COA fraud audit (1210), the Ombudsman §3(e), and the pay-or-buy settlement leverage"},
]


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_objectives (
        id serial PRIMARY KEY, matter_code text NOT NULL, goal_id int, case_file text,
        contribution text, leverage int DEFAULT 1, note text, updated_at timestamptz DEFAULT now(),
        UNIQUE (matter_code))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS keystones (
        id serial PRIMARY KEY, case_file text, label text, controlling_matter text,
        cascade_matters text[] DEFAULT '{}', basis text, downstream_note text,
        status text DEFAULT 'open', updated_at timestamptz DEFAULT now(),
        UNIQUE (case_file, label))""")


def seed(go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    # 1. north-star objective in client_goals (idempotent on goal_category='north_star')
    cur.execute("SELECT DISTINCT client_id FROM client_goals WHERE case_file='MWK-001' LIMIT 1")
    row = cur.fetchone()
    client_id = row["client_id"] if row else None
    ns_id = None
    cur.execute("SELECT id FROM client_goals WHERE case_file='MWK-001' AND goal_category='north_star' LIMIT 1")
    ex = cur.fetchone()
    if ex:
        ns_id = ex["id"]
    elif go:
        cur.execute("""INSERT INTO client_goals (client_id, case_file, goal_text, goal_category, priority, status, progress_pct)
                       VALUES (%s,'MWK-001',%s,'north_star','critical','active',0) RETURNING id""",
                    (client_id, NORTH_STAR["MWK-001"]))
        ns_id = cur.fetchone()["id"]
        # re-parent the existing tactical goals under the north-star
        cur.execute("UPDATE client_goals SET parent_goal_id=%s WHERE case_file='MWK-001' AND goal_category<>'north_star' AND parent_goal_id IS NULL", (ns_id,))
    print(f"[strategy] north-star goal_id={ns_id} client_id={client_id}")
    # 2. matter leverage mapping (all MWK matters)
    cur.execute("SELECT matter_code, matter_type, status FROM matters WHERE case_file='MWK-001'")
    mapped = 0
    for m in cur.fetchall():
        mc = m["matter_code"]
        if (m["status"] or "") in ("closed", "merged", "archived", "out_of_scope", "resolved", "resolved_no_merit", "pending_triage", "pending_context"):
            lev, contrib, why = (0, "dormant", "terminal/triage — not active toward the north-star")
        elif mc in MWK_LEVERAGE:
            lev, contrib, why = MWK_LEVERAGE[mc]
        elif mc.startswith("MWK-ARTA"):
            lev, contrib, why = (2, "pressure", "administrative pressure / record-building")
        else:
            lev, contrib, why = (1, "support", "supporting matter")
        if go:
            cur.execute("""INSERT INTO matter_objectives (matter_code, goal_id, case_file, contribution, leverage, note, updated_at)
                VALUES (%s,%s,'MWK-001',%s,%s,%s, now())
                ON CONFLICT (matter_code) DO UPDATE SET goal_id=EXCLUDED.goal_id, contribution=EXCLUDED.contribution,
                    leverage=EXCLUDED.leverage, note=EXCLUDED.note, updated_at=now()""",
                (mc, ns_id, contrib, lev, why))
        mapped += 1
    # 3. keystones
    for k in KEYSTONES:
        if go:
            cur.execute("""INSERT INTO keystones (case_file, label, controlling_matter, cascade_matters, basis, downstream_note, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (case_file, label) DO UPDATE SET controlling_matter=EXCLUDED.controlling_matter,
                    cascade_matters=EXCLUDED.cascade_matters, basis=EXCLUDED.basis, downstream_note=EXCLUDED.downstream_note, updated_at=now()""",
                (k["case_file"], k["label"], k["controlling_matter"], k["cascade_matters"], k["basis"], k["downstream_note"]))
    print(f"[strategy] {'WROTE' if go else 'DRY'} matters_mapped={mapped} keystones={len(KEYSTONES)}")
    cur.close(); c.close()


def board(case_file):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT goal_text, progress_pct FROM client_goals WHERE case_file=%s AND goal_category='north_star' LIMIT 1", (case_file,))
    ns = cur.fetchone()
    cur.execute("SELECT * FROM keystones WHERE case_file=%s AND status='open'", (case_file,))
    keys = cur.fetchall()
    controlling = {k["controlling_matter"]: k for k in keys}
    # ready plays for this client's matters, joined with leverage
    cur.execute("""SELECT p.matter_code, p.title, p.impact, p.urgency_days, p.suggested_action,
                          coalesce(o.leverage,1) AS leverage, coalesce(o.contribution,'support') AS contribution
                   FROM matter_plays p
                   JOIN matters m ON m.matter_code=p.matter_code
                   LEFT JOIN matter_objectives o ON o.matter_code=p.matter_code
                   WHERE m.case_file=%s AND p.readiness='ready'""", (case_file,))
    plays = cur.fetchall()
    for p in plays:
        boost = 0
        if p["matter_code"] in controlling:
            boost = 30 + 5 * len(controlling[p["matter_code"]]["cascade_matters"])
        urg = 4 if (p["urgency_days"] is not None and p["urgency_days"] <= 14) else 0
        p["score"] = p["leverage"] * 10 + p["impact"] + boost + urg
        p["keystone"] = p["matter_code"] in controlling
    plays.sort(key=lambda x: x["score"], reverse=True)

    print("\n" + "=" * 78)
    print(f"CAMPAIGN BOARD — {case_file}")
    print("=" * 78)
    print(f"NORTH STAR: {ns['goal_text'] if ns else '(not set)'}")
    if keys:
        print("\nKEYSTONE(S) — one outcome, many matters unlocked:")
        for k in keys:
            print(f"  ◆ {k['label']}")
            print(f"      litigated in: {k['controlling_matter']}  →  cascades to: {', '.join(k['cascade_matters'])} {k.get('downstream_note') or ''}")
    if plays:
        top = plays[0]
        print("\n▶ HIGHEST-LEVERAGE MOVE (fire first):")
        kf = "  ★ KEYSTONE — unlocks the cascade above" if top["keystone"] else ""
        due = f" · ⏰{top['urgency_days']}d" if top["urgency_days"] is not None else ""
        print(f"  {top['title']}  [{top['matter_code']}{due}]{kf}")
        print(f"  do: {top['suggested_action']}")
        print("\nTHEN, by leverage toward the north-star:")
        for p in plays[1:12]:
            due = f"⏰{p['urgency_days']}d" if p["urgency_days"] is not None else "—"
            print(f"  [lev{p['leverage']}·{p['contribution']:<9}] {p['matter_code']:<20} {due:<6} {p['title']}")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--seed" in a:
        seed(go="--go" in a)
    elif "--board" in a:
        board(a[a.index("--board") + 1])
    else:
        print(__doc__)
