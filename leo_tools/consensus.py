#!/usr/bin/env python3
"""consensus.py — the Read Composer: one reader over the ranked stores (A86 candidate).

Design: docs/READ_CONSENSUS_DIRECTIVE.md. P0 scope: compose_answer() + four intents
(matter_status · title · deadlines · facts) + the composer_audit log.

Contract (directive §2):
  * ALWAYS answer — status makes degradation machine-legible:
      hit     — composed from answer-grade stores
      partial — claims exist, material gaps declared
      miss    — nothing answer-grade; gaps say why and what unblocks (A73/A74)
      hold    — A5 scope violation (the ONLY refusal at this layer)
  * Consensus is MECHANICAL (A24): provenance tier > as_of > corroboration > rank. No LLM here;
    LLMs paraphrase the frame at the emission plane (A75/A79), never upstream of it.
  * Authority order lives in consensus_registry (the table, never per-surface, never scattered
    in code). Embedded fallback exists only for degrade-don't-crash and flags itself as a gap.
  * mention_only stores (document_titles, proposed_facts, prose dates) contribute LEADS and GAPS,
    never answer values — mention is not membership.
  * The composer owns no truth (A50): reads SoR + derived cards; writes ONLY composer_audit.
    (Dissent→contradictions upserts are the drain phase, directive §6 — not P0.)

Deterministic, creditless, read-only on governed stores.

CLI smoke:
  python3 leo_tools/consensus.py --intent matter_status --matter MWK-GUARDIANSHIP
  python3 leo_tools/consensus.py --intent title --title T-4497
  python3 leo_tools/consensus.py --intent deadlines --client MWK-001
  python3 leo_tools/consensus.py --intent facts --matter MWK-CV26360 --topic SPA --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Tier → confidence the answer actually earns (A34: never upgraded downstream)
TIER_CONF = {
    "verified": 0.95,
    "operator": 0.90,
    "inferred_corroborated": 0.70,
    "inferred_strong": 0.55,
    "inferred_weak": 0.30,
}
CACHE_CONF = 0.80  # fresh derived card (rank 2)

# Degrade-don't-crash fallback if the registry table is unreachable; flags itself as a gap.
_FALLBACK_STALENESS_H = 26

INTENTS = ("matter_status", "title", "deadlines", "facts")


# ---------------------------------------------------------------- plumbing

def _cur():
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _claim(value, text, source_table, source_id, provenance, rank, excerpt=None):
    c = {"value": value, "text": text, "source_table": source_table,
         "source_id": source_id, "provenance": provenance, "rank": rank}
    if excerpt:
        c["excerpt"] = excerpt
    return c


def _gap(kind, detail=None, n=None, unblocks=None):
    g = {"kind": kind}
    if detail is not None:
        g["detail"] = detail
    if n is not None:
        g["n"] = n
    if unblocks is not None:
        g["unblocks"] = unblocks  # A74: what re-check condition clears this gap
    return g


def _confidence(claims):
    best = 0.0
    for c in claims:
        best = max(best, TIER_CONF.get(c.get("provenance") or "", CACHE_CONF if c.get("rank") == 2 else 0.4))
    return round(best, 2)


def _envelope(intent, params, client_code, role, status, claims, dissent, gaps, frame):
    return {
        "intent": intent,
        "params": params,
        "client_code": client_code,
        "role": role,
        "status": status,
        "claims": claims,
        "confidence": _confidence(claims) if claims else 0.0,
        "dissent": dissent,
        "gaps": gaps,
        "frame": frame,
        "freshness": datetime.now(timezone.utc).isoformat(),
    }


def _load_registry(cur, concept):
    try:
        cur.execute("SELECT store_rank, reconcile_rule, staleness_h FROM consensus_registry WHERE concept=%s",
                    (concept,))
        row = cur.fetchone()
        if row:
            return row, None
    except Exception as e:  # noqa: BLE001 — degrade, flag, keep answering
        return None, _gap("registry_unavailable", detail=str(e)[:200],
                          unblocks="consensus_registry reachable (deploy_939 applied)")
    return None, _gap("registry_unavailable", detail=f"no registry row for concept {concept}",
                      unblocks="seed consensus_registry (deploy_939)")


def _matter_client(cur, matter_code):
    cur.execute("SELECT client_code FROM matters WHERE matter_code=%s", (matter_code,))
    r = cur.fetchone()
    return r["client_code"] if r else None


def _scope_hold(intent, params, client_code, role, owner):
    """A5: the one refusal the composer makes. Scope is checked, never post-filtered."""
    return _envelope(intent, params, client_code, role, "hold", [], [],
                     [_gap("scope_refused",
                           detail=f"requested client {client_code!r} does not own this object (owner: {owner!r})")],
                     {"headline": "scope refused (A5)"})


def _audit(cur, env, caller=None):
    """Best-effort — the audit must never block the answer."""
    try:
        cur.execute(
            """INSERT INTO composer_audit (intent, params, client_code, role, status, n_claims,
                                           confidence, gaps, dissent, envelope, caller)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (env["intent"], json.dumps(env["params"]), env["client_code"], env["role"], env["status"],
             len(env["claims"]), env["confidence"], json.dumps(env["gaps"]), json.dumps(env["dissent"]),
             json.dumps(env, default=str), caller))
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------- intents

