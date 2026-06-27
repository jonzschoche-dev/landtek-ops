#!/usr/bin/env python3
"""ocr_path_matcher.py — designer-lane module: tiered local-path matcher for
the OCR worklist generator (case_work/OCR_WORKLIST.md producer).

Goal: grow 162/341 matched toward ~280+ by handling filename variations,
sub-folders, and content-hash matches. Category-A (gmail attachments / messenger
hashes) and Category-B (empty original_filename) are NOT addressed here — those
need separate fetch designs.

Designed to be imported by the existing worklist generator. The generator passes
each pending doc through `match_doc(original_filename, drive_file_id, index)`
and gets back (relative_path, strategy_name) or (None, None).

Build the index ONCE per generator run:
    from ocr_path_matcher import build_index, match_doc
    index = build_index("/Users/jonathanzschoche/Library/CloudStorage/GoogleDrive-jonathan@hayuma.org/My Drive/LANDTEK ")
    path, strat = match_doc(doc_row["original_filename"], doc_row.get("drive_file_id"), index)

The strategy name is recorded so we can MEASURE matcher improvement:
record per-doc which strategy hit. After integration, executor can report
"matcher improvement: exact=120, case_ci=8, normalized=22, stem=15, fuzzy=9 → 174/341 matched."

Strategies in order (first hit wins):
  1. exact          — original_filename matches a file basename verbatim
  2. case_ci        — case-insensitive basename match
  3. normalized     — punctuation/whitespace-collapsed basename match
  4. stem_strip     — strip common suffixes (' (1)', '_v2', '-final', '-edit',
                      '-copy', date-suffix) then re-match
  5. drive_id       — drive_file_id lookup in a side-mapping (if executor seeds one)
  6. extless        — match without file extension (catches .PDF vs .pdf)
  7. substring      — basename contains-or-contained-by (length-aware)
  8. fuzzy          — difflib.get_close_matches, cutoff=0.86 (last resort, tight)

The matcher returns the FIRST hit only — never tries multiple paths. If multiple
files normalize to the same key, picks shortest path (heuristic: shorter usually
== canonical; renames sit deeper in archive/backup subdirs).
"""
from __future__ import annotations

import difflib
import os
import re
from pathlib import Path
from typing import Optional


# ─── Normalization helpers ───────────────────────────────────────────────────

_PUNCT_RX = re.compile(r"[\s_\-\.()[\]{}]+")
_STEM_SUFFIX_RX = re.compile(
    r"(?:\s*\(\d+\)|\s*-\s*copy(?:\s*\d+)?|\s*-\s*v\d+|"
    r"\s*-\s*final|\s*-\s*edit|\s*-\s*revised?|"
    r"\s*-\s*\d{4}[-_]\d{2}[-_]\d{2}|"
    r"\s*_\s*v\d+|\s*_\s*\d{8}|\s*_\s*signed)",
    re.IGNORECASE,
)
# extra spaces, normalized
_WS_RX = re.compile(r"\s+")


def _basename_no_ext(p: str) -> str:
    return Path(p).stem


def _norm(s: str) -> str:
    """Punctuation-collapsed, lowercased, whitespace-normalized."""
    if not s:
        return ""
    s = s.casefold()
    s = _PUNCT_RX.sub(" ", s)
    s = _WS_RX.sub(" ", s).strip()
    return s


def _stem_strip(s: str) -> str:
    """Strip common rename suffixes (' (1)', '_v2', '-final', date suffix, etc.)."""
    if not s:
        return s
    prev = None
    cur = s
    while cur != prev:
        prev = cur
        cur = _STEM_SUFFIX_RX.sub("", cur).strip()
    return cur


# ─── Index build ─────────────────────────────────────────────────────────────


