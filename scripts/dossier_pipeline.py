#!/usr/bin/env python3
"""dossier_pipeline.py — ONE request -> an accurate, DECISION-FIRST dossier for a matter.

Makes the dossier correct BY CONSTRUCTION, not hand-assembled. Each stage is a GATE:

  0 COMPLETENESS  recover referenced-but-unheld records from the LIVE sources + OCR (find_missing_record)
  1 INTEGRITY     complaint present? no cross-matter contamination / blanks / hollow scans?
  2 POSITION      claim<->forum<->remedy fit (flags 'positioned to lose'); posture/clock; the opponent's
                  FILED position; element->proof map; gaps
  3 SYNTHESIS     decision-first dossier (bottom line -> status -> position -> element-by-element proof ->
                  opponent + rebuttal -> gaps -> actions). A doc earns its place only by proving a point.
  4 GATE          diligence (dossier_verify)
  5 DELIVER       bound PDF (brief + exhibits in order)  (case_bundle --brief)

Runs on the MAC (reuses case_synthesizer's local RAG + Ollama + ssh DB). Stages 0 & 5 run on the VPS.

  python3 scripts/dossier_pipeline.py MWK-ARTA-1319 [--send] [--no-recover] [--frontier]
"""
import argparse, os, subprocess, sys
import case_synthesizer as cs

VPS = os.environ.get("LANDTEK_VPS", "root@100.85.203.58")
OUTDIR = "1891_output"
Q = cs._vps_psql

DOCKETS = {"MWK-ARTA-1319": "SL-2026-0209-1319", "MWK-ARTA-1321": "SL-2026-0209-1321",
           "MWK-ARTA-1210": "SL-2026-0128-1210", "MWK-ARTA-1212": "SL-2026-0128-1212",
           "MWK-ARTA-1378": "SL-2026-0218-1378"}
PLAYBOOKS = {
    "MWK-ARTA": {
        "forum": "the Anti-Red Tape Authority (ARTA), under R.A. No. 11032",
        "grants": "administrative sanctions on officials for service-delivery (red-tape) violations under §21",
        "cannot_grant": "correction of cadastral/survey records, or boundary / title / patent validity / ownership",
        "reserve_to": "the DENR Land Management Bureau (technical correction) and the Regional Trial Court (title/boundary)",
        "law": "11032", "law_kw": "Imposition of additional requirements",
        "elements": [
            ("§21(e) / §9 — failure to render the service within the prescribed processing time",
             "a dated request to the office + the Citizen's Charter processing clock + no compliant response within it",
             ("Citizens Charter", "working day")),
            ("§21(b)/(c) — imposition of a requirement or cost not in the Citizen's Charter",
             "an extra-legal requirement (e.g. hire a private professional, sue) imposed on the requester",
             ("11032", "Imposition of additional requirements")),
        ],
    },
}


def _pb(matter):
    return next((pb for pre, pb in PLAYBOOKS.items() if matter.startswith(pre)), None)


def _one(sql):
    return (Q(sql) or "").strip()


def _rows(sql, n=6):
    return [r for r in (Q(sql) or "").splitlines() if r.strip()][:n]


# ── 0 COMPLETENESS ───────────────────────────────────────────────────────────
def stage_completeness(matter, apply):
    print("\n── 0 · COMPLETENESS (recover from live sources) ──")
    cmd = ("cd /root/landtek && set -a; . .env 2>/dev/null; set +a; "
           f"python3 scripts/find_missing_record.py --matter {matter}" + (" --apply" if apply else ""))
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=60", VPS, cmd], capture_output=True, text=True, timeout=1200)
    for l in r.stdout.splitlines():
        if l.startswith("[find]") or l.strip().startswith(("+", "⊕")):
            print("   " + l.strip())


