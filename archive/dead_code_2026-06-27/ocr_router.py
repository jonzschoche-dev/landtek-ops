#!/usr/bin/env python3
"""ocr_router.py — score-based routing for the OCR attack.

Decides per-doc whether to upload the raw PDF to the OCR engine, or to run the
Optimizer (ocr_preprocess.py) first and upload preprocessed PNG variants. The
routing rule is a property of the document, not of the operator's memory.

Routing bands (default thresholds — overridable via env):
    score >= 0.50         → 'raw'             upload the original PDF
    0.20 <= score < 0.50  → 'blue'            preprocess + upload blue-channel PNG
    score < 0.20          → 'blue+gray'       preprocess BOTH; upload to two engines, merge
    score IS NULL         → 'gray_hidpi'      preprocess at higher DPI; upload to vision engine
                                                (images / never-OCR'd scans)

The router is invoked by `ocr_browser_adapter.py --next-ocr` (per integration
patch authored alongside this module). Each doc in the returned worklist now
arrives pre-routed: the staged PNG paths already exist on disk when score < 0.50,
so the operator's loop is identical regardless of doc complexity.

CLI (designer-side smoke testing; executor uses the imported `route()` function):

  python3 scripts/ocr_router.py --doc 87 --score 0.16 --filename "TCT-4503.pdf"
  python3 scripts/ocr_router.py --doc 246 --score 0.07 --filename "SPA.pdf"
  python3 scripts/ocr_router.py --doc 246 --score 0.07 --filename "SPA.pdf" --no-preprocess

Standing rule (per MASTER_PLAN §5A — to be amended per
drafts/MASTER_PLAN_amendment_ocr_router.md): the router output is canonical.
No silent overrides of the routing decision — operator's --no-preprocess flag
must be visible in the staged manifest.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
STAGING_ROOT = REPO_ROOT / "drafts" / "ocr_staging"

# Thresholds (overridable via env so tuning doesn't require a code change)
SCORE_RAW_FLOOR = float(os.environ.get("OCR_ROUTER_RAW_FLOOR", "0.50"))
SCORE_BLUE_FLOOR = float(os.environ.get("OCR_ROUTER_BLUE_FLOOR", "0.20"))
GRAY_HIDPI = int(os.environ.get("OCR_ROUTER_GRAY_HIDPI", "450"))


def route(
    doc_id: int,
    score: Optional[float],
    filename: Optional[str] = None,
    repo_root: Path = REPO_ROOT,
    no_preprocess: bool = False,
    run_preprocess: bool = True,
) -> dict:
    """Decide routing + (optionally) invoke the Optimizer.

    Returns a plan dict:
      {
        "doc_id": int,
        "score": float|None,
        "band": "raw"|"blue"|"blue+gray"|"gray_hidpi",
        "needs_preprocess": bool,
        "preprocess_invoked": bool,
        "variants": ["blue", "gray", ...] or [],
        "dpi": int,
        "staged_dir": "drafts/ocr_staging/<doc_id>",
        "staged_paths": ["drafts/ocr_staging/<doc_id>/page_NN_blue.png", ...] or None,
        "reason": "human-readable explanation",
        "override_applied": "no_preprocess"|None,
      }

    Idempotent: if staged PNGs already exist for this (doc, variants, DPI), they
    are reused and `preprocess_invoked` is False.
    """
    plan = {
        "doc_id": doc_id,
        "score": score,
        "band": None,
        "needs_preprocess": False,
        "preprocess_invoked": False,
        "variants": [],
        "dpi": 300,
        "staged_dir": str((STAGING_ROOT / str(doc_id)).relative_to(repo_root)),
        "staged_paths": None,
        "reason": "",
        "override_applied": None,
    }

    # Override path — operator explicitly disabled preprocessing
    if no_preprocess:
        plan["band"] = "raw"
        plan["reason"] = "operator override --no-preprocess; raw upload regardless of score"
        plan["override_applied"] = "no_preprocess"
        return plan

    # Band selection
    if score is None:
        plan["band"] = "gray_hidpi"
        plan["needs_preprocess"] = True
        plan["variants"] = ["gray"]
        plan["dpi"] = GRAY_HIDPI
        plan["reason"] = (
            "score IS NULL (likely image / never-OCR'd scan); preprocess gray @"
            f" {GRAY_HIDPI} DPI then upload to vision engine"
        )
    elif score >= SCORE_RAW_FLOOR:
        plan["band"] = "raw"
        plan["reason"] = (
            f"score {score:.2f} >= {SCORE_RAW_FLOOR:.2f} floor; upload raw PDF "
            "(clean modern CTC path)"
        )
    elif score >= SCORE_BLUE_FLOOR:
        plan["band"] = "blue"
        plan["needs_preprocess"] = True
        plan["variants"] = ["blue"]
        plan["reason"] = (
            f"score {score:.2f} in [{SCORE_BLUE_FLOOR:.2f}, {SCORE_RAW_FLOOR:.2f}); "
            "old paper title CTC — blue-channel isolation suppresses yellowed paper + "
            "red/black cancellation stamps"
        )
    else:
        plan["band"] = "blue+gray"
        plan["needs_preprocess"] = True
        plan["variants"] = ["blue", "gray"]
        plan["reason"] = (
            f"score {score:.2f} < {SCORE_BLUE_FLOOR:.2f}; worst tier — produce BOTH variants "
            "for parallel-engine + merge"
        )

    # Invoke the Optimizer if needed (idempotent — ocr_preprocess.py skips existing files)
    if plan["needs_preprocess"] and run_preprocess:
        out_dir = STAGING_ROOT / str(doc_id)
        # Check idempotency: are the expected variant files already present?
        existing = []
        if out_dir.is_dir():
            for v in plan["variants"]:
                existing.extend(sorted(out_dir.glob(f"page_*_{v}.png")))
        if existing:
            plan["staged_paths"] = [str(p.relative_to(repo_root)) for p in existing]
            plan["preprocess_invoked"] = False
            plan["reason"] += " (staged PNGs already exist; reused)"
        else:
            # Subprocess invoke so the router stays decoupled from PIL/fitz imports
            cmd = [
                sys.executable,
                str(repo_root / "scripts" / "ocr_preprocess.py"),
                "--doc", str(doc_id),
                "--variants", ",".join(plan["variants"]),
                "--dpi", str(plan["dpi"]),
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if res.returncode != 0:
                    plan["reason"] += (
                        f" | ocr_preprocess.py FAILED rc={res.returncode}: "
                        f"{(res.stderr or res.stdout)[:200]}"
                    )
                else:
                    plan["preprocess_invoked"] = True
                    # Collect produced paths
                    produced = []
                    if out_dir.is_dir():
                        for v in plan["variants"]:
                            produced.extend(sorted(out_dir.glob(f"page_*_{v}.png")))
                    plan["staged_paths"] = [str(p.relative_to(repo_root)) for p in produced]
            except subprocess.TimeoutExpired:
                plan["reason"] += " | ocr_preprocess.py TIMEOUT (120s)"
            except Exception as e:
                plan["reason"] += f" | ocr_preprocess.py raised {type(e).__name__}: {e}"

    return plan


def _cli():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--doc", type=int, required=True)
    ap.add_argument("--score", type=float, default=None,
                    help="ocr_quality.score for this doc (omit to test the NULL/no_text path)")
    ap.add_argument("--filename", default=None, help="for display only")
    ap.add_argument("--no-preprocess", action="store_true",
                    help="operator override; always route 'raw'")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute the plan but do not invoke ocr_preprocess.py")
    args = ap.parse_args()

    plan = route(
        doc_id=args.doc,
        score=args.score,
        filename=args.filename,
        no_preprocess=args.no_preprocess,
        run_preprocess=not args.dry_run,
    )
    print(json.dumps(plan, indent=2, default=str))
    # Exit code: 0 if a sensible plan was produced (raw or staged files exist)
    if plan["band"] == "raw":
        sys.exit(0)
    if plan["needs_preprocess"] and plan.get("staged_paths"):
        sys.exit(0)
    if args.dry_run:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    _cli()
