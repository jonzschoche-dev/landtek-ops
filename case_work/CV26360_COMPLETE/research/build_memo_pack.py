"""Bind the memorandum pack for Atty. Barandon: a 14-pt action cover, then one annex per action
(the draft first, then the supporting pages), each with a divider listing its contents and every page
stamped with its annex, page and source. 8.5 x 13.

Run:  python3 research/build_memo_pack.py
"""
import fitz, subprocess, os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
LT = os.path.dirname(os.path.dirname(ROOT))
DL = os.path.join(LT, "drive_local")
TI = os.path.join(DL, "01 - Clients", "Heirs of Mary Worrick Keesey- LTC-002", "Evidence", "Transfer Investigation")
PACK = os.path.join(ROOT, "MEMO_PACK_2026-10-15")
W, H = 612, 936
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

RD_SALE = os.path.join(TI, "Balane Supporting Docs.partition.titles.pdf")   # certified Registry file Ref. 2025001098
ANSWER = os.path.join(DL, "Answer with Special and Affirmative Defenses and Compulsory Counterclaim.pdf")
DEF5 = os.path.join(DL, "Exhibit 5 - Receipts.pdf")
DEF7 = os.path.join(DL, "Exhibit 7 - Special Power of Attorney dated March 16, 1992.pdf")
EX = lambda n: os.path.join(DL, n)


def html(path):
    out = os.path.join(BASE, "_pack_" + os.path.basename(path).replace(".html", ".pdf"))
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", "file://" + path], check=True, capture_output=True)
    return out


def without_part6(pdf_path):
    d = fitz.open(pdf_path)
    keep = next((i for i, p in enumerate(d) if "Part 6. Draft for counsel" in p.get_text()), d.page_count)
    out = os.path.join(BASE, "_pack_plan_no_part6.pdf")
    o = fitz.open(); o.insert_pdf(d, from_page=0, to_page=keep - 1); o.save(out)
    return out


def allpages(path):
    return list(range(1, fitz.open(path).page_count + 1))


