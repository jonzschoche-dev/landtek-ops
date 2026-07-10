# COMM-AGENT-MAX — Phase 0 Design & First Migration (executor: Fable)

**Scope of this doc.** The grounded Phase-0 output for the COMM-AGENT-MAX directive: current-state
assessment, the exact schema + architecture delta, the ready-to-apply first migration (read-only
interaction spine), the `entity_id` unblock draft (A25 Part 2), and the prompts for the Ontology +
Supervisory agents. **Nothing here is applied yet** — this is the propose/greenlight step. A technical
design spec (sibling to `docs/ontology_validator_spec.md`), not a roadmap; the north star stays in
`MASTER_PLAN.md`. **Zero Aug-12 risk: everything is additive, shadow-first, reversible.**

---

## 1. Current state — grounded live (2026-07-09, VPS `n8n-postgres-1`)

**Live & working:**
- Serving layer up: `leo_tools` on :8765, `channel_adapters.py` mounted (`/api/channel/*` responding).
- **Telegram** live (n8n/Leo, S14-enforced). **Email inbound** live (deploy_654; `landtek-email-bridge.timer`).
- **PlatformCoordinator v1** (`scripts/platform_coordinator.py`) + `landtek-coordinator.timer` running;
  `channel_audit` = 3 activation rows (A30 surface real).
- 3 bridge timers running (email/whatsapp/viber), none failed.
- **V7 (A25 Part 1) APPLIED IN SHADOW** — `ontology_validator_config.V7='log'`, `v_ontology_channel_cross`
  returns **0** (clean). Validators live: V1/V3/V4/V9/V10 `block`; V5/V6/V7/V8 `log`.
- **Real stakeholders already flowing in:** `channel_users` = 9 rows; email (channel 4) is capturing
  Barandon-office people (Litigation Division, Loida Macale, AB Law Admin, Pamela Cruz) in
  `awaiting_classification` — a live onboarding flow (`onboarding_state`, `approved_role`, `approved_scope_case`).

**The real gaps (grounded, not assumed):**
| Gap | Evidence | Consequence |
|---|---|---|
| **Bus not universal (A27)** | `channel_messages`=52 vs `outbound_messages`=1,899 vs `leo_interactions`=2,994 | 97% of interaction history is off-bus → no unified relationship memory |
| **No person-key (A25 Part 2)** | `channel_users` has NO `entity_id`; still `UNIQUE(channel_id, channel_user_id)` | can't join the same human across channels → cross-channel identity unprovable |
| **Stakeholders unclassified** | 5 email identities `mapped_client_code=NULL` | the relationship graph + resolver have nothing to bind to yet |
| **No relationship memory** | no interaction-history view; `conversation_context` **was DROPPED** (deploy_804) | style/preferred-platform/open-loop/next-action all impossible today |
| **Specialist prep agents absent** | grep: no LawyerPrepAgent/StylePersonalizer/etc. | prep packages still manual |

> ⚠️ **Ontology drift to flag to the ontology desk (I'm frozen from editing ONTOLOGY.md):** §2.14's
> `UnifiedClientPersona` cites `conversation_context`/`conversation_chunks` as its canonical home, but
> **both were dropped in deploy_804.** The persona-memory home must be re-pointed (candidate: a new
> `comms_interactions` store or the views below). Handed to the Ontology agent (§5 prompt).

**Honest scoping.** The directive's vision (sentiment, NPS proxy, self-improving style AI, PWA, mining
integration) is a multi-month program. Phase 0–1 build the **spine that makes all of it possible**: one
queryable interaction memory + one person-key + the coordinator as the real chokepoint. Everything
"agentic/10×" rides on that spine. We build the spine first, measured, reversible.

---

## 2. Architecture delta — the spine

```
                         ┌─────────────────────────────────────────────┐
  inbound (any channel)  │              PlatformCoordinator             │  outbound (governed)
  ──────────────────────▶│  resolve identity → route → drain → audit    │──────────────────────▶
   TG·Email·WA·Viber·MSG │  A25 (entity_id) · A26 token-switch · A27 bus │   S14 + outward_guard
                         └───────────────┬─────────────────────────────┘
                                         │ writes/reads
             ┌───────────────────────────┼───────────────────────────────┐
             ▼                           ▼                                ▼
      channel_users               INTERACTION SPINE                 channel_audit
   (+entity_id person-key)   v_comms_interactions (unifies the 3     (activation/exposure,
      A25 client-scope        stores) → v_comms_relationship          A30 — live)
                              (per-party memory: cadence, channels,
                               client, open-loop, next-best-action)
```

