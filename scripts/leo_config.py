#!/usr/bin/env python3
"""leo_config.py — leo_config@N: the versioned, swappable Leo (TRUTH_LAYER_FITNESS_SPEC.md Part II, A1/A2).

A config is a JSON body with EXACTLY seven sections. Only the knobs listed in SCHEMA are tunable; everything
else a candidate might want to touch is either a constitutional floor (lives in code/DB gates ABOVE the config:
provenance write-gate, answer gate, stack-first inquiry gate, A5/A25 isolation, A21 outward chokepoint, A79
role clamp) or not yet wired (held fixed — a candidate that changes it is refused, not silently ignored).

Validation runs at PARSE time: a candidate that fails is rejected before any evaluation. The DB repeats the
floor check (leo_config_no_floor_keys) so the rule does not depend on this file.

  validate(body)           -> list of violations ([] = acceptable)
  config_hash(body)        -> content address (sha256 of canonical JSON)
  load_active(cur, dflt)   -> (body, hash) of the active row; falls back to dflt on any problem (degrade)
"""
import copy
import hashlib
import json
import re

SECTIONS = ("prompt_set", "tool_manifest", "retrieval_params", "routing", "model_selection",
            "memory_context_assembly", "recipient_projection")

# Tunable leaves: (type, min, max) for numbers, type for the rest. Anything not here is refused.
SCHEMA = {
    "prompt_set": {"system": str},
    "model_selection": {"model": str, "temperature": (float, 0.0, 1.0), "seed": (int, 0, 2**31 - 1)},
    "retrieval_params": {"facts_hit_limit": (int, 1, 50), "facts_recent_limit": (int, 0, 50),
                         "facts_total": (int, 1, 60), "facts_fallback_limit": (int, 1, 50)},
    "memory_context_assembly": {"recent_turns": (int, 0, 40)},
    "routing": {"mprb_brief": bool},
    "tool_manifest": {"exposed": list},
    "recipient_projection": {"strip_fluff": bool},
}
NULLABLE = {("model_selection", "seed")}

# Sections whose knobs are recorded but NOT wired into the running assistant yet: a candidate may not change
# them (a change would be an unmeasurable no-op dressed up as an improvement).
FIXED_SECTIONS = ("tool_manifest",)

# Names that ARE the constitutional floors (A2). Mirrors the DB CHECK leo_config_no_floor_keys.
FLOOR_KEY_RE = re.compile(r"^(answer_gate|outward_guard|client_of|provenance\w*|send\w*|test_identities|"
                          r"inquiry_gate|stack_first|role_clamp|channel_mode|a5|a21|a25|a79)$", re.I)

# The grounding clause every system prompt must keep, and wording that would talk the model past the gates.
REQUIRED_PROMPT_CLAUSES = ("never invent",)
WEAKENING_RE = re.compile(r"(ignore (the )?(gate|rules|grounding|facts below)|you may (guess|speculate|invent)|"
                          r"without (a )?(citation|grounding)|make up|fill in (any )?gaps)", re.I)
# Offline-sovereignty floor: the reply brain is local. A metered/remote model is refused.
REMOTE_MODEL_RE = re.compile(r"(claude|gpt|gemini|anthropic|openai|o\d-|mistral-large|command-r)", re.I)


def canonical(body):
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_hash(body):
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_keys(v)


def validate(body, baseline=None):
    """Parse-time gate. Returns a list of violations; [] means the body may be stored/evaluated.
    `baseline` (the default/active body) is used to hold FIXED_SECTIONS constant."""
    errs = []
    if not isinstance(body, dict):
        return ["config body must be a JSON object"]
    for k in _walk_keys(body):
        if FLOOR_KEY_RE.match(str(k)):
            errs.append(f"floor: '{k}' is a constitutional floor — not candidate-controllable (A2)")
    keys = set(body)
    if keys != set(SECTIONS):
        missing, extra = set(SECTIONS) - keys, keys - set(SECTIONS)
        if missing:
            errs.append(f"missing section(s): {sorted(missing)}")
        if extra:
            errs.append(f"unknown section(s): {sorted(extra)}")
    for sec, leaves in SCHEMA.items():
        got = body.get(sec)
        if not isinstance(got, dict):
            errs.append(f"{sec}: must be an object")
            continue
        for leaf in set(got) - set(leaves):
            errs.append(f"{sec}.{leaf}: not a tunable knob")
        for leaf, spec in leaves.items():
            if leaf not in got:
                errs.append(f"{sec}.{leaf}: missing")
                continue
            v = got[leaf]
            if v is None and (sec, leaf) in NULLABLE:
                continue
            if isinstance(spec, tuple):
                typ, lo, hi = spec
                ok = isinstance(v, (int, float)) and not isinstance(v, bool) if typ is float else \
                    isinstance(v, int) and not isinstance(v, bool)
                if not ok or not (lo <= v <= hi):
                    errs.append(f"{sec}.{leaf}: must be {typ.__name__} in [{lo}, {hi}] (got {v!r})")
            elif not isinstance(v, spec):
                errs.append(f"{sec}.{leaf}: must be {spec.__name__}")
    system = ((body.get("prompt_set") or {}).get("system") or "")
    for clause in REQUIRED_PROMPT_CLAUSES:
        if clause not in system.lower():
            errs.append(f"floor: prompt_set.system must keep the grounding clause '{clause}'")
    if WEAKENING_RE.search(system):
        errs.append("floor: prompt_set.system contains wording that weakens the grounding gates")
    model = ((body.get("model_selection") or {}).get("model") or "")
    if REMOTE_MODEL_RE.search(model):
        errs.append(f"floor: model '{model}' is a metered/remote model — the reply brain stays local")
    if baseline is not None:
        for sec in FIXED_SECTIONS:
            if body.get(sec) != baseline.get(sec):
                errs.append(f"{sec}: not wired into the running assistant yet — held fixed")
    return errs


def merge(base, patch):
    """Deep-merge a partial patch onto a full body (the way candidates are proposed)."""
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def diff(a, b, prefix=""):
    """Leaf-level diff a→b as {path: [old, new]}."""
    out = {}
    for k in sorted(set(a or {}) | set(b or {})):
        va, vb = (a or {}).get(k), (b or {}).get(k)
        path = f"{prefix}{k}"
        if isinstance(va, dict) and isinstance(vb, dict):
            out.update(diff(va, vb, path + "."))
        elif va != vb:
            out[path] = [va, vb]
    return out


def load_active(cur, default):
    """The running assistant's config. No table / no active row / invalid body → the default.
    Degrade, never crash the reply path."""
    # to_regclass never raises, so a missing table can't abort the caller's transaction.
    cur.execute("SELECT to_regclass('public.leo_config') IS NOT NULL AS ok")
    r = cur.fetchone()
    if not (r["ok"] if isinstance(r, dict) else r[0]):
        return default, None
    cur.execute("SELECT body, config_hash FROM leo_config WHERE active LIMIT 1")
    r = cur.fetchone()
    if not r:
        return default, None
    body = r["body"] if isinstance(r, dict) else r[0]
    h = r["config_hash"] if isinstance(r, dict) else r[1]
    if validate(body):
        return default, None
    return body, h
