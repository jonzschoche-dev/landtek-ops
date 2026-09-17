"""LandTek client app shell — Portfolio · Money · Chat.

Phone-first product face. Home reads ONLY a publish-safe title set
(portfolio_publish when present; else a conservative heuristic). Money reuses
transactions + thin client_billing/invoices. Chat uses client_app_messages
(never channel_messages — avoids leo_inbound dual-brain).

Routes (wired from client_access / client_portal):
  /client/<token>              → Home
  /client/<token>/money        → Accounting + billing
  /client/<token>/chat         → In-app chat (GET/POST)
  /client/<token>/cases        → legacy legal portal
  /client/<token>/map          → existing premium map
  /ops/portal/<code>/portfolio → ops preview (basic-auth)
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from typing import Any

try:
    from ops_dashboard import PG_DSN
except Exception:  # pragma: no cover — local preview
    PG_DSN = "postgresql://n8n:n8npassword@127.0.0.1:5432/n8n"

_esc = html.escape

# Title keys that are OCR trash / form serials / truncated — never client-visible.
_JUNK_TITLE_RE = re.compile(
    r"^(T-079|T-2010000|T-2021002|5226881|4770981)$"
    r"|^[0-9]{1,7}$"
    r"|^T-\d{1,4}$"
    r"|^ARP-",
    re.I,
)

# Registrant strings that are OCR field labels, not people.
_JUNK_REG_RE = re.compile(
    r"conjugal partnership|state the citizenship|unknown|^\?$|^—$|^-$",
    re.I,
)


def _db():
    import psycopg2
    return psycopg2.connect(PG_DSN)


def _case_file_for(cur, client_code: str) -> str:
    cur.execute(
        "SELECT COALESCE(NULLIF(case_file,''), client_code) AS cf FROM clients WHERE client_code=%s",
        (client_code,),
    )
    row = cur.fetchone()
    if not row:
        return client_code
    if isinstance(row, dict):
        return row.get("cf") or client_code
    return row[0] or client_code


def _publish_table_exists(cur) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name='portfolio_publish'"
    )
    return cur.fetchone() is not None


def _load_published_titles(cur, client_code: str, case_file: str) -> list[dict]:
    """Prefer portfolio_publish; else conservative heuristic over titles."""
    if _publish_table_exists(cur):
        cur.execute(
            """
            SELECT p.title_no AS tct_number,
                   COALESCE(NULLIF(p.display_registrant,''), t.registrant_canonical,
                            t.registrant_name_raw, '—') AS registrant,
                   COALESCE(NULLIF(p.lifecycle,''), t.lifecycle_status, t.status, 'unknown') AS lifecycle,
                   COALESCE(NULLIF(p.location,''), t.location, '') AS location,
                   COALESCE(p.area_sqm, t.area_sqm) AS area_sqm,
                   p.sort_order
              FROM portfolio_publish p
              LEFT JOIN titles t
                ON upper(t.tct_number) = upper(p.title_no)
               AND t.case_file = %s
             WHERE p.client_code = %s AND p.published IS TRUE
             ORDER BY p.sort_order NULLS LAST, p.title_no
            """,
            (case_file, client_code),
        )
        rows = cur.fetchall()
        if rows:
            return [dict(r) for r in rows]

    cur.execute(
        """
        SELECT t.tct_number,
               COALESCE(NULLIF(t.registrant_canonical,''), t.registrant_name_raw, '—') AS registrant,
               COALESCE(NULLIF(t.lifecycle_status,''), t.status, 'unknown') AS lifecycle,
               COALESCE(t.location, '') AS location,
               t.area_sqm,
               CASE
                 WHEN lower(COALESCE(t.lifecycle_status, t.status, '')) = 'active' THEN 0
                 WHEN lower(COALESCE(t.lifecycle_status, t.status, '')) IN ('contested','clouded') THEN 1
                 WHEN lower(COALESCE(t.lifecycle_status, t.status, '')) LIKE '%%cancel%%' THEN 3
                 ELSE 2
               END AS sort_order
          FROM titles t
         WHERE t.case_file = %s
           AND COALESCE(t.lifecycle_status, '') NOT IN ('not_a_title', 'not_mwk_heirs')
           AND lower(COALESCE(t.lifecycle_status, t.status, '')) NOT IN ('invalid', 'out_of_scope')
         ORDER BY sort_order, t.tct_number
        """,
        (case_file,),
    )
    out = []
    for r in cur.fetchall():
        d = dict(r)
        tno = (d.get("tct_number") or "").strip()
        reg = (d.get("registrant") or "").strip()
        if not tno or _JUNK_TITLE_RE.search(tno):
            continue
        if len(tno) < 4:
            continue
        if reg and _JUNK_REG_RE.search(reg):
            d["registrant"] = "—"
        # Prefer display form without double T- prefix noise later
        out.append(d)
    return out


def _tax_linked(cur, title_nos: list[str]) -> set[str]:
    if not title_nos:
        return set()
    cur.execute(
        "SELECT DISTINCT upper(title_no) AS tn FROM title_tax_links WHERE upper(title_no) = ANY(%s)",
        ([t.upper() for t in title_nos],),
    )
    out = set()
    for r in cur.fetchall():
        if isinstance(r, dict):
            out.add(r["tn"])
        else:
            out.add(r[0])
    return out


def _map_status(cur, client_code: str, title_nos: list[str]) -> dict[str, str]:
    """title_no upper → plotted|draft|awaiting|none"""
    if not title_nos:
        return {}
    cur.execute(
        """
        SELECT title_no, label, status, (geom_geojson IS NOT NULL) AS has_geom
          FROM map_parcels
         WHERE client_code = %s
        """,
        (client_code,),
    )
    by = {}
    uppers = {t.upper(): t for t in title_nos}
    for row in cur.fetchall():
        if isinstance(row, dict):
            title_no, label, status, has_geom = (
                row.get("title_no"), row.get("label"), row.get("status"), row.get("has_geom"),
            )
        else:
            title_no, label, status, has_geom = row
        keys = []
        if title_no:
            keys.append(str(title_no).upper())
        if label:
            for u in uppers:
                if u in str(label).upper() or u.replace("T-", "") in str(label).upper():
                    keys.append(u)
        for k in keys:
            if k not in uppers and k not in {x.upper() for x in title_nos}:
                for u in uppers:
                    if u.replace("T-", "") == k.replace("T-", ""):
                        k = u
                        break
            if has_geom and (status or "") in ("plotted", "draft", "live", "published"):
                by[k] = "plotted"
            elif has_geom:
                by[k] = by.get(k) or "plotted"
            elif (status or "") == "awaiting_plot":
                by[k] = by.get(k) or "awaiting"
            else:
                by[k] = by.get(k) or "awaiting"
    return by


def _attention_items(cur, client_code: str) -> list[dict]:
    """Active matters with real dates or honest undated — plain language only."""
    cur.execute(
        """
        SELECT matter_code, title, next_deadline, next_event, status, current_stage
          FROM matters
         WHERE client_code = %s
           AND matter_code NOT LIKE 'AUTO-%%'
           AND COALESCE(status, '') NOT IN ('closed', 'archived')
         ORDER BY next_deadline NULLS LAST, matter_code
         LIMIT 12
        """,
        (client_code,),
    )
    today = date.today()
    items = []
    for r in cur.fetchall():
        d = dict(r)
        due = d.get("next_deadline")
        if due is not None and hasattr(due, "isoformat"):
            days = (due - today).days
        else:
            days = None
        # Sanitize next_event for client: strip gmail# doc# CTN-heavy dumps
        ev = (d.get("next_event") or "").strip()
        ev = re.sub(r"\[.*?\]", "", ev)
        ev = re.sub(r"\bgmail#\d+\b", "", ev, flags=re.I)
        ev = re.sub(r"\bdoc#?\d+\b", "", ev, flags=re.I)
        ev = re.sub(r"\s{2,}", " ", ev).strip()
        if len(ev) > 140:
            ev = ev[:137] + "…"
        title = (d.get("title") or d.get("matter_code") or "Matter").strip()
        # Shorten ARTA legalese for chips
        if title.startswith("ARTA "):
            title = re.sub(r"\s*—\s*.*$", "", title)
            if len(title) > 48:
                title = title[:45] + "…"
        items.append(
            {
                "title": title,
                "days": days,
                "due": due.isoformat() if due else None,
                "event": ev,
                "matter_code": d.get("matter_code"),
            }
        )
    # Rank: overdue, soon, undated last
    def sk(it):
        if it["days"] is None:
            return (2, 9999)
        if it["days"] < 0:
            return (0, it["days"])
        return (1, it["days"])

    items.sort(key=sk)
    return items[:6]


def load_portfolio(client_code: str) -> dict[str, Any]:
    import psycopg2.extras
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT client_code, name, case_file FROM clients WHERE client_code=%s",
            (client_code,),
        )
        client = cur.fetchone()
        if not client:
            return {"ok": False, "error": "unknown_client"}
        case_file = (client.get("case_file") or client_code).strip()
        titles = _load_published_titles(cur, client_code, case_file)
        nos = [t["tct_number"] for t in titles]
        tax = _tax_linked(cur, nos)
        maps = _map_status(cur, client_code, nos)
        enriched = []
        for t in titles:
            u = t["tct_number"].upper()
            life = (t.get("lifecycle") or "unknown").lower()
            if "cancel" in life or life == "superseded":
                life_ui = "cancelled"
            elif life in ("contested", "clouded"):
                life_ui = life
            elif life == "active":
                life_ui = "active"
            else:
                life_ui = "review"
            tax_s = "linked" if u in tax else "pending"
            map_s = maps.get(u) or maps.get(u.replace("T-", "T-")) or "none"
            # try bare number match for map
            if map_s == "none":
                bare = u.replace("T-", "")
                for k, v in maps.items():
                    if k.replace("T-", "") == bare:
                        map_s = v
                        break
            area = t.get("area_sqm")
            try:
                area_s = f"{float(area):,.0f} sqm" if area is not None else ""
            except (TypeError, ValueError):
                area_s = ""
            loc = (t.get("location") or "").strip()
            if "relationship to" in loc.lower() or "not yet verified" in loc.lower():
                loc = re.split(r"\(|relationship", loc, maxsplit=1)[0].strip(" ,")
            enriched.append(
                {
                    "tct": t["tct_number"],
                    "display": _display_tct(t["tct_number"]),
                    "registrant": t.get("registrant") or "—",
                    "lifecycle": life_ui,
                    "location": loc,
                    "area": area_s,
                    "tax": tax_s,
                    "map": map_s if map_s != "none" else "pending",
                }
            )
        attention = _attention_items(cur, client_code)
        living = [e for e in enriched if e["lifecycle"] == "active"]
        # Stats from published set
        n = len(enriched)
        n_living = len(living) or sum(1 for e in enriched if e["lifecycle"] not in ("cancelled",))
        n_map = sum(1 for e in enriched if e["map"] == "plotted")
        n_tax_gap = sum(1 for e in enriched if e["tax"] != "linked" and e["lifecycle"] == "active")
        n_actions = sum(
            1
            for a in attention
            if a["days"] is not None and a["days"] <= 31
        )
        return {
            "ok": True,
            "client_code": client_code,
            "client_name": client.get("name") or client_code,
            "as_of": date.today().isoformat(),
            "titles": enriched,
            "attention": attention,
            "stats": {
                "titles": n_living if n_living else n,
                "on_map": n_map,
                "need_tax": n_tax_gap,
                "actions": n_actions,
            },
            "publish_mode": "table" if _publish_table_exists(cur) else "heuristic",
        }
    finally:
        cur.close()
        conn.close()


def _display_tct(tct: str) -> str:
    t = (tct or "").strip()
    if re.match(r"^\d{3}-\d+", t):
        return f"TCT {t}"
    if t.upper().startswith("T-"):
        return f"TCT {t[2:]}" if not t[2:].startswith("T") else t
    return f"TCT {t}"


def _chip(kind: str, label: str) -> str:
    return f'<span class="chip chip-{_esc(kind)}">{_esc(label)}</span>'


def _life_chip(life: str) -> str:
    m = {
        "active": ("ok", "Active"),
        "cancelled": ("off", "Cancelled"),
        "contested": ("bad", "Contested"),
        "clouded": ("warn", "Clouded"),
        "review": ("warn", "Under review"),
    }
    k, lab = m.get(life, ("off", life.title() if life else "Unknown"))
    return _chip(k, lab)


def _tax_chip(s: str) -> str:
    return _chip("ok", "Tax linked") if s == "linked" else _chip("warn", "Tax pending")


def _map_chip(s: str) -> str:
    if s == "plotted":
        return _chip("ok", "On map")
    if s == "awaiting":
        return _chip("warn", "Map queued")
    return _chip("off", "Map pending")


def _attn_badge(days: int | None) -> str:
    if days is None:
        return _chip("off", "Date TBD")
    if days < 0:
        return _chip("bad", f"{abs(days)}d overdue")
    if days == 0:
        return _chip("bad", "Today")
    if days <= 7:
        return _chip("bad", f"In {days}d")
    if days <= 31:
        return _chip("warn", f"In {days}d")
    return _chip("ok", f"In {days}d")


def _tabbar(token: str | None, active: str = "home") -> str:
    """Five-tab product chrome. token=None → inert demo links."""
    def href(path: str) -> str:
        if not token:
            return "javascript:void(0)"
        if path == "":
            return f"/client/{token}"
        return f"/client/{token}/{path}"

    tabs = [
        ("home", "", "▣", "Home"),
        ("map", "map", "◎", "Map"),
        ("money", "money", "₱", "Money"),
        ("chat", "chat", "◉", "Chat"),
        ("cases", "cases", "☰", "Cases"),
    ]
    bits = []
    for key, path, icon, label in tabs:
        on = " on" if key == active else ""
        bits.append(
            f'<a class="tab{on}" href="{_esc(href(path))}">'
            f'<span class="ti">{icon}</span>{label}</a>'
        )
    return f'<nav class="tabbar">{"".join(bits)}</nav>'


def _php(n) -> str:
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f"₱{v:,.0f}" if v == int(v) else f"₱{v:,.2f}"


def _php_compact(n) -> str:
    """Axis labels: 1.2M / 45k / 800."""
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        v = 0.0
    if abs(v) >= 1_000_000:
        return f"₱{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"₱{v/1_000:.0f}k"
    return f"₱{v:.0f}"


_CHART_COLORS = (
    "#3DDC97", "#5B9FD4", "#F0B429", "#FF6B6B", "#A78BFA",
    "#2DD4BF", "#FB923C", "#94A3B8",
)


def _render_monthly_chart(monthly: list[dict]) -> str:
    """Server-rendered SVG column chart — live from transactions, no JS lib."""
    if not monthly:
        return '<div class="empty-block">No monthly activity yet.</div>'
    max_v = max((m.get("debit") or 0) for m in monthly) or 1.0
    # viewBox chart area
    W, H = 360, 160
    pad_l, pad_r, pad_t, pad_b = 8, 8, 12, 28
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    n = len(monthly)
    gap = 4
    bar_w = max(8, (plot_w - gap * (n - 1)) / n)

    bars = []
    labels = []
    for i, m in enumerate(monthly):
        v = float(m.get("debit") or 0)
        h = 0 if max_v <= 0 else (v / max_v) * plot_h
        x = pad_l + i * (bar_w + gap)
        y = pad_t + plot_h - h
        active = v > 0
        fill = "#3DDC97" if active else "#1A222D"
        opacity = "1" if active else "0.45"
        title = f"{m.get('month','')}: {_php(v)} ({m.get('n') or 0} txs)"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 1.5):.1f}" '
            f'rx="3" fill="{fill}" opacity="{opacity}">'
            f"<title>{_esc(title)}</title></rect>"
        )
        # label every month if ≤12
        lx = x + bar_w / 2
        labels.append(
            f'<text x="{lx:.1f}" y="{H - 8}" text-anchor="middle" '
            f'fill="#5C6B80" font-size="9" font-family="system-ui,sans-serif">'
            f'{_esc(m.get("label") or "")}</text>'
        )

    # y max label
    ymax = (
        f'<text x="{W - pad_r}" y="10" text-anchor="end" fill="#5C6B80" '
        f'font-size="9" font-family="system-ui,sans-serif">{_esc(_php_compact(max_v))}</text>'
    )
    baseline = (
        f'<line x1="{pad_l}" y1="{pad_t + plot_h}" x2="{W - pad_r}" y2="{pad_t + plot_h}" '
        f'stroke="#243041" stroke-width="1"/>'
    )
    return (
        f'<div class="chart-card" data-live="transactions">'
        f'<div class="chart-head"><span class="chart-title">Monthly spend</span>'
        f'<span class="chart-live">LIVE</span></div>'
        f'<svg class="chart-svg" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Monthly property spend for the last 12 months">'
        f"{baseline}{ymax}{''.join(bars)}{''.join(labels)}"
        f"</svg>"
        f'<p class="chart-cap">Debits by month · last 12 · as of today</p>'
        f"</div>"
    )


def _render_category_chart(by_cat: list[dict], outflow: float) -> str:
    """Horizontal bar share chart from live category totals."""
    rows = []
    for r in by_cat or []:
        if (r.get("direction") or "debit") != "debit":
            continue
        total = float(r.get("total") or 0)
        if total <= 0:
            continue
        rows.append(
            {
                "cat": (r.get("category") or "other").replace("_", " "),
                "total": total,
                "n": int(r.get("n") or 0),
            }
        )
    if not rows:
        return '<div class="empty-block">No property payments posted yet.</div>'

    max_v = max(r["total"] for r in rows) or 1.0
    bits = []
    for i, r in enumerate(rows):
        pct = (r["total"] / outflow * 100) if outflow > 0 else 0
        bar_pct = (r["total"] / max_v * 100) if max_v > 0 else 0
        color = _CHART_COLORS[i % len(_CHART_COLORS)]
        bits.append(
            f'<div class="hbar">'
            f'<div class="hbar-meta"><span class="hbar-cat">{_esc(r["cat"])}</span>'
            f'<span class="hbar-amt">{_esc(_php(r["total"]))} · {r["n"]} · {pct:.0f}%</span></div>'
            f'<div class="hbar-track"><div class="hbar-fill" style="width:{bar_pct:.1f}%;'
            f'background:{color}"></div></div></div>'
        )
    return (
        f'<div class="chart-card" data-live="transactions">'
        f'<div class="chart-head"><span class="chart-title">Spend by type</span>'
        f'<span class="chart-live">LIVE</span></div>'
        f'<div class="hbar-list">{"".join(bits)}</div>'
        f"</div>"
    )


def _client_meta(cur, client_code: str) -> dict | None:
    cur.execute(
        "SELECT client_code, name, case_file FROM clients WHERE client_code=%s",
        (client_code,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def load_money(client_code: str) -> dict[str, Any]:
    """Accounting (transactions) + billing (client_billing/invoices)."""
    import psycopg2.extras
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        client = _client_meta(cur, client_code)
        if not client:
            return {"ok": False}
        case_file = (client.get("case_file") or client_code).strip()

        # Property ledger — live, as-of today only (no future-dated phantoms)
        cur.execute(
            """
            SELECT COALESCE(SUM(amount) FILTER (WHERE direction='credit'), 0) AS inflow,
                   COALESCE(SUM(amount) FILTER (WHERE direction='debit'), 0) AS outflow,
                   COUNT(*) AS n
              FROM transactions
             WHERE case_file = %s
               AND tx_date <= CURRENT_DATE
            """,
            (case_file,),
        )
        tot = dict(cur.fetchone() or {})
        inflow = float(tot.get("inflow") or 0)
        outflow = float(tot.get("outflow") or 0)

        cur.execute(
            """
            SELECT COALESCE(NULLIF(category,''), 'other') AS category,
                   direction, COUNT(*) AS n, SUM(amount) AS total
              FROM transactions
             WHERE case_file = %s AND tx_date <= CURRENT_DATE
               AND direction = 'debit'
             GROUP BY 1, 2
             ORDER BY total DESC NULLS LAST
             LIMIT 8
            """,
            (case_file,),
        )
        by_cat = [dict(r) for r in cur.fetchall()]

        # Live monthly chart: last 12 calendar months of debits (spend)
        cur.execute(
            """
            WITH months AS (
              SELECT generate_series(
                       date_trunc('month', CURRENT_DATE) - INTERVAL '11 months',
                       date_trunc('month', CURRENT_DATE),
                       INTERVAL '1 month'
                     )::date AS month_start
            )
            SELECT m.month_start,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.direction = 'debit'), 0) AS debit,
                   COALESCE(SUM(t.amount) FILTER (WHERE t.direction = 'credit'), 0) AS credit,
                   COUNT(t.id) AS n
              FROM months m
              LEFT JOIN transactions t
                ON t.case_file = %s
               AND t.tx_date >= m.month_start
               AND t.tx_date <  m.month_start + INTERVAL '1 month'
               AND t.tx_date <= CURRENT_DATE
             GROUP BY m.month_start
             ORDER BY m.month_start
            """,
            (case_file,),
        )
        monthly = []
        for r in cur.fetchall():
            d = dict(r)
            ms = d.get("month_start")
            monthly.append(
                {
                    "month": ms.strftime("%Y-%m") if ms else "",
                    "label": ms.strftime("%b") if ms else "",
                    "debit": float(d.get("debit") or 0),
                    "credit": float(d.get("credit") or 0),
                    "n": int(d.get("n") or 0),
                }
            )

        cur.execute(
            """
            SELECT tx_date, direction, category, amount, description, counterparty,
                   provenance_level
              FROM transactions
             WHERE case_file = %s
               AND tx_date <= CURRENT_DATE
             ORDER BY tx_date DESC, id DESC
             LIMIT 40
            """,
            (case_file,),
        )
        txs = []
        for r in cur.fetchall():
            d = dict(r)
            desc = (d.get("description") or d.get("category") or "Transaction").strip()
            desc = re.sub(r"\s+", " ", desc)
            if len(desc) > 90:
                desc = desc[:87] + "…"
            cat = (d.get("category") or "other").replace("_", " ")
            txs.append(
                {
                    "date": d["tx_date"].isoformat() if d.get("tx_date") else "",
                    "direction": d.get("direction") or "",
                    "category": cat,
                    "amount": float(d.get("amount") or 0),
                    "description": desc,
                    "prov": d.get("provenance_level") or "",
                }
            )

        # Billing
        billing = {
            "plan_label": "LandTek services",
            "monthly_amount": None,
            "status": "not_set",
            "next_bill_date": None,
            "currency": "PHP",
        }
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='client_billing'"
        )
        if cur.fetchone():
            cur.execute("SELECT * FROM client_billing WHERE client_code=%s", (client_code,))
            b = cur.fetchone()
            if b:
                billing = {
                    "plan_label": b.get("plan_label") or billing["plan_label"],
                    "monthly_amount": float(b["monthly_amount"]) if b.get("monthly_amount") is not None else None,
                    "status": b.get("status") or "not_set",
                    "next_bill_date": b["next_bill_date"].isoformat() if b.get("next_bill_date") else None,
                    "currency": b.get("currency") or "PHP",
                }

        invoices = []
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='client_invoices'"
        )
        if cur.fetchone():
            cur.execute(
                """
                SELECT invoice_no, issue_date, due_date, amount, status, description
                  FROM client_invoices
                 WHERE client_code = %s AND status <> 'void'
                 ORDER BY issue_date DESC, id DESC
                 LIMIT 20
                """,
                (client_code,),
            )
            for r in cur.fetchall():
                d = dict(r)
                invoices.append(
                    {
                        "no": d.get("invoice_no") or "",
                        "issue": d["issue_date"].isoformat() if d.get("issue_date") else "",
                        "due": d["due_date"].isoformat() if d.get("due_date") else "",
                        "amount": float(d.get("amount") or 0),
                        "status": d.get("status") or "draft",
                        "description": (d.get("description") or "").strip()[:80],
                    }
                )

        open_due = sum(
            i["amount"]
            for i in invoices
            if i["status"] in ("sent", "overdue", "past_due")
        )
        return {
            "ok": True,
            "client_code": client_code,
            "client_name": client.get("name") or client_code,
            "as_of": date.today().isoformat(),
            "ledger": {
                "inflow": inflow,
                "outflow": outflow,
                "net": inflow - outflow,
                "n": int(tot.get("n") or 0),
                "by_cat": by_cat,
                "monthly": monthly,
                "txs": txs,
            },
            "billing": billing,
            "invoices": invoices,
            "open_due": open_due,
        }
    finally:
        cur.close()
        conn.close()


def load_chat(client_code: str) -> dict[str, Any]:
    import psycopg2.extras
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        client = _client_meta(cur, client_code)
        if not client:
            return {"ok": False}
        msgs = []
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='client_app_messages'"
        )
        if cur.fetchone():
            cur.execute(
                """
                SELECT id, direction, author, body, status, created_at
                  FROM client_app_messages
                 WHERE client_code = %s
                 ORDER BY created_at ASC, id ASC
                 LIMIT 200
                """,
                (client_code,),
            )
            for r in cur.fetchall():
                d = dict(r)
                ts = d.get("created_at")
                msgs.append(
                    {
                        "id": d.get("id"),
                        "direction": d.get("direction"),
                        "author": d.get("author") or "",
                        "body": d.get("body") or "",
                        "status": d.get("status") or "",
                        "when": ts.strftime("%b %d · %H:%M") if ts else "",
                    }
                )
        return {
            "ok": True,
            "client_code": client_code,
            "client_name": client.get("name") or client_code,
            "messages": msgs,
        }
    finally:
        cur.close()
        conn.close()


def post_chat(client_code: str, body: str) -> tuple[bool, str]:
    """Client inbound message. Returns (ok, error_message)."""
    text = (body or "").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        return False, "Message is empty."
    if len(text) > 1000:
        return False, "Keep messages under 1,000 characters."
    # crude control-char strip
    text = "".join(ch for ch in text if ch >= " " or ch in "\n\t")
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='client_app_messages'"
        )
        if not cur.fetchone():
            return False, "Chat is not available yet."
        # dose: max 40 client messages / rolling day
        cur.execute(
            """
            SELECT COUNT(*) FROM client_app_messages
             WHERE client_code = %s AND direction = 'inbound'
               AND created_at > now() - INTERVAL '1 day'
            """,
            (client_code,),
        )
        n = cur.fetchone()[0]
        if n >= 40:
            return False, "Daily message limit reached. Try again tomorrow or call your contact."
        cur.execute(
            """
            INSERT INTO client_app_messages (client_code, direction, author, body, status)
            VALUES (%s, 'inbound', 'client', %s, 'sent')
            """,
            (client_code, text),
        )
        return True, ""
    finally:
        cur.close()
        conn.close()


def render_portfolio_body(data: dict, token: str | None = None) -> str:
    """Inner body HTML (no full document). token set → client nav links."""
    if not data.get("ok"):
        return f'<p class="empty">Portfolio unavailable.</p>'

    name = data["client_name"]
    st = data["stats"]
    map_href = f"/client/{token}/map" if token else "javascript:void(0)"
    money_href = f"/client/{token}/money" if token else "javascript:void(0)"
    chat_href = f"/client/{token}/chat" if token else "javascript:void(0)"
    cases_href = f"/client/{token}/cases" if token else "javascript:void(0)"

    # Attention cards
    attn_html = []
    for a in data["attention"]:
        sub = a["event"] or (f"Due {a['due']}" if a["due"] else "Waiting on a confirmed date")
        href = f"/client/{token}/matter/{a['matter_code']}" if token and a.get("matter_code") else "#"
        attn_html.append(
            f'<a class="attn-card" href="{_esc(href)}">'
            f'<div class="attn-top">{_attn_badge(a["days"])}</div>'
            f'<div class="attn-title">{_esc(a["title"])}</div>'
            f'<div class="attn-sub">{_esc(sub)}</div>'
            f"</a>"
        )
    if not attn_html:
        attn_html.append(
            '<div class="attn-card muted-card"><div class="attn-title">No urgent actions</div>'
            '<div class="attn-sub">Your portfolio is quiet right now.</div></div>'
        )

    rows = []
    for t in data["titles"]:
        meta = " · ".join(x for x in (t.get("location"), t.get("area")) if x)
        if not meta:
            meta = "Location on file with LandTek"
        rows.append(
            f'<div class="title-row">'
            f'<div class="title-main">'
            f'<div class="title-no">{_esc(t["display"])}</div>'
            f'<div class="title-reg">{_esc(t["registrant"])}</div>'
            f'<div class="title-meta">{_esc(meta)}</div>'
            f"</div>"
            f'<div class="title-chips">'
            f'{_life_chip(t["lifecycle"])}{_tax_chip(t["tax"])}{_map_chip(t["map"])}'
            f"</div></div>"
        )
    if not rows:
        rows.append(
            '<div class="empty-block">No published titles yet. '
            "LandTek is preparing your portfolio set.</div>"
        )

    n_show = len(data["titles"])
    n_plot = st["on_map"]
    map_note = ""
    if n_show and n_plot < n_show:
        map_note = (
            f'<p class="map-note">Map shows {n_plot} of {st["titles"]} living titles with '
            f"survey placement. The rest are queued.</p>"
        )

    mode = data.get("publish_mode") or "heuristic"
    mode_note = (
        ""
        if mode == "table"
        else '<p class="fineprint">Showing a curated working set (junk IDs filtered). '
        "Operator publish list freezes the client view.</p>"
    )

    return f"""
{_tabbar(token, "home")}
<section class="hero">
  <div class="eyebrow">Portfolio · {_esc(data["as_of"])}</div>
  <h1>{_esc(name)}</h1>
  <p class="lede">Your land at a glance — titles, map, money, and what needs attention.</p>