def _compose_matter_status(cur, matter, client_code, role, params):
    claims, dissent, gaps = [], [], []
    reg, reg_gap = _load_registry(cur, "matter_status")
    if reg_gap:
        gaps.append(reg_gap)
    staleness_h = (reg or {}).get("staleness_h") or _FALLBACK_STALENESS_H

    cur.execute("""SELECT matter_code, client_code, status, current_stage, forum, next_deadline,
                          next_event, docket_number, court_or_agency
                   FROM matters WHERE matter_code=%s""", (matter,))
    m = cur.fetchone()
    if not m:
        return _envelope("matter_status", params, client_code, role, "miss", [], [],
                         [_gap("unknown_matter", detail=matter,
                               unblocks="a matters row for this code")],
                         {"headline": f"no matter {matter}"})
    if client_code and m["client_code"] != client_code:
        return _scope_hold("matter_status", params, client_code, role, m["client_code"])

    # Rank 1 — the SoR row (structured, operator-maintained columns)
    claims.append(_claim(
        {"status": m["status"], "stage": m["current_stage"], "forum": m["forum"] or m["court_or_agency"]},
        f"{matter}: {m['status'] or '—'} / {m['current_stage'] or '—'} · {m['forum'] or m['court_or_agency'] or '—'}",
        "matters", matter, "operator", 1))
    if m["next_deadline"]:
        claims.append(_claim(m["next_deadline"].isoformat(),
                             f"next deadline {m['next_deadline'].isoformat()}",
                             "matters", matter, "operator", 1))
    else:
        gaps.append(_gap("needs_date", detail=f"{matter} has no structured next_deadline",
                         unblocks="a source-cited forward date (A68)"))

    # Rank 2 — the derived card, if fresh (stale card still shown, flagged)
    cur.execute("SELECT headline, computed_at, n_facts_verified, n_open_contradictions "
                "FROM matter_brief WHERE matter_code=%s", (matter,))
    b = cur.fetchone()
    n_v = 0
    if b:
        fresh = b["computed_at"] and b["computed_at"] > datetime.now(timezone.utc) - timedelta(hours=staleness_h)
        claims.append(_claim(b["headline"], b["headline"], "matter_brief", matter,
                             None, 2))
        if not fresh:
            gaps.append(_gap("stale_brief",
                             detail=f"matter_brief computed_at {b['computed_at']}",
                             unblocks="materialize_matter_brief run"))
        n_v = b["n_facts_verified"] or 0
        if b["n_open_contradictions"]:
            gaps.append(_gap("open_contradictions", n=b["n_open_contradictions"],
                             unblocks="contradiction resolution (directive §6)"))
    else:
        cur.execute("SELECT count(*) FILTER (WHERE provenance_level='verified') AS nv "
                    "FROM matter_facts WHERE matter_code=%s", (matter,))
        n_v = (cur.fetchone() or {}).get("nv") or 0

    # mention_only — proposed_facts contributes ONLY the gap, never a claim
    cur.execute("SELECT count(*) AS n FROM proposed_facts WHERE matter_code=%s "
                "AND status NOT IN ('accepted','rejected','promoted')", (matter,))
    npend = (cur.fetchone() or {}).get("n") or 0
    if npend:
        gaps.append(_gap("pending_adjudication", n=npend,
                         unblocks="adjudicate_sweep / operator batch queue (directive §6)"))

    status = "hit" if claims else "miss"
    if status == "hit" and (n_v == 0 or any(g["kind"] in ("needs_date",) for g in gaps)):
        status = "partial"
    frame = {"headline": claims[0]["text"] if claims else f"{matter}: no data",
             "verified_facts": n_v,
             "lines": [c["text"] for c in claims[1:]] + [f"[gap] {g['kind']}" + (f" ×{g['n']}" if g.get("n") else "")
                                                          for g in gaps]}
    return _envelope("matter_status", params, client_code, role, status, claims, dissent, gaps, frame)


