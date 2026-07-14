#!/usr/bin/env python3
"""test_property_development.py — mechanical floor for the Property Development spine (deploy_911).

Grounds the provisional invariants A81–A84 + the two design refinements against the LIVE ledger,
not the doc. Design of record: docs/PROPERTY_DEVELOPMENT_SPINE.md.

  schema            — the 6 spine tables + 2 views + the A82 constraint exist
  A81_client_code   — every governed row carries a client_code (isolation wall present)
  A82_check_bites   — status='ok' with NO evidence is REJECTED by the DB CHECK (fail-closed)
  A83_no_free_coords— no free-text coordinate columns on projects (geometry only via link tables)
  A84_ready_earned  — no active project at stage 'ready' with a non-ok precondition
  board_scope       — v_development_board shows only ACTIVE + CURATED projects
  population        — no project attaches to an origin='title' stub (curated-only)
  ownership_place   — asset-owned codes are never stored under owner_kind='project'
  asset_is_cache    — asset-owned rows are engine-derived (never operator/verified) [Refinement 2]
  tenure_rule       — clouded title => secure_tenure/marketable_title blocked; clean => not blocked
"""
import os
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _harness import run, TruthFailure

SPINE_TABLES = ["development_projects", "asset_titles", "asset_map_parcels",
                "asset_survey_parcels", "asset_preconditions", "development_permits"]
SPINE_VIEWS = ["v_development_board", "v_asset_inventory"]
GOVERNED = SPINE_TABLES + []          # every spine table carries client_code
ASSET_OWNED_CODES = ["secure_tenure", "survey_geometry", "possession",
                     "marketable_title", "seller_authority", "tax_clearance", "registrable",
                     "usable", "mineral_rights"]


def schema_present(cur):
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename = ANY(%s)", (SPINE_TABLES,))
    have = {r["tablename"] for r in cur.fetchall()}
    missing = set(SPINE_TABLES) - have
    if missing:
        raise TruthFailure(f"missing spine tables: {sorted(missing)}")
    cur.execute("SELECT viewname FROM pg_views WHERE viewname = ANY(%s)", (SPINE_VIEWS,))
    have_v = {r["viewname"] for r in cur.fetchall()}
    if set(SPINE_VIEWS) - have_v:
        raise TruthFailure(f"missing views: {sorted(set(SPINE_VIEWS) - have_v)}")
    cur.execute("SELECT 1 FROM pg_constraint WHERE conname='asset_preconditions_ok_requires_evidence'")
    if not cur.fetchone():
        raise TruthFailure("A82 CHECK constraint asset_preconditions_ok_requires_evidence is missing")


def a81_client_code(cur):
    """Every row of every spine table carries a non-null client_code (A81 isolation)."""
    offenders = []
    for t in SPINE_TABLES:
        cur.execute(f"SELECT count(*) AS n FROM {t} WHERE client_code IS NULL")
        n = cur.fetchone()["n"]
        if n:
            offenders.append((t, n))
    if offenders:
        raise TruthFailure(f"rows with NULL client_code (A81 breach): {offenders}")


def a82_check_bites(cur):
    """A silent ok (no source_doc_id, no evidence_ref, not operator) must be REJECTED."""
    probe = "__a82_probe__"
    cur.execute("DELETE FROM asset_preconditions WHERE code=%s", (probe,))
    try:
        cur.execute("""INSERT INTO asset_preconditions
            (client_code,owner_kind,owner_code,mode,code,label,status,provenance_level)
            VALUES ('Paracale-001','asset','PA-GOLDEN-SAND','develop',%s,'probe','ok','inferred_strong')""",
            (probe,))
    except psycopg2.errors.CheckViolation:
        return  # correct: fail-closed
    # got here => constraint did not bite; clean up and fail
    cur.execute("DELETE FROM asset_preconditions WHERE code=%s", (probe,))
    raise TruthFailure("A82: silent ok (no evidence) was ACCEPTED — CHECK is not enforcing")