</section>

<section class="stats">
  <div class="stat"><div class="n">{st["titles"]}</div><div class="l">Titles</div></div>
  <div class="stat"><div class="n">{st["on_map"]}</div><div class="l">On map</div></div>
  <div class="stat"><div class="n">{st["need_tax"]}</div><div class="l">Need tax</div></div>
  <div class="stat"><div class="n">{st["actions"]}</div><div class="l">Due soon</div></div>
</section>
{map_note}

<section class="block">
  <div class="block-h">
    <h2>Needs attention</h2>
  </div>
  <div class="attn-grid">{"".join(attn_html)}</div>
</section>

<section class="block">
  <div class="block-h">
    <h2>Living titles</h2>
    <span class="count">{n_show}</span>
  </div>
  <div class="title-list">{"".join(rows)}</div>
  {mode_note}
</section>

<section class="cta">
  <a class="btn primary" href="{_esc(map_href)}">Open property map</a>
  <a class="btn ghost" href="{_esc(money_href)}">Money &amp; billing</a>
  <a class="btn ghost" href="{_esc(chat_href)}">Message LandTek</a>
  <a class="btn ghost" href="{_esc(cases_href)}">Cases &amp; deadlines</a>
</section>
"""


def render_money_body(data: dict, token: str | None = None) -> str:
    if not data.get("ok"):
        return '<p class="empty">Money unavailable.</p>'
    led = data["ledger"]
    bill = data["billing"]
    chat_href = f"/client/{token}/chat" if token else "javascript:void(0)"

    st = bill.get("status") or "not_set"
    if st == "active":
        bill_chip = _chip("ok", "Retainer active")
    elif st in ("past_due", "overdue"):
        bill_chip = _chip("bad", "Past due")
    elif st == "paused":
        bill_chip = _chip("warn", "Paused")
    else:
        bill_chip = _chip("off", "Billing not set")

    monthly = bill.get("monthly_amount")
    monthly_s = _php(monthly) + "/mo" if monthly is not None else "—"
    next_b = bill.get("next_bill_date") or "—"

    inv_html = []
    for inv in data.get("invoices") or []:
        sc = inv["status"]
        chip = _chip(
            "ok" if sc == "paid" else ("bad" if sc in ("overdue", "past_due") else "warn"),
            sc.replace("_", " "),
        )
        sub = (inv.get("description") or inv.get("issue") or "").strip()
        due = inv.get("due") or "—"
        sub_line = f"{sub} · due {due}" if sub else f"due {due}"
        inv_html.append(
            f'<div class="tx-row">'
            f'<div class="tx-main"><div class="tx-title">{_esc(inv["no"])}</div>'
            f'<div class="tx-sub">{_esc(sub_line)}</div></div>'
            f'<div class="tx-amt">{_esc(_php(inv["amount"]))}{chip}</div></div>'
        )
    if not inv_html:
        inv_html.append(
            '<div class="empty-block">No invoices yet. When LandTek bills this portfolio, '
            "they appear here.</div>"
        )

    monthly_chart = _render_monthly_chart(led.get("monthly") or [])
    cat_chart = _render_category_chart(led.get("by_cat") or [], float(led.get("outflow") or 0))

    tx_rows = []
    for t in led.get("txs") or []:
        sign = "−" if t["direction"] == "debit" else "+"
        cls = "debit" if t["direction"] == "debit" else "credit"
        tx_rows.append(
            f'<div class="tx-row">'
            f'<div class="tx-main"><div class="tx-title">{_esc(t["description"])}</div>'
            f'<div class="tx-sub">{_esc(t["date"])} · {_esc(t["category"])}</div></div>'
            f'<div class="tx-amt {cls}">{sign}{_esc(_php(t["amount"]))}</div></div>'
        )
    if not tx_rows:
        tx_rows.append(
            '<div class="empty-block">No ledger lines yet for this portfolio.</div>'
        )

    note = (
        '<p class="fineprint">Charts and totals are live from the property ledger (as of today). '
        "LandTek service billing is separate. OR-backed lines preferred; future-dated rows excluded.</p>"
    )

    return f"""
{_tabbar(token, "money")}
<section class="hero">
  <div class="eyebrow">Money · {_esc(data["as_of"])}</div>
  <h1>Accounting &amp; billing</h1>
  <p class="lede">Live property spend, plus your LandTek service account.</p>
