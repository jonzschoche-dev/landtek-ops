#!/usr/bin/env python3
"""client_dependability.py — the STANDING dependability harness + gate for the proof clients.

WHY (operator, 2026-07-03): "these products are not dependable yet." True — the session before
fixed correctness defects (a fabricated Aug-1 date, a phantom overdue, a garbled internal label)
one at a time, reactively. Whack-a-mole is not a guarantee. This replaces it with a SYSTEMATIC,
re-runnable measurement over the exact facts a client SEES on their portal + matter-detail pages,
composed into a per-client Dependability Score (0-100) and a documented SHIP gate that decides
whether a client should be handed their link.

DISCIPLINE (load-bearing): this is a GUARANTEE tool, so it must be HONEST above all. A dependability
harness that over-reports dependability is the worst possible bug. Every check is deterministic
($0, no LLM, no credit burn). The score weights CORRECTNESS heaviest — one fabricated/ungrounded
fact must tank the score and force a FAIL, regardless of how complete or stable the rest is. We
audit what the client SEES (the rendered portal HTML), not raw tables, so a guard that hides a
defect from the client legitimately raises the score, and a defect that leaks lowers it.

Four axes the operator named:
  CORRECT     — per shown fact: grounded? phantom? stale? garbled/internal-leak? draft-leak?
                separation-clean? (ALL matters, every fact — not spot checks)
  COMPLETE    — % action-stage matters with a grounded date · % docs readable · verified-fact cov
  STABLE      — portal + matter-detail render 200/clean · data freshness · deadline refresh daemon
                · systemctl --failed clean (expected-idle distinguished from real failure)
  TRUSTWORTHY — the composed score + gate + ranked gap list

Reuses (does NOT rebuild): client_portal.render_client_portal / render_matter_detail (the exact
client-visible render), its guards (_is_internal_fragment / _has_tag / _safe_label), deadlines.py
freshness, knowledge_coverage-style verified-fact coverage, the record_gaps table.

  python3 scripts/client_dependability.py            # measure both proof clients, print report
  python3 scripts/client_dependability.py --write     # also persist to client_dependability table
  python3 scripts/client_dependability.py --client MWK-001
  python3 scripts/client_dependability.py --json       # machine-readable (for /ops/dependability)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone

import psycopg2
import psycopg2.extras

# Import the LIVE client-facing render layer + its guards so we audit exactly what a client SEES.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
sys.path.insert(0, "/root/landtek/leo_tools")
try:
    from client_portal import (  # noqa: E402
        render_client_portal, render_matter_detail,
        _NO_DATE_STAGES, _INTERNAL_LABEL_MARKERS,
    )
except Exception as _e:  # pragma: no cover — harness must fail LOUD, never green-when-broken
    print(f"FATAL: cannot import the live client_portal render layer: {_e}", file=sys.stderr)
    raise

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
PROOF_CLIENTS = ("MWK-001", "Paracale-001")

# Freshness thresholds (days). The client-facing deadline surface is re-derived by deadlines.py
# --write; if the latest as_of is older than this, dates on the portal are STALE and a "3 days
# overdue" could silently be wrong. STALE_WARN flags it; STALE_FAIL treats it as a correctness
# defect (a shown date can no longer be trusted as current).
STALE_WARN_DAYS = 2
STALE_FAIL_DAYS = 7

# A date shown to a client is GROUNDED only if it is either (a) a structured next_deadline /
# surfaced deadline that traces to a matter the operator dated, OR (b) honestly marked as not-yet-
# confirmed via a §4B caveat tag or a NEEDS-A-DATE bucket. An action-stage matter that shows a bare
# date with NO caveat and NO structured backing would be an ungrounded assertion — the class we tank.
_ISO_DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")

# Stages that legitimately carry no deadline (advisory/observation). Mirrors client_portal +
# deadlines.py so "no date" on these is NOT counted as an incompleteness or correctness defect.
_NO_DATE_TOKENS = tuple(_NO_DATE_STAGES)


def _conn():
    c = psycopg2.connect(DSN)
    c.autocommit = True
    return c


def _rd(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _no_date_ok(stage: str | None) -> bool:
    s = (stage or "").lower()
    return any(tok in s for tok in _NO_DATE_TOKENS)


# A snake_case stage token (e.g. "trial_aug12_testimony_set") trips client_portal's
# _is_internal_fragment (it starts lowercase) — but it is the DESIGNED _safe_label fallback and
# the portal renders it deliberately. It is NOT internal scratch (no cross-matter reference, no
# pipeline separator). Calibration to zero false positives: treat a bare snake_case status token
# as an "unpolished label" (soft WARN), and reserve the "internal_fragment leak" verdict for the
# genuinely-internal markers (the || separator, perjury-point / cross-matter narrative shorthand).
_SNAKE_STAGE_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)+$")


def _is_snake_stage(text: str | None) -> bool:
    return bool(text) and bool(_SNAKE_STAGE_RE.match((text or "").strip()))


def _has_hard_internal_marker(text: str | None) -> bool:
    """True only for genuinely-internal content that must never reach a client — the || pipeline
    separator or a known internal narrative phrase. This is the strict subset of
    _is_internal_fragment that excludes benign snake_case stage tokens."""
    if not text:
        return False
    low = text.strip().lower()
    return any(mk in low for mk in _INTERNAL_LABEL_MARKERS)


# ---------------------------------------------------------------------------
# Fact enumeration — the EXACT facts a client reads, pulled from the live render.
# ---------------------------------------------------------------------------
def _strip_html(h: str) -> str:
    """Crude tag strip → the visible text a client actually reads. Good enough to hunt leaks."""
    h = re.sub(r"<[^>]+>", " ", h or "")
    h = re.sub(r"&larr;|&rarr;", " ", h)
    h = re.sub(r"&amp;", "&", h)
    h = re.sub(r"&nbsp;", " ", h)
    h = re.sub(r"\s+", " ", h)
    return h.strip()


def _active_matters(conn, client_code: str) -> list[dict]:
    """The active (non-AUTO, non-closed) matters exactly as the portal selects them."""
    cur = _rd(conn)
    cur.execute("""
        SELECT matter_code, title, status, current_stage, next_deadline, next_event,
               matter_type, docket_number, court_or_agency
          FROM matters
         WHERE client_code = %s
           AND matter_code NOT LIKE 'AUTO-%%'
           AND COALESCE(status, '') NOT IN ('closed', 'archived')
         ORDER BY matter_code
    """, (client_code,))
    rows = cur.fetchall()
    cur.close()
    return rows


def _latest_surface_asof(conn) -> date | None:
    cur = conn.cursor()
    cur.execute("SELECT max(as_of) FROM surfaced_deadlines")
    r = cur.fetchone()
    cur.close()
    return r[0] if r and r[0] else None


# ---------------------------------------------------------------------------
# CORRECT — per-fact checks over the rendered client view.
# ---------------------------------------------------------------------------
def check_correct(conn, client_code: str, asof: date | None, today: date) -> list[dict]:
    """Return a list of FINDING rows (only failures / warnings). A finding is:
       {fact_type, matter, check, verdict (FAIL|WARN), detail}.
       Verdicts of FAIL on a correctness check are score-tanking + gate-blocking."""
    findings: list[dict] = []

    # (1) Render the portal home exactly as the client gets it, then scan the visible text for
    #     internal-fragment leaks + separation bleed. This is the strongest check: it audits the
    #     literal client output, so any guard that hides a defect legitimately passes here.
    try:
        _title, body = render_client_portal(client_code)
    except Exception as e:
        findings.append({"fact_type": "portal", "matter": None, "check": "render",
                         "verdict": "FAIL", "detail": f"portal render raised: {str(e)[:120]}"})
        return findings  # can't audit facts we can't render — fail loud
    visible = _strip_html(body)

    # separation: no OTHER client's code may appear in this client's rendered portal.
    for other in PROOF_CLIENTS:
        if other != client_code and other in body:
            findings.append({"fact_type": "separation", "matter": None, "check": "cross_client_leak",
                             "verdict": "FAIL",
                             "detail": f"other client's code '{other}' appears in {client_code}'s portal HTML"})
    # separation: matter codes of the OTHER client must not render here.
    cur = _rd(conn)
    cur.execute("""SELECT matter_code FROM matters
                    WHERE client_code IN %s AND client_code <> %s""",
                (PROOF_CLIENTS, client_code))
    for r in cur.fetchall():
        mc = r["matter_code"]
        if mc and re.search(r"\b" + re.escape(mc) + r"\b", body):
            findings.append({"fact_type": "separation", "matter": mc, "check": "cross_matter_leak",
                             "verdict": "FAIL",
                             "detail": f"foreign matter '{mc}' rendered in {client_code}'s portal"})
    cur.close()

    matters = _active_matters(conn, client_code)

    # surfaced label per matter (latest snapshot) — to detect phantom + internal-leak at source.
    surf = {}
    if asof is not None:
        cur = _rd(conn)
        cur.execute("""
            SELECT DISTINCT ON (matter_code) matter_code, due_date, label, bucket, as_of
              FROM surfaced_deadlines
             WHERE matter_code IN (SELECT matter_code FROM matters WHERE client_code = %s)
             ORDER BY matter_code, as_of DESC, (bucket='OVERDUE') DESC, due_date ASC
        """, (client_code,))
        surf = {r["matter_code"]: r for r in cur.fetchall()}
        cur.close()

    for m in matters:
        mc = m["matter_code"]
        stage = m.get("current_stage") or m.get("status") or ""
        s = surf.get(mc)
        next_event = m.get("next_event")

        # ---- garbled / internal-leak at the SOURCE (surfaced label + next_event) -------------
        # Two distinct classes, calibrated to zero false positives:
        #   (a) HARD internal shorthand (|| separator, perjury/cross-matter narrative) — a FAIL if
        #       it reaches the visible text, else a WARN (guarded upstream by _safe_label).
        #   (b) a bare snake_case stage token rendered AS the next-action label — the designed
        #       fallback, but unpolished for a client; a soft "unpolished_label" WARN, NOT a leak.
        for src_name, src in (("surfaced_label", (s or {}).get("label")),
                              ("next_event", next_event)):
            if not src:
                continue
            if _has_hard_internal_marker(src):
                verdict = "FAIL" if src.strip() in visible else "WARN"
                findings.append({"fact_type": "next_action", "matter": mc, "check": "internal_fragment",
                                 "verdict": verdict,
                                 "detail": f"{src_name} is internal shorthand: {src.strip()[:80]!r}"
                                           + ("" if verdict == "FAIL" else " (guarded from client view)")})
        # (b) is judged on what the client ACTUALLY sees: does the rendered "Next action" cell show
        #     a raw snake_case token? We detect it from the visible text so a polished fallback passes.
        if _is_snake_stage(stage) and stage.strip() in visible:
            findings.append({"fact_type": "next_action", "matter": mc, "check": "unpolished_label",
                             "verdict": "WARN",
                             "detail": f"next-action shows a raw status token {stage.strip()!r} "
                                       f"(reads as jargon, not a client next-action)"})

        # ---- grounded? a shown date must be structured OR honestly caveated ------------------
        has_structured_date = (m.get("next_deadline") is not None) or (
            s is not None and s.get("due_date") is not None)
        action_stage = not _no_date_ok(stage) and not mc.startswith("AUTO-")
        if has_structured_date:
            # a date IS shown. If it's from prose-harvest with no caveat AND no structured
            # next_deadline, that's the phantom class. deadlines.py deploy_644 gates prose harvest
            # to matters that already carry next_deadline, so re-verify that invariant holds live.
            if m.get("next_deadline") is None and s is not None and s.get("due_date") is not None:
                # surfaced a date for a matter whose next_deadline is NULL — the exact phantom trap.
                findings.append({"fact_type": "deadline", "matter": mc, "check": "phantom_date",
                                 "verdict": "FAIL",
                                 "detail": f"surfaced date {s['due_date']} for a matter with NULL "
                                           f"next_deadline (prose-harvest phantom risk)"})
        # ---- stale? (only matters if a date is actually shown) ------------------------------
        if has_structured_date and asof is not None:
            age = (today - asof).days
            if age >= STALE_FAIL_DAYS:
                findings.append({"fact_type": "deadline", "matter": mc, "check": "stale",
                                 "verdict": "FAIL",
                                 "detail": f"deadline surface is {age}d old (>= {STALE_FAIL_DAYS}d); "
                                           f"shown countdown may be wrong"})
            elif age >= STALE_WARN_DAYS:
                findings.append({"fact_type": "deadline", "matter": mc, "check": "stale",
                                 "verdict": "WARN",
                                 "detail": f"deadline surface is {age}d old (>= {STALE_WARN_DAYS}d)"})

    # (2) matter-detail leak scan — render each matter's detail page and audit its visible text +
    #     timeline notes (the class where a stage-classifier's internal reasoning string leaks).
    for m in matters:
        mc = m["matter_code"]
        try:
            _t, mbody = render_matter_detail(client_code, mc)
        except Exception as e:
            # a 404/abort is expected only if the matter is legitimately hidden; here we selected
            # exactly the portal's active set, so a raise IS a real failure.
            findings.append({"fact_type": "matter_detail", "matter": mc, "check": "render",
                             "verdict": "FAIL", "detail": f"matter-detail render raised: {str(e)[:100]}"})
            continue
        mvisible = _strip_html(mbody)
        # internal separator / shorthand must never reach the visible matter page
        for marker in ("||", "PERJURY POINT", "docs from other matters", "contaminated"):
            if marker.lower() in mvisible.lower():
                findings.append({"fact_type": "matter_detail", "matter": mc, "check": "internal_leak",
                                 "verdict": "FAIL",
                                 "detail": f"internal marker {marker!r} visible on matter page"})
        # foreign matter codes must not appear on this matter's page
        for other in PROOF_CLIENTS:
            if other != client_code and other in mbody:
                findings.append({"fact_type": "matter_detail", "matter": mc, "check": "cross_client_leak",
                                 "verdict": "FAIL",
                                 "detail": f"other client '{other}' referenced on {mc} page"})

    # (2b) DOCUMENT cross-client separation — the robust check. A filename need not contain the
    #      other client's code (e.g. 'drive_new_Pages_151-330_EXPA-000250-V.pdf' is an MWK doc with
    #      no 'MWK' in the name), so string-scanning HTML misses it. Instead: for each matter the
    #      portal lists, find any linked+non-draft (i.e. client-visible) document whose OWN case_file
    #      belongs to a DIFFERENT client. That is a cross-client document bleed rendered to the wrong
    #      client — a separation breach, FAIL. Mirrors the portal/matter-detail doc queries exactly.
    cur = _rd(conn)
    cur.execute("""
        SELECT l.matter_code, d.id, d.case_file,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename,'') nm
          FROM documents d
          JOIN document_matter_links l ON l.doc_id = d.id
          JOIN matters mm ON mm.matter_code = l.matter_code
         WHERE mm.client_code = %s
           AND mm.matter_code NOT LIKE 'AUTO-%%'
           AND COALESCE(mm.status,'') NOT IN ('closed','archived')
           AND d.case_file IS NOT NULL AND d.case_file <> ''
           AND d.case_file NOT IN (%s, 'Owner')
           -- match the client-visible doc filter: drafts are already excluded from the render
           AND COALESCE(d.classification,'') NOT ILIKE '%%draft%%'
           AND COALESCE(NULLIF(d.smart_filename,''),d.original_filename,'') NOT ILIKE '%%draft%%'
         ORDER BY l.matter_code, d.id
    """, (client_code, client_code))
    for r in cur.fetchall():
        # Only a leak if the foreign case_file is another REAL client (not a scoping tag / matter code).
        findings.append({"fact_type": "document", "matter": r["matter_code"], "check": "cross_client_doc",
                         "verdict": "FAIL",
                         "detail": f"doc#{r['id']} '{(r['nm'] or '')[:48]}' has case_file "
                                   f"'{r['case_file']}' but is linked to {client_code}'s matter "
                                   f"{r['matter_code']} — foreign document rendered to client"})
    cur.close()

    # (3) draft-leak — any draft doc reaching the client's visible deliverables/docs. The portal
    #     SQL filters drafts, so this should be zero; we re-verify by scanning the rendered docs.
    if re.search(r"\bdraft\b", visible, re.I):
        # only a FAIL if it's a document/deliverable name, not the word in prose. Check the docs.
        cur = _rd(conn)
        cur.execute("""
            SELECT DISTINCT COALESCE(NULLIF(d.smart_filename,''), d.original_filename,'') nm
              FROM documents d JOIN document_matter_links l ON l.doc_id=d.id
              JOIN matters mm ON mm.matter_code=l.matter_code
             WHERE mm.client_code=%s
               AND (COALESCE(d.classification,'') ILIKE '%%draft%%'
                    OR COALESCE(NULLIF(d.smart_filename,''),d.original_filename,'') ILIKE '%%draft%%')
        """, (client_code,))
        for r in cur.fetchall():
            nm = (r["nm"] or "").strip()
            if nm and nm[:40] in visible:
                findings.append({"fact_type": "document", "matter": None, "check": "draft_leak",
                                 "verdict": "FAIL",
                                 "detail": f"draft document surfaced to client: {nm[:70]!r}"})
        cur.close()

    return findings


# ---------------------------------------------------------------------------
# COMPLETE — per-client coverage.
# ---------------------------------------------------------------------------
def measure_complete(conn, client_code: str) -> dict:
    cur = _rd(conn)
    matters = _active_matters(conn, client_code)
    action = [m for m in matters
              if not _no_date_ok(m.get("current_stage") or m.get("status"))
              and not m["matter_code"].startswith("AUTO-")]
    action_dated = [m for m in action if m.get("next_deadline") is not None]
    pct_action_dated = (len(action_dated) / len(action)) if action else 1.0

    # docs readable (clean OCR) for this client's case_file
    cf = client_code
    cur.execute("""SELECT count(*) FROM documents d
                    WHERE d.case_file=%s AND (coalesce(d.file_path,'')<>'' OR d.drive_file_id IS NOT NULL)""",
                (cf,))
    docs_total = cur.fetchone()["count"]
    cur.execute("""SELECT count(*) FROM documents d JOIN ocr_quality q ON q.doc_id=d.id
                    WHERE d.case_file=%s AND q.flagged IS FALSE""", (cf,))
    docs_readable = cur.fetchone()["count"]
    pct_docs_readable = (docs_readable / docs_total) if docs_total else 0.0

    # verified-fact coverage (reuse the knowledge_coverage definition: verified vs all facts)
    cur.execute("""SELECT count(*) f, count(*) FILTER (WHERE mf.provenance_level='verified') v
                     FROM matter_facts mf JOIN matters m ON m.matter_code=mf.matter_code
                    WHERE m.client_code=%s""", (client_code,))
    row = cur.fetchone()
    facts, facts_v = row["f"], row["v"]
    pct_facts_verified = (facts_v / facts) if facts else 0.0
    cur.close()
    return {
        "action_matters": len(action),
        "action_dated": len(action_dated),
        "pct_action_dated": pct_action_dated,
        "docs_total": docs_total,
        "docs_readable": docs_readable,
        "pct_docs_readable": pct_docs_readable,
        "facts": facts,
        "facts_verified": facts_v,
        "pct_facts_verified": pct_facts_verified,
    }


# ---------------------------------------------------------------------------
# STABLE — reachability, freshness, refresh daemon, systemd health.
# ---------------------------------------------------------------------------
def _systemctl_failed() -> tuple[int, list[str]]:
    """Count of --failed units + their names. Empty/unavailable → (0, []) but flagged in detail."""
    try:
        out = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain"],
                             capture_output=True, text=True, timeout=10)
        names = [ln.split()[0] for ln in out.stdout.splitlines() if ln.strip()]
        return len(names), names
    except Exception:
        return -1, []  # -1 = couldn't check (e.g. running off-box); reported honestly


def _deadline_refresh_daemon() -> dict:
    """Is the surfaced_deadlines refresh actually scheduled+running? The client-facing dates are
    only as fresh as the last deadlines.py --write; if nothing schedules it, freshness is manual."""
    info = {"timer": "landtek-proactive.timer", "enabled": None, "active": None}
    for key, arg in (("enabled", "is-enabled"), ("active", "is-active")):
        try:
            r = subprocess.run(["systemctl", arg, "landtek-proactive.timer"],
                               capture_output=True, text=True, timeout=10)
            info[key] = r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            info[key] = f"check_failed:{str(e)[:40]}"
    return info


def measure_stable(conn, client_code: str, asof: date | None, today: date) -> dict:
    findings: list[dict] = []
    # reachability: the render functions run without raising for every active matter (already
    # partially covered in CORRECT; here we produce the STABLE signal).
    reach_ok = True
    try:
        render_client_portal(client_code)
    except Exception as e:
        reach_ok = False
        findings.append({"axis": "stable", "check": "portal_reachable", "verdict": "FAIL",
                         "detail": f"portal render raised: {str(e)[:100]}"})
    n_matter_ok = 0
    matters = _active_matters(conn, client_code)
    for m in matters:
        try:
            render_matter_detail(client_code, m["matter_code"])
            n_matter_ok += 1
        except Exception as e:
            reach_ok = False
            findings.append({"axis": "stable", "check": "matter_detail_reachable", "verdict": "FAIL",
                             "detail": f"{m['matter_code']}: {str(e)[:80]}"})

    # freshness
    age = (today - asof).days if asof else None
    fresh_ok = age is not None and age < STALE_WARN_DAYS
    if age is None:
        findings.append({"axis": "stable", "check": "deadline_freshness", "verdict": "FAIL",
                         "detail": "no surfaced_deadlines rows at all — deadline surface is empty"})
    elif age >= STALE_FAIL_DAYS:
        findings.append({"axis": "stable", "check": "deadline_freshness", "verdict": "FAIL",
                         "detail": f"deadline surface {age}d old (as_of {asof})"})
    elif age >= STALE_WARN_DAYS:
        findings.append({"axis": "stable", "check": "deadline_freshness", "verdict": "WARN",
                         "detail": f"deadline surface {age}d old (as_of {asof})"})

    # refresh daemon
    daemon = _deadline_refresh_daemon()
    daemon_ok = (daemon.get("enabled") == "enabled" and daemon.get("active") == "active")
    if not daemon_ok:
        findings.append({"axis": "stable", "check": "deadline_refresh_daemon", "verdict": "WARN",
                         "detail": f"{daemon['timer']} enabled={daemon['enabled']} active={daemon['active']} "
                                   f"— surfaced_deadlines refresh is not scheduled; dates go stale silently"})

    # systemd health (a green monitor over a broken unit is worse than a red one — report truly)
    n_failed, failed_names = _systemctl_failed()
    sysd_ok = (n_failed == 0)
    if n_failed > 0:
        findings.append({"axis": "stable", "check": "systemctl_failed", "verdict": "WARN",
                         "detail": f"{n_failed} failed unit(s): {', '.join(failed_names)}"})
    elif n_failed < 0:
        findings.append({"axis": "stable", "check": "systemctl_failed", "verdict": "WARN",
                         "detail": "could not query systemctl (running off-box?) — health unknown"})

    return {
        "reach_ok": reach_ok,
        "matters_rendered_ok": n_matter_ok,
        "matters_total": len(matters),
        "freshness_days": age,
        "fresh_ok": fresh_ok,
        "daemon": daemon,
        "daemon_ok": daemon_ok,
        "systemctl_failed": n_failed,
        "systemctl_failed_names": failed_names,
        "systemd_ok": sysd_ok,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# TRUSTWORTHY — the composed score + gate.
# ---------------------------------------------------------------------------
# The formula (documented + honest):
#   CORRECT is a HARD gate first: any correctness FAIL → the correctness sub-score is forced very
#   low so the composite cannot pass. This encodes "one fabricated fact tanks the score."
#   Then the composite is a weighted blend: CORRECT 60, COMPLETE 25, STABLE 15.
SHIP_THRESHOLD = 90         # composite score bar
# SHIP also REQUIRES zero open correctness FAILs (belt-and-suspenders with the hard gate above).

W_CORRECT, W_COMPLETE, W_STABLE = 60, 25, 15


def _correct_subscore(findings: list[dict]) -> tuple[float, int, int]:
    fails = sum(1 for f in findings if f["verdict"] == "FAIL")
    warns = sum(1 for f in findings if f["verdict"] == "WARN")
    if fails > 0:
        # Hard tank: any correctness FAIL drives the sub-score to near-zero (each fail is a shown
        # falsehood). Multiple fails floor it at 0. This is the "worst possible bug" guardrail.
        sub = max(0.0, 15.0 - 15.0 * fails)   # 1 fail → 0, capped at 0
    else:
        # No fabricated facts. Warns are soft data-quality dings (guarded from the client view).
        sub = max(60.0, 100.0 - 8.0 * warns)
    return sub, fails, warns


def _complete_subscore(c: dict) -> float:
    # blend the three coverage ratios; action-dated weighted most (it's the point of the product).
    return 100.0 * (0.55 * c["pct_action_dated"]
                    + 0.25 * c["pct_docs_readable"]
                    + 0.20 * c["pct_facts_verified"])


def _stable_subscore(s: dict) -> float:
    score = 100.0
    if not s["reach_ok"]:
        score -= 60.0
    if not s["fresh_ok"]:
        score -= 20.0
    if not s["daemon_ok"]:
        score -= 12.0
    if not s["systemd_ok"]:
        score -= 8.0
    return max(0.0, score)


def score_client(conn, client_code: str, today: date) -> dict:
    asof = _latest_surface_asof(conn)
    correct_findings = check_correct(conn, client_code, asof, today)
    complete = measure_complete(conn, client_code)
    stable = measure_stable(conn, client_code, asof, today)

    sub_correct, n_fail, n_warn = _correct_subscore(correct_findings)
    sub_complete = _complete_subscore(complete)
    sub_stable = _stable_subscore(stable)

    composite = (W_CORRECT * sub_correct + W_COMPLETE * sub_complete + W_STABLE * sub_stable) / (
        W_CORRECT + W_COMPLETE + W_STABLE)
    composite = round(composite, 1)

    ship = (composite >= SHIP_THRESHOLD) and (n_fail == 0)

    # ranked gap list — what to fix to raise the score, highest-leverage first.
    gaps: list[tuple[float, str]] = []
    for f in correct_findings:
        weight = 100.0 if f["verdict"] == "FAIL" else 8.0
        gaps.append((weight, f"[CORRECT/{f['verdict']}] {f['matter'] or '-'} · {f['check']}: {f['detail']}"))
    # completeness gaps (leverage = how far each ratio is from 1.0, scaled by its blend weight)
    if complete["pct_action_dated"] < 1.0:
        gaps.append((0.55 * (1 - complete["pct_action_dated"]) * 25 * 100,
                     f"[COMPLETE] only {complete['action_dated']}/{complete['action_matters']} "
                     f"action-stage matters have a grounded date"))
    if complete["pct_docs_readable"] < 0.85:
        gaps.append((0.25 * (1 - complete["pct_docs_readable"]) * 25 * 100,
                     f"[COMPLETE] only {complete['docs_readable']}/{complete['docs_total']} docs readable "
                     f"({complete['pct_docs_readable']*100:.0f}%)"))
    if complete["pct_facts_verified"] < 0.5:
        gaps.append((0.20 * (1 - complete["pct_facts_verified"]) * 25 * 100,
                     f"[COMPLETE] verified-fact coverage {complete['facts_verified']}/{complete['facts']} "
                     f"({complete['pct_facts_verified']*100:.0f}%)"))
    for f in stable.get("findings", []):
        weight = 30.0 if f["verdict"] == "FAIL" else 6.0
        gaps.append((weight, f"[STABLE/{f['verdict']}] {f['check']}: {f['detail']}"))
    gaps.sort(reverse=True)

    return {
        "client_code": client_code,
        "as_of": str(asof) if asof else None,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "score": composite,
        "ship": ship,
        "ship_threshold": SHIP_THRESHOLD,
        "n_correct_fail": n_fail,
        "n_correct_warn": n_warn,
        "sub_correct": round(sub_correct, 1),
        "sub_complete": round(sub_complete, 1),
        "sub_stable": round(sub_stable, 1),
        "complete": complete,
        "stable": stable,
        "correct_findings": correct_findings,
        "gaps": [g for _, g in gaps],
    }


# ---------------------------------------------------------------------------
# Persistence.
# ---------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS client_dependability (
    id           serial PRIMARY KEY,
    run_at       timestamptz DEFAULT now(),
    client_code  text NOT NULL,
    score        real,
    ship         boolean,
    sub_correct  real,
    sub_complete real,
    sub_stable   real,
    n_fail       int,
    n_warn       int,
    detail       jsonb          -- full result (findings, complete, stable, gaps) for the /ops page
);
CREATE INDEX IF NOT EXISTS idx_client_dependability_client_run
    ON client_dependability (client_code, run_at DESC);
"""


