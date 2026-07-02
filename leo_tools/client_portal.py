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


def _truncate_keep_tags(text: str, cap: int = 200) -> str:
    """Cap label length WITHOUT severing a §4B caveat tag. If a tag sits past the cut,
    append it after an ellipsis so the caveat always survives length-capping (BLOCKER 3)."""
    text = text or ""
    if len(text) <= cap:
        return text
    head = text[:cap]
    kept = [m.group(0) for m in _TAG_RE.finditer(text) if m.start() >= cap]
    # de-dup while preserving order
    seen, extra = set(), []
    for t in kept:
        if t not in seen:
            seen.add(t)
            extra.append(t)
    suffix = (" … " + " ".join(extra)) if extra else "…"
    return head + suffix


def _client_layout(title: str, body: str) -> str:
    """Client-facing chrome — deliberately NO ops nav.

    A retainer client must never see (or be tempted to click) the internal
    cockpit links (/ops/cases, /ops/clients, /ops/spend, …). The ops _layout()
    renders that whole nav bar; this one renders ONLY the LandTek brand + the
    client's own page. Same CSS (one style), zero pivot surface.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} — LandTek</title>{CSS}
<style>
  /* Client chrome: brand only, no nav, comfortable on a phone. */
  .topbar {{ justify-content:space-between; }}
  .wrap {{ max-width:820px; }}
  @media (max-width:640px) {{
    .grid-4 {{ grid-template-columns:repeat(2,1fr); }}
    table {{ font-size:12px; }}
    th,td {{ padding:6px 7px; }}
    h1 {{ font-size:19px; }}
  }}
</style></head><body>
<header class="topbar">
  <div class="brand">LandTek <span class="muted">client portal</span></div>
  <div class="ts">{now}</div>
</header>
<main class="wrap">{body}</main>
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


def render_client_portal(client_code: str, link_builder=None) -> tuple[str, str]:
    """Build (page_title, body_html) for ONE client's portal, led by the
    deadline countdown. Pure content — the caller wraps it in the appropriate
    chrome (_layout for internal /ops, _client_layout for the client link).

    link_builder: optional (doc_url_fn, matter_url_fn) pair. When the portal is
    rendered in CLIENT chrome (reached via /client/<token>), the caller passes a
    builder that emits TOKEN-SCOPED, ownership-checked URLs
    (/client/<token>/doc/<id>, /client/<token>/m/<code>). When None (the internal
    /ops/portal view, which is ops-gated), we fall back to the /files/c proxy.
    CRITICAL-1: no bare /files/c/ string may reach the client HTML — that is
    enforced by always routing client links through the injected builder.

    Separation is enforced HERE: every row filters on matters.client_code (the
    validated FK), never case_file. A 404 is raised for an unknown client_code
    so both callers behave identically."""
    doc_url, matter_url = (link_builder if link_builder
                           else (_default_doc_url, _default_matter_url))
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
               next_deadline, next_event, matter_type, docket_number, court_or_agency
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

        rows.append({
            "matter_code": mc,
            "title": m.get("title"),
            "stage": m.get("current_stage") or m.get("status") or "—",
            "due": due,
            "days_out": days_out,
            "bucket": bucket,
            "label": label,
            "estimated": estimated,
            "forum": m.get("court_or_agency") or m.get("matter_type") or "",
            "docket": m.get("docket_number") or "",
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
            # BLOCKER 2: an estimated date is shown as estimated, never as a hard date —
            # both on the date cell and the countdown.
            est = r.get("estimated")
            due_txt = (_esc(str(r["due"])) + (" (est)" if est else "")) if r["due"] else "—"
            when_badge = f"<span class='badge {badge}'>{_esc(when)}</span>"
            est_badge = (' <span class="badge badge-warn">estimated · awaiting confirmation</span>'
                         if est else "")
            # BLOCKER 3: cap length WITHOUT severing a §4B caveat tag (preserve it after the cut).
            label = _truncate_keep_tags(r["label"] or "")
            note = ""
            if b == "NEEDS-A-DATE" and r["no_date_ok"]:
                note = ' <span class="badge badge-off">advisory — no deadline expected</span>'
            elif b == "NEEDS-A-DATE":
                note = ' <span class="badge badge-warn">awaiting a confirmed date</span>'
            trs.append(
                f"<tr><td>{when_badge}</td>"
                f"<td>{due_txt}</td>"
                f"<td><strong>{_esc(r['title'] or r['matter_code'])}</strong>"
                f"<div class='muted' style='font-size:12px'><code>{_esc(r['matter_code'])}</code>"
                f"{(' · ' + _esc(r['forum'])) if r['forum'] else ''}"
                f"{(' · ' + _esc(r['docket'])) if r['docket'] else ''}</div></td>"
                f"<td>{_esc(label)}{est_badge}{note}</td></tr>"
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
            dt = _esc(str(d["doc_date"])) if d.get("doc_date") else ""
            nm = _esc((d.get("name") or "Deliverable")[:110])
            durl = _esc(doc_url(int(d["id"])))
            drows.append(
                f"<tr><td><a href='{durl}'>{nm}</a>"
                f"<div class='muted' style='font-size:12px'>"
                f"{('as of ' + dt) if dt else 'counsel deliverable'} · doc#{int(d['id'])}</div></td>"
                f"<td><a class='badge badge-ok' href='{durl}'>view / download</a></td></tr>"
            )
        deliverable_block = (
            '<div class="section-title">Your deliverables '
            f'<span class="muted">({len(deliverables)})</span></div>'
            '<div class="card"><table>'
            '<tr><th>Document</th><th>Get it</th></tr>'
            f'{"".join(drows)}</table></div>'
        )

    # Per-matter document lists route through the injected builder: token-scoped
    # (/client/<token>/m/<code>) in client chrome, /files/c/m/ only for the ops view.
    doc_links = " · ".join(
        f"<a href='{_esc(matter_url(r['matter_code']))}'>{_esc(r['matter_code'])}</a>"
        for r in rows
    )
    docs_block = (
        '<div class="section-title">Documents by matter</div>'
        f'<div class="card"><p class="muted" style="font-size:13px">Open the source '
        f'documents on file for any matter:</p><p>{doc_links}</p></div>'
        if doc_links else ""
    )

    body = f"""
<h1>{_esc(client.get('name') or client_code)}</h1>
<p class="lead">Your matters and deadlines · <code>{_esc(client_code)}</code>
  · as of {now}</p>
{ns_banner}
<div class="grid grid-4" style="margin-bottom:8px">{stat_cards}</div>
{''.join(bucket_blocks)}
{deliverable_block}
{docs_block}
<p class="muted" style="margin-top:16px;font-size:12px">
  Dates are read from the grounded deadline record (latest surface {_esc(str(today))}).
  Items marked <code>[HUMAN VERIFY]</code> or <code>[verify-img]</code> are still being
  confirmed against the source document and are shown with that caveat — they are not
  presented as settled fact. Matters awaiting a confirmed date are listed openly rather
  than hidden.</p>
"""
    title = f"{client.get('name') or client_code} — portal"
    return title, body
