#!/usr/bin/env python3
"""human_pass.py — facts-first emission + equation for when to pass to a human.

Protocol:
  1. Answer ONLY with stack facts (ids, dates, stages, goals) — no speculative legal advice
     unless a scenario pack + local law supports it.
  2. Compute human_pass_score. If score >= THRESHOLD → HOLD for human (with facts attached).
  3. If score < THRESHOLD and facts exist → short facts-only reply.
  4. If no facts → hold (never invent).

Equation (0–100, higher = more need for human):

  score =
      40 * I_scenario          # what-if / should we / if ignored / strategy
    + 25 * I_law_gap           # process depends on law not in local corpus
    + 20 * I_no_verified       # zero verified facts in scope
    + 15 * I_clarity_unclear   # matter/title marked needs_human_review / unclear
    + 15 * I_contradiction     # open contradiction / conflict holes
    + 10 * I_multi_matter      # ask spans many matters without a clear bind
    + 10 * I_expectation       # client expectation / deadline commitment at stake
    - 20 * I_lookup_only       # pure id lookup with hard hit (docket, MRO, CTN, TCT)
    - 10 * I_single_fact_hit   # one clear typed hit answers the ask

  THRESHOLD default = 50  → pass to human
  score < 50 and facts    → auto facts-only
  score < 50 and no facts → hold (treated as pass/gap)

Usage:
  from human_pass import score_inquiry, format_facts_only, decide_emission
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Pass to human when score >= this
HUMAN_PASS_THRESHOLD = 50

# Emission caps (S14 / equilibrium dose)
FACTS_ONLY_CAP = 220


def _is_scenario(message: str) -> bool:
    t = (message or "").lower()
    return bool(re.search(
        r"\b(what should|should we|if .+ ignor|if .+ fail|what if|how do we|"
        r"recommend|advise|next step|strategy|options?)\b",
        t,
    ))


def _is_lookup(message: str) -> bool:
    t = (message or "").lower()
    return bool(re.search(
        r"\b(docket|mro|ctn|case no|case number|tct|oct|title no|ref|receiving|"
        r"when was|what is the|which ctn|how many)\b",
        t,
    )) and not _is_scenario(t)


def score_inquiry(
    message: str,
    *,
    atoms: list | None = None,
    layers: list | None = None,
    n_verified_in_scope: int = 0,
    clarity_unclear: bool = False,
    open_contradictions: int = 0,
    n_matters_touched: int = 1,
    law_gap: bool = False,
    expectation_at_stake: bool = False,
    hard_lookup_hit: bool = False,
) -> dict:
    """Return {score, threshold, pass_to_human, reasons, mode}."""
    atoms = atoms or []
    layers = layers or []
    reasons = []
    score = 0

    scenario = _is_scenario(message)
    lookup = _is_lookup(message) or hard_lookup_hit

    if scenario:
        score += 40
        reasons.append("+40 scenario/strategy ask")
    if law_gap:
        score += 25
        reasons.append("+25 law gap (local corpus miss)")
    if n_verified_in_scope <= 0 and not hard_lookup_hit:
        score += 20
        reasons.append("+20 no verified facts in scope")
    if clarity_unclear:
        score += 15
        reasons.append("+15 clarity unclear / needs_human_review")
    if open_contradictions > 0:
        score += 15
        reasons.append(f"+15 open contradictions ({open_contradictions})")
    if n_matters_touched >= 4:
        score += 10
        reasons.append("+10 multi-matter sprawl")
    if expectation_at_stake:
        score += 10
        reasons.append("+10 client expectation / commitment")

    if lookup and (hard_lookup_hit or atoms):
        score -= 20
        reasons.append("-20 pure lookup with stack hit")
    if hard_lookup_hit and len(atoms) <= 3:
        score -= 10
        reasons.append("-10 single clear typed hit")

    score = max(0, min(100, score))
    pass_human = score >= HUMAN_PASS_THRESHOLD

    if pass_human:
        mode = "pass_to_human"
    elif atoms or hard_lookup_hit:
        mode = "facts_only"
    else:
        mode = "hold_no_facts"  # also human-visible gap

    return {
        "score": score,
        "threshold": HUMAN_PASS_THRESHOLD,
        "pass_to_human": pass_human or mode == "hold_no_facts",
        "mode": mode,
        "reasons": reasons,
        "scenario": scenario,
        "lookup": lookup,
    }


def format_facts_only(atoms: list, standing: Optional[dict] = None, cap: int = FACTS_ONLY_CAP) -> str:
    """Short emission: only facts the stack has. Plain sentences, no jargon dump."""
    standing = standing or {}
    clauses = []

    # Prefer human labels over internal matter codes when we can
    if standing.get("label"):
        clauses.append(str(standing["label"]))
    elif standing.get("matter"):
        mc = str(standing["matter"])
        if "OP-PETITION" in mc.upper():
            clauses.append("OP petition")
        elif "ARTA" in mc.upper():
            m = re.search(r"(\d{4})$", mc)
            clauses.append(f"ARTA CTN {m.group(1)}" if m else "ARTA matter")
        else:
            clauses.append(mc.replace("MWK-", "").replace("-", " "))

    if standing.get("filed_on"):
        clauses.append(f"filed {standing['filed_on']}")
    if standing.get("stage"):
        st = str(standing["stage"]).replace("_", " ")
        clauses.append(st)

    order = ["mro_ref", "docket", "ctn", "tct", "oct", "e_title", "tax_dec", "date"]
    by_kind: dict[str, list[str]] = {}
    for a in atoms or []:
        k = a.get("atom_kind") or "other"
        v = (a.get("value_norm") or "").strip()
        if not v:
            continue
        by_kind.setdefault(k, [])
        if v not in by_kind[k]:
            by_kind[k].append(v)

    if by_kind.get("mro_ref"):
        clauses.append("Malacañang ref " + ", ".join(by_kind["mro_ref"][:2]))
    if by_kind.get("docket"):
        clauses.append(", ".join(by_kind["docket"][:2]))
    if by_kind.get("ctn"):
        # Few distinct full CTNs → answer with them in full; the 4-digit tail
        # alone is a non-answer when the asker already used the tail to ask.
        full = sorted({
            v for v in by_kind["ctn"]
            if re.fullmatch(r"20\d{2}-\d{4}-\d{3,4}", v)
        })
        if 1 <= len(full) <= 3:
            clauses.append("CTN " + ", ".join(full))
        else:
            shorts = []
            for v in by_kind["ctn"][:4]:
                m = re.search(r"(\d{4})$", v)
                code = m.group(1) if m else v
                if code not in shorts:
                    shorts.append(code)
            clauses.append("ARTA " + ", ".join(shorts))
    if by_kind.get("tct"):
        clauses.append("title " + ", ".join(by_kind["tct"][:2]))
    if by_kind.get("oct"):
        clauses.append("OCT " + ", ".join(by_kind["oct"][:2]))
    if by_kind.get("tax_dec"):
        clauses.append("tax " + ", ".join(by_kind["tax_dec"][:2]))

    if not clauses:
        return "I don't have a clear fact on that yet. Flagging for human review."

    # One plain sentence
    text = "; ".join(clauses) + "."
    if not text[0].isupper():
        text = text[0].upper() + text[1:]
    if len(text) > cap:
        text = text[: cap - 1].rsplit(" ", 1)[0] + "…"
    return text


def format_human_pass_bundle(decision: dict, facts_text: str) -> str:
    """Escalate without sounding robotic: facts, then a plain handoff."""
    # Client-facing: no scores, no "pass_to_human" jargon
    base = (facts_text or "").rstrip(".")
    if not base:
        base = "I have limited facts on this"
    text = f"{base}. I'll flag this for human review before recommending next steps."
    if len(text) > 280:
        text = base[:200].rstrip(".") + ". Flagged for human review."
    return text


def decide_emission(
    message: str,
    atoms: list,
    *,
    standing: Optional[dict] = None,
    n_verified_in_scope: int = 0,
    clarity_unclear: bool = False,
    open_contradictions: int = 0,
    n_matters_touched: int = 1,
    law_gap: bool = False,
    expectation_at_stake: bool = False,
    hard_lookup_hit: bool = False,
    operator_channel: bool = False,
) -> dict:
    """Full decision for inquiry/Leo.

    Returns:
      mode: facts_only | pass_to_human | hold_no_facts
      text: what to send (or hold payload)
      decision: score breakdown
      pass_to_human: bool
    """
    decision = score_inquiry(
        message,
        atoms=atoms,
        n_verified_in_scope=n_verified_in_scope,
        clarity_unclear=clarity_unclear,
        open_contradictions=open_contradictions,
        n_matters_touched=n_matters_touched,
        law_gap=law_gap,
        expectation_at_stake=expectation_at_stake,
        hard_lookup_hit=hard_lookup_hit,
    )
    facts_text = format_facts_only(atoms, standing=standing)

    if decision["mode"] == "facts_only":
        return {
            "mode": "facts_only",
            "text": facts_text,
            "pass_to_human": False,
            "decision": decision,
        }

    if decision["mode"] == "hold_no_facts":
        text = "I don't have a clear fact on that yet. Flagging for human review."
        return {
            "mode": "hold_no_facts",
            "text": text,
            "pass_to_human": True,
            "decision": decision,
        }

    # pass_to_human: still show facts we have; do not invent strategy
    text = format_human_pass_bundle(decision, facts_text)
    if operator_channel:
        text += f" [score {decision['score']}/{decision['threshold']}]"
    return {
        "mode": "pass_to_human",
        "text": text[:280],
        "pass_to_human": True,
        "decision": decision,
    }
