#!/usr/bin/env python3
"""ontology_check.py — read-only ontology linter (the loop-closer for ONTOLOGY.md).

The ontology_validator triggers (deploy_691) catch violations at WRITE time. This
script is the periodic WHOLE-CORPUS audit — it re-grounds ONTOLOGY.md against the live
schema and surfaces drift the write-gate can't (pre-existing rows, new unregistered
tables, provenance vocab creep, V4 client contamination). Read-only: prints a report,
mutates nothing. Runs on the VPS (needs the container-internal DSN).

Usage:
  python3 scripts/ontology_check.py            # full report
  python3 scripts/ontology_check.py --brief    # phone-friendly one-screen summary
  python3 scripts/ontology_check.py --sentinel # daily timer mode: silent when clean; writes ONE
                                               # high-severity holes_findings row ONLY on NEW
                                               # actionable contamination (V3/V4 > 0). Standing
                                               # backlog (drift tables, vocab creep) never alerts.

Exit code: 0 = clean, 1 = drift/contamination found (usable as a health gate).
"""
from __future__ import annotations
import os
import sys
import psycopg2

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# Canonical provenance vocabulary (grounded 2026-07-05 — see ONTOLOGY.md A1).
PROVENANCE_VOCAB = {
    "verified", "operator", "inferred_strong", "inferred_corroborated", "inferred_weak",
}

# Drift tables — nothing should be writing these (ONTOLOGY.md sec3).
DRIFT_TABLES = ["chain_of_title", "cases", "finance_transactions", "fact_edges"]

# Fact-bearing tables that carry provenance_level (for vocab audit).
PROVENANCE_TABLES = [
    "matter_facts", "entities", "titles", "title_chain", "title_transfers",
    "doc_entities", "transferees", "legal_authorities", "knowledge_graph_triples",
    "subdivision_plans", "transactions",
]

# Tables named in ONTOLOGY.md sec2 (canonical + staging). New public tables NOT in this
# set are candidate drift → flagged for registry review. n8n plumbing is excluded.
REGISTERED = set(DRIFT_TABLES + PROVENANCE_TABLES + [
    "documents", "rag_local", "extraction_runs", "extraction_chunks", "extraction_contract",
    "field_consensus", "gmail_messages", "email_documents", "duplicate_groups",
    "duplicate_group_members", "actor_lifespan", "clients", "matters", "proposed_facts",
    "claims", "claim_truth_verdicts", "verified_claims", "cross_matter_links", "keystones",
    "matter_state", "matter_plays", "matter_authorities", "doc_requirements_law",
    "ombudsman_candidates", "arta_cases", "case_threads", "channels", "channel_messages",
    "outbound_messages", "outbound_blocks", "leo_interactions", "client_access_tokens",
    "file_access_tokens", "map_parcels", "parcels", "document_titles", "title_matter_links",
    "instruments_on_title", "transfer_doc_status", "document_matter_links",
    "ontology_validator_config",
])

# n8n plumbing prefixes/names to exclude from "unregistered" noise.
PLUMBING_PREFIX = (
    "workflow", "execution", "credentials", "shared_", "oauth", "chat_hub", "instance_ai",
    "installed_", "folder", "data_table", "annotation", "webhook", "tag_", "project",
    "insights", "test_case", "auth_provider", "secrets_provider", "dynamic_credential",
    "role", "scope", "user", "settings", "migrations", "variables", "event_destinations",
    "processed_data", "invalid_auth", "api_keys",
)


def is_plumbing(t: str) -> bool:
    return t in ("role", "scope", "role_scope", "user", "settings", "migrations",
                 "api_keys", "user_api_keys") or t.startswith(PLUMBING_PREFIX)


