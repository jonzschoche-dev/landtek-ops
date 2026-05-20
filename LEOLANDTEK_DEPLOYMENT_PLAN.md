# LEOLANDTEK — Unified Deployment Plan

*The hybrid: System Overview vision (May 9, 2026) + LEO_RELEASE_ROADMAP (May 20)
+ WORKFLOW (multi-agent discipline) + verified current state (May 20)
+ innovation-without-stalling framework.*

This is the single source of truth for what we are building and how we ship.
**Authored: 2026-05-20**
**Owner: Jonathan Zschoche**

**Companion docs:**
- `LEOLANDTEK_SYSTEM_OVERVIEW.md` — product/market/compliance/security/pricing context (the May 9 doc, now in repo)
- `WORKFLOW.md` — multi-agent git discipline
- `LEO_MASTER_PLAN.md` — internal strategy + principles + metrics (will be revised to align with this doc)
- `LEO_RELEASE_ROADMAP.md` — version history detail (subsumed under § 5 here)

---

## 1. The vision in one sentence

LeoLandTek is **the operating system for serious Philippine property and legal matters** — an evidence-grade, AI-powered practice-management platform with a proactive intelligence layer that compounds with every interaction.

The product layers, top to bottom:

- **Workspace** — what users open every day (web app + mobile + Telegram + future channels)
- **Intelligence brain** — Leo (RAG + truth-negotiator + ontology + meta-agent)
- **Canonical ontology** — typed, provenance-grounded, temporally-valid (the master of truth)
- **Document corpus** — Drive + Postgres + pgvector
- **Infrastructure** — VPS + n8n + Postgres + systemd + cowork-bridge

---

## 2. Independently-verified current state (2026-05-20)

### What's built — confirmed against the codebase

| Capability | Evidence | Notes |
|---|---|---|
| V4 schema | `scripts/v4_schema.sql` | 14 tables incl. pgvector halfvec(3072), audit_log, authorized_users, provenance_level |
| Heightened Gemini OCR | `autonomous/tct_sweep.py` + `heightened_ocr/` | 2-pass cross-validation, gemini-2.5-flash, quality 0.8 |
| Orchestrator (deterministic phases) | `autonomous/orchestrator.py` | Phase A re-queue, Phase B source-quote verifier, Phase B-prime consensus promotion, Phase C state snapshot |
| Sweep loop | `autonomous/sweep_loop.sh` | Adaptive sleep (10s/15min/30min/1hr) |
| Comms chokepoint | `comms.py` (deployed 2026-05-19) | Audience taxonomy (ops/client/both) + denylist + STRICT_AUDIT_KINDS + telegram.org backstop |
| Onboarding state machine | `leo_tools/onboarding_endpoints.py` (deploy_116) | `/api/onboard`, `/api/approve_user`, `/api/deny_user`, `/api/pending_approvals` |
| Channels + channel_users tables | `migrations/apply_deploy_114_channels_schema.py` | Multi-channel adapter foundation |
| Files dashboard web UI | `leo_tools/files_dashboard.py` (`/files/` route) | Searchable document browser |
| 6 systemd services | `systemd/landtek-{conflict,continuous,digest,proactive,verify}.timer` + `leo-watchdog.timer` | All version-controlled |
| Memory tree in git | deploy_184 | Symlinked, 52 rule files committed |
| Leo Flask service | `leo_tools/server.py` | 20+ endpoints incl. eval, query, rate, deadlines, entities |
| Truth-negotiator | `truth_negotiator.py` (525 lines) | Back-test pass rate 67% as of 5-17 |
| Case bible generator | `generate_case_bible.py` (1300 lines) | Omnibus + per-matter bibles |
| Opus pre-delivery audit gate | `opus_audit_gate.py` + `opus_advisor.py` + `drafts/Opus_Case_Bible_Audit_Gate_May2026.md` | Returns NO-GO when fixes needed |
| Improvement agent (self-diagnosis) | `improvement_agent.py` | Top-5 leverage moves auto-ranked |
| Cowork-bridge deploy pipeline | systemd unit + `leolandtek-deploys.git` | 184+ deploys shipped |
| 17 matters across 2 clients | `daily_digest_2026-05-17.md` confirms | MWK-001 (10 matters) + Paracale-001 (8 matters) |
| 354/682 chunks verified (52%) | `notifications/pending.txt` last entry 5-17 09:36 | Target ≥ 80% |
| 388+ docs indexed | `system_state.json` last_doc=943 | Per case_file scoping |
| 40 case-relevant Gmail messages ingested | `gmail_messages` table | 26-360 thread visible |

### What's gap — confirmed missing

