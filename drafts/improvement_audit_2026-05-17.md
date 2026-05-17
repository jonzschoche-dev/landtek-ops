# Landtek Improvement Audit — 2026-05-17
_Generated 05:18 UTC · improvement_agent.py_

## Trajectory snapshot

- **Trajectory score:** None / 100
- **Commentary:** (--no-llm — synthesis skipped)

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
| `client_history_events` | 914 |

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