ANNEXES = [
 dict(id="A", title="How this unfolds: the record, the lock-in, the trap", action="The strategy · read first", parts=[
   ("Trap map: why the rules allow it; our case-in-chief; the stages; quiet gathering; the traps claim by claim; risks", html(os.path.join(PACK, "05_TRAP_MAP.html")), None),
 ]),
 dict(id="B", title="Quiet gathering: my written requests", action="Action 1 · now to 27 November", parts=[
   ("My requests to the Registry of Deeds and the Clerk of Court (partition agreement, notarial registers)", os.path.join(ROOT, "RD_OCC_REQUESTS_2026-10", "RD_OCC_REQUESTS_2026-10.pdf"), None),
 ]),
 dict(id="C", title="Completing Exhibits E and H; the 1991 SPA", action="Action 2 · at the 9 December offer", parts=[
   ("Exh. E as filed (two pages of the 1992 SPA)", EX("Exhibit E - Complaint - Civil Case No. 26-360.pdf"), None),
   ("Def. Exh. 7: the 1992 SPA complete, as the defense filed it", DEF7, None),
   ("Exh. H as filed (page 1 of 2)", EX("Exhibit H - Complaint - Civil Case No. 26-360.pdf"), None),
   ("Registry file Ref. 2025001098: the deed's page 2, with the eCAR (the missing page of Exh. H)", RD_SALE, [12]),
   ("Registry file pages 2 to 4: the 1991 SPA, administration only (Doc. 260/Pg. 53/Bk. I/1991, Makati)", RD_SALE, [2, 3, 4]),
   ("Exh. B, page 5: the 1991 SPA annotated on T-52540 on 10 Oct 2016", EX("Exhibit B to B-4 - Complaint - Civil Case No. 26-360.pdf"), [5]),
 ]),
 dict(id="D", title="Patricia Keesey Zschoche: rebuttal affidavit and her documents", action="Action 3 · her answers by 31 October", parts=[
   ("Filled draft judicial affidavit, with counsel's notes", html(os.path.join(ROOT, "PATRICIA_JUDICIAL_AFFIDAVIT_FILLED_DRAFT_2026-10-15.html")), None),
   ("Exh. F: the revocation of 15 Aug 2005", EX("Exhibit F - Complaint - Civil Case No. 26-360.pdf"), None),
   ("Exh. G: the Bicol Post notice, Sep to Oct 2020", EX("Exhibit G to G-1 - Complaint - Civil Case No. 26-360.pdf"), None),
   ("Exh. I, pages 1 to 2: her Affidavit of Adverse Claim, Feb 2023", EX("Exhibit I - Complaint - Civil Case No. 26-360.pdf"), [1, 2]),
   ("Her Affidavit of Loss, Feb 2023 (proposed Exh. O-1)", os.path.join(TI, "AFFIDAVIT OF LOSS P.Zschoche 22Feb2023.pdf"), None),
   ("Agcaoili & Associates letter of 15 Aug 2019 (proposed Exh. O-2)", os.path.join(TI, "Reply to JDavis CGrippo re CDelaFuente 15Aug2019.pdf"), None),
   ("Exh. A: her SPA to Jonathan, apostilled 12 Nov 2025", EX("Exhibit A - Complaint - Civil Case No. 26-360.pdf"), None),
 ]),
 dict(id="E", title="Briefing: how we win, the demurrer, the 9 December offer", action="Action 4 · 9 December", parts=[
   ("Briefing memo: priorities, the facts that decide it, what we do not argue, Judge Cu", html(os.path.join(PACK, "00_COVER_MEMO.html")), None),
   ("Proof plan: each element proved without Jonathan; admissibility; the T-52540 point; doors for rebuttal; calendar", html(os.path.join(ROOT, "OVERWHELM_PLAN_2026-10-14.html")), None),
   ("Focus sheet: the case on one page, Ramos's lines and the answers, statute spine, calendar", html(os.path.join(ROOT, "COUNSEL_FOCUS_SHEET_2026-10-14.html")), None),
 ]),
 dict(id="F", title="Lock-in on cross: checklist and the papers to show", action="Action 5 · 13 January to 10 March 2027", parts=[
   ("Checklist: Salvador, Princess, Erwin, Gloria; fact, question, what to show and what to hold", html(os.path.join(PACK, "04_CROSS_CHECKLIST.html")), None),
   ("Def. Exh. 5: survey receipt of 29 Dec 2006, \"owned by the Heirs\"", DEF5, [1]),
   ("Def. Exh. 5: first receipt, Oct 2003, signed \"Von dela Fuente\"", DEF5, [2]),
   ("Def. Exh. 5: \"Down payment\" receipt of 6 Jan 2005", DEF5, [3]),
   ("Def. Exh. 5: Receipt No. 0228, \"Full payment\", Feb 2017", DEF5, [33]),
   ("Answer, pages 4 to 7: rooms rented (par. 27), renters (pars. 40, 43), improvements (par. 49)", ANSWER, [4, 5, 6, 7]),
   ("Answer, Annex \"1\": Gloria's SPA of 28 May 2020", EX("Annex 1 - Special Power of Attorney .pdf"), [1, 2, 3]),
   ("Erwin H. Balane's judicial affidavit: \"first with Ben Llamanzares\"", EX("CV26360 - Trial Brief for Atty. Botor (2026-08-30)/C5 - Judicial Affidavit - Engr. Erwin H. Balane (defense).pdf"), [1]),
   ("Def. Exh. 7, page 1: Registry copy obtained for Gloria in August 2021", DEF7, [1]),
   ("Exh. C, page 2: survey 8 Sep 2020, approved 6 Apr 2021", EX("Exhibit C to C-1 - Complaint - Civil Case No. 26-360.pdf"), [2]),
 ]),
 dict(id="G", title="Rebuttal: the records held back, and the subpoena request to rework", action="Action 6 · after 10 March 2027", parts=[
   ("Registry file: Gloria's SPA to Elevado of 15 Sep 2021, \"my property\" (her admission)", RD_SALE, [20]),
   ("Registry file: Cesar's Deed of Confirmation of 28 Mar 2017 (the agent confirming himself)", RD_SALE, [16]),
   ("Exh. B, page 6: Entry 2021003236, the partition dated 15 Mar 2017 (Doc. 402/Pg. 81/Bk. CXXII)", EX("Exhibit B to B-4 - Complaint - Civil Case No. 26-360.pdf"), [6]),
   ("T-4497, page 13: Cesar's 1993 Subdivision Agreement entry naming his buyers; no Balane",  os.path.join(BASE, "src", "T4497_CTC_doc25.pdf"), [13]),
   ("Draft subpoena request: to be reworked for rebuttal, filed after the defense rests", os.path.join(ROOT, "SUBPOENA_REQUEST_2026-10", "SUBPOENA_REQUEST_2026-10.pdf"), None),
 ]),
 dict(id="H", title="War of the Statutes (reference)", action="Reference", parts=[
   ("War of the Statutes", os.path.join(ROOT, "WAR_OF_THE_STATUTES_2026-10.pdf"), None),
 ]),
]