**Design decisions (recommended defaults, greenlight in §6):**
1. **Relationship graph = VIEWS FIRST, promote to tables only when proven.** Start with read-only views
   over the 1,899 + 2,994 + 52 rows we already have — zero schema risk, instantly queryable, trivially
   dropped. Promote `v_comms_relationship` to a materialized table + write-path only after it earns its keep.
2. **Person-key = `channel_users.entity_id` → `entities`** (the A25 Part 2 unblock, mirrors the
   `parcels.client_code`/deploy_733 pattern). Additive, nullable, forward-filled by the coordinator's
   resolver. **Greenlight-gated** (§6.1).
3. **Coordinator stays the governance layer above the bridges** — it does not replace n8n/Telegram or the
   bridges; it resolves identity, unifies memory, audits, and (Phase 2) routes. No rebuild.

---

## 3. First migration — interaction spine (READY, idempotent, reversible; NOT applied)

Pure read-only views. No tables, no triggers, no writes. `--rollback` = `DROP VIEW`. Needs a dry-run
against live before apply (column casts verified against the grounded schemas below).

```sql
-- migrations/deploy_NNN_comms_interaction_spine.sql  (READ-ONLY VIEWS — additive, reversible)
-- Unifies the three comms stores into one interaction timeline + a per-party relationship rollup.
-- Grounded schemas: channel_messages(channel_id,channel_user_id,direction,text_content,status,sent_at);
--   leo_interactions(channel,sender_id,sender_name,question,reply_text,case_file,timestamp);
--   outbound_messages(chat_id,recipient_name,content_preview,source,success,sent_at).

CREATE OR REPLACE VIEW v_comms_interactions AS
  -- the unified bus (authoritative going forward)
  SELECT 'channel_messages'::text AS src, cm.id::text AS ref,
         c.name AS channel, cm.channel_user_id AS party_key,
         cm.direction, cm.sent_at AS ts,
         left(cm.text_content, 240) AS preview, cm.status AS meta
  FROM   channel_messages cm JOIN channels c ON c.id = cm.channel_id
UNION ALL
  -- the rich Leo turn history (2,994) — the real relationship record today
  SELECT 'leo_interactions', li.id::text,
         li.channel, li.sender_id,
         'exchange', li.timestamp,
         left(coalesce(li.question, li.reply_text), 240), li.case_file
  FROM   leo_interactions li
UNION ALL
  -- legacy Telegram outbound log (1,899)
  SELECT 'outbound_messages', om.id::text,
         coalesce(om.source,'telegram'), om.chat_id,
         'outbound', om.sent_at,
         left(om.content_preview, 240), (CASE WHEN om.success THEN 'sent' ELSE 'failed' END)
  FROM   outbound_messages om;

-- per-party relationship memory (the agentic substrate): cadence, reach, client, recency
CREATE OR REPLACE VIEW v_comms_relationship AS
SELECT party_key,
       count(*)                                   AS interactions,
       count(*) FILTER (WHERE direction='inbound') AS inbound,
       min(ts)                                    AS first_seen,
       max(ts)                                    AS last_seen,
       array_agg(DISTINCT channel)                AS channels_used,
       max(meta) FILTER (WHERE meta LIKE 'MWK%' OR meta LIKE 'PAR%' OR meta LIKE '%-001') AS client_hint
FROM   v_comms_interactions
WHERE  party_key IS NOT NULL
GROUP  BY party_key;

-- rollback: DROP VIEW IF EXISTS v_comms_relationship; DROP VIEW IF EXISTS v_comms_interactions;
```

**What this unlocks immediately (measurable):** "show every interaction with Loida Macale across channels,
newest first" and "who has an open inbound with no reply in >48h" become one-query answers — the foundation
for FollowUpCloser + StylePersonalizer, from data we already have.

---

## 4. A25 Part 2 unblock — `channel_users.entity_id` (DRAFT, greenlight-gated)

Mirrors the V6/deploy_733 pattern exactly. Additive, nullable, self-testing, `--rollback`.

