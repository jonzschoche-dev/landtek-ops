"""LandTek client portal — the per-CLIENT, client-facing view.

Mounted under /ops/ (so it inherits the nginx auth_basic gate on /ops/ —
same gate as the rest of the cockpit; NOT public like /files/c/).

This is the first client-VISIBLE surface: a retainer client opens
/ops/portal/<client_code> and sees ONLY their world — their matters, every
deadline as a human countdown (north-star ordering: OVERDUE → THIS WEEK →
THIS MONTH → UPCOMING → NEEDS-A-DATE), the next action text, and stage.

HARD INVARIANTS honored here:
  * Client/matter separation is ABSOLUTE. Every row is filtered by
    matters.client_code — the NOT-NULL FK to clients(client_code), i.e. the
    VALIDATED matter→client tag — never the weak free-text case_file. A view
    that leaks another client's matter is a data breach, not a bug.
  * No hallucination. Deadlines come from the hardened structured columns
    (surfaced_deadlines at the latest as_of, with matters.next_deadline as the
    grounded fallback). NEEDS-A-DATE is surfaced honestly rather than guessing
    a date or hiding the matter.
  * [HUMAN VERIFY] / [verify-img] tags are rendered VERBATIM — the client sees
    what is confirmed vs estimated; we never strip the caveat.

Reuses ops_dashboard's layout/CSS/helpers so styling stays one cockpit.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

import psycopg2
import psycopg2.extras
from flask import Blueprint, abort

# Reuse the cockpit chrome + DB plumbing so this is ONE app, one style.
from ops_dashboard import CSS, PG_DSN, _esc, _layout, _safe_fetch, _stat_card

# The ONTOLOGY → CLIENT PROJECTION LAYER (deploy_744). EVERY client-visible field is
# rendered THROUGH this module — raw internal fields (snake_case stage codes, "/"-mashed
# forums, next_event prose full of gmail#/CTN/§/doc#/[OPERATOR-ATTESTED] tokens, matter
# codes, dockets) NEVER reach the client HTML. The projection is total: any value it has
# not enumerated returns a clean safe generic (logged via co.unmapped_report()), never the
# raw string. This is ontology invariant A32 enforced at the render boundary.
import client_ontology as co

bp = Blueprint("client_portal", __name__, url_prefix="/ops")

# Aug 12 is counsel's PLANNED testimony date (operator-confirmed 2026-07-01), NOT a written
# court order — a live-source hunt found no grounding notice in corpus, live Gmail, or
# chat_notes, and Barandon's newest email (2026-06-01) says the court had not yet ruled.
# next_deadline IS set (2026-08-12) so the countdown works, but this banner must never read
# as a court-confirmed hearing: it states the date is counsel-planned, notice pending.
NORTH_STAR_DATE = date(2026, 8, 12)
NORTH_STAR_TXT = (
    "Jonathan to testify as Patricia's witness — CV 26-360 (MTC Mercedes, Summary Procedure). "
    "Counsel's planned testimony date; no written court order on file yet (awaiting the notice)."
)

# §4B inference / provenance tags that must survive into a client-facing label — a caveat
# dropped is inference shown as settled fact. [v:...] is a verified-citation marker; the
# rest flag estimated / OCR-soft / uncertain content.
_TAG_RE = re.compile(r"\[(?:HUMAN VERIFY|OPERATOR-ATTESTED[^\]]*|verify-img|OCR:[^\]]*|v:[^\]]*|\?[^\]]*)\]")

# Stages that legitimately carry NO deadline — advisory / observation / closed-ish.
# Mirrors the deadlines.py + /ops/awareness convention so "NEEDS-A-DATE" stays honest
# (an advisory-tracking matter is not a missing-date defect).
_NO_DATE_STAGES = (
    "observation_only", "advisory", "tracking", "no_immediate_deadline",
    "asset_development", "declared_unrelated", "under_review", "out_of_scope",
    "pending_context", "needs_context", "auto_promoted", "auto_triage",
)

# Bucket display order + styling (north-star countdown first).
_BUCKET_ORDER = ["OVERDUE", "THIS WEEK", "THIS MONTH", "UPCOMING", "NEEDS-A-DATE"]
_BUCKET_BADGE = {
    "OVERDUE": "badge-bad",
    "THIS WEEK": "badge-bad",
    "THIS MONTH": "badge-warn",
    "UPCOMING": "badge-ok",
    "NEEDS-A-DATE": "badge-off",
}


def _db():
    return psycopg2.connect(PG_DSN)


def _client_name(client_code: str) -> str | None:
    """Look up a client's display name for the chrome header. Read-only, single-row,
    scoped to the passed (already token-resolved) client_code. Returns None on miss."""
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM clients WHERE client_code = %s", (client_code,))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def _bucket_for(days_out: int | None) -> str:
    """Same boundaries the deadline engine uses (deadlines.py)."""
    if days_out is None:
        return "NEEDS-A-DATE"
    if days_out < 0:
        return "OVERDUE"
    if days_out <= 7:
        return "THIS WEEK"
    if days_out <= 31:
        return "THIS MONTH"
    return "UPCOMING"


def _countdown(days_out: int | None) -> str:
    """Plain-language countdown for a client (no jargon)."""
    if days_out is None:
        return "needs a date"
    if days_out < 0:
        n = -days_out
        return f"{n} day{'s' if n != 1 else ''} overdue"
    if days_out == 0:
        return "due today"
    if days_out == 1:
        return "due tomorrow"
    return f"in {days_out} days"


def _is_no_date_ok(stage: str | None) -> bool:
    s = (stage or "").lower()
    return any(tok in s for tok in _NO_DATE_STAGES)


def _has_tag(*texts: str | None) -> bool:
    """True if any §4B inference/caveat tag (excluding verified [v:...]) is present —
    i.e. the date/claim is estimated or unconfirmed, not settled fact."""
    for t in texts:
        if not t:
            continue
        for m in _TAG_RE.finditer(t):
            if not m.group(0).startswith("[v:"):
                return True
    return False


# Fingerprints of INTERNAL shorthand that must never reach a client label. A
# surfaced_deadlines label carrying any of these is operator/pipeline scratch — not a
# client-safe next-action string. We fall back to next_event / current_stage instead.
# (Defence-in-depth: product-hardener owns the upstream fix in deadlines.py /
# surfaced_deadlines; we never touch that data, we only refuse to render it raw.)
_INTERNAL_LABEL_MARKERS = ("||", "perjury point", "docs from other matters")


def _is_internal_fragment(text: str | None) -> bool:
    """True if a surfaced label looks like internal shorthand rather than a client-facing
    next-action. Trips on: a `||` field separator, known internal phrases, or a string that
    begins lowercase mid-word (a truncated fragment, e.g. '...docs from other matters')."""
    if not text:
        return False
    low = text.strip().lower()
    if any(m in low for m in _INTERNAL_LABEL_MARKERS):
        return True
    # Starts lowercase AND not a normal sentence lead-in — a severed fragment. We allow a
    # leading '[' (a §4B tag like [HUMAN VERIFY]) and normal capitalised/®digit starts.
    first = text.strip()[:1]
    if first and first.islower():
        return True
    return False


def _safe_label(surfaced_label: str | None, next_event: str | None,
                current_stage: str | None) -> str:
    """Choose a client-safe next-action label. Prefer the surfaced label, but if it reads
    as an internal fragment (BLOCKER 1 guard) fall back to next_event, then current_stage,
    then a neutral placeholder — a client label must never pass raw internal shorthand."""
    if surfaced_label and not _is_internal_fragment(surfaced_label):
        return surfaced_label
    if next_event and not _is_internal_fragment(next_event):
        return next_event
    if current_stage and not _is_internal_fragment(current_stage):
        return current_stage
    return "—"


# A document FILENAME is free-text operator metadata (e.g.
# "CTN SL 2026-0128-1210 TO MUNICIPAL MAYOR ... .pdf",
# "RESOLUTION_NOC_CTN_SL_2026_0128_1210_..._v_LGU.PDF") — NOT a typed ontology value, so
# co.friendly_title (which targets matter-TITLE jargon) does not clean the space/underscore
# control-number forms that appear in filenames. This composes the projection's OWN strip
# regexes (referenced read-only) with the free-text CTN/SL/CL control forms, and falls back
# to the TYPED classification when nothing legible survives — so a client-forbidden docket
# ref (CTN / SL- / CL-) can never reach the client from a document name.
#   NOTE: the durable fix is to extend co.friendly_title's control-number regex to the
#   space/underscore forms; that lives in client_ontology.py (out of scope for this pass).
_DOCNAME_EXT_RE = re.compile(r"\.(pdf|png|jpe?g|docx?|xlsx?|txt|heic)$", re.IGNORECASE)
_DOCNAME_CTRL_RE = re.compile(r"\b(?:CTN|NSR|NOC)\b", re.IGNORECASE)
_DOCNAME_CTRLNUM_RE = re.compile(
    r"\b(?:SL|CL)[\s_-]*\d{4}[\s_-]*\d{2,4}[\s_-]*\d{2,4}\b", re.IGNORECASE)
_DOCNAME_CTRLNUM2_RE = re.compile(r"\b(?:SL|CL)\s*\d{4}[-\d]*\b", re.IGNORECASE)
_DOCNAME_TRAILSL_RE = re.compile(r"[\s_-]+(?:SL|CL)\s*$", re.IGNORECASE)


def _client_doc_name(name: str | None, classification: str | None = None) -> str:
    """Client-facing document label. Delegates to the ontology projection
    (`client_ontology.client_doc_name`) so document-filename cleaning is governed in ONE
    place (A32) — hardened there to strip OAC-L / SPA- / bare-docket / spelled-out Sec.
    forms the earlier local version missed."""
    return co.client_doc_name(name, classification)


def _truncate_keep_tags(text: str, cap: int = 200) -> str:
    """Cap label length WITHOUT severing a §4B caveat tag. If a tag sits past the cut,
    append it after an ellipsis so the caveat always survives length-capping (BLOCKER 3)."""
    text = text or ""
    if len(text) <= cap:
        return text
    # If a §4B tag STRADDLES the cap (opens before it, closes after), extend the
    # head to the tag's end so an opened caveat is never cut mid-content.
    head_end = cap
    for m in _TAG_RE.finditer(text):
        if m.start() < cap and m.end() > head_end:
            head_end = m.end()
    head = text[:head_end]
    kept = [m.group(0) for m in _TAG_RE.finditer(text) if m.start() >= head_end]
    # de-dup while preserving order
    seen, extra = set(), []
    for t in kept:
        if t not in seen:
            seen.add(t)
            extra.append(t)
    suffix = (" … " + " ".join(extra)) if extra else "…"
    return head + suffix


def _client_layout(title: str, body: str, client_name: str | None = None,
                   back_url: str | None = None) -> str:
    """Client-facing chrome — deliberately NO ops nav.

    A retainer client must never see (or be tempted to click) the internal
    cockpit links (/ops/cases, /ops/clients, /ops/spend, …). The ops _layout()
    renders that whole nav bar; this one renders ONLY the LandTek brand + the
    client's own page. Same CSS (one style), zero pivot surface.

    Mobile-first: a client opens this on a phone. Header carries the client's
    own name so it reads as *their* workspace; a footer carries the standing
    service-scope disclaimer (LandTek does property & legal-ops work, not legal
    advice). `back_url` renders a single in-portal breadcrumb link (used by the
    matter-detail page to return to the portal home) — it is always a
    token-scoped URL supplied by the caller, never a pivot to another surface.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    who = _esc(client_name) if client_name else ""
    sub = (f'<div class="client-name">{who}</div>' if who else "")
    back = (f'<a class="back" href="{_esc(back_url)}">&larr; Back to your workspace</a>'
            if back_url else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="manifest" href="/client/_app/manifest.webmanifest">
<meta name="theme-color" content="#0B2545">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LandTek">
<link rel="apple-touch-icon" href="/client/_app/icons/icon-180.png">
<title>{_esc(title)} — LandTek</title>{CSS}
<script>
if('serviceWorker' in navigator){{window.addEventListener('load',function(){{navigator.serviceWorker.register('/client/_app/sw.js',{{scope:'/client/'}}).catch(function(){{}});}});}}
</script>
<style>
  /* Client chrome: brand only, no nav, product-grade, comfortable on a phone. */
  .topbar {{ justify-content:flex-start; gap:12px; padding:14px 20px;
             background:#0f172a; border-bottom:3px solid #38bdf8; }}
  .topbar .brand {{ font-size:18px; letter-spacing:.02em; }}
  .topbar .brand .muted {{ opacity:.65; font-weight:400; }}
  .topbar .client-name {{ margin-left:auto; font-size:13px; color:#cbd5e1;
                          font-weight:600; text-align:right; }}
  .subtitle {{ background:#0f172a; color:#94a3b8; font-size:12.5px;
               padding:0 20px 12px; }}
  .subtitle .ts {{ opacity:.6; }}
  .wrap {{ max-width:820px; padding-top:20px; padding-bottom:8px; }}
  .back {{ display:inline-block; font-size:13px; margin:0 0 12px;
           color:var(--link); }}
  .client-footer {{ max-width:820px; margin:0 auto; padding:20px;
                    color:var(--muted); font-size:12px; line-height:1.6;
                    border-top:1px solid var(--line); }}
  .client-footer .disclaimer {{ font-weight:600; }}
  @media (max-width:640px) {{
    .grid-4 {{ grid-template-columns:repeat(2,1fr); }}
    table {{ font-size:12px; }}
    th,td {{ padding:6px 7px; }}
    h1 {{ font-size:19px; }}
    .topbar {{ flex-wrap:wrap; }}
    .topbar .client-name {{ margin-left:auto; }}
  }}
</style></head><body>
<header class="topbar">
  <div class="brand">LandTek <span class="muted">workspace</span></div>
  {sub}
</header>
<div class="subtitle">Your property &amp; legal-operations workspace <span class="ts">· {now}</span></div>
<main class="wrap">{back}{body}</main>
<footer class="client-footer">
  <div class="disclaimer">LandTek performs property &amp; legal-operations services only; not legal advice.</div>
  <div>Questions on any item here go through your LandTek point of contact.</div>
</footer>
</body></html>"""


@bp.route("/portal/<client_code>")
def client_portal(client_code: str):
    """INTERNAL cockpit view for ONE client — stays behind the /ops basic-auth
    gate (Jonathan's own use). The external, token-gated client entry is
    /client/<token> in client_access.py, which calls render_client_portal()
    with the client-only chrome."""
    title, body = render_client_portal(client_code)
    return _layout(title, body, active="clients")


def _default_doc_url(doc_id: int) -> str:
    """Ops-chrome doc link — the ops-gated public proxy. ONLY used for the internal
    /ops/portal view (behind nginx basic-auth). The client chrome NEVER uses this."""
    return f"/files/c/{int(doc_id)}"


def _default_matter_url(matter_code: str) -> str:
    """Ops-chrome per-matter doc-list link. Ops-gated; not used in client chrome."""
    return f"/files/c/m/{matter_code}"


def _default_matter_detail_url(matter_code: str) -> str:
    """Ops-chrome matter-detail link — the internal /ops/portal view routes the
    matter row to the ops per-client portal (behind nginx basic-auth). The client
    chrome NEVER uses this; the token builder supplies /client/<token>/matter/<code>."""
    return f"/ops/portal/matter/{matter_code}"


def render_client_portal(client_code: str, link_builder=None) -> tuple[str, str]:
    """Build (page_title, body_html) for ONE client's portal, led by the
    deadline countdown. Pure content — the caller wraps it in the appropriate
    chrome (_layout for internal /ops, _client_layout for the client link).

    link_builder: optional (doc_url_fn, matter_url_fn, matter_detail_url_fn) triple.
    When the portal is rendered in CLIENT chrome (reached via /client/<token>), the
    caller passes a builder that emits TOKEN-SCOPED, ownership-checked URLs
    (/client/<token>/doc/<id>, /client/<token>/m/<code>,
    /client/<token>/matter/<code>). When None (the internal /ops/portal view, which
    is ops-gated), we fall back to the /files/c proxy + the ops matter-detail path.
    CRITICAL-1: no bare /files/c/ string may reach the client HTML — that is
    enforced by always routing client links through the injected builder.

    Separation is enforced HERE: every row filters on matters.client_code (the
    validated FK), never case_file. A 404 is raised for an unknown client_code
    so both callers behave identically."""
    doc_url, matter_url, matter_detail_url = (
        link_builder if link_builder
        else (_default_doc_url, _default_matter_url, _default_matter_detail_url))
    today = date.today()
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # --- Resolve the client by its VALIDATED code (FK target), not by case_file. ---
    cur.execute(
        "SELECT client_code, case_file, name, status FROM clients WHERE client_code = %s",
        (client_code,),
    )
    client = cur.fetchone()
    if not client:
        cur.close()
        conn.close()
        abort(404)

    # --- This client's matters ONLY — filtered on the NOT-NULL client_code FK. ---
    # Exclude AUTO- triage stubs + closed/archived from the client-facing view, but
    # keep every active/advisory matter so NEEDS-A-DATE is shown honestly.
    matters = _safe_fetch(cur, conn, """
        SELECT matter_code, title, status, current_stage,
               next_deadline, next_event, matter_type, docket_number,
               court_or_agency, forum
          FROM matters
         WHERE client_code = %s
           AND matter_code NOT LIKE 'AUTO-%%'
           AND COALESCE(status, '') NOT IN ('closed', 'archived')
         ORDER BY matter_code
    """, (client_code,), default=[])

    # --- Latest surfaced-deadline snapshot per matter (the hardened engine output). ---
    # surfaced_deadlines is re-derived as a snapshot (as_of); take the freshest row per
    # (matter_code, due_date) so we read the most recent grounded surface, never re-derive.
    surfaced = _safe_fetch(cur, conn, """
        SELECT DISTINCT ON (matter_code)
               matter_code, due_date, bucket, days_out, label, kind, as_of
          FROM surfaced_deadlines
         WHERE matter_code IN (
                 SELECT matter_code FROM matters WHERE client_code = %s)
         ORDER BY matter_code, as_of DESC, (bucket = 'OVERDUE') DESC, due_date ASC
    """, (client_code,), default=[])
    surf_by_matter = {r["matter_code"]: r for r in surfaced}

    # --- Servable counsel deliverables (bound-PDF dossiers) for THIS client. ---
    # Scope on the client's validated case_file AND (defence-in-depth) require the
    # doc's matter_code — when set — to belong to this client, so a mis-tagged doc
    # can never surface under the wrong client. Only servable rows (a real file on
    # disk or in Drive) are linked; we NEVER invent a link to a doc that isn't there.
    # MEDIUM-1: scope on this client's VALIDATED case_file only, and guard against an
    # empty/blank case_file matching blank-case_file rows (the `Owner`/unassigned escape
    # hatch). We do NOT fall back to client_code and we require the case_file to be
    # non-empty (%s <> '') — a client whose case_file is blank pulls ZERO deliverables
    # rather than every blank-tagged doc. Defence-in-depth: a doc that DOES carry a
    # matter_code must additionally belong to this client's matters; matter_code-NULL rows
    # (the 8 real MWK-001 deliverables) still pass because they're scoped by case_file.
    case_file = (client.get("case_file") or "").strip()
    deliverables = _safe_fetch(cur, conn, """
        SELECT d.id,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename, 'Deliverable') AS name,
               d.doc_date, d.classification, d.matter_code
          FROM documents d
         WHERE %s <> ''
           AND d.case_file = %s
           AND d.classification ILIKE '%%Counsel Deliverable%%'
           AND (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL)
           AND (d.matter_code IS NULL OR d.matter_code IN (
                  SELECT matter_code FROM matters WHERE client_code = %s))
           -- evidence-grade = RECEIVED, not draft: never surface a draft to a client.
           AND COALESCE(d.classification,'')                       NOT ILIKE '%%draft%%'
           AND COALESCE(NULLIF(d.smart_filename,''), d.original_filename, '') NOT ILIKE '%%draft%%'
         ORDER BY d.doc_date DESC NULLS LAST, d.id DESC
    """, (case_file, case_file, client_code), default=[])

    # Property spine (same property_readiness the ops UI + Leo read). Client-facing
    # projection only — no asset_code / prep-engine jargon in the HTML.
    title_rows = _safe_fetch(cur, conn, """
        SELECT a.title_ref, a.label, a.title_status, a.possession,
               r.readiness_score, r.weakest_axis, r.next_prep_action,
               r.documents, r.status_axis, r.occupants, r.ownership,
               r.title_issues, r.mapping
          FROM property_assets a
          LEFT JOIN property_readiness r ON r.asset_code = a.asset_code
         WHERE a.client_code = %s
            OR (%s <> '' AND a.case_file = %s)
         ORDER BY r.readiness_score ASC NULLS LAST, a.title_ref
         LIMIT 25
    """, (client_code, case_file, case_file), default=[])

    cur.close()
    conn.close()

    # --- Assemble one display row per matter, bucketed. ---
    rows: list[dict] = []
    for m in matters:
        mc = m["matter_code"]
        s = surf_by_matter.get(mc)
        next_event = m.get("next_event")
        if s and s.get("due_date") is not None:
            due = s["due_date"]
            # days_out from the snapshot may be stale (computed at as_of); recompute vs today.
            days_out = (due - today).days
            bucket = _bucket_for(days_out)
            # BLOCKER 1 guard: reject an internal-shorthand surfaced label (falls back to
            # next_event / current_stage) so a client never sees pipeline scratch as a label.
            label = _safe_label(s.get("label"), next_event, m.get("current_stage"))
        elif m.get("next_deadline") is not None:
            due = m["next_deadline"]
            days_out = (due - today).days
            bucket = _bucket_for(days_out)
            label = _safe_label(None, next_event, m.get("current_stage"))
        else:
            due = None
            days_out = None
            bucket = "NEEDS-A-DATE"
            label = _safe_label(None, next_event, m.get("current_stage"))

        # BLOCKER 2: surfaced_deadlines.label is often a bare stage string that strips the
        # [HUMAN VERIFY]/est caveat the matter's next_event carries on the date. The date is
        # estimated if EITHER the surfaced label OR the matter's next_event is tagged — flag
        # it regardless of which label source wins, so a client never sees an inferred ARTA
        # date (e.g. 2026-09-14) as a hard, court-confirmed deadline.
        estimated = due is not None and _has_tag(next_event, s.get("label") if s else None)

        # PROJECTION (A32): every client-visible field goes THROUGH client_ontology —
        # a clean plain-language phrase, never the raw internal field. `label` (the raw
        # next-action prose full of gmail#/CTN/§/[OPERATOR-ATTESTED]) is replaced by the
        # stage-derived / fully-sanitized client_next_step; forum/docket collapse to a
        # plain venue; matter_code is DROPPED from the client view entirely.
        rows.append({
            "matter_code": mc,
            "title": co.friendly_title(m.get("title"), mc),
            "kind": co.client_matter_kind(m.get("matter_type"), mc),
            "stage": co.client_stage(m.get("current_stage"), m.get("status")),
            "due": due,
            "days_out": days_out,
            "bucket": bucket,
            # clean next step: stage template, or fully-sanitized next_event prose.
            "next_step": co.client_next_step(m.get("current_stage"), next_event, mc),
            # honesty preserved in plain words: a short pill + a full sentence.
            "confidence_badge": (co.client_confidence_badge(next_event, s.get("label") if s else None)
                                 if estimated else None),
            "confidence_note": (co.client_confidence(next_event, s.get("label") if s else None)
                                if estimated else None),
            "estimated": estimated,
            # plain venue ONLY (lead venue, humanized) — no "/"-mashup, no docket/CTN.
            # Venue comes from forum/court_or_agency ONLY; matter_type is the KIND field
            # (rendered separately) and must NOT be fed to client_forum (it's not a venue,
            # and doing so logs a spurious unmapped forum for kind values like 'business').
            "venue": co.client_forum(m.get("forum"), m.get("court_or_agency")),
            "no_date_ok": _is_no_date_ok(m.get("current_stage")),
        })

    # Sort: by bucket order, then soonest due first.
    def _sort_key(r):
        bi = _BUCKET_ORDER.index(r["bucket"]) if r["bucket"] in _BUCKET_ORDER else 99
        d = r["days_out"] if r["days_out"] is not None else 10 ** 6
        return (bi, d)

    rows.sort(key=_sort_key)

    # --- Top-line counts. ---
    counts = {b: 0 for b in _BUCKET_ORDER}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    action_now = counts["OVERDUE"] + counts["THIS WEEK"]

    # --- Testimony-target banner (Aug 12). ---
    # NOT a court setting: CV-26360 has no court hearing notice on file (next_deadline NULL,
    # old Aug-1 pre-trial DISCREDITED). Labelled an operator planning target + carries the
    # caveat verbatim so a client cannot read it as a confirmed hearing (BLOCKER 1).
    ns_days = (NORTH_STAR_DATE - today).days
    if ns_days >= 0:
        ns_when = f"in {ns_days} days" if ns_days else "today"
    else:
        ns_when = f"{-ns_days} days ago"
    # Always warn-tone (never the red "hard deadline" colour) — it's a planning target.
    show_ns = any(r["matter_code"] == "MWK-CV26360" for r in rows)
    ns_banner = (
        f'<div class="alert alert-warn">Target date (operator-set, not a court setting) — '
        f'{NORTH_STAR_DATE} ({ns_when}): {_esc(NORTH_STAR_TXT)}</div>'
        if show_ns else ""
    )

    # --- Deadline cards by bucket (lead with this). ---
    bucket_blocks = []
    for b in _BUCKET_ORDER:
        brows = [r for r in rows if r["bucket"] == b]
        if not brows:
            continue
        trs = []
        for r in brows:
            badge = _BUCKET_BADGE.get(b, "badge-off")
            when = _countdown(r["days_out"])
            # BLOCKER 2 / honesty: an estimated date is shown as estimated — but in PLAIN
            # words via the projection, never with a raw §4B tag and never "(est)" jargon.
            est = r.get("estimated")
            due_txt = _esc(co.friendly_date(r["due"])) if r["due"] else "—"
            when_badge = f"<span class='badge {badge}'>{_esc(when)}</span>"
            # confidence pill/note come from client_confidence_badge/client_confidence —
            # plain language, raw [OPERATOR-ATTESTED]/[HUMAN VERIFY] tags never render.
            cb = r.get("confidence_badge")
            est_badge = (f' <span class="badge badge-warn">{_esc(cb)}</span>' if cb else "")
            # The next step is ALREADY clean+bounded (stage template or sanitized prose);
            # no raw-label truncation needed — projection guarantees no internal token.
            next_step = r.get("next_step") or "—"
            cnote = r.get("confidence_note")
            note = ""
            if b == "NEEDS-A-DATE" and r["no_date_ok"]:
                note = ' <span class="badge badge-off">advisory — no deadline expected</span>'
            elif b == "NEEDS-A-DATE":
                note = ' <span class="badge badge-warn">awaiting a confirmed date</span>'
            # plain venue + "what this is" subline — matter_code and docket DROPPED.
            sub_bits = [b_ for b_ in (r.get("kind"), r.get("venue")) if b_]
            subline = (" · ".join(_esc(x) for x in sub_bits)) if sub_bits else ""
            mdurl = _esc(matter_detail_url(r["matter_code"]))
            trs.append(
                f"<tr><td>{when_badge}</td>"
                f"<td>{due_txt}</td>"
                f"<td><a href='{mdurl}'><strong>{_esc(r['title'] or r['matter_code'])}</strong></a>"
                f"{('<div class=\"muted\" style=\"font-size:12px\">' + subline + '</div>') if subline else ''}</td>"
                f"<td>{_esc(next_step)}{est_badge}{note}"
                f"{('<div class=\"muted\" style=\"font-size:12px\">' + _esc(cnote) + '</div>') if cnote else ''}</td></tr>"
            )
        bucket_blocks.append(
            f'<div class="section-title">{_esc(b)} '
            f'<span class="muted">({len(brows)})</span></div>'
            f'<div class="card"><table>'
            f'<tr><th>Countdown</th><th>Due</th><th>Matter</th><th>Next action</th></tr>'
            f'{"".join(trs)}</table></div>'
        )

    if not bucket_blocks:
        bucket_blocks.append('<div class="card"><p class="empty">No active matters for this client.</p></div>')

    # Honest empty/quiet-state framing: a client whose matters are ALL awaiting a
    # confirmed date (Paracale-001 today) must NOT read as broken or empty. Lead
    # with a positive, TRUE statement — we're tracking N matters; dates appear as
    # they're confirmed. Never fabricates a date to fill the space.
    dated = counts["OVERDUE"] + counts["THIS WEEK"] + counts["THIS MONTH"] + counts["UPCOMING"]
    quiet_banner = ""
    if rows and dated == 0:
        n = len(rows)
        quiet_banner = (
            f'<div class="alert alert-ok">We are tracking {n} '
            f'matter{"s" if n != 1 else ""} for you. Confirmed deadlines will '
            f'appear here as soon as a court or agency sets them — nothing is '
            f'overdue right now.</div>'
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stat_cards = "".join([
        _stat_card("Needs action now", action_now, "overdue + this week"),
        _stat_card("This month", counts["THIS MONTH"], "coming up"),
        _stat_card("Active matters", len(rows)),
        _stat_card("Awaiting a date", counts["NEEDS-A-DATE"], "shown honestly"),
    ])

    # --- Deliverables card (bound-PDF dossiers), served via the public /files/c
    # doc proxy so the client can actually GET the artifact. Only rendered when a
    # real, servable deliverable exists — no invented links. ---
    deliverable_block = ""
    if deliverables:
        drows = []
        for d in deliverables:
            dt = _esc(co.friendly_date(d["doc_date"])) if d.get("doc_date") else ""
            nm = _esc(_client_doc_name((d.get("name") or "Deliverable")[:110],
                                       d.get("classification")))
            durl = _esc(doc_url(int(d["id"])))
            # drop the internal doc#NNN ref from the client view — a plain "prepared <date>"
            # line only (the projection carries no internal identifier to the client HTML).
            drows.append(
                f"<tr><td><a href='{durl}'>{nm}</a>"
                f"<div class='muted' style='font-size:12px'>"
                f"{('prepared ' + dt) if dt else 'counsel deliverable'}</div></td>"
                f"<td><a class='badge badge-ok' href='{durl}'>view / download</a></td></tr>"
            )
        deliverable_block = (
            '<div class="section-title">Your deliverables '
            f'<span class="muted">({len(deliverables)})</span></div>'
            '<div class="card"><table>'
            '<tr><th>Document</th><th>Get it</th></tr>'
            f'{"".join(drows)}</table></div>'
        )
    else:
        # Honest empty state — never invent a document to fill the space.
        deliverable_block = (
            '<div class="section-title">Your deliverables</div>'
            '<div class="card"><p class="empty">No bound dossiers yet — we prepare '
            'these on request and as your matters progress. When one is ready it '
            'appears here as a single download.</p></div>'
        )

    # Per-matter document lists route through the injected builder: token-scoped
    # (/client/<token>/m/<code>) in client chrome, /files/c/m/ only for the ops view.
    # LINK TEXT is the friendly matter title (projected) — the raw matter_code is only
    # ever in the href path segment (a token-scoped route id), never client-visible text.
    doc_links = " · ".join(
        f"<a href='{_esc(matter_url(r['matter_code']))}'>{_esc(r['title'] or 'Matter')}</a>"
        for r in rows
    )
    docs_block = (
        '<div class="section-title">Documents by matter</div>'
        f'<div class="card"><p class="muted" style="font-size:13px">Open the source '
        f'documents on file for any matter:</p><p>{doc_links}</p></div>'
        if doc_links else ""
    )

    # --- Titles / property readiness (APP surface of the property spine) ---
    titles_block = _render_client_titles(title_rows)

    body = f"""
<h1>{_esc(client.get('name') or client_code)}</h1>
<p class="lead">Your matters and deadlines · Updated {_esc(co.friendly_today())}</p>
{ns_banner}
{quiet_banner}
<div class="grid grid-4" style="margin-bottom:8px">{stat_cards}</div>
{titles_block}
{''.join(bucket_blocks)}
{deliverable_block}
{docs_block}
<p class="muted" style="margin-top:16px;font-size:12px">
  Dates and stages are read from the grounded record. Anything not yet confirmed against
  the source document is shown with a plain "estimated" or "awaiting confirmation" note —
  it is never presented as settled fact. Matters awaiting a confirmed date are listed
  openly rather than hidden. Title preparation status, when shown, is the same operational
  record your team and Leo use — projected into plain language for you.</p>
"""
    title = f"{client.get('name') or client_code} — portal"
    return title, body


# Axis grades → short plain phrases (never "solid/partial/thin" ops jargon alone).
_AXIS_PLAIN = {
    "solid": "in good shape",
    "partial": "partly known",
    "thin": "needs work",
    "unknown": "not yet assessed",
}
_WEAK_PLAIN = {
    "documents": "documents",
    "status": "legal status",
    "occupants": "who is on the land",
    "ownership": "ownership record",
    "title_issues": "title issues",
    "mapping": "mapping / boundaries",
}


def _render_client_titles(title_rows: list) -> str:
    """Client-facing property titles block. Empty → silent (legal-only clients)."""
    if not title_rows:
        return ""
    trs = []
    for t in title_rows:
        name = (t.get("title_ref") or t.get("label") or "Property").strip()
        score = t.get("readiness_score")
        if score is not None:
            pct = int(round(float(score) * 100))
            if pct >= 70:
                badge = f'<span class="badge badge-ok">{pct}% ready</span>'
            elif pct >= 40:
                badge = f'<span class="badge badge-warn">{pct}% ready</span>'
            else:
                badge = f'<span class="badge badge-bad">{pct}% ready</span>'
        else:
            badge = '<span class="badge badge-off">not yet scored</span>'
        weak = _WEAK_PLAIN.get((t.get("weakest_axis") or "").strip(), "")
        focus = ("Focus: " + weak) if weak else "—"
        # Prefer a gentle next-step line; strip internal codes if projection not applied.
        nxt = (t.get("next_prep_action") or "").strip()
        if nxt and len(nxt) > 160:
            nxt = nxt[:157] + "…"
        # Hide lines that look like pure operator engine codes
        if nxt and any(tok in nxt.lower() for tok in ("precond_", "asset_code", "null")):
            nxt = ""
        status = (t.get("title_status") or "").replace("_", " ").strip()
        poss = (t.get("possession") or "").replace("_", " ").strip()
        meta_bits = [b for b in (status, poss) if b]
        meta = " · ".join(meta_bits)
        axes_bits = []
        for key, label in (
            ("documents", "Docs"),
            ("status_axis", "Status"),
            ("occupants", "Occupants"),
            ("ownership", "Ownership"),
            ("title_issues", "Title"),
            ("mapping", "Map"),
        ):
            g = (t.get(key) or "unknown").lower()
            axes_bits.append(f"{label}: {_AXIS_PLAIN.get(g, g)}")
        axes_line = " · ".join(axes_bits)
        meta_html = ""
        if meta:
            meta_html = (
                '<div class="muted" style="font-size:12px">'
                + _esc(meta) + "</div>"
            )
        nxt_html = ""
        if nxt:
            nxt_html = (
                '<div class="muted" style="font-size:12px">'
                + _esc(nxt) + "</div>"
            )
        trs.append(
            "<tr><td><strong>" + _esc(name) + "</strong>"
            + meta_html
            + "</td><td>" + badge + "</td>"
            + "<td>" + _esc(focus)
            + nxt_html
            + '<div class="muted" style="font-size:11px;margin-top:4px">'
            + _esc(axes_line) + "</div>"
            + "</td></tr>"
        )
    return (
        f'<div class="section-title">Your titles '
        f'<span class="muted">({len(title_rows)})</span></div>'
        f'<div class="card"><p class="muted" style="font-size:13px;margin:0 0 10px">'
        f'Preparation status for each title we are working — documents, status, occupants, '
        f'ownership, title issues, and mapping. Updated automatically; ask us (or Leo) for detail.</p>'
        f'<table><tr><th>Title</th><th>Readiness</th><th>What needs attention</th></tr>'
        f'{"".join(trs)}</table></div>'
    )


def render_matter_detail(client_code: str, matter_code: str,
                         link_builder=None) -> tuple[str, str]:
    """Build (page_title, body_html) for ONE matter's full picture — the token-scoped
    drill-down reached from a matter row on the portal home.

    Shows: the matter's title, forum/court + docket, current stage, the deadline +
    human next-action (via _safe_label), a chronological timeline built ONLY from
    grounded case_stage_transitions rows for THIS matter, and its documents as
    token-scoped download links.

    SEPARATION (defence-in-depth): the caller (client_access.client_matter_detail)
    already ownership-checks matter ∈ client and 404s otherwise. This function
    ADDITIONALLY re-verifies the (matter_code, client_code) pair against matters
    before reading anything, and aborts 404 on mismatch — so the trust boundary
    holds even if this were ever called from a new path. Every query filters on the
    validated client_code / matter_code; no client-supplied value widens scope.

    NO hallucination: dates come from matters.next_deadline / the latest
    surfaced_deadlines snapshot only; [HUMAN VERIFY]/[OPERATOR-ATTESTED] caveats are
    preserved via _safe_label + the estimated flag; an absent timeline/deadline/doc
    is shown honestly, never filled.

    link_builder: same (doc_url, matter_url, matter_detail_url) triple contract as
    render_client_portal. In client chrome the doc links are token-scoped
    (/client/<token>/doc/<id>) — NO bare /files/c/ reaches the HTML (CRITICAL-1).
    """
    doc_url, matter_url, _matter_detail_url = (
        link_builder if link_builder
        else (_default_doc_url, _default_matter_url, _default_matter_detail_url))
    today = date.today()
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # --- Re-verify matter ∈ client on the VALIDATED FK before reading anything. ---
    m = _safe_fetch(cur, conn, """
        SELECT matter_code, title, status, current_stage, next_deadline, next_event,
               matter_type, docket_number, court_or_agency, forum, date_opened
          FROM matters
         WHERE matter_code = %s AND client_code = %s
           -- drill-down surface == listed surface: never expose a triage stub or a
           -- closed/archived matter the portal home deliberately hides (security F1).
           AND matter_code NOT LIKE 'AUTO-%%'
           AND COALESCE(status,'') NOT IN ('closed', 'archived')
    """, (matter_code, client_code), default=None, one=True)
    if not m:
        cur.close()
        conn.close()
        abort(404)

    # Client name for the chrome header.
    cli = _safe_fetch(cur, conn,
                      "SELECT name FROM clients WHERE client_code = %s",
                      (client_code,), default=None, one=True)
    client_name = (cli or {}).get("name") if cli else None

    # --- Latest grounded surfaced-deadline snapshot for THIS matter only. ---
    s = _safe_fetch(cur, conn, """
        SELECT DISTINCT ON (matter_code)
               matter_code, due_date, bucket, days_out, label, kind, as_of
          FROM surfaced_deadlines
         WHERE matter_code = %s
         ORDER BY matter_code, as_of DESC, (bucket = 'OVERDUE') DESC, due_date ASC
    """, (matter_code,), default=None, one=True)

    # --- Grounded timeline: stage transitions for THIS matter (never re-derived). ---
    timeline = _safe_fetch(cur, conn, """
        SELECT to_stage, from_stage, transitioned_at, notes, transition_doc_id,
               detected_by
          FROM case_stage_transitions
         WHERE matter_code = %s
         ORDER BY transitioned_at ASC
    """, (matter_code,), default=[])

    # --- Documents linked to THIS matter (token-scoped links, ownership-checked at
    # the route level; the /client/<token>/doc/<id> route re-checks per doc). ---
    docs = _safe_fetch(cur, conn, """
        SELECT d.id,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename, 'Document') AS name,
               d.doc_date, d.classification,
               (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL) AS servable
          FROM documents d
          JOIN document_matter_links l ON l.doc_id = d.id
         WHERE l.matter_code = %s
           -- evidence-grade = RECEIVED, not draft: never hand a client a draft as a
           -- document "on file" (matches the deliverables-card discipline).
           AND COALESCE(d.classification,'')                                NOT ILIKE '%%draft%%'
           AND COALESCE(NULLIF(d.smart_filename,''), d.original_filename,'') NOT ILIKE '%%draft%%'
           -- SEPARATION (defence-in-depth, deploy_674): never render a document whose OWN
           -- case_file is a DIFFERENT real client than this matter's client, even if a stray
           -- document_matter_links row points here. Mirrors the deliverables-card discipline
           -- above + client_dependability's cross_client_doc check, so the leak is structurally
           -- impossible rather than merely absent. Blank / 'Owner' / own-client docs pass; a
           -- non-client scoping tag passes; only real OTHER clients (MWK/Paracale/NIBDC) are cut.
           AND (
                COALESCE(d.case_file,'') IN ('', 'Owner', %s)
                OR d.case_file NOT IN (
                     SELECT client_code FROM clients
                      WHERE COALESCE(client_code,'') NOT IN ('', 'Owner', 'Archive', 'PENDING_TRIAGE')
                )
           )
         ORDER BY d.doc_date ASC NULLS LAST, d.id ASC
    """, (matter_code, client_code), default=[])

    cur.close()
    conn.close()

    next_event = m.get("next_event")
    # --- Deadline + next action (same grounded logic as the portal row). ---
    if s and s.get("due_date") is not None:
        due = s["due_date"]
        days_out = (due - today).days
        bucket = _bucket_for(days_out)
    elif m.get("next_deadline") is not None:
        due = m["next_deadline"]
        days_out = (due - today).days
        bucket = _bucket_for(days_out)
    else:
        due = None
        days_out = None
        bucket = "NEEDS-A-DATE"
    estimated = due is not None and _has_tag(next_event, s.get("label") if s else None)
    # PROJECTION (A32): the next action is the stage-derived / fully-sanitized clean step —
    # never the raw next_event prose (no gmail#/CTN/§/doc#/[OPERATOR-ATTESTED] reaches here).
    next_step = co.client_next_step(m.get("current_stage"), next_event, matter_code)
    # honesty: a plain confidence pill + sentence when the date is not court-confirmed.
    confidence_badge = (co.client_confidence_badge(next_event, s.get("label") if s else None)
                        if estimated else None)
    confidence_note = (co.client_confidence(next_event, s.get("label") if s else None)
                       if estimated else None)

    badge = _BUCKET_BADGE.get(bucket, "badge-off")
    when = _countdown(days_out)
    when_badge = f"<span class='badge {badge}'>{_esc(when)}</span>"
    if due is not None:
        due_txt = _esc(co.friendly_date(due))
    else:
        due_txt = "awaiting a confirmed date"

    # Plain venue + "what this is" — matter_code and docket DROPPED from the client view.
    # Venue from forum/court_or_agency ONLY (matter_type is the KIND field, rendered
    # separately; feeding it to client_forum would log a spurious unmapped forum).
    venue = co.client_forum(m.get("forum"), m.get("court_or_agency"))
    kind = co.client_matter_kind(m.get("matter_type"), matter_code)
    stage = co.client_stage(m.get("current_stage"), m.get("status"))

    # --- Facts card (what this is / venue / status). No internal code or docket. ---
    fact_rows = []
    if kind:
        fact_rows.append(f"<tr><th>What this is</th><td>{_esc(kind)}</td></tr>")
    if venue:
        fact_rows.append(f"<tr><th>Where</th><td>{_esc(venue)}</td></tr>")
    fact_rows.append(f"<tr><th>Status</th><td>{_esc(stage)}</td></tr>")
    if m.get("date_opened"):
        fact_rows.append(f"<tr><th>Opened</th><td>{_esc(co.friendly_date(m['date_opened']))}</td></tr>")
    facts_block = (
        '<div class="card"><table>' + "".join(fact_rows) + "</table></div>"
    )

    # --- Deadline / next-action card. ---
    est_note = (f' <span class="badge badge-warn">{_esc(confidence_badge)}</span>'
                if confidence_badge else "")
    conf_line = (f'<div class="muted" style="font-size:12px">{_esc(confidence_note)}</div>'
                 if confidence_note else "")
    deadline_block = (
        '<div class="section-title">Deadline &amp; next action</div>'
        '<div class="card"><table>'
        f'<tr><th>Countdown</th><td>{when_badge}</td></tr>'
        f'<tr><th>Due</th><td>{due_txt}{est_note}</td></tr>'
        f'<tr><th>Next action</th><td>{_esc(next_step)}{conf_line}</td></tr>'
        '</table></div>'
    )

    # --- Timeline (grounded only). Each entry that carries a source doc links via
    # the token-scoped doc route — the doc route re-checks ownership per id. ---
    if timeline:
        tl_rows = []
        for ev in timeline:
            when_ts = ev.get("transitioned_at")
            when_disp = _esc(co.friendly_date(str(when_ts)[:10])) if when_ts else "—"
            # PROJECTION (A32): stage codes are snake_case internal values — render the
            # plain client STATUS phrase for both ends of the move, never the raw code.
            to_disp = _esc(co.client_stage(ev.get("to_stage")))
            frm = ev.get("from_stage")
            move = (f"{_esc(co.client_stage(frm))} &rarr; {to_disp}" if frm else to_disp)
            note = ev.get("notes")
            # notes is the stage classifier's INTERNAL reasoning string. Keep the existing
            # internal-fragment guard, THEN additionally run it through the projection's
            # sanitizer so any surviving raw token (gmail#/CTN/§/doc#/matter code / §4B tag)
            # is stripped; if nothing clean survives, the note is dropped (shown as nothing
            # rather than as internal scratch). No raw tag/code can reach the client.
            if note and _is_internal_fragment(note):
                note = None
            note_clean = co._sanitize_next_event(note) if note else ""
            note_disp = _esc(note_clean) if note_clean else ""
            note_html = (f"<div class='muted' style='font-size:12px'>{note_disp}</div>"
                         if note_disp else "")
            doc_link = ""
            did = ev.get("transition_doc_id")
            if did:
                # Route through the ownership-checked doc route (token-scoped in
                # client chrome). NO bare /files/c/.
                du = _esc(doc_url(int(did)))
                doc_link = f" <a href='{du}'>source doc</a>"
            tl_rows.append(
                f"<tr><td style='white-space:nowrap'>{when_disp}</td>"
                f"<td><strong>{move}</strong>{note_html}{doc_link}</td></tr>"
            )
        timeline_block = (
            '<div class="section-title">Timeline '
            f'<span class="muted">({len(timeline)})</span></div>'
            '<div class="card"><table>'
            '<tr><th>Date</th><th>What happened</th></tr>'
            f'{"".join(tl_rows)}</table></div>'
        )
    else:
        timeline_block = (
            '<div class="section-title">Timeline</div>'
            '<div class="card"><p class="empty">No dated milestones recorded yet for '
            'this matter. As steps are confirmed against source documents they will '
            'appear here in order.</p></div>'
        )

    # --- Documents on file (token-scoped links). ---
    if docs:
        drows = []
        avail = 0
        for d in docs:
            # _client_doc_name strips control-tracking (CTN/SL-/CL-) + code/§ jargon from the
            # raw filename and defers to the typed classification when thin; the raw doc#NNN
            # identifier is DROPPED from the client view (kept only in the href route id).
            nm = _esc(_client_doc_name((d.get("name") or "Document")[:90],
                                       d.get("classification")))
            dt = _esc(co.friendly_date(d["doc_date"])) if d.get("doc_date") else ""
            cls = _esc((d.get("classification") or "")[:40])
            if d.get("servable"):
                du = _esc(doc_url(int(d["id"])))
                link = f"<a href='{du}'>view / download</a>"
                avail += 1
            else:
                link = '<span class="muted">no scan on file yet</span>'
            cls_html = (f"<div class='muted' style='font-size:12px'>{cls}</div>" if cls else "")
            drows.append(
                f"<tr><td style='white-space:nowrap'>{dt}</td>"
                f"<td>{nm}{cls_html}</td>"
                f"<td>{link}</td></tr>"
            )
        docs_block = (
            '<div class="section-title">Documents on file '
            f'<span class="muted">({len(docs)} · {avail} downloadable)</span></div>'
            '<div class="card"><table>'
            '<tr><th>Date</th><th>Document</th><th>File</th></tr>'
            f'{"".join(drows)}</table></div>'
        )
    else:
        docs_block = (
            '<div class="section-title">Documents on file</div>'
            '<div class="card"><p class="empty">No documents are linked to this '
            'matter yet.</p></div>'
        )

    body = f"""
<h1>{_esc(co.friendly_title(m.get('title'), matter_code))}</h1>
<p class="lead">One matter in your workspace · Updated {_esc(co.friendly_today())}</p>
{facts_block}
{deadline_block}
{timeline_block}
{docs_block}
<p class="muted" style="margin-top:16px;font-size:12px">
  Dates and stages are read from the grounded record. Anything not yet confirmed against
  the source document is shown with a plain "estimated" or "awaiting confirmation" note —
  it is never presented as settled fact. A matter awaiting a confirmed date is shown
  openly rather than hidden.</p>
"""
    title = f"{co.friendly_title(m.get('title'), matter_code)} — {client_name or client_code}"
    return title, body
