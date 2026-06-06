"""holes.d2_memory_contradiction — CC-SESSION routine.

This routine is implemented as a Claude Code session, not Python. The class below
exists only so the dispatcher --list shows it in the unified registry.

Actual implementation: holes/prompts/d2_memory_contradiction.md
Fired by: systemd timer running `claude -p < holes/prompts/d2_memory_contradiction.md`
See: holes/prompts/README.md for the deployment pattern.

WHY CC-SESSION: 50+ feedback_*.md files. Finding contradictions requires SEMANTIC
comparison of rule intent, not keyword overlap. CC session can read each file in
full, reason about pairs, propose resolutions — exactly its judgment sweet spot.
"""
from holes.base import Routine


class D2_MemoryContradiction(Routine):
    name = "D2_memory_contradiction"
    version = "v0-cc-session"
    hole_type = "memory_drift"
    cadence = "weekly"
    kind = "cc_session"
    cc_prompt_path = "holes/prompts/d2_memory_contradiction.md"
    severity_default = "P2"
    description = ("Weekly Sonnet pass over feedback_*.md finds contradictions and stale rules. "
                   "Implemented as a CC session (see holes/prompts/d2_memory_contradiction.md).")

    def find_holes(self, cur):
        raise RuntimeError(
            "D2_memory_contradiction is a CC-session routine; invoke via "
            "`claude -p < holes/prompts/d2_memory_contradiction.md` instead."
        )