def _norm_title_keys(raw):
    t = (raw or "").strip().upper().replace("TCT ", "").replace("NO. ", "").replace(" ", "")
    keys = [t]
    if t.startswith("T-"):
        keys.append(t[2:])
    else:
        keys.append("T-" + t)
    return list(dict.fromkeys(keys))


def _compose_title(cur, title_no, client_code, role, params):
    claims, dissent, gaps = [], [], []
    reg, reg_gap = _load_registry(cur, "title")
    if reg_gap:
        gaps.append(reg_gap)
    staleness_h = (reg or {}).get("staleness_h") or _FALLBACK_STALENESS_H
    keys = _norm_title_keys(title_no)

    # Rank 2 card first for scope resolution (title_brief carries client_code), but rank 1 wins content.
    cur.execute("SELECT * FROM title_brief WHERE upper(title_key) = ANY(%s) OR upper(display_no) = ANY(%s) "
                "ORDER BY computed_at DESC LIMIT 1", (keys, keys))
    brief = cur.fetchone()
    if client_code and brief and brief.get("client_code") and brief["client_code"] != client_code:
        return _scope_hold("title", params, client_code, role, brief["client_code"])

    cur.execute("SELECT * FROM titles WHERE upper(tct_number) = ANY(%s) LIMIT 1", (keys,))
    t = cur.fetchone()

    # Rank 3 support — the verified chain (authority over any face-read)
    cur.execute("""SELECT parent_title, child_title, relationship, provenance_level, source_doc_id
                   FROM title_chain
                   WHERE (upper(parent_title) = ANY(%s) OR upper(child_title) = ANY(%s))
                     AND provenance_level = 'verified'""", (keys, keys))
    chain = cur.fetchall()

    if not t and not brief:
        # mention_only may explain WHERE to look — leads, never an answer
        cur.execute("SELECT count(*) AS docs, coalesce(sum(mentions),0) AS mentions FROM document_titles "
                    "WHERE upper(tct_number) = ANY(%s)", (keys,))
        dm = cur.fetchone() or {}
        g = [_gap("unknown_title", detail=title_no, unblocks="a titles/title_brief row for this key")]
        if dm.get("docs"):
            g.append(_gap("mention_only_leads", n=dm["docs"],
                          detail=f"mentioned in {dm['docs']} docs ({dm['mentions']} mentions) — mention is not membership",
                          unblocks="face-read/comprehend the mentioning docs into titles"))
        return _envelope("title", params, client_code, role, "miss", [], [], gaps + g,
                         {"headline": f"no title record for {title_no}"})

    # Reconcile lifecycle: chain-cancellation outranks a clean face-read (the T-52540 trap)
    face_status = (t or {}).get("lifecycle_status") or (t or {}).get("status") or (brief or {}).get("lifecycle_status")
    cancelled_by = (t or {}).get("cancelled_by_title")
    chain_cancel = cancelled_by or any("cancel" in (e["relationship"] or "").lower() for e in chain
                                       if e["parent_title"].upper() in keys)
    if chain_cancel:
        canonical = f"cancelled{' → ' + cancelled_by if cancelled_by else ''}"
        if face_status and "cancel" not in face_status.lower():
            dissent.append({"value": face_status, "source_table": "titles(face-read)",
                            "lost_to": "title_chain (verified cancellation outranks face-read — authority rule)"})
    else:
        canonical = face_status or "unknown"

    if t:
        claims.append(_claim(
            {"tct_number": t["tct_number"], "registrant": t["registrant_canonical"] or t["registrant_name_raw"],
             "lifecycle": canonical, "area_sqm": float(t["area_sqm"]) if t["area_sqm"] is not None else None,
             "location": t["location"], "parent_title": t["parent_title"]},
            f"TCT {t['tct_number']}: {t['registrant_canonical'] or t['registrant_name_raw'] or '—'} · "
            f"{canonical} · {t['location'] or '—'}",
            "titles", t["tct_number"], t["provenance_level"] or "inferred_strong", 1,
            excerpt=None))
    if brief:
        fresh = brief["computed_at"] and brief["computed_at"] > datetime.now(timezone.utc) - timedelta(hours=staleness_h)
        claims.append(_claim(brief["headline"], brief["headline"], "title_brief", brief["title_key"], None, 2))
        if not fresh:
            gaps.append(_gap("stale_brief", detail=f"title_brief computed_at {brief['computed_at']}",
                             unblocks="materialize_title_brief run"))
    for e in chain:
        claims.append(_claim({"parent": e["parent_title"], "child": e["child_title"],
                              "relationship": e["relationship"]},
                             f"chain: {e['parent_title']} → {e['child_title']} ({e['relationship'] or 'derives'})",
                             "title_chain", e.get("source_doc_id"), e["provenance_level"], 3))

    n_answer = sum(1 for c in claims if c["rank"] <= 2)
    status = "hit" if n_answer else ("partial" if claims else "miss")
    if status == "hit" and canonical == "unknown":
        status = "partial"
        gaps.append(_gap("no_verified_fact", detail="lifecycle unresolved from SoR",
                         unblocks="verified chain edge or face-read reconcile"))
    frame = {"headline": claims[0]["text"] if claims else f"{title_no}: no data",
             "lines": [c["text"] for c in claims[1:6]] +
                      [f"[dissent] {d['value']} ({d['source_table']}) lost to chain" for d in dissent]}
    return _envelope("title", params, client_code, role, status, claims, dissent, gaps, frame)