def persist(conn, result: dict):
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute("""INSERT INTO client_dependability
        (client_code, score, ship, sub_correct, sub_complete, sub_stable, n_fail, n_warn, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (result["client_code"], result["score"], result["ship"], result["sub_correct"],
         result["sub_complete"], result["sub_stable"], result["n_correct_fail"],
         result["n_correct_warn"], json.dumps(result, default=str)))
    cur.close()


# ---------------------------------------------------------------------------
# CLI report.
# ---------------------------------------------------------------------------
def _print_report(result: dict):
    r = result
    print("\n" + "=" * 78)
    print(f"DEPENDABILITY — {r['client_code']}   (deadline surface as_of {r['as_of']})")
    print("=" * 78)
    verdict = "READY TO SHIP" if r["ship"] else "NOT HANDOFF-READY"
    print(f"  SCORE {r['score']:5.1f}/100   ship-gate (>= {r['ship_threshold']} & 0 correctness fails): {verdict}")
    print(f"    CORRECT   {r['sub_correct']:5.1f}   ({r['n_correct_fail']} fail, {r['n_correct_warn']} warn)")
    c = r["complete"]
    print(f"    COMPLETE  {r['sub_complete']:5.1f}   action-dated {c['action_dated']}/{c['action_matters']} · "
          f"docs {c['docs_readable']}/{c['docs_total']} · verified {c['facts_verified']}/{c['facts']}")
    s = r["stable"]
    print(f"    STABLE    {r['sub_stable']:5.1f}   portal {'ok' if s['reach_ok'] else 'BROKEN'} · "
          f"matters {s['matters_rendered_ok']}/{s['matters_total']} · fresh={s['freshness_days']}d · "
          f"daemon={'ok' if s['daemon_ok'] else 'off'} · failed_units={s['systemctl_failed']}")
    if r["gaps"]:
        print("\n  RANKED GAP LIST (fix top-down to raise the score):")
        for g in r["gaps"][:14]:
            print(f"    • {g}")
    else:
        print("\n  No gaps — all axes clean.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", help="one client_code (default: both proof clients)")
    ap.add_argument("--write", action="store_true", help="persist to client_dependability table")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--today")
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    clients = [a.client] if a.client else list(PROOF_CLIENTS)

    conn = _conn()
    results = []
    for cc in clients:
        res = score_client(conn, cc, today)
        results.append(res)
        if a.write:
            persist(conn, res)
    conn.close()

    if a.json:
        print(json.dumps(results, default=str, indent=2))
    else:
        for res in results:
            _print_report(res)
        if a.write:
            print(f"\n[write] persisted {len(results)} client scores to client_dependability.")
        # honest bottom line
        print("\n" + "-" * 78)
        any_ship = any(r["ship"] for r in results)
        print(f"HANDOFF-READY TODAY: {'YES' if any_ship else 'NO'} — "
              f"{sum(1 for r in results if r['ship'])}/{len(results)} proof clients pass the ship gate.")


if __name__ == "__main__":
    main()
