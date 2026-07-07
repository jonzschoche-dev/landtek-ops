#!/usr/bin/env python3
"""ontology_check.py — read-only ontology linter (the loop-closer for ONTOLOGY.md).

The ontology_validator triggers (deploy_691) catch violations at WRITE time. This
script is the periodic WHOLE-CORPUS audit — it re-grounds ONTOLOGY.md against the live
schema and surfaces drift the write-gate can't (pre-existing rows, new unregistered
tables, provenance vocab creep, V4 client contamination). Read-only: prints a report,
mutates nothing. Runs on the VPS (needs the container-internal DSN).

Usage:
  python3 scripts/ontology_check.py            # full report
  python3 scripts/ontology_check.py --brief    # phone-friendly one-screen summary
  python3 scripts/ontology_check.py --coverage # every populated domain table must be NAMED in ONTOLOGY.md
  python3 scripts/ontology_check.py --structure # STRUCTURE lint (no DB): unique section numbers + heading depth
  python3 scripts/ontology_check.py --invariants # every §4 invariant's named enforcement artifact must EXIST
  python3 scripts/ontology_check.py --render-audit # A32: projected client output must carry NO internal token
  python3 scripts/ontology_check.py --sentinel # daily timer mode: silent when clean; writes a
                                               # holes_findings row on NEW V3/V4 contamination,
                                               # a coverage regression, OR a broken §4 invariant
                                               # enforcement ref (--invariants). Standing amber
                                               # backlog (drift, vocab creep, 🟡 invariants) never alerts.

Exit code: 0 = clean, 1 = drift/contamination found (usable as a health gate).
"""
from __future__ import annotations
import os
import re
import sys
import json
try:
    import psycopg2                       # DB paths need it; --structure is a pure file lint and must
except ImportError:                       # run anywhere (e.g. the Mac during migration authoring)
    psycopg2 = None

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Canonical provenance vocabulary (grounded 2026-07-05 — see ONTOLOGY.md A1).
PROVENANCE_VOCAB = {
    "verified", "operator", "inferred_strong", "inferred_corroborated", "inferred_weak",
}

# Drift tables — nothing should be writing these (ONTOLOGY.md sec3).
DRIFT_TABLES = ["chain_of_title", "cases", "finance_transactions", "fact_edges"]

# Fact-bearing tables that carry provenance_level (for vocab audit).
PROVENANCE_TABLES = [
    "matter_facts", "entities", "titles", "title_chain", "title_transfers",
    "doc_entities", "transferees", "legal_authorities", "knowledge_graph_triples",
    "subdivision_plans", "transactions", "parcels",
]

# Geometry ACCURACY is a SEPARATE controlled vocabulary from provenance (ONTOLOGY.md §2.4,
# GeometrySource). A map_parcels accuracy_tier is NOT a provenance_level — kept distinct on
# purpose so the two vocabularies never bleed. rough→survey→ortho is the fidelity ladder.
ACCURACY_VOCAB = {"rough", "survey", "ortho"}

# Tables named in ONTOLOGY.md sec2 (canonical + staging). New public tables NOT in this
# set are candidate drift → flagged for registry review. n8n plumbing is excluded.
REGISTERED = set(DRIFT_TABLES + PROVENANCE_TABLES + [
    "documents", "rag_local", "extraction_runs", "extraction_chunks", "extraction_contract",
    "field_consensus", "gmail_messages", "email_documents", "duplicate_groups",
    "duplicate_group_members", "actor_lifespan", "clients", "matters", "proposed_facts",
    "claims", "claim_truth_verdicts", "verified_claims", "cross_matter_links", "keystones",
    "matter_state", "matter_plays", "matter_authorities", "doc_requirements_law",
    "ombudsman_candidates", "arta_cases", "case_threads", "channels", "channel_messages",
    "outbound_messages", "outbound_blocks", "leo_interactions", "client_access_tokens",
    "file_access_tokens", "map_parcels", "parcels", "document_titles", "title_matter_links",
    "instruments_on_title", "transfer_doc_status", "document_matter_links",
    "ontology_validator_config",
])

