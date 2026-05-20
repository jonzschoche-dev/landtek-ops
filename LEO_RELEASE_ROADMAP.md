# LEO — Product Release Roadmap

> Versioned releases of Leo, the LandTek property-management AI.
> Each release ships a coherent theme. Releases are gated on readiness criteria,
> not calendar dates.
>
> Companion docs:
> - `LEO_MASTER_PLAN.md` — internal strategy + phases + metrics
> - `WORKFLOW.md` — how changes get shipped between agents
>
> Authored: 2026-05-20

---

## Why this exists

Leo isn't a script — it's a product. Clients depend on it. Investors will be evaluated against it. Partner firms may eventually license it. Treating Leo's evolution as **versioned releases** (rather than continuous patches) gives:

1. A clear story for what shipped when
2. A scoreboard that's outward-facing (not just trajectory_score)
3. A discipline that says **"a release ships only when its readiness criteria are met"** — never on calendar pressure
4. An artifact suitable for pitch decks, licensing pages, and partner conversations

Releases are different from deploys:
- A **deploy** is one change pushed via the cowork-bridge pipeline (we're on deploy_184+)
- A **release** is a coherent collection of deploys that together hit a readiness bar and earn a version number

---

## Versioning convention

```
MAJOR . MINOR . PATCH
```

- **MAJOR** = a strategic capability unlock (multi-client, public API, second jurisdiction)
- **MINOR** = a coherent theme (financial layer, channel expansion, predictive)
- **PATCH** = bug fixes + small improvements between minors

Current state: **v0.9 (internal alpha — running, but not yet client-safe for output)**.

---

## Release cadence

- **Minor releases**: roughly every 4-6 weeks, gated on readiness criteria
- **Major releases**: every 3-6 months, when a strategic capability is proven
- **Patch releases**: continuous, as deploys land

No release ships on a calendar date alone. If criteria aren't met, the release slips and the slip is documented in `LEO_MASTER_PLAN.md` § Slip Log.

---

## Audience taxonomy

| Tier | Who | Sees |
|---|---|---|
| **Internal** | Jonathan, future Landtek staff | Everything |
| **Counsel** | Atty. Barandon, Atty. Botor, future counsel | Verified-only outputs (`_safe` views); briefings; evidence packs |
| **Client** | Patricia, Allan, Don Qi, future clients | Per-matter dashboards, deadline alerts, status digests |
| **Partner firm** | Future licensees | API + their tenanted instance |
| **Investor** | Future capital partners | Investor-grade financials + platform metrics |

A release is "for" a given tier when its features land in that tier's surface.

---

## The everyday-product philosophy

**Leo is a practice-management platform for property recovery and management, with an AI brain underneath.**

The brain (RAG, truth-negotiator, OCR, etc.) is invisible to users. What they see is the **workspace** — a place to:

- Track every client's progress at a glance
- Capture notes from calls, meetings, observations (typed, voice, photo)
- Upload evidence (documents, photos of titles, voicemails) from desktop or phone
- See per-matter timelines of everything that has happened
- Set deadlines and get reminded
- Search across everything ever captured
- Communicate with counsel + client + co-administrators inside the platform

**The database grows because the product is used.** Every note, every upload, every conversation becomes a row in the canonical ontology. The better the product, the richer the database, the smarter Leo becomes.

This is the inversion: today the database exists and the product is a thin set of CLI scripts on top. The target is to make **the daily-use product the primary surface** and have the database be the natural exhaust.

### Daily-use product surfaces (what users open)

| Surface | Who uses it | When |
|---|---|---|
| **Web app** (`app.landtek.com`) — primary workspace | Jonathan + Landtek staff | Every day, all day |
| **Mobile-optimized web** (same URL) | Jonathan when mobile, future staff | Photo/voice capture, on-the-go review |
| **Native iOS/Android app** | Long-term — staff + clients | After v3+ |
| **Telegram** | Quick captures + alerts | Throughout the day |
| **Email** | Inbound evidence + outbound updates | Always |
| **Client portal** (read-mostly) | Patricia, Allan, Don Qi, future clients | When they want to check status |
| **Partner-firm portal** | Future licensees | Daily, their own tenant |

### Daily-use product features (what users do)

Six core "verbs" every user expects in a workspace:

1. **See** — dashboard of what matters today, this week
2. **Capture** — drop a note, upload evidence, snap a photo, leave a voice note → auto-routed to the right matter
3. **Track** — every matter has a live timeline of activity + open items
4. **Search** — find anything across documents, notes, communications, entities
5. **Act** — set a deadline, send a message, log a call, draft a filing, approve a Leo proposal
6. **Collaborate** — assign work, comment, mention, share with counsel/client

Anything Leo does behind the scenes (RAG retrieval, validity audits, deadline prediction) shows up as a **suggestion or status indicator** in the workspace, not as a separate output to read.

---

## The roadmap

### v0.9 — "Alpha" (current as of 2026-05-20)

**Theme:** the engine works, but rough edges. No user-facing product yet — Jonathan operates via Termius + Telegram.

**Backend shipped:**
- Document ingestion (Drive + Gmail + Telegram uploads)
- Heightened Gemini OCR (2-pass cross-validation, gemini-2.5-flash, quality 0.8)
- Postgres v4 schema with pgvector halfvec(3072), entity resolution, audit log
- Truth-negotiator (backtest pass rate 67%)
- Comms chokepoint architecture (deployed 2026-05-19)
- Telegram inquiry queue + dispatcher
- 17 matters tracked across 2 active clients (MWK-001 + Paracale-001)
- 1,117 client-history events indexed
- Case bible generator (omnibus + per-matter)
- Daily strategic digest
- Improvement agent (self-diagnosis with leverage rankings)
- Opus pre-delivery audit gate
- 6 systemd services + n8n workflow + Flask leo_tools
- Cowork-bridge deploy pipeline
- Memory tree in git (52 rule files)

**Daily-use product:** None. Operation is CLI + Telegram + Termius + manual Drive folders.

**Known gaps:**
- **No web workspace** — every interaction goes through CLI or Telegram
- Bible NO-GO from Opus audit (5 existential fixes outstanding)
- 46.6% chunks verified (target ≥ 80%)
- Trajectory score 34/100
- 43-file DSN scatter, 15 TG queue bypasses, 26-file hard-coded TG ID
- Spend hit $4.96 in one day (ceiling $5)
- Single-cockpit dependency on Jonathan

**Audience:** Internal only. Counsel-facing outputs require manual audit pass.

---

### v1.0 — "Trustworthy Foundation + The Workspace"

**Theme:** Leo's word is good (ontology-as-truth structurally enforced), AND Jonathan stops opening Termius for routine work — there's an actual product to open every morning.

**Targeted readiness:** before 2026-06-02 (mediation date — Leo must be safe for counsel-facing output by then)

**Backend — must ship:**
- **Ontology-as-truth** structurally enforced
  - `provenance NOT NULL + source_doc_id` constraint on every fact-bearing table
  - `actor_lifespan` table + temporal-validity CHECK constraints (catches Cesar-post-2017 at insert time)
  - `output_audit.py` — pre-render check that every named entity, docket, date in proposed output exists in canonical inventory
- **Bible passes Opus audit GO**
- **Verified chunks ≥ 80%** (lift from 46.6% via nightly Haiku validity-audit backfill)
- **Auto-rollback sentinel** for comms / sweep / orchestrator
- **Critical-path test suite** (30-second smoke test)
- **TG dispatcher chokepoint** — close all 15 direct bypasses
- **DSN consolidation** into `landtek_core.config`
- **Heartbeat dashboard** — single page summarizing every sentinel + service + last-success time
- All 17 matters have explicit `best_state` target + assigned owner + deadline ladder

**Daily-use product — must ship (the workspace v1):**
- **Web app at `app.landtek.com`** — login (Jonathan + Don Qi), accessible from desktop + mobile browser
- **Dashboard / home** — what matters today: deadlines this week, open inquiries, recent activity feed across all matters
- **Matter list** — all 17 matters with stage + next action + last activity, sortable + filterable
- **Per-matter page** — header (parties, stage, venue, docket) + timeline (every event, document, transaction, communication) + documents list + notes + entities + deadlines
- **Quick-capture** — three buttons accessible from every screen:
  - **+ Note** — type a note, auto-tagged to matter (or "matter: ?" if unclear)
  - **+ Evidence** — drag-drop or photo-upload, lands in ingestion queue, auto-classified
  - **+ Deadline** — date picker + matter + description
- **Search bar** — global search across documents, notes, communications, entities; returns ranked results with snippets + matter
- **Mobile-optimized** — same web app, responsive layout; photo capture from phone camera + voice notes (transcribed)
- **Activity feed** — live (or near-live) feed of Leo's autonomous work: "Processed doc#943", "Verified chunk for T-32917", "Detected new ARTA correspondence in inbox"

**Audience:** Internal + counsel (Barandon, Botor). Counsel-facing outputs are now defensible. Workspace is staff-only for now.

**Readiness gate:**
- Opus audit gate returns GO on the omnibus bible
- Jonathan can run an entire workday from the web app without opening Termius (except for emergencies)
- At least one piece of evidence captured via mobile photo upload, processed end-to-end, surfaced in matter timeline

---

### v1.5 — "Multi-Front Recovery + Workspace Maturity"

**Theme:** Leo runs the whole recovery campaign across all fronts, AND the workspace is mature enough that capturing/finding/acting feels frictionless.

**Targeted readiness:** ~2026-06-30

**Backend — must ship:**
- **Financial ledger** — `accounts/transactions/monthly_overhead/value_extraction_events/asset_valuations` schema, populated from existing tax-doc corpus + Leo's API spend
- **Investor-grade reports** — P&L, runway, ROI per matter, valuation memos per property (first draft, not yet investor-pitched)
- **Per-matter ROI tracking** — what each matter has cost vs. recovered/projected
- **ARTA campaign dashboard** — all 9 matters with RA 11032 deadline ladders, bad-faith evidence yield, agency-response cadence
- **Cross-matter pattern detection** — same actor in multiple matters, same property contested across tracks
- **Per-transferee recovery posture** — all 20 named MWK transferees, individual case strategies
- **Asset valuation layer** — per-title tax-dec / assessed / zonal / declared market value, depressed-value buy/sell modeling
- **Bad-faith evidence map** — cross-matter index of agency stonewalling, opposing counsel patterns, refusals

**Daily-use product — must ship (workspace v2):**
- **Multi-user with permissions** — Jonathan, Don Qi, future Landtek staff; per-user roles (admin / paralegal / read-only)
- **Voice notes** — record on mobile, auto-transcribed (Whisper or similar), saved as a matter note + searchable
- **Photo capture from phone camera** — first-class flow: open camera in app → snap doc → matter is auto-suggested → confirm → enters ingestion queue
- **Push notifications** (mobile-web or PWA) — deadlines, new evidence ingested, Leo proposals waiting, urgent inquiries
- **Real-time activity feed** — live updates instead of polling
- **Email composer (in-app)** — drafts using verified-only citations; outbound goes through `comms.comms_send()` chokepoint; record of every sent message attached to matter
- **Telegram parity** — anything you can do in the web app is doable from Telegram via slash commands
- **Campaign view** — per-campaign dashboard (ARTA campaign, civil campaign, estate admin) showing all matters in that campaign, their stages, evidence yield, bad-faith hits
- **Matter detail enhancements** — financial sub-tab (cost vs. recovery), evidence sub-tab (gap list with priority), parties sub-tab (every actor + role + status)
- **Saved searches / smart filters** — "all open ARTA deadlines next 14 days", "all matters where Cesar appears", etc.

**Audience:** Internal + counsel + Jonathan-as-strategist + Don Qi (administrator).

**Readiness gate:**
- Every active matter has a populated `best_state` and `next_action`
- Financial ledger reconciles within ±5% of bank statements
- Bad-faith map has at least 10 cross-matter entries
- Don Qi can use the workspace independently without Jonathan walking him through it

---

### v2.0 — "Multi-Client Scale"

**Theme:** Onboarding client #3 is a wizard, not a code change.

**Targeted readiness:** ~2026-08-15

**Must ship:**
- **Monolithic file decomposition complete** — `generate_case_bible.py`, `tg_dispatcher.py`, `build_system_blueprint.py` split into testable submodules (≤200 lines each)
- **Per-client config injection** — every script honors a `--client` flag or reads from a client config table
- **Client onboarding wizard** — intake form → matter scaffolding → Drive folder seed → contact mapping → first deadline import
- **Per-client isolation** — separate folders, separate Telegram routes, separate spend tracking
- **Light client portal v1** — read-only per-client dashboard showing all matters, deadlines, recent activity (web view, not yet WhatsApp)
- **Email reply bot** — Leo replies to client emails directly via existing Gmail integration, audience-gated through `comms_send()`

**Audience:** Internal + counsel + first client preview (read-only portal).

**Readiness gate:** A new client can be onboarded end-to-end in under 1 hour without code changes; their data is fully isolated from other clients.

---

### v2.5 — "Channel Expansion"

**Theme:** Meet clients where they are.

**Targeted readiness:** ~2026-09-30

**Must ship:**
- **WhatsApp Business API adapter** — Meta verification + WABA provider (360dialog or Twilio) + inbound webhook + outbound API; same audience-gated chokepoint
- **Web chat widget** — embeddable on landtek.com / client portals; first-contact + lead capture
- **Email reply bot** (v2 — better threading + attachment handling)
- **Channels table** — `channels {channel, webhook_url, auth_secret, default_locale}` formalized
- **Identity bridge** — same client across email + WhatsApp + Telegram resolves to one mapped_client_code

**Audience:** Internal + counsel + clients (now multi-channel reachable).

**Readiness gate:** A client message arriving on WhatsApp, web chat, or email is processed identically to one arriving on Telegram.

---

### v3.0 — "Platform"

**Theme:** Leo is licensable. Other PH property firms can run their own Leo.

**Targeted readiness:** ~2026-11-30

**Must ship:**
- **Public REST/GraphQL API v1** — `/api/v1/leo/chat`, `/api/v1/leo/verify`, `/api/v1/leo/extract`, `/api/v1/leo/onboard`, `/api/v1/leo/portfolio`
- **Multi-tenant architecture** — per-firm data isolation, per-firm config, per-firm spend tracking
- **Quota + billing** — per-firm API key + token meter + monthly invoice
- **First partner firm licensed** — one external PH property firm running on Leo, paying recurring fees
- **Audit-log per tenant** — each firm can pull their own audit log
- **Documentation site** — public API docs, ontology spec, integration guide

**Audience:** Internal + counsel + clients + **partner firms (licensees)**.

**Readiness gate:** First external firm processes a real matter end-to-end on the licensed instance, with no Landtek intervention; their data never touches MWK-001 or Paracale-001 tenancy.

---

### v3.5 — "Predictive"

**Theme:** Leo tells you what to do before you ask.

**Targeted readiness:** ~2027-01-31

**Must ship:**
- **Goal accelerator daily proposals** — 1-3 actions per active matter + 1-2 firm-level actions, delivered Telegram with one-tap accept/decline; backed by `truth_negotiator` (no hallucinated suggestions)
- **Procedural deadline prediction** — given party filings + 18 PH civil-procedure stages, Leo predicts deadlines (doesn't just log them)
- **Low-hanging-fruit engine** — auto-flag opportunities where intrinsic > 1.4 × market + mitigation cost low; the asset-acquisition competitive moat
- **Hyper-vigilance meta-agent (full)** — second AI node auditing Leo every hour; back-tests truth_negotiator; auto-remediates gaps before Jonathan flags them
- **Proposal acceptance metrics** — what % of Leo's proposed actions get accepted; tune ranking

**Audience:** Internal + counsel + clients + partners.

**Readiness gate:** ≥ 40% of Leo's daily proposed actions are accepted; ≤ 0 false-positive deadline alerts in 30 days.

---

### v4.0 — "Investor-Grade"

**Theme:** Landtek is a fundable business with provable platform economics.

**Targeted readiness:** ~2027-03-31

**Must ship:**
- **Investor-grade financial reports** — audited P&L by client cohort, by matter type, by channel; runway with sensitivity analysis
- **Platform metrics dashboard** — per-tenant cost-to-serve, gross margin, churn projection
- **Cohort analytics** — which client types convert highest LTV; which matters yield highest ROI
- **Capital pitch deck** — auto-generated quarterly from live data
- **Demonstrable platform ROI** — ≥ 1 paying licensee with positive unit economics

**Audience:** All previous + **investors**.

**Readiness gate:** Investor pitch deck regenerates from live data with zero manual editing; numbers reconcile with bank + ledger to penny.

---

### v5.0 — "International"

**Theme:** Beyond PH. Diaspora-focused, jurisdiction-extensible.

**Targeted readiness:** ~2027-06-30

**Must ship:**
- **Second jurisdiction onboarding proof** — one client matter outside PH (US, AU, or CA) handled by Leo with appropriate jurisdiction-specific legal framework plugged in
- **Pluggable legal frameworks** — abstract "PH Civil Code rubric" as a `legal_framework` plugin pattern
- **Diaspora client acquisition** — Leo as the "trusted bridge" for US/AU/CA-based heirs of PH property (the original Patricia Zschoche use case, productized)
- **Cross-jurisdiction asset tracking** — clients with PH + US/AU/CA holdings managed in one place

**Audience:** All + **diaspora clients globally**.

**Readiness gate:** First non-PH matter ships verified output without bespoke code changes.

---

## What ships when (summary table)

| Version | Theme | Target | Audience reach |
|---|---|---|---|
| **v0.9** | Alpha | ✓ (current) | Internal only |
| **v1.0** | Trustworthy Foundation | 2026-06-02 | + Counsel |
| **v1.5** | Multi-Front Recovery | 2026-06-30 | (counsel + strategist) |
| **v2.0** | Multi-Client Scale | 2026-08-15 | + Clients (portal) |
| **v2.5** | Channel Expansion | 2026-09-30 | + Clients (WhatsApp/web/email) |
| **v3.0** | Platform | 2026-11-30 | + Partner firms (licensees) |
| **v3.5** | Predictive | 2027-01-31 | (all + sharper) |
| **v4.0** | Investor-Grade | 2027-03-31 | + Investors |
| **v5.0** | International | 2027-06-30 | + Diaspora globally |

---

## How releases get cut

1. **Each release has an owner** (initially Jonathan; later, possibly a release manager role)
2. **A release is opened** as a tracked milestone with its readiness criteria
3. **Deploys land continuously** into `main` (via the cowork-bridge pipeline)
4. **When all readiness criteria pass**, the release is tagged: `git tag vX.Y.Z` + release notes written
5. **Release notes** summarize what shipped, what's still in-progress (rolled to next), and any known gaps
6. **Release notes file** lives at `releases/vX.Y.Z.md`
7. **CHANGELOG.md** at repo root is the rolling summary

---

## Marketing surfaces (where releases get told)

| Surface | Audience | Cadence |
|---|---|---|
| **`CHANGELOG.md`** | Internal + counsel | Updated per release |
| **`releases/` directory** | Internal + counsel | Per release |
| **Pitch deck** | Investors | Quarterly (auto-regen from v4.0+) |
| **landtek.com release page** | Public / prospects | Major + Minor releases |
| **Partner firm portal** | Licensees | Every release affecting their tenant |
| **Client portal "What's new"** | Clients | Minor releases with client-visible changes |

---

## Open questions for Jonathan (to be resolved before v1.0 cuts)

1. **Versioning kickoff** — should v0.9 be retroactively tagged at the current commit so we have a baseline? Or do we start tagging at v1.0?
2. **Release manager role** — stays with you indefinitely, or do we hire/delegate by v2.0?
3. **Public release page** — do we want landtek.com to publicly list version history (transparency play) or keep it internal (competitive secrecy)?
4. **Partner firm acquisition** — how is the first licensee sourced? Direct outreach, referral, public marketing?
5. **Capital partner approach** — bootstrap to v4.0 first, or raise on the v1.0/v1.5 momentum?

---

_This document is living. Update it when a release tag is cut, when readiness criteria change, or when scope shifts between versions. All updates go through the WORKFLOW.md git discipline._