```sql
-- migrations/deploy_NNN_channel_users_entity_id.sql  (ADDITIVE — DO NOT APPLY without greenlight §6.1)
ALTER TABLE channel_users ADD COLUMN IF NOT EXISTS entity_id integer REFERENCES entities(id);
-- forward-filled by platform_coordinator.py --resolve (entity-resolution path); nullable until resolved.

-- V7 Part 2 detector (ships 'log' like Part 1): one human (entity) must not carry two clients.
CREATE OR REPLACE VIEW v_ontology_channel_person_cross AS
SELECT entity_id,
       count(DISTINCT mapped_client_code)     AS n_clients,
       array_agg(DISTINCT mapped_client_code) AS codes
FROM   channel_users
WHERE  entity_id IS NOT NULL AND mapped_client_code IS NOT NULL
GROUP  BY entity_id HAVING count(DISTINCT mapped_client_code) > 1;   -- >1 = A25 violation
-- rollback: DROP VIEW …; ALTER TABLE channel_users DROP COLUMN entity_id;
```

On apply, the ontology desk graduates the A25 marker (Part 2 shadow) and the coordinator's `--resolve`
begins binding email stakeholders → `entities` → single client.

---

## 5. Agent prompts (the directive asks for these verbatim)

### 5.1 Ontology Agent — prompt
> You are the Ontology desk for LandTek. A new Communications spine is being built (COMM-AGENT-MAX).
> Tasks, in order: (1) **Re-point `UnifiedClientPersona` (§2.14):** its cited home
> `conversation_context`/`conversation_chunks` was DROPPED in deploy_804 — re-ground the marker to the new
> interaction spine (`v_comms_interactions`/`v_comms_relationship`, or a promoted `comms_interactions`
> table if approved). (2) On greenlight of `channel_users.entity_id`, **graduate A25**: Part 1 (shadow,
> live) → note Part 2 shadow via `v_ontology_channel_person_cross`; keep both `log` until a ≥72h clean
> window + operator go, per the V7 roadmap. (3) Register `v_comms_interactions`/`v_comms_relationship` in
> the coverage check so `--coverage` stays green. (4) Confirm A27's mechanical floor (`truth_tests` — every
> outbound rode the S14 guard) still passes as traffic migrates onto the bus. **Constraints:** ONTOLOGY.md
> markers only, no schema; shadow-first; never renumber the A-series; ground every rowcount live; zero
> Aug-12 risk. Report deltas as change-log entries + honest 🟢/🟡/○ markers.

### 5.2 Supervisory Agent — prompt
> You are the Supervisor for LandTek (fail-closed governance over `work_orders` + `outward_guard`). A
> Communications spine is going live. Tasks: (1) Register a new work-order kind **`comms_package`** (lawyer
> prep, stakeholder digest, demand letter) — T2 auto-draftable, **T3 (any outward send/file/publish) holds
> for a human**, per A21/A26/S14. (2) Route every coordinator outbound through the `outward_action`
> chokepoint; a send with no S14 decision is a fail-closed block. (3) Watch `v_comms_relationship` for
> **open loops** (inbound >48h unanswered) and enqueue a draft-reply work order — never an auto-send. (4)
> Keep `systemctl --failed` at zero; degrade gracefully when a channel is tokenless (expected-idle ≠
> failure). **Constraints:** nothing outward without human approval pre-Aug-12; every action audited; reuse
> `supervisor.py` KINDS + `outward_guard`, do not add a framework.

---

## 6. Open decisions (surface → Jonathan greenlights)

| # | Decision | My recommendation |
|---|---|---|
| **6.1** | Add `channel_users.entity_id` now? | **Yes** — it's the A25 Part 2 unblock *and* the relationship-graph person-key; additive/nullable/reversible; the 5 email stakeholders are waiting to be bound. |
| **6.2** | Relationship graph: tables or views? | **Views first** (ship §3 now, zero risk), promote `v_comms_relationship` → materialized table + write-path only once it's proven useful. |
| **6.3** | Channel priority after TG/Email? | **Viber next** (already ARMED, one token from live, PH-ubiquitous), then WhatsApp (Meta verification is the long pole), Messenger last (needs new adapter). |
| **6.4** | First live *outward* test? | **Post-Aug-12 only.** Pre-Aug-12 everything stays inbound + draft-and-hold; the outward switch is yours, per `no-external-exposure-until-ready`. |

**Immediate next step on greenlight:** apply §3 (spine views, ~zero risk) → dry-run + apply §4
(`entity_id`) → point `--resolve` at the 5 email stakeholders → first measurable win: cross-channel
relationship memory for the live MWK-CV26360 legal team.
```