# n8n plumbing prefixes/names to exclude from "unregistered" noise.
PLUMBING_PREFIX = (
    "workflow", "execution", "credentials", "shared_", "oauth", "chat_hub", "instance_ai",
    "installed_", "folder", "data_table", "annotation", "webhook", "tag_", "project",
    "insights", "test_case", "auth_provider", "secrets_provider", "dynamic_credential",
    "role", "scope", "user", "settings", "migrations", "variables", "event_destinations",
    "processed_data", "invalid_auth", "api_keys",
)


def is_plumbing(t: str) -> bool:
    return t in ("role", "scope", "role_scope", "user", "settings", "migrations",
                 "api_keys", "user_api_keys") or t.startswith(PLUMBING_PREFIX)


def _named_in(doc: str, t: str) -> bool:
    """True iff table name `t` appears as a WHOLE snake_case token in the doc (not as a substring of
    a longer name). Precise coverage check — `entities` must not count as covered by `doc_entities`."""
    return re.search(r'(?<![a-z0-9_])' + re.escape(t) + r'(?![a-z0-9_])', doc, re.I) is not None


def _doc_path():
    """The ONTOLOGY.md to lint: an explicit `*.md` arg (for a draft/alternate copy) or the repo file."""
    p = next((a for a in sys.argv if a.endswith(".md")), None)
    return p or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ONTOLOGY.md")


