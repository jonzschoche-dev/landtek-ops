# Scheduling Assistant — design draft

**The verdict that produced this:** the calendar sync engine we shipped (deploys 648–651)
is a good *data spine* but runs on **computer cadence** — a 15-min cron mirroring DB rows
onto a grid. The commercial product must interact in the **cadence of a human**. So: keep
the spine, build a conversational, anticipatory **assistant** on top of it. The Google
Calendar becomes the shared *canvas*; the **assistant is the product**.

This is subordinate to `MASTER_PLAN.md`. It reuses existing scaffold heavily — it is
mostly *wiring*, not greenfield.

---

## 1. Principle → what "human cadence" concretely means

A human scheduler doesn't dump a grid. They **talk, anticipate, nudge at the right
moment, track who-owes-what, and reschedule in cascades.** So the assistant must be:

- **Event- and policy-timed**, never a fixed cron for *communication* (the 15-min sync
  stays as a silent heartbeat; the *talking* is separate and deliberate).
- **Two-way**: natural language in → action + confirmation out.
- **Anticipatory**: works backward from a hard date; blocks prep; chases the unconfirmed.
- **Commitment-aware**: every obligation has an owner and a status; it drives each to closure.
- **One thing at a time, plain language** (S14) — it speaks like a person, not a bot.

---

## 2. Architecture (components — REUSE marked ✅, NEW marked 🔨)

```
   inbound (Telegram)                          outbound (Telegram → you only, v1)
        │                                                 ▲
        ▼                                                 │
 ┌──────────────┐   ┌───────────────┐   ┌──────────────┐  │
 │ inbound      │──▶│ channel_bus   │──▶│ assistant     │──┘  via tg_send (S14) ✅
 │ handler   🔨 │   │ channel_msgs ✅│   │ core       🔨 │
 └──────────────┘   └───────────────┘   └──────┬───────┘
                                               │ reads/writes (confirm-gated)
                    ┌──────────────────────────┼───────────────────────────┐
                    ▼                          ▼                           ▼
             ┌────────────┐            ┌────────────────┐          ┌───────────────┐
             │ agenda     │            │ commitment     │          │ cadence       │
             │ spine    ✅│            │ ledger      🔨 │          │ engine     🔨 │
             │ calendar_  │            │ (extends       │          │ (speak-policy)│
             │ sync +     │            │  case_actions) │          │               │
             │ matters …  │            └────────────────┘          └───────────────┘
             └────────────┘
                    │
                    ▼  push (idempotent, separation-safe)
             Google Calendar (shared canvas) ✅
```

- **Agenda spine** ✅ — `calendar_sync.py` + `matters` / `case_actions` / `matter_plays`.
  Source of truth for obligations; already grounded + client-separation-safe.
- **Channel bus** ✅ — `channel_messages` (has `direction`, `text_content`, `reply_to_id`,
  `metadata`, `status`), `channel_users`, `channels`, `outbound_messages`, `outbound_blocks`.
  A real conversation store — inbound + outbound.
- **Outbound** ✅ — `tg_send.py` (S14: plain, one-at-a-time, no double-tap to you).
- **Brain** ✅ — local qwen 7B/14B via the Mac reverse-tunnel (creditless, offline-first);
  frontier optional for hard NL. Deterministic fast-paths first (see §4).
- **Inbound handler** 🔨 — a standalone `getUpdates` loop → writes `channel_messages`
  (`direction='in'`). Owns the assistant's Telegram intake independently of n8n Leo
  (which is OFF — no contention).
- **Assistant core** 🔨 — perceive → parse intent → resolve target → plan → **confirm** →
  act on the spine. Writes are always proposed-then-confirmed (human-in-loop).
- **Cadence engine** 🔨 — the "when + how to speak" policy (§3).
- **Commitment ledger** 🔨 — extend `case_actions` (already `planned→…→confirmed`) with
  `owner`, `due`, `last_nudge_at`, `awaiting` (who owes) → drives nudges.

---

## 3. The cadence policy (the crux — what makes it feel human)

The engine decides *whether to speak at all*, and if so, one message:

| Trigger | Behavior |
|---|---|
| **Morning brief** 07:00 Manila | "Today/this week," **only if** there's something; else silence |
| **Day-before** a hearing/hard deadline | single reminder + the one prep item that's open |
| **T-minus countdown** on a filing deadline | work-backward: create a prep block, remind at T-7/T-3/T-1 |
| **Slip alert** | obligation past due & unconfirmed → "this slipped — rebook or drop?" |
| **Follow-up chaser** | a commitment owed by counsel/client, unconfirmed N days → "want me to nudge Barandon?" |
| **Quiet hours + rate limit** | never chain (S14 no-double-tap); one point, waits for your reply |

