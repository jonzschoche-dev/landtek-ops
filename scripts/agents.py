#!/usr/bin/env python3
"""agents.py — the LandTek resident-agent registry + health supervisor.

One canonical catalog of every autonomous ("resident") agent in the stack: its role, fuel tier,
cadence, systemd unit, and status. This is the production-readiness backbone for shipping a fully
ready Leo LandTek — it makes the fleet explicit, shows exactly what's still missing, and `--health`
checks each live agent is actually running (timer enabled + scheduled, last run not failed) so the
system can't silently stall. New resident agents get registered here as we build them.

Fuel tiers:  det = $0 deterministic (no LLM)  ·  local = in-house Ollama (sovereign, unlimited, $0)
             api = external API (quota/credits)  ·  human = needs operator adjudication

  python3 scripts/agents.py --list      # the roster
  python3 scripts/agents.py --health    # are the live ones alive? (run on the VPS)
"""
import argparse
import subprocess

# key, role, fuel, cadence, systemd timer unit (or ''), status, notes
AGENTS = [
    # ── LIVE — knowledge freshness ─────────────────────────────────────────────
    ("verify_loop",          "scout — find/rank/measure verification candidates", "det",
     "daily 03:00", "landtek-verify.timer", "live", "also regenerates case dossiers"),
    ("verify_worker",        "reader — docs → verified cited facts (local-first)", "local",
     "every 15 min", "landtek-verify-worker.timer", "live", "Ollama@MacStudio; Gemini fallback"),
    ("case_dossier",         "librarian — lay out each matter's corpus + evidence", "det",
     "daily (in verify svc)", "", "live", "case_dossiers/<MATTER>.md + INDEX.md"),
    ("cross_client_sentinel","separator — prevent cross-client entity conflation", "det",
     "daily", "landtek-cross-client.timer", "live", "MWK / Paracale / NIBDC isolation"),
    # ── LIVE — proactivity ─────────────────────────────────────────────────────
    ("deadlines",            "watchdog — never miss a date", "det",
     "daily (in digest)", "", "live", "forward-marker date engine"),
    ("build_digest",         "reporter — daily operator digest", "det",
     "daily 01:00", "landtek-digest.timer", "live", "Telegram-friendly"),
    ("supervisor",           "health — verify the fleet is alive (this script)", "det",
     "daily", "", "live", "agents.py --health"),
    # ── LIVE — gap-fillers (complete the corpus) ───────────────────────────────
    ("corpus_steward",       "steward — keep every matter's case file complete, current & reachable", "det",
     "every 6h", "landtek-corpus-steward.timer", "live", "case_corpus_sweep.sh: live-source recovery+OCR -> dedup/separation guard -> per-matter snapshots -> facts/strategy -> cross-matter awareness scorecard"),
    ("doc_discovery",        "find/link doc-less matters' papers from the unlinked pool", "det",
     "daily (in verify svc)", "", "live", "conservative; proposes + auto-links strong docket signals"),
    ("contradiction",        "cross-check verified facts for conflicts per matter", "det",
     "daily (in verify svc)", "", "live", "caught the Sept-2016-vs-2019 sale-date conflict"),
    ("ocr_triage",           "re-OCR the OCR-garbage docs (local Tesseract)", "det",
     "daily (in verify svc)", "", "live", "side-table, no overwrite; Drive-fetch for 66 remaining = next increment"),
    ("reconciler",           "adjudicate proposed_facts → verified/reject", "det+human",
     "on demand", "", "live", "human-in-the-loop; gate still checks on accept"),
    # ── LIVE — output / reasoning (in-house Ollama tier) ───────────────────────
    ("analyst",              "case theory / strategy from the verified corpus", "local",
     "on demand", "", "live", "derived reasoning, labeled; never a verified fact"),
    ("brief_drafter",        "draft work-product grounded in verified facts", "local",
     "on demand", "", "live", "[PENDING VERIFICATION] for gaps; draft for counsel"),
    # ── LIVE — monitoring & execution (the filing cycle; system never files itself) ─────
    ("filing_monitor",       "Discovery — watch email for incoming filings → alert operator", "det",
     "every 6h", "landtek-filing-monitor.timer", "live", "filing_alerts + tg_send (S14); 32 baselined"),
    ("execution_tracker",    "track filings/actions to completion (planned→filed→confirmed)", "det",
     "on demand", "", "live", "case_actions ledger + stale-watch; NEVER files with the court"),
    # ── FORUM DESKS — one engine (agency_agent.py), four playbooks ──────────────
    ("agency:ARTA",          "forum desk — RA 11032 clocks/procedure/escalation", "det",
     "on demand", "", "live", "9 matters; grounded (docs 384/967); agency_agent.py --desk ARTA"),
    ("agency:CIVIL",         "forum desk — Rules of Court / Summary Procedure", "det",
     "on demand", "", "live", "RTC/MTC cluster; grounded (docs 452/1088)"),
    ("agency:CSC",           "forum desk — CSC administrative-case rules", "det",
     "on demand", "", "ready", "no matters yet; periods NEEDS-COUNSEL-VERIFICATION"),
    ("agency:OMBUDSMAN",     "forum desk — R.A. 6770 / AO 07", "det",
     "on demand", "", "ready", "no matters yet; periods NEEDS-COUNSEL-VERIFICATION"),
    ("ombudsman_hunter",     "OFFENSIVE graft/misconduct lead engine — ranks public officers by exposure (RA 3019/6713/RPC), ripeness-gates, drafts; NEVER files", "det",
     "on demand", "", "live", "ombudsman_hunter.py --scan/--board/--candidate/--playbook; leads only (inference-grade), filing human-gated; feeds case_synthesizer + strategy_engine Ombudsman lever"),
    # ── LIVE — case builder (the operator interface) ───────────────────────────
    ("forum_router",         "wire each grievance → candidate oversight forums (case_forums)", "det",
     "on demand", "", "live", "feeds /ops/cases; curated from agency_mandates"),
    ("case_builder_ui",      "cockpit /ops/cases — live case cards (forums + corpus support)", "det",
     "live (web)", "", "live", "ops_dashboard.py; grows fluidly with the corpus"),
    ("legal_authority",      "forum law library — verbatim statutes/circulars in a local-embed RAG", "local",
     "on demand", "", "live", "5 forums seeded; nomic-embed (Ollama $0); retrieve(forum,q)"),
    ("case_files",           "find all docs of a case + links to the originals", "det",
     "on demand", "", "live", "case_files.py MATTER [--read-only]"),
    ("case_pdf",             "organized case-brief PDF → Telegram (relevance-tiered + annexes)", "det",
     "on demand", "", "live", "case_pdf.py MATTER --send"),
    ("case_memo",            "corpus-grade Action Memo → Telegram (separation, provenance-tagged, src-availability)", "local",
     "on demand", "", "live", "deterministic scaffolding + fenced derived block; case_memo.py MATTER --send"),
    ("render_memo",          "render a markdown doc → PROFESSIONAL PDF (title, page numbers, footer, real tables, links)", "det",
     "on demand", "", "live", "frontier-authored briefs/dossiers; numbered-canvas footer + confidential; render_memo.py memo.md 'cap' --send"),
    ("proof",                "corrective QA pass — lint final output for professional-form defects (gate before delivery)", "det+local",
     "on demand", "", "live", "markdown-leak/placeholder/machine-token/empty-section/date checks + optional --llm editorial; proof.py doc.md --pdf doc.pdf"),
    ("finalize_docx",        "FINALIZER — grounded markdown → professional editable Word doc (separates content from presentation)", "det",
     "on demand", "", "live", "title page + TOC + Word heading styles + styled tables + footer (CONFIDENTIAL+Page X/Y); python-docx; finalize_docx.py in.md out.docx"),
    ("case_synthesizer",     "RAG-fed element-driven legal synthesis — LOCAL-FIRST (offline); frontier optional sharpener", "local",
     "on demand", "", "live", "playbook→coverage-gate→per-element rag_local+law retrieval→Ollama 14B synth→finalize; case_synthesizer.py --playbook P --out O [--frontier]"),
    ("case_dossier_pdf",     "scannable corpus dossier → Telegram (timeline + docs-by-category + embedded content)", "det",
     "on demand", "", "live", "case-bundle front matter; embeds each doc's grounded content inline; case_dossier_pdf.py MATTER --send"),
    ("pdf_pages",            "carve specific pages out of a bundle PDF (a focused exhibit, not the whole thing)", "det",
     "on demand", "", "live", "by range or by finding text (OCR-backed for scans); pdf_pages.py DOC_ID 12-14|--find TEXT|--toc [--compress] [--send]"),
    ("pdf_compress",         "shrink a PDF for delivery (downsample+JPEG scans; keeps text pages intact)", "det",
     "on demand", "", "live", "Ghostscript-free PyMuPDF; 16.6MB→9.1MB; pdf_compress.py in.pdf [out] [--dpi 150] [--quality 55]"),
    ("case_bundle",          "filing-grade CASE BUNDLE: clean front matter + the actual supporting docs bound in as exhibits", "det",
     "on demand", "", "live", "cover + numbered statement-of-facts (exhibit cross-refs) + index + merged exhibit pages (compressed); case_bundle.py MATTER [--send]"),
    ("case_package",         "counsel-ready PACKAGE for external delivery: brief + CORE docs bound + the rest as OPEN public links", "det",
     "on demand", "", "live", "leo.hayuma.org/files/c links (public, no login); case_package.py MATTER --brief b.md --core 708,709,... [--send]"),
    ("legal_agent",          "discerning final-output reasoner — multi-step harness on 14B", "local",
     "on demand", "", "live", "element-map → draft → self-critique; powers case_memo's derived block"),
    ("matter_readiness",     "TRUTH DATA-LAYER pre-flight — is a matter ready for a true memo?", "det",
     "on demand", "", "live", "operative-pleading/orphan/conflation/grounding check + fix-list; run BEFORE case_memo"),
    ("matter_fix",           "one-command fast path: readiness → safe auto-fix → re-check → (memo)", "local",
     "on demand", "", "live", "links docket-orphans + targeted source-read; --generate self-gates via case_memo"),
    ("data_audit",           "audit the data layer — classify every doc↔matter link KEEP/DROP", "det",
     "on demand", "", "live", "image/foreign/no-signal breakdown; measures the verified-relevant fraction"),
    ("relevance_triage",     "fast keep/drop relevance call over ambiguous linked docs", "local",
     "on demand", "", "live", "one light LLM call/doc; over-drops on umbrella matters — pending multi-signal arch"),
    ("data_remediate",       "operator-run: unlink high-confidence noise (reviewable+reversible)", "human",
     "on demand", "", "live", "--plan/--unlink/--relink; image-noise + OFF-PROFILE only; autonomous DELETE blocked"),
    ("drive_offload",        "operator-run: Drive-canonical PDF policy (upload→record→drop local)", "human",
     "on demand", "", "live", "--plan/--go [--keep-local]; only offloads docs whose TEXT is already local (offline-safe)"),
    ("offline_audit",        "can the stack REASON unplugged? local-core check + external-touchpoint scan", "det",
     "on demand", "", "live", "reasoning core (PG+Ollama+embedded law+text) is offline-capable; edges resume online"),
    ("relevance",            "classify surrounding corpus by relevance to a focal matter", "det",
     "on demand", "", "live", "CORE/RELATED/CONTEXTUAL/OFF-PROFILE + connection; docket+title+party fingerprint"),
    ("chronology",           "date-ordered evidence & submissions (the case timeline)", "det",
     "on demand", "", "live", "events from verified facts + filings; leads the case_pdf brief"),
    # ── LIVE — no-hallucination pipeline + law-corpus (2026-06) ─────────────────
    ("dossier_verify",       "DILIGENCE gate — citation fidelity / source integrity / client-separation / name (paralegal-grade)", "det",
     "on demand", "", "live", "structured issues; verify_text() reusable; dossier_verify.py doc.md --matter PREFIX"),
    ("dossier_fix",          "SELF-HEAL loop — flag→fix→re-verify until clean; escalates the un-fixable", "det",
     "on demand", "", "live", "acronym/name/citation/draft-source/cross-matter fixes; dossier_fix.py doc.md --matter"),
    ("execution_classify",   "execution-status GATE — draft vs executed/received (no draft posing as evidence)", "det",
     "on demand", "", "live", "regex_classifier_v2: received-stamp + tribunal-order + complainant-letter guard; --matter scope"),
    ("correspondence_ledger","delivery-aware, quote-verified correspondence ledger — delivery is its own fact, gaps are findings", "det",
     "on demand", "", "live", "correspondence_events table; --gaps/--render; every claim a verbatim ✓ source quote"),
    ("correspondence_extract","delivery-gap candidate feed — mine non/late-delivery language (verbatim), curate into the ledger", "det",
     "on demand", "", "live", "high-recall + META filter + per-doc cap; correspondence_extract.py --matter"),
    ("cross_matter",         "cross-matter evidence map — a verified fact → the other matters it strengthens (quote-verified)", "det",
     "on demand", "", "live", "cross_matter_links table; --matter X surfaces out-of-matter ammunition"),
    ("law_coverage",         "law-library coverage + completeness monitor — needed provisions + full/partial/missing inventory", "det",
     "on demand", "", "live", "law_coverage.py [--corpus]; 15 major acts full; flags gaps to embed"),
    ("corpus_ingest",        "bulk full-text law ingester — fetch lawphil → strip → embed (offline self-sufficiency)", "det",
     "on demand", "", "live", "skips stubs; ingested full LGC/Constitution/Admin Code; one-line per act"),
    # ── PLANNED ────────────────────────────────────────────────────────────────
    # ── THE FACE ───────────────────────────────────────────────────────────────
    ("leo",                  "Telegram interface — answers grounded in the corpus", "api",
     "realtime", "", "needs-wiring", "n8n AI-Agent; wire discernment protocol + answer gate"),
    ("channel:viber",        "Viber Bot channel for Leo (inbound webhook + outbound send)", "api",
     "realtime", "", "needs-creds", "/api/channel/viber mirrors WhatsApp; needs VIBER_AUTH_TOKEN + public HTTPS URL (viber_set_webhook.py)"),
]


