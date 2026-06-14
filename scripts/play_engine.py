#!/usr/bin/env python3
"""play_engine.py — the offensive layer of the Grounded Matter Engine.

A database is passive. This makes the system an AGENT: for every matter it maintains a ranked
queue of OFFENSIVE moves (motions, demands, filings, discovery, escalations, protective acts),
each with a readiness state computed from the live evidence matrix + deadlines + matter posture.
Re-run on every freshness event, so the queue is *always prepared* — and it's pure rules, so
preparation is $0. Credits are spent only when you tell it to DRAFT a specific move (on-demand).

Readiness: ready (fire now) | blocked (needs X) | watching (waits for a future event).

  python3 play_engine.py --generate-all --go
  python3 play_engine.py --matter MWK-CV26360
  python3 play_engine.py --queue            # cross-matter ranked "what to fire next"
"""
import datetime as dt
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def has(el, code):
    return el.get(code) == "have"


def thin(el, code):
    return el.get(code) in (None, "missing", "partial")


def missing(el, code):
    return el.get(code) in (None, "missing")


# Each play: (code, title, category, impact, legal_basis, suggested_action, rule)
# rule(m, el) -> (readiness, rationale, requires)
def _ready(why):
    return ("ready", why, None)


def _blocked(why, need):
    return ("blocked", why, need)


def _watch(why):
    return ("watching", why, None)


