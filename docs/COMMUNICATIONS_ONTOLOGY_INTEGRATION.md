# Communications Layer — Ontology Integration

**Purpose.** Model the multi-channel Communications domain (Telegram · Email · WhatsApp · Viber ·
Messenger), the unified channel bus, cross-channel identity, and the planned Platform Coordinator as a
first-class Layer III domain in `ONTOLOGY.md` — so client identity, channel routing, and external
exposure become *governed concepts with invariants*, not implicit implementation details.

**Scope discipline.** This is a staging/supporting document (meta-layer only). It proposes a §2.14
section + three invariants (A25–A27) for `ONTOLOGY.md`. **No code, scripts, or systemd units are
touched.** The canonical insertion into `ONTOLOGY.md` (with the version bump + change-log entry the
constitution requires) is a separate, sign-off-gated act — deliberately not done here, also to avoid a
merge collision with the concurrent edits to `docs/ontology_validator_spec.md`.

**Grounding note (honest).** Rowcounts below are carried forward from the counts already in `ONTOLOGY.md`
§2.7 / §8.6 (recently re-grounded). This session runs Mac-side and cannot reach the VPS Postgres, so
counts marked *(re-ground)* must be verified with `pg_stat_user_tables` on the VPS before the §2.14
section is committed — per the constitution's "never author counts from memory" checklist.

---

## 1. Current State Analysis

**What is built.** A unified channel bus already exists (deploy_114): `channels` → `channel_messages` →
`channel_audit`, with a cross-channel identity table `channel_users` (carrying `mapped_client_code`,
`role`, `authorized`). One Flask blueprint (`leo_tools/channel_adapters.py`) exposes inbound webhooks for
**whatsapp · viber · web · email · sms** plus a unified outbound `/api/channel/send`, and every inbound
flows through one router (`_route_to_onboard_or_agent → _forward_to_agent →` queue reply). Outbound sends
are governed by S14 (human-readable, one-point, no-double-tap) enforced in `scripts/tg_send.py`, logged to
`outbound_blocks` (~14,346 — the most-exercised control in the system).

**Per-channel readiness** (the five in scope):

| Channel | State | Evidence / gap |
|---|---|---|
| **Telegram** | 🟢 live | primary channel, Leo via n8n (`@LeoLandtekBot`); the reference implementation |
| **Email** | 🟢 inbound live / send held | deploy_654: `landtek-email-bridge.timer` runs `--inbound` (routes+queues, nothing leaves); `--send` unscheduled = the held external switch |
| **WhatsApp** | 🟡 armed, awaiting token | deploy_662: adapter (incl. Meta GET verify-challenge) + `whatsapp_channel_bridge.py` backlog drain + timer, token-gated idle-clean; needs WABA + Meta verification + public webhook |
| **Viber** | 🟡 armed, awaiting token | deploy_663: `viber_channel_bridge.py` reads `.env` live + exits 0 idle + timer; needs bot token (partners.viber.com) + public webhook |
| **Messenger** | ○ not built | no `/api/channel/messenger` endpoint; ~80% a clone of the working WhatsApp adapter; needs a Meta app + Page |

**The real gap (why this domain needs modeling).** Three things are *implicit* today and should be
governed concepts:

1. **The bus is not yet the single normalization point.** `channel_messages` is lightly populated
   (~20) while most live traffic still flows through older channel-specific stores — Telegram via
   `outbound_messages` (~1,898) / `leo_interactions` (~2,994), email via `gmail_messages`. The "one bus"
   is a target, not a finished fact.
2. **Cross-channel identity has a schema slot but no resolver.** `channel_users.mapped_client_code`
   *can* tie a person across channels to one client — but nothing populates or guards it, so the
   client-separation firewall (A5) does not yet extend to the comms identity layer.
3. **The Platform Coordinator does not exist** as a component. Routing, identity resolution, and
   per-channel health are scattered across adapters, bridges, and timers; nothing unifies them.

---

## 2. Canonical Concepts (definitions + state)

