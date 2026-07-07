# DIRECTIVE — Integrate the Calendar/Notification Agent into the Ontology Layer

**To:** the designated ontology-integration agent (the authorized `ONTOLOGY.md` pusher)
**From:** calendar-agent build session (2026-07-07)
**Status:** analysis complete; edits drafted but **NOT applied** — ONTOLOGY.md writes are ceded to you.
**Scope discipline:** meta-layer only (Ontology / Governance / Supervision). Doc-only edits. No enforcement without operator approval. Append-only invariants.

---

## 0. Why this is a handoff
ONTOLOGY.md advanced **v0.7 → v0.16** during analysis (concurrent comms/omnichannel formalization). The original draft (v0.7-era) would now **duplicate or conflict** with the new **§2.14 Communications domain (invariants A25–A31)**. Re-anchoring + reconciliation must be done by you against the **current** file.

**Before editing:** re-read the *current* `§8.16`, `§2.14`, and the `A25–A31` invariant block. Line anchors below were NOT re-verified against v0.16 — treat the draft text as content to adapt, not a blind patch.

---

## 1. Objective
Register the Calendar/Notification agent (`scripts/calendar_sync.py` + `scripts/assistant_cadence.py`) as a **governed operational surface** — mapped in **§8**, **NOT provenance-gated** (it is comms/process, not truth-claims; gating it would be the category error §8 already warns against).

---

## 2. Mandatory reconciliation with §2.14 (the key constraint)
The calendar agent's **DeliveryChannel** and **NotificationGovernance** concepts are now **instances governed by §2.14** — map them by reference, do NOT restate S14/exposure logic:

| Calendar concept | Governed by (existing §2.14 invariant) |
|---|---|
| DeliveryChannel (Telegram / Email) | **A26** (outbound exposure-gated; token-as-switch) + **A27** (one bus, one S14 guard) |
| Client-isolation on outbound | **A25** (ChannelUser → ≤1 client_code) applied to the notification surface |
| External-send-held (self-only email, no external drain) | **ExternalExposureGate** / **A26** |

---

## 3. Changes to make (A–D)

### (A) Expand §8.16 → "Calendar / Notification & Scheduling surface"
Register the calendar-specific concepts **§2.14 does not cover** (AgendaSource, AgendaItem, CalendarSync, ReminderCadence), reference A25–A27 for the channel/governance concepts, and mark InboundCapture held. **Draft block (adapt anchors + cross-refs to current file):**

> ### 8.16 Calendar / Notification & Scheduling surface — *the governed outbound agent*
> `calendar_events` · `calendar_sync_map` · `calendar_targets` · `associates` (event-owner registry — Barandon/Botor) · `assistant_nudge_log` · `surfaced_deadlines` · `deadline_alerts` · `calendar_briefs_sent` · `email_briefs_sent` · `action_items` · `pending_questions` · `pending_inquiries`. **🟢 ACTIVE.** Two agents: **`calendar_sync`** (Postgres→Google Calendar projection; idempotent via `calendar_sync_map` content-hash; multi-calendar routing via `calendar_targets` with strict per-client isolation) and **`assistant_cadence`** (dual-channel reminder briefs — Telegram + Email — over the agenda spine; dedup via `assistant_nudge_log`). Reads `matters`/`case_actions`/`calendar_events` (the agenda spine); writes to **external Google Calendar** + Gmail/Telegram egress.
>
> **Canonical concepts (a governed comms/process surface — mapped, NOT provenance-gated):**
> | Concept | Canonical home | Notes |
> |---|---|---|
> | **AgendaSource** | `matters`(next_deadline/next_event) · `case_actions` · `calendar_events` + Google Calendar | the spine is source of truth; Google Calendar is a projection + manual-edit reconcile |
> | **AgendaItem** | a normalized gather over AgendaSource (no single table) | tagged `[client·matter·owner]`; `matter_plays` EXCLUDED from spoken reminders (strategy ≠ commitment) |
> | **CalendarSync** | `calendar_sync` + `calendar_sync_map` + `calendar_targets` | idempotent, separation-safe; external target = Google Calendar |
> | **ReminderCadence** | `assistant_cadence` + timers + `assistant_nudge_log` | morning 07:00 / day-before 18:00 (Manila); silent-when-nothing; one-message-per-run |
> | **DeliveryChannel** | Telegram (`tg_send`→`outbound_messages`/`outbound_blocks`) · Email (Gmail send, self-only) | governed by **A26/A27** (§2.14); each independently gated (`ASSISTANT_CADENCE_LIVE` / `ASSISTANT_EMAIL_LIVE`) |
> | **NotificationGovernance** | S14 (`outbound_blocks`) + code guards; see **A25–A27** | who/what may be notified, under what conditions |
> | **InboundCapture (Sponge)** | 🌱 HELD — would write `channel_messages`(dir=in)+`chat_notes` | not built; bot-channel decision parked |
>
> **Governance (code-asserted; truth_tests PROPOSED — flagged, not added):**
> - **Client isolation on outbound** — a per-client calendar target receives ONLY positively-resolved items of that client (`match_target` strict); `[SEPARATION-ABORT]` skips the whole target if any foreign-client item matches. This is **A25/A5 applied to the notification surface**, enforced **in code** — not yet a DB trigger or truth_test.
> - **External-send discipline** — Email is **self-only** (`JONATHAN_EMAIL` hard-coded); general `email_channel_bridge --send` external drain stays held ([[no-external-exposure-until-ready]]); external calendar sharing (Allan/Paracale) parked. Gmail token now carries `send`+`readonly` (old backed up).
> - **Fail-safe defaults** — `calendar_sync` dry-run by default; timers self-guard (install disabled until the matching `*_LIVE` flag); `--daemon`/missing-token → exit 0 (never trips `systemctl --failed`).
> - **Idempotency** — `calendar_sync_map (landtek_uid, gcal_calendar_id)` + content-hash.
>
> **DEAD-PRODUCER disposition (not neglect):** `agent_concept_map --triage` flags `calendar_sync_map`/`calendar_targets`/`associates`/`assistant_nudge_log` as DEAD-PRODUCER. **False positive** — same read-regex blind spot §8.19 records for `client_access`: consumers are **external** (Google Calendar consumes `calendar_sync_map` event-ids) or **in-module** (`assistant_cadence` self-reads `assistant_nudge_log` for dedup via `SELECT 1 FROM assistant_nudge_log`; `calendar_sync` self-reads its map for idempotency — neither read seen by the per-file scan). Retained by disposition.

