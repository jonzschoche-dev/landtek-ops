# Landtek Improvement Audit — 2026-05-17
_Generated 22:01 UTC · improvement_agent.py_

## Trajectory snapshot

- **Trajectory score:** 34 / 100
- **Commentary:** Strong data depth (1117 events, 17 matters) but 46% verified chunks, 43-file DSN scatter, and 15 TG bypasses cap trust + scale ceiling hard.

## System KPIs

| Metric | Value |
|---|---|
| `active_matters` | 17 |
| `active_clients` | 2 |
| `avg_call_cost_7d` | 0.0043 |
| `spend_last_7d` | 2026-05-16=$0.8106, 2026-05-17=$4.9641 |
| `validity_audit_coverage_pct` | 50.0 |
| `audits_done` | 212 |
| `audits_auditable` | 424 |
| `chunks_verified_pct` | 46.6 |
| `backtest_pass_rate_7d_pct` | 66.9 |
| `hallucinations_logged_30d` | 2 |
| `client_history_events` | 1117 |

## Static-code scan findings

- ⚠️ `hard_coded_dsn` (43): classify_execution_status.py, doc_date_extractor.py, seed_asset_risks.py, correlate_orphan_cases.py, gmail_watcher.py, systems_analyzer.py, party_filing_classifier.py, seed_firm_goals.py …
- ⚠️ `reimpl_env_loader` (23): doc_date_extractor.py, gmail_watcher.py, systems_analyzer.py, batch_extract_unextracted.py, educate_leo.py, extract_tax_doc_financials.py, financial_report.py, generate_case_posture_report.py …
- ⚠️ `hard_coded_jonathan_tg_id` (26): get_client_for_telegram_id.py, gmail_watcher.py, systems_analyzer.py, safe_ingest_wrapper.py, educate_leo.py, log_telegram_with_client.py, financial_report.py, deadline_sentinel.py …
- ⚠️ `tg_send_direct_bypass_queue` (15): gmail_watcher.py, systems_analyzer.py, safe_ingest_wrapper.py, educate_leo.py, financial_report.py, deadline_sentinel.py, leo_watchdog.py, conflict_detector.py …
- ⚠️ `anthropic_no_cache_control` (1): synthesize_case.py
- ⚠️ `sonnet_used_where_haiku_might_do` (2): truth_negotiator.py, improvement_agent.py
- ⚠️ `large_files` (8): tg_dispatcher.py (778 lines), truth_negotiator.py (525 lines), generate_case_bible.py (1300 lines), bulk_ingest_mwk.py (507 lines), timeline.py (507 lines), build_manual_extraction_packet.py (505 lines), build_system_blueprint.py (689 lines), ingest.py (544 lines)
- ⚠️ `missing_landtek_core_import` (57): classify_execution_status.py, doc_date_extractor.py, seed_asset_risks.py, correlate_orphan_cases.py, verification_ladder.py, backfill_assets.py, gmail_watcher.py, systems_analyzer.py …

## Top leverage moves

### 1. Consolidate all DSN/env loading into a single landtek_core.config module and enforce via pre-commit hook  _(leverage 10/10)_
- **WHY:** Cost-discipline + Reliability: 43 files with hard-coded DSNs and 23 with reimplemented env loaders are a credential-leak and drift risk; a single source of truth cuts future refactor cost to zero
- **HOW:** 1) Create landtek_core/config.py with get_dsn(), get_tg_id(user), load_env() using python-dotenv + Vault/env fallback. 2) Write a sed/ast-grep script that auto-replaces all hard-coded DSN strings and reimpl loaders across the 43+23 file lists. 3) Add a pre-commit hook (grep for 'postgresql://' and 'os.getenv("DB' outside landtek_core) that blocks commits. 4) Run + merge in one PR. 5) Add JONATHAN_TG_ID to config.get_tg_id('jonathan') so 26-file scatter is fixed in same pass.
- **COST:** ~3h dev + 0 LLM spend; one-time

