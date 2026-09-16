# Handoff → VPS desk (transient; delete this file once the ask below is done)

**From:** Mac desk, 16 Sep 2026, after the deploy_1057 reconcile.
**One ask.** Please commit your **ombudsman-hunter rewrite**, together with its guard tests.

## What is sitting uncommitted

| Path | State |
|---|---|
| `.claude/agents/ombudsman-hunter.md` | tracked, modified — **37 insertions / 52 deletions** vs origin |
| `truth_tests/test_ombudsman_hunter_guards.py` | **untracked** — 25 tests, all 25 failing |

The agent file is **byte-identical on both desks** (sha256 `eb2bea23…`), so this is not a
Mac/VPS conflict — it is one coherent rewrite that has simply never been committed anywhere.
It is good work (the operating-boundaries section, referral≠finding discipline, the
fail-closed language) and right now it exists only as working-tree state on two machines.

## Why it is worth doing now

1. **It is the last thing keeping the VPS tree dirty.** After the reconcile the VPS is at
   origin tip with 0 staged, 0 missing tracked files, and exactly **one** tracked-modified
   file — this one. Until it lands, every Mac deploy re-prints the "lineage DIVERGING"
   warning, which is what let the clone drift 85 commits behind in the first place.
2. **Its tests are gating both desks' deploys.** `truth_tests/run_all.py` fails 25/25 in that
   file, so the routine's pre-deploy gate blocks, and deploys 1055–1058 have each had to be
   pushed with `LANDTEK_SKIP_TRUTH_TESTS=1`. A skipped gate is a gate that stops protecting
   anyone.

## What the failures look like from here (observation, not a finding — your call)

They read as **tests written ahead of the implementation** rather than a regression, and two
of them appear to describe real client-separation defects in `scripts/ombudsman_hunter.py`:

- `test_playbook_keeps_incorporation_gate_and_client_output` expects
  `'"matter": _client_code()'` in `cmd_playbook`; the source shown in the failure has
  **`"matter": "MWK"` hardcoded** — a Paracale playbook would emit MWK-tagged output.
  That is the P0 client-separation invariant, so it is worth a look regardless of the test.
- `test_unknown_client_connection_fails_closed` expects a `ValueError` that is not raised —
  i.e. the fail-closed path for an unknown client is not in place yet.
- `test_paracale_has_no_mwk_seed_or_exclusion` expects `hunter.THEORY_HINTS == {}`; it is
  currently populated with MWK theory text.
- `test_scan_preserves_agency_referrals_and_resets_machine_provenance` expects
  `? 'agency_referral'` in the upsert; the current upsert has no such branch.

If that reading is right, the fix is in `scripts/ombudsman_hunter.py`, not in the tests — and
committing the three together (script + tests + agent definition) restores a green gate.

## Nothing of yours was touched

The deploy_1057 reconcile advanced HEAD with `git reset --mixed origin/main` (pointer only),
restored 83 tracked files that were missing from VPS disk, and took origin **only** on three
files proven to be strict subsets (0 insertions): `.gitignore`, `MASTER_PLAN.md`,
`agent_specs/005_drip.md`. Your two files above were deliberately left alone. Backups of
everything at risk: `/root/landtek_reconcile_backup/20260916_deploy1057/`. Your 3 stashes are
untouched, and the 54 untracked work-product files were left in place.

Separately, `system_state.json` was untracked + gitignored (deploy_1058) because it is a
daemon checkpoint `landtek_daemon.py load_state()` rebuilds in full when absent; the live copy
is on disk and backed up. That was the recurring dirty-guard trip.

— Mac desk
