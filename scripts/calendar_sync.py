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


_OWNER_PLACEHOLDERS = {"owner", "tbd", "n/a", "na", "none", "-", ""}


def _counsel_to_owner(lead_counsel):
    """Map a matters owner/counsel free-text value to a clean associate label."""
    if not lead_counsel:
        return None
    lc = lead_counsel.strip().lower()
    if lc in _OWNER_PLACEHOLDERS:
        return None
    if "barandon" in lc:
        return "Barandon"
    if "botor" in lc:
        return "Botor"
    return lead_counsel.strip()[:40]


class MatterInfo:
    __slots__ = ("id", "matter_code", "client", "owner", "label",
                 "next_deadline", "next_event", "current_stage")

    def __init__(self, **kw):
        for s in self.__slots__:
            setattr(self, s, kw.get(s))


def load_matters_index(cur):
    """Load matters once into an index keyed by every join handle (matter_code,
    docket_number, case_file) → MatterInfo. Owner = next_event_owner or lead_counsel.
    This is the single source of client/owner truth; all sources resolve through it,
    so client_code is never guessed (client-separation invariant)."""
    index, by_code = {}, {}
    if not table_exists(cur, "matters"):
        return index, by_code
    cols = columns_of(cur, "matters")
    if "matter_code" not in cols or "client_code" not in cols:
        return index, by_code
    optional = [c for c in ("docket_number", "case_file", "lead_counsel",
                            "next_event_owner", "next_deadline", "next_event",
                            "current_stage") if c in cols]
    sel = ["id", "matter_code", "client_code"] + optional
    cur.execute(f"SELECT {', '.join(sel)} FROM matters")
    pos = {c: i for i, c in enumerate(sel)}
    for r in cur.fetchall():
        def g(c):
            return r[pos[c]] if c in pos else None
        owner = _counsel_to_owner(g("next_event_owner") or g("lead_counsel"))
        mi = MatterInfo(
            id=g("id"), matter_code=g("matter_code"), client=g("client_code"),
            owner=owner, label=g("matter_code"), next_deadline=g("next_deadline"),
            next_event=g("next_event"), current_stage=g("current_stage"))
        by_code[str(mi.matter_code).strip().lower()] = mi
        for handle in (g("matter_code"), g("docket_number"), g("case_file")):
            if handle:
                index[str(handle).strip().lower()] = mi
    return index, by_code


def _client_match(client, client_filter):
    """True if this item passes a client-scoped run. Unresolved items pass (they
    carry no client to contaminate); resolved items must match the filter."""
    if not client_filter:
        return True
    if not client:
        return True
    return client_filter.upper() in str(client).upper()


def gather_from_matters(cur, client_filter, index, by_code):
    """Source A: matters.next_deadline — fully tagged natively (client + owner + matter)."""
    items = []
    for mi in by_code.values():
        if mi.next_deadline is None:
            continue
        if not _client_match(mi.client, client_filter):
            continue
        title = mi.next_event or mi.current_stage or "Matter deadline"
        items.append(Item(
            uid=f"matter:{mi.id}:deadline", source="matters", source_id=str(mi.id),
            title=str(title)[:200], start=mi.next_deadline, end=None, all_day=True,
            client=mi.client, matter=mi.label, owner=mi.owner, kind="deadline",
            status="scheduled",
            desc=f"Matter deadline (matters.next_deadline). Stage: {mi.current_stage or 'n/a'}."))
    return items


def gather_from_events(cur, client_filter, index, clients_by_id):
    """Source B: calendar_events. Client via client_id→clients (authoritative);
    matter/owner via related_case→matters. Client left UNRESOLVED if no real join."""
    if not table_exists(cur, "calendar_events"):
        return []
    cols = columns_of(cur, "calendar_events")
    if not {"id", "title", "start_at"} <= cols:
        return []
    opt = [c for c in ("description", "end_at", "location", "related_case",
                       "client_id", "status") if c in cols]
    sel = ["id", "title", "start_at"] + opt
    sql = f"SELECT {', '.join(sel)} FROM calendar_events"
    if "status" in cols:
        sql += " WHERE (status IS NULL OR status <> 'cancelled')"
    cur.execute(sql)
    rows = cur.fetchall()
    pos = {c: i for i, c in enumerate(sel)}
    items = []
    for r in rows:
        def g(c):
            return r[pos[c]] if c in pos else None
        mi = index.get(str(g("related_case")).strip().lower()) if g("related_case") else None
        client = clients_by_id.get(g("client_id")) or (mi.client if mi else None)
        owner = mi.owner if mi else None
        matter = mi.label if mi else g("related_case")
        if not _client_match(client, client_filter):
            continue
        items.append(Item(
            uid=f"event:{g('id')}", source="calendar_events", source_id=str(g("id")),
            title=str(g("title"))[:200], start=g("start_at"), end=g("end_at"),
            all_day=False, client=client, matter=matter, owner=owner, kind="event",
            status=g("status") or "scheduled",
            desc=(g("description") or "") +
                 ("" if client else "\n[client UNRESOLVED — untagged to avoid contamination]")))
    return items