def main():
    brief = "--brief" in sys.argv
    sentinel = "--sentinel" in sys.argv
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    problems = 0
    v3 = v4 = 0
    out = []
    with conn.cursor() as cur:
        # 1. validator installed?
        cur.execute("SELECT check_code, mode FROM ontology_validator_config ORDER BY 1;")
        cfg = cur.fetchall()
        out.append(f"validator: {'installed ' + str(cfg) if cfg else 'NOT INSTALLED (run deploy_691)'}")

        # 2. V4 client contamination (verified facts citing a cross-client doc)
        cur.execute("SELECT count(*) FROM v_ontology_client_cross;")
        v4 = cur.fetchone()[0]
        if v4:
            problems += 1
            out.append(f"[X] V4 client contamination: {v4} verified fact(s) cite a cross-client doc — SELECT * FROM v_ontology_client_cross;")
        else:
            out.append("[ok] V4 client isolation: clean (0 cross-client verified facts)")

        # 3. V3 grounding: verified facts missing source/excerpt
        cur.execute("SELECT count(*) FROM matter_facts WHERE provenance_level='verified' AND (source_id IS NULL OR coalesce(excerpt,'')='');")
        v3 = cur.fetchone()[0]
        if v3:
            problems += 1
            out.append(f"[X] V3 grounding: {v3} verified matter_fact(s) missing source_id/excerpt")
        else:
            out.append("[ok] V3 grounding: clean (all verified facts grounded)")

        # 4. drift tables — should be cold
        for t in DRIFT_TABLES:
            cur.execute(f"SELECT count(*) FROM {t};")
            n = cur.fetchone()[0]
            if n:
                out.append(f"[!] drift '{t}': {n} row(s) present — canonical target in ONTOLOGY.md sec3 (do not add more)")
            elif not brief:
                out.append(f"[ok] drift '{t}': empty")

        # 5. provenance vocab creep
        if not brief:
            bad = []
            for t in PROVENANCE_TABLES:
                cur.execute(f"SELECT DISTINCT provenance_level FROM {t} WHERE provenance_level IS NOT NULL;")
                for (v,) in cur.fetchall():
                    if v not in PROVENANCE_VOCAB:
                        bad.append(f"{t}:{v}")
            if bad:
                problems += 1
                out.append(f"[X] provenance vocab creep: {bad} (canonical set: {sorted(PROVENANCE_VOCAB)})")
            else:
                out.append(f"[ok] provenance vocab: all values in canonical set of {len(PROVENANCE_VOCAB)}")

        # 6. unregistered domain tables (candidate drift → update ONTOLOGY.md sec2)
        if not brief:
            cur.execute("SELECT relname FROM pg_stat_user_tables;")
            live = {r[0] for r in cur.fetchall()}
            unreg = sorted(t for t in live if not is_plumbing(t) and t not in REGISTERED)
            if unreg:
                out.append(f"[i] {len(unreg)} domain table(s) not in ONTOLOGY.md registry (review): {unreg[:25]}{'...' if len(unreg) > 25 else ''}")

    # --sentinel: alert ONLY on new actionable contamination (V3/V4), never on standing backlog.
    if sentinel and (v3 or v4):
        bits = []
        if v4:
            bits.append(f"{v4} verified fact(s) cite a cross-client document (V4)")
        if v3:
            bits.append(f"{v3} verified fact(s) missing source/excerpt (V3)")
        desc = ("ontology_check daily sentinel: " + "; ".join(bits)
                + ". Triage: SELECT * FROM v_ontology_client_cross; re-home to the doc's matter (see ONTOLOGY.md A5).")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO holes_findings(routine_name, routine_version, finding_id_hash,
                         severity, hole_type, description, metadata, status)
                       VALUES ('ontology_check','v1', md5(%s), 'high', 'ontology_contamination',
                         %s, jsonb_build_object('v3',%s,'v4',%s), 'open')""",
                    (desc[:200], desc, v3, v4),
                )
        except Exception:
            pass  # sentinel must never crash the timer

    conn.close()
    print("=== ontology_check " + ("(brief) " if brief else "") + ("(sentinel) " if sentinel else "") + "===")
    for line in out:
        print("  " + line)
    print(f"=== {'CLEAN' if problems == 0 else str(problems) + ' PROBLEM(S)'} ===")
    # Interactive/gate mode: non-zero on any drift so it's usable as a health gate.
    # Sentinel mode: exit reflects ONLY actionable contamination (V3/V4) — the standing
    # backlog (vocab creep, pre-existing drift rows) must not put the daily oneshot into
    # a systemd 'failed' state (keep `systemctl --failed` at zero).
    if sentinel:
        sys.exit(1 if (v3 or v4) else 0)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