# ── 1 INTEGRITY ────────────────────────────────────────────────────────────────
def stage_integrity(matter, docket):
    print("\n── 1 · INTEGRITY (clean, complete matter) ──")
    tail = docket.split("-")[-1]
    others = "|".join(t.split("-")[-1] for m, t in DOCKETS.items() if m != matter and t != docket)
    j = "documents d JOIN document_matter_links l ON l.doc_id=d.id WHERE l.matter_code=%r" % matter
    n = _one(f"SELECT count(*) FROM {j}")
    complaint = _one(f"SELECT count(*) FROM {j} AND original_filename ~* 'complaint' AND coalesce(original_filename,'') !~* 'sample|template'")
    blanks = _rows(f"SELECT d.id||' '||left(coalesce(original_filename,''),48) FROM {j} AND (original_filename ~* 'sample|template' OR extracted_text ~* 'voluntarily executes this|, of legal age, with address at _')")
    hollow = _rows(f"SELECT d.id||' '||left(coalesce(original_filename,''),48) FROM {j} AND coalesce(extracted_text,'')='' AND file_path IS NOT NULL")
    contam = _rows(f"SELECT d.id||' '||left(coalesce(original_filename,''),48) FROM {j} AND coalesce(original_filename,'')||coalesce(left(extracted_text,2500),'') ~* '({others})' AND coalesce(original_filename,'')||coalesce(left(extracted_text,2500),'') !~* '{tail}'") if others else []
    print(f"   docs linked: {n} · complaint present: {'YES' if complaint != '0' else '** MISSING **'}")
    for label, rs in [("blank/template (exclude)", blanks), ("hollow scan (needs OCR)", hollow), ("cross-matter contamination", contam)]:
        if rs:
            print(f"   ! {label}: " + "; ".join(r.strip() for r in rs))
    return {"complaint": complaint != "0", "blanks": blanks, "hollow": hollow, "contam": contam}


# ── 2 POSITION (the accuracy core) ──────────────────────────────────────────────
def stage_position(matter, docket, pb):
    print("\n── 2 · POSITION (forum-fit · posture · opponent · element→proof) ──")
    ids = cs._docket_doc_ids(docket) if docket else []
    j = "documents d JOIN document_matter_links l ON l.doc_id=d.id WHERE l.matter_code=%r" % matter
    posture = _one(f"SELECT left(coalesce(doc_date::text,'?'),10)||' — '||left(coalesce(original_filename,''),64) "
                   f"FROM {j} AND original_filename ~* 'NSR|notice of submission|resolution|order|disposition' ORDER BY doc_date DESC NULLS LAST LIMIT 1")
    complaint = _one(f"SELECT regexp_replace(left(extracted_text,1800),'[[:space:]]+',' ','g') FROM {j} AND original_filename ~* 'complaint' AND coalesce(original_filename,'') !~* 'sample|template' ORDER BY doc_date LIMIT 1")
    opp = _rows(f"SELECT 'doc:'||d.id||' '||left(coalesce(original_filename,''),46)||' :: '||regexp_replace(left(coalesce(extracted_text,''),900),'[[:space:]]+',' ','g')"
                f"FROM {j} AND (original_filename ~* 'counter-affidavit|joint response|reply to' OR extracted_text ~* 'Joint Response|Counter-Affidavit|respectfully den') ORDER BY doc_date LIMIT 3", n=3)
    law = cs._pinpoint_law(pb["law"], pb["law_kw"]) or "(law text not embedded)"
    elements = []
    for label, proofdesc, probe in pb["elements"]:
        ps = cs.rag.retrieve(f"{label} {proofdesc} {docket}", k=3, ids=ids or None)
        cites = " || ".join(f"[doc:{p.get('doc_id')}] {(p.get('text') or '')[:240]}" for p in ps)
        authority = (cs._pinpoint_law(*probe) if probe else "") or ""   # the governing rule from legal_chunks
        elements.append((label, proofdesc, cites or "(no passage retrieved → likely GAP)", authority))
    facts = _rows("SELECT '- '||regexp_replace(statement,'[[:space:]]+',' ','g')||'  [doc:'||coalesce(source_id,'?')||']' "
                  "FROM matter_facts WHERE matter_code=%r AND provenance_level='verified' ORDER BY id LIMIT 30" % matter, n=30)
    print(f"   posture: {posture or '(none found)'}")
    print(f"   opponent filings: {len(opp)} · verified facts: {len(facts)} · elements scored: {len(elements)}")
    return {"posture": posture, "complaint": complaint, "opp": opp, "law": law, "elements": elements, "facts": facts}