def _sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def list_roster():
    by = {}
    for a in AGENTS:
        by.setdefault(a[5], []).append(a)
    order = ["live", "planned", "needs-wiring"]
    print("=" * 78)
    print("LANDTEK RESIDENT-AGENT ROSTER")
    print("=" * 78)
    for st in order + [k for k in by if k not in order]:
        if st not in by:
            continue
        print(f"\n[{st.upper()}]  ({len(by[st])})")
        for key, role, fuel, cad, unit, status, notes in by[st]:
            print(f"  {key:22} {fuel:10} {cad:22} {role}")
    live = sum(1 for a in AGENTS if a[5] == "live")
    planned = sum(1 for a in AGENTS if a[5] == "planned")
    print(f"\n{live} live · {planned} planned · {len(AGENTS)} total. "
          f"Ship-readiness = build the planned gap-fillers + output agents, then wire Leo.")
    print("  (this is the on-demand TOOL catalog — for the systemd/cron automation layer run "
          "`agents.py --wired`)")


def health():
    print("=" * 78)
    print("FLEET HEALTH (live agents with a systemd timer)")
    print("=" * 78)
    ok = True
    for key, role, fuel, cad, unit, status, notes in AGENTS:
        if status != "live" or not unit:
            continue
        enabled = _sh(f"systemctl is-enabled {unit} 2>/dev/null") or "?"
        active = _sh(f"systemctl is-active {unit} 2>/dev/null") or "?"
        svc = unit.replace(".timer", ".service")
        result = _sh(f"systemctl show {svc} -p Result --value 2>/dev/null") or "-"
        nxt = _sh(f"systemctl list-timers {unit} --no-pager 2>/dev/null | grep -i {unit.split('.')[0]} | awk '{{print $1, $2}}'")
        good = enabled == "enabled" and active == "active" and result in ("success", "-")
        ok = ok and good
        flag = "✓" if good else "✗"
        print(f"  {flag} {key:22} {unit:30} enabled={enabled} active={active} last={result} next={nxt or '?'}")
    print("\n" + ("✓ fleet healthy" if ok else "✗ one or more agents need attention"))