Every message is plain, one point, and usually ends with an actionable choice
("Reply 1 to hold Thu 9am, 2 to pick another time").

---

## 4. Two-way intent loop (concrete)

Inbound *"move the Botor meeting to next Tuesday"* →
1. **Parse** intent → `{action: reschedule, target: <resolve>, when: next Tue}`.
   Deterministic fast-paths (keywords: move/reschedule/confirm/done/free/snooze) handle the
   common 80%; qwen handles the messy rest. Degrade: if brain down, "didn't catch that —
   try 'move <thing> to <date>'".
2. **Resolve target** against the spine (which obligation?). Ambiguous → ask, never guess.
3. **Check conflicts** (reuse the existing conflict detector).
4. **Propose + confirm** — "Move guardianship-hearing prep to Tue Jul 8, 9am? Reply yes."
   **Never writes without confirmation.**
5. On **yes** → write to the spine (`matters.next_event/next_deadline` or `case_actions`) →
   `calendar_sync` reflects it (or push immediately) → confirm "done."

Supported v1 intents: **query** ("what's on / am I free before the hearing?") and
**reschedule/confirm** (propose→confirm→write). Everything else → "I can't do that yet."

---

## 5. Safety / grounding (non-negotiable — reuses existing discipline)

- **No hallucination** — only real obligations from the spine; never fabricate a date or a
  confirmation (provenance discipline).
- **Confirm-before-write** — the assistant *proposes*; you *decide*. No autonomous external
  action; it never files or sends to third parties ([[landtek-not-a-law-firm]]).
- **S14** — plain, one-at-a-time, no double-tap; violations log to `outbound_blocks`.
- **Client separation** — scoped per client/matter; the spine already enforces it.
- **Internal-only first** — v1 talks to **you** (chat 6513067717) only; external client
  channels stay parked ([[no-external-exposure-until-ready]]).

---

## 6. Reuse vs build (honest scope)

**Reuse (already live):** agenda spine, channel bus (`channel_messages` I/O), `tg_send`
(S14), `matters`/`case_actions`, `agent_audit`, local qwen, the conflict detector.

**Build NEW (small, well-scoped):**
- `assistant_inbound.py` — getUpdates → `channel_messages(direction='in')`.
- `assistant_core.py` — perceive→parse→resolve→propose→confirm→act.
- `cadence_engine.py` — the speak-policy timer (§3).
- commitment fields on `case_actions` (+ a `commitments` view over matters+case_actions).

---

## 7. First increment (v1 — ship + test on ourselves)

The smallest thing that actually *feels* human:
1. **Inbound handler** live (standalone getUpdates → channel_messages).
2. **Cadence v1**: morning brief + day-before nudge from the spine, S14-clean, to you only.
3. **Two-way, two intents**: (a) "what's on / am I free…"; (b) "reschedule/confirm X" with
   propose→confirm→write-to-spine (calendar updates within the cycle).
4. **Commitment status** on `case_actions` (confirmed/slipped) → a daily "needs your reply."

**Explicitly NOT in v1:** external channels, autonomous writes, WhatsApp/Leo, full NL
coverage, reschedule *cascades* (dependencies) — those are v2.

---

## 8. Example (what "human cadence" looks like)

```
07:00  Assistant → you:
   Morning. 3 things this week. Biggest: Jul 27 guardianship hearing (Botor) — the
   publication proof isn't confirmed yet. Want me to chase it?

09:14  You → Assistant:  move the botor prep to next tue
09:14  Assistant → you:
   Guardianship-hearing prep → Tue Jul 8, 9am? (frees Thu, no conflicts) Reply yes.
09:15  You → Assistant:  yes
09:15  Assistant → you:  Done. Moved to Tue Jul 8, 9am. Calendar updated.

Jul 26 18:00  Assistant → you:
   Tomorrow: guardianship hearing, RTC Br 41 Daet, 8:30am. Publication proof still
   unconfirmed — this is the last day to fix it.
```

---

## 9. Risks / honest unknowns

- **NL reliability** on local qwen for messy intents → deterministic fast-paths +
  confirm-before-write contain the blast radius.
- **Webhook contention** if Leo/n8n is ever reactivated → need a router (Leo is off now).
- **Reschedule cascades** (obligation dependencies) — real value, but v2.
- **Manual-Google-Calendar-edit write-back** — the phase-2 pull-ingest (more relevant once
  anyone can edit a calendar).