# ── 3 SYNTHESIS (decision-first, grounded) ──────────────────────────────────────
def stage_synthesis(matter, docket, pb, pos, integ, use_frontier):
    print("\n── 3 · SYNTHESIS (decision-first) ──")
    el = "\n".join(f"- ELEMENT: {lab}\n  GOVERNING AUTHORITY (quote the rule/clock): {(auth or '(not embedded)')[:480]}\n"
                   f"  proof needed: {pd}\n  retrieved proof: {ct}" for lab, pd, ct, auth in pos["elements"])
    facts = "\n".join(pos["facts"]) or "(no verified facts on file)"
    opp = "\n".join("- " + o.strip() for o in pos["opp"]) or "(no respondent filing in record)"
    integ_note = ("Cross-matter docs present (do NOT cite as this matter's proof): "
                  + "; ".join(r.strip() for r in integ["contam"])) if integ["contam"] else "clean"
    prompt = f"""You are preparing a DECISION-FIRST case dossier for counsel on matter {matter} (docket {docket}),
before {pb['forum']}. The forum CAN grant: {pb['grants']}. The forum CANNOT grant: {pb['cannot_grant']};
any such claims MUST be RESERVED to {pb['reserve_to']}.

Write GitHub-markdown with EXACTLY these sections. Be grounded ONLY in the EVIDENCE; cite documents as
[doc:ID] from the evidence; if an element has no proof, write **GAP**. Do not invent facts or doc ids.
Be honest about weakness — this is for the lawyer's eyes, not advocacy.

## Bottom line
Three sentences: what the matter is, its current posture, and the single most important call now.
## Status & clock
From POSTURE. State what is pending and any deadline.
## Position — does our claim fit this forum?
Assess claim↔forum↔remedy fit. If our pleaded claims include matters the forum CANNOT grant, say so plainly
and state they must be reserved. Give an explicit verdict: are we positioned to WIN, CONTESTED, or LOSE — and why.
## The theory — element by element
For each ELEMENT, the RULE must be a VERBATIM quote from that element's GOVERNING AUTHORITY text shown below —
copy its key standard/figure exactly (for §21(e), quote the Citizen's Charter clock, i.e. the working-day
number). NEVER restate the element label as the rule. Then the fact, then the proving exhibit [doc:ID]; or
**GAP** if unproven. PREFER the VERIFIED FACT LEDGER below for proof citations (each fact is tied to its source doc);
use the retrieved passages only to corroborate.
## The opponent's position
Their filed defense (from OPPONENT) and our rebuttal grounded in the record. If OPPONENT is non-empty, you
MUST engage it — do not write "no respondent filing."
## Gaps & what to obtain
## Recommended actions
Concrete next step(s) with an owner and a real deadline. The action MUST fit the POSTURE: if the matter is
already submitted for resolution, the record is closed — the move is a manifestation/motion to the handling
lawyer (narrowing the claim and reserving out-of-forum issues), NOT requesting a response.

EVIDENCE
========
APPLICABLE LAW: {pos['law'][:1200]}
OUR COMPLAINT (claims pleaded): {pos['complaint'][:1600]}
POSTURE (latest disposition): {pos['posture']}
VERIFIED FACT LEDGER (each already cited to its source doc — PREFER as element proof):
{facts}
OPPONENT (respondent filings, verbatim excerpts):
{opp}
ELEMENT → retrieved proof passages:
{el}
INTEGRITY: {integ_note}
"""
    body = (cs._frontier(prompt) if use_frontier else cs._ollama(prompt)) or "(synthesis failed)"
    title = (f"# Case Dossier — {matter}  ·  docket {docket}\n\n"
             f"*Prepared by LandTek for counsel — decision-first; not a pleading. Generated by the one-request "
             f"pipeline (completeness → integrity → position → synthesis → gate → bound exhibits). "
             f"Verify each cited document before relying.*\n")
    foot = (f"\n\n---\n*Primary documents are bound as exhibits after this brief, in order. "
            f"Matter {matter}; forum: {pb['forum']}.*\n")
    md = title + "\n" + body.strip() + foot
    out = os.path.join(OUTDIR, f"dossier_{matter}.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(out, "w").write(md)
    print(f"   wrote {out} ({len(md)} bytes)")
    return out


# ── 3b RED TEAM (adversarial critique — a separate, deliberately hostile pass) ──
def stage_redteam(md_path, matter, docket, pos, use_frontier):
    print("\n── 3b · RED TEAM (opposing critique) ──")
    body = open(md_path).read()
    opp = "\n".join("- " + o.strip() for o in pos["opp"]) or "(no respondent filing in record)"
    prompt = f"""You are OPPOSING COUNSEL and a skeptical handling lawyer reviewing the dossier below for matter
{matter} ({docket}). ATTACK the complainant's case and expose every weakness — be ruthless and concrete. This
is a PRE-MORTEM so our side fixes it before the tribunal does. Ground the critique in the dossier and the
respondents' filing; do NOT invent facts. Output GitHub-markdown, exactly this section:

## Weaknesses & the opposing case (red team)
- **Strongest arguments against us** — the 2–4 points the respondents / tribunal will press (jurisdiction,
  "we already acted", proper-referral, FOI exemption, non-receipt of the request, record already closed, etc.).
- **Where our proof is thin** — the weakest element; any citation that is procedural rather than probative;
  what we ASSERT but have not PROVEN.
- **Most likely path to dismissal** — the single cleanest way ARTA rules against us.
- **Shore-ups** — the concrete fix for each weakness (a document to obtain, a count to drop, an argument to add).

THE DOSSIER (our case):
{body[:4200]}

RESPONDENTS' ACTUAL FILING (their defense):
{opp[:1500]}
"""
    crit = (cs._frontier(prompt) if use_frontier else cs._ollama(prompt)) or ""
    if not crit.strip():
        print("   (red-team pass produced nothing)"); return
    marker = "\n\n---\n*Primary documents"
    body = (body.replace(marker, "\n\n" + crit.strip() + marker, 1) if marker in body
            else body + "\n\n" + crit.strip() + "\n")
    open(md_path, "w").write(body)
    print("   appended red-team critique")


# ── 4 GATE · 5 DELIVER ──────────────────────────────────────────────────────────
def stage_gate(md_path, matter):
    print("\n── 4 · DILIGENCE GATE ──")
    if os.path.exists("scripts/dossier_verify.py"):
        r = subprocess.run([sys.executable, "scripts/dossier_verify.py", md_path, "--matter", matter],
                           capture_output=True, text=True)
        print("   " + ((r.stdout.strip().splitlines() or ["(no output)"])[-1]))


def stage_deliver(matter, md_path, send, exclude_ids=()):
    print("\n── 5 · DELIVER (bound PDF) ──")
    remote_md = f"/tmp/dossier_{matter}.md"
    subprocess.run(["scp", "-q", md_path, f"{VPS}:{remote_md}"], timeout=120)
    exc = (" --exclude " + ",".join(str(i) for i in exclude_ids)) if exclude_ids else ""
    cmd = ("cd /root/landtek && set -a; . .env 2>/dev/null; set +a; "
           f"python3 scripts/case_bundle.py {matter} --brief {remote_md}{exc}" + (" --send" if send else ""))
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=60", VPS, cmd], capture_output=True, text=True, timeout=900)
    for l in r.stdout.splitlines():
        if "[bundle]" in l or "[send]" in l:
            print("   " + l.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("matter")
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--no-recover", action="store_true")
    ap.add_argument("--frontier", action="store_true")
    a = ap.parse_args()
    pb = _pb(a.matter)
    if not pb:
        sys.exit(f"no playbook for {a.matter} (add one to PLAYBOOKS)")
    docket = DOCKETS.get(a.matter, "")
    print(f"━━━ dossier_pipeline {a.matter} ({docket or 'no docket'}) ━━━")
    if not a.no_recover:
        stage_completeness(a.matter, apply=True)
    integ = stage_integrity(a.matter, docket)
    pos = stage_position(a.matter, docket, pb)
    md = stage_synthesis(a.matter, docket, pb, pos, integ, a.frontier)
    stage_redteam(md, a.matter, docket, pos, a.frontier)
    stage_gate(md, a.matter)
    contam_ids = [r.split()[0] for r in integ["contam"] if r.split() and r.split()[0].isdigit()]
    stage_deliver(a.matter, md, a.send, exclude_ids=contam_ids)
    print("\n✓ done")


if __name__ == "__main__":
    main()
