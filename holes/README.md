# `holes/` — Gap-finding routines for Leo

> Routines that surface holes in the system. Each routine is a Python class that
> reads state, identifies a gap, and emits a finding to `holes_findings`. A daily
> Telegram digest consolidates open findings into a single Holes Report; P0 findings
> are pushed immediately.

Authored: 2026-05-20 · Plan: see "Routine catalog" section below.

---

## Architecture

```
holes/
├── base.py                # Routine class + run_cli helper
├── dispatcher.py          # cadence-aware: knows when each routine is due
├── digest.py              # daily 06:00 PHT consolidator (Telegram + markdown)
├── p0_pusher.py           # immediate Telegram push for new P0 findings
├── a1_tn_regression.py    # ⚙ WORKING
├── a2_self_research.py    # ⚙ WORKING — highest leverage
├── b1_matter_readiness.py # ⚙ WORKING — the daily compass
├── a3_hallucination_canary.py  # 🔧 STUB
├── b2_expected_evidence.py     # 🔧 STUB
├── b3_stage_claim_backtest.py  # 🔧 STUB
├── b4_untouched_entities.py    # 🔧 STUB
├── c1_provenance_drift.py      # 🔧 STUB
├── c2_ops_language_leak.py     # 🔧 STUB
├── d1_schema_drift.py          # 🔧 STUB
├── d2_memory_contradiction.py  # 🔧 STUB
├── d3_dead_script.py           # 🔧 STUB
├── e1_capacity_health.py       # 🔧 STUB
└── e2_state_divergence.py      # 🔧 STUB
```

Tables (created by `migrations/apply_deploy_207_holes_schema.py`):
- `holes_findings` — one row per OPEN hole. Idempotent via `finding_id_hash` partial unique index.
- `holes_runs` — one row per routine invocation. Run history.

---

## Install (one-time on VPS)

```bash
cd /root/landtek
git pull
python3 migrations/apply_deploy_207_holes_schema.py
```

Verify:
```bash
python3 -m holes.dispatcher --list
```

You should see 14 routines listed, 3 marked due (the first time you run anything they all run because last_ok is NULL).

---

## Day-to-day usage

```bash
# Run any due routines (this is what the systemd timer calls every 15 min):
python3 -m holes.dispatcher

# Force-run one routine:
python3 -m holes.dispatcher --routine A2

# Or directly:
python3 -m holes.a2_self_research
python3 -m holes.b1_matter_readiness --json

# Push any new P0s to Telegram (called every 5 min):
python3 -m holes.p0_pusher

# Generate today's Holes Report (called daily at 06:00 PHT):
python3 -m holes.digest
python3 -m holes.digest --since 24h    # window
python3 -m holes.digest --no-tg        # stdout only
```

---

## Systemd recipes (add these on the VPS)

`/etc/systemd/system/holes-dispatcher.timer`:
```ini
[Unit]
Description=Run any due holes routines

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Persistent=true

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/holes-dispatcher.service`:
```ini
[Unit]
Description=Holes routine dispatcher

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 -m holes.dispatcher
StandardOutput=append:/var/log/holes-dispatcher.log
StandardError=append:/var/log/holes-dispatcher.log
```

`/etc/systemd/system/holes-p0-pusher.timer`:
```ini
[Unit]
Description=Push P0 holes to Telegram

[Timer]
OnBootSec=3min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/holes-p0-pusher.service`:
```ini
[Unit]
Description=P0 push
[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 -m holes.p0_pusher
StandardOutput=append:/var/log/holes-p0-pusher.log
StandardError=append:/var/log/holes-p0-pusher.log
```

`/etc/systemd/system/holes-digest.timer`:
```ini
[Unit]
Description=Daily Holes Report (06:00 PHT = 22:00 UTC)

[Timer]
OnCalendar=*-*-* 22:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/holes-digest.service`:
```ini
[Unit]
Description=Daily Holes Report
[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 -m holes.digest
StandardOutput=append:/var/log/holes-digest.log
StandardError=append:/var/log/holes-digest.log
```

Enable:
```bash
systemctl daemon-reload
systemctl enable --now holes-dispatcher.timer holes-p0-pusher.timer holes-digest.timer
```

---

## Routine catalog

| Routine | Hole type | Cadence | Severity default | Status |
|---|---|---|---|---|
| **A1 TN regression** | truth_gap | daily | P1 (P0 if regression) | ⚙ working |
| **A2 Self-research audit** | truth_gap | every 6h | P2 | ⚙ working |
| **A3 Hallucination canary** | discipline_drift | every 4h | P0 | 🔧 stub |
| **B1 Matter readiness** | coverage_gap | daily | P2 | ⚙ working |
| **B2 Expected evidence** | evidence_gap | weekly | P2 | 🤖 CC-session (prompt authored) |
| **B3 Stage-claim back-test** | coverage_gap | daily | P2 | 🔧 stub |
| **B4 Untouched entities** | coverage_gap | weekly | P3 | 🔧 stub |
| **C1 Provenance drift** | discipline_drift | every 6h | P1 | 🔧 stub |
| **C2 Ops-language leak** | discipline_drift | every 6h | P0 | 🔧 stub |
| **D1 Schema drift** | schema_drift | weekly | P1 | 🔧 stub |
| **D2 Memory contradiction** | memory_drift | weekly | P2 | 🤖 CC-session (prompt authored) |
| **D3 Dead script** | schema_drift | weekly | P3 | 🔧 stub |
| **E1 Capacity health** | capacity_gap | daily | P2 | 🔧 stub |
| **E2 State divergence** | coordination_gap | session_boundary | P3 | 🔧 stub |

---