| Concept | Definition | State |
|---|---|---|
| **CommunicationChannel** | A supported medium a person can reach LandTek on / be reached through (Telegram, Email, WhatsApp, Viber, Messenger). Registered in `channels` with a provider, secret-ref, and active flag; per-channel readiness varies (live → armed → not-built). | 🟢 **modeled** (bus live; readiness per-channel) |
| **ChannelUser** | A person reachable on one or more channels, resolved to a **single client identity** (`client_code`). The cross-channel identity spine: same human on email + WhatsApp + Telegram = one `ChannelUser` bound to at most one client. | 🟡 **partial** — table exists (`channel_users.mapped_client_code`); resolver + separation guard not built |
| **ChannelMessage** | A single message, inbound or outbound, on any channel — normalized onto the bus (`channel_messages`), carrying direction, status (`sent`/`pending_*`/`failed`), and provider message-id. Outbound passes the S14 gate before reaching a human. | 🟢 **modeled** (bus + `outbound_messages` + `outbound_blocks`); normalization not yet universal |
| **PlatformCoordinator** | The central layer that (a) resolves cross-channel identity to one client, (b) routes inbound to onboarding/agent and drains outbound per channel, and (c) reports per-channel health — degrading gracefully (expected-idle vs real failure). Today its functions exist piecemeal (`_route_to_onboard_or_agent`, per-channel bridges/timers); **no unifying component exists.** | ○ **planned** — do not build without governance sign-off |
| **ExternalExposureGate** | The rule-set governing when a `ChannelMessage` may leave the system to an external party. Two mechanics: (i) email splits inbound (internal) from send (outward); (ii) for inline-send channels (WhatsApp/Viber/Messenger) **the provider token IS the switch** — provisioning it is an outward action. Rides the outward chokepoint (A21) + `internal_targets` classifier (A17) + `no-external-exposure-until-ready`. | 🟡 **partial** — guard exists in shadow; comms-specific gate not yet an invariant |

---

## 3. Mapping — concept → components → canonical home → status

| Concept | Canonical table(s) | Code / adapters / bridges | Recent deploys | Status |
|---|---|---|---|---|
| **CommunicationChannel** | `channels` (~9) · `channel_audit` *(re-ground)* | `channel_adapters.py` (whatsapp/viber/web/email/sms + `/api/channel/send`) · `tg_send.py` · `sync_telegram_webhook.py` · `viber_set_webhook.py` | 114 (bus) · 654 (email) · 662 (whatsapp) · 663 (viber) | 🟢 bus / per-channel varies |
| **ChannelUser** | `channel_users` *(re-ground)* · `authorized_users` · `client_access_tokens` (~7) | `_route_to_onboard_or_agent` · `onboard_client.py` · `_client_of()` resolver | 114 | 🟡 partial — no cross-channel resolver |
| **ChannelMessage** | `channel_messages` (~20) · `outbound_messages` (~1,898) · `outbound_blocks` (~14,346) · `leo_interactions` (~2,994) · `gmail_messages` | `email/viber/whatsapp_channel_bridge.py` (inbound feed + backlog drain) · S14 in `tg_send.py` | 654 · 662 · 663 | 🟢 live — normalization not universal |
| **PlatformCoordinator** | *(none — planned)* | scattered: adapters + bridges + `landtek-{email,whatsapp,viber}-bridge.timer` | — | ○ planned |
| **ExternalExposureGate** | `internal_targets` (4) · `outward_guard_config` · `outbound_blocks` | `outward_guard.py` (A21) · S14 sanitize/pace in `tg_send.py` · token-as-switch (per-channel `.env`) | 654 (email split) | 🟡 shadow + doctrine |

*Supersession note:* the older comms stores (`outbound_messages`, `leo_interactions`, `gmail_messages`)
are **not drift** — they are the live traffic today. The bus (`channel_messages`) is the *intended*
single normalization point; convergence onto it is the PlatformCoordinator's job. No 🔴 successor edge is
asserted here (that would be a §3 decision, deferred).

---

## 4. Proposed New Invariants (continuing the A-series from A24)

Three domain invariants, one per governance theme the objective names — client separation, external
exposure, coordinated routing. All honestly marked 🟡 **asserted / flagged** (schema supports them;
mechanical enforcement not yet built).

> **A25 — Cross-channel identity is client-scoped.** A `ChannelUser` resolves to **at most one**
> `client_code`; the same human reachable on multiple channels resolves to a single client identity, and
> no channel identity is mapped across two clients. *Extends A5/A16 to the comms identity layer.*
> 🟡 **asserted / flagged** — `channel_users.mapped_client_code` is the slot; no resolver or block-guard
> exists yet (the identity firewall does not yet reach comms).

