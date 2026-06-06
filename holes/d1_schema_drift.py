"""holes.d1_schema_drift — STUB.

Weekly: parse all *.py files in /root/landtek/ for SQL column references, compare
against actual DB schema. Find: (a) columns referenced in code that don't exist
in DB (bug — will runtime-error someday), (b) columns in DB never referenced in
code (possibly dead).

TODO:
  1. Walk /root/landtek/**/*.py
  2. Regex-extract column references:
       - SELECT (col_list) FROM (table)
       - WHERE (col) =
       - INSERT INTO (table) (col_list)
       - cur.execute("...col...")
     (Use sqlparse for robustness, or just a careful regex pass)
  3. Compare against information_schema.columns
  4. Code → no DB: P1 finding (latent bug)
  5. DB → no code: P3 finding (possibly dead)
  6. Idempotent: hash by (table, column, direction)
"""
from holes.base import Routine, run_cli


class D1_SchemaDrift(Routine):
    name = "D1_schema_drift"
    version = "v0-stub"
    hole_type = "schema_drift"
    cadence = "weekly"
    severity_default = "P1"
    description = "Code/DB schema drift — columns referenced in code that don't exist, or vice versa."

    def find_holes(self, cur):
        raise NotImplementedError(
            "D1_schema_drift not yet implemented — see module docstring."
        )


if __name__ == "__main__":
    run_cli(D1_SchemaDrift)