def _compose_deadlines(cur, matter, client_code, role, params):
    claims, dissent, gaps = [], [], []
    _, reg_gap = _load_registry(cur, "deadlines")
    if reg_gap:
        gaps.append(reg_gap)

    if matter:
        owner = _matter_client(cur, matter)
        if owner is None:
            return _envelope("deadlines", params, client_code, role, "miss", [], [],
                             gaps + [_gap("unknown_matter", detail=matter)],
                             {"headline": f"no matter {matter}"})
        if client_code and owner != client_code:
            return _scope_hold("deadlines", params, client_code, role, owner)

    seen = set()

    # Home 1 — the structured SoR column
    cur.execute("""SELECT matter_code, next_deadline FROM matters
                   WHERE next_deadline IS NOT NULL
                     AND (%s::text IS NULL OR matter_code = %s)
                     AND (%s::text IS NULL OR client_code = %s)
                   ORDER BY next_deadline""", (matter, matter, client_code, client_code))
    today = datetime.now(timezone.utc).date()
    for r in cur.fetchall():
        key = (r["matter_code"], r["next_deadline"])
        seen.add(key)
        label = f"{r['matter_code']}: {r['next_deadline'].isoformat()}"
        if r["next_deadline"] < today:
            label += " [OVERDUE/stale — confirm done or re-date]"  # A57 overdue-confirm, never silent
        claims.append(_claim(r["next_deadline"].isoformat(), label,
                             "matters", r["matter_code"], "operator", 1))

    # Home 2 — the surfaced layer (freshness is A57's own test; we flag, not fail)
    cur.execute("SELECT max(as_of) AS latest FROM surfaced_deadlines")
    latest = (cur.fetchone() or {}).get("latest")
    if latest is None or latest < (datetime.now(timezone.utc).date() - timedelta(days=2)):
        gaps.append(_gap("surface_stale", detail=f"surfaced_deadlines as_of {latest}",
                         unblocks="deadlines.py nightly run (A57 freshness)"))
    else:
        cur.execute("""SELECT DISTINCT ON (matter_code, due_date) matter_code, due_date, label, kind
                       FROM surfaced_deadlines
                       WHERE as_of = %s AND due_date >= CURRENT_DATE
                         AND (%s::text IS NULL OR matter_code = %s)
                       ORDER BY matter_code, due_date""", (latest, matter, matter))
        for r in cur.fetchall():
            key = (r["matter_code"], r["due_date"])
            if key in seen:
                continue
            seen.add(key)
            claims.append(_claim(r["due_date"].isoformat(),
                                 f"{r['matter_code'] or '—'}: {r['due_date'].isoformat()} — {r['label'] or r['kind'] or ''}".strip(),
                                 "surfaced_deadlines", r["matter_code"], "operator", 1))

    # Home 3 — calendar events (source-cited rows carry their provenance; A68)
    cur.execute("""SELECT id, title, start_at, related_case, source_doc_id, status
                   FROM calendar_events
                   WHERE status IN ('scheduled','proposed') AND start_at >= now()
                     AND (%s::text IS NULL OR related_case = %s)
                   ORDER BY start_at LIMIT 40""", (matter, matter))
    for r in cur.fetchall():
        d = r["start_at"].date()
        key = (r["related_case"], d)
        if key in seen:
            continue
        seen.add(key)
        prov = "verified" if r["source_doc_id"] else "operator"
        label = f"{r['related_case'] or '—'}: {d.isoformat()} — {r['title']}"
        if r["status"] == "proposed":
            label += " [proposed — not confirmed]"
            prov = "inferred_strong"
        claims.append(_claim(d.isoformat(), label, "calendar_events", r["id"], prov, 1))

    # Honest undated count (never silenced — A57)
    cur.execute("""SELECT count(*) AS n FROM matters
                   WHERE status='active' AND next_deadline IS NULL
                     AND (%s::text IS NULL OR matter_code = %s)
                     AND (%s::text IS NULL OR client_code = %s)""",
                (matter, matter, client_code, client_code))
    undated = (cur.fetchone() or {}).get("n") or 0
    if undated:
        gaps.append(_gap("needs_date", n=undated,
                         detail=f"{undated} active matter(s) carry no forward date",
                         unblocks="source-cited dates (A68) or explicit dateless classification"))

    claims.sort(key=lambda c: c["value"])
    status = "hit" if claims else "miss"
    if status == "hit" and any(g["kind"] in ("needs_date", "surface_stale") for g in gaps):
        status = "partial"
    frame = {"headline": f"{len(claims)} dated item(s), {undated} undated",
             "lines": [c["text"] for c in claims[:12]]}
    return _envelope("deadlines", params, client_code, role, status, claims, dissent, gaps, frame)


