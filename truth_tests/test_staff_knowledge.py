#!/usr/bin/env python3
"""test_staff_knowledge.py — the field-officer bot's training (deploy_1326) stays sourced and routes right.

Locks what the first exam of 3 Nov 2026 found, without calling the model (the gate must not depend on the Mac):
  1. Task questions that mention "deadline", "petition" or "Landbank" were sent to the case branch.
     Only an explicit case question (kaso, hearing, court, a docket) may go there first.
  2. "Kailangan ba ng cedula?" was read as "why is this task needed".
  3. Every knowledge card carries a source and a checked date; a card is live only if its topic's exam passed
     (or Jonathan answered it himself), so nothing unexamined reaches an officer.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from _harness import run, TruthFailure
import staff_desk as SD

TASK_QS = ("When is the deadline for the FAO?", "Where do I look for the petition for correction?",
           "Which Landbank branch should I go to?", "What form do I use for BIR registration? 1903?",
           "Ano ang TIN ng company? 506-955-144-000?", "What is the status of my BIR registration?")
CASE_QS = ("Kailan ang next hearing ng 26-360?", "What is the status of the Balane case?",
           "ano na ang kaso sa guardianship?", "status of CV6839")


def task_questions_do_not_go_to_case_branch(cur):
    for q in TASK_QS:
        if SD.CASE_EXPLICIT.search(q):
            raise TruthFailure(f"task question {q!r} would go to the case branch ({SD.CASE_EXPLICIT.search(q).group(0)!r})")


def explicit_case_questions_go_to_case_branch(cur):
    for q in CASE_QS:
        if not SD.CASE_EXPLICIT.search(q):
            raise TruthFailure(f"case question {q!r} would not reach the case answer")


def why_is_not_a_needs_question(cur):
    for q in ("Kailangan ba ng cedula?", "Kailangan ba ang notary?", "Is a selfie necessary for ORUS?"):
        if SD.WHY.search(q) or SD.WHY_SHORT.match(q):
            raise TruthFailure(f"{q!r} would be answered with the task's 'why'")
    for q in ("Why is it necessary?", "Bakit?", "Kailangan ba?", "necessary?", "para saan ito?"):
        if not (SD.WHY.search(q) or SD.WHY_SHORT.match(q)):
            raise TruthFailure(f"{q!r} would not be answered with the task's 'why'")


def cards_are_sourced(cur):
    cur.execute("""SELECT id FROM staff_knowledge
                    WHERE coalesce(trim(source_ref), '') = '' OR checked_on IS NULL OR coalesce(trim(fact), '') = ''""")
    bad = [r["id"] for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"knowledge cards without source, date or fact: {bad}")


def live_cards_passed_their_exam(cur):
    cur.execute("""SELECT k.id, k.topic FROM staff_knowledge k
                    WHERE k.state = 'live' AND k.source_kind <> 'jonathan_said'
                      AND NOT EXISTS (SELECT 1 FROM staff_exam e JOIN staff_exam_run r ON r.exam_id = e.id
                                       WHERE e.topic = k.topic AND r.passed)""")
    bad = [(r["id"], r["topic"]) for r in cur.fetchall()]
    if bad:
        raise TruthFailure(f"live cards whose topic never passed an exam question: {bad}")


TESTS = [
    ("staff_knowledge.task_qs_not_case_branch", task_questions_do_not_go_to_case_branch),
    ("staff_knowledge.case_qs_reach_case_branch", explicit_case_questions_go_to_case_branch),
    ("staff_knowledge.needs_question_not_why", why_is_not_a_needs_question),
    ("staff_knowledge.cards_sourced", cards_are_sourced),
    ("staff_knowledge.live_cards_examined", live_cards_passed_their_exam),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
