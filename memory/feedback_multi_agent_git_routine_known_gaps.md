---
name: multi-agent-git-routine-known-gaps
description: "Five known gaps in landtek_git_routine.sh (diff-bypass in deploy mode, no shared-canon warning, @{push} fails on branches without upstream, hand-filled handoff template, fragile side detection). Disposition: don't pre-emptively fix; add the fix in the deploy that follows the incident."
metadata:
  type: feedback
---

**Don't pre-emptively close these gaps.** Add the fix in the deploy that follows the first time one bites.

**Why:** Pre-emptive fixes for hypothetical failure modes inflate the routine's surface area without proof the failure is common enough to justify the ceremony. The current routine already prevented the 2026-05-20 442-line divergence on `LEOLANDTEK_DEPLOYMENT_PLAN.md` from recurring. Let the residual gaps prove they're load-bearing before adding more.

**How to apply:** When you spot one of the gaps and feel the urge to "harden the routine," resist unless an incident on record actually traces back to it. When an incident does land, close the matching gap in the same deploy that fixes the immediate damage.

---

## Gap A — `deploy` mode bypasses eyeball-the-diff

The P0 routine rule [[multi-agent-git-routine-p0]] § "During session" mandates:
> Before each commit:
> - `git status` to see what changed
> - `git diff <file>` to eyeball every line of the change

But `scripts/landtek_git_routine.sh deploy` (lines 161-163) runs only:
```
git add "${paths[@]}"
git status --short | head -10
```

No `git diff --staged` is surfaced before the commit. The routine encodes the mechanical safety net (specific paths, pull-rebase, retry on rejection) but silently skips the human-judgment step. A daemon-edited file accidentally passed via the deploy command would commit without review.

**Reactive fix when it bites:** insert `git diff --staged` before the commit step, ideally gated behind a `--review` flag so non-interactive automation (cron, hooks) still works.

---

## Gap B — No shared-canon conflict warning

The P0 rule § "Shared-canon documents" lists files both agents will edit:
- `LEOLANDTEK_DEPLOYMENT_PLAN.md`, `LEO_MASTER_PLAN.md`, `STATUS.md`, `WORKFLOW.md`, `memory/MEMORY.md`, `memory/feedback_*.md`

When `deploy` includes a shared-canon path, the routine should warn — but currently it doesn't. Pre-flight pull-rebase handles the case where the other side already pushed, but not the case where the other side is *about to push* in the next minute. A 120-second auto-sync window plus a slow human reviewing a diff is enough room for a concurrent edit.

**Reactive fix when it bites:** when a shared-canon merge headache actually lands, add a check before the stage step: if any path in `${paths[@]}` matches the shared-canon list, print a warning and re-fetch immediately before committing.

---

## Gap C — `@{push}` silently no-ops on branches without upstream

`scripts/landtek_git_routine.sh end` (line 103) prints unpushed commits via:
```
unpushed=$(git log --oneline @{push}..HEAD 2>/dev/null || true)
```

`@{push}` requires a configured push remote, which is set automatically only when you push with `-u` (or have `push.autoSetupRemote = true`). On a fresh feature branch created without `-u`, the `@{push}` reference is undefined; the `2>/dev/null || true` swallows the error; the "Committed but unpushed" warning silently doesn't fire.

This is fine for `main` (always has upstream). It activates the moment anyone follows the P0 rule § "Branch for big work" and creates `feature/whatever`.

**Reactive fix when it bites:** replace `@{push}..HEAD` with a branch-name-derived form (`origin/$(git rev-parse --abbrev-ref HEAD)..HEAD`) and emit an explicit "no upstream set — push with `git push -u origin <branch>`" warning when even that fails.

---

## Gap D — Handoff template requires hand-fill

`end` mode (lines 122-129) prints a heredoc with `<fill in>` placeholders for `PENDING ON OTHER END` and `NEXT NATURAL MOVE`. Templates that require human completion get skipped under time pressure or in autonomous flows. A skipped handoff is functionally equivalent to no handoff — the other agent starts its next session without the context the template was meant to carry.

**Reactive fix when it bites:** auto-derive both fields. `PENDING ON OTHER END` can be a diff against the previous `end`-run output (requires persisting it). `NEXT NATURAL MOVE` can be the last TODO marker in any modified file, or the latest open entry in `chat_notes` / `tg_inquiry_queue`. Fall back to `<fill in>` only when auto-derivation produces nothing.

---

## Gap E — Side detection via path heuristic is fragile

The script identifies VPS vs Mac by which path exists (`/root/landtek/.git` vs `$HOME/landtek/.git`, lines 18-25). If the Mac ever mounts the VPS repo at `/root/landtek` (sshfs, dev container, Tailscale-mounted share, devbox), the routine identifies the Mac as VPS. Side identification gates handoff messaging — wrong side means wrong context for the operator.

**Reactive fix when it bites:** prefer a more robust signal. Options ranked:
1. `hostname` (matches `landtek-vps` vs `Jonathans-Mac-Studio.local` — no setup, distinguishes any future machine too)
2. `.git/landtek-side` marker file written once at clone time (more explicit but requires a setup step)
3. Tailscale identity if it ever becomes load-bearing elsewhere

---

## Origin

Jonathan, 2026-05-20: *"The routine is a substantial improvement over ad-hoc git discipline and directly addresses the documented 2026-05-20 failure modes. The two real gaps are (a) eyeball-the-diff getting bypassed in the deploy path and (b) no proactive shared-canon conflict detection. Both are additive fixes that don't require rewriting what's there — worth adding in a follow-up deploy when one of the gaps actually bites."*

Jonathan, 2026-05-20 (architectural-review follow-up): expanded to five gaps with the same wait-for-incident disposition. Added gaps C (`@{push}` upstream-tracking dependency), D (hand-filled handoff template), and E (path-based side detection). All three have a sketched reactive fix so when the gap does bite, the fix is already designed.

---

## Related rules
- [[multi-agent-git-routine-p0]] — the routine these gaps live in
