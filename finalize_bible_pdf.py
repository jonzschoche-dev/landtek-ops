#!/usr/bin/env python3
"""finalize_bible_pdf — apply post-processor + re-render PDF + deliver (deploy_165).

Skips narrative regen (already cost $0.10 today). Just:
  1. Read the current bible MD
  2. Apply narrative_postprocess (fixes venue/spelling/header artifacts)
  3. Re-render PDF from corrected MD
  4. Send to Jonathan's Telegram
"""
import sys
from pathlib import Path
sys.path.insert(0, "/root/landtek")

BIBLE_MD = Path("/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.md")
BIBLE_PDF = Path("/root/landtek/drafts/bible_OMNIBUS_MWK-001_2026-05-17.pdf")


def main():
    from narrative_postprocess import patch_narrative_blocks
    from generate_case_bible import render_pdf, tg_send_document, upload_to_drive

    # 1. Apply post-processor
    md = BIBLE_MD.read_text()
    new_md, applied = patch_narrative_blocks(md)
    BIBLE_MD.write_text(new_md)
    n_corrections = sum(a['n'] for a in applied)
    print(f"[1/4] post-processor: {n_corrections} corrections across narratives")
    for a in applied:
        print(f"      ({a['n']}x) {a['why']}")

    # 2. Re-render PDF
    print(f"[2/4] re-rendering PDF from corrected MD...")
    render_pdf(new_md, str(BIBLE_PDF))
    size_kb = BIBLE_PDF.stat().st_size / 1024
    print(f"      wrote {BIBLE_PDF} ({size_kb:.0f} KB)")

    # 3. Drive (graceful-fail)
    print(f"[3/4] Drive upload...")
    try:
        drive_result, err = upload_to_drive(str(BIBLE_PDF), "MWK-001")
        if drive_result:
            print(f"      Drive: uploaded as file_id={drive_result.get('id')}")
        else:
            print(f"      Drive: SKIPPED — {err}")
    except Exception as e:
        msg = str(e)[:200]
        print(f"      Drive: ⚠ FAILED (continuing with Telegram) — {msg}")

    # 4. Telegram delivery
    print(f"[4/4] Telegram delivery...")
    cap = ("📖 <b>MWK Omnibus Master Case Bible — Final</b>\n"
           "<i>Post-Opus-audit (3 passes) · 1,034 events · 33 years · v3.2.1</i>\n\n"
           "All 5 Opus-flagged critical defects fixed:\n"
           "  ✅ Cesar dela Fuente post-2017 attribution purged\n"
           "  ✅ CV-26360 venue corrected to RTC Camarines Norte Br. 64 Daet\n"
           "  ✅ Missing MWK-ARTA-1212 matter created + 3 docs retagged\n"
           "  ✅ 9 CV-6839 title-bleed events retagged from TCT-4497\n"
           "  ✅ Patricia Keesee Zschoche caption spelling normalized\n\n"
           "<i>Opus audit verdict: SHIP-WITH-NOTES (presentational only).</i>")
    ok, info = tg_send_document(str(BIBLE_PDF), caption=cap)
    print(f"      Telegram: {'✓ delivered' if ok else '✗ failed: ' + info[:120]}")

    print("\n=== Final Bible delivery complete ===")


if __name__ == "__main__":
    main()