### (B) Name two populated-imminent tables — THE MECHANICAL TRIGGER
`calendar_targets` and `assistant_nudge_log` are **unnamed** in ONTOLOGY.md and currently **empty** (so `--coverage` passes today), but will trip `ontology_check.py --coverage` (exit-1 + `holes_findings` `ontology_coverage_gap`) on first populate:
- `assistant_nudge_log` → first non-empty scheduled brief (~2026-07-17, when agenda enters the 7-day window).
- `calendar_targets` → first per-client calendar seeded.

Draft (A) names both. **This is the concrete reason to push now, not later.**

### (C) §8.19 — correct `calendar_sync` disposition
Change from "out of lane — activate-or-retire call" → **ACTIVATED** (calendar sync + dual-channel cadence live, 2026-07) → now the governed notification surface (§8.16); its DEAD-PRODUCER flag is the known external/in-module consumer blind spot, retained by disposition.

### (D) §8.18 + changelog
Re-home `associates` (calendar event-owner registry) from "Client extra" → referenced in §8.16. Add a **v0.17 changelog** entry recording: §8.16 rewrite, 2 tables named, notification governance recorded (referencing A25–A27), enforcement scope unchanged, truth_tests proposed-not-added.

---

## 4. Verification (mechanical; run on VPS via `ssh landtek`)
1. `python3 scripts/ontology_check.py --coverage` → must stay **exit-0, N/N named**.
2. `python3 scripts/agent_concept_map.py --triage` → confirm the `calendar_sync`/`assistant_cadence` disposition text matches output.
3. Deploy gate green (no truth_test regressions).
4. Push via the git routine (`scripts/landtek_git_routine.sh deploy NNN ...`) — it `pull --rebase`s before push, safe against the concurrent editor.

---

## 5. Flagged items — operator-gated, DO NOT auto-decide
1. **🔴 NEW gap surfaced by §2.14:** `assistant_cadence`'s **email delivery bypasses the channel bus AND S14** — `email_send()` calls Gmail directly, so email notifications are **not** logged to `outbound_messages`/`outbound_blocks` and **not S14-paced** (Telegram *is*, via `tg_send`). Under **A27** (one bus, one S14 guard) this is a partial-satisfaction gap. Routing email through the bus/S14 is a real code change — **escalate to the operator**, do not silently "fix."
2. **🟡 Client-isolation on outbound is code-only.** Propose (don't add without approval) a `calendar_targets` strict-config truth_test.
3. **🟡 `calendar_targets` empty** → isolation path untested in prod; add a separation truth_test **before** any per-client calendar is seeded.
4. **Sponge** governance undefined; specify client-attribution rule (inherit client only from a validated matter tag) before building.

---

## 6. Do NOT
- Provenance-gate the notification surface (category error, §8).
- Enforce new invariants (V-triggers / deploy-gating tests) on the notification/external surface without operator approval — this is the high-risk external/user-notification boundary.
- Renumber existing invariants (append-only, per the A-series discipline).

---

## 7. Source artifacts (ground truth for this directive)
- Agents: `scripts/calendar_sync.py` (deploys 648–651), `scripts/assistant_cadence.py` (deploys 656–658).
- Runbook: `docs/calendar_agenda_engine.md`; design: `docs/scheduling_assistant_design.md`.
- Live tables (2026-07-07): `calendar_sync_map`=29, `calendar_events`=17, `surfaced_deadlines`=82, `associates`=2, `calendar_targets`=0, `assistant_nudge_log`=0.
- Timers live: `landtek-assistant-{morning,evening}{,-email}.timer` (both channels `*_LIVE=1`); `landtek-calendar-sync{,-pull}.timer`.
- Related ontology memory: [[project-ontology-layer]], [[project-omnichannel-status]], [[client-separation-invariants]], [[no-external-exposure-until-ready]].
