---
name: multi-agent-git-routine-known-gaps
description: "Two known gaps in landtek_git_routine.sh (eyeball-the-diff bypassed in deploy mode + no shared-canon conflict warning). Disposition: don't pre-emptively fix; add the fix in the deploy that follows the incident."
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

## Origin

Jonathan, 2026-05-20: *"The routine is a substantial improvement over ad-hoc git discipline and directly addresses the documented 2026-05-20 failure modes. The two real gaps are (a) eyeball-the-diff getting bypassed in the deploy path and (b) no proactive shared-canon conflict detection. Both are additive fixes that don't require rewriting what's there — worth adding in a follow-up deploy when one of the gaps actually bites."*

---

## Related rules
- [[multi-agent-git-routine-p0]] — the routine these gaps live in