</section>

<section class="stats stats-3">
  <div class="stat"><div class="n sm">{_esc(_php(led["outflow"]))}</div><div class="l">Paid out</div></div>
  <div class="stat"><div class="n sm">{_esc(_php(led["inflow"]))}</div><div class="l">Inflows</div></div>
  <div class="stat"><div class="n sm">{_esc(_php(data.get("open_due") or 0))}</div><div class="l">Inv. due</div></div>
</section>

<section class="block">
  <div class="block-h"><h2>Live charts</h2>
    <span class="count">{led.get("n") or 0} txs</span></div>
  {monthly_chart}
  <div style="height:12px"></div>
  {cat_chart}
</section>

<section class="block">
  <div class="block-h"><h2>LandTek billing</h2>{bill_chip}</div>
  <div class="bill-card">
    <div class="bill-line"><span>Plan</span><strong>{_esc(bill.get("plan_label") or "—")}</strong></div>
    <div class="bill-line"><span>Retainer</span><strong>{_esc(monthly_s)}</strong></div>
    <div class="bill-line"><span>Next bill</span><strong>{_esc(str(next_b))}</strong></div>
  </div>
  <div class="block-h" style="margin-top:16px"><h2>Invoices</h2>
    <span class="count">{len(data.get("invoices") or [])}</span></div>
  <div class="title-list">{"".join(inv_html)}</div>
  <a class="btn ghost" style="margin-top:12px" href="{_esc(chat_href)}">Message about billing</a>