| Gap | Evidence | Severity |
|---|---|---|
| Sweep-loop heartbeat stopped 2026-05-17 09:36 UTC | `notifications/pending.txt` tail | 🔴 Critical — verifier not running for 3 days |
| Bible NO-GO from Opus audit | `drafts/opus_bible_audit_2026-05-17.md` | 🔴 Critical — 5 existential fixes outstanding |
| Hallucinations of Cesar dela Fuente in 2025/2026 | Same Opus audit | 🔴 Critical — actor died 2017, structurally caught only by `actor_lifespan` constraint (not built) |
| CV-26360 venue confusion (MTC vs RTC) | Same | 🔴 Critical — structural fix needed |
| Hallucinated dockets (CV-6922, Crim-9221) | Same | 🔴 Critical — output_audit not enforcing inventory |
| CV-6839 set bleed | Same — 10+ events mis-tagged | 🟠 High — title chain enforcement needed |
| Forensic layer not built | No OpenTimestamps, signature hashing absent | 🟠 High — required for court-grade evidence |
| `fraud_indicators` table empty | 0 rows confirmed | 🟠 High |
| PDPA paperwork not filed | No DPIA file, no NPC registration | 🟠 High — blocks paying clients |
| Multi-channel adapters not built | Telegram only; Email/Viber/Messenger/WhatsApp/Web/SMS pending | 🟠 High — blocks PH market reach |
| Stripe / billing layer absent | No payment scripts | 🟡 Medium — blocks revenue scaling |
| Web app workspace absent | Only `/files/` dashboard exists | 🟡 Medium — blocks daily-use product |
| Trajectory score 34/100 | `improvement_audit_2026-05-17.md` | 🟡 Medium — system self-diagnosed |
| 15 TG queue bypasses | Same audit | 🟠 High — caused 2026-05-17 blackout pattern |
| 43-file hard-coded DSN scatter | Same audit | 🟡 Medium — credential leak + drift risk |
| 26-file hard-coded Jonathan TG ID | Same audit | 🟡 Medium |
| 8 files >500 lines | Same audit | 🟡 Medium — blocks per-client config injection |
| Auth gate not enforced everywhere | `authorized_users` schema exists but call-sites need audit | 🟡 Medium |
| 2 hallucinations logged in 30d | Same audit | 🟡 Medium |

### What's partial

| Component | Where | What's missing |
|---|---|---|
| Auth gate | Schema + onboarding endpoints exist | Per-call-site enforcement audit |
| Matter portfolio | 17 matters with stage + WHAT + WHO | Per-matter `best_state` not all populated; ARTA-1212 missing from inventory |
| Multi-channel | Schema exists | Inbound adapters (only Telegram wired) |
| Cost discipline | Cost logging deployed | No daily-spend alerting threshold |
| Provenance enforcement | `provenance_level` column on chunks | No `NOT NULL` constraint; no `actor_lifespan` temporal validity |

**Overall assessment:** The system is significantly more built than the May 9 doc framed (which suggested ~40% capability). Realistic estimate today: **~65% of v0.9 alpha capability**, with critical structural gaps in ontology enforcement that prevent reaching v1.0.

---

## 3. The product target — hybrid model

### Three concurrent product surfaces, one brain

```
       ┌─────────────────────────────────────────────────────────┐
       │                                                         │
       │   PRODUCT SURFACES (what users open)                    │
       │                                                         │
       │   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
       │   │  Web app     │  │  Mobile-web  │  │  Multi-      │  │
       │   │  workspace   │  │   capture    │  │  channel     │  │
       │   │ (matters,    │  │ (photo, voice│  │ (TG, WhatsApp│  │
       │   │  notes, etc.)│  │  notes)      │  │  Viber, etc.)│  │
       │   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
       │          │                 │                 │          │
       │          └─────────────────┼─────────────────┘          │
       │                            ▼                            │
       │   ╔═══════════════════════════════════════════════╗     │
       │   ║      LEO BRAIN                                ║     │
       │   ║                                               ║     │
       │   ║  - Comms chokepoint (audience-aware)          ║     │
       │   ║  - Truth-negotiator (cross-validation)        ║     │
       │   ║  - Output audit gate (Opus)                   ║     │
       │   ║  - Goal accelerator (proposals)               ║     │
       │   ║  - Deadline sentinel                          ║     │
       │   ║  - Meta-agent (drift detection)               ║     │
       │   ║  - Improvement agent (self-diagnosis)         ║     │
       │   ╚════════════════════╤══════════════════════════╝     │
       │                        ▼                                │
       │   ╔═══════════════════════════════════════════════╗     │
       │   ║   CANONICAL ONTOLOGY — MASTER OF TRUTH        ║     │
       │   ║                                               ║     │
       │   ║  - Typed entities (person/title/parcel/...)   ║     │
       │   ║  - Typed relations                            ║     │
       │   ║  - Provenance on every row (NOT NULL)         ║     │
       │   ║  - Temporal validity (actor_lifespan)         ║     │
       │   ║  - Formal-validity verdicts (PH Civil Code)   ║     │
       │   ║  - Evidence trail queryable per claim         ║     │
       │   ╚════════════════════╤══════════════════════════╝     │
       │                        ▼                                │
       │   ┌───────────────────────────────────────────────┐     │
       │   │  CORPUS                                       │     │
       │   │  Postgres (v4 schema) + pgvector(3072) +      │     │
       │   │  Drive (folder-structured) + Qdrant (legacy)  │     │
       │   └───────────────────────────────────────────────┘     │
       │                                                         │
       └─────────────────────────────────────────────────────────┘
```

