#!/usr/bin/env python3
"""dossier_fix.py — the SELF-HEAL loop. Verify the dossier, FIX what the diligence gate flags,
re-verify, and repeat until clean or no further progress — so the stack catches AND resolves its own
defects (like a paralegal), instead of just handing back a list. $0, deterministic.

Auto-fixes:
  ACRONYM   → strip the (possibly invented) parenthetical expansion, keep the bare acronym
  NAME      → replace the variant with the verified canonical spelling
  CITATION  → strip a parenthetical reference to an un-grounded statute
  SOURCE(missing|notext) → drop the bad entry from the Document index
  SOURCE(draft)          → repoint the index link to the received/stamped twin
  MATTER    → drop the cross-matter (client-separation) entry from the Document index
Anything not SAFELY auto-fixable is left in place and reported for human judgment — a paralegal
escalates the judgment calls too; we don't paper over them.

  python3 scripts/dossier_fix.py 1891_output/synth_v2.md [--matter MWK] [--inplace|--out PATH] [--max 3]
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dossier_verify as dv


def _drop_index_line(md, doc_id):
    return re.sub(rf"(?m)^[-*] .*?/files/c/{doc_id}\).*$\n?", "", md)


def apply_fix(md, it):
    """Return (new_md, fixed). fixed=False means it is not safely auto-fixable → leave for a human."""
    c = it["cat"]
    if c == "ACRONYM":
        return re.sub(rf"\b{re.escape(it['acr'])}\b\s*\(\s*{re.escape(it['exp'])}\s*\)", it["acr"], md), True
    if c == "NAME":
        return md.replace(it["found"], it["canon"]), True
    if c == "MATTER":
        return _drop_index_line(md, it["doc_id"]), True
    if c == "SOURCE":
        if it.get("kind") in ("missing", "notext"):
            return _drop_index_line(md, it["doc_id"]), True
        if it.get("kind") == "draft" and it.get("twin"):
            return md.replace(f"/files/c/{it['doc_id']})", f"/files/c/{it['twin']})"), True
    if c == "CITATION":
        n = it["act"]
        new = re.sub(rf"\s*\((?:a\s+)?(?:violation of\s+)?(?:R\.?\s?A\.?|P\.?\s?D\.?)\s*(?:No\.?\s*)?{n}\)", "", md)
        if new != md:
            return new, True
    return md, False


def heal(md, matter=None, max_iters=3):
    log = []
    for it_no in range(1, max_iters + 1):
        issues = dv.verify_text(md, matter)
        if not issues:
            log.append(f"iteration {it_no}: CLEAN")
            break
        fixed_any = False
        for it in issues:
            new_md, ok = apply_fix(md, it)
            if ok and new_md != md:
                md, fixed_any = new_md, True
                log.append(f"iteration {it_no}: fixed [{it['cat']}] — {it['msg'][:72]}")
        if not fixed_any:
            log.append(f"iteration {it_no}: remaining issues need human judgment (not auto-fixable)")
            break
    return md, log, dv.verify_text(md, matter)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: dossier_fix.py dossier.md [--matter PREFIX] [--inplace|--out PATH] [--max N]")
    md_path = sys.argv[1]
    matter = sys.argv[sys.argv.index("--matter") + 1] if "--matter" in sys.argv else None
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 3
    healed, log, final = heal(open(md_path).read(), matter, mx)
    out = (md_path if "--inplace" in sys.argv else
           (sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else md_path.replace(".md", "_healed.md")))
    open(out, "w").write(healed)
    print(f"=== SELF-HEAL — {os.path.basename(md_path)} ===")
    for line in log:
        print("  ·", line)
    print(f"  → wrote {out}")
    if final:
        print(f"  ⚠ {len(final)} issue(s) remain for human judgment:")
        for it in final:
            print("     -", it["msg"])
        sys.exit(1)
    print("  ✓ clean after self-heal.")
    sys.exit(0)


if __name__ == "__main__":
    main()