</section>

<section class="block">
  <div class="block-h"><h2>Recent property transactions</h2></div>
  <div class="title-list">{"".join(tx_rows)}</div>
  {note}
</section>
"""


def render_chat_body(data: dict, token: str | None = None, flash: str | None = None) -> str:
    if not data.get("ok"):
        return '<p class="empty">Chat unavailable.</p>'
    action = f"/client/{token}/chat" if token else "#"
    bubbles = []
    for m in data.get("messages") or []:
        side = "in" if m.get("direction") == "inbound" else "out"
        who = "You" if side == "in" else (
            "LandTek" if m.get("author") in ("ops", "system", "leo") else "LandTek"
        )
        bubbles.append(
            f'<div class="bubble {side}">'
            f'<div class="b-who">{_esc(who)} · {_esc(m.get("when") or "")}</div>'
            f'<div class="b-body">{_esc(m.get("body") or "")}</div></div>'
        )
    if not bubbles:
        bubbles.append(
            '<div class="empty-block">No messages yet. Say hello — your LandTek team will reply.</div>'
        )
    flash_html = ""
    if flash:
        err = any(x in flash.lower() for x in ("empty", "limit", "could not", "available", "under"))
        flash_html = f'<div class="flash{" err" if err else ""}">{_esc(flash)}</div>'
    form = ""
    if token:
        form = f"""