### Five "elite" dimensions (what makes Leo best-in-class)

1. **Per-matter elite** — instant case theory, evidence gap, deadline radar, drafting, opposing-counsel response prediction
2. **Per-portfolio elite** — every title valued, risk-rated, opportunity-tagged; "buy this depressed parcel", "sell that one", "this title is shaky, fix it"
3. **Per-firm elite** — financial planning, capacity, intake automation, revenue forecasting — Landtek as a fundable business
4. **Per-channel elite** — WhatsApp + web + email + voice + Telegram + Viber + Messenger + SMS — one brain, every surface
5. **Per-jurisdiction elite** — fluent in PH property law today; designed so a second jurisdiction is an extension, not a rewrite

### Three product tiers (from System Overview, validated pricing TBD)

| Tier | Audience | Indicative price | Build readiness |
|---|---|---|---|
| T1 — Intelligence Retainer | Estate executors, mining principals, disputed-land owners, HNW individuals | PHP 15K–50K/mo | After v1.5 |
| T2 — Property Management | Landlords, small developers, property companies | PHP 500–2K/unit/mo or PHP 8K–25K/mo flat | After v3.0 |
| T3 — Platform / White-label | Law firms, property companies, govt liaison specialists | PHP 50K–200K/mo or enterprise contract | After v3.0 |

**Validation principle (from May 9 doc):** No firm pricing committed until real client data validates willingness to pay. Current clients (Paracale-001, MWK-001) are the proof-of-concept dataset.

---

## 4. The four non-negotiable guardrails

These are immutable. Every release respects them or doesn't ship.

| # | Guardrail | Mechanism | Status |
|---|---|---|---|
| 0 | **Ontology is master of truth** | Provenance NOT NULL + actor_lifespan + output_audit + typed canonical entities | 🔴 Not yet structurally enforced — v1.0 hard requirement |
| 1 | **Never break client comms** | `comms.comms_send()` chokepoint + `telegram.org` backstop + audience taxonomy | ✅ Deployed 2026-05-19 |
| 2 | **Never miss a deadline** | `deadline_sentinel.py` + multi-step escalation + audit trail | ✅ Running |
| 3 | **Auth gate every client-data access** | `authorized_users` + onboarding state machine + per-call-site enforcement | 🟠 Partial — call-site audit needed |

---

## 5. Versioned release schedule (gated on readiness, not calendar)

### v0.9 — "Alpha" (current as of 2026-05-20)

**Theme:** Engine works, gaps known. No client-safe daily-use product.
**State:** Already shipped (see § 2 verification). Trajectory score 34/100.
**Audience:** Internal only.
**Slip log:** None (this is the current state).

### v1.0 — "Trustworthy Foundation + The Workspace"

**Theme:** Ontology-as-truth structurally enforced. Bible passes audit. Jonathan opens a web app every morning instead of Termius.
**Targeted readiness:** before 2026-06-02 (mediation forces the date, but readiness gates final cut)

**Must ship — backend:**

- **Ontology hardening:**
  - `provenance NOT NULL` + `source_doc_id REFERENCES documents(id)` on every fact-bearing table
  - `actor_lifespan` table + temporal-validity CHECK constraints (catches Cesar-post-2017 at insert)
  - `output_audit.py` — pre-render check that every named entity/docket/date in proposed output exists in canonical inventory; REJECTS rather than paraphrases
  - Migrate existing chunks to schema-compliant rows; archive non-compliant rows for human review

- **Bible safety pass** — 5 Opus-flagged existential fixes, BUT enforced structurally not patched:
  - Cesar-post-2017 → `actor_lifespan` blocks at insert
  - Venue confusion → `matters.venue` single-valued + bible reads from it
  - Hallucinated dockets → `output_audit` rejects any docket not in `matters`
  - CV-6839 set bleed → `title.belongs_to_chain` constraint
  - CV-6922 + Crim-9221 → same `output_audit` enforcement

- **Verified chunks ≥ 80%** (lift from 52% via nightly Haiku validity-audit backfill, ~$0.80/night)
- **Auto-rollback sentinel** for comms / sweep / orchestrator
- **Critical-path test suite** (30-second smoke test)
- **TG dispatcher chokepoint** — close all 15 direct bypasses
- **DSN consolidation** into `landtek_core.config`
- **Heartbeat dashboard** — single page summarizing every sentinel + service + last-success
- **Restart wedged orchestrator** (one-shot — `pending.txt` heartbeat resumes)
- **Per-call-site auth gate audit** — every code path that returns client data checks `authorized_users`

**Must ship — daily-use product (workspace v1):**

