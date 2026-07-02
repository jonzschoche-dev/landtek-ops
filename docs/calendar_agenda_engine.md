# Calendar Agenda Engine — runbook

`scripts/calendar_sync.py` mirrors LandTek's live agenda out to Google Calendar so
every **client** and every **associate (legal counsel)** has their actions on a real
calendar that pushes agendas forward. Postgres stays the source of truth; Google
Calendar is a projection.

This is a **VPS** subsystem (the DB lives at `172.18.0.3` and the OAuth creds live in
`/root/landtek/.env`). It was authored on the Mac side and deploys via the git routine;
it has **not** been run against the live DB yet — do the dry-run first (Step 2).

## What it syncs

| Source | Tagging | Notes |
|---|---|---|
| `matters.next_deadline` / `next_event` | client_code + lead_counsel **native** | primary; fully tagged with client + owner + matter |
| `calendar_events` | resolved via `related_case → matters` | client/owner left **UNRESOLVED** (not guessed) when no join — protects the client-separation invariant |

Each Google event summary is prefixed `[CLIENT · MATTER · OWNER] title`. A stable
`landtek_uid` + `calendar_sync_map` content-hash make re-runs idempotent (patch what
changed, never double-create). `associates` is seeded with **Barandon** and **Botor**.

## Step 0 — one-time: mint a calendar-scoped OAuth token (the real blocker)

The existing `GMAIL_REFRESH_TOKEN` is scoped `gmail.readonly` only and will **not**
authorize calendar writes. Mint a token with `.../auth/calendar.events` once, reusing
the existing OAuth client (`/root/landtek/gmail_oauth_client.json`):

```bash
cd /root/landtek
python3 - <<'PY'
import json
from google_auth_oauthlib.flow import InstalledAppFlow
conf = json.load(open("gmail_oauth_client.json"))
flow = InstalledAppFlow.from_client_config(
    conf, scopes=["https://www.googleapis.com/auth/calendar.events"])
creds = flow.run_console()   # prints a URL → consent in browser → paste code back
print("\nCALENDAR_REFRESH_TOKEN=" + creds.refresh_token)
PY
```

> If `run_console()` is unavailable in the installed lib version, use
> `flow.run_local_server(port=0)` from a machine with a browser, or generate the
> token on the Mac and copy just the refresh-token string over.

Add the result to `/root/landtek/.env` (chmod 600 — never commit it):

```
CALENDAR_REFRESH_TOKEN=1//0g...        # from the step above
LANDTEK_CALENDAR_ID=primary            # or a dedicated LandTek calendar id
```

The OAuth client's consent screen must list the `calendar.events` scope. If it's a
"Testing" app, add the Google account as a test user first.

## Step 1 — deploy is already done via git

`scripts/calendar_sync.py` + this runbook ship in the same deploy. On the VPS just
`git pull --rebase` per the session-start routine.

## Step 2 — dry-run (safe; introspects the live schema, writes nothing)

```bash
cd /root/landtek
python3 scripts/calendar_sync.py                 # all clients
python3 scripts/calendar_sync.py --client MWK     # scope to one client
```

The dry-run self-provisions `associates` + `calendar_sync_map` (idempotent
`CREATE TABLE IF NOT EXISTS`), prints every item it *would* create/patch, and flags
same-day conflicts (≥2 items on one day). **Read this output** — it reveals any
schema mismatch (e.g. a missing matter-label column) with zero blast radius.

## Step 3 — apply (writes to Google Calendar)

```bash
python3 scripts/calendar_sync.py --apply
python3 scripts/calendar_sync.py --pull --apply   # reconcile manual gcal deletes back
```

`--apply` aborts cleanly if `CALENDAR_REFRESH_TOKEN` is missing.

## Step 4 — make it seamless (systemd timer) — after Step 3 looks right

Mirror the existing calendar/deadline timers (see `apply_deploy_276_agentic_calendar.py`):
a `calendar-sync.service` (oneshot: `calendar_sync.py --apply`) + `calendar-sync.timer`
every ~15 min, plus a nightly `--pull --apply`. Hold this until the manual `--apply`
run is verified so the daemon never amplifies a mistake.

## Guardrails baked in

- **Dry-run by default** — no `--apply`, no writes.
- **Degrade, don't crash** — missing creds/tables/columns downgrade the run, not break it.
- **No client contamination** — `client_code` only from a real `matters` join; otherwise
  the item is left untagged (`UNRESOLVED`), never prefix-guessed.
- **Idempotent** — `calendar_sync_map` + content-hash; re-runs patch only real changes.

## Known phase-2 items

- Two-way pull currently records **drift** (managed events cancelled by hand); it does
  not yet ingest brand-new manual Google events into `calendar_events`.
- Per-client / per-associate **separate calendars** (so a client sees only their own):
  today it's one calendar with `[CLIENT · MATTER · OWNER]` prefixes + extendedProperties
  (`client_code`, `owner`) for filtering. Splitting to per-owner calendars is a config
  add once the single-calendar flow is trusted.
- Wiring `case_actions` / `matter_plays` (client-facing operations) as a third source.