<form class="chat-form" method="post" action="{_esc(action)}">
  <textarea name="body" rows="3" maxlength="1000"
    placeholder="Ask about a title, tax, map, deadline, or billing…" required></textarea>
  <button type="submit" class="btn primary">Send message</button>
</form>
<p class="fineprint">Replies come from your LandTek team. Do not send passwords or card numbers here.</p>
"""
    else:
        form = '<p class="fineprint">Demo — chat posts only on a live magic link.</p>'

    return f"""
{_tabbar(token, "chat")}
<section class="hero">
  <div class="eyebrow">Chat</div>
  <h1>Message LandTek</h1>
  <p class="lede">One thread for your portfolio — titles, money, map, cases.</p>
</section>
{flash_html}
<section class="chat-thread">{"".join(bubbles)}</section>
{form}
"""


PORTFOLIO_CSS = """
:root {
  --bg: #0B0F14;
  --bg2: #121820;
  --card: #141A22;
  --card2: #1A222D;
  --line: #243041;
  --text: #E8EEF7;
  --muted: #8B9BB0;
  --faint: #5C6B80;
  --accent: #3DDC97;
  --accent2: #5B9FD4;
  --bad: #FF6B6B;
  --warn: #F0B429;
  --ok: #3DDC97;
  --radius: 16px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin:0; padding:0; background:var(--bg); color:var(--text);
  font-family:var(--font); -webkit-font-smoothing:antialiased; }