- **Web app at app.landtek.com** — login (Jonathan + Don Qi), desktop + mobile browser
- **Dashboard / home** — today's deadlines, open inquiries, recent activity feed across matters
- **Matter list** — all 17 matters with stage + next action + last activity
- **Per-matter page** — header + timeline + documents + notes + entities + deadlines
- **Quick-capture** (accessible from every screen):
  - `+ Note` — type, auto-tagged to matter
  - `+ Evidence` — drag-drop or photo-upload, ingestion queue, auto-classified
  - `+ Deadline` — date + matter + description
- **Search bar** — global across documents, notes, communications, entities
- **Mobile-optimized** — same web app, responsive; phone-camera + voice notes (transcribed)
- **Activity feed** — live or near-live updates of Leo's autonomous work

**Audience:** Internal + Counsel (Barandon, Botor) — counsel-facing outputs are now defensible.

**Readiness gate:**
- Opus audit gate returns GO on omnibus bible
- Jonathan can run an entire workday from web app without opening Termius
- One piece of evidence captured via mobile photo upload, processed end-to-end, surfaced in matter timeline

### v1.5 — "Multi-Front Recovery + Workspace Maturity + Compliance Foundation"

**Theme:** Leo runs the whole multi-front recovery campaign. Workspace is smooth. PDPA compliance documented before paying clients.
**Targeted readiness:** ~2026-06-30

**Must ship — backend:**

- **Financial ledger** — `accounts/transactions/monthly_overhead/value_extraction_events/asset_valuations`
- **Investor-grade reports v1** — P&L, runway, ROI per matter, valuation memos per property
- **ARTA campaign dashboard** — all 9 matters w/ RA 11032 deadline ladders, bad-faith evidence yield, agency-response cadence
- **Cross-matter pattern detection** — same actor in multiple matters, same property contested across tracks
- **Per-transferee recovery posture** — all 20 named MWK transferees, individual case strategies
- **Asset valuation layer** — per-title tax-dec / assessed / zonal / declared market value, depressed-value buy/sell modeling
- **Bad-faith evidence map** — cross-matter index of stonewalling, refusals, opposing-counsel patterns

**Must ship — daily-use product (workspace v2):**

- **Multi-user with permissions** — Jonathan, Don Qi, future Landtek staff; per-user roles
- **Voice notes** — record on mobile, auto-transcribed (Whisper), saved as matter note + searchable
- **Photo capture** — open camera in app → snap → matter auto-suggested → confirm → ingestion queue
- **Push notifications (PWA)** — deadlines, new evidence, Leo proposals, urgent inquiries
- **Real-time activity feed**
- **Email composer in-app** — drafts using verified-only citations; outbound via `comms.comms_send()`
- **Telegram parity** — anything in web app doable via Telegram slash commands
- **Campaign view** — per-campaign dashboard (ARTA campaign, civil campaign, estate admin)
- **Saved searches / smart filters**

**Must ship — compliance:**

- **DPIA (Data Protection Impact Assessment)** documented
- **Consent + legitimate-interest documentation** per active client
- **Encryption at rest** — Postgres data + Qdrant vectors + Drive
- **Access logging** — every sensitive-data access timestamped with actor
- **Data subject rights** — process documented (access + deletion + legal-hold exceptions)

**Audience:** Internal + counsel + Jonathan-as-strategist + Don Qi (administrator).

**Readiness gate:**
- Every active matter has populated `best_state` + `next_action`
- Financial ledger reconciles within ±5% of bank
- Bad-faith map has ≥ 10 cross-matter entries
- Don Qi uses workspace independently
- DPIA complete + filed

### v2.0 — "Multi-Client Scale + RBAC"

**Theme:** Onboarding client #3 is a wizard. RBAC enforces every access. NPC-registered before public launch.
**Targeted readiness:** ~2026-08-15

**Must ship:**

- **Monolithic decomposition complete** — `generate_case_bible.py`, `tg_dispatcher.py`, `build_system_blueprint.py` split into ≤200-line modules with pytest coverage
- **Per-client config injection** — every script honors `--client` flag or client-config table
- **Multi-tenancy schema deployed:**
  - `organizations` (one row per paying-client organization)
  - `users` (proper identity layer; replaces raw telegram_id)
  - `organization_members` (links users to orgs with role + JSONB permissions)
  - `permission_definitions` (default permission sets per role)
  - `organization_id UUID` added to `clients/cases/conversations/action_items/documents`
- **8-role RBAC:** `owner / admin / lawyer / property_manager / heir / contractor / tenant / government`
- **Permission Filter node in n8n** — filters context BEFORE Leo sees it (defense in depth: context filtered first, prompt is last line of defense)
- **Client onboarding wizard** — intake form → matter scaffolding → Drive folder seed → contact mapping → first deadline import (in under 1 hour, no code changes)
- **Light client portal v1** — read-only per-client dashboard (web, not yet WhatsApp)
- **Email reply bot** — Leo replies to client emails via Gmail, audience-gated through `comms.comms_send()`
- **NPC registration filed** with the National Privacy Commission

**Audience:** Internal + counsel + clients (read-only portal).

