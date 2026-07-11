#!/usr/bin/env python3
"""ingest_gate.py — WRITER-side ingestion-fidelity gate (A77/A78). $0, deterministic, no LLM.

The DB triggers (tg_prov_facts, ontvv_*) belong to the ontology desk and are NOT touched here.
This module is the harvest/ingest lane's OWN refusal point, applied at the writer BEFORE a
matter_facts write. It exists because of a defect proven live 2026-07-11: the V4 client-isolation
trigger passes when a cited document's owner resolves NULL, so untagged docs 1172/1177 (NIBDC/MGB
content, case_file NULL) seeded MWK-OP-PETITION facts. A77(1): an unresolved artifact never forms
an edge — so the WRITER refuses and HOLDS:

  owner_gate(cur, matter_code, doc_id, writer)      -> True (proceed) / False (HELD, no edge)
  hold_contradiction(cur, writer, matter, doc, ...)  -> A78 hold record for a conflicting ingest
                                                        (the conflict CHECK lives in
                                                        contradiction.conflicts_with_verified)

Holds are visible, never silent: one idempotent open holes_findings row per (kind, doc, matter),
routine_name='ingestion_fidelity_gate', carrying an A74-style machine-checkable recheck_condition
in metadata. Degrade-don't-crash: a gate ERROR holds the write (returns False) — it never admits
a fact on failure; only the hold-LOGGING is best-effort.

Wired into harvest_facts.py and verify_worker.py (together >99% of automated matter_facts writes).
Other writers (decipher_matter, reconciler, load_issue_spine, source_read_facts) are operator-run;
the durable stack-wide fix is a V4 amendment (ontology-desk lane — see the A77/A78 close-out).
"""
import psycopg2

ROUTINE = "ingestion_fidelity_gate"


def _val(row, key):
    """Support both RealDictCursor and plain-tuple cursors."""
    if row is None:
        return None
    return row[key] if isinstance(row, dict) else row[0]


def doc_owner_client(cur, doc_id):
    """The CLIENT the cited document resolves to (via the DB's _client_of over
    COALESCE(matter_code, case_file)), or None when unresolvable — the V4 bypass class."""
    cur.execute("SELECT _client_of(COALESCE(matter_code, case_file)) AS c FROM documents WHERE id=%s",
                (int(doc_id),))
    return _val(cur.fetchone(), "c")


def _hold(cur, kind, writer, matter_code, doc_id, description, recheck_condition):
    """Idempotent visible hold: one OPEN holes_findings row per (kind, doc, matter). Best-effort —
    the REFUSAL is enforced by the caller's return value regardless of whether logging succeeds."""
    try:
        key = f"{kind}|{matter_code}|{doc_id}"
        cur.execute("""INSERT INTO holes_findings (routine_name, routine_version, finding_id_hash,
                         severity, hole_type, matter_code, doc_id, description, metadata, status)
                       SELECT %s, 'v1', md5(%s), 'high', %s, %s, %s, %s,
                              jsonb_build_object('writer', %s, 'recheck_condition', %s), 'open'
                       WHERE NOT EXISTS (SELECT 1 FROM holes_findings
                          WHERE finding_id_hash = md5(%s) AND status = 'open')""",
                    (ROUTINE, key, kind, matter_code, int(doc_id), description,
                     writer, recheck_condition, key))
    except Exception:
        pass  # logging must never crash the writer; the write is refused either way


def owner_gate(cur, matter_code, doc_id, writer, record=True):
    """A77(1)/A5: may a fact for `matter_code` cite document `doc_id`?
    True  -> the doc's owner resolves to a client (V4 then enforces cross-client at the trigger).
    False -> owner UNRESOLVABLE (or gate error) — the write is HELD; with record=True a visible
             holes_findings hold is recorded. Never guesses, never silently allows."""
    try:
        client = doc_owner_client(cur, doc_id)
    except Exception:
        client = None  # degrade-don't-crash: a gate error HOLDS, never admits
    if client:
        return True
    if record:
        _hold(cur, "unresolved_doc_owner", writer, matter_code, doc_id,
              f"A77 hold ({writer}): doc {doc_id} has no resolvable client owner "
              f"(matter_code/case_file NULL or unmapped) — fact-write for {matter_code} REFUSED; "
              f"an unresolved artifact never forms an edge (A5). Tag the doc's owner, then re-run.",
              f"documents id={doc_id}: _client_of(COALESCE(matter_code,case_file)) IS NOT NULL")
    return False


def hold_contradiction(cur, writer, matter_code, doc_id, statement, conflicts, record=True):
    """A78: record a visible hold for an inbound fact that CONTRADICTS a verified fact.
    `conflicts` = contradiction.conflicts_with_verified(...) output. The caller refuses the write."""
    if not (record and conflicts):
        return
    det = "; ".join(f"{c['event']}: incoming {c['incoming']} vs verified {','.join(c['verified'])} "
                    f"(fact_ids {','.join(str(i) for i in c['fact_ids'])})" for c in conflicts[:4])
    _hold(cur, "contradiction_hold", writer, matter_code, doc_id,
          f"A78 hold ({writer}): incoming fact from doc {doc_id} contradicts VERIFIED fact(s) — "
          f"HELD upstream of the engine, not propagated. {det} | statement: {statement[:220]}",
          f"contradiction resolved: the matter's verified facts carry one date for the event(s) "
          f"[{', '.join(c['event'] for c in conflicts[:4])}] (contradictions row closed)")
