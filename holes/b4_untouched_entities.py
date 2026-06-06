"""holes.b4_untouched_entities — STUB.

Weekly: find entities (in `entities` table) referenced in 3+ documents but with
NO relationship edges in title_chain / transferees / parties / case_party_roles.
Leo sees them in the corpus but has no model of who they are.

TODO:
  1. SELECT e.* FROM entities e
     JOIN doc_entities de ON de.entity_id = e.id
     LEFT JOIN transferees t ON t.entity_id = e.id  -- or whatever the FK is
     LEFT JOIN ... (title_chain.source_entity? case_party_roles?)
     WHERE [no role/relationship]
     GROUP BY e.id HAVING COUNT(DISTINCT de.doc_id) >= 3
  2. For each: emit P3 finding "Entity X appears in N docs but Leo has no model of who they are"
  3. suggested_fix: Haiku pass to propose role + relationship from doc contexts
  4. Idempotent: hash by entity_id
"""
from holes.base import Routine, run_cli


class B4_UntouchedEntities(Routine):
    name = "B4_untouched_entities"
    version = "v0-stub"
    hole_type = "coverage_gap"
    cadence = "weekly"
    severity_default = "P3"
    description = "Entities in 3+ docs that Leo has no relational model for."

    def find_holes(self, cur):
        raise NotImplementedError(
            "B4_untouched_entities not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(B4_UntouchedEntities)