**Readiness gate:**
- New client onboarded end-to-end in < 1 hour with no code changes
- Their data fully isolated (Postgres row-level + n8n context-filter)
- NPC registration acknowledged

### v2.5 — "Channel Expansion + Stripe"

**Theme:** Meet clients on the channel they prefer. Money flows in.
**Targeted readiness:** ~2026-09-30

**Must ship:**

- **Viber adapter** — PH-preferred business + professional channel
- **Messenger (Meta Business)** — mass-market PH dominant
- **WhatsApp Business API** — OFW + international diaspora
- **Web chat widget** — embed on landtek.com / client portal
- **Email reply bot v2** — better threading + attachment handling
- **SMS (Twilio)** — last-resort fallback
- **Stripe integration** — Tier 1 retainer + Tier 2 unit billing
- **Per-tenant spend tracking** — every API call meter-tagged with tenant
- **Identity bridge** — same client across email + WhatsApp + Telegram resolves to one `mapped_client_code`

**Audience:** Internal + counsel + clients (now multi-channel reachable + billable).

**Readiness gate:**
- A client message on WhatsApp/Viber/Messenger/web/email is processed identically to Telegram
- First Tier 1 retainer collected via Stripe

### v3.0 — "Platform — Licensable"

**Theme:** First external firm runs on Leo. Licensing revenue starts.
**Targeted readiness:** ~2026-11-30

**Must ship:**

- **Public REST/GraphQL API v1** — `/api/v1/leo/chat`, `/verify`, `/extract`, `/onboard`, `/portfolio`
- **Multi-tenant architecture proven** — per-firm data isolation, per-firm config, per-firm spend tracking
- **Quota + billing per-firm** — API key + token meter + monthly invoice
- **First partner firm licensed** — one external PH property firm running on Leo, paying recurring fees
- **Audit-log per tenant** — each firm pulls their own log
- **Documentation site** — public API docs, ontology spec, integration guide
- **Multi-model routing** — Claude (reasoning), GPT-4o (docs/cross-val), Gemini Flash (classification/embeddings), Grok (PH regulatory news)

**Audience:** All previous + Partner firms (licensees).

**Readiness gate:** First external firm processes a real matter end-to-end on licensed instance with no Landtek intervention.

### v3.5 — "Predictive + Forensic"

**Theme:** Leo proposes actions you accept. Documents are court-grade-verified.
**Targeted readiness:** ~2027-01-31

**Must ship:**

- **Goal accelerator daily proposals** — 1-3 actions per matter + 1-2 firm-level, one-tap accept/decline, backed by truth-negotiator
- **Procedural deadline prediction** — 18 PH civil-procedure stages → Leo predicts, not just logs
- **Low-hanging-fruit engine** — auto-flag intrinsic > 1.4 × market + low mitigation cost
- **Forensic layer:**
  - Signature perceptual hashing + Siamese network comparison
  - OpenTimestamps anchoring
  - Hash-chained audit log
  - Notarization validation pipeline
  - Temporal anomaly detection on documents
- **Evidence bundle export** — court-ready PDF on demand
- **Hyper-vigilance meta-agent (full)** — second AI node auditing Leo every hour; auto-remediates gaps

**Audience:** All + sharper.

**Readiness gate:** ≥ 40% of Leo's daily proposed actions accepted; ≤ 0 false-positive deadline alerts in 30 days; first court-ready evidence bundle generated and accepted by counsel.

### v4.0 — "Investor-Grade"

**Theme:** Landtek is a fundable business with provable platform economics.
**Targeted readiness:** ~2027-03-31

**Must ship:**

- **Investor-grade financial reports** — audited P&L by client cohort, matter type, channel
- **Platform metrics dashboard** — per-tenant cost-to-serve, gross margin, churn projection
- **Cohort analytics** — LTV per client type, ROI per matter type
- **Capital pitch deck** — auto-generated quarterly from live data
- **Demonstrable platform ROI** — ≥ 1 paying licensee with positive unit economics

**Audience:** All + investors.

**Readiness gate:** Pitch deck regenerates from live data with zero manual edits; numbers reconcile with bank + ledger to penny.

### v5.0 — "International"

**Theme:** Diaspora-focused, jurisdiction-extensible.
**Targeted readiness:** ~2027-06-30

**Must ship:**

- **Second jurisdiction onboarding proof** — one non-PH client matter (US, AU, or CA) handled with jurisdiction plugin
- **Pluggable legal frameworks** — abstract "PH Civil Code rubric" as `legal_framework` plugin pattern
- **Diaspora client acquisition** — Leo as trusted bridge for US/AU/CA heirs of PH property
- **Cross-jurisdiction asset tracking**

**Audience:** All + diaspora clients globally.

---

## 6. Innovate without stalling — the operational framework

**This is THE thing** that lets Leo evolve continuously without ever taking down what's working.

### 6.1 Why this matters

The 2026-05-17 comms blackout cost 48 hours of silently-dropped Don Qi + Jonathan inbound. The fear of repeating that incident is rational — and if it constrains innovation, the project stalls. The answer isn't to slow down. It's to make every change **cheap to reverse** and **structurally unable to break load-bearing components**.

