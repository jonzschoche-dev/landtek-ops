---
name: multi-agent-git-routine-p0
description: "P0 — Session start + session end git routine for any Claude session touching the landtek-ops repo. Closes the multi-agent coordination loop (VPS Claude + Mac Claude + Cowork desktop app) without races, conflicts, or silently-lost work."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**P0 — Every Claude session on the `landtek-ops` repo follows this exact routine.**

There are at least three agents that may push to `landtek-ops`:
- **VPS Claude** — runs on the LandTek VPS, edits in `/root/landtek`
- **Mac Claude** — runs in the Anthropic desktop app's SSH workspace, edits in `~/landtek` on Jonathan's Mac
- **Cowork / desktop chat sessions** — may also commit through the Mac clone

If any session pushes without first pulling, the other sides race or get rejected on push, and the human (Jonathan) ends up resolving conflicts manually. This routine prevents that.

---

## SESSION START RITUAL

Within the first 2-3 tool calls of any session that may edit files in this repo:

```bash
cd /root/landtek                      # or ~/landtek on Mac
git fetch origin main
git status                            # any pre-existing dirty state?
git log --oneline HEAD..origin/main   # what did the other agents push?
git pull --rebase                     # catch up cleanly
```

**If `git status` shows uncommitted changes from a previous session**, decide before pulling:
- If they're real work that should ship → stage + commit them FIRST with a backfill deploy_NNN tag, THEN pull
- If they're daemon-written churn (`system_state.json`, `drafts/daily_digest_*.md`) → `git checkout --` to discard, THEN pull
- If unclear → ask Jonathan; never blindly discard

**If pull surfaces files the other agent wrote**, read the new files into context before editing anything else. The other agent likely wrote them for a reason that affects your current task.

---

## DURING SESSION

- Edit files in the repo path. Never on the VPS outside `/root/landtek`.
- Before each commit:
  - `git status` to see what changed
  - `git diff <file>` to eyeball every line of the change
  - Stage SPECIFIC paths: `git add path/a path/b path/c`. NEVER `git add .` or `git add -A` — daemon-written files (system_state.json, snapshots) sneak in.
- Commit message format: `deploy_NNN: short title — one-paragraph why`
- After commit: `git push origin main`. If rejected:
  ```bash
  git pull --rebase             # rebase your commit on top of theirs
  git push                       # fast-forward now
  ```
- NEVER `git push --force` to main. Ever. It overwrites the other agent's work + breaks the auto-sync daemon's safety check.

---

## SESSION END RITUAL

Before saying "done for now":

```bash
git status                            # anything uncommitted?
git log --oneline @{push}..HEAD       # anything committed but unpushed?
```

Surface to operator:
- Uncommitted work → "I left N files modified in {paths} — commit before close?"
- Unpushed commits → "I committed deploy_NNN but didn't push. Push now?"
- Untracked files that look like real work → "These look committable: {paths}. Stage + commit?"

Never silently exit a session with unpushed work — the other agent will be operating on stale state by morning.

---

## SHARED-CANON DOCUMENTS (expect both agents to edit)

These files are explicitly shared canon; both agents will edit them; merge conflicts are expected and resolvable:

- `LEOLANDTEK_DEPLOYMENT_PLAN.md` — the single source of truth strategy doc
- `LEO_MASTER_PLAN.md` — internal strategy + principles
- `STATUS.md` — live operations compass
- `WORKFLOW.md` — multi-agent coordination doc
- `memory/MEMORY.md` — memory file index
- `memory/feedback_*.md` — feedback rules

Merge resolution principle: **additive wins.** If both agents added text, keep both. If they conflict on the same line, raise the conflict to Jonathan with a side-by-side diff — don't silently pick.

Backup file pattern: `<file>.mac-backup-YYYY-MM-DD` or `<file>.vps-backup-YYYY-MM-DD` — these are pre-merge snapshots, NOT to be committed (add pattern to `.gitignore` if needed).

---

## DAEMON-WRITTEN CHURN — never commit

These are runtime-state artifacts that change constantly; they belong in `.gitignore`:

- `system_state.json` — daemon writes
- `drafts/daily_digest_*.md` — auto-generated artifacts
- `*.log`, `*.tmp`
- `__pycache__/`, `*.pyc`
- `.venv/`, `venv/`
- snapshots from one-shot scripts

The `.gitignore` already covers most; if a new daemon starts writing somewhere unexpected, add it BEFORE committing anything else.

---

## CROSS-AGENT HANDOFF MESSAGE TEMPLATE

When ending a session that touched shared state:

```
Session summary (handoff to other agent):
  PUSHED: deploy_NNN (commit hash) — <one-line summary>
  PENDING ON YOUR END: <files / open inquiries / things needing the other side>
  KNOWN GOTCHAS: <anything weird the other agent might trip on>
  NEXT NATURAL MOVE: <what would unstick this>
```

This goes in the operator's chat OR as a `chat_notes` row, so the other agent reads it on session start.

---

## WHY THIS RULE EXISTS

2026-05-20 incidents in the multi-agent ramp-up:
- Mac Claude built `WORKFLOW.md` + `LEO_MASTER_PLAN.md` + `scripts/mac_sync.sh` locally but didn't push immediately. VPS Claude added a "Git push protocol" section to CLAUDE.md without knowing those files existed.
- VPS Claude pushed 15 commits while Mac Claude was offline; on next Mac launch the auto-sync had to pull 15 cuts in one shot.
- A 442-line diff accumulated on `LEOLANDTEK_DEPLOYMENT_PLAN.md` because both sides edited the same document without a pull-rebase in between.

None of these resulted in data loss (thanks to git), but each cost minutes-to-tens-of-minutes reconciling. At higher cadence — when more than two agents are pushing throughout the day — this becomes the dominant failure mode. The routine above prevents it mechanically.

---

## Related rules
- `[[feedback_client_comms_hardcoded]]` — same "load-bearing infrastructure" posture
- `[[feedback_synthesis_must_cross_source]]` — analogous principle: never anchor on a single source when the truth is distributed
- `[[feedback_no_premature_reports]]` — output discipline that depends on this coordination working