### 2. Route all outbound Telegram sends through tg_dispatcher queue — eliminate 15 direct-bypass callers  _(leverage 9/10)_
- **WHY:** Reliability + Proactive autonomy: direct-bypass files (gmail_watcher, deadline_sentinel, leo_watchdog etc.) cause duplicate alerts, skip rate-limiting, and make false-alert tracking impossible — directly hurting the '<1 false alert/month' KPI
- **HOW:** 1) Add tg_dispatcher.enqueue(chat_id, text, priority) as the sole public send surface. 2) In each of the 15 bypass files replace bot.send_message() calls with tg_dispatcher.enqueue(). 3) Add a dedup key (matter_id + alert_type + date) to the queue so same-day repeated alerts are suppressed. 4) Emit a hallucinations/false-alert counter to system_kpis on each suppressed dupe. 5) Add integration test asserting no file outside tg_dispatcher imports telegram.Bot directly.
- **COST:** ~4h dev + 0 LLM spend

### 3. Lift chunks_verified_pct from 46.6% to 80%+ by running a nightly parallel validity-audit backfill job  _(leverage 9/10)_
- **WHY:** Evidence-grade discipline: at 46.6% verified and 66.9% backtest pass rate, Leo is citing unvetted chunks in ~half of outputs — the single biggest hallucination liability and blocker to 'greatest land exec assistant' credibility
- **HOW:** 1) Query all chunks WHERE validity_checked = false LIMIT 500 per run. 2) For each chunk, call Haiku (not Sonnet) with a structured verify prompt: does chunk contradict its source doc hash? Return {valid: bool, confidence: 0-1, note}. 3) Write result to validity_audit table. 4) Schedule via pg_cron or APScheduler at 02:00 PHT nightly. 5) Add validity_audit_coverage_pct and backtest_pass_rate to daily digest. 6) Gate any case-posture or bible generation on coverage >= 75% for that matter.
- **COST:** ~2h dev; ~$0.80/night LLM (Haiku at $0.00025/1K tokens × 500 chunks × ~400 tokens each)

### 4. Decompose the 4 files >600 lines (generate_case_bible.py 1300L, tg_dispatcher.py 778L, build_system_blueprint.py 689L) into tested sub-modules  _(leverage 8/10)_
- **WHY:** Multi-client scalability + Reliability: monolithic files cannot be unit-tested per-client, hide dead code, and make onboarding client #3 a fork risk; splitting is prerequisite for per-client config injection
- **HOW:** 1) generate_case_bible.py → bible_fetcher.py, bible_formatter.py, bible_renderer.py + bible_orchestrator.py (≤200L each). 2) tg_dispatcher.py → tg_queue.py, tg_rate_limiter.py, tg_sender.py. 3) build_system_blueprint.py → blueprint_schema.py, blueprint_builder.py, blueprint_exporter.py. 4) For each split, write pytest covering happy-path + empty-matter edge case. 5) Delete dead functions surfaced during split (expect 15-20% line reduction). 6) Update missing_landtek_core_import list — these new modules get the core import by default.
- **COST:** ~8h dev + $0.50 LLM (Claude for docstring generation); one-time

### 5. Enable Anthropic prompt caching on all high-frequency Sonnet calls (synthesize_case, truth_negotiator, improvement_agent) and downgrade truth_negotiator/improvement_agent to Haiku for non-verdict tasks  _(leverage 8/10)_
- **WHY:** Cost-discipline: spend spiked to $4.96 on May 17 — caching on repeated system prompts cuts Sonnet cost ~80% on cache hits; Haiku substitution on the 2 flagged files saves ~6× per call; both keep daily spend under $5 ceiling as client count grows
- **HOW:** 1) In synthesize_case.py add cache_control: {type: ephemeral} to the system prompt block (already flagged as missing). 2) In truth_negotiator.py identify which functions produce final legal verdicts (keep Sonnet) vs. parsing/classification tasks (switch to claude-haiku-3-5). 3) In improvement_agent.py use Haiku for the code-scan summarization pass; Sonnet only for final leverage scoring. 4) Add a cost_guard decorator that logs model, tokens_in, tokens_out, cache_hit to a daily spend table. 5) Alert via tg_dispatcher if projected daily spend > $4.50 by 18:00 PHT.
- **COST:** ~2h dev; saves est. $1.50-$2.50/day at current volume
