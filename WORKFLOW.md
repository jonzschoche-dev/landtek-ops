# LANDTEK — Multi-Agent Workflow

> How the VPS Claude Code session and the Cowork (Mac clone) session collaborate
> on the same codebase without breaking production.
>
> Last updated: 2026-05-20

---

## Why this exists

LandTek runs on a live VPS (`/root/landtek/`) with Postgres, Gemini OCR, the Leo n8n
workflow, Telegram comms, and several systemd services. A change pushed carelessly
caused the **2026-05-17 comms blackout** — Don Qi + Jonathan inbound silently dropped
for 48 hours. We can't let that happen again.

This document codifies the rules so two (or more) Claude agents can work in parallel
without re-creating that failure mode.

---

## The topology

```
+--------------------------------------+              +--------------------------------------+
|  VPS Claude Code (Termius / SSH)     |              |  Cowork (Mac, Claude desktop chat)   |
|  Works in:  /root/landtek/           |              |  Works in:  ~/landtek/  (clone)      |
|  Has:       live DB, Gemini keys,    |              |  Has:       file edit, sandbox bash, |
|             systemd, leo, Telegram   |              |             web/Chrome MCP, etc.     |
+--------------------+-----------------+              +-----------------+--------------------+
                     |                                                  |
                     |          shared state: GitHub                    |
                     |        (landtek-ops + leolandtek-deploys)        |
                     +--------------------------------------------------+
```

The two agents are on **different machines, different filesystems**. They only
collide through git. That collision surface is what this document manages.

---

## Role split (default)

| Agent | Owns | Examples |
|---|---|---|
| **VPS Claude** (Termius) | Runtime + ops | Run sweep, query Postgres, restart services, send Telegram, apply migrations, write memory during work |
| **Cowork** (Mac chat) | Codebase + design | Edit scripts, refactor, draft documents, plan, review diffs, write new tools, prepare deploy scripts |

**Crossover is allowed** — Cowork can prepare a deploy script and VPS Claude can read
a Python file. But default to the split above when work could be done from either side.

---

## Mac auto-sync (one-way: GitHub → Mac)

The Mac clone at `~/landtek` is kept in sync automatically by a launchd job that
polls origin every 2 minutes and pulls when there's something new — but only when
the working tree is clean and the pull is a clean fast-forward. **It never auto-merges
or auto-commits.** Local edits are safe.

Files:
- `scripts/mac_sync.sh` — the pull script (in this repo)
- `~/Library/LaunchAgents/com.landtek.sync.plist` — the schedule
- `~/Library/Logs/landtek_sync.log` — what happened on each poll

**Install (one-time, run on Mac Terminal):**
```bash
chmod +x ~/landtek/scripts/mac_sync.sh
launchctl load -w ~/Library/LaunchAgents/com.landtek.sync.plist
```

**Force a sync right now (skip the 2-min wait):**
```bash
bash ~/landtek/scripts/mac_sync.sh && tail -5 ~/Library/Logs/landtek_sync.log
```

**Check what's happened:**
```bash
tail -50 ~/Library/Logs/landtek_sync.log
```

**Stop / re-enable:**
```bash
launchctl unload ~/Library/LaunchAgents/com.landtek.sync.plist   # stop
launchctl load -w ~/Library/LaunchAgents/com.landtek.sync.plist  # start
```

## VPS-side sync

VPS-side pull is still manual right now — when you start a Termius session, run
`cd /root/landtek && git pull` to catch anything Cowork pushed. (We can wire the
same launchd-style auto-pull into a systemd timer on the VPS as a follow-up.)

## Session-start checklist

### When you fire up the VPS Claude session

```bash
cd /root/landtek
git pull          # catch anything Cowork pushed
# proceed with work
```

### When you fire up a Cowork session (in chat)

The Mac auto-sync should already have you up to date. If you want to be sure,
tell Cowork **"pull landtek first"** — it'll run the sync script and confirm.

---

## Git discipline

1. **Pull before editing.** Always. Even if you think nothing changed.
2. **Commit small.** One logical change per commit. Easier to revert.
3. **Push fast.** Don't sit on uncommitted changes — that's where conflicts incubate.
4. **Pull-rebase if rejected.** If `git push` fails with non-fast-forward, run
   `git pull --rebase`, resolve any conflicts, retry the push.
5. **Branch for big work.** If a change spans 10+ files or might break things,
   `git checkout -b feature/whatever` and merge to main only when done.

---

## Memory tree (`/root/landtek/memory/`)

The memory tree was symlinked into the repo on 2026-05-20. Both agents can now see it.

**Default ownership: VPS Claude.** It updates memory naturally during operational work
(captures decisions, lessons, feedback).

