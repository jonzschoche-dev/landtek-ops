#!/usr/bin/env python3
"""finalize_bible_pdf — re-render PDF from existing MD + optional delivery.

Skips narrative regen (already cost ~$0.10 in the original producer run). Just:
  1. Read the current bible MD
  2. Apply narrative_postprocess (fixes venue/spelling/header artifacts)
  3. Re-render PDF from corrected MD
  4. (optional) Drive upload
  5. (optional) Telegram delivery

Usage:
  python3 finalize_bible_pdf.py --md path/to/bible.md              # render only
  python3 finalize_bible_pdf.py --md path/to/bible.md --tg         # render + Telegram
  python3 finalize_bible_pdf.py --md path/to/bible.md --drive --tg # full delivery
  python3 finalize_bible_pdf.py --md ... --case Paracale-001       # client-aware caption
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

# Per-client caption tail. Lookup by case_file.
CAPTION_TAIL = {
    "MWK-001":      "Mary Worrick Keesey estate — Civil Case 26-360 + ARTA + CV-6839 tracks",
    "Paracale-001": "Allan V. Inocalla — Paracale matters (Capacuan, Vito Cruz, TCT-1616, etc.)",
    "Owner":        "Owner File — personal/family record",
}


def infer_case_file(md_path: Path) -> str:
    n = md_path.name
    if "Paracale" in n or "PAR" in n:
        return "Paracale-001"
    if "Owner" in n:
        return "Owner"
    return "MWK-001"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", required=True, help="Path to bible MD")
    ap.add_argument("--case", default=None, help="case_file override")
    ap.add_argument("--drive", action="store_true", help="Upload to Drive")
    ap.add_argument("--tg", action="store_true", help="Send to Jonathan's Telegram")
    ap.add_argument("--no-postprocess", action="store_true",
                    help="Skip narrative post-processor (use MD as-is)")
    args = ap.parse_args()

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"✗ MD not found: {md_path}"); sys.exit(2)
    pdf_path = md_path.with_suffix(".pdf")
    case_file = args.case or infer_case_file(md_path)

    from generate_case_bible import render_pdf

    # 1. Optional post-processor
    md = md_path.read_text()
    if not args.no_postprocess:
        try:
            from narrative_postprocess import patch_narrative_blocks
            md, applied = patch_narrative_blocks(md)
            md_path.write_text(md)
            n_corrections = sum(a['n'] for a in applied)
            print(f"[1/3] post-processor: {n_corrections} corrections")
        except Exception as e:
            print(f"[1/3] post-processor skipped: {e}")
    else:
        print("[1/3] post-processor: skipped (--no-postprocess)")

    # 2. Re-render PDF
    print(f"[2/3] rendering PDF from {md_path.name}...")
    render_pdf(md, str(pdf_path))
    size_kb = pdf_path.stat().st_size / 1024
    print(f"      wrote {pdf_path} ({size_kb:.0f} KB)")

    # 3. Optional delivery
    if args.drive:
        try:
            from generate_case_bible import upload_to_drive
            drive_result, err = upload_to_drive(str(pdf_path), case_file)
            if drive_result:
                print(f"[3a] Drive: uploaded as file_id={drive_result.get('id')}")
            else:
                print(f"[3a] Drive: SKIPPED — {err}")
        except Exception as e:
            print(f"[3a] Drive: ⚠ FAILED — {str(e)[:200]}")
    if args.tg:
        try:
            from generate_case_bible import tg_send_document
            tail = CAPTION_TAIL.get(case_file, case_file)
            cap = (f"📖 <b>Bible: {md_path.stem.replace('_', ' ')}</b>\n"
                   f"<i>{tail}</i>\n"
                   f"<i>Generated {md_path.stem.split('_')[-1]} · {size_kb:.0f} KB</i>")
            ok, info = tg_send_document(str(pdf_path), caption=cap)
            print(f"[3b] Telegram: {'✓ delivered' if ok else '✗ failed: ' + str(info)[:120]}")
        except Exception as e:
            print(f"[3b] Telegram: ⚠ FAILED — {str(e)[:200]}")

    print(f"\n✓ Done. PDF at: {pdf_path}")


if __name__ == "__main__":
    main()
