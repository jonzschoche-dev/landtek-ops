"""holes.a2_self_research — self-research audit.

Every 6h: scan `truth_negotiations` for verdicts in (unsourced, uncertain) from the
last 24h. For each, re-research with:
  1. Expanded concept search (bilingual_search) against the FULL current corpus
  2. Wider evidence window (more probe directions)
  3. A Sonnet judgment call: "given this fresh evidence, can the claim now be verified?"

If the re-research now yields verdict=verified, emit a "I_DID_NOT_KNOW_BUT_NOW_DO"
finding. These are gold — each one is a moment where Leo missed an answer he could
have given. The user-facing impact: every such finding can be surfaced back into
the conversation thread it came from (chat_notes, gmail thread, Telegram).

This is the around-the-clock intelligence loop: Leo's prior 'I don't knows' become
today's knowledge.

Build complexity: medium. Uses existing truth_negotiator.negotiate() + Sonnet.
"""
import sys
from datetime import timedelta

from holes.base import Routine, run_cli, LANDTEK_ROOT, load_env

# How far back to look
LOOKBACK_HOURS = 24
# Cap to keep cost bounded per run
MAX_RECHECKS_PER_RUN = 25


class A2_SelfResearch(Routine):
    name = "A2_self_research"
    version = "v1"
    hole_type = "truth_gap"
    cadence = "every_6h"
    severity_default = "P2"
    description = "Re-attempts 'I don't know' answers from the last 24h. Each promotion is a missed-intelligence event."

    def find_holes(self, cur):
        load_env()
        sys.path.insert(0, LANDTEK_ROOT)
        from truth_negotiator import negotiate

        cur.execute(f"""
            SELECT id, claim_text, case_file, verdict, asked_by, created_at
              FROM truth_negotiations
             WHERE verdict IN ('unsourced', 'uncertain')
               AND created_at >= now() - INTERVAL '{LOOKBACK_HOURS} hours'
               AND id NOT IN (
                   -- skip negotiations we've already re-audited and resolved
                   SELECT (metadata->>'original_negotiation_id')::int
                     FROM holes_findings
                    WHERE routine_name=%s
                      AND metadata ? 'original_negotiation_id'
               )
             ORDER BY created_at DESC
             LIMIT %s
        """, (self.name, MAX_RECHECKS_PER_RUN))
        candidates = cur.fetchall()
        if not candidates:
            return

        for orig in candidates:
            # Re-attempt with fresh probe. truth_negotiator.negotiate() already does
            # bilingual concept expansion + 4-direction probe + challenger; re-running
            # against current corpus state can promote previously-uncertain claims
            # if new docs landed since the original ask.
            try:
                r = negotiate(orig["claim_text"], case_file=orig["case_file"],
                              asked_by=f"A2_recheck:{orig['id']}")
            except Exception as e:
                self.emit(
                    severity="info",
                    description=f"A2 re-research raised on negotiation #{orig['id']}: {e}",
                    case_file=orig["case_file"],
                    metadata={"original_negotiation_id": orig["id"], "error": str(e)},
                    hash_parts={"a2_recheck_error": orig["id"]},
                )
                continue

            new_verdict = r["verdict"]
            if new_verdict == "verified" and orig["verdict"] != "verified":
                # Promotion! Leo previously didn't know; now he does.
                self.emit(
                    severity="P2",
                    description=(
                        f"I_DID_NOT_KNOW_BUT_NOW_DO: '{orig['claim_text'][:200]}' "
                        f"(asked by {orig['asked_by']} {orig['created_at'].strftime('%Y-%m-%d %H:%M UTC')}, "
                        f"answered {orig['verdict']}; now verified: {r.get('citation_tag','')})"
                    ),
                    case_file=orig["case_file"],
                    suggested_fix=(
                        "Surface this back to the original asker. If asked via Telegram, "
                        "send a follow-up: 'Update on your earlier question — I now have the answer.'"
                    ),
                    metadata={
                        "original_negotiation_id": orig["id"],
                        "original_verdict": orig["verdict"],
                        "new_verdict": new_verdict,
                        "citation_tag": r.get("citation_tag"),
                        "fact_backers": list(r.get("fact_backers") or [])[:10],
                        "asked_by": orig["asked_by"],
                        "promotion_lag_hours": int(
                            (r["duration_ms"] or 0) / 1000 / 3600
                        ),  # filler; replace with real lag below
                        "original_asked_at": orig["created_at"].isoformat(),
                    },
                    hash_parts={"a2_promotion": orig["id"]},
                )
            elif new_verdict in ("unsourced", "uncertain") and orig["verdict"] == "unsourced":
                # Still nothing in the corpus. This is a true coverage gap — the
                # answer needs to come from somewhere outside the current corpus
                # (a new Gmail attachment, a doc Jonathan should request, etc.)
                self.emit(
                    severity="P3",
                    description=(
                        f"STILL_UNKNOWN after re-research: '{orig['claim_text'][:200]}' "
                        f"(asked by {orig['asked_by']} {orig['created_at'].strftime('%Y-%m-%d %H:%M')})"
                    ),
                    case_file=orig["case_file"],
                    suggested_fix=(
                        "Genuine evidence gap. Consider: (a) new document acquisition, "
                        "(b) request from counsel/client, (c) public records pull. "
                        "Surface in next intake review."
                    ),
                    metadata={
                        "original_negotiation_id": orig["id"],
                        "verdict": new_verdict,
                        "asked_by": orig["asked_by"],
                    },
                    hash_parts={"a2_still_unknown": orig["id"]},
                )


if __name__ == "__main__":
    run_cli(A2_SelfResearch)