def build_index(base_dir: str) -> dict:
    """Walk `base_dir` once. Return a multi-key index for fast tiered lookup.

    Index shape:
      {
        "by_exact_basename":      {basename: [relative_path, ...]},
        "by_case_ci_basename":    {basename.casefold(): [paths]},
        "by_norm_basename":       {normalized_basename: [paths]},
        "by_norm_stem":           {normalized_stem_stripped: [paths]},
        "by_norm_extless":        {normalized basename without extension: [paths]},
        "all_paths":              [relative_path, ...],
        "all_basenames":          [basename, ...],
        "base_dir":               base_dir,
      }

    Multiple files mapping to the same key → list. Pick shortest at match time.
    Skips hidden, .DS_Store, common metadata. Skips files >0 bytes only.
    """
    base = Path(base_dir).expanduser()
    if not base.is_dir():
        raise FileNotFoundError(f"base_dir not found: {base}")

    by_exact: dict[str, list[str]] = {}
    by_case_ci: dict[str, list[str]] = {}
    by_norm: dict[str, list[str]] = {}
    by_norm_stem: dict[str, list[str]] = {}
    by_norm_extless: dict[str, list[str]] = {}
    all_paths: list[str] = []
    all_basenames: list[str] = []

    SKIP_EXTS = {".ds_store", ".cfg", ".lock", ".tmp"}
    SKIP_NAMES = {".ds_store", "icon\r", "thumbs.db", ".trash"}

    for root, dirs, files in os.walk(base):
        # skip hidden dirs in place (don't recurse into them)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() != "__macosx"]
        for fn in files:
            if fn.startswith(".") or fn.lower() in SKIP_NAMES:
                continue
            ext = Path(fn).suffix.lower()
            if ext in SKIP_EXTS:
                continue
            full = Path(root) / fn
            try:
                if full.stat().st_size == 0:
                    continue
            except OSError:
                continue
            rel = str(full.relative_to(base))

            all_paths.append(rel)
            all_basenames.append(fn)
            by_exact.setdefault(fn, []).append(rel)
            by_case_ci.setdefault(fn.casefold(), []).append(rel)

            n = _norm(fn)
            if n:
                by_norm.setdefault(n, []).append(rel)
            stem_n = _norm(_stem_strip(_basename_no_ext(fn)))
            if stem_n:
                by_norm_stem.setdefault(stem_n, []).append(rel)
            extless_n = _norm(_basename_no_ext(fn))
            if extless_n:
                by_norm_extless.setdefault(extless_n, []).append(rel)

    return {
        "by_exact_basename": by_exact,
        "by_case_ci_basename": by_case_ci,
        "by_norm_basename": by_norm,
        "by_norm_stem": by_norm_stem,
        "by_norm_extless": by_norm_extless,
        "all_paths": all_paths,
        "all_basenames": all_basenames,
        "base_dir": str(base),
    }


# ─── Match ────────────────────────────────────────────────────────────────────


def _shortest(candidates: list[str]) -> str:
    """Of multiple matches, return the shortest path (heuristic: canonical not archive)."""
    return min(candidates, key=lambda p: (len(p), p))