def gather_from_case_actions(cur, client_filter, index):
    """Source C: case_actions — LandTek's planned actions with a due_date."""
    if not table_exists(cur, "case_actions"):
        return []
    cur.execute(
        "SELECT id, matter_code, description, status, due_date FROM case_actions "
        "WHERE due_date IS NOT NULL AND status <> 'confirmed'")
    items = []
    for cid, matter_code, desc, status, due in cur.fetchall():
        mi = index.get(str(matter_code).strip().lower()) if matter_code else None
        client = mi.client if mi else None
        if not _client_match(client, client_filter):
            continue
        items.append(Item(
            uid=f"action:{cid}", source="case_actions", source_id=str(cid),
            title=f"[{status}] {desc}"[:200], start=due, end=None, all_day=True,
            client=client, matter=(mi.label if mi else matter_code),
            owner=(mi.owner if mi else None), kind="action", status=status or "planned",
            desc=f"Case action ({status}). Source: execution_tracker case_actions."))
    return items


def gather_from_plays(cur, client_filter, index, by_code):
    """Source D: matter_plays — READY offensive moves, anchored to the matter's next
    deadline (a play has no date of its own). Only 'ready' plays with a real deadline."""
    if not table_exists(cur, "matter_plays"):
        return []
    cur.execute(
        "SELECT id, matter_code, play_code, title, readiness, suggested_action "
        "FROM matter_plays WHERE readiness = 'ready'")
    items = []
    for pid, matter_code, play_code, title, readiness, action in cur.fetchall():
        mi = by_code.get(str(matter_code).strip().lower())
        if mi is None or mi.next_deadline is None:
            continue  # no anchor date → not calendarable
        if not _client_match(mi.client, client_filter):
            continue
        items.append(Item(
            uid=f"play:{matter_code}:{play_code}", source="matter_plays",
            source_id=str(pid), title=f"READY: {title or play_code}"[:200],
            start=mi.next_deadline, end=None, all_day=True, client=mi.client,
            matter=mi.label, owner=mi.owner, kind="play", status="ready",
            desc=f"Ready offensive move (matter_plays). Anchored to matter deadline. "
                 f"Suggested: {(action or '')[:300]}"))
    return items


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
    ap.add_argument("--lookback-days", type=int, default=30,
                    help="include items due within this many days in the past (default 30)")
    ap.add_argument("--all-dates", action="store_true", help="sync every item, incl. old past ones")
    ap.add_argument("--daemon", action="store_true",
                    help="run mode: missing calendar creds exit 0 (quiet) so a timer "
                         "never marks the unit failed before the token is provisioned")
    ap.add_argument("--limit", type=int, default=None, help="cap items (debug)")
    args = ap.parse_args()

    env = load_env()
    calendar_id = args.calendar_id or env.get("LANDTEK_CALENDAR_ID", "primary")

    conn = db()
    cur = conn.cursor()
    ensure_schema(cur)
    conn.commit()

    index, by_code = load_matters_index(cur)
    clients_by_id = {}
    if table_exists(cur, "clients") and "client_code" in columns_of(cur, "clients"):
        cur.execute("SELECT id, client_code FROM clients WHERE client_code IS NOT NULL")
        clients_by_id = {cid: code for cid, code in cur.fetchall()}

    items = (gather_from_matters(cur, args.client, index, by_code)
             + gather_from_events(cur, args.client, index, clients_by_id)
             + gather_from_case_actions(cur, args.client, index)
             + gather_from_plays(cur, args.client, index, by_code))
    items = [i for i in items if i.start is not None]

    # Forward-looking by default: drop items whose date is older than the lookback
    # window so the calendar isn't cluttered with long-past events (still idempotent —
    # dropped items simply aren't (re)created). --all-dates keeps everything.
    if not args.all_dates:
        from datetime import timedelta
        try:
            from zoneinfo import ZoneInfo
            today = datetime.now(ZoneInfo(TZ)).date()
        except Exception:
            today = datetime.now(timezone.utc).date()
        cutoff = today - timedelta(days=args.lookback_days)

        def _d(it):
            return it.start.date() if isinstance(it.start, datetime) else it.start
        before = len(items)
        items = [i for i in items if _d(i) >= cutoff]
        dropped = before - len(items)
        if dropped:
            print(f"[calendar_sync] skipped {dropped} item(s) older than {cutoff} "
                  f"(use --all-dates to include)")
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
        msg = ("[calendar_sync] --apply requested but no CALENDAR_REFRESH_TOKEN / calendar "
               "auth. Mint a calendar-scoped token first (scripts/mint_calendar_token.py).")
        if args.daemon:  # degrade quietly so the timer unit never goes 'failed'
            print(msg + " Daemon mode: no-op this cycle.")
            conn.close()
            sys.exit(0)
        print(msg + " Aborting write.", file=sys.stderr)
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