a { color:inherit; text-decoration:none; }
.shell-top {
  position:sticky; top:0; z-index:20;
  display:flex; align-items:center; gap:12px;
  padding:14px 18px; background:rgba(11,15,20,.92);
  backdrop-filter: blur(12px); border-bottom:1px solid var(--line);
}
.brand { font-weight:700; letter-spacing:.04em; font-size:15px; }
.brand span { color:var(--accent); font-weight:600; }
.who { margin-left:auto; font-size:12px; color:var(--muted); font-weight:600;
  text-align:right; max-width:45%; }
.wrap { max-width:480px; margin:0 auto; padding:8px 16px 100px; }
.tabbar {
  display:flex; gap:6px; margin:8px 0 18px; padding:4px;
  background:var(--bg2); border-radius:14px; border:1px solid var(--line);
}
.tab {
  flex:1; text-align:center; padding:8px 2px; border-radius:11px;
  font-size:10px; font-weight:600; color:var(--muted);
  display:flex; flex-direction:column; align-items:center; gap:2px;
}
.tab .ti { font-size:13px; opacity:.85; }
.tab.on { background:var(--card2); color:var(--text); box-shadow:0 1px 0 rgba(255,255,255,.04); }
.stats-3 { grid-template-columns:repeat(3,1fr); }
.stat .n.sm { font-size:15px; letter-spacing:-.02em; }
.bill-card {
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:4px 14px;
}
.bill-line {
  display:flex; justify-content:space-between; gap:12px; padding:12px 0;
  border-bottom:1px solid var(--line); font-size:13px;
}
.bill-line:last-child { border-bottom:0; }
.bill-line span { color:var(--muted); }
.bill-line strong { font-weight:650; text-align:right; }
.cat-list { display:flex; flex-direction:column; gap:8px; }
.cat-row {
  display:flex; justify-content:space-between; gap:10px; font-size:13px;
  background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px;
}
.cat-row .muted { color:var(--muted); font-size:12px; }
.tx-row {
  display:flex; justify-content:space-between; gap:12px; align-items:flex-start;
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:12px 14px;
}
.tx-title { font-size:13px; font-weight:600; line-height:1.3; }
.tx-sub { font-size:11px; color:var(--faint); margin-top:3px; }
.tx-amt { font-size:13px; font-weight:700; white-space:nowrap; text-align:right; }
.tx-amt.debit { color:var(--bad); }
.tx-amt.credit { color:var(--ok); }
.tx-amt .chip { display:block; margin-top:6px; }
.chat-thread { display:flex; flex-direction:column; gap:10px; margin-bottom:18px; }
.bubble {
  max-width:92%; padding:10px 12px; border-radius:14px; border:1px solid var(--line);
  background:var(--card);
}
.bubble.out { align-self:flex-start; border-bottom-left-radius:4px; }
.bubble.in {
  align-self:flex-end; background:rgba(61,220,151,.1);
  border-color:rgba(61,220,151,.28); border-bottom-right-radius:4px;
}
.b-who { font-size:10px; color:var(--faint); font-weight:700; margin-bottom:4px;
  letter-spacing:.03em; text-transform:uppercase; }