def wired_automation():
    """The OTHER roster. The AGENTS list above is the on-demand TOOL catalog; it does NOT list the
    scripts wired into systemd timers + cron — a separate ~50-script automation layer. This reads the
    LIVE host state so 'what actually runs, how often' is visible in one place and dormancy stays
    catchable (the bloat audit found these two rosters had drifted apart). Run on the VPS host."""
    import re
    print("=" * 78)
    print("WIRED AUTOMATION  (systemd timers + cron — the running layer, read live)")
    print("=" * 78)
    enabled = _sh("systemctl list-unit-files --state=enabled --no-legend 2>/dev/null")
    en_set = {l.split()[0] for l in enabled.splitlines()
              if (".timer" in l or ".service" in l) and re.search(r"landtek|leo|cowork", l)}
    raw = _sh("systemctl list-timers --all --no-legend 2>/dev/null")
    timers = sorted({next((p for p in l.split() if p.endswith(".timer")), "")
                     for l in raw.splitlines() if re.search(r"landtek|leo", l)} - {""})
    print(f"\n[systemd timers]  ({len(timers)})")
    for unit in timers:
        print(f"  {unit:36} {'enabled' if unit in en_set else 'DISABLED'}")
    svcs = sorted(u for u in en_set if u.endswith(".service"))
    print(f"\n[systemd services enabled]  ({len(svcs)})")
    for s in svcs:
        print(f"  {s}")
    cron = _sh("crontab -l 2>/dev/null")
    jobs = [l for l in cron.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    print(f"\n[cron]  ({len(jobs)})")
    for l in jobs:
        flds = l.split()
        sched = " ".join(flds[:5]) if len(flds) >= 5 else "?"
        m = re.search(r"([\w./-]+\.py)(\s+[\w-]+)?", l)
        print(f"  {sched:16} {(m.group(0).strip() if m else l[-44:])}")
    if not timers and not jobs:
        print("\n  (no systemd/cron visible — run this on the VPS host)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--wired", action="store_true")
    a = ap.parse_args()
    if a.health:
        health()
    elif a.wired:
        wired_automation()
    else:
        list_roster()


if __name__ == "__main__":
    main()