def _compose_facts(cur, matter, topic, client_code, role, params):
    claims, dissent, gaps = [], [], []
    _, reg_gap = _load_registry(cur, "facts")
    if reg_gap:
        gaps.append(reg_gap)

    owner = _matter_client(cur, matter)
    if owner is None:
        return _envelope("facts", params, client_code, role, "miss", [], [],
                         gaps + [_gap("unknown_matter", detail=matter)],
                         {"headline": f"no matter {matter}"})
    if client_code and owner != client_code:
        return _scope_hold("facts", params, client_code, role, owner)

    like = f"%{topic}%" if topic else "%"
    # Answer grade: tier-ranked matter_facts (verified first; inferred only labeled)
    cur.execute("""SELECT id, statement, excerpt, source_id, provenance_level, as_of
                   FROM matter_facts
                   WHERE matter_code=%s AND statement ILIKE %s
                   ORDER BY CASE provenance_level
                              WHEN 'verified' THEN 0 WHEN 'operator' THEN 1
                              WHEN 'inferred_corroborated' THEN 2 WHEN 'inferred_strong' THEN 3
                              ELSE 4 END,
                            as_of DESC NULLS LAST, id DESC
                   LIMIT 12""", (matter, like))
    rows = cur.fetchall()
    for r in rows:
        label = r["statement"]
        if r["provenance_level"] not in ("verified", "operator"):
            label = f"[{r['provenance_level']}] {label}"   # inferred emitted only labeled (§4 rank 4)
        claims.append(_claim(r["statement"], label, "matter_facts", r["id"],
                             r["provenance_level"], 1 if r["provenance_level"] in ("verified", "operator") else 4,
                             excerpt=(r["excerpt"] or "")[:240] or None))

    n_verified = sum(1 for r in rows if r["provenance_level"] == "verified")
    if topic and n_verified == 0:
        gaps.append(_gap("no_verified_fact", detail=f"no verified fact matches {topic!r} in {matter}",
                         unblocks="verify_worker pass over the matching source docs"))

    # mention_only — pending proposals are a gap, never claims
    cur.execute("""SELECT count(*) AS n FROM proposed_facts
                   WHERE matter_code=%s AND status NOT IN ('accepted','rejected','promoted')
                     AND statement ILIKE %s""", (matter, like))
    npend = (cur.fetchone() or {}).get("n") or 0
    if npend:
        gaps.append(_gap("pending_adjudication", n=npend,
                         unblocks="adjudicate_sweep / operator batch queue (directive §6)"))

    answer_grade = [c for c in claims if c["rank"] == 1]
    status = "hit" if answer_grade else ("partial" if claims else "miss")
    if status == "hit" and gaps:
        status = "partial" if any(g["kind"] != "pending_adjudication" for g in gaps) else "hit"
    frame = {"headline": f"{matter}: {n_verified} verified / {len(rows)} matched" + (f" for {topic!r}" if topic else ""),
             "lines": [c["text"] for c in claims[:8]]}
    return _envelope("facts", params, client_code, role, status, claims, dissent, gaps, frame)


