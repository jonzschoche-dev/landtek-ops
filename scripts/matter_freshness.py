#!/usr/bin/env python3
"""matter_freshness.py — the Grounded Matter Engine's currency layer ("up to the minute").

Each matter depends on a live input set: its linked documents (which change when re-OCR'd or
re-linked), its mapped legal authorities (which change when law is updated/superseded), and the
matter record itself. This fingerprints that set and flags a matter STALE the moment any input
changes since the last synthesis — and says WHAT changed. That event-driven invalidation is what
keeps generated documentation current instead of silently drifting. Pure-Python, creditless.

  python3 matter_freshness.py --scan --go     # recompute fingerprints + staleness for all matters
  python3 matter_freshness.py --report        # stale-first list with reasons
  python3 matter_freshness.py --matter MWK-CV26360
  python3 matter_freshness.py --mark-synthesized MWK-CV26360   # call after a synthesis run lands
"""
import hashlib
import json
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _inputs(cur, matter_code):
    """The live input set the matter's documentation depends on."""
    cur.execute("""SELECT l.doc_id, coalesce(d.text_length, 0) AS tl,
                          to_char(l.updated_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS lu
                   FROM document_matter_links l LEFT JOIN documents d ON d.id = l.doc_id
                   WHERE l.matter_code = %s ORDER BY l.doc_id""", (matter_code,))
    docs = {str(r["doc_id"]): [r["tl"], r["lu"]] for r in cur.fetchall()}
    cur.execute("""SELECT a.id, to_char(coalesce(a.as_of_checked, a.updated_at::date), 'YYYY-MM-DD') AS asof
                   FROM matter_authorities m JOIN legal_authorities a ON a.id = m.authority_id
                   WHERE m.matter_code = %s ORDER BY a.id""", (matter_code,))
    auth = {str(r["id"]): r["asof"] for r in cur.fetchall()}
    cur.execute("SELECT to_char(updated_at, 'YYYY-MM-DD\"T\"HH24:MI:SS') AS rev FROM matters WHERE matter_code=%s", (matter_code,))
    row = cur.fetchone()
    matter_rev = row["rev"] if row else None
    cur.execute("SELECT count(*) AS n FROM matter_facts WHERE matter_code=%s", (matter_code,))
    n_facts = cur.fetchone()["n"]
    return {"docs": docs, "authorities": auth, "matter_rev": matter_rev}, n_facts


def _fingerprint(inputs):
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _diff_reason(cur_inputs, synth_snap):
    if not synth_snap:
        return "never synthesized"
    cur_docs, old_docs = cur_inputs["docs"], (synth_snap.get("docs") or {})
    new_docs = [d for d in cur_docs if d not in old_docs]
    chg_docs = [d for d in cur_docs if d in old_docs and cur_docs[d][0] != old_docs[d][0]]
    cur_auth, old_auth = cur_inputs["authorities"], (synth_snap.get("authorities") or {})
    new_auth = [a for a in cur_auth if a not in old_auth]
    chg_auth = [a for a in cur_auth if a in old_auth and cur_auth[a] != old_auth[a]]
    parts = []
    if new_docs:
        parts.append(f"{len(new_docs)} new doc(s)")
    if chg_docs:
        parts.append(f"{len(chg_docs)} doc(s) re-OCR'd/changed")
    if new_auth:
        parts.append(f"{len(new_auth)} new authority(ies)")
    if chg_auth:
        parts.append(f"{len(chg_auth)} authority(ies) updated")
    if cur_inputs.get("matter_rev") != synth_snap.get("matter_rev"):
        parts.append("matter record edited")
    return "; ".join(parts) if parts else "inputs changed"


