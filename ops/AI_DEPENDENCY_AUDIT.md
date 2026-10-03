# AI Dependency Audit — LandTek stack
Stack Inspector · 27 Sep 2026 ~22:30 PHT · read-only (nothing changed on Mac or VPS)
Scope: every runtime entry point on the VPS (`/root/landtek` @ b9d6f79, 55 systemd timers, 8 always-on services, 7 cron lines), the Mac launchd jobs, and the on-demand roster in `scripts/agents.py`.
Method: follow Python imports from each entry script down to a file that calls a model provider (Ollama, Gemini, Anthropic, OpenAI); false hits hand-checked; 7-day call volume from `inference_audit`, `llm_calls`, `reocr_log`.
Verdicts: **KEEP AI** (code can't do it) · **CODE** (a rule/query/template replaces it) · **CUT** (not needed) · **MERGE** (keep the job, one runner only).

## 1. Headline
- **13 of 70 VPS runtime jobs reach a model** (plus 2 on the Mac). The other 57, including every digest, deadline, calendar, filing-monitor, supervisor and coordinator job, are already plain code.
- Nearly all real AI use is two jobs the product genuinely needs: **reading scans (OCR)** and **Leo's free-text replies**. Fact extraction and embeddings are the rest.
- The waste is **duplication, not dependence**: 6 separate OCR runners, 2 embedding paths, 2 Telegram reply brains.
- **Observed volume is tiny**: last 7 days `inference_audit` = 2 calls (verify), `reocr_log` = 1, `llm_calls` = 44 Claude Sonnet calls (purposes `challenger` 40, `strategic_audit` 4 — from `holes/` scripts run by hand, not from any timer). **Leo's Ollama calls are not logged anywhere I could find, so Leo volume is UNKNOWN.**
- False alarms cleared: `gmail_watcher.py` and `correspondence_spine.py` only mention "anthropic/openai" as sender-filter regexes. So email-briefer, correspondence-matcher, email-bridge, email-attachments, gmail-backup-sweep, reenrich, and corpus-steward's `find_missing_record` are **no-AI**. `worker/cowork_bridge.py` imports model names from `worker/config.py` but only runs shell commands — no-AI.

## 2. Runtime jobs that call a model
| # | Job (VPS unless noted) | Cadence | Model | What the model does | Verdict | Replacement / note |
|---|---|---|---|---|---|---|
| 1 | `landtek-leo-service.timer` → `leo_service.py --once` | 5 min | Ollama qwen2.5 14B (Mac) | Writes Leo's reply to client messages | **KEEP AI (narrow)** | Status, deadline, title and document lookups become query + template (deploy_1092 identifier gate already does this for e-titles). Model only phrases free-text answers. |
| 2 | `landtek-leo-instant.service` → `leo_instant.py` → `comm_agent_max` → `leo_service` | always on | same | Same engine, instant path | **MERGE** with #1 | One Leo runner. |
| 3 | `landtek-comm-agent-soak.timer` → `comm_agent_soak.py --tick` | 15 min | same (via Leo) | Soak-tests the comm agent | **CUT** once the soak verdict is recorded | A test harness running in production every 15 min. Whether the soak is finished is UNKNOWN. |
| 4 | `landtek-tg-router.service` → `handlers/llm.py` | always on | Ollama (Anthropic path present) | Free-text fallback reply on Telegram | **MERGE** into Leo | A second reply brain; route free text to Leo only. |
| 5 | `landtek-verify-worker.timer` → `verify_worker.py --limit 10` | 15 min | Ollama, then Gemini fallback | Reads document text, proposes cited facts | **KEEP AI** (prose reading) + **CODE** first pass | Dates, TCT/e-title numbers, amounts, docket numbers, party names by regex/parsers before any model call. 2 calls in 7 days, so mostly idle. |
| 6 | `landtek-reocr-sweep.timer` → `reocr_gemini.py` | 1 h, ≤80 calls | Gemini vision | Re-OCRs bad scans | **MERGE** | Six OCR runners (#6–#11) share one job. Proposal: one OCR queue, Tesseract first (already exists as `ocr_triage`), local vision model second, Gemini only on failure. `reocr_log`: 1 run in 7 days. |
| 7 | `landtek-reocr-local-sweep.timer` → `reocr_local.py` | 20 min | Ollama vision | Same job, token-free twin | **MERGE** (becomes the tier-2 of the one queue) | |
| 8 | `landtek-subdiv-reocr.timer` → `subdivision_reocr_retry.py` | 4 h | Gemini | Retries subdivision-plan OCR | **MERGE** | |
| 9 | `landtek-geometry-drip.timer` → `geometry_pipeline.py` | 3 h | Gemini/Ollama via reocr | Cleans survey pages before plotting | **MERGE** (OCR step) · **KEEP CODE** (geometry) | |
| 10 | `landtek-daemon.service` → `step_a_ocr` | always on | Gemini (fallback) | OCR on ingest | **MERGE** | |
| 11 | `landtek-corpus-backfill.service` | always on | Gemini OCR + `gemini-embedding-001` into Qdrant | OCR + embeddings | **MERGE** (OCR into queue; embedding see #13) | |
| 12 | `landtek-inference-sentinel.timer` | 6 h | probes Mac Ollama | Health check of the model host | **CODE** | Plain HTTP health check; not a model use. |
| 13 | Mac `com.landtek.embed` → `embed_sweep.sh` | at load | local embed model | Embeddings for search | **KEEP AI** (embeddings) · **MERGE** with #11 | Two embedding paths (Gemini on VPS, local on Mac) = two vector sets. Pick one. |
| 14 | `landtek-jurisprudence-steward.timer` → `ingest_jurisprudence` → `legal_authority` | weekly | Ollama nomic-embed | Embeds fetched case law | **KEEP AI** (embedding only) | Gap scan and harvest are already code. |
| 15 | Mac `com.landtek.ollama-host` | always on | — | Serves the local model | **KEEP** (infra) | Shrinks as #1–#11 shrink. |

## 3. Digests and clocks — already no AI
`autonomous/daily_digest.py`, `scripts/case_forward_digest.py`, `assistant_cadence.py` (morning/evening, with and without email), `calendar_briefer`, `email_briefer`, `deadline_extractor`, `deadlines.py`, `date_proposer`, `calendar_orchestrator`, `filing_monitor`, `platform_coordinator`, `supervisor`, `refresh_all` (hot/warm/daily). **No model calls.** Their problem is overlap (four 07:00 PHT outputs; see cut proposal B), not AI.

## 4. On-demand tools in `scripts/agents.py` that use a model
| Tool | Fuel | What the model does | Verdict | Note |
|---|---|---|---|---|
| `brief_drafter` | local | Drafts work product from verified facts | **KEEP AI** | Prose. |
| `case_synthesizer` | local (+frontier opt.) | Element-by-element legal synthesis | **KEEP AI** | Prose; coverage gate is already code. |
| `legal_agent` | local | Draft, self-critique loop behind case_memo | **KEEP AI** | |
| `case_memo` | local | Derived-reasoning block in the memo | **KEEP AI** (block only) | Scaffolding already code. |
| `analyst` | local | Case theory / strategy | **CUT** (candidate) | Duplicates matter bots and the Claude strategist desk; strategy lives with the matter owner. |
| `relevance_triage` | local | Keep/drop call per document | **CODE** | Deterministic `relevance` (docket + title + party fingerprint) already exists; roster note says the LLM version over-drops. |
| `proof --llm` | det+local | Optional editorial pass | **CUT** the `--llm` flag | Deterministic lint already covers form defects. |
| `matter_fix` | local | Readiness fix, then memo | **CODE** except its memo step | |
| `legal_authority` | local | Embedding retrieval of statutes | **KEEP AI** (embedding) | |
| `leo` row | api | "n8n AI-Agent, needs-wiring" | **RELABEL** | Stale; Leo is `leo_service.py` now. |
| `build_digest` row | det | points at retired `landtek-digest.timer` | **RELABEL** | Timer disabled on VPS. |

## 5. Model-calling files not on any schedule
112 Python files reference a model provider. Of those, the 13 runtime paths above plus the on-demand tools are live. The remainder are mostly root-level and `worker/` legacy (e.g. `opus_advisor.py`, `haiku_matter_tagger.py`, `verify_t4497_via_gpt4o.py`, `truth_negotiator.py`, `worker/llm.py`, `worker/backtest.py`) and `holes/` probes. **Verdict: CUT candidates, pending a reference check per file** (not done here; no file-by-file claim made). `holes/` produced the only Claude API spend in the last 7 days (44 calls).

## 6. What the restructure needs from this
1. **One model gateway.** Every call goes through `model_router.py` and logs to `inference_audit`. Today Leo's calls bypass logging, so real volume can't be measured. (CODE)
2. **One OCR queue**, Tesseract first. Replaces 6 runners. (MERGE)
3. **One embedding path.** (MERGE)
4. **One Leo.** Lookups by query + template; model only for free-text phrasing. (CODE + KEEP AI narrow)
5. **Cut** the comm-agent soak timer once its verdict is recorded, `analyst`, `proof --llm`, and the unscheduled legacy callers after reference checks.
Net effect: model use shrinks to OCR fallback, fact reading, embeddings, and prose drafting. Everything the bots do for clocks, checklists, directive/reply matching and contradiction checks is already code or should be.

## Limits
- Import tracing does not follow `subprocess` calls; shell wrappers traced one level (`case_corpus_sweep.sh`).
- VPS tree is 5 commits behind origin with 6 hand-edited files; the audit reflects what is actually running.
- Leo call volume: UNKNOWN (not logged). Comm-agent soak status: UNKNOWN.
