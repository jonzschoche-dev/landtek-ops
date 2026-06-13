# LeoLandTek — Master Plan (single source of truth)

> **THIS IS THE ONLY AUTHORITATIVE PLAN. Update it in place.**
> Do not create parallel directive / roadmap / status / deployment-plan docs. That sprawl —
> and stale "READ FIRST" pointers into it — is what kept dragging every new session back to a
> May-2026 reality and causing knowledge regression. `CLAUDE.md` points here as READ FIRST.
>
> **Last updated:** 2026-06-12 — consolidates 9 prior planning docs (now in `archive/planning-2026-06/`).
> **Provenance discipline applies to THIS doc too.** Facts are tagged **✅ VERIFIED** (checked against the
> live system this session) or **⚠️ UNVERIFIED** (carried from May-2026 docs, not re-checked — confirm
> before relying). Never let an unverified carry-over harden into an asserted fact.

---

## 1. North star & live legal posture

**✅ Aug 12, 2026 — Jonathan Zschoche testifies as Patricia Keesey Zschoche's witness** in **Civil Case 26-360 (Zschoche v. Balane)**.

- **✅ Court: MTC Mercedes, Camarines Norte; governed by Summary Procedure.** NOT the RTC. NOT an "Aug 1 pre-trial." Pre-trial was **May 13, 2026 (passed)** — the case advanced into motion practice.
- **✅ Live now:** our **Motion for Summary Judgment** pending a ruling; defendants moving to admit **Gloria Balane's Judicial Affidavit** (excluded at pre-trial); **mediation** held ~June 2.
- **Posture: wartime, not peacetime.** Everything the stack does serves the Aug 12 deadline / the SJ motion, or it is deferred. No from-scratch rebuilds during the live window.

**✅ Verified case corrections (override older docs / CLAUDE.md):**
- Balane's title = **T-079-2021002126** (not …2127).
- Operative instrument = the **16 Mar 1992 SPA** to de la Fuente (revoked **2005**, *published* only **2020**).
- SJ kill-shot = that 1992 SPA grants only "negotiate," **not "sell"** → sale is **void**, good faith irrelevant (*nemo dat quod non habet*). Backup prong: revocation + duty of inquiry (*Yoshizaki*).

## 2. Active deliverable

**✅ Balane Evidence Spine — `case_work/MWK-001/BALANE_EVIDENCE_SPINE.md`.** Source-grounded void-chain, both sides' arguments, and a cross-examination map built from Gloria Balane's own affidavit (doc 1089). Feeds the SJ motion + Aug 12 testimony.
- **Next:** SJ/trial exhibit list + cross-exam outline; obtain the **2016 Deed of Absolute Sale** to Balane (CTC from RD Daet — not yet in corpus); vision-OCR the 1999/revocation images (docs 1132–1134); close the T-32917 → T-52540 chain hole.

## 3. Current verified state (2026-06-12)

- **✅ Infra:** single DigitalOcean droplet — **1 vCPU / 2 GB / 67 GB NVMe + 2 GB swap** (39% disk), Premium Intel, $16/mo (upgraded 2026-06-13 from 1 GB / 33 GB; load dropped 1.8→0.5 — **freeze risk resolved**, single vCPU adequate). Postgres in docker `n8n-postgres-1` (`172.18.0.3:5432/n8n`). Repo `landtek-ops`, pushed from Mac (`~/landtek`) + VPS (`/root/landtek`). Tailscale SSH (check-mode reauth).
- **✅ Corpus:** ~**1,056 canonical** docs (1,126 total). All 26-360 court filings are blended in from Barandon's emails, incl. **both sides' judicial affidavits**. **~791 MWK-001 docs sit at `pending_classification`** (text captured, integration layer unfinished); 95 in `error`.
- **✅ Daemons active:** `leo-simulator`, `landtek-truth-loop`, `landtek-fullstack-loop`, `landtek-corpus-backfill`, `landtek-tg-router/-inbox/-media`. **`truth-qa-loop` INACTIVE.**
- **✅ Ingestion:** Gemini vision OCR (free tier — exhausted) + **local Tesseract via PyMuPDF** (the cost-driven pivot). Qdrant Cloud embeddings (gemini-embedding-001).
- **✅ Reasoning:** Claude `sonnet-4-5`; `truth_negotiator` + `truth_judge` + `claim_truth_verdicts`; `_safe` views; provenance grading (verified / inferred_strong / inferred_weak).

