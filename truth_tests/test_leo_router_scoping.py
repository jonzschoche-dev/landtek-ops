#!/usr/bin/env python3
"""test_leo_router_scoping.py — Leo's record-answer router must answer the asked client only, and
must not answer a non-title question with a title list. Locks the defects found 2026-11-03 while
testing whether Kristyle (field officer, Messenger) could ask case questions:

  1. CROSS-CLIENT LEAK (A5/A25): "When is the next hearing in the Balane case?" asked under
     Paracale-001 / NIBDC-001 / LANDTEK-CORP returned MWK-001 dates. The deadlines composer's
     surfaced_deadlines and calendar_events homes had no client filter.
  2. GARBAGE ANSWER: "ano ang next court date?", "What is the status of the guardianship?",
     "status of CV6839" returned "Title 079-2018001329, 079-2021002126." The inquiry stack's
     general branch volunteered title atoms for any ask, against its own comment.
  3. The no-hit reply was operator jargon ("No typed stack hit ... human review").

Data-relative (matter ownership is read from the DB). Every probe runs in a rolled-back transaction.
"""
import os
import re
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "leo_tools"))
from _harness import run, TruthFailure, DSN
import leo_service as LS
import inquiry_stack as IST
from consensus import compose_answer

CLIENTS = ("MWK-001", "Paracale-001", "NIBDC-001", "LANDTEK-CORP")
DEADLINE_ASKS = ("When is the next hearing in the Balane case?", "What is the next deadline?",
                 "anything due this month?")
NON_TITLE_ASKS = ("ano ang next court date?", "What is the status of the guardianship?",
                  "status of CV6839")
JARGON = re.compile(r"\b(stack|typed|corpus|layers?|CTNs?|atoms?|human review|fail-?closed)\b", re.I)
TITLE_LIST = re.compile(r"\bTitles?\s+(T-?\d{2,}|\d{3}-\d{6,})")


def _rb():
    conn = psycopg2.connect(DSN); conn.autocommit = False
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _ask(client, q):
    conn, tc = _rb()
    try:
        return LS.try_purpose_route(tc, client, q, channel="messenger", channel_user_id="probe",
                                    dry_run=True) or {}
    finally:
        conn.rollback(); conn.close()


def _owned(cur):
    cur.execute("SELECT matter_code, client_code FROM matters WHERE matter_code IS NOT NULL")
    out = {}
    for r in cur.fetchall():
        out.setdefault(r["client_code"], set()).add(r["matter_code"])
    return out


def deadlines_composer_returns_only_own_matters(cur):
    """Every claim the deadlines composer returns for client X names a matter X owns."""
    owned = _owned(cur)
    for c in CLIENTS:
        env = compose_answer("deadlines", client_code=c, caller="truth_test:router_scoping")
        if env["status"] == "hold":
            continue
        mine = owned.get(c, set()) | {c}           # a client-level item is coded as the client
        for cl in env.get("claims") or []:
            mc = (cl.get("text") or "").split(":", 1)[0].strip()
            if mc not in mine:
                raise TruthFailure(f"CROSS-CLIENT LEAK: deadlines for {c} carried {mc!r}: "
                                   f"{cl.get('text')!r}")


def deadline_reply_never_names_another_clients_matter(cur):
    owned = _owned(cur)
    for c in CLIENTS:
        foreign = [m for k, ms in owned.items() if k != c for m in ms] + \
                  [k for k in CLIENTS if k != c]
        for q in DEADLINE_ASKS:
            text = _ask(c, q).get("text") or ""
            for m in foreign:
                if re.search(rf"(?<![\w-]){re.escape(m)}(?![\w-])", text):
                    raise TruthFailure(f"CROSS-CLIENT LEAK: {c} asked {q!r} and was told about "
                                       f"{m}: {text[:200]!r}")


def general_ask_never_volunteers_titles(cur):
    """Unit lock: the stack's general branch returns no atoms even when title atoms are present."""
    atoms = [{"atom_kind": "e_title", "value_norm": "079-2018001329"},
             {"atom_kind": "tct", "value_norm": "T-3126"}]
    for q in NON_TITLE_ASKS:
        intent = IST._intent(q.lower())
        if intent in ("title", "title_history", "title_count"):
            raise TruthFailure(f"{q!r} classified as a title ask ({intent})")
        used = IST._atoms_for_intent(intent, atoms, q.lower())
        if any(a.get("atom_kind") in ("tct", "oct", "e_title") for a in used):
            raise TruthFailure(f"{q!r} (intent {intent}) volunteered title atoms: {used}")


def non_title_question_gets_no_title_list(cur):
    for c in CLIENTS:
        for q in NON_TITLE_ASKS:
            r = _ask(c, q)
            if TITLE_LIST.search(r.get("text") or ""):
                raise TruthFailure(f"{c} asked {q!r} and got a title list: via={r.get('via')} "
                                   f"text={(r.get('text') or '')[:160]!r}")


def no_hit_reply_is_plain_language(cur):
    texts = {"STACK_CLOSED_TEXT": LS.STACK_CLOSED_TEXT}
    for q in ("blorp quux zibble?", "what is the thing about the other thing?"):
        r = IST.synthesize(q, {"atoms": [], "layers": [], "matters": []})
        texts[f"stack no-hit for {q!r}"] = r.get("text") or ""
    for label, t in texts.items():
        m = JARGON.search(t)
        if m:
            raise TruthFailure(f"{label} uses operator jargon {m.group(0)!r}: {t!r}")


TESTS = [
    ("leo_router.deadlines_composer_own_matters", deadlines_composer_returns_only_own_matters),
    ("leo_router.deadline_reply_no_foreign_matter", deadline_reply_never_names_another_clients_matter),
    ("leo_router.general_never_volunteers_titles", general_ask_never_volunteers_titles),
    ("leo_router.non_title_no_title_list", non_title_question_gets_no_title_list),
    ("leo_router.no_hit_plain_language", no_hit_reply_is_plain_language),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