## Execution model — Python vs Claude Code session

Routines come in two kinds (see `Routine.kind` in `base.py`):

- **`kind="python"`** — the routine's `find_holes(cur)` runs inline in the Python dispatcher. SQL + embedded Sonnet/Haiku calls via existing wrappers (`truth_negotiator.negotiate()`, `llm_billing.anthropic_call()`). Cheap (~$0.005–$0.20/invocation). Right for deterministic / high-volume routines.
- **`kind="cc_session"`** — the routine is implemented as a Claude Code session prompt in `holes/prompts/<name>.md`, fired by its own systemd timer running `claude -p < prompt_file`. The CC session writes findings directly to `holes_findings` via psql. Pricier (~$0.20–$1.50/invocation) but unlocks adaptive judgment + full tool suite. Right for open-ended legal/architectural reasoning at weekly+ cadences.

The Python dispatcher SKIPS `kind="cc_session"` routines but lists them in `--list` so the registry view is unified. See `holes/prompts/README.md` for the CC-session deployment recipe.

**Decide between them using this rule:** if the work is "for each row, classify or verify," choose Python. If the work needs to derive what to look for from open-ended reasoning, choose CC session.

## Adding a Python routine

1. Create `holes/<id>_<name>.py` modeled on `a2_self_research.py`.
2. Inherit `Routine`, set `name / hole_type / cadence / severity_default / description`. Leave `kind` at default ("python").
3. Implement `find_holes(cur)`. Call `self.emit(severity=, description=, ...)` for each hole.
4. End with `if __name__ == "__main__": run_cli(MyRoutine)`.
5. Add to `REGISTRY` in `dispatcher.py`.
6. Test: `python3 -m holes.<id>_<name> --dry-run` (won't persist).

## Adding a CC-session routine

1. Create the Python stub at `holes/<id>_<name>.py` that sets `kind = "cc_session"` and `cc_prompt_path = "holes/prompts/<id>_<name>.md"`. The `find_holes` method raises — never called.
2. Author the prompt at `holes/prompts/<id>_<name>.md` following the conventions in `holes/prompts/README.md`.
3. Add the Python stub to `REGISTRY` so `--list` shows it.
4. Add a dedicated systemd timer + service that runs `claude -p < holes/prompts/<id>_<name>.md` on the cadence. See template in `holes/prompts/README.md`.

### Idempotency contract

`self.emit()` defaults to hashing `(description, case_file, matter_code, doc_id)` plus routine name.
If your routine re-finds the same hole on a subsequent run, the partial unique index on
`finding_id_hash` (WHERE status='open') prevents duplicates. Override `hash_parts={...}` if
you want stricter or looser collapsing.

When a finding is remediated/dismissed, status changes and a new occurrence of the same
hole can be emitted fresh — by design.

### Severity guidelines

- **P0** — legal output hallucination, client comms blackout, schema-breaking change, regression dropping us below baseline. Pushed to Telegram immediately. Don't use casually.
- **P1** — quality-of-output issue affecting client deliverables; calibration regression; latent bug.
- **P2** — coverage or evidence gap. Standard finding. Most routines emit P2 by default.
- **P3** — drift, dead code, low-severity opportunity. Background hygiene.
- **info** — diagnostic / observability data not requiring action.

---

## How to triage findings

```sql
-- All open findings, severity-sorted
SELECT id, severity, hole_type, routine_name, case_file, description, suggested_fix
  FROM holes_findings
 WHERE status='open'
 ORDER BY array_position(ARRAY['P0','P1','P2','P3','info']::text[], severity), created_at DESC;

-- Mark a finding remediated (manual)
UPDATE holes_findings SET status='remediated', remediated_at=now(),
       remediated_via='manual', remediated_by='jonathan'
 WHERE id = 42;

-- Dismiss with reason (e.g. known false-positive)
UPDATE holes_findings SET status='dismissed', dismissed_at=now(),
       dismissed_reason='B1 thresholds too strict for paracale matters — tune in v2'
 WHERE id = 43;
```

A finding marked `remediated` or `dismissed` will no longer block re-emit of the same hole.
This is intentional: if the underlying condition recurs after you fixed it, you want to know.

---

## Deploy sequence (after this commit)

1. `deploy_207` (this deploy): foundation + 3 working routines + 11 stubs
2. `deploy_208`: implement A3 (hallucination canary) — highest impact stub
3. `deploy_209`: implement C1 + C2 (output discipline pair)
4. `deploy_210`: implement E1 (capacity board)
5. `deploy_211`: implement B2 + B3 (evidence + stage backtests)
6. `deploy_212`: implement B4 + D2 (entities + memory contradictions — LLM-heavy)
7. `deploy_213`: implement D1 + D3 (code/schema integrity)
8. `deploy_214`: implement E2 (state divergence — needs Mac↔VPS sync mechanism)

> Note: deploy_205 and deploy_206 (parallel VPS-Claude work, 2026-05-20)
> shipped the Truth-Negotiator calibration round 1 + round 2. The A1 routine
> here piggybacks on that work — it just wraps `back_test_diagnostic.py` in
> the holes-finding pattern.

Each stub's docstring describes implementation steps. Aim for ~150 lines per routine.

---

## See also

- `LEO_MASTER_PLAN.md` § Phase 1.1 (truth-negotiator), § Phase 3.4 (hyper-vigilance meta-agent)
- `memory/feedback_hyper_vigilance_meta_agent.md` — the design rationale
- `systems_analyzer.py` — predecessor; this package extends and consolidates its pattern
- `comms.py` — the chokepoint every routine uses to send findings to Telegram
- `truth_negotiator.py` — the verification engine routines A1, A2, A3, B3 call
