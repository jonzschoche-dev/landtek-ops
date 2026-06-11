#!/usr/bin/env python3
"""Test the corpus by running real questions through Leo's actual answer pipeline
(tools + client scoping + truth discipline) — without sending anything to Telegram."""
import os, sys
for _line in open("/root/landtek/.env"):
    _line = _line.strip()
    if "=" in _line and not _line.startswith("#"):
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
sys.path.insert(0, "/root/landtek")
from landtek_telegram.handlers import llm

matters = llm._live_matters_block()
vault = llm._live_vault_state()
SYSP = llm.SYSTEM_PROMPT_PRIVATE_JONATHAN_TEMPLATE.format(
    matters_block=matters, vault_state_block=vault)

QUESTIONS = [
    "Who are the registered owners of the mother title TCT T-4497?",
    "Explain, with the source documents, why Gloria Balane's title is void.",
    "When exactly was Cesar de la Fuente's SPA revoked, and which document proves it?",
    "Is TCT T-30683 (Manguisoc) part of the Civil Case 26-360 matter, or a separate property?",
    "Do we have Patricia Keesey's 1947 birth certificate and the executed disinterested-person affidavits for her delayed birth registration? Give download links.",
    "What do we have on the Labo Civil Case No. 4992?",
]

for i, q in enumerate(QUESTIONS, 1):
    print(f"\n{'='*78}\nQ{i}: {q}\n{'-'*78}")
    try:
        reply, err = llm._call_anthropic(SYSP, q, [])
        print(reply or f"(no reply; err={err})")
    except Exception as e:
        print(f"(handler error: {type(e).__name__}: {e})")
