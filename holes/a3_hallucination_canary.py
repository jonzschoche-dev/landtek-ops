"""holes.a3_hallucination_canary — MECHANICAL hallucination canary (deploy_728).

Replaces the LLM stub (Haiku claim-extraction + truth_negotiator) with a DETERMINISTIC,
creditless guard on the LEO_MASTER_PLAN "zero hallucination in client-facing output"
guarantee.

Every 4h it scans recent CLIENT-FACING outbound messages (`outbound_messages`, excluding
the operator + sim chats) and extracts structured TITLE identifiers (T-#### / P-#### /
OCT-shaped) — the classic domain hallucination vector, since a fabricated TCT number is the
textbook made-up fact. Each identifier is GROUNDED against the verified record in a cheap
ladder: `titles.tct_number` -> `title_chain` -> `documents.extracted_text`. A title asserted
to a client that is grounded NOWHERE -> a P1 finding ("verify before it reaches more
clients"). No LLM, no truth_negotiator — pure normalized set-membership.

Why title identifiers only: they are high-structure (regex-extractable), high-signal, and
cheaply groundable against a canonical table, so the canary calibrates to ~zero false
positives (verified 2026-07-06: all 16 title tokens in historical outbound are real).
Free-text claim verification stays with the LLM Simulator; this is the deterministic egress
guard, in the same spirit as the mechanical truth_tests that replaced the truth_qa harness.

Severity is P1 (review), NOT P0: a mechanical miss (OCR/format truncation) is possible, so
the canary asks a human to verify rather than paging — calibrated for zero harm on a rare FP.
"""
import re

from holes.base import Routine, run_cli

# Non-client chats — never a "client-facing" hallucination: operator + sim-guard + sim range.
INTERNAL_CHATS = {"6513067717", "0"}
# Title-shaped identifiers: optional OCT prefix, T-/P- stem, >=3 digits, optional -NNN groups.
TITLE_RE = re.compile(r"\b(?:OCT[ -]*)?[TP]-?\d{3,}(?:-\d+)*\b", re.I)


def _norm(tok):
    """Normalize a title token for format-insensitive matching (drop spaces/hyphens/case)."""
    return re.sub(r"[^A-Z0-9]", "", (tok or "").upper())


class A3_HallucinationCanary(Routine):
    name = "A3_hallucination_canary"
    version = "v1"
    hole_type = "discipline_drift"
    cadence = "every_4h"
    severity_default = "P1"
    description = ("Mechanical canary: every TITLE identifier in client-facing outbound must be grounded "
                   "in the verified record (titles / title_chain / corpus). Ungrounded -> P1, creditless.")

    def find_holes(self, cur):
        # Ground-truth: normalized known title identifiers (canonical table + chain).
        cur.execute("SELECT tct_number FROM titles WHERE tct_number IS NOT NULL")
        known = {_norm(r["tct_number"]) for r in cur.fetchall()}
        cur.execute("SELECT parent_title FROM title_chain UNION SELECT child_title FROM title_chain")
        known |= {_norm(r["parent_title"]) for r in cur.fetchall() if r["parent_title"]}
        known.discard("")

        # Recent client-facing outbound carrying a title-shaped token.
        cur.execute("""SELECT id, chat_id, content_preview FROM outbound_messages
                       WHERE sent_at > now() - interval '30 days'
                         AND content_preview ~* 'T-?[0-9]{3}'
                       ORDER BY sent_at DESC LIMIT 500""")
        msgs = cur.fetchall()   # materialized — safe to re-use cur inside the loop

        for m in msgs:
            chat = str(m["chat_id"] or "")
            if chat in INTERNAL_CHATS or chat.startswith("999000"):
                continue
            seen = set()
            for tok in TITLE_RE.findall(m["content_preview"] or ""):
                nt = _norm(tok)
                if len(nt) < 4 or nt in seen:   # skip 3-digit noise (T-525 truncations) + dedup within msg
                    continue
                seen.add(nt)
                if nt in known:
                    continue
                # Last-resort grounding: is the raw token anywhere in the corpus text?
                cur.execute("SELECT 1 FROM documents WHERE extracted_text ILIKE %s LIMIT 1", (f"%{tok}%",))
                if cur.fetchone():
                    continue
                self.emit(
                    severity="P1",
                    description=(f"Possible HALLUCINATED title identifier '{tok}' in a client-facing "
                                 f"outbound message (chat {chat}, msg {m['id']}): grounded nowhere — not "
                                 f"in titles, title_chain, or any corpus document. Verify before it "
                                 f"reaches more clients (the 'zero hallucination in client output' guarantee)."),
                    metadata={"chat_id": chat, "msg_id": m["id"], "token": tok},
                    hash_parts={"msg_id": m["id"], "token": nt},   # one open finding per (message, bad token)
                )


if __name__ == "__main__":
    run_cli(A3_HallucinationCanary)