### 6.2 The five-layer safety substrate

Every change passes through these layers before it reaches production. Each is independent. Compromising one doesn't break the others.

| Layer | Mechanism | Status |
|---|---|---|
| 1. Two-plane isolation | Data plane (Python services) + Conversational plane (n8n/Leo) share DB, can fail independently | ✅ Already operational |
| 2. Clone-first authoring | Edits happen in Mac clone, never on VPS directly. Git is the audit trail. | ✅ WORKFLOW.md codifies it |
| 3. Staging branches | Big changes go to `staging` branch; merged to `main` only after passing tests | 🟠 To deploy in v1.0 |
| 4. Critical-path tests | 30-second smoke suite: comms send, sweep cycle, audit gate. Run pre-deploy. | 🟠 v1.0 must-ship |
| 5. Auto-rollback sentinel | Detects comms silence / sweep stall / heartbeat gap → reverts last deploy | 🟠 v1.0 must-ship |

### 6.3 The four invariants — must always be true

If any of these is false, innovation pauses until restored:

1. `systemctl status sweep-loop.service` = `active`
2. `systemctl status n8n` = `active` (Leo's runtime)
3. `tail -1 notifications/pending.txt` heartbeat < 1 hour old
4. Telegram bot `@LeoLandTekBot` responds to a test ping

The heartbeat dashboard (v1.0 deploy) surfaces all four. Auto-rollback sentinel triggers on invariant breach.

### 6.4 Innovation cadence — what happens daily

```
┌────────────────────────────────────────────────────────────────────────┐
│                                                                        │
│  EVERY DAY (Jonathan + Cowork + VPS Claude):                           │
│                                                                        │
│  1. git pull (auto-sync runs every 2 min on Mac via launchd)           │
│  2. Open web workspace → see what Leo did overnight                    │
│  3. Review proposed actions → accept/decline (one tap each)            │
│  4. Capture today's evidence/notes/calls in the workspace              │
│  5. Address any deadline alerts                                        │
│  6. End of day: improvement_agent posts top 3 leverage moves           │
│                                                                        │
│  EVERY WEEK (release review):                                          │
│                                                                        │
│  1. Check current release's readiness criteria                         │
│  2. If green → tag the release, write release notes                    │
│  3. If amber → identify what's blocking, schedule for next week        │
│  4. Update slip log if a release date moves                            │
│                                                                        │
│  EVERY MONTH (vision check):                                           │
│                                                                        │
│  1. Verify the four invariants are still holding                       │
│  2. Review LEOLANDTEK_DEPLOYMENT_PLAN.md — what assumptions changed?   │
│  3. Update tiers, readiness criteria, pricing as evidence comes in     │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.5 The deployment pipeline (how changes physically ship)

```
1. Idea / problem
       ↓
2. Cowork proposes change in ~/landtek (Mac clone)
       ↓
3. Jonathan reviews diff in chat
       ↓
4. Critical-path tests run (30s smoke)
       ↓
5. Commit to staging branch first
       ↓
6. Auto-rollback sentinel armed
       ↓
7. Merge to main → push to landtek-ops
       ↓
8. If activation needed: deploy_NNN.sh script → leolandtek-deploys/inbox/
       ↓
9. cowork-bridge daemon executes (30-min timeout)
       ↓
10. Watch heartbeat for one sentinel cycle (30 min)
       ↓
11. If any invariant breaks → AUTOMATIC REVERT
       ↓
12. If clean → release tag candidate
```

### 6.6 Per-client canary deploys

When a new feature could affect client experience:

1. **Internal canary** — Jonathan tests for 24 hours
2. **Friendly canary** — Don Qi (MWK-001) gets it next — he's the most engaged client
3. **Full client roll** — Patricia + future clients
4. **Partner-firm roll** — licensees (only after v3.0)

Each tier has its own kill switch. A feature can be enabled for canaries while disabled for everyone else.

### 6.7 Feature flags (v2.0+)

Per-client config injection unlocks feature flags:

```yaml
features:
  voice_notes: enabled_for: [jonathan, don_qi]
  email_reply_bot: enabled_for: [jonathan]
  whatsapp_inbound: enabled_for: []
  goal_proposals_telegram: enabled_for: [jonathan, don_qi, patricia]
```

A bad feature is disabled in seconds without code change.

### 6.8 Shadow traffic (for the highest-risk changes)

When the change is to a load-bearing component (truth-negotiator, classifier, output_audit):

1. New version runs alongside old, on the same inputs
2. Outputs are compared — divergence is logged, not acted on
3. After N days of clean comparison, the new version is promoted
4. Old version stays runnable as instant rollback

### 6.9 The improvement agent feeds itself

Already running (`improvement_agent.py`). Its weekly job:

1. Static-code scan for new technical debt (hard-coded DSN, env loader reimplementation, monolithic file growth, etc.)
2. Pattern detection across `hallucination_log` + `escalations_log`
3. Cost analysis (which models cost more than they should)
4. Auto-rank top 5 leverage moves by impact / effort
5. Post to a `improvement_proposals` queue
6. Jonathan accepts → it becomes a deploy
7. Loop

This is self-improvement that respects the safety substrate — the agent proposes, the substrate guards, Jonathan decides.

---

## 7. The four guardrails — operational truth table

Innovation is blocked if any guardrail breaks. Restoring is the priority.

| Guardrail | Test | If broken |
|---|---|---|
| Ontology master of truth | `output_audit` returns clean on the bible | ALL counsel-facing output blocked until restored |
| Comms chokepoint | `comms.comms_send()` audience flag honored on every send | ALL outbound blocked until restored |
| Never miss deadline | `deadline_sentinel.timer` active + escalation ladder firing | ALL goal-accelerator proposals paused |
| Auth gate | No client-data API returns without `authorized_users` check | ALL public endpoints disabled |

These are simultaneously safety substrate invariants and release-blocking conditions.

---

## 8. PDPA + Security + Compliance schedule

Anchored to release cuts:

| Release | Compliance milestone |
|---|---|
| v1.0 | Internal threat model documented; encryption-in-transit verified |
| v1.5 | DPIA filed; consent + legitimate-interest docs per client; encryption-at-rest; access logging on |
| v2.0 | NPC registration; 8-role RBAC enforced; data subject rights procedures live |
| v2.5 | Per-channel data handling docs; international transfer disclosures (US/AU/CA diaspora correspondence) |
| v3.0 | Per-tenant audit logs; partner-firm NDA + DPA templates ready |
| v3.5 | Court-grade audit trail (OpenTimestamps) live; chain-of-custody documentation |
| v4.0 | SOC 2 Type 1 readiness (if pursuing institutional capital) |

---

## 9. Cost model + path to profitability

### Current cost (verified)

- AI subscriptions: $140/mo (Claude + GPT-4o + Gemini + Grok)
- VPS: $10/mo (DigitalOcean $6 droplet + backups)
- Qdrant: $0 (free tier)
- Drive: $0 (existing)
- **Total: $150/mo**

### Scaling triggers (no upgrade before trigger fires)

| Item | Upgrade cost | Trigger |
|---|---|---|
| VPS | +$10–20/mo | CPU/RAM > 70% sustained |
| Managed Postgres | +$15/mo | 5+ active orgs OR backup criticality |
| n8n Cloud | +$20/mo | Team access OR 5+ active workflows |
| Qdrant Starter | +$25/mo | Collections > 1GB |
| AI subscription tier | +$50–100/mo | Rate limits OR larger context needed |

At 10 active orgs, total cost ceiling: **$250–300/mo**.

### Path to profitability

- **Break-even:** one Tier 1 client at any retainer ≥ PHP 8,500/mo covers all costs
- **Sustainable revenue:** 3-5 Tier 1 clients at validated retainer pricing
- **Scale revenue:** Tier 2 + Tier 3 unlock 10× addressable market (after v3.0)
- **External funding optional, not required** to reach profitability — cost structure is lean enough to bootstrap

### Validation principle

Before any price is committed:

1. Complete v1.0
2. Run Paracale-001 + MWK-001 live for 30-60 days post-v1.0
3. Measure actual time + intelligence value delivered
4. Price against demonstrated value — not assumed value

---

## 10. The matter portfolio (live state — 2026-05-20)

### Client: MWK-001 (Heirs of Mary Worrick Keesey)

**North star:** Property recovery + estate profitability.

| Matter | Stage | Best state target | Counsel |
|---|---|---|---|
| MWK-CV26360 | `post_pretrial_pending_trial_schedule` | Title cancellation + property recovery via accion reinvindicatoria | Atty. Barandon |
| MWK-CV6839 | `active` | Just-compensation award (CARP) | Yuzon Law (referenced) |
| MWK-ESTATE | `estate_administration_active` | Full estate administration through to distribution | Atty. Botor (guardianship) |
| MWK-TCT4497 | `demand_letter_pending_send` | Title-history correction at RD Camarines Norte | (paralegal) |
| MWK-ARTA-0690 | `resolved_no_merit` | Closed | — |
| MWK-ARTA-0747 | `complaint_filed_awaiting_response` | Adverse finding vs. Mayor Pajarillo | ARTA |
| MWK-ARTA-0792 | `resolved_no_merit` | Closed | — |
| MWK-ARTA-1210 | `complaint_filed_awaiting_response` | TBD — needs respondent ID + complaint affidavit upload | ARTA |
| MWK-ARTA-1212 | `complaint_filed_awaiting_response` | ⚠ Missing from inventory — backfill needed | ARTA |
| MWK-ARTA-1319 | `complaint_filed_awaiting_response` | TBD — needs respondent identification | ARTA |
| MWK-ARTA-1321 | `complaint_filed_awaiting_response` | Coordinate w/ ARTA-1319 (filed same day) | ARTA |
| MWK-ARTA-1378 | `complaint_filed_awaiting_response` | Third-count action vs. Mun. Engineer Mercedes | ARTA |
| MWK-ARTA-1891 | `referred_to_csc_dilg_awaiting` | CSC/DILG action follow-up | CSC / DILG |

### Client: Paracale-001 (Allan V. Inocalla)

**North star:** TBD with Allan (engagement freshness needed).

| Matter | Stage | Notes |
|---|---|---|
| AUTO-PARACALE_001 | `needs_context_from_user` | Auto-promoted, 48 docs unassigned |
| PAR-CAPACUAN | `pending_context` | Capacuan dispute |
| PAR-CASE-88750 | `pending_context` | Francisco vs Allan (omnibus resolution on file) |
| PAR-COMPLAINT-ACE | `pending_context` | Complaint against Ace |
| PAR-CV13-131220 | `pending_context` | RTC Camarines Norte (presumed) |
| PAR-GOLDEN-SAND | `pending_context` | Golden Sand Beach Resort asset matter |
| PAR-TCT1616 | `pending_context` | TCT/OCT 1616 chain verification |
| PAR-VITO-CRUZ | `pending_context` | Vito Cruz case |

**Note:** 4 of 8 Paracale matters are flagged CRITICAL ("ZERO events in timeline — unreliable / not really active") per `drafts/Inocalla_full_timeline_2026-05-17.md`. Engagement audit needed at next Allan touchpoint.

---

## 11. The immediate-priority queue (next 14 days, ranked)

| # | Move | Phase | Effort | Blocks |
|---|---|---|---|---|
| 1 | Restart wedged orchestrator | Phase 0 | < 1 hr | All other innovation (`pending.txt` heartbeat) |
| 2 | Ontology hardening: `actor_lifespan` + provenance NOT NULL + output_audit | v1.0 | 2-3 days | Bible safety + counsel-facing output |
| 3 | Bible safety pass (now structurally enforced) | v1.0 | 1 day after ontology | 26-360 mediation 6-2 |
| 4 | Verified-chunks lift via nightly Haiku audit | v1.0 | 2 hrs + $0.80/night | Trustworthy output bar |
| 5 | TG dispatcher chokepoint — close 15 bypasses | v1.0 | 4 hrs | Blackout repeat risk |
| 6 | DSN consolidation into `landtek_core.config` | v1.0 | 3 hrs | Per-client config injection (v2.0) |
| 7 | Heartbeat dashboard | v1.0 | 1.5 days | Visibility |
| 8 | Auto-rollback sentinel | v1.0 | 2 days | Innovation-without-stalling |
| 9 | Critical-path smoke test suite | v1.0 | 1 day | Safe deploys |
| 10 | Web app workspace v1 (matter dashboard + capture + search) | v1.0 | 5-7 days | Daily-use product layer |
| 11 | Botor briefing pack (Friday 5-22) | Independent | < 1 day | Friday guardianship meeting |
| 12 | Save System Overview + Deployment Plan + Master Plan to repo | Repo hygiene | < 1 hr | VPS Claude visibility |

**Critical path to v1.0 cut:** 1 → 2 → 3 → (4 + 5 + 7 + 8 + 9 parallel) → 10. Estimated 12-14 days if focused.

---

## 12. How this plan stays accurate

- This document is reviewed weekly (state-of-the-system check)
- The slip log below records every readiness-criteria miss + cause + new date
- Both agents have edit rights via WORKFLOW.md discipline
- The `improvement_agent.py` feeds it new data; the `meta-agent.py` audits it

### Slip log

| Date | Release | Original date | New date | Cause |
|---|---|---|---|---|
| none yet | | | | |

---

## 13. Open decisions (Jonathan only)

These shape v1.0 and beyond. Each is non-blocking but the longer they're open, the more downstream work is provisional.

1. **Versioning kickoff** — tag v0.9 retroactively at current commit? (Recommended: yes.)
2. **9 ARTA cases** — each a separate matter, or campaigns within a single "MWK admin campaign"? (Current model: each separate. Reconfirm.)
3. **Paracale-001 status** — active engagement or maintenance mode? (4 of 8 matters stale.)
4. **Don Qi role** — client (administrator of MWK estate) or co-principal? (Affects portfolio structure.)
5. **Botor guardianship** — separate matter (MWK-GUARDIANSHIP) or sub-track of MWK-ESTATE?
6. **Recovery vs settlement preference** — parcel recovery or monetary settlement, per matter? Or matter-by-matter judgment?
7. **Capital strategy** — bootstrap to v4.0 first, or raise on v1.0/v1.5 momentum?
8. **Public release page** — landtek.com lists version history transparently, or kept private?
9. **First licensee acquisition path** — direct outreach, referral, public marketing?
10. **Release manager role** — stays with you indefinitely, or delegate by v2.0?

---

*All updates to this document go through git via WORKFLOW.md. Both agents edit; conflicts resolved per discipline. This is the single source of truth — every other plan document references it.*
