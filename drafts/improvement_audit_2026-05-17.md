# Landtek Improvement Audit — 2026-05-17
_Generated 05:23 UTC · improvement_agent.py_

## Trajectory snapshot

- **Trajectory score:** 34 / 100
- **Commentary:** Strong domain depth, near-zero cost; but 51 files with infra rot, 50% audit gap, 64.7% backtest, and 1 client block the goal hard.

## System KPIs

| Metric | Value |
|---|---|
| `active_matters` | 9 |
| `active_clients` | 1 |
| `avg_call_cost_7d` | 0.0049 |
| `spend_last_7d` | 2026-05-16=$0.8106, 2026-05-17=$0.5126 |
| `validity_audit_coverage_pct` | 50.0 |
| `audits_done` | 212 |
| `audits_auditable` | 424 |
| `chunks_verified_pct` | 55.5 |
| `backtest_pass_rate_7d_pct` | 64.7 |
| `hallucinations_logged_30d` | 2 |
| `client_history_events` | 915 |

## Static-code scan findings

- ⚠️ `hard_coded_dsn` (38): classify_execution_status.py, doc_date_extractor.py, seed_asset_risks.py, correlate_orphan_cases.py, gmail_watcher.py, systems_analyzer.py, party_filing_classifier.py, seed_firm_goals.py …
- ⚠️ `reimpl_env_loader` (23): doc_date_extractor.py, gmail_watcher.py, systems_analyzer.py, batch_extract_unextracted.py, educate_leo.py, extract_tax_doc_financials.py, financial_report.py, generate_case_posture_report.py …
- ⚠️ `hard_coded_jonathan_tg_id` (25): get_client_for_telegram_id.py, gmail_watcher.py, systems_analyzer.py, safe_ingest_wrapper.py, educate_leo.py, log_telegram_with_client.py, financial_report.py, deadline_sentinel.py …
- ⚠️ `tg_send_direct_bypass_queue` (16): gmail_watcher.py, systems_analyzer.py, safe_ingest_wrapper.py, educate_leo.py, financial_report.py, deadline_sentinel.py, leo_watchdog.py, goal_accelerator.py …
- ⚠️ `anthropic_no_cache_control` (1): synthesize_case.py
- ⚠️ `sonnet_used_where_haiku_might_do` (2): truth_negotiator.py, improvement_agent.py
- ⚠️ `large_files` (6): truth_negotiator.py (523 lines), bulk_ingest_mwk.py (507 lines), timeline.py (507 lines), build_manual_extraction_packet.py (505 lines), build_system_blueprint.py (689 lines), ingest.py (544 lines)
- ⚠️ `missing_landtek_core_import` (52): classify_execution_status.py, doc_date_extractor.py, seed_asset_risks.py, correlate_orphan_cases.py, verification_ladder.py, backfill_assets.py, gmail_watcher.py, systems_analyzer.py …

## Top leverage moves

### 1. Extract a single `landtek_core.py` bootstrap module and enforce it as the mandatory first import across all 51 non-compliant files  _(leverage 10/10)_
- **WHY:** Reliability + Cost-discipline: scattered DSN strings, reimplemented env loaders, and hardcoded Telegram IDs across 38/23/25 files respectively create silent prod failures, config drift, and a maintenance surface that will block multi-client scaling
- **HOW:** 1) Create `landtek_core.py` with: `get_db()` (DSN from env), `get_env(key)`, `JONATHAN_TG_ID = int(os.getenv('JONATHAN_TG_ID'))`, `tg_queue_send(chat_id, msg)` wrapper that always routes through queue. 2) Run `sed` + AST rewriter script to replace all inline patterns in the 51 files. 3) Add a pre-commit hook: `python -m ast` parse + grep for `psycopg2.connect('postgres` and `JONATHAN_TG_ID = 6` literals — fail CI if found. 4) Deploy and smoke-test deadline_sentinel + gmail_watcher. Target: 0 hard-coded DSN files by next audit.
- **COST:** 4h dev + 0 LLM cost; one-time

