"""holes.e2_state_divergence — STUB.

Called at session start/end (not by the dispatcher's cadence — cadence='session_boundary').
Compares VPS clone vs Mac clone for uncommitted/untracked divergence and stale
session state. Extends `scripts/landtek_git_routine.sh end` mode.

TODO:
  1. On VPS: git status --short → list of (mode, path) pairs
  2. On Mac (via a sync record table or git push timestamp): get last-known dirty state
  3. Diff: any file dirty on one side but not the other for >1h → P2 finding
     "Mac side has uncommitted X for 4h; either commit or surface to Jonathan"
  4. Untracked files matching real-work patterns (.py, .sql, .md not in drafts/) → P3
  5. Idempotent: hash by (path, side)

This depends on a sync mechanism between VPS and Mac to know each other's state.
Options: (a) Mac periodically writes its `git status` output to a shared file in the
repo (timestamped, ignored from commits); (b) VPS pulls Mac's state via a dedicated
endpoint. (a) is simpler.
"""
from holes.base import Routine, run_cli


class E2_StateDivergence(Routine):
    name = "E2_state_divergence"
    version = "v0-stub"
    hole_type = "coordination_gap"
    cadence = "session_boundary"
    severity_default = "P3"
    description = "VPS vs Mac uncommitted/untracked divergence. Extends git routine."

    def find_holes(self, cur):
        raise NotImplementedError(
            "E2_state_divergence not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(E2_StateDivergence)