.b-body { font-size:14px; line-height:1.4; white-space:pre-wrap; word-break:break-word; }
.chat-form textarea {
  width:100%; background:var(--bg2); color:var(--text); border:1px solid var(--line);
  border-radius:14px; padding:12px; font:inherit; font-size:14px; resize:vertical;
  margin-bottom:10px; min-height:72px;
}
.chat-form textarea:focus { outline:none; border-color:var(--accent); }
.flash {
  background:rgba(61,220,151,.12); border:1px solid rgba(61,220,151,.3);
  color:var(--ok); border-radius:12px; padding:10px 12px; font-size:13px;
  font-weight:600; margin-bottom:12px;
}
.flash.err { background:rgba(255,107,107,.12); border-color:rgba(255,107,107,.3); color:var(--bad); }
.chart-card {
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px 12px 10px;
}
.chart-head {
  display:flex; align-items:center; justify-content:space-between;
  margin-bottom:8px; padding:0 4px;
}
.chart-title { font-size:13px; font-weight:700; letter-spacing:-.01em; }
.chart-live {
  font-size:9px; font-weight:800; letter-spacing:.08em;
  color:#062816; background:var(--accent); border-radius:999px;
  padding:3px 7px;
}
.chart-svg { width:100%; height:auto; display:block; }
.chart-cap {
  margin:6px 4px 0; font-size:10px; color:var(--faint); letter-spacing:.02em;
}
.hbar-list { display:flex; flex-direction:column; gap:12px; padding:4px 2px 2px; }
.hbar-meta {
  display:flex; justify-content:space-between; gap:10px; margin-bottom:5px;
  font-size:12px;
}
.hbar-cat { font-weight:650; text-transform:capitalize; }
.hbar-amt { color:var(--muted); font-size:11px; white-space:nowrap; }
.hbar-track {
  height:8px; background:var(--bg2); border-radius:999px; overflow:hidden;
  border:1px solid var(--line);
}
.hbar-fill {
  height:100%; border-radius:999px; min-width:2px;
  transition: width .35s ease;
}
.hero { margin:6px 0 18px; }
.eyebrow { font-size:11px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--faint); font-weight:600; margin-bottom:6px; }
.hero h1 { margin:0 0 8px; font-size:26px; line-height:1.15; font-weight:700;
  letter-spacing:-.02em; }
