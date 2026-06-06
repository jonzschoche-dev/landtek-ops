"""holes.d3_dead_script — STUB.

Weekly: find *.py files in /root/landtek/ that aren't referenced by any
systemd timer, cron entry, slash command, deploy script, OR another Python file.
These are either dead code (delete candidates) or undocumented entry points
(need to be documented).

TODO:
  1. Enumerate *.py files (excluding migrations/, .git/, __pycache__/, tests/)
  2. Build the set of files referenced by:
     - systemctl list-unit-files → ExecStart paths
     - crontab -l (if any)
     - /etc/cowork-bridge/inbox/*.sh references
     - import statements in other .py files
     - landtek_git_routine.sh and other shell scripts
  3. Unreferenced → P3 finding with suggested_fix='Confirm dead → delete, or document entry point'
  4. Idempotent: hash by file path
"""
from holes.base import Routine, run_cli


class D3_DeadScript(Routine):
    name = "D3_dead_script"
    version = "v0-stub"
    hole_type = "schema_drift"
    cadence = "weekly"
    severity_default = "P3"
    description = "Finds .py files no one calls. Either dead code or undocumented entry points."

    def find_holes(self, cur):
        raise NotImplementedError(
            "D3_dead_script not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(D3_DeadScript)
