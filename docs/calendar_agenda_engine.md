# Calendar Agenda Engine — runbook

`scripts/calendar_sync.py` mirrors LandTek's live agenda out to Google Calendar so
every **client** and every **associate (legal counsel)** has their actions on a real
calendar that pushes agendas forward. Postgres stays the source of truth; Google
Calendar is a projection.

This is a **VPS** subsystem (the DB lives at `172.18.0.3` and the OAuth creds live in
`/root/landtek/.env`). It was authored on the Mac side and deploys via the git routine;
it has **not** been run against the live DB yet — do the dry-run first (Step 2).

## What it syncs

Four sources, all resolved through one `matters` index so client/owner are never guessed:

| Source | Kind | Client / owner | Notes |
|---|---|---|---|
| `matters.next_deadline` | deadline | native (`client_code`, `next_event_owner`/`lead_counsel`) | fully tagged |
| `calendar_events` | event | client via `client_id → clients`; matter/owner via `related_case → matters` | left **UNRESOLVED** (untagged) when no real join — protects client-separation |
| `case_actions` (with `due_date`, not confirmed) | action | via `matter_code → matters` | LandTek's planned actions |
| `matter_plays` (`readiness='ready'`) | play | via `matter_code → matters` | anchored to the matter's `next_deadline`; skipped if no anchor date |

Each Google event summary is prefixed `[CLIENT · MATTER · OWNER] title`, with
`client_code`/`owner`/`kind` in extendedProperties for filtering. A stable
`landtek_uid` + `calendar_sync_map` content-hash make re-runs idempotent (patch what
changed, never double-create). `associates` is seeded with **Barandon** and **Botor**.

**Forward-looking by default:** items older than 30 days are skipped (`--lookback-days N`
/ `--all-dates` to override). Validated against the live DB 2026-07-02: 29 forward
items across MWK-001 + Paracale-001, 8 conflict-days flagged, client separation intact.

## Step 0 — one-time: mint a calendar-scoped OAuth token (the real blocker)

The existing `GMAIL_REFRESH_TOKEN` is scoped `gmail.readonly` only and will **not**
authorize calendar writes. Mint a `calendar.events` token with the turnkey helper
(reuses the existing OAuth client `gmail_oauth_client.json`):

```bash
cd /root/landtek
python3 scripts/mint_calendar_token.py --console   # headless VPS: prints URL, paste code
# or, from a machine with a browser:
python3 scripts/mint_calendar_token.py             # opens the consent page
```

Add its output to `/root/landtek/.env` (chmod 600 — never commit it):

```
CALENDAR_REFRESH_TOKEN=1//0g...        # from the helper
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

## Step 4 — make it seamless (systemd timer)

```bash
python3 migrations/apply_deploy_649_calendar_sync_timer.py
```

Installs a push timer (every 15 min, `--apply --daemon`) + a nightly pull-reconcile.
**Self-guarding:** it only *enables* the timers when `CALENDAR_REFRESH_TOKEN` is set —
before that it installs the units but leaves them disabled, so nothing ever shows as a
`failed` unit (honors the `systemctl --failed == 0` invariant). Re-run it after the
token is in place to flip the timers on. `--daemon` mode makes a missing token a clean
no-op (exit 0), not a failure.

## Guardrails baked in

- **Dry-run by default** — no `--apply`, no writes.
- **Degrade, don't crash** — missing creds/tables/columns downgrade the run, not break it.
- **No client contamination** — `client_code` only from a real `matters` join; otherwise
  the item is left untagged (`UNRESOLVED`), never prefix-guessed.
- **Idempotent** — `calendar_sync_map` + content-hash; re-runs patch only real changes.

## Multi-calendar routing (`calendar_targets`)

The engine pushes one agenda to **N calendars**, each row in `calendar_targets`:

| column | meaning |
|---|---|
| `gcal_calendar_id` | the Google calendar to push to |
| `client_filter` | `NULL` = master ops calendar (everything, incl. UNRESOLVED); a value = client calendar |
| `strict` | client calendars set `TRUE` → **only items positively resolved to that client**; UNRESOLVED and other-client items are excluded |

Intended topology (internal-first):
- **LandTek Ops** — `client_filter=NULL` — the internal cockpit, shared with the team (Kristyle).
- **Paracale — Inocalla** — `client_filter='Paracale'`, `strict=TRUE` — shared with Allan; carries **only** Paracale-001 items.

**Separation is enforced by construction**, not by trusting the tag: a client target is
fed by its filter and additionally guarded by a `[SEPARATION-ABORT]` assertion that skips
the whole target if any foreign-client item ever matches. `calendar_sync_map` is keyed by
`(landtek_uid, gcal_calendar_id)`, so the same item can live on both the ops and client
calendars independently and idempotently. Proven 2026-07-02: a strict Paracale target
received 1 item (the resolved Paracale one); the MWK `Civil Case 26-360` / `Owner` /
`CV-6839` unresolved items were excluded.

## Known phase-2 items

- Two-way pull currently records **drift** (managed events cancelled by hand); it does
  not yet ingest brand-new manual Google events into `calendar_events`.
- Auto-provisioning of the calendars + ACL sharing needs the broader `calendar` scope
  (create/share); the every-cycle engine only needs `calendar.events`.
