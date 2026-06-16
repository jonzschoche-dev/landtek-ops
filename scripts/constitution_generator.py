#!/usr/bin/env python3
"""constitution_generator.py — auto-generate the SYSTEM CONSTITUTION. $0, deterministic, no LLM.

WHY (operator, 2026-06-16): the system is fragmented — MASTER_PLAN (manual, stales), DB facts
(grounded but not synthesized), memos (static), engines (running without a unified grounded
context). The missing layer is a single machine-synthesized FACTS document that any LLM/human
reads before deciding, so outputs can't drift from verified ground truth.

DESIGN (deliberate, per the design review):
  • FACTS layer only. Intent / north-star / decisions stay MANUAL in MASTER_PLAN.md. This file is
    the auto-generated mirror of the DB; it POINTS to MASTER_PLAN for intent, never duplicates it.
  • Fixed preamble (operating rules — stable, hand-authored here) + generated body (volatile facts).
    The generator only ever writes the body.
  • Confidence is law: only provenance='verified' facts and keystone cascades are ASSERTED.
    Inferred facts are shown as COUNTS only (marked, never asserted). Candidate cascades go in an
    UNKNOWN section for human promotion — never auto-promoted to verified.
  • Cascade discipline (the lesson from the cross-client work): overlap is NOT a cascade. A shared
    Register of Deeds / appraiser / jurisdiction means nothing. The only asserted cascades are the
    hand-curated `keystones` rows (status open/verified), each re-checked for live grounding facts.
    Shared-title overlap is surfaced as an UNKNOWN candidate only.
  • Regenerate IN PLACE. Git history is the version trail; a content-hash header flags real change.
    No semantic version bumps on a daily auto-regen.

Reads (all `_safe`/grounded): matters, matter_facts (verified), keystones, matter_state.
  python3 scripts/constitution_generator.py            # print to stdout
  python3 scripts/constitution_generator.py --write     # write SYSTEM_CONSTITUTION.md (repo root)

Runs on the VPS (psycopg2 + PG_DSN). Rides landtek-cross-client.timer (regen after self-heal).
Wiring into LLM entry points (Leo systemMessage / comprehend / play+memo generation) is step 2.
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "SYSTEM_CONSTITUTION.md")
SKIP_MATTERS = ("AUTO-ARCHIVE",)   # orphan/archive buckets, not real matters

PREAMBLE = """## OPERATING RULES (fixed — read before every decision)

1. Read this brief AND `MASTER_PLAN.md` before any autonomous decision. This file is FACTS
   (auto, grounded); MASTER_PLAN is INTENT (manual, authoritative for direction).
2. Every play, memo, or output must CITE the verified fact(s) that support it (doc:NNN).
3. Only **VERIFIED** facts and cascades may be asserted. **Inferred** content is marked, never
   asserted as fact. **UNKNOWN** candidates are never assumed true — they are open questions.
4. Mark confidence on every claim: verified / inferred / unknown.
5. Overlap is not a cascade. A shared official, appraiser, or jurisdiction proves nothing — a
   cascade requires the SAME operative instrument with a traceable citation (see keystones).
6. Do not hand-edit the generated body below; it is overwritten on each regen. Fix the DB facts
   (`matter_facts`, `keystones`) and regenerate.
