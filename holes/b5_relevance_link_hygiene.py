"""holes.b5_relevance_link_hygiene — READ-ONLY consumer for doc_relevance_triage (deploy_729).

`relevance_triage.py` wrote 958 per-(doc,matter) relevance verdicts (local qwen2.5:7b) into
`doc_relevance_triage`, then nothing ever read them back (a DEAD-PRODUCER in --triage). This
is the missing consumer — but deliberately the SAFEST possible one: it emits ONE aggregate
finding summarizing how many doc-matter LINKS contradict those verdicts (a doc linked to a
matter the local model scored NOT relevant to it), with a per-matter breakdown in metadata.

It NEVER unlinks anything. The verdicts are inference-grade (7B) and stale, and the signal is
dominated by broad matters (MWK-ESTATE / MWK-TCT4497 / MWK-CV26360) where a docket-scoped
relevance model almost certainly mis-scores — so bulk action would shred legitimate links.
The finding is explicitly ADVISORY (P3): it turns 958 dark rows into one reviewable signal
without noise or mutation. Creditless: reads Postgres only, no LLM.
"""
from holes.base import Routine, run_cli


class B5_RelevanceLinkHygiene(Routine):
    name = "B5_relevance_link_hygiene"
    version = "v1"
    hole_type = "coordination_gap"
    cadence = "weekly"
    severity_default = "P3"
    description = ("Doc-matter links that contradict the local relevance triage — one aggregate "
                   "ADVISORY finding, read-only, never auto-unlinks.")

    def find_holes(self, cur):
        # Docs linked to a matter that the local relevance model scored NOT relevant to it.
        cur.execute("""
            SELECT t.matter_code, count(*) AS n
            FROM doc_relevance_triage t
            JOIN document_matter_links l ON l.doc_id = t.doc_id AND l.matter_code = t.matter_code
            WHERE t.relevant = false
            GROUP BY t.matter_code ORDER BY n DESC""")
        rows = cur.fetchall()
        total = sum(r["n"] for r in rows)
        if total == 0:
            return   # loop closes: nothing to review → any prior finding auto-resolves on re-run

        by_matter = {r["matter_code"]: r["n"] for r in rows}
        cur.execute("SELECT max(model) m, max(decided_at)::date d FROM doc_relevance_triage")
        meta = cur.fetchone()
        top = ", ".join(f"{m} {n}" for m, n in list(by_matter.items())[:4])

        self.emit(
            severity="P3",
            description=(
                f"{total} doc-matter links across {len(by_matter)} matters contradict the LOCAL "
                f"relevance triage ({meta['m']}, INFERENCE-GRADE, last {meta['d']}): a document is "
                f"linked to a matter the local model scored NOT relevant to it. ADVISORY ONLY — do "
                f"NOT bulk-unlink. Dominated by broad matters ({top}) where a docket-scoped model "
                f"likely mis-scores; ARTA-scoped verdicts are more reliable. Review candidates via "
                f"suggested_fix; disposition is a human call."),
            suggested_fix=(
                "SELECT t.doc_id, t.matter_code, t.reason FROM doc_relevance_triage t "
                "JOIN document_matter_links l ON l.doc_id=t.doc_id AND l.matter_code=t.matter_code "
                "WHERE t.relevant=false ORDER BY t.matter_code, t.doc_id;"),
            metadata={"total": total, "by_matter": by_matter, "model": meta["m"], "last_decided": str(meta["d"])},
            hash_parts={"kind": "relevance_link_mismatch"},   # ONE standing advisory finding
        )


if __name__ == "__main__":
    run_cli(B5_RelevanceLinkHygiene)
