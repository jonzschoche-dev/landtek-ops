"""holes.b2_expected_evidence — CC-SESSION routine.

This routine is implemented as a Claude Code session, not Python. The class below
exists only so the dispatcher --list shows it in the unified registry.

Actual implementation: holes/prompts/b2_expected_evidence.md
Fired by: systemd timer running `claude -p < holes/prompts/b2_expected_evidence.md`
See: holes/prompts/README.md for the deployment pattern.

WHY CC-SESSION: this routine needs to *derive* what primary documents should exist
for each matter, based on procedural stage + case-specific theory + PH property
law. That's open-ended legal reasoning where Claude Code's full tool suite +
adaptive judgment is the right shape, not a fixed Python+SQL pipeline.
"""
from holes.base import Routine


class B2_ExpectedEvidence(Routine):
    name = "B2_expected_evidence"
    version = "v0-cc-session"
    hole_type = "evidence_gap"
    cadence = "weekly"
    kind = "cc_session"
    cc_prompt_path = "holes/prompts/b2_expected_evidence.md"
    severity_default = "P2"
    description = ("Per-matter expected primary-evidence audit. Implemented as a CC session "
                   "(see holes/prompts/b2_expected_evidence.md).")

    def find_holes(self, cur):
        # CC-session routines are skipped by the Python dispatcher. The CC session
        # writes findings to holes_findings directly via psql. This method is never
        # called in production — but exists so the class is importable + listable.
        raise RuntimeError(
            "B2_expected_evidence is a CC-session routine; invoke via "
            "`claude -p < holes/prompts/b2_expected_evidence.md` instead."
        )