> **A26 — Outbound comms is exposure-gated.** No `ChannelMessage` is delivered to an **external**
> recipient except through the outward chokepoint (A21) under `no-external-exposure-until-ready`.
> *Corollary — token-as-switch:* for inline-send channels (WhatsApp/Viber/Messenger) the provider
> credential **is** the external switch, so provisioning it is an outward action requiring sign-off;
> email is the one channel that separates inbound (internal) from send (outward).
> 🟡 **asserted / flagged** — email split is live (654); Meta/Viber are armed-but-tokenless by design;
> S14 + `outbound_blocks` + `outward_guard` partially enforce; block-mode dormant.

> **A27 — One bus, one guard.** Every comms event, inbound or outbound, on any channel normalizes onto
> the unified bus (`channels`/`channel_messages`), and any message reaching Jonathan passes the S14
> human-readability + no-double-tap pacing gate; **no adapter may send outside the bus-plus-guard path.**
> 🟡 **asserted / flagged** — S14 enforced in `tg_send` (14,346 blocks); adapters route through one
> onboarding path, but universal bus-normalization + a single PlatformCoordinator are ○ planned.

*(A25 and A26 are also **system-invariant instances** — client separation and outward-chokepoint —
inherited by this domain, made concrete for comms. A27 is a domain invariant.)*

---

## 5. Proposed Section for ONTOLOGY.md (draft — ready to paste as §2.14)

```markdown
## 2.14 Communications & Omnichannel — *one identity, many doors, one governed exit*

> **Definition.** The multi-channel reach layer: a person contacts LandTek (and Leo replies) over any
> supported channel (Telegram · Email · WhatsApp · Viber · Messenger), normalized onto a single bus,
> resolved to one client identity, and released outward only through the exposure gate. *(Elevates the
> terse §2.7 and the §8.6 operational cluster.)*

| Concept | Canonical home | State | Notes |
|---|---|---|---|
| **CommunicationChannel** | 🟢 `channels` (~9) → `channel_messages` | active | a supported medium; per-channel readiness varies — Telegram 🟢 live · Email 🟢 inbound-live/send-held (deploy_654) · WhatsApp 🟡 armed/tokenless (662) · Viber 🟡 armed/tokenless (663) · Messenger ○ not built |
| **ChannelUser** | 🟡 `channel_users.mapped_client_code` | partial | a person across ≥1 channel → **one** `client_code`; slot exists, resolver + separation-guard not built (A25) |
| **ChannelMessage** | 🟢 `channel_messages` · `outbound_messages` (~1,898) · `outbound_blocks` (~14,346) | active | inbound/outbound on the bus; older stores (`leo_interactions`, `gmail_messages`) still carry most live traffic — bus is the *intended* single normalizer, not yet universal (A27) |
| **PlatformCoordinator** | ○ *(none — planned)* | **NET-NEW** | cross-channel identity resolver + unified router + per-channel health daemon; today scattered across adapters + bridges + timers; **do not build without sign-off** |
| **ExternalExposureGate** | 🟡 `internal_targets` (4) · `outward_guard_config` · `outbound_blocks` | partial | when a message may leave the system; email splits inbound/send, inline-send channels gate on the token = the switch (A26); rides A21 + `no-external-exposure-until-ready` |

> ⚠️ **Token-as-switch (do not confuse the two send models).** Email separates inbound (internal, safe to
> schedule) from `--send` (outward). WhatsApp/Viber/Messenger send **inline** — gated only by whether the
> provider token + webhook are provisioned, so provisioning IS opening the channel (an outward action).
> ⚠️ **The bus is not yet the single point of truth** — `channel_messages` (~20) is light; convergence
> onto it is the PlatformCoordinator's remit. Don't assert the older comms stores as drift (§3) yet.
> **Enforcement:** S14 (human-readable · one-point · no-double-tap) in `tg_send.py` → `outbound_blocks`;
> outward funnels through `outward_guard` (A21, shadow). Client identity across channels rides A5 (A25).

*Components: `leo_tools/channel_adapters.py` (webhooks + `/api/channel/send`) · `tg_send.py` (S14) ·
`{email,whatsapp,viber}_channel_bridge.py` (feed + backlog drain) · `landtek-{email,whatsapp,viber}-bridge.timer`
· `outward_guard.py` · `_client_of()`. **Invariants: A25–A27.***
```