**⚠️➜🔴 COST — the biggest open liability.** Real burn ~**$40/day**, driven by `leo-simulator` running through n8n (439 execs/24h). `cost_governor` (deploy_420) enforces a daily cap **but does not see n8n spend** → `llm_spend` reads **$0**. **Cost is invisible to our own telemetry.** Simulator ROI ≈ 1 verified improvement per 1,744 probes. **Decision pending (Jonathan): throttle / instrument / cap the sim** (do not auto-stop — operator's standing rule).

## 4. Strategic frame (carried forward — still sound)

- **Vision:** the most truth-seeking, deadline-reliable property + legal-ops AI; database is exhaust, the workspace is the product.
- **8 non-negotiable principles:** (1) no hallucination, (2) never miss a deadline, (3) comms chokepoint sacred (S14 Telegram rules), (4) `provenance_level` sacred, (5) information is gold, (6) self-research, (7) git discipline, (8) hard cost stop. **⚠️ Principle 8 is currently violated in practice — see §3.**
- **5 elite layers:** per-matter · per-portfolio · per-firm · per-channel · per-jurisdiction.
- **Phases:** 0 safety substrate · 1 data integrity · 2 relational + financial · 3 autonomous agency · 4 channels · 5 multi-jurisdiction. **⚠️ All May-2026 phase timelines are obsolete — rebaseline against Aug 12.**

## 5. Operating model (multi-agent — condensed; full git protocol in CLAUDE.md)

- **Two agents:** VPS Claude (`/root/landtek`, runtime/ops) + Mac Claude (`~/landtek`, authoring/design). Both push to `landtek-ops`. Mac auto-sync launchd pulls every 2 min (fast-forward only).
- **Git discipline:** `pull --rebase` before work; commit **specific paths** (never `git add .`); deploy via `scripts/landtek_git_routine.sh deploy NN "title" paths`; never force-push `main`; never commit secrets (`.env`, `*.pem`, `google-creds.json`).
- **Deploy pipeline:** clone-first author → diff review → `truth_tests` gate → commit `deploy_NN` → `cowork-bridge` executes batch scripts (`leolandtek-deploys/inbox/`) → heartbeat watch.
- **Safety substrate:** provenance ontology = master of truth; `_safe` views for any legal output; never break comms; auth-gate every access; clone-first authoring.
- **Health invariants:** daemons active · heartbeat < 1 hr · Telegram bot responds · n8n active.

## 6. Roadmap (rebaselined to Aug 12 — legal deliverable first)

1. **✅ in progress — Balane SJ/testimony pack** (spine → exhibit list → cross-exam outline). The only calendar-bound work; everything else yields to it.
2. **✅ Cost governance — DONE (deploy_427).** `scripts/anthropic_spend_bridge.py` records n8n/simulator token usage into `llm_spend`, so `cost_governor.can_afford()` now gates on TOTAL burn. Validated: 25 sim execs = $2.82 (~$0.11/probe, ~32k input tokens each — *that* was the ~$40/day). Live cockpit panel at `/ops/spend` (deploy_428). The cap becomes real the moment the bridge timer is enabled (see Activation).
3. **Data integrity** — title-chain holes + live-filing exhibit-tier still open. **Corpus backlog (re-assessed 2026-06-13):** 938 docs at `pending_classification` = 703 OCR-able digital docs the backfill daemon isn't draining (idle despite eligible — needs a runtime look at its Qdrant-seed startup) + ~54 needing Drive/Gmail re-fetch + ~50 unsupported formats (.eml/.docx/zip/corrupt). **No automated `pending→classified` transition exists** (only one-shot `scannerpro_ingest.py` sets it); the missing classify step is LLM-dependent = credit-gated. This is an *operational* drain, not a creditless build.
4. **Carried-over "blockers" — RE-VERIFIED 2026-06-13 (mostly de-haunted):** heartbeat dashboard ✅ exists (`/ops/health` + `/ops/spend`); auth-gate ✅ exists (`leo_tools/server.py`, `channel_adapters.py`; `/files/c/` is intentionally public); DSN "fragmentation" benign (3 env-var names → one DB); Bible pipeline built (`generate_case_bible.py` + `opus_validate_bible.py`) — only the Opus audit *verdict* is unverified (needs an Opus run = credit-gated); **auto-rollback sentinel genuinely not built** (mitigated by the truth_tests deploy gate + manual `git revert` — low priority). `leo_qa_runner` v2-stub kinds fixed (deploy_429).
5. **Web workspace v1** — deferred (peacetime; the server-rendered Flask cockpit at `/ops` suffices for now; removes the Termius dependency only when the live matter is clear).

## 6.5 Activation — flip the stack ON when credits land (architecture is in place)

Everything is built cold and **inert**: the spend-bridge timer is disabled, the synthetic loops
are paused/disabled, Leo answers only once `ANTHROPIC_API_KEY` has balance. Construction cost $0;
only activation consumes tokens. One safe, ordered, idempotent step — run on the VPS from `/root/landtek`:

    ./scripts/activate_stack.sh                  # DRY RUN — prints the plan, changes nothing
    ./scripts/activate_stack.sh --go             # bridge FIRST, then truth-loop + fullstack-loop
    ./scripts/activate_stack.sh --go --with-sim  # ALSO re-enable the simulator (opt-in; the big burner)

Order is enforced for a reason: the **cost-metering bridge goes live before the loops**, or they burn
invisibly again (the outage). The simulator is opt-in (~$47/day, ~1 verified improvement per 1,744
probes — decide per §7 first; consider a wider cycle / lower `LANDTEK_DAILY_LLM_CAP`). After running,
confirm `/ops/spend` shows recorded n8n spend + the cap enforcing, and that Leo replies.

## 7. Open decisions for Jonathan (still live)

- The simulator burn — throttle, instrument, or cap? (§3)
- ARTA cases: 9 separate matters or 1 campaign?
- Paracale-001: active, or maintenance mode?
- Don Qi role (client vs co-principal); Botor guardianship as its own track?
- Recovery vs. settlement posture per transferee (the 20-transferee campaign).
- Product versioning kickoff; capital strategy.

## 8. Slip / change log

- **2026-05-13** — pre-trial held; case advanced to motion practice (phase change, not a slip).
- **2026-06-02** — mediation held; May-2026 docs had targeted a "v1.0 by June 2" cut — not cut; north star reset to **Aug 12** (trial testimony).
- **2026-06-13** — droplet upgraded 1 GB→2 GB RAM / 33→67 GB / +2 GB swap ($16/mo); load 1.8→0.5, freezes resolved. VPS git resynced **381→423** (had drifted 42 commits behind, phantom-dirty — running code already matched origin, only HEAD was stale). `notifications/pending.txt` gitignored to stop the recurring dirty-tree-blocks-pull friction that caused the drift.
- **2026-06-13** — **stack-completion build (deploys 427–430), architecture-first / zero API spend:** cost-metering bridge (`anthropic_spend_bridge.py` → `llm_spend`; validated 25 execs = $2.82) + `/ops/spend` cockpit + `leo_qa_runner` v2-stub fix + `activate_stack.sh` runbook + carried-over blockers re-verified (mostly de-haunted). Synthetic loops removed from `fullstack_engineer` CRITICAL so SRE no longer auto-resurrects the paused sim. The stack is built + inert; it flips on via `activate_stack.sh` once credits are topped.
- *(append entries as milestones move — cause + new date)*

## 9. Sources & related

- **Consolidated & archived → `archive/planning-2026-06/`:** `DIRECTIVE.md`, `LEO_MASTER_PLAN.md`, `LEO_RELEASE_ROADMAP.md`, `LEOLANDTEK_DEPLOYMENT_PLAN.md` (+ `.mac-backup`), `STATUS.md`, `WORKFLOW.md`, `LANDTEK-PIPELINE-REPORT-2026-05-10.md`, `AGENDA.md.deprecated-2026-05-12`. *(Archived, not deleted — their detail is preserved in git for reference; they are no longer authoritative.)*
- **Live companions (kept):** `CLAUDE.md` (operating instructions / where things are — incl. the full git + simulator-safety protocols), `DEPLOY_LOG.md` (append-only deploy log), `memory/MEMORY.md` (recall index), `case_work/MWK-001/BALANE_EVIDENCE_SPINE.md` (active deliverable).