"""


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True
    return c


def _cur(c):
    return c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _q(cur, sql, args=None):
    cur.execute(sql, args or ())
    return cur.fetchall()


def gather(cur):
    d = {}
    # NORTH STARS — sourced from client_goals (data, not hardcoded). The north_star row per
    # client + its active sub-goals. This is the harvested framing from the designer's draft,
    # but grounded in the table instead of a hardcoded dict that would stale.
    d["north_stars"] = _q(cur, """
        SELECT case_file, goal_text, priority FROM client_goals
        WHERE goal_category='north_star' ORDER BY case_file""")
    d["subgoals"] = _q(cur, """
        SELECT case_file, goal_text FROM client_goals
        WHERE goal_category <> 'north_star' AND status='active' AND parent_goal_id IS NOT NULL
        ORDER BY case_file, priority""")
    d["verified_facts"] = _q(cur, """
        SELECT matter_code, statement, source_kind, source_id, as_of
        FROM matter_facts WHERE provenance_level='verified'
        ORDER BY matter_code, id""")
    d["inferred_counts"] = _q(cur, """
        SELECT matter_code, count(*) AS n FROM matter_facts
        WHERE provenance_level <> 'verified' GROUP BY matter_code ORDER BY n DESC""")
    d["keystones"] = _q(cur, """
        SELECT case_file, label, controlling_matter, cascade_matters, basis, downstream_note, status
        FROM keystones ORDER BY case_file, id""")
    d["matters"] = _q(cur, """
        SELECT m.matter_code, m.case_file, m.matter_type, m.title,
               coalesce(m.current_stage, m.status) AS stage, m.next_deadline, m.next_event,
               m.subject_titles, s.is_stale, s.staleness_reason, s.n_facts, s.last_synthesized_at
        FROM matters m LEFT JOIN matter_state s ON s.matter_code = m.matter_code
        WHERE (m.status IS NULL OR m.status NOT IN ('closed','archived'))
          AND m.matter_code <> ALL(%s)
        ORDER BY m.case_file, m.matter_code""", (list(SKIP_MATTERS),))
    return d


def _titles_of(m):
    st = m.get("subject_titles")
    if not st:
        return set()
    if isinstance(st, (list, tuple)):
        return {str(x).strip() for x in st if x}
    return {t.strip() for t in str(st).replace("{", "").replace("}", "").split(",") if t.strip()}


def candidate_cascades(matters, keystone_controllers):
    """UNKNOWN candidates: a title named as subject of >=2 matters → do they cascade? Never
    asserted. Overlap is a question, not a conclusion."""
    by_title = {}
    for m in matters:
        for t in _titles_of(m):
            by_title.setdefault(t, set()).add(m["matter_code"])
    out = []
    for title, mset in sorted(by_title.items()):
        if len(mset) >= 2:
            out.append((title, sorted(mset)))
    return out


def render(d, now_iso):
    L = []
    L.append("# SYSTEM CONSTITUTION")
    L.append("")
    L.append("> AUTO-GENERATED FACTS LAYER — do not hand-edit the body. The system reads this before "
             "every decision. Intent/strategy decisions are authored MANUALLY in `MASTER_PLAN.md`; "
             "this Constitution is the grounded-facts mirror (every line cited or marked).")
    L.append("")
    L.append(PREAMBLE)

    # ── NORTH STARS (per client; objective from client_goals, keystone from keystones) ──
    ks_by_cf = {}
    for k in d["keystones"]:
        ks_by_cf.setdefault(k["case_file"], []).append(k)
    sub_by_cf = {}
    for s in d["subgoals"]:
        sub_by_cf.setdefault(s["case_file"], []).append(s["goal_text"])
    L.append("## NORTH STARS (per client — objective + keystone)")
    L.append("")
    if not d["north_stars"]:
        L.append("_(no north_star goals set in client_goals)_")
    for ns in d["north_stars"]:
        cf = ns["case_file"]
        L.append(f"### {cf}")
        L.append(f"- **objective:** {ns['goal_text'].strip()}")
        for k in ks_by_cf.get(cf, []):
            casc = k["cascade_matters"]
            casc = ", ".join(casc) if isinstance(casc, (list, tuple)) else (casc or "")
            L.append(f"- **keystone:** {k['label']} → `{k['controlling_matter']}` cascades to {casc}")
        subs = sub_by_cf.get(cf, [])
        for s in subs[:6]:
            L.append(f"  - sub-goal: {s.strip()[:120]}")
        L.append("")

    # ── VERIFIED CASCADES (keystones, re-checked for grounding) ──
    vf = d["verified_facts"]
    facts_by_matter = {}
    for f in vf:
        facts_by_matter.setdefault(f["matter_code"], []).append(f)
    L.append("## VERIFIED CASCADES (asserted — keystones, each grounded in verified facts)")
    L.append("")
    asserted_ks = [k for k in d["keystones"] if (k["status"] or "").lower() in ("open", "verified")]
    if not asserted_ks:
        L.append("_(none)_")
    for k in asserted_ks:
        ctrl = k["controlling_matter"]
        grounding = facts_by_matter.get(ctrl, [])
        cites = ", ".join(sorted({f"{f['source_kind']}:{f['source_id']}" for f in grounding
                                  if f["source_id"]})[:6]) or "⚠ NO verified grounding facts"
        casc = k["cascade_matters"]
        casc = ", ".join(casc) if isinstance(casc, (list, tuple)) else (casc or "")
        L.append(f"- **[{k['case_file']}] {k['label']}**")
        L.append(f"  - controlling: `{ctrl}` → cascades to: {casc}")
        L.append(f"  - basis: {k['basis']}")
        L.append(f"  - grounded by (verified): {cites}")
    L.append("")

    # ── VERIFIED FACTS by matter ──
    L.append(f"## VERIFIED FACTS ({len(vf)} total, provenance=verified only)")
    L.append("")
    if not vf:
        L.append("_(none)_")
    for mc in sorted(facts_by_matter):
        L.append(f"### {mc} ({len(facts_by_matter[mc])})")
        for f in facts_by_matter[mc]:
            src = f"[{f['source_kind']}:{f['source_id']}]" if f["source_id"] else "[src?]"
            L.append(f"- {f['statement'].strip()} {src}")
        L.append("")

    # ── MATTER STATE ── (fact counts computed live from matter_facts, not the stale n_facts)
    inf_by_matter = {r["matter_code"]: r["n"] for r in d["inferred_counts"]}
    L.append("## MATTER STATE (active matters — stage · deadline · facts verified/inferred)")
    L.append("")
    cur_cf = object()
    for m in sorted(d["matters"], key=lambda x: (x["case_file"] or "~unfiled", x["matter_code"])):
        cf = m["case_file"] or "(unfiled)"
        if cf != cur_cf:
            cur_cf = cf
            L.append(f"### {cf}")
        dl = m["next_deadline"].isoformat() if m["next_deadline"] else "—"
        nv = len(facts_by_matter.get(m["matter_code"], []))
        ni = inf_by_matter.get(m["matter_code"], 0)
        stale = " · ⚠never-synthesized" if m["is_stale"] else ""
        L.append(f"- `{m['matter_code']}` · {m['stage']} · deadline {dl} · "
                 f"{nv}v/{ni}i{stale}")
    L.append("")

    # ── INFERRED (counts only — NOT asserted) ──
    L.append("## INFERRED — NOT verified (counts only; do not assert)")
    L.append("")
    total_inf = sum(r["n"] for r in d["inferred_counts"])
    L.append(f"_{total_inf} inferred_strong facts await verification. They are NOT ground truth — "
             f"verify against `_safe` sources before any output relies on them._")
    L.append("")
    for r in d["inferred_counts"][:12]:
        L.append(f"- {r['matter_code']}: {r['n']} inferred")
    L.append("")

    # ── UNKNOWN — candidate cascades (never assumed) ──
    ctrls = {k["controlling_matter"] for k in d["keystones"]}
    cands = candidate_cascades(d["matters"], ctrls)
    ks_cands = [k for k in d["keystones"] if (k["status"] or "").lower() not in ("open", "verified")]
    L.append("## UNKNOWN — CANDIDATE CASCADES (open questions; DO NOT assume)")
    L.append("")
    L.append("_Shared subjects below are QUESTIONS, not conclusions. A title appearing in two "
             "matters does not mean they cascade — promote to a keystone only with a traceable "
             "same-instrument citation._")
    L.append("")
    for k in ks_cands:
        L.append(f"- [{k['case_file']}] {k['label']} — keystone status `{k['status']}` [UNKNOWN]")
    for title, mset in cands:
        L.append(f"- title `{title}` is a subject of {', '.join(mset)} — do they cascade? [UNKNOWN]")
    if not ks_cands and not cands:
        L.append("_(no candidates detected)_")
    L.append("")

    body = "\n".join(L)
    h = hashlib.sha256(body.encode()).hexdigest()[:12]
    header = (f"<!-- generated-at: {now_iso} · content-hash: {h} · "
              f"source: matters + matter_facts(verified) + keystones + matter_state · $0 deterministic -->\n\n")
    return header + body + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help=f"write {OUT} (default: stdout)")
    a = ap.parse_args()
    c = _conn(); cur = _cur(c)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = render(gather(cur), now_iso)
    if a.write:
        with open(OUT, "w") as f:
            f.write(out)
        print(f"[constitution] wrote {OUT} ({len(out)} bytes)")
    else:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