def coverage_gaps(cur):
    """Return (named_count, total, [(table, rows) gaps]) — populated domain tables NOT named in
    ONTOLOGY.md. Reusable by cmd_coverage AND the daily sentinel so completeness stays a live check."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(repo, "ONTOLOGY.md")) as f:
            doc = f.read()
    except Exception:
        return None, None, None
    cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE n_live_tup > 0 ORDER BY n_live_tup DESC;")
    rows = [(t, n) for (t, n) in cur.fetchall() if not is_plumbing(t)]
    missing = [(t, n) for (t, n) in rows if not _named_in(doc, t)]
    return len(rows) - len(missing), len(rows), missing


def cmd_coverage(cur) -> int:
    """AUTHORITATIVE coverage: every POPULATED domain table must be NAMED in ONTOLOGY.md.
    Reads the actual file — this is what makes 'nothing orphaned' a CHECK, not a hand-curated claim
    (deploy_718's §8 silently missed 100 tables). Exit 1 on any gap so it's a tracked invariant."""
    named, total, missing = coverage_gaps(cur)
    if missing is None:
        print("cannot read ONTOLOGY.md"); return 2
    print("=== ONTOLOGY.md coverage — populated domain tables named in the map ===")
    print(f"  named: {named}/{total}")
    if missing:
        print(f"  ORIENTATION GAPS — {len(missing)} populated domain tables NOT named (rows shown):")
        for t, n in missing:
            print(f"    [{n:>7}]  {t}")
        print("  → orient each in ONTOLOGY.md (§2 if gated-core evidence; §8 with a state otherwise).")
    else:
        print("  ✓ every populated domain table is named — nothing orphaned (VERIFIED, not claimed).")
    return 1 if missing else 0


# A "specific artifact" reference in §4 enforcement prose — something that MUST exist as a real
# trigger / function / view / test file / code def. (Conceptual names like `ontology_validator`,
# `_safe views`, `matter_facts` are NOT required to resolve — they describe, they don't name an artifact.)
ARTIFACT_STRONG = re.compile(r'(\.py(\b|::)|\(\)|^ontvv_|^trg_|^enforce_|^test_|^v_[a-z]|^truth_tests/)')


def invariant_gaps(cur):
    """Parse ONTOLOGY §4 and resolve each invariant's named enforcement artifact against the live DB +
    repo code. Returns (oks, conceptual, amber, fails) — reused by cmd_invariants (prints) AND the daily
    sentinel (writes a finding on `fails`). `fails` = 🟢 invariants naming an artifact that doesn't exist.
    Returns None on unreadable doc."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(_doc_path()) as f:
            doc = f.read()
    except Exception:
        return None
    # Ground-truth artifact universe: live DB triggers/functions/views + code defs + test/script files.
    cur.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    known = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT proname FROM pg_proc")
    known |= {r[0] for r in cur.fetchall()}
    cur.execute("SELECT viewname FROM pg_views WHERE schemaname = 'public'")
    known |= {r[0] for r in cur.fetchall()}
    skip = {".git", "archive", "node_modules", "__pycache__", "staging", "snapshots", "drafts"}
    for root, dirs, fns in os.walk(repo):          # walk ALL repo code — enforcement fns live in
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]  # scripts/holes/leo_tools/…
        for fn in fns:
            if fn.endswith(".py"):
                try:
                    for line in open(os.path.join(root, fn), encoding="utf-8", errors="ignore"):
                        m = re.match(r'\s*(?:def|class)\s+(\w+)', line)
                        if m:
                            known.add(m.group(1))
                except Exception:
                    pass

    def resolves(tok):
        t = tok.split("::")[0].split("(")[0].strip().strip("`")
        if not t:
            return False
        if t.endswith(".py") or "/" in t:                       # a test/script file path (+ maybe a CLI flag)
            return os.path.exists(os.path.join(repo, t.split("::")[0].split()[0]))
        if t in known:
            return True
        return any(os.path.exists(os.path.join(repo, d, t + ".py")) for d in ("scripts", "holes", "truth_tests"))

    fails, oks, conceptual, amber = [], [], [], []
    for line in doc.splitlines():
        if not re.match(r'^\|\s*A\d+\s*\|', line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        aid, enf = cells[0], cells[-1]
        # green iff the LEADING state marker is 🟢 — not any 🟢 mentioned in prose (e.g. "graduation to 🟢")
        green = next((c for c in enf if c in "🟢🟡🔴○⛔"), None) == "🟢"
        strong = [t for t in re.findall(r'`([^`]+)`', enf) if ARTIFACT_STRONG.search(t)]
        missing = [t for t in strong if not resolves(t)]
        verified = [t for t in strong if resolves(t)]
        if missing and green:
            fails.append((aid, missing, enf[:70]))
        elif verified:
            oks.append((aid, verified))
        elif green:
            conceptual.append(aid)                              # 🟢 but enforcement is schema/prose — unverifiable by name
        else:
            amber.append(aid)                                   # 🟡/flagged/shadow — expected gap, not a failure
    return oks, conceptual, amber, fails


def cmd_invariants(cur) -> int:
    """INVARIANT INTEGRATION check — the governance↔ontology loop-closer. Parses every A# row in
    ONTOLOGY.md §4 and verifies that each SPECIFIC named enforcement artifact (a trigger, function,
    view, `truth_tests/*.py`, or code def) actually EXISTS. A 🟢 invariant that names an artifact which
    is missing is 'green that isn't true' → FAIL (exit 1). Invariants enforced conceptually (schema
    NOT NULL, `_safe` views) or still amber (🟡/flagged/shadow) are reported, not failed. Makes
    'governance is integrated with the ontology' a CHECK, not a claim (sibling of --coverage/--structure)."""
    result = invariant_gaps(cur)
    if result is None:
        print("cannot read ONTOLOGY.md"); return 2
    oks, conceptual, amber, fails = result
    print("=== ONTOLOGY §4 invariant integration — every named enforcement artifact must exist ===")
    print(f"  🟢 backed by a VERIFIED artifact ({len(oks)}): " + ", ".join(a for a, _ in oks))
    print(f"  🟢 conceptual/schema enforcement, no specific artifact named ({len(conceptual)}): " + ", ".join(conceptual))
    print(f"  🟡 asserted/flagged/shadow — expected amber ({len(amber)}): " + ", ".join(amber))
    if fails:
        print(f"\n  ✗ {len(fails)} GREEN invariant(s) naming an artifact that does NOT exist (green-that-isn't-true):")
        for aid, miss, enf in fails:
            print(f"    - {aid}: missing {miss}  —  “{enf}…”")
        print("  → fix the artifact name in §4, or build/confirm the artifact. Governance is not fully integrated until 0.")
        return 1
    print("\n  ✓ every 🟢 invariant that names a specific artifact resolves to a real one — no broken enforcement refs.")
    return 0


# A32 RENDER-AUDIT — internal tokens that must NEVER survive projection onto a client surface
# (the §2.15 "MAY NOT" list). If one appears in PROJECTED output, the projection has a gap = a client leak.
FORBIDDEN_RENDER = {
    "matter_code":    re.compile(r"\b[A-Z]{2,4}-[A-Z0-9-]*\d{3,}"),  # MWK-CV26360 · MWK-001 · MWK-ARTA-0690 · PAR-CASE-88750
    "section_cite":   re.compile(r"§\s*\d|\bSec(?:tion)?\.?\s*\d+\b"),
    "ra_cite":        re.compile(r"\bR\.?\s*A\.?\s*\d{3,}\b"),
    "docket_ctn_sl":  re.compile(r"\bCTN\b|\bSL[\s-]*\d|\b\d{4}-\d{3,4}-\d{3,4}\b"),
    "ref_hash":       re.compile(r"\b(?:gmail|doc)\s*#\s*\d+|(?<!\w)#\d{3,}\b"),
    "inference_tag":  re.compile(r"\[(?:OCR|STRUCTURE|v|HUMAN[ _]?VERIFY|OPERATOR|\?)[^\]]*\]"),
    "raw_provenance": re.compile(r"\b(?:inferred_weak|inferred_strong|inferred_corroborated)\b"),
    "control_code":   re.compile(r"\b(?:SPA|NOR|OAC-?L|MOA|MOU|CTC)-\s*\d"),
}
# Government PERMIT/agreement identifiers a client legitimately owns and may see (like a TCT number) —
# they match the matter_code shape but are NOT internal codes. Excluded from the matter_code leak class.
PERMIT_SAFE = {"EXPA", "APSA", "MPSA", "FTAA", "SSMP", "SSMPA", "MPP", "EPEP", "CSAG", "EP", "IPO"}


def render_leaks(cur):
    """Run each leak-prone field's RAW values through its `client_ontology` projector and scan the PROJECTED
    output for a FORBIDDEN token. Returns (checked, leaks, unmapped) — reused by cmd_render_audit (prints)
    and the sentinel (writes). Total / fail-safe: a projector that RAISES on a value is itself counted a leak.
    Returns (None, None, None) if client_ontology can't be imported."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "leo_tools"))
        import client_ontology as co
    except Exception:
        return None, None, None
    fields = [
        ("current_stage",    "SELECT DISTINCT current_stage FROM matters WHERE current_stage IS NOT NULL",
         lambda v: co.client_stage(v)),
        ("forum",            "SELECT DISTINCT forum FROM matters WHERE forum IS NOT NULL",
         lambda v: co.client_forum(v)),
        ("provenance_level", "SELECT DISTINCT provenance_level FROM matter_facts WHERE provenance_level IS NOT NULL",
         lambda v: co.client_provenance(v)),
        ("matters.title",    "SELECT DISTINCT title FROM matters WHERE title IS NOT NULL",
         lambda v: co.friendly_title(v)),
        ("next_event",       "SELECT DISTINCT next_event FROM matters WHERE next_event IS NOT NULL",
         lambda v: co.client_next_step(None, v)),
        ("document_name",    "SELECT DISTINCT original_filename FROM documents WHERE original_filename IS NOT NULL LIMIT 400",
         lambda v: co.client_doc_name(v)),
    ]
    checked, leaks = 0, []
    for label, sql, project in fields:
        try:
            cur.execute(sql)
            raws = [r[0] for r in cur.fetchall()]
        except Exception:
            continue                                            # column/table absent on this schema — skip
        for raw in raws:
            checked += 1
            try:
                out = project(raw) or ""
            except Exception as e:                              # fail-safe: an unhandled value is a potential leak
                leaks.append((label, "projector_error", str(raw)[:60], f"<raised {type(e).__name__}>"))
                continue
            for cls, rx in FORBIDDEN_RENDER.items():
                m = rx.search(out)
                if not m:
                    continue
                if cls == "matter_code" and m.group(0).split("-")[0].upper() in PERMIT_SAFE:
                    continue   # a client-safe government permit/agreement ID (their own), not an internal code
                leaks.append((label, cls, str(raw)[:60], out[:90]))
                break
    try:
        unmapped = co.unmapped_report()
    except Exception:
        unmapped = []
    return checked, leaks, unmapped


def cmd_render_audit(cur) -> int:
    """A32 RENDER-AUDIT — prove the client projection layer prevents raw internal tokens from reaching a
    client surface. For every leak-prone field it projects each RAW value via `client_ontology` and scans the
    PROJECTED output for a forbidden token (matter code · § / R.A. cite · docket / CTN / SL · gmail#/doc# ·
    §4B inference tag · raw provenance enum · control code). A survivor = a projection gap = a client leak →
    exit 1. Read-only. Makes A32 mechanical instead of asserted (sibling of --invariants/--coverage)."""
    checked, leaks, unmapped = render_leaks(cur)
    if checked is None:
        print("cannot import leo_tools/client_ontology.py — A32 render-audit unavailable"); return 2
    print("=== A32 render-audit — projected client output must be free of internal tokens ===")
    print(f"  scanned {checked} raw value(s) across client-facing fields")
    if leaks:
        print(f"  ✗ {len(leaks)} projected value(s) STILL carry a forbidden token (projection gap → client leak):")
        for label, cls, raw, out in leaks[:40]:
            print(f"    [{label} · {cls}]  raw='{raw}'  →  projected='{out}'")
        print("  → extend the matching client_ontology projector so the token is stripped; re-run until 0.")
    else:
        print("  ✓ no forbidden token survives projection on any sampled field.")
    if unmapped:
        print(f"  ⚠ {len(unmapped)} value(s) hit the safe-generic FALLBACK (fail-safe A33, but flags vocab gaps to fill):")
        for kind, val in unmapped[:20]:
            print(f"    [{kind}] {str(val)[:60]}")
    return 1 if leaks else 0


def cmd_structure() -> int:
    """STRUCTURE lint of ONTOLOGY.md (no DB needed — pure file parse). Two mechanical rules:
      1. No DUPLICATE section number (the live doc has two `§2.6`).
      2. Markdown heading depth must equal the dotted-number depth + 1 — so `## 2.8` (an H2 carrying a
         two-part number) is a violation; it must be `### 2.8`. (`## 2`→H2, `### 2.1`→H3, `#### 2.6.1`→H4.)
    Catches exactly the debt that crept in during the v0.9→v0.13 authoring burst (dup §2.6; §2.8–2.14
    authored as H2 instead of H3). Read-only; exit 1 on any violation. This is the acceptance test for
    the ONTOLOGY.md v1.0 renumber (docs/ONTOLOGY_STRUCTURE.md §6.1) — NOT yet wired to the deploy gate,
    because the current doc intentionally still carries these violations until that migration runs."""
    try:
        with open(_doc_path()) as f:
            lines = f.read().splitlines()
    except Exception:
        print("cannot read ONTOLOGY.md"); return 2
    # A numbered heading: leading '#'s, space, a dotted number (2 · 2.6 · 8.19 · 2.6.1), then a boundary.
    heading = re.compile(r'^(#{1,6})\s+(\d+(?:\.\d+)*)\b')
    problems, seen = [], {}
    for ln, line in enumerate(lines, 1):
        m = heading.match(line)
        if not m:
            continue
        depth, num = len(m.group(1)), m.group(2)
        expected = num.count(".") + 2   # '2'→2(##) · '2.6'→3(###) · '8.19'→3 · '2.6.1'→4
        if num in seen:
            problems.append(f"DUPLICATE §{num}: line {seen[num]} and line {ln} — '{line.strip()[:48]}'")
        else:
            seen[num] = ln
        if depth != expected:
            problems.append(f"DEPTH §{num}: heading is H{depth}, expected H{expected} "
                            f"({num.count('.')} dot(s)) at line {ln} — '{line.strip()[:48]}'")
    print("=== ONTOLOGY.md structure lint (unique section numbers · heading depth == dots+1) ===")
    if problems:
        print(f"  ✗ {len(problems)} structural violation(s):")
        for p in problems:
            print(f"    - {p}")
        print("  → resolve in the ONTOLOGY.md v1.0 renumber (docs/ONTOLOGY_STRUCTURE.md §6.1). "
              "Rule: section numbers unique; heading depth == dotted-number depth + 1.")
        return 1
    print("  ✓ every numbered heading is unique and at the correct depth.")
    return 0


def main():
    brief = "--brief" in sys.argv
    sentinel = "--sentinel" in sys.argv
    as_json = "--json" in sys.argv
    if "--structure" in sys.argv:   # pure file lint — no DB, dispatch before connecting
        sys.exit(cmd_structure())
    if psycopg2 is None:
        print("psycopg2 not installed — DB checks need the VPS; only --structure runs offline.")
        sys.exit(2)
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    if "--coverage" in sys.argv:
        with conn.cursor() as cur:
            rc = cmd_coverage(cur)
        conn.close()
        sys.exit(rc)
    if "--invariants" in sys.argv:
        with conn.cursor() as cur:
            rc = cmd_invariants(cur)
        conn.close()
        sys.exit(rc)
    if "--render-audit" in sys.argv:
        with conn.cursor() as cur:
            rc = cmd_render_audit(cur)
        conn.close()
        sys.exit(rc)
    problems = 0
    v3 = v4 = 0
    drift_counts, bad, unreg, inference = {}, [], [], {}
    out = []
    with conn.cursor() as cur:
        # 1. validator installed?
        cur.execute("SELECT check_code, mode FROM ontology_validator_config ORDER BY 1;")
        cfg = cur.fetchall()
        out.append(f"validator: {'installed ' + str(cfg) if cfg else 'NOT INSTALLED (run deploy_691)'}")

        # 2. V4 client contamination (verified facts citing a cross-client doc)
        cur.execute("SELECT count(*) FROM v_ontology_client_cross;")
        v4 = cur.fetchone()[0]
        if v4:
            problems += 1
            out.append(f"[X] V4 client contamination: {v4} verified fact(s) cite a cross-client doc — SELECT * FROM v_ontology_client_cross;")
        else:
            out.append("[ok] V4 client isolation: clean (0 cross-client verified facts)")

        # 3. V3 grounding: verified facts missing source/excerpt
        cur.execute("SELECT count(*) FROM matter_facts WHERE provenance_level='verified' AND (source_id IS NULL OR coalesce(excerpt,'')='');")
        v3 = cur.fetchone()[0]
        if v3:
            problems += 1
            out.append(f"[X] V3 grounding: {v3} verified matter_fact(s) missing source_id/excerpt")
        else:
            out.append("[ok] V3 grounding: clean (all verified facts grounded)")

        # 4. drift tables — should be cold
        for t in DRIFT_TABLES:
            cur.execute(f"SELECT count(*) FROM {t};")
            n = cur.fetchone()[0]
            drift_counts[t] = n
            if n:
                out.append(f"[!] drift '{t}': {n} row(s) present — canonical target in ONTOLOGY.md sec3 (do not add more)")
            elif not brief:
                out.append(f"[ok] drift '{t}': empty")

        # 5. provenance vocab creep
        for t in PROVENANCE_TABLES:
            cur.execute(f"SELECT DISTINCT provenance_level FROM {t} WHERE provenance_level IS NOT NULL;")
            for (v,) in cur.fetchall():
                if v not in PROVENANCE_VOCAB:
                    bad.append(f"{t}:{v}")
        if bad:
            problems += 1
            if not brief:
                out.append(f"[X] provenance vocab creep: {bad} (canonical set: {sorted(PROVENANCE_VOCAB)})")
        elif not brief:
            out.append(f"[ok] provenance vocab: all values in canonical set of {len(PROVENANCE_VOCAB)}")

        # 5b. geometry accuracy vocab — a SEPARATE controlled vocabulary (ONTOLOGY.md §2.4 GeometrySource).
        #     map_parcels.accuracy_tier is NOT a provenance_level; audited on its own set, never merged.
        bad_tier = []
        cur.execute("SELECT DISTINCT accuracy_tier FROM map_parcels WHERE accuracy_tier IS NOT NULL;")
        for (v,) in cur.fetchall():
            if v not in ACCURACY_VOCAB:
                bad_tier.append(f"map_parcels:{v}")
        if bad_tier:
            problems += 1
            out.append(f"[X] accuracy vocab creep: {bad_tier} (canonical set: {sorted(ACCURACY_VOCAB)})")
        elif not brief:
            out.append(f"[ok] accuracy vocab: all map_parcels.accuracy_tier in canonical set of {len(ACCURACY_VOCAB)}")

        # 6. ONTOLOGY.md coverage — AUTHORITATIVE (vs the actual file, not a hardcoded REGISTERED list).
        cov_named, cov_total, cov_missing = coverage_gaps(cur)
        unreg = [t for (t, n) in (cov_missing or [])]
        if unreg:
            out.append(f"[!] ontology coverage: {len(unreg)} populated domain table(s) NOT named in ONTOLOGY.md → run --coverage: {unreg[:20]}")
        elif not brief:
            out.append(f"[ok] ontology coverage: {cov_named}/{cov_total} populated domain tables named (nothing orphaned)")

        # 7. inference tier (24h) — unify the health surface so /health JSON carries BOTH
        #    data-integrity and inference signals (mirrors the inference_tier_sentinel rollup).
        try:
            cur.execute("""
                SELECT count(*) AS total,
                       count(*) FILTER (WHERE model_tier='tier1')          AS tier1,
                       count(*) FILTER (WHERE fallback_reason IS NOT NULL) AS fallbacks,
                       count(*) FILTER (WHERE NOT success)                 AS failed,
                       max(timestamp) FILTER (WHERE success AND model_tier='tier1') AS last_local
                  FROM inference_audit WHERE timestamp > now() - interval '24 hours';""")
            r = cur.fetchone()
            if r and r[0]:
                inference = {"calls_24h": r[0], "tier1": r[1], "tier1_pct": round(100 * r[1] / r[0]),
                             "fallbacks": r[2], "failed": r[3],
                             "last_local_ok": r[4].isoformat() if r[4] else None}
                if not brief:
                    out.append(f"[i] inference tier (24h): {r[0]} calls · {inference['tier1_pct']}% local · {r[2]} fallback(s)")
            else:
                inference = {"calls_24h": 0}
        except Exception:
            inference = {"error": "inference_audit unavailable"}

    # --sentinel: alert ONLY on new actionable contamination (V3/V4), never on standing backlog.
    if sentinel and (v3 or v4):
        bits = []
        if v4:
            bits.append(f"{v4} verified fact(s) cite a cross-client document (V4)")
        if v3:
            bits.append(f"{v3} verified fact(s) missing source/excerpt (V3)")
        desc = ("ontology_check daily sentinel: " + "; ".join(bits)
                + ". Triage: SELECT * FROM v_ontology_client_cross; re-home to the doc's matter (see ONTOLOGY.md A5).")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                         severity, hole_type, description, metadata, status)
                       VALUES ('ontology_check','v1', md5(%s), 'high', 'ontology_contamination',
                         %s, jsonb_build_object('v3',%s,'v4',%s), 'open')""",
                    (desc[:200], desc, v3, v4),
                )
        except Exception:
            pass  # sentinel must never crash the timer

    # coverage regression: a NEW populated domain table appeared unnamed → keep the map honest.
    if sentinel and unreg:
        cdesc = (f"ontology coverage regression: {len(unreg)} populated domain table(s) not named in "
                 f"ONTOLOGY.md — {unreg[:15]}. Orient each (§2 gated-core or §8 with a state); run "
                 f"scripts/ontology_check.py --coverage.")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                         severity, hole_type, description, metadata, status)
                       VALUES ('ontology_check','v1', md5(%s), 'medium', 'ontology_coverage_gap',
                         %s, jsonb_build_object('unnamed',%s), 'open')""",
                    (str(sorted(unreg))[:200], cdesc, len(unreg)),
                )
        except Exception:
            pass

    # invariant-integration regression: a 🟢 §4 invariant names an enforcement artifact that no longer
    # EXISTS (green-that-isn't-true) → governance has drifted from what the ontology claims. Alert on any
    # broken ref; NEVER on the standing amber backlog (🟡/flagged/shadow are expected, not failures).
    if sentinel:
        try:
            with conn.cursor() as cur:
                res = invariant_gaps(cur)
            fails = res[3] if res else []
            if fails:
                key = "; ".join(f"{a}:{','.join(m)}" for a, m, _ in fails)
                idesc = (f"ontology invariant-integration regression: {len(fails)} 🟢 §4 invariant(s) name an "
                         f"enforcement artifact that does NOT exist — {[a for a, _, _ in fails]}. Green-that-isn't-"
                         f"true: §4 claims enforcement the DB/code can't back. Fix the artifact name or build it; "
                         f"run scripts/ontology_check.py --invariants.")
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                             severity, hole_type, description, metadata, status)
                           VALUES ('ontology_check','v1', md5(%s), 'high', 'ontology_invariant_broken',
                             %s, jsonb_build_object('broken',%s), 'open')""",
                        (key[:200], idesc, len(fails)),
                    )
        except Exception:
            pass  # sentinel must never crash the timer

    # A32 client render-audit: a raw internal token survived projection onto a client-facing field → a
    # client-visible leak. Alert (shadow — this guard never blocks); silent when clean.
    if sentinel:
        try:
            with conn.cursor() as cur:
                _checked, leaks, _unmapped = render_leaks(cur)
            if leaks:
                classes = sorted({cls for _, cls, _, _ in leaks})
                fields = sorted({f for f, _, _, _ in leaks})
                key = "client_render_leak:" + ",".join(classes) + "|" + ",".join(fields)
                rdesc = (f"A32 client render-audit: {len(leaks)} projected client value(s) still carry a "
                         f"forbidden internal token — classes {classes} in fields {fields}. A raw internal "
                         f"string would reach a client surface. Extend the client_ontology projector(s); "
                         f"run scripts/ontology_check.py --render-audit for the raw→projected list.")
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                             severity, hole_type, description, metadata, status)
                           VALUES ('ontology_check','v1', md5(%s), 'high', 'client_render_leak',
                             %s, jsonb_build_object('leaks',%s,'classes',%s), 'open')""",
                        (key[:200], rdesc, len(leaks), json.dumps(classes)),
                    )
        except Exception:
            pass  # sentinel must never crash the timer

    conn.close()

    if as_json:
        report = {
            "status": "clean" if problems == 0 else "problems",
            "problems": problems,
            "actionable_contamination": bool(v3 or v4),  # the only thing that should page you
            "checks": {
                "v3_ungrounded_verified": v3,
                "v4_cross_client_facts": v4,
                "drift_table_rows": drift_counts,
                "provenance_vocab_creep": bad,
                "unregistered_tables": len(unreg),
            },
            "inference_tier": inference,
            "validator_mode": {c: m for c, m in cfg} if cfg else None,
        }
        print(json.dumps(report, indent=2))
        sys.exit((1 if (v3 or v4) else 0) if sentinel else (1 if problems else 0))

    print("=== ontology_check " + ("(brief) " if brief else "") + ("(sentinel) " if sentinel else "") + "===")
    for line in out:
        print("  " + line)
    print(f"=== {'CLEAN' if problems == 0 else str(problems) + ' PROBLEM(S)'} ===")
    # Interactive/gate mode: non-zero on any drift so it's usable as a health gate.
    # Sentinel mode: exit reflects ONLY actionable contamination (V3/V4) — the standing
    # backlog (vocab creep, pre-existing drift rows) must not put the daily oneshot into
    # a systemd 'failed' state (keep `systemctl --failed` at zero).
    if sentinel:
        sys.exit(1 if (v3 or v4) else 0)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