def scan(go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT matter_code FROM matters ORDER BY matter_code")
    matters = [r["matter_code"] for r in cur.fetchall()]
    stale = 0
    for mc in matters:
        inputs, n_facts = _inputs(cur, mc)
        fp = _fingerprint(inputs)
        cur.execute("SELECT last_synthesized_fingerprint, last_synth_snapshot FROM matter_state WHERE matter_code=%s", (mc,))
        st = cur.fetchone()
        last_fp = st["last_synthesized_fingerprint"] if st else None
        synth_snap = st["last_synth_snapshot"] if st else None
        is_stale = (fp != last_fp)
        reason = _diff_reason(inputs, synth_snap) if is_stale else "current"
        if is_stale:
            stale += 1
        if go:
            cur.execute("""INSERT INTO matter_state
                (matter_code, input_fingerprint, inputs_snapshot, is_stale, staleness_reason,
                 last_change_at, n_docs, n_authorities, n_facts, updated_at)
                VALUES (%s,%s,%s,%s,%s, now(),%s,%s,%s, now())
                ON CONFLICT (matter_code) DO UPDATE SET
                    input_fingerprint=EXCLUDED.input_fingerprint, inputs_snapshot=EXCLUDED.inputs_snapshot,
                    is_stale=EXCLUDED.is_stale, staleness_reason=EXCLUDED.staleness_reason,
                    last_change_at=CASE WHEN matter_state.input_fingerprint IS DISTINCT FROM EXCLUDED.input_fingerprint
                                        THEN now() ELSE matter_state.last_change_at END,
                    n_docs=EXCLUDED.n_docs, n_authorities=EXCLUDED.n_authorities, n_facts=EXCLUDED.n_facts,
                    updated_at=now()""",
                (mc, fp, json.dumps(inputs), is_stale, reason,
                 len(inputs["docs"]), len(inputs["authorities"]), n_facts))
    print(f"[freshness] {'WROTE' if go else 'DRY'} matters={len(matters)} stale={stale} current={len(matters)-stale}")
    cur.close(); c.close()


def mark_synthesized(matter_code):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    inputs, _ = _inputs(cur, matter_code)
    fp = _fingerprint(inputs)
    cur.execute("""UPDATE matter_state SET last_synthesized_fingerprint=%s, last_synth_snapshot=%s,
                   last_synthesized_at=now(), is_stale=false, staleness_reason='synthesized', updated_at=now()
                   WHERE matter_code=%s""", (fp, json.dumps(inputs), matter_code))
    print(f"[freshness] marked {matter_code} synthesized @ fp={fp}")
    cur.close(); c.close()


def report():
    c = _conn(); cur = c.cursor()
    cur.execute("""SELECT s.matter_code, m.matter_type, s.is_stale, s.n_docs, s.n_authorities, s.n_facts,
                          coalesce(s.staleness_reason,''), to_char(s.last_synthesized_at,'YYYY-MM-DD')
                   FROM matter_state s JOIN matters m ON m.matter_code=s.matter_code
                   ORDER BY s.is_stale DESC, s.n_docs DESC""")
    rows = cur.fetchall()
    print(f"{'MATTER':<26}{'TYPE':<16}{'STALE':<6}{'DOCS':>5}{'LAW':>4}{'FACTS':>6}  REASON / last-synth")
    for mc, mt, stale, nd, na, nf, reason, ls in rows:
        flag = "YES" if stale else "-"
        tail = reason if stale else f"synth {ls}"
        print(f"{mc:<26}{(mt or ''):<16}{flag:<6}{nd:>5}{na:>4}{nf:>6}  {tail}")
    cur.close(); c.close()


def show(matter_code):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    inputs, n_facts = _inputs(cur, matter_code)
    cur.execute("SELECT * FROM matter_state WHERE matter_code=%s", (matter_code,))
    st = cur.fetchone()
    print(json.dumps({"matter": matter_code, "n_docs": len(inputs["docs"]),
                      "n_authorities": len(inputs["authorities"]), "n_facts": n_facts,
                      "fingerprint": _fingerprint(inputs),
                      "is_stale": st["is_stale"] if st else None,
                      "reason": st["staleness_reason"] if st else "no state row",
                      "last_synthesized_at": str(st["last_synthesized_at"]) if st and st["last_synthesized_at"] else None}, indent=2))
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--mark-synthesized" in a:
        mark_synthesized(a[a.index("--mark-synthesized") + 1])
    elif "--matter" in a:
        show(a[a.index("--matter") + 1])
    elif "--report" in a:
        report()
    elif "--scan" in a:
        scan(go="--go" in a)
    else:
        print(__doc__)
