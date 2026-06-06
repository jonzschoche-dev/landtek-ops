# `holes/prompts/` — Claude Code session routines

> Some hole-finding routines need genuine LLM judgment, not just SQL + a single
> classifier call. Those are deployed as Claude Code sessions, fired by their
> own systemd timer, with the prompt template living here.

## When to choose CC-session over Python

A routine should be a CC session when:

1. **It needs adaptive exploration** — the right query depends on what early reads reveal.
2. **It needs semantic comparison** — comparing rule intent, theory consistency, evidence sufficiency.
3. **It needs the full tool suite** — Read, Grep, Bash, subagents — not just one Sonnet completion.

A routine should be Python+embedded-LLM when:

1. **The shape is "for each row in table, classify or verify"** — deterministic loops.
2. **High frequency** (every 4-6h) — CC session overhead doesn't amortize.
3. **Cost-sensitive** — Python+TN-call is ~10–30× cheaper per invocation.

## Cost math (Sonnet 4.6, May 2026 rates)

| Mode | Per invocation | At weekly cadence | At daily cadence |
|---|---|---|---|
| Python + 1 Sonnet challenger call | ~$0.005 | ~$0.02/mo | ~$0.15/mo |
| Python + ~25 challenger calls (A2-shape) | ~$0.18 | ~$0.70/mo | ~$5/mo |
| Claude Code session (50K-200K tokens) | $0.20–1.50 | $0.80–6/mo | $6–45/mo |

CC sessions are 10–30× the per-invocation cost. Use them where their judgment beats that ratio.

## Currently authored CC-session routines

- **B2 Expected-Primary-Evidence audit** — weekly. See `b2_expected_evidence.md`.
- **D2 Memory contradiction scanner** — weekly. See `d2_memory_contradiction.md`.

Future candidates (not yet authored — these are intelligence engines from LEO_MASTER_PLAN):
- Case theory + evidence-gap engine (task #9)
- Per-transferee recovery posture (task #10) — 19 transferees × ~$5/run = $95 one-off
- Procedural deadline prediction (task #12)
- Opposing-counsel response prediction (task #13)

## Deployment pattern (systemd recipe)

Each CC-session routine gets its own systemd `.service` + `.timer`. Example for B2:

```ini
# /etc/systemd/system/holes-b2.service
[Unit]
Description=Holes B2 expected-evidence audit (CC session, weekly)
After=network.target

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/bin/bash -c 'claude -p "$(cat /root/landtek/holes/prompts/b2_expected_evidence.md)" \
          --output-format=stream-json \
          --dangerously-skip-permissions \
          >> /var/log/holes-b2.jsonl 2>&1'
TimeoutStartSec=30min
```

```ini
# /etc/systemd/system/holes-b2.timer
[Unit]
Description=Run holes B2 weekly (Sundays 02:00 UTC = 10:00 PHT Monday morning)

[Timer]
OnCalendar=Sun *-*-* 02:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Replace `b2` → `d2` (or future routine) for additional ones.

## Prompt-writing conventions

Every prompt file is **self-contained** — the CC session starts knowing nothing
beyond what the prompt + your repo + your DB tell it. Each prompt should:

1. **State the role** ("You are running unattended as a weekly hole-finder…")
2. **List required reads** (specific files, specific SQL queries)
3. **Define the task precisely** — what to look for, what to ignore
4. **Specify the output** — INSERT rows into `holes_findings` with the right schema
5. **Cap cost** — explicit token budget, "use Haiku for batch work"
6. **Define exit criteria** — when to stop and write the run record to `holes_runs`
7. **Reference CLAUDE.md** for project context (the session will read it automatically via the hook on launch)

## Verifying a CC-session routine

```bash
# Dry-run locally (won't write to DB if you add --dry-run handling in your prompt)
cd /root/landtek
claude -p "$(cat holes/prompts/b2_expected_evidence.md)" \
  --output-format=stream-json \
  | head -200

# Check what landed
psql ... -c "SELECT routine_name, severity, description FROM holes_findings 
             WHERE routine_name='B2_expected_evidence' AND status='open' 
             ORDER BY created_at DESC LIMIT 10;"
```

If the CC session goes off-script, look at `/var/log/holes-b2.jsonl` to see what it did.