**Cowork only edits memory when:**
- Deliberately reorganizing (e.g., consolidating duplicate rules)
- Adding a meta-level rule (e.g., this WORKFLOW.md)
- Explicitly asked by Jonathan

This prevents double-writes on the same feedback file.

---

## Innovation discipline (clone-first, prod-last)

```
1. Idea / problem
2. Cowork proposes change in ~/landtek/   ← you review diff
3. Cowork commits + pushes to landtek-ops
4. VPS Claude pulls + activates if needed
5. Watch logs / heartbeat for impact
6. If broken: git revert + push + VPS pulls revert
```

**No more "edit on the VPS at 3am and pray."** Edits flow through git so they're
reviewable, revertable, and auditable.

---

## What counts as "ready to deploy"

Before pushing a change that touches production, the change should have:

| Check | When required |
|---|---|
| **Diff reviewed by Jonathan** | Always |
| **No secrets in the diff** | Always (use git secret-scanner pre-commit hook if added) |
| **Schema migration written** | If schema changes |
| **Snapshot taken** | Before any Leo n8n workflow change (already standard) |
| **Comms chokepoint respected** | If touching outbound messaging (use `comms.comms_send()`) |
| **Critical-path test run** | If touching: comms, sweep, orchestrator, or audit gates |
| **Deploy script prepared** | If activation requires a one-time command (migration, service restart, n8n import) |

If any of these are missing and the change is risky, **don't push to main**. Branch it.

---

## The deploy pipeline (activation)

For changes that need explicit activation on the VPS:

1. Cowork writes a deploy script: `deploy_NNN_short_name.sh` in `~/landtek/`
2. Reviews + commits + pushes to `landtek-ops`
3. Pushes a copy to `leolandtek-deploys.git/inbox/NNN_short_name.sh`
4. `cowork-bridge` daemon (polling every 30s) picks it up, runs it, writes to `outbox/`
5. VPS Claude (or Jonathan) reads `outbox/` to verify success

For passive changes (a new Python module that sweep will pick up next cycle):
just push to `landtek-ops`. No deploy script needed.

---

## Conflict resolution (when both agents edit the same file)

1. The agent whose push is rejected runs `git pull --rebase`.
2. Git marks the conflict. Open the file, find the `<<<<<<<` markers.
3. Decide which version wins (or merge both):
   - **VPS Claude work**: usually wins for memory notes about ops events
   - **Cowork work**: usually wins for code refactors, design docs
   - **Both**: merge by hand if the changes are complementary
4. `git add <file>` once resolved.
5. `git rebase --continue`, then `git push`.

If unsure, ask Jonathan. Conflicts are a signal to pause and coordinate, not just
auto-resolve.

---

## Anti-patterns (don't do these)

- ❌ **Editing `/root/landtek/` files directly on the VPS without committing.** Bypasses git, loses the audit trail, makes the next pull a conflict.
- ❌ **Force-pushing to main** (`git push --force`). Rewrites history, can drop other agent's work.
- ❌ **Pushing without pulling first.** Will fail at push time, but also means you didn't see what the other agent did before editing.
- ❌ **Deploying directly with `bash my_script.sh` on the VPS without going through `leolandtek-deploys/inbox/`.** Bypasses the audit-logged deploy pipeline.
- ❌ **Memory edits from Cowork during a VPS Claude session.** Wait until VPS Claude is idle, or coordinate explicitly.

---

## Emergency: rollback

If a deploy breaks production:

1. **Identify the bad commit:** `git log --oneline -10`
2. **Revert it:** `git revert <bad-sha>` (creates a new commit that undoes the change)
3. **Push the revert:** `git push`
4. **VPS Claude pulls** the revert.
5. **If activation is needed for the revert,** write a deploy script for it.

If the system is mid-failure and a revert isn't fast enough:
- Stop the affected service: `systemctl stop <unit>`
- Restore from the last known-good snapshot in `~/landtek/snapshots/`
- Then do the git revert in parallel

---

## Operational health invariants

These should always be true. If they're not, stop innovating and fix:

- `systemctl status sweep-loop.service` is **active**
- `systemctl status comms-health-sentinel.timer` is **active**
- `systemctl status cowork-bridge` is **active**
- `tail -1 /root/landtek/notifications/pending.txt` heartbeat is **< 1 hour old**
- `systemctl status n8n` is **active** (Leo's runtime)
- Telegram bot @LeoLandTekBot responds to a test ping

If any of these break, that's the priority — innovation waits.

---

## When to update this document

- A new failure mode (like the 5-17 blackout) teaches us something
- A new agent or surface joins the workflow (e.g., a browser-based Leo)
- A discipline rule above proves wrong or unnecessary

Both agents have edit rights on this file. Update via the same git discipline.