def clean(s):
    return (s.replace("–", "-").replace("—", "-").replace("₱", "P").replace("“", '"').replace("”", '"')
             .replace("‘", "'").replace("’", "'").replace("…", "...").replace("§", "s.").replace("¶", "par."))


out = fitz.open()
cover = fitz.open(html(os.path.join(PACK, "00_ACTION_COVER.html")))
out.insert_pdf(cover)
for i in range(cover.page_count):
    pg = out[i]
    pg.insert_text((54, H - 14), f"Memorandum pack, Civil Case No. 26-360  ·  Actions for counsel  ·  p. {i + 1} of {cover.page_count}",
                   fontsize=7.2, fontname="helv", color=(.3, .3, .3))
toc = [[1, "Actions for counsel (cover)", 1]]


def normalize(src, idx):
    sp = src[idx]
    r = sp.rect
    sw, sh = (r.height, r.width) if sp.rotation in (90, 270) else (r.width, r.height)
    np_ = out.new_page(width=W, height=H)
    top, bot = 18, 34
    s = min((W - 24) / sw, (H - top - bot) / sh)
    tw, th = sw * s, sh * s
    x0 = (W - tw) / 2
    y0 = top + (H - top - bot - th) / 2
    np_.show_pdf_page(fitz.Rect(x0, y0, x0 + tw, y0 + th), src, idx, rotate=0)
    return np_


for a in ANNEXES:
    parts = [(lbl, path, pages if pages else allpages(path)) for lbl, path, pages in a["parts"]]
    total = sum(len(p[2]) for p in parts)
    d = out.new_page(width=W, height=H)
    start = out.page_count
    d.insert_text((54, 110), clean(a["action"]).upper(), fontsize=10, fontname="hebo", color=(.35, .35, .35))
    d.insert_text((54, 152), f"ANNEX {a['id']}", fontsize=34, fontname="tibo")
    d.draw_rect(fitz.Rect(54, 164, W - 54, 168), color=(0, 0, 0), fill=(0, 0, 0))
    d.insert_textbox(fitz.Rect(54, 182, W - 54, 250), clean(a["title"]), fontsize=17, fontname="tibo")
    y = 262
    d.insert_text((54, y), "CONTENTS", fontsize=9, fontname="hebo", color=(.35, .35, .35))
    y += 16
    k = 1
    for lbl, path, pages in parts:
        rng = f"{k}" if len(pages) == 1 else f"{k}-{k + len(pages) - 1}"
        line = f"pp. {rng}   {clean(lbl)}"
        h = 18 if len(line) < 78 else (34 if len(line) < 156 else 50)
        d.insert_textbox(fitz.Rect(54, y, W - 54, y + h + 4), line, fontsize=12, fontname="tiro")
        y += h + 4
        k += len(pages)
    d.insert_text((54, H - 14), f"Annex {a['id']} divider  ·  Memorandum pack, Civil Case No. 26-360  ·  15 October 2026",
                  fontsize=7.2, fontname="helv", color=(.3, .3, .3))
    k = 1
    for lbl, path, pages in parts:
        src = fitz.open(path)
        for pnum in pages:
            if not 1 <= pnum <= src.page_count:
                raise SystemExit(f"Annex {a['id']}: page {pnum} out of range in {path}")
            np_ = normalize(src, pnum - 1)
            np_.draw_rect(fitz.Rect(0, H - 28, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 13), clean(f"ANNEX {a['id']}  ·  p. {k} of {total}  ·  {lbl[:70]}, p. {pnum}  ·  Civil Case No. 26-360"),
                            fontsize=7, fontname="helv", color=(.25, .25, .25))
            k += 1
    toc.append([1, f"Annex {a['id']}: {a['title']}", start])

out.set_toc(toc)
out.set_metadata({"title": "Civil Case No. 26-360: actions for counsel, with annexes, 15 October 2026", "author": "", "subject": "for counsel; not filed"})
dest = os.path.join(ROOT, "MEMO_PACK_BARANDON_2026-10-15.pdf")
out.rewrite_images(dpi_threshold=160, dpi_target=140, quality=62, lossy=True, lossless=True)
out.save(dest, garbage=4, deflate=True)
print(out.page_count, "pp", {(round(p.rect.width), round(p.rect.height)) for p in out}, os.path.getsize(dest) // 1024, "KB")
for t in toc:
    print(t[2], t[1])