def match_doc(
    original_filename: Optional[str],
    drive_file_id: Optional[str],
    index: dict,
    drive_id_map: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Return (relative_path, strategy_name) or (None, None) if no match.

    `drive_id_map` is an optional {drive_file_id: relative_path} dict the executor
    can pass for category-D recovery via Drive metadata.
    """
    if not original_filename:
        # Category B — designer-lane matcher cannot help.
        if drive_file_id and drive_id_map and drive_file_id in drive_id_map:
            return (drive_id_map[drive_file_id], "drive_id")
        return (None, None)

    fn = original_filename.strip()
    if not fn:
        return (None, None)

    # 1. exact
    if fn in index["by_exact_basename"]:
        return (_shortest(index["by_exact_basename"][fn]), "exact")

    # 2. case-insensitive
    fn_ci = fn.casefold()
    if fn_ci in index["by_case_ci_basename"]:
        return (_shortest(index["by_case_ci_basename"][fn_ci]), "case_ci")

    # 3. normalized (punctuation/whitespace collapsed)
    fn_norm = _norm(fn)
    if fn_norm and fn_norm in index["by_norm_basename"]:
        return (_shortest(index["by_norm_basename"][fn_norm]), "normalized")

    # 4. stem-stripped (strip ' (1)', '_v2', '-final', etc.)
    fn_stem = _norm(_stem_strip(_basename_no_ext(fn)))
    if fn_stem and fn_stem in index["by_norm_stem"]:
        return (_shortest(index["by_norm_stem"][fn_stem]), "stem_strip")

    # 5. drive_file_id lookup (executor-supplied side-table)
    if drive_file_id and drive_id_map and drive_file_id in drive_id_map:
        return (drive_id_map[drive_file_id], "drive_id")

    # 6. extension-less basename match
    fn_extless = _norm(_basename_no_ext(fn))
    if fn_extless and fn_extless in index["by_norm_extless"]:
        return (_shortest(index["by_norm_extless"][fn_extless]), "extless")

    # 7. substring (length-aware: requires a meaningful overlap, not just shared word)
    if fn_extless and len(fn_extless) >= 12:
        for key, paths in index["by_norm_extless"].items():
            if not key:
                continue
            if fn_extless in key or key in fn_extless:
                shorter, longer = sorted([fn_extless, key], key=len)
                # require at least 80% of the shorter to be inside the longer
                if len(shorter) / max(len(longer), 1) >= 0.80:
                    return (_shortest(paths), "substring")

    # 8. fuzzy (tight cutoff — last resort)
    if fn_extless and len(fn_extless) >= 8:
        cands = difflib.get_close_matches(
            fn_extless, list(index["by_norm_extless"].keys()), n=1, cutoff=0.86
        )
        if cands:
            return (_shortest(index["by_norm_extless"][cands[0]]), "fuzzy")

    return (None, None)


# ─── Measurement helpers ─────────────────────────────────────────────────────


def stats(results: list[tuple[Optional[str], Optional[str]]]) -> dict:
    """Given a list of (path, strategy) from match_doc calls, return per-strategy counts.

    Lets executor measure matcher improvement vs the deploy_475 baseline (162/341 exact-only).
    """
    counts: dict[str, int] = {}
    matched = 0
    for path, strat in results:
        if path:
            matched += 1
            counts[strat or "unknown"] = counts.get(strat or "unknown", 0) + 1
    return {"matched": matched, "by_strategy": counts}


# ─── CLI: standalone sanity check (designer convenience; executor runs the real pipeline) ───


def _cli():
    import argparse, json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", required=True, help="LANDTEK base dir to index")
    ap.add_argument("--name", help="single filename to test-match")
    ap.add_argument("--names-file", help="newline-separated filenames to test-match")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()
    idx = build_index(args.base)
    if args.name:
        result = match_doc(args.name, None, idx)
        print(json.dumps({"name": args.name, "path": result[0], "strategy": result[1]}, indent=2))
        return
    if args.names_file:
        with open(args.names_file) as f:
            names = [l.strip() for l in f if l.strip()]
        results = []
        for n in names:
            p, s = match_doc(n, None, idx)
            results.append({"name": n, "path": p, "strategy": s})
        if args.json:
            print(json.dumps({"results": results, "stats": stats([(r["path"], r["strategy"]) for r in results])}, indent=2))
        else:
            for r in results:
                mark = "✓" if r["path"] else "✗"
                print(f"  {mark} [{r['strategy'] or '-':<11}] {r['name']}  →  {r['path'] or '(no match)'}")
            st = stats([(r["path"], r["strategy"]) for r in results])
            print(f"\n  total: {st['matched']}/{len(results)} matched")
            print(f"  by strategy: {st['by_strategy']}")
        return
    print("error: pass --name or --names-file (see --help)")


if __name__ == "__main__":
    _cli()