### 2. Route 100% of Telegram sends through a durable queue and ban all `tg_send_direct_bypass_queue` call sites in the 16 offending files  _(leverage 9/10)_
- **WHY:** Reliability + Multi-client scalability: direct-bypass calls mean rate-limit hits, duplicate alerts, and no audit trail — catastrophic once client count grows beyond 1; currently 2 hallucinations logged likely correlate with unsuppressed duplicate sends
- **HOW:** 1) Add `tg_queue_send()` in `landtek_core.py` (Move 1 dependency) that inserts into `tg_outbox` table with dedup key = `(chat_id, sha256(msg), minute_bucket)`. 2) Run a worker (`tg_dispatcher.py`) that flushes queue every 15s with exponential backoff. 3) Grep-ban pattern `bot.send_message(` / `requests.post(TG_URL` outside `tg_dispatcher.py` — add to pre-commit hook. 4) Refactor the 16 files to call `tg_queue_send()`. 5) Add KPI: `tg_direct_bypass_fires_24h` → alert if > 0.
- **COST:** 3h dev; $0 LLM; persistent reliability gain

### 3. Push validity audit coverage from 50% to 90% by auto-scheduling unaudited chunks through the meta-agent nightly sweep  _(leverage 9/10)_
- **WHY:** Evidence-grade discipline: 424 auditable chunks but only 212 done and chunk verification at 55.5% is the single biggest gap blocking Leo from being trusted on contested title and tax matters — the core PH property value prop
- **HOW:** 1) Query `SELECT id FROM chunks WHERE audited = false LIMIT 50` nightly in `meta_agent.py`. 2) Pipe each through existing validity ladder using Haiku (not Sonnet) with prompt: 'Does this chunk contradict any verified fact in the case? Output JSON {verdict, confidence, contradiction_quote}'. 3) Write results to `chunk_audits` table; flip `audited = true`. 4) Add `validity_audit_coverage_pct` and `chunks_verified_pct` to the daily digest with delta vs prior day. 5) Set meta-agent alert threshold: if nightly batch < 30 chunks processed, fire Telegram warning. Target: 90% coverage in 14 days at ~$0.003/chunk = ~$0.63 total.
- **COST:** $0.63 one-time LLM (Haiku); 2h dev

### 4. Refactor the 6 large files (505–689 lines) into domain modules and add Anthropic prompt caching to `synthesize_case.py`  _(leverage 8/10)_
- **WHY:** Cost-discipline + Proactive autonomy: `build_system_blueprint.py` at 689 lines is a god-file that slows iteration; `synthesize_case.py` lacks cache_control despite being the highest-token call — fixing both cuts cost and unblocks autonomous case synthesis firing without approval
- **HOW:** 1) Split `build_system_blueprint.py` → `blueprint_schema.py`, `blueprint_renderer.py`, `blueprint_validator.py`. 2) Split `truth_negotiator.py` (523L) → `claim_extractor.py` + `verdict_writer.py`. 3) In `synthesize_case.py`: wrap the static system prompt block with `{'type':'text','text':...,'cache_control':{'type':'ephemeral'}}` — Anthropic caches prompts >1024 tokens for 5 min, saving ~60% on repeat calls. 4) Downgrade `truth_negotiator.py` and `improvement_agent.py` from Sonnet to Haiku for non-verdict passes (classification, routing) — use Sonnet only for final verdict emission. 5) Add per-file line-count check to CI: warn if > 400 lines.
- **COST:** 3h dev; LLM savings est. $0.15–0.30/day ongoing

### 5. Instrument a multi-client readiness scorecard and wire it into the daily digest to make scale-blockers visible before the second client onboards  _(leverage 8/10)_
- **WHY:** Multi-client scalability: active_clients=1 with ARR=0 means Leo has no revenue proof — the scorecard creates weekly pressure to fix the exact gaps (DSN isolation, TG routing per client, per-client cost tracking) that would cause outages at client #2
- **HOW:** 1) Add `client_readiness` table: columns `check_name`, `status` (red/amber/green), `detail`, `updated_at`. 2) Populate nightly via `meta_agent.py`: check (a) 0 hard-coded DSNs, (b) 0 TG bypass calls, (c) validity_audit_coverage > 80%, (d) backtest_pass_rate > 80% (currently 64.7% — amber), (e) per-client cost isolation exists, (f) hallucinations_30d = 0. 3) Render scorecard as first section of daily Telegram digest with emoji traffic lights. 4) Add `trajectory_score` field (mirrors this agent's output) to digest so Jonathan sees Leo's self-assessed readiness daily. 5) Gate any new client onboarding on all-green status.
- **COST:** 2h dev; $0 LLM; 1 DB migration