.lede { margin:0; color:var(--muted); font-size:14px; line-height:1.45; }
.stats {
  display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:10px;
}
.stat {
  background:linear-gradient(180deg, var(--card2), var(--card));
  border:1px solid var(--line); border-radius:14px; padding:12px 8px; text-align:center;
}
.stat .n { font-size:22px; font-weight:700; letter-spacing:-.03em; color:var(--text); }
.stat .l { font-size:10px; color:var(--muted); margin-top:2px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; }
.map-note { font-size:12px; color:var(--muted); margin:0 0 16px; line-height:1.4; }
.block { margin:22px 0; }
.block-h { display:flex; align-items:baseline; gap:10px; margin-bottom:12px; }
.block-h h2 { margin:0; font-size:15px; font-weight:700; letter-spacing:-.01em; }
.block-h .count {
  font-size:11px; color:var(--faint); background:var(--bg2);
  border:1px solid var(--line); border-radius:999px; padding:2px 8px; font-weight:600;
}
.attn-grid { display:flex; flex-direction:column; gap:8px; }
.attn-card {
  display:block; background:var(--card); border:1px solid var(--line);
  border-radius:var(--radius); padding:14px 14px 12px;
  transition: border-color .15s, transform .15s;
}
.attn-card:active { transform: scale(.99); }
a.attn-card:hover { border-color:#3a4d66; }
.muted-card { opacity:.9; }
.attn-top { margin-bottom:8px; }
.attn-title { font-size:14px; font-weight:650; line-height:1.3; margin-bottom:4px; }
.attn-sub { font-size:12px; color:var(--muted); line-height:1.4; }
.title-list { display:flex; flex-direction:column; gap:8px; }
.title-row {
  background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:14px; display:flex; flex-direction:column; gap:10px;
}
.title-no { font-size:15px; font-weight:700; letter-spacing:-.01em; }
.title-reg { font-size:13px; color:var(--text); margin-top:2px; opacity:.92; }
.title-meta { font-size:11px; color:var(--faint); margin-top:4px; }
.title-chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip {
  display:inline-flex; align-items:center; font-size:10.5px; font-weight:700;
  letter-spacing:.02em; padding:4px 8px; border-radius:999px; border:1px solid transparent;
}
.chip-ok { background:rgba(61,220,151,.12); color:var(--ok); border-color:rgba(61,220,151,.25); }
.chip-warn { background:rgba(240,180,41,.12); color:var(--warn); border-color:rgba(240,180,41,.28); }
.chip-bad { background:rgba(255,107,107,.12); color:var(--bad); border-color:rgba(255,107,107,.28); }
.chip-off { background:rgba(139,155,176,.1); color:var(--muted); border-color:rgba(139,155,176,.2); }
.cta { display:flex; flex-direction:column; gap:10px; margin:28px 0 12px; }
.btn {
  display:block; text-align:center; padding:14px 16px; border-radius:14px;
  font-weight:700; font-size:14px; border:1px solid transparent;
}
.btn.primary { background:var(--accent); color:#062816; }
.btn.ghost { background:transparent; color:var(--text); border-color:var(--line); }
.fineprint { font-size:11px; color:var(--faint); margin:12px 0 0; line-height:1.4; }
.empty-block, .empty { color:var(--muted); font-size:13px; padding:16px; text-align:center;
  border:1px dashed var(--line); border-radius:var(--radius); }
.shell-foot {
  max-width:480px; margin:0 auto; padding:8px 20px 28px; color:var(--faint);
  font-size:11px; line-height:1.5; text-align:center;
}
.shell-foot strong { color:var(--muted); font-weight:600; }
@media (min-width:720px) {
  .wrap { max-width:560px; padding-top:16px; }
  .stats { gap:10px; }
  .stat .n { font-size:26px; }
}
"""


def _shell_page(title: str, client_name: str, body: str, brand_sub: str = "portfolio") -> str:
    who = _esc(client_name)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0B0F14">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LandTek">
<link rel="manifest" href="/client/_app/manifest.webmanifest">
<title>{_esc(title)} · LandTek</title>
<style>{PORTFOLIO_CSS}</style>
</head>
<body>
<header class="shell-top">
  <div class="brand">LANDTEK <span>{_esc(brand_sub)}</span></div>
  <div class="who">{who}</div>
</header>
<main class="wrap">
{body}
</main>
<footer class="shell-foot">
  <strong>LandTek</strong> property &amp; legal-operations · not legal advice<br>
  Updated {now}
</footer>
</body>
</html>"""


def render_portfolio_page(client_code: str, token: str | None = None) -> str:
    """Full HTML document for the portfolio home."""
    data = load_portfolio(client_code)
    if not data.get("ok"):
        return "<!doctype html><title>Not found</title><p>Not found</p>"
    body = render_portfolio_body(data, token=token)
    return _shell_page(
        f"Portfolio — {data['client_name']}",
        data["client_name"],
        body,
    )


def render_money_page(client_code: str, token: str | None = None) -> str:
    data = load_money(client_code)
    if not data.get("ok"):
        return "<!doctype html><title>Not found</title><p>Not found</p>"
    body = render_money_body(data, token=token)
    return _shell_page(
        f"Money — {data['client_name']}",
        data["client_name"],
        body,
        brand_sub="money",
    )


def render_chat_page(client_code: str, token: str | None = None, flash: str | None = None) -> str:
    data = load_chat(client_code)
    if not data.get("ok"):
        return "<!doctype html><title>Not found</title><p>Not found</p>"
    body = render_chat_body(data, token=token, flash=flash)
    return _shell_page(
        f"Chat — {data['client_name']}",
        data["client_name"],
        body,
        brand_sub="chat",
    )


def render_demo_page() -> str:
    """Static demo with polished sample data (no DB) for local open-in-browser."""
    data = {
        "ok": True,
        "client_code": "MWK-001",
        "client_name": "Heirs of Mary Worrick Keesey",
        "as_of": date.today().isoformat(),
        "publish_mode": "table",
        "stats": {"titles": 18, "on_map": 5, "need_tax": 6, "actions": 3},
        "attention": [
            {
                "title": "Testimony — Zschoche v. Balane",
                "days": (date(2026, 8, 12) - date.today()).days,
                "due": "2026-08-12",
                "event": "Counsel-planned testimony date · MTC Mercedes",
                "matter_code": None,
            },
            {
                "title": "Guardianship hearing",
                "days": (date(2026, 7, 27) - date.today()).days,
                "due": "2026-07-27",
                "event": "RTC Br. 41 Daet · initial hearing 8:30am",
                "matter_code": None,
            },
            {
                "title": "ARTA follow-ups",
                "days": (date(2026, 7, 24) - date.today()).days,
                "due": "2026-07-24",
                "event": "Several complaint tracks awaiting agency movement",
                "matter_code": None,
            },
        ],
        "titles": [
            {"display": "TCT 4497", "registrant": "Heirs of Mary Worrick Keesey",
             "lifecycle": "active", "location": "Mercedes, Camarines Norte",
             "area": "mother title", "tax": "linked", "map": "pending", "tct": "T-4497"},
            {"display": "TCT 32911", "registrant": "Heirs of Mary Worrick Keesey",
             "lifecycle": "active", "location": "Lot 2-A · Mercedes",
             "area": "≈8,000 sqm", "tax": "linked", "map": "plotted", "tct": "T-32911"},
            {"display": "TCT 52540", "registrant": "Gloria H. Balane (chain)",
             "lifecycle": "cancelled", "location": "Cancelled → 079-2021002126",
             "area": "", "tax": "pending", "map": "pending", "tct": "T-52540"},
            {"display": "TCT 079-2021002126", "registrant": "Gloria H. Balane",
             "lifecycle": "contested", "location": "Subject of CV-26360",
             "area": "2,587 sqm", "tax": "pending", "map": "plotted", "tct": "079-2021002126"},
            {"display": "TCT 33776", "registrant": "Rosco Leano",
             "lifecycle": "active", "location": "Lot 2-X-6-H",
             "area": "1,295 sqm", "tax": "pending", "map": "plotted", "tct": "T-33776"},
            {"display": "TCT 36668", "registrant": "Alsa O. Iligan",
             "lifecycle": "active", "location": "Lot 2-X-6-A",
             "area": "500 sqm", "tax": "pending", "map": "plotted", "tct": "T-36668"},
            {"display": "TCT 30681", "registrant": "Heirs of Mary Worrick Keesey",
             "lifecycle": "active", "location": "Mercedes, Camarines Norte",
             "area": "804,188 sqm", "tax": "linked", "map": "pending", "tct": "T-30681"},
            {"display": "TCT 38838", "registrant": "Mary Worrick Keesey",
             "lifecycle": "active", "location": "Mercedes, Camarines Norte",
             "area": "32,448 sqm", "tax": "linked", "map": "pending", "tct": "T-38838"},
        ],
    }
    body = render_portfolio_body(data, token=None)
    # demo nav without real links
    body = body.replace('href="#"', 'href="javascript:void(0)"')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0B0F14">
<title>LandTek Portfolio — Demo</title>
<style>{PORTFOLIO_CSS}
.demo-banner {{
  background: linear-gradient(90deg, #1a3a2a, #0B0F14 40%);
  border-bottom: 1px solid rgba(61,220,151,.35);
  color: var(--accent); font-size: 11px; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase;
  text-align: center; padding: 8px 12px;
}}
</style>
</head>
<body>
<div class="demo-banner">Demo preview · curated publish set · not live token</div>
<header class="shell-top">
  <div class="brand">LANDTEK <span>portfolio</span></div>
  <div class="who">Heirs of Mary Worrick Keesey</div>
</header>
<main class="wrap">{body}</main>
<footer class="shell-foot">
  <strong>LandTek</strong> — this is the client product face<br>
  Home · Map · Cases · publish-safe titles only
</footer>
</body>
</html>"""


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        print(render_demo_page())
    elif len(sys.argv) > 1:
        print(render_portfolio_page(sys.argv[1]))
    else:
        print(render_demo_page())
