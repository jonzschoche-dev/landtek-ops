"""holes.b3_stage_claim_backtest — STUB.

Daily: for each active matter, run the claim "Matter X is at stage Y" through
truth_negotiator. verdict != verified → finding flagging that the matter's stage
assignment doesn't actually have evidence backing it.

TODO:
  1. Query matters WHERE status='active' AND current_stage IS NOT NULL
  2. For each: construct claim string from {title, docket_number, current_stage}
     e.g. "Civil Case 26-360 is at the pretrial_pending stage"
  3. negotiate(claim, case_file=matter.case_file)
  4. If verdict != 'verified': emit P2 finding with the actual verdict + challenger_reason
  5. Special: if verdict=='refuted' (active contradiction in corpus): bump to P1
  6. Idempotent: hash by (matter_code, current_stage)

This catches misclassified matters early. If we say a case is at pretrial but
the corpus says otherwise, that's a calibration hole worth knowing about.
"""
from holes.base import Routine, run_cli


class B3_StageClaimBacktest(Routine):
    name = "B3_stage_claim_backtest"
    version = "v0-stub"
    hole_type = "coverage_gap"
    cadence = "daily"
    severity_default = "P2"
    description = "Every matter's stage assignment is back-tested against the corpus daily."

    def find_holes(self, cur):
        raise NotImplementedError(
            "B3_stage_claim_backtest not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(B3_StageClaimBacktest)
