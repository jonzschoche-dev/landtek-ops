#!/usr/bin/env python3
"""test_staff_knowledge.py — the field-officer bot's training (deploy_1326) stays sourced and routes right.

Locks what the first exam of 3 Nov 2026 found, without calling the model (the gate must not depend on the Mac):
  1. Task questions that mention "deadline", "petition" or "Landbank" were sent to the case branch.
     Only an explicit case question (kaso, hearing, court, a docket) may go there first.
  2. "Kailangan ba ng cedula?" was read as "why is this task needed".
  3. 4 Nov: a case answer called Wed 11 Nov 2026 a "Saturday"; a weekday the sources do not state is rejected.
  4. Every knowledge card carries a source and a checked date; a card is live only if its topic's exam passed
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


def invented_weekday_is_rejected(cur):
    src = "A hearing is reported for 11 November 2026; the time is not known."
    if not SD._unsupported("The hearing is on Saturday, November 11, 2026.", src):
        raise TruthFailure("an answer naming a weekday the sources do not state was not rejected")
    if SD._unsupported("The hearing is on 11 November 2026.", src):
        raise TruthFailure("a plain sourced date was rejected")


def named_cases_are_found(cur):
    for q, code in (("Ano ang Ombudsman case 1214?", "MWK-OMB-IC-OC-JUL-26-1214"),
                    ("Sino ang abogado sa Balane case?", "MWK-CV26360"),
                    ("Who is the respondent in ARTA 1378?", "MWK-ARTA-1378")):
        got = [h["matter_code"] for h in SD._find_matters(cur, q)]
        if got != [code]:
            raise TruthFailure(f"{q!r} found {got}, expected [{code}]")


def strategy_questions_never_reach_the_model(cur):
    for q in ("What is our strategy against Balane in the case?", "Ano ang diskarte natin sa kaso?",
              "Paano tayo mananalo sa Balane case?", "What are their weaknesses?"):
        if not SD.STRATEGY.search(q):
            raise TruthFailure(f"strategy question {q!r} would be answered on the officer desk")
    for q in ("Sino ang abogado sa Balane case?", "Kailan ang hearing?"):
        if SD.STRATEGY.search(q):
            raise TruthFailure(f"plain question {q!r} blocked as strategy")


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
    ("staff_knowledge.invented_weekday_rejected", invented_weekday_is_rejected),
    ("staff_knowledge.named_cases_found", named_cases_are_found),
    ("staff_knowledge.strategy_blocked", strategy_questions_never_reach_the_model),
    ("staff_knowledge.cards_sourced", cards_are_sourced),
    ("staff_knowledge.live_cards_examined", live_cards_passed_their_exam),
]

if __name__ == "__main__":
    p, f = run(TESTS)
    sys.exit(0 if not f else 1)