**Companion edits when §2.14 is committed:**
- **§4 registry** — append A25/A26/A27 rows (text above), honestly marked 🟡 asserted / flagged.
- **§8.6** — add a one-line pointer: *"Elevated to a Layer III model in §2.14."*
- **§9** — cross-reference the "Client Portal & Access" 🟡 row to §2.14 (comms is the reach layer that
  the portal token surface sits on).
- **Change log** — new `v0.10` entry: doc-only; three asserted invariants; no schema/enforcement change.
- **`ontology_check.py --coverage`** — must stay green (all named tables already exist; no new tables).

---

## 6. Governance Recommendations

1. **Extend the client firewall to comms (highest value).** A25 is the load-bearing one: today a person
   on two channels can be silently bound to two clients, or to none. The fix is a resolver that writes
   `channel_users.mapped_client_code` through `_client_of()` and a detector (later a block-trigger)
   mirroring V4 on `matter_facts`. Until then, comms client-separation is a *discipline, not a guarantee*
   — the same wording §5 uses for the corpus.
2. **Keep the exposure gate honest per send-model.** Document the token-as-switch distinction (A26) so
   no future agent "activates" a Meta/Viber channel thinking it's internal-only. The only inbound-safe /
   send-held channel is email; the rest are all-or-nothing on the token.
3. **Route every send through the guard before the coordinator is built.** A27 should be provable now via
   a `truth_tests/` assertion (every outbound row has a matching `outbound_blocks` decision or a clean
   S14 pass) — the mechanical floor, ahead of the coordinator.
4. **When the PlatformCoordinator graduates (○ → 🟢),** it inherits A5·A21·A24 for free (per §9
   graduation protocol) and must wire the outward chokepoint + identity resolver *before* any external
   channel goes live.

---

## 7. Flagged Items (need human decision / carry risk)

- **⛔ Identity-merge risk (A25).** No guard prevents a cross-client channel-identity mapping. Decision:
  build the resolver + detector now (shadow), or accept discipline-only until a second client onboards to
  a channel. *Recommend: shadow detector now — cheap, and comms is where a new external client first
  appears.*
- **⚠️ Bus convergence (A27).** Deciding whether `outbound_messages`/`leo_interactions` become 🔴-drift
  (superseded by `channel_messages`) is a §3 canonical-table decision with real migration weight — **not
  taken here.** Flagged for an explicit call.
- **⚠️ External exposure (A26).** Provisioning any WhatsApp/Viber/Messenger token is an outward action
  under `no-external-exposure-until-ready`; the armed timers are correct (idle until token) but the
  *decision to provision* stays with Jonathan.
- **Messenger build (○).** Not started; needs a Meta app + Page (Meta review can take days). Bundling it
  with WhatsApp (same Meta app, same webhook) is the efficient path — an operator decision, not a modeling
  one.
- **Rowcounts** marked *(re-ground)* must be verified on the VPS before commit.

---

## 8. Recommended Next Steps (prioritized)

1. **Sign-off to commit §2.14** into `ONTOLOGY.md` (v0.10) with A25–A27 — the modeling deliverable. Re-ground
   counts on the VPS first; sequence after the cowork agent's `ontology_validator_spec.md` edits land to
   avoid a collision.
2. **Add the A27 mechanical floor** — a `truth_tests/` assertion that every outbound comms row rode the
   S14 guard (cheap, provable today; drives A27 documented → asserted).
3. **Author the A25 shadow resolver spec** in `docs/ontology_validator_spec.md` (a V-check on
   `channel_users` mirroring V4) — *spec only*, no code, matching the V6-geometry staging pattern.
4. **Defer PlatformCoordinator (○)** until at least one more channel is provisioned — it earns a schema +
   a §2.N graduation then, not before (per §9).
5. **Hold Messenger** for a bundled Meta provisioning pass with WhatsApp.

---

*Staging document — meta-layer only. Nothing here changes code, schema, or enforcement. The canonical
§2.14 insertion + version bump is gated on Jonathan's sign-off.*