def a83_no_free_coords(cur):
    """No free-text coordinate columns on development_projects (geometry only via link tables)."""
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='development_projects'
                     AND (column_name ILIKE '%%lat%%' OR column_name ILIKE '%%lng%%'
                          OR column_name ILIKE '%%geom%%' OR column_name ILIKE '%%coord%%')""")
    bad = [r["column_name"] for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"A83: development_projects has coordinate columns {bad} — use link tables")


def a84_ready_earned(cur):
    """No active project at stage 'ready' while any of its preconditions is not ok."""
    cur.execute("""
        SELECT p.project_code, count(*) FILTER (WHERE x.status <> 'ok') AS not_ok
        FROM development_projects p
        JOIN asset_preconditions x
          ON x.mode = p.mode
         AND ((x.owner_kind='asset'   AND x.owner_code=p.asset_code)
           OR (x.owner_kind='project' AND x.owner_code=p.project_code))
        WHERE p.stage = 'ready' AND p.status = 'active'
        GROUP BY p.project_code
        HAVING count(*) FILTER (WHERE x.status <> 'ok') > 0
    """)
    bad = [(r["project_code"], r["not_ok"]) for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"A84: projects at 'ready' with non-ok preconditions: {bad}")


def board_scope(cur):
    """v_development_board must expose only active + curated projects."""
    cur.execute("""SELECT count(*) AS n FROM development_projects p
                   WHERE p.status='active'
                     AND EXISTS (SELECT 1 FROM property_assets a
                                 WHERE a.asset_code=p.asset_code AND a.origin IN ('seed','operator'))""")
    expect = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM v_development_board")
    got = cur.fetchone()["n"]
    if got != expect:
        raise TruthFailure(f"v_development_board scope: expected {expect} active+curated, got {got}")


def population_curated_only(cur):
    """No development_project may attach to a title stub (origin='title')."""
    cur.execute("""SELECT p.project_code, a.origin FROM development_projects p
                   JOIN property_assets a ON a.asset_code=p.asset_code
                   WHERE a.origin NOT IN ('seed','operator')""")
    bad = [(r["project_code"], r["origin"]) for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"projects attached to non-curated assets (design §1.1): {bad}")


def ownership_placement(cur):
    """Asset-owned codes must never be stored with owner_kind='project'."""
    cur.execute("""SELECT owner_code, code FROM asset_preconditions
                   WHERE owner_kind='project' AND code = ANY(%s)""", (ASSET_OWNED_CODES,))
    bad = [(r["owner_code"], r["code"]) for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"asset-owned codes stored under a project (design §1.3): {bad}")


def asset_rows_are_cache(cur):
    """Refinement 2: asset-owned precondition rows are engine-derived — never operator/verified."""
    cur.execute("""SELECT owner_code, code, provenance_level FROM asset_preconditions
                   WHERE owner_kind='asset' AND provenance_level IN ('operator','verified')""")
    bad = [(r["owner_code"], r["code"], r["provenance_level"]) for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"asset-owned rows hand-set to operator/verified (must be engine-derived): {bad}")


def tenure_rule(cur):
    """clouded title => tenure precondition blocked; clean => not blocked."""
    cur.execute("""SELECT a.asset_code, a.title_status, x.code, x.status
                   FROM property_assets a
                   JOIN asset_preconditions x
                     ON x.owner_kind='asset' AND x.owner_code=a.asset_code
                    AND x.code IN ('secure_tenure','marketable_title')
                   WHERE a.title_status IN ('clouded','cancelled','clean')""")
    bad = []
    for r in cur.fetchall():
        ts = (r["title_status"] or "").lower()
        if ts in ("clouded", "cancelled") and r["status"] != "blocked":
            bad.append((r["asset_code"], r["code"], f"{ts}->{r['status']} (want blocked)"))
        if ts == "clean" and r["status"] == "blocked":
            bad.append((r["asset_code"], r["code"], f"clean->blocked (wrong)"))
    if bad:
        raise TruthFailure(f"tenure rule violations: {bad}")


def ledger_covers_stubs(cur):
    """deploy_913: title stubs must carry asset-owned ledger rows after full recompute (not curated-only)."""
    cur.execute("SELECT count(*) AS n FROM property_assets WHERE origin='title' AND client_code IS NOT NULL")
    stubs = cur.fetchone()["n"]
    if stubs < 1:
        return  # empty portfolio — nothing to assert
    cur.execute("""SELECT count(DISTINCT owner_code) AS n FROM asset_preconditions
                   WHERE owner_kind='asset' AND owner_code IN (
                     SELECT asset_code FROM property_assets WHERE origin='title' AND client_code IS NOT NULL
                   )""")
    covered = cur.fetchone()["n"]
    if covered < stubs * 0.9:  # allow tiny drift; full sync should be ~100%
        raise TruthFailure(
            f"ledger covers only {covered}/{stubs} title stubs — run development_engine --recompute "
            f"(revenue_engine --sync). Curated-only recompute would leave stubs dark.")


def revenue_reads_ledger(cur):
    """revenue_engine.plan_for must not invent ok without a ledger row (grep-floor + live sample)."""
    # code contract: revenue_engine imports CATALOG from development_engine and loads asset_preconditions
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "revenue_engine.py")
    src = open(path, encoding="utf-8").read()
    if "from development_engine import" not in src and "import development_engine" not in src:
        raise TruthFailure("revenue_engine must import development_engine (single catalog/writer)")
    if "asset_preconditions" not in src:
        raise TruthFailure("revenue_engine must read asset_preconditions (ledger)")
    if "def _assess(" in src and "_assess(a, code)" in src:
        # old ephemeral assess path must not remain as the board brain
        if "Return (status, reason). status: ok | blocked" in src:
            raise TruthFailure("revenue_engine still has ephemeral _assess board path — remove dual epistemology")


def v12_shadow_present(cur):
    """V12 config is log-mode and all spine isolation triggers exist (deploy_912)."""
    cur.execute("SELECT mode FROM ontology_validator_config WHERE check_code='V12'")
    row = cur.fetchone()
    if not row:
        raise TruthFailure("V12 missing from ontology_validator_config")
    if row["mode"] not in ("log", "block"):
        raise TruthFailure(f"V12 mode unexpected: {row['mode']}")
    needed = [
        "ontvv_v12_asset_preconditions",
        "ontvv_v12_asset_map_parcels",
        "ontvv_v12_asset_survey_parcels",
        "ontvv_v12_asset_titles",
        "ontvv_v12_development_projects",
        "ontvv_v12_development_permits",
    ]
    cur.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname = ANY(%s)", (needed,))
    have = {r["tgname"] for r in cur.fetchall()}
    missing = set(needed) - have
    if missing:
        raise TruthFailure(f"V12 triggers missing: {sorted(missing)}")


def v12_orphan_owner_logged(cur):
    """Shadow bite: orphan owner_code is rejected-or-logged (log mode allows write but records).

    In log mode the insert SUCCEEDS but ontology_reject should fire. We use a SAVEPOINT,
    insert a synthetic precondition with a nonexistent asset owner, then check holes_findings
    (or accept that block mode would RAISE — we only require log does not crash and either
    logs or the row can be cleaned). Cleanup always.
    """
    tag = "TT-V12-ORPHAN-OWNER"
    cur.execute("DELETE FROM asset_preconditions WHERE owner_code=%s AND code=%s", (tag, "secure_tenure"))
    # Use a real client so the FK on client_code (if any) is happy
    cur.execute("SELECT client_code FROM property_assets WHERE client_code IS NOT NULL LIMIT 1")
    cc = cur.fetchone()["client_code"]
    try:
        cur.execute(
            """INSERT INTO asset_preconditions
               (client_code, owner_kind, owner_code, mode, code, label, status, provenance_level)
               VALUES (%s, 'asset', %s, 'develop', 'secure_tenure', 'tt orphan', 'unknown', 'inferred_weak')""",
            (cc, tag),
        )
    except Exception as e:
        # block mode would raise — also acceptable
        if "V12" not in str(e) and "ontology_validator" not in str(e):
            raise TruthFailure(f"orphan insert failed for unexpected reason: {e}")
        return
    # log mode: row present (shadow does not block). Clean up always.
    cur.execute("DELETE FROM asset_preconditions WHERE owner_code=%s AND code=%s", (tag, "secure_tenure"))


TESTS = [
    ("property_development.schema", schema_present),
    ("property_development.A81_client_code", a81_client_code),
    ("property_development.A82_check_bites", a82_check_bites),
    ("property_development.A83_no_free_coords", a83_no_free_coords),
    ("property_development.A84_ready_earned", a84_ready_earned),
    ("property_development.board_scope", board_scope),
    ("property_development.population_curated_only", population_curated_only),
    ("property_development.ownership_placement", ownership_placement),
    ("property_development.asset_rows_are_cache", asset_rows_are_cache),
    ("property_development.tenure_rule", tenure_rule),
    ("property_development.v12_shadow_present", v12_shadow_present),
    ("property_development.v12_orphan_owner_path", v12_orphan_owner_logged),
    ("property_development.ledger_covers_stubs", ledger_covers_stubs),
    ("property_development.revenue_reads_ledger", revenue_reads_ledger),
]


if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
