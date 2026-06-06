# Holes routine D2 — Memory contradiction scanner (CC session)

You are running unattended on the LandTek VPS as a weekly hole-finding routine. Your job
is to scan the 50+ `feedback_*.md` rule files in `memory/`, find rules that contradict
each other or reference deprecated systems, and write findings to `holes_findings`.

This is Phase 1.4 of `LEO_MASTER_PLAN.md` (memory tree consolidation: 50+ → ~25 canonical).

## What you have access to

- `/root/landtek/memory/feedback_*.md` — the rule files. Skip `*.deprecated-*`.
- `/root/landtek/memory/MEMORY.md` — the index.
- Postgres for writing findings (DSN in env).
- `comms_send()` exists but DO NOT use — silent run.

## Your task

### Step 1 — enumerate

List `/root/landtek/memory/feedback_*.md` excluding `*.deprecated-*`. Read each file's
frontmatter (the YAML header with `name:`, `description:`, `originSessionId`) plus the
first 100 lines of body.

### Step 2 — index by topic

Cheap pre-pass with Haiku: for each rule file, extract 3-5 topic keywords. Build a
mapping `topic → [file_paths]`. This is your candidate-pair list for the deeper compare.

### Step 3 — pairwise compare (the judgment-heavy part)

For each pair of rule files sharing 2+ topic keywords, do a Sonnet judgment call:

> "Read rule A and rule B. Do they contradict each other? If yes:
>  (a) name the specific point of contradiction in 1 sentence;
>  (b) propose which rule should win and why (the more recent/specific/load-bearing one);
>  (c) classify severity: P1 if contradiction affects active client work, P2 if architectural, P3 if cosmetic.
>  If they don't contradict, return null."

Skip pairs where one is clearly a superset (e.g., a project file referencing a feedback file). Focus on rules that purport to apply to the same situation but say different things.

### Step 4 — scan for deprecated references

Separate pass: regex-grep each file for references to deprecated names:
- `AGENDA.md` (replaced by `DIRECTIVE.md`)
- `legacy_bot` / `tg_bot_legacy` (decommissioned per `feedback_legacy_bot_decommission.md`)
- old extraction contracts (anything pre-`tct_v3_canonical`)
- Any file you find marked `.deprecated-*` referenced from a non-deprecated file

These get emitted as `memory_drift` findings at severity P3.

### Step 5 — emit findings

For each contradiction found:

```sql
INSERT INTO holes_findings (
    routine_name, routine_version, finding_id_hash,
    severity, hole_type, description, suggested_fix, metadata
) VALUES (
    'D2_memory_contradiction', 'v1',
    %s,  -- sha256("D2" + sorted_paths_joined)[:24]
    %s,  -- P1 | P2 | P3
    'memory_drift',
    %s,  -- "Rules X and Y contradict on Z. Sonnet says X wins because..."
    %s,  -- "Edit rule Y to add an exception, OR retire it, OR clarify scope"
    %s::jsonb  -- {"rule_a": path, "rule_b": path, "topic": "...", "winner_proposal": "..."}
);
```

For each deprecated-reference found:

```sql
INSERT INTO holes_findings (...) VALUES (
    'D2_memory_contradiction', 'v1', %s, 'P3', 'memory_drift',
    'Rule X still references deprecated NAME', 
    'Edit X to remove or update the reference',
    %s::jsonb -- {"file": path, "deprecated_token": "..."}
);
```

## Idempotency

`finding_id_hash` = sha256("D2_memory_contradiction" + sorted([rule_a, rule_b]).join("|"))[:24]
so re-running won't duplicate the same pair-contradiction.

## Cost discipline

- Haiku for the topic-keyword extraction pass (cheap; 50 files × ~$0.002 = $0.10).
- Sonnet ONLY for the pairwise contradiction-judgment. Cap at 25 pairs per run; if more
  candidates exist, prioritize by topic-keyword overlap depth and process top 25.
- Total cost target per run: <$2. Hard cap: $5 (write `status='degraded'` to holes_runs if hit).

## Exit + run logging

```sql
INSERT INTO holes_runs (
    routine_name, routine_version, status, duration_ms,
    findings_count, p0_count, metadata
) VALUES (
    'D2_memory_contradiction', 'v1',
    'ok',  -- or 'degraded' if cost-capped
    %s, %s, 0,
    %s::jsonb  -- {"files_scanned": N, "pairs_judged": M, "contradictions": K, "deprecated_refs": L}
);
```

## Common pitfalls to avoid

- **DON'T flag minor wording differences as contradictions** — the threshold is "applying both rules to the same situation produces different actions."
- **DON'T emit a finding for every rule pair that's even slightly related** — be selective. Phase 1.4 says target is ~25 canonical files; we want surgical finds, not noise.
- **DON'T edit the rule files** — your job is to FLAG, not fix. Jonathan/the next session resolves.
- **DON'T re-judge pairs already-open in holes_findings** — query first.
- **DON'T touch any non-memory files** — strict scope is `memory/feedback_*.md`.

## Start

Begin by reading `/root/landtek/CLAUDE.md` and `/root/landtek/memory/MEMORY.md`, then enumerate the feedback files.
