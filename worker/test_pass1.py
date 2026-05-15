"""Smoke test for Pass 1 OCR + XML normalizer.

Run from /root/landtek/worker/:
    python3 test_pass1.py [optional_pdf_path]

If no path given, processes everything in /root/landtek/inbox/.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ocr import pass1


def main():
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
    else:
        inbox = Path("/root/landtek/inbox")
        targets = sorted(list(inbox.glob("*.pdf")) + list(inbox.glob("*.PDF")))
    print(f"Found {len(targets)} PDF(s)")
    if not targets:
        print("No PDFs to process. Drop some into /root/landtek/inbox/ first.")
        return
    for pdf in targets:
        print(f"\n{'='*72}\n{pdf.name}\n{'='*72}")
        try:
            result = pass1(str(pdf))
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
            import traceback; traceback.print_exc()
            continue
        print(f"  pages: {result['page_count']}")
        print(f"  avg_confidence: {result['average_confidence']}")
        print(f"  extraction methods: {result['extraction_method_counts']}")
        print(f"  block counts: {result['block_counts']}")
        print(f"  needs_review_pages: {result['needs_review_pages']}")
        print(f"  file_hash: {result['file_hash']}")
        # Save XML to /root/landtek/pass1_out/<filename>.xml for inspection
        out_dir = Path("/root/landtek/pass1_out"); out_dir.mkdir(exist_ok=True)
        out_file = out_dir / (pdf.stem + ".xml")
        out_file.write_text(result["xml"])
        print(f"  full xml -> {out_file} ({len(result['xml'])} chars)")
        # Print head + tail
        xml = result["xml"]
        print("\n--- XML (first 1500 chars) ---")
        print(xml[:1500])
        if len(xml) > 3000:
            print("\n--- XML (last 1000 chars) ---")
            print(xml[-1000:])


if __name__ == "__main__":
    main()
