"""Bind the memorandum pack for Atty. Barandon, in order of priority.

Cover memo -> Tab 1 Request for Admission -> Tab 2 Motion for Production -> Tab 3 Subpoena request
-> Tab 4 Focus sheet -> Tab 5 Proof plan (overwhelm plan without its Part 6, which is Tab 1)
-> Tab 6 Patricia rebuttal affidavit draft -> Tab 7 War of the Statutes.
Every page carries a footer: pack name, tab, page within tab. 8.5 x 13.

Run:  python3 research/build_memo_pack.py
"""
import fitz, subprocess, os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
PACK = os.path.join(ROOT, "MEMO_PACK_2026-10-15")
W, H = 612, 936
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def html2pdf(html):
    out = os.path.join(BASE, "_pack_" + os.path.basename(html).replace(".html", ".pdf"))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", "file://" + html], check=True, capture_output=True)
    return fitz.open(out)


def without_part6(doc):
    """Drop the pages from the one that starts Part 6 (the request-for-admission draft) to the end."""
    keep = doc.page_count
    for i, p in enumerate(doc):
        if "Part 6. Draft for counsel" in p.get_text():
            keep = i
            break
    out = fitz.open()
    out.insert_pdf(doc, from_page=0, to_page=keep - 1)
    return out


TABS = [
    (1, "Request for Admission (Rule 26)", "PRIORITY 1 · File by 21 October",
     "Eighteen items, each deemed admitted unless denied under oath within fifteen days. Draft for counsel's signature.",
     lambda: html2pdf(os.path.join(PACK, "02_REQUEST_FOR_ADMISSION.html"))),
    (2, "Motion for Production and Inspection (Rule 27)", "PRIORITY 1 · File by 21 October",
     "Llamanzares papers they claim, the receipt books, the room-rental records, the improvement costs and permits, the owner's duplicate of TCT 079-2021002127. Draft for counsel's signature.",
     lambda: html2pdf(os.path.join(PACK, "03_MOTION_FOR_PRODUCTION.html"))),
    (3, "Request for subpoenas, ten custodians", "PRIORITY 1 · File by 21 October",
     "Returnable 2 December 2026. Draft for counsel's signature.",
     lambda: fitz.open(os.path.join(ROOT, "SUBPOENA_REQUEST_2026-10", "SUBPOENA_REQUEST_2026-10.pdf"))),
    (4, "Focus sheet", "PRIORITY 2 · How we win",
     "The case in one line, the order of argument, decisions, the statute spine with exhibit pages, Ramos's lines and the answers, the calendar.",
     lambda: html2pdf(os.path.join(ROOT, "COUNSEL_FOCUS_SHEET_2026-10-14.html"))),
    (5, "Proof plan", "PRIORITY 2 · How we win",
     "The demurrer; each element proved twice without Jonathan; what each piece of proof can and cannot do; the T-52540 point; the doors for rebuttal; the calendar to 2027.",
     lambda: without_part6(html2pdf(os.path.join(ROOT, "OVERWHELM_PLAN_2026-10-14.html")))),
    (6, "Draft judicial affidavit of Patricia Keesey Zschoche (rebuttal)", "PRIORITY 3 · Rebuttal",
     "Forty-three questions; her answers to be given in her own words at the examination; counsel's notes on separate pages.",
     lambda: html2pdf(os.path.join(ROOT, "PATRICIA_JUDICIAL_AFFIDAVIT_DRAFT_2026-10-14.html"))),
    (7, "War of the Statutes", "REFERENCE",
     "Each provision both sides will cite, with the exhibit that fits it and the expected result.",
     lambda: fitz.open(os.path.join(ROOT, "WAR_OF_THE_STATUTES_2026-10.pdf"))),
]

out = fitz.open()
cover = html2pdf(os.path.join(PACK, "00_COVER_MEMO.html"))
out.insert_pdf(cover)
for i in range(cover.page_count):
    pg = out[i]
    pg.draw_rect(fitz.Rect(0, H - 26, W, H), color=(1, 1, 1), fill=(1, 1, 1))
    pg.insert_text((54, H - 12), f"Memorandum pack, Civil Case No. 26-360  ·  Cover memo  ·  p. {i + 1} of {cover.page_count}  ·  15 October 2026",
                   fontsize=7.2, fontname="helv", color=(.3, .3, .3))
toc = [[1, "Cover memo: priorities after 14 October", 1]]

for n, title, pri, why, loader in TABS:
    d = out.new_page(width=W, height=H)
    start = out.page_count
    d.insert_text((54, 120), pri, fontsize=10, fontname="hebo", color=(.35, .35, .35))
    d.insert_text((54, 160), f"TAB {n}", fontsize=34, fontname="tibo")
    d.draw_rect(fitz.Rect(54, 172, W - 54, 176), color=(0, 0, 0), fill=(0, 0, 0))
    d.insert_textbox(fitz.Rect(54, 192, W - 54, 260), title, fontsize=17, fontname="tibo")
    d.insert_textbox(fitz.Rect(54, 262, W - 54, 400), why, fontsize=12.5, fontname="tiro")
    src = loader()
    first = out.page_count
    out.insert_pdf(src)
    total = src.page_count
    for k in range(total):
        pg = out[first + k]
        pg.draw_rect(fitz.Rect(0, H - 26, W, H), color=(1, 1, 1), fill=(1, 1, 1))
        pg.insert_text((54, H - 12), f"Memorandum pack, Civil Case No. 26-360  ·  Tab {n}: {title[:60]}  ·  p. {k + 1} of {total}",
                       fontsize=7.2, fontname="helv", color=(.3, .3, .3))
    toc.append([1, f"Tab {n}: {title}", start])

out.set_toc(toc)
out.set_metadata({"title": "Civil Case No. 26-360: memorandum pack for counsel, 15 October 2026", "author": "", "subject": "for counsel; not filed"})
dest = os.path.join(ROOT, "MEMO_PACK_BARANDON_2026-10-15.pdf")
out.save(dest, garbage=4, deflate=True)
print(out.page_count, "pp", {(round(p.rect.width), round(p.rect.height)) for p in out}, os.path.getsize(dest) // 1024, "KB")
for t in toc:
    print(t[2], t[1])