# ---------------------------------------------------------------- public API

def compose_answer(intent, client_code=None, role="operator", caller=None, **params):
    """The one reader (A86). Returns the envelope dict; never raises on missing data.

    client_code=None with role='operator' is the internal plane (all clients visible —
    the house pattern for operator surfaces). Any explicit client_code puts the A5 wall
    IN THE QUERY: a mismatch returns status='hold', never a filtered peek.
    """
    if intent not in INTENTS:
        return _envelope(intent, params, client_code, role, "miss", [], [],
                         [_gap("unknown_intent", detail=f"{intent} not in {INTENTS}",
                               unblocks="register the intent in the composer")],
                         {"headline": f"unknown intent {intent}"})
    conn, cur = _cur()
    try:
        if intent == "matter_status":
            env = _compose_matter_status(cur, params.get("matter"), client_code, role, params)
        elif intent == "title":
            env = _compose_title(cur, params.get("title"), client_code, role, params)
        elif intent == "deadlines":
            env = _compose_deadlines(cur, params.get("matter"), client_code, role, params)
        else:
            env = _compose_facts(cur, params.get("matter"), params.get("topic"), client_code, role, params)
        _audit(cur, env, caller=caller)
        return env
    finally:
        conn.close()


def render_frame(env):
    """Plain-text render of the frame — a convenience for CLI/debug. Surfaces use A75 projection."""
    out = [f"[{env['status']} conf={env['confidence']}] {env['frame'].get('headline', '')}"]
    out += [f"  {ln}" for ln in env["frame"].get("lines", [])]
    for g in env["gaps"]:
        out.append(f"  gap: {g['kind']}" + (f" ×{g['n']}" if g.get("n") else "") +
                   (f" — {g['detail']}" if g.get("detail") else ""))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Read Composer (A86) — one reader over the ranked stores")
    ap.add_argument("--intent", required=True, choices=INTENTS)
    ap.add_argument("--matter")
    ap.add_argument("--title")
    ap.add_argument("--topic")
    ap.add_argument("--client", dest="client_code")
    ap.add_argument("--role", default="operator")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    env = compose_answer(a.intent, client_code=a.client_code, role=a.role, caller="cli",
                         matter=a.matter, title=a.title, topic=a.topic)
    if a.json:
        print(json.dumps(env, indent=2, default=str))
    else:
        print(render_frame(env))
    return 0


if __name__ == "__main__":
    sys.exit(main())
