#!/usr/bin/env python3
"""LandTek Agenda Engine — Postgres → Google Calendar sync (deploy: agenda_engine).

Mirrors LandTek's live agenda out to Google Calendar so every client's and every
associate's (legal counsel's) actions land on a real calendar that pushes agendas
forward. Postgres stays the source of truth; Google Calendar is a projection.

Design principles (match the house doctrine):
  * DEGRADE, DON'T CRASH. Missing creds / missing tables / missing columns are
    handled — the tool reports and no-ops rather than throwing.
  * DRY-RUN BY DEFAULT. Nothing is written to Google Calendar unless --apply.
  * NO CLIENT CONTAMINATION. client_code is only ever taken from a real matters
    join, never guessed from a matter-code prefix (client-separation invariant).
  * INTROSPECTS THE LIVE SCHEMA. Column/table presence is checked at runtime, so
    a schema drift downgrades a source instead of breaking the run.

Agenda sources (most-reliable first):
  A. matters.next_deadline / next_event  — carries client_code + lead_counsel
     NATIVELY, so these items are fully tagged with client + owner + matter.
  B. calendar_events                      — discrete events; client/owner resolved
     best-effort via related_case → matters, else left UNRESOLVED (not guessed).

Idempotency: every synced item has a stable landtek_uid (e.g. 'matter:12:deadline',
'event:45'); calendar_sync_map remembers the Google event id + a content hash so a
re-run patches only what changed and never double-creates.

Usage:
  python3 scripts/calendar_sync.py                 # dry-run: show what WOULD sync
  python3 scripts/calendar_sync.py --apply         # push to Google Calendar
  python3 scripts/calendar_sync.py --pull          # reconcile manual gcal edits back
  python3 scripts/calendar_sync.py --calendar-id primary
  python3 scripts/calendar_sync.py --client MWK    # limit to one client
  python3 scripts/calendar_sync.py --limit 20

Credentials (VPS, /root/landtek/.env):
  CALENDAR_REFRESH_TOKEN   OAuth refresh token WITH calendar scope. The Gmail
                           token is scoped gmail.readonly only and will NOT work —
                           mint a calendar-scoped token once (see docs/handoff).
  LANDTEK_CALENDAR_ID      target calendar (default: 'primary').
  gmail_oauth_client.json  reused for the OAuth client_id / client_secret.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
ENV_PATH = "/root/landtek/.env"
OAUTH_CLIENT_PATH = "/root/landtek/gmail_oauth_client.json"
TZ = "Asia/Manila"
CAL_SCOPE = "https://www.googleapis.com/auth/calendar.events"

# Associates = legal counsel (owners of legal actions). Seeded idempotently.
ASSOCIATES_SEED = [
    # (code, full_name, role, email)
    ("BARANDON", "Atty. Bonifacio Jr. Barandon", "lead_counsel", None),
    ("BOTOR", "Atty. Botor", "lead_counsel", None),
]


# ── infra ──────────────────────────────────────────────────────────────
def load_env():
    env = {}
    try:
        with open(ENV_PATH) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.strip().partition("=")
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    # process env overrides file
    for k in ("CALENDAR_REFRESH_TOKEN", "LANDTEK_CALENDAR_ID", "PG_DSN"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def db():
    return psycopg2.connect(DSN)


def calendar_client(env):
    """Build a Google Calendar service, or return None (degrade) if unconfigured."""
    token = env.get("CALENDAR_REFRESH_TOKEN")
    if not token:
        return None
    try:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        with open(OAUTH_CLIENT_PATH) as f:
            oauth = json.load(f)
        conf = oauth.get("web") or oauth.get("installed")
        creds = Credentials(
            token=None,
            refresh_token=token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=conf["client_id"],
            client_secret=conf["client_secret"],
            scopes=[CAL_SCOPE],
        )
        creds.refresh(Request())
        return build("calendar", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001 — degrade, don't crash
        print(f"[calendar_sync] calendar auth unavailable: {e}", file=sys.stderr)
        return None


# ── schema introspection + self-provision ──────────────────────────────
def table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s)", (f"public.{name}",))
    return cur.fetchone()[0] is not None


def columns_of(cur, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=%s",
        (table,),
    )
    return {r[0] for r in cur.fetchall()}


def ensure_schema(cur):
    """Create the sync-map + associates tables if absent; seed counsel."""
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS associates (
            code        TEXT PRIMARY KEY,
            full_name   TEXT NOT NULL,
            role        TEXT DEFAULT 'lead_counsel',
            email       TEXT,
            gcal_id     TEXT,
            active      BOOLEAN DEFAULT TRUE,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_sync_map (
            landtek_uid       TEXT PRIMARY KEY,
            source            TEXT NOT NULL,
            source_id         TEXT,
            gcal_event_id     TEXT,
            gcal_calendar_id  TEXT,
            content_hash      TEXT,
            status            TEXT DEFAULT 'active',
            last_synced_at    TIMESTAMPTZ,
            created_at        TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    for code, name, role, email in ASSOCIATES_SEED:
        cur.execute(
            """
            INSERT INTO associates (code, full_name, role, email)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE
              SET full_name = EXCLUDED.full_name, role = EXCLUDED.role
            """,
            (code, name, role, email),
        )


# ── agenda gathering ────────────────────────────────────────────────────
class Item:
    """Normalized agenda item."""

    __slots__ = ("uid", "source", "source_id", "title", "start", "end",
                 "all_day", "client", "matter", "owner", "kind", "status", "desc")

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw.get(s))

    def summary(self):
        tag_bits = [b for b in (self.client, self.matter, self.owner) if b]
        prefix = f"[{' · '.join(tag_bits)}] " if tag_bits else ""
        return f"{prefix}{self.title}"[:250]

    def hash(self):
        raw = "|".join(str(x) for x in (
            self.title, self.start, self.end, self.client, self.matter,
            self.owner, self.status, self.desc))
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _counsel_to_owner(lead_counsel):
    """Map a matters.lead_counsel free-text value to an associate label."""
    if not lead_counsel:
        return None
    lc = lead_counsel.lower()
    if "barandon" in lc:
        return "Barandon"
    if "botor" in lc:
        return "Botor"
    return lead_counsel.strip()[:40]


def gather_from_matters(cur, client_filter):
    """Source A: matters.next_deadline / next_event — fully tagged natively."""
    if not table_exists(cur, "matters"):
        return []
    cols = columns_of(cur, "matters")
    # Prefer a human matter label; fall back through likely columns.
    label_col = next((c for c in ("matter_code", "docket_number", "case_file")
                      if c in cols), None)
    have = {c for c in ("id", "client_code", "lead_counsel", "next_deadline",
                        "next_event", "current_stage") if c in cols}
    if "id" not in have or "next_deadline" not in have:
        return []
    select_cols = sorted(have | ({label_col} if label_col else set()))
    sql = f"SELECT {', '.join(select_cols)} FROM matters WHERE next_deadline IS NOT NULL"
    params = []
    if client_filter and "client_code" in cols:
        sql += " AND client_code ILIKE %s"
        params.append(f"{client_filter}%")
    cur.execute(sql, params)
    rows = cur.fetchall()
    idx = {c: i for i, c in enumerate(select_cols)}
    items = []
    for r in rows:
        def g(c):
            return r[idx[c]] if c in idx else None
        deadline = g("next_deadline")
        if deadline is None:
            continue
        title = (g("next_event") or g("current_stage") or "Matter deadline")
        matter_label = g(label_col) if label_col else None
        items.append(Item(
            uid=f"matter:{g('id')}:deadline",
            source="matters",
            source_id=str(g("id")),
            title=str(title)[:200],
            start=deadline,
            end=None,
            all_day=True,
            client=g("client_code"),
            matter=matter_label,
            owner=_counsel_to_owner(g("lead_counsel")),
            kind="deadline",
            status="scheduled",
            desc=f"Matter deadline surfaced from matters.next_deadline. "
                 f"Stage: {g('current_stage') or 'n/a'}.",
        ))
    return items


def gather_from_events(cur, client_filter):
    """Source B: calendar_events — client/owner resolved via matters, else UNRESOLVED."""
    if not table_exists(cur, "calendar_events"):
        return []
    cols = columns_of(cur, "calendar_events")
    needed = {"id", "title", "start_at"}
    if not needed <= cols:
        return []
    opt = [c for c in ("description", "end_at", "location", "related_case",
                       "related_tct", "status") if c in cols]
    sel = ["id", "title", "start_at"] + opt
    sql = f"SELECT {', '.join(sel)} FROM calendar_events"
    # only future-ish and non-cancelled if the column exists
    where = []
    if "status" in cols:
        where.append("(status IS NULL OR status <> 'cancelled')")
    if where:
        sql += " WHERE " + " AND ".join(where)
    cur.execute(sql)
    rows = cur.fetchall()
    idx = {c: i for i, c in enumerate(sel)}
    # Build a resolver: related_case → (client_code, lead_counsel)
    resolver = _matter_resolver(cur)
    items = []
    for r in rows:
        def g(c):
            return r[idx[c]] if c in idx else None
        related_case = g("related_case")
        client, owner, matter = resolver(related_case)
        if client_filter and (client or "").upper().find(client_filter.upper()) < 0:
            # if we couldn't resolve a client, don't filter it out silently on a
            # client-scoped run — but do skip clearly-other-client rows.
            if client:
                continue
        start = g("start_at")
        items.append(Item(
            uid=f"event:{g('id')}",
            source="calendar_events",
            source_id=str(g("id")),
            title=str(g("title"))[:200],
            start=start,
            end=g("end_at"),
            all_day=False,
            client=client,
            matter=matter or related_case,
            owner=owner,
            kind="event",
            status=g("status") or "scheduled",
            desc=(g("description") or "") +
                 ("" if client else "\n[client UNRESOLVED — not tagged to avoid contamination]"),
        ))
    return items


def _matter_resolver(cur):
    """Return f(related_case)->(client_code, owner, matter_label) via real joins only."""
    if not table_exists(cur, "matters"):
        return lambda _rc: (None, None, None)
    cols = columns_of(cur, "matters")
    keys = [c for c in ("docket_number", "case_file", "matter_code") if c in cols]
    if not keys or "client_code" not in cols:
        return lambda _rc: (None, None, None)
    lc = "lead_counsel" if "lead_counsel" in cols else "NULL"
    label = keys[0]
    # Load a small in-memory index (matters is ~dozens of rows).
    idxmap = {}
    cur.execute(
        f"SELECT client_code, {lc} AS lead_counsel, {label} AS label, "
        f"{', '.join(keys)} FROM matters"
    )
    for row in cur.fetchall():
        client_code, lead_counsel, label_val = row[0], row[1], row[2]
        for keyval in row[3:]:
            if keyval:
                idxmap[str(keyval).strip().lower()] = (
                    client_code, _counsel_to_owner(lead_counsel), label_val)

    def resolve(related_case):
        if not related_case:
            return (None, None, None)
        return idxmap.get(str(related_case).strip().lower(), (None, None, None))

    return resolve


# ── Google Calendar upsert ──────────────────────────────────────────────
def _to_gcal_time(value, all_day):
    """Return a Google Calendar start/end dict for a date or datetime."""
    if value is None:
        return None
    if all_day and not isinstance(value, datetime):
        return {"date": value.isoformat()}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return {"dateTime": value.isoformat(), "timeZone": TZ}
        return {"dateTime": value.isoformat()}
    # a plain date used as a timed event
    return {"date": value.isoformat()}


def build_event_body(item):
    start = _to_gcal_time(item.start, item.all_day)
    end = _to_gcal_time(item.end, item.all_day) or start
    body = {
        "summary": item.summary(),
        "description": (item.desc or "").strip() +
                       f"\n\n— LandTek Agenda Engine · uid={item.uid} · do not edit summary",
        "start": start,
        "end": end,
        "extendedProperties": {"private": {
            "landtek_uid": item.uid,
            "client_code": item.client or "",
            "matter": str(item.matter or ""),
            "owner": item.owner or "",
            "kind": item.kind or "",
        }},
    }
    return body


def sync_push(conn, service, items, calendar_id, apply):
    cur = conn.cursor()
    created = patched = skipped = 0
    for it in items:
        cur.execute(
            "SELECT gcal_event_id, content_hash FROM calendar_sync_map WHERE landtek_uid=%s",
            (it.uid,),
        )
        row = cur.fetchone()
        h = it.hash()
        body = build_event_body(it)
        if row and row[1] == h:
            skipped += 1
            continue
        if not apply:
            action = "PATCH" if row else "CREATE"
            print(f"  [{action}] {it.summary()}  ({it.start})")
            if row:
                patched += 1
            else:
                created += 1
            continue
        # apply
        try:
            if row and row[0]:
                try:
                    service.events().patch(
                        calendarId=calendar_id, eventId=row[0], body=body).execute()
                    patched += 1
                except Exception:  # event may have been deleted in gcal → recreate
                    ev = service.events().insert(
                        calendarId=calendar_id, body=body).execute()
                    _upsert_map(cur, it, ev["id"], calendar_id, h)
                    created += 1
                    conn.commit()
                    continue
            else:
                ev = service.events().insert(
                    calendarId=calendar_id, body=body).execute()
                _upsert_map(cur, it, ev["id"], calendar_id, h)
                created += 1
                conn.commit()
                continue
            _upsert_map(cur, it, row[0], calendar_id, h)
            conn.commit()
        except Exception as e:  # noqa: BLE001
            print(f"  [ERROR] {it.uid}: {e}", file=sys.stderr)
    return created, patched, skipped


def _upsert_map(cur, it, gcal_id, calendar_id, h):
    cur.execute(
        """
        INSERT INTO calendar_sync_map
            (landtek_uid, source, source_id, gcal_event_id, gcal_calendar_id,
             content_hash, status, last_synced_at)
        VALUES (%s,%s,%s,%s,%s,%s,'active', now())
        ON CONFLICT (landtek_uid) DO UPDATE SET
            gcal_event_id = EXCLUDED.gcal_event_id,
            gcal_calendar_id = EXCLUDED.gcal_calendar_id,
            content_hash = EXCLUDED.content_hash,
            status = 'active',
            last_synced_at = now()
        """,
        (it.uid, it.source, it.source_id, gcal_id, calendar_id, h),
    )


def sync_pull(conn, service, calendar_id, apply):
    """Reconcile manual Google-Calendar edits back into Postgres (phase-1 basic).

    Walks our own calendar_sync_map (the set of LandTek-managed events) and asks
    Google for each event's current state, recording drift where a managed event
    was cancelled/deleted by hand. Iterating the map — rather than listing by
    extended property — is the correct approach: Google's list filter matches
    key=value, not key-presence. Write-back of brand-new manual events into
    calendar_events is a phase-2 item.
    """
    if service is None:
        print("[pull] no calendar service — skipping.")
        return 0
    cur = conn.cursor()
    cur.execute(
        "SELECT landtek_uid, gcal_event_id FROM calendar_sync_map "
        "WHERE status='active' AND gcal_event_id IS NOT NULL "
        "AND gcal_calendar_id=%s", (calendar_id,))
    managed = cur.fetchall()
    drift = 0
    for uid, gcal_id in managed:
        try:
            ev = service.events().get(calendarId=calendar_id, eventId=gcal_id).execute()
        except Exception:  # 404 / gone → treated as deleted
            ev = {"status": "cancelled"}
        if ev.get("status") == "cancelled":
            drift += 1
            print(f"  [DRIFT] {uid} cancelled/deleted in Google Calendar")
            if apply:
                cur.execute(
                    "UPDATE calendar_sync_map SET status='deleted', last_synced_at=now() "
                    "WHERE landtek_uid=%s", (uid,))
                conn.commit()
    return drift


# ── conflict detection ──────────────────────────────────────────────────
def detect_conflicts(items):
    """Flag same-day collisions of deadlines/events across matters."""
    by_day = {}
    for it in items:
        if it.start is None:
            continue
        d = it.start.date() if isinstance(it.start, datetime) else it.start
        by_day.setdefault(d, []).append(it)
    hot = []
    for d, group in sorted(by_day.items()):
        if len(group) >= 2:
            hot.append((d, group))
    return hot


# ── main ─────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="LandTek Postgres → Google Calendar sync")
    ap.add_argument("--apply", action="store_true", help="write to Google Calendar (default: dry-run)")
    ap.add_argument("--pull", action="store_true", help="reconcile manual gcal edits back")
    ap.add_argument("--calendar-id", default=None, help="target calendar (default: env or 'primary')")
    ap.add_argument("--client", default=None, help="limit to one client code prefix, e.g. MWK")
    ap.add_argument("--limit", type=int, default=None, help="cap items (debug)")
    args = ap.parse_args()

    env = load_env()
    calendar_id = args.calendar_id or env.get("LANDTEK_CALENDAR_ID", "primary")

    conn = db()
    cur = conn.cursor()
    ensure_schema(cur)
    conn.commit()

    items = gather_from_matters(cur, args.client) + gather_from_events(cur, args.client)
    items = [i for i in items if i.start is not None]
    items.sort(key=lambda i: (i.start if isinstance(i.start, datetime)
                              else datetime(i.start.year, i.start.month, i.start.day, tzinfo=timezone.utc)))
    if args.limit:
        items = items[: args.limit]

    print(f"[calendar_sync] {len(items)} agenda item(s) gathered "
          f"(client={args.client or 'ALL'}, calendar={calendar_id})")

    conflicts = detect_conflicts(items)
    if conflicts:
        print(f"[calendar_sync] ⚠ {len(conflicts)} day(s) with ≥2 items (potential conflicts):")
        for d, group in conflicts:
            print(f"    {d}: " + " | ".join(f"{g.matter or g.client or '?'}:{g.title[:30]}" for g in group))

    service = calendar_client(env)
    if args.apply and service is None:
        print("[calendar_sync] --apply requested but no CALENDAR_REFRESH_TOKEN / calendar "
              "auth. Mint a calendar-scoped token first (see handoff). Aborting write.",
              file=sys.stderr)
        sys.exit(2)

    if args.pull:
        drift = sync_pull(conn, service, calendar_id, args.apply)
        print(f"[calendar_sync] pull: {drift} drift event(s)"
              + ("" if args.apply else " (dry-run, no DB writes)"))

    created, patched, skipped = sync_push(conn, service, items, calendar_id, args.apply)
    verb = "synced" if args.apply else "would sync"
    print(f"[calendar_sync] {verb}: {created} create, {patched} update, {skipped} unchanged"
          + ("" if args.apply else "  (DRY-RUN — pass --apply to write)"))

    conn.close()


if __name__ == "__main__":
    main()
