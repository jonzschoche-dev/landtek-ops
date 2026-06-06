"""holes.e1_capacity_health — STUB.

Daily: heightened OCR throughput trend, queue age, API-key cooldown state,
Anthropic + Gemini spend trajectory and projected cap-hit dates.

This sits next to the existing token-health-sentinel and the heightened_ocr_queue
heartbeat from sweep_loop.sh. The difference: this routine emits FINDINGS for
gaps (zero throughput today, oldest queued doc > 7 days, projected to hit cap
in N days), not just metrics.

TODO:
  1. Query heightened_ocr_queue: count by status; oldest queued doc age
  2. Query extraction_runs: docs extracted today, throughput trend (7d)
  3. Query api_key_cooldowns or gemini_key_state: any key cool >24h?
  4. Query extraction_budget / cost_log: spend trajectory; days until cap
  5. Emit P1 if throughput == 0 today AND queue > 0
  6. Emit P2 if oldest queued doc > 7 days
  7. Emit P3 if projected to hit Gemini cap in <3 days
"""
from holes.base import Routine, run_cli


class E1_CapacityHealth(Routine):
    name = "E1_capacity_health"
    version = "v0-stub"
    hole_type = "capacity_gap"
    cadence = "daily"
    severity_default = "P2"
    description = "OCR throughput, queue age, API-key state, spend trajectory."

    def find_holes(self, cur):
        raise NotImplementedError(
            "E1_capacity_health not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(E1_CapacityHealth)