PLAYBOOK = {
    "accion_reinvindicatoria": [
        ("summary_judgment", "Move for Summary Judgment — void SPA → void deed → void title", "motion", 5,
         "Rule 35; void instruments are inexistent ab initio (Civil Code 1409)",
         "Draft SJ motion + supporting judicial affidavit citing the revocation + the chain.",
         lambda m, el: _ready("defect + ownership both proven — no genuine issue of fact")
            if has(el, "defect") and has(el, "ownership")
            else _blocked("core elements not yet proven", "harden " + ("defect" if not has(el, "defect") else "ownership"))),
        ("subpoena_adverse", "Subpoena defendant's Owner's Duplicate + BIR CAR", "discovery", 4,
         "Rule 21/27; PD 1529 §53 — a transfer with no CAR/owner's-duplicate cannot be registered",
         "Serve subpoena duces tecum; their inability to produce becomes affirmative void-proof.",
         lambda m, el: _ready("adverse title thinly evidenced — force production; absence proves void")
            if thin(el, "adverse_claim") else _watch("adverse claim already documented")),
        ("demand_cnr", "Demand CNRs (no CAR / no CGT / no registered deed)", "demand", 4,
         "evidence_action_list — a Certificate of No Record is affirmative proof the transfer is void",
         "Send CNR demand letters to RD/BIR/LGU/DAR per EVIDENCE_COLLECTION_LIST.",
         lambda m, el: _ready("the absence IS the evidence — demand the CNRs that prove non-recordability")),
        ("lis_pendens", "Annotate lis pendens on the contested derivative titles", "protect", 3,
         "Rule 13 §14; PD 1529 §76 — freeze the chain so no further good-faith transfer can occur",
         "File notice of lis pendens with the RD against each derivative TCT.",
         lambda m, el: _ready("land identity established — lock the title against onward transfer")
            if has(el, "identity") else _blocked("identity not pinned", "confirm technical description / parcel identity")),
    ],
    "ra11032": [
        ("file_section21", "File R.A. 11032 §21 complaint vs the official", "filing", 4,
         "R.A. 11032 §21 — fixing/undue delay/failure to render service",
         "File the complaint-affidavit with ARTA naming the respondent + the violation.",
         lambda m, el: _ready("violation documented + respondent identified")
            if has(el, "violation") and not missing(el, "respondent_forum")
            else _blocked("violation/respondent not nailed", "secure complaint-affidavit + respondent identity")),
        ("escalate_op_dilg", "Escalate to Office of the President / DILG", "escalation", 3,
         "R.A. 11032 — supervisory escalation after agency inaction",
         "File the manifestation/appeal to OP or DILG referencing the unresolved docket.",
         lambda m, el: _ready("notice/exhaustion shown — escalate")
            if has(el, "notice_exhaustion") else _watch("escalate once the 30-day window lapses")),
    ],
    "title_chain": [
        ("demand_rd_correction", "Demand RD title-history correction + certified chain", "demand", 4,
         "PD 1529 — force the official record to reflect the void 2016 deed → derivative chain",
         "Send demand to RD Camarines Norte; on refusal, ARTA referral (already a live path).",
         lambda m, el: _ready("defects in the chain identified — compel the official correction")
            if has(el, "defects") else _blocked("defects not yet proven", "document the void/spurious instrument")),
        ("file_adverse_claim", "File adverse claim on the contested derivative", "protect", 3,
         "PD 1529 §70 — put the world on notice of the estate's superior claim",
         "Register an adverse claim against the contested TCT.",
         lambda m, el: _ready("encumbrance posture supports an adverse claim")
            if not missing(el, "encumbrances") else _watch("gather encumbrance/annotation history first")),
    ],
    "estate_admin": [
        ("settle_estate_tax", "Settle estate tax (confirm current amnesty/penalty regime)", "filing", 4,
         "NIRC estate tax — amnesty windows change; verify current rule via AnyCase before filing",
         "Compute estate tax + any penalties; the amnesty deadline must be checked against current law.",
         lambda m, el: _ready("decedent death established — move estate tax now (verify amnesty status)")
            if has(el, "death") else _blocked("death not proven in corpus", "obtain death certificate")),
        ("publish_ejs", "Execute + publish Extrajudicial Settlement", "filing", 3,
         "Rule 74 — settle + publish to perfect the heirs' partition",
         "Draft EJS, secure heirs' signatures, publish 3 consecutive weeks.",
         lambda m, el: _ready("heirs established — execute the settlement")
            if has(el, "heirs") and not has(el, "settlement") else _watch("heirs/settlement not ready")),
    ],
    "just_compensation": [
        ("challenge_valuation", "File/raise just-valuation challenge", "filing", 4,
         "Rule 67 / R.A. 6657 — contest the offered valuation toward fair market value",
         "File the valuation challenge with the SAC/RTC with appraisal support.",
         lambda m, el: _ready("valuation evidence in hand — contest the offer")
            if not missing(el, "valuation") else _blocked("no valuation evidence", "obtain appraisal / zonal valuation")),
        ("demand_interest", "Demand interest from time of taking", "demand", 3,
         "just compensation accrues legal interest from the date of taking",
         "Compute + demand interest from the taking date.",
         lambda m, el: _ready("taking established — claim interest")
            if has(el, "taking") else _watch("establish the taking first")),
    ],
    "criminal": [
        ("file_complaint_affidavit", "File complaint-affidavit with the prosecutor", "filing", 5,
         "Rule 110 — initiate prosecution",
         "Prepare + file the complaint-affidavit with witness affidavits.",
         lambda m, el: _ready("act + accused identified")
            if has(el, "corpus_delicti") and has(el, "accused_identity")
            else _blocked("cannot charge yet", "identify the accused + secure witness affidavits")),
    ],
    "guardianship": [
        ("file_guardianship_petition", "File guardianship petition", "filing", 4,
         "Rule 92-97 — appoint a guardian to protect the ward's property",
         "File the verified petition with proof of incapacity + property inventory.",
         lambda m, el: _ready("ward status + estate documented")
            if has(el, "ward_status") and not missing(el, "estate_to_protect")
            else _blocked("petition not ready", "document ward incapacity + estate to protect")),
    ],
    "generic": [
        ("assemble_demand", "Assemble + send a demand letter", "demand", 2,
         "demand preserves rights + creates a record",
         "Draft the demand letter from the matter's documented facts.",
         lambda m, el: _ready("operative facts documented — send the demand")
            if has(el, "facts") else _blocked("facts thin", "link the operative documents to this matter")),
    ],
}


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_plays (
        id serial PRIMARY KEY,
        matter_code text NOT NULL,
        play_code text NOT NULL,
        title text, category text, impact int DEFAULT 3,
        readiness text DEFAULT 'watching',       -- ready | blocked | watching | done
        urgency_days int,                        -- days to next matter deadline (NULL = none)
        score int DEFAULT 0,
        rationale text, requires text, legal_basis text, suggested_action text,
        updated_at timestamptz DEFAULT now(),
        UNIQUE (matter_code, play_code))""")


def _days_to(deadline):
    if not deadline:
        return None
    return (deadline - dt.date.today()).days


def generate(matter_code, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    cur.execute("SELECT matter_type, legal_theory, title, status, next_deadline, current_stage FROM matters WHERE matter_code=%s", (matter_code,))
    m = cur.fetchone()
    if not m:
        cur.close(); c.close(); return {"matter": matter_code, "error": "no matter"}
    # don't propose offensive moves on terminal/triage matters — an agent that says "file on a won
    # case" loses trust. Clear any stale plays for them so the war room stays honest.
    TERMINAL = {"closed", "merged", "archived", "out_of_scope", "resolved", "resolved_no_merit",
                "pending_triage", "pending_context", "unknown"}
    if (m["status"] or "") in TERMINAL:
        if go:
            cur.execute("DELETE FROM matter_plays WHERE matter_code=%s", (matter_code,))
        cur.close(); c.close()
        return {"matter": matter_code, "skipped": m["status"], "plays": []}
    cur.execute("SELECT framework_key, element_code, status FROM matter_elements WHERE matter_code=%s", (matter_code,))
    rows = cur.fetchall()
    if not rows:
        cur.close(); c.close(); return {"matter": matter_code, "error": "no matrix — seed matter_elements first"}
    fw = rows[0]["framework_key"]
    el = {r["element_code"]: r["status"] for r in rows}
    days = _days_to(m["next_deadline"])
    out = {"matter": matter_code, "framework": fw, "plays": []}
    for code, title, cat, impact, basis, action, rule in PLAYBOOK.get(fw, PLAYBOOK["generic"]):
        readiness, rationale, requires = rule(m, el)
        score = impact * (2 if readiness == "ready" else 1) + (3 if (days is not None and days <= 14) else 0)
        out["plays"].append({"code": code, "readiness": readiness, "impact": impact, "score": score})
        if go:
            cur.execute("""INSERT INTO matter_plays
                (matter_code, play_code, title, category, impact, readiness, urgency_days, score,
                 rationale, requires, legal_basis, suggested_action, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (matter_code, play_code) DO UPDATE SET
                    title=EXCLUDED.title, category=EXCLUDED.category, impact=EXCLUDED.impact,
                    readiness=EXCLUDED.readiness, urgency_days=EXCLUDED.urgency_days, score=EXCLUDED.score,
                    rationale=EXCLUDED.rationale, requires=EXCLUDED.requires, legal_basis=EXCLUDED.legal_basis,
                    suggested_action=EXCLUDED.suggested_action, updated_at=now()""",
                (matter_code, code, title, cat, impact, readiness, days, score,
                 rationale, requires, basis, action))
    cur.close(); c.close()
    return out


def generate_all(go=False):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT DISTINCT matter_code FROM matter_elements ORDER BY matter_code")
    codes = [r[0] for r in cur.fetchall()]
    cur.close(); c.close()
    ready = 0
    for mc in codes:
        r = generate(mc, go=go)
        if "plays" in r:
            ready += sum(1 for p in r["plays"] if p["readiness"] == "ready")
    print(f"[play_engine] {'WROTE' if go else 'DRY'} matters={len(codes)} ready_plays={ready}")


def matter(matter_code):
    c = _conn(); cur = c.cursor()
    cur.execute("""SELECT readiness, impact, urgency_days, title, rationale, requires, suggested_action, legal_basis
                   FROM matter_plays WHERE matter_code=%s ORDER BY score DESC, impact DESC""", (matter_code,))
    rows = cur.fetchall()
    if not rows:
        print(f"no plays for {matter_code} — run --generate-all --go"); cur.close(); c.close(); return
    print(f"\nOFFENSIVE QUEUE — {matter_code}\n" + "=" * 74)
    for rd, imp, days, title, rat, req, act, basis in rows:
        mark = {"ready": "▶ READY  ", "blocked": "⛔ BLOCKED", "watching": "… WATCH  "}.get(rd, rd)
        due = f" · ⏰{days}d" if days is not None else ""
        print(f" [{imp}] {mark}{due}  {title}")
        print(f"        why: {rat}")
        if req:
            print(f"        needs: {req}")
        print(f"        do: {act}")
    cur.close(); c.close()


def queue():
    c = _conn(); cur = c.cursor()
    cur.execute("""SELECT p.matter_code, p.impact, p.urgency_days, p.title, p.suggested_action
                   FROM matter_plays p WHERE p.readiness='ready'
                   ORDER BY p.score DESC, p.impact DESC, p.urgency_days NULLS LAST LIMIT 25""")
    rows = cur.fetchall()
    print("WAR ROOM — ready offensive moves, ranked (fire next):\n" + "=" * 78)
    for mc, imp, days, title, act in rows:
        due = f"⏰{days}d" if days is not None else "—"
        print(f" [{imp}] {mc:<22} {due:<6} {title}")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--generate-all" in a:
        generate_all(go="--go" in a)
    elif "--matter" in a:
        matter(a[a.index("--matter") + 1])
    elif "--queue" in a:
        queue()
    elif "--generate" in a:
        import json
        print(json.dumps(generate(a[a.index("--generate") + 1], go="--go" in a), indent=2))
    else:
        print(__doc__)
