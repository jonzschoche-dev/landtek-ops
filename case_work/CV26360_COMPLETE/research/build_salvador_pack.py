"""Build the evidence pack for Salvador Osum ("Von") dela Fuente (defense witness, Def. Exh. 5), 2027 defense stage.
Brief (00_BRIEF.html -> PDF via Chrome) + 11 tabs, each a divider page then the source pages,
every page stamped with tab and source page. Supplements CROSS_BINDERS_2026-10/CROSS_BINDER_SALVADOR_OSUM_DELA_FUENTE.pdf.
Output: SALVADOR_PACK_2027-01/SALVADOR_EVIDENCE_PACK_2027-01.pdf

  python3 research/build_salvador_pack.py
"""
import fitz, os, subprocess

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "SALVADOR_PACK_2027-01"); os.makedirs(OUT, exist_ok=True)
W, H = 612, 936
DL = "/Users/jonathanzschoche/landtek/drive_local/"
LTC = DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/"
TB = DL + "CV26360 - Trial Brief for Atty. Botor (2026-08-30)/"
TAX = LTC + "Finance/TAXES Municipal Assesor /"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
F = {
 "JAS": TB + "C3 - Judicial Affidavit - Salvador Osum Dela Fuente (defense).pdf",
 "SAL": BASE + "/src/SAL_drive_new_Letter_from_Salvador_Dela_Fuente.pdf",
 "EX7": DL + "Exhibit 7 - Special Power of Attorney dated March 16, 1992.pdf",
 "EX5": DL + "Exhibit 5 - Receipts.pdf",
 "TD": TAX + "HRS of  Mary Worrick Tax Declarations.pdf",
 "SOA": TAX + "do overScan Jan 2, 2025 at 5.45 PM.pdf",
 "D7": TB + "D7 - 2012 SPA Cesar de la Fuente to Salvador (Von) - the unauthorized sub-delegation, Art. 1892.pdf",
 "EXB": DL + "Exhibit B to B-4 - Complaint - Civil Case No. 26-360.pdf",
 "SP": LTC + "Correspondence/DAR Landbank/Scan Jun 17, 2025 at 3.30 PM.pdf",
 "JAG": TB + "C2 - Judicial Affidavit - Gloria H. Balane (EXCLUDED at pre-trial; admission motion pending).pdf",
 "EX6": DL + "Exhibit 6 - Deed of Absolute Sale.pdf",
}
LABEL = {"JAS": "Salvador JA", "SAL": "letter 25 Nov 2025", "EX7": "Def. Exh. 7", "EX5": "Def. Exh. 5",
         "TD": "heirs' tax declarations (scan 2 Jan 2025)", "SOA": "Treasurer SOA set (scan 2 Jan 2025)", "D7": "2012 paper",
         "EXB": "Exh. B", "SP": "SP 2156 docket", "JAG": "Gloria JA (tendered)", "EX6": "Def. Exh. 6"}
# (tab title, description, [(key, [pages])])  pages 1-based
TABS = [
 ("His judicial affidavit, sworn 1 April 2026", "S14 to S16 (the 1992 visit to Llamanzares); S19 to S22 (rent and partial payments; Exh. 5); S24 to S25 (amilyar); S29 ('ipinalakad na niya sa iba'); S31 ('Wala po').", [("JAS", [1, 2, 3, 4, 5, 6, 7])]),
 ("His letter of 25 November 2025, signed 'VON DELA FUENTE'", "p. 2: the class as he states it ('CONTRACT OF SALE issued by Benjamin Llamanzares' / 'RECEIPTS OF SALES signed by Benjamin Llamanzares'); 'Jonathan you branded me as a BAD GUY you know I never admit it.'", [("SAL", [1, 2])]),
 ("1992 SPA (Def. Exh. 7), p. 3", "Paragraphs 6 to 9: sale only to holders of Llamanzares contracts to sell or payers to him; after prior consultation.", [("EX7", [3])]),
 ("Def. Exh. 5: five receipts", "p. 2: October 2003, signed 'Von dela Fuente'. p. 3: 6 January 2005, 'Down payment'. p. 29: No. 0129, P40,000, 31 March 2016. p. 30: No. 0217, August 2016, first to write '2587'. p. 33: No. 0228, February 2017, 'Full payment'.", [("EX5", [2, 3, 29, 30, 33])]),
 ("Heirs' tax declarations of 28 April 2016", "ARP GR-2014-HH-07-001-00246, PIN 025-07-001-01-047: 2,587 sq m segregated 'PER LETTER REQUEST, SKETCH PLAN, COPY OF DEMAND LETTER AND SPA ALL SUBMITTED'; taxes under ORs 0033799 to 0033800; owners still the heirs. Then the remaining portion, PIN 025-07-001-01-004. Our scan of 2 Jan 2025 (family files, not from Von); obtain certified copies.", [("TD", [6, 11])]),
 ("Treasurer's statement of account, 31 July 2019", "PIN 025-07-001-01-004, Barangay I, 20,776 sq m, ARPs 001-00247 and 001-00252: every year 1994 to 2019 unpaid; total P794,154.73; signed Loida E. Macale. Our scan of 2 Jan 2025 (family files, not from Von); obtain a certified copy.", [("SOA", [1])]),
 ("The 29 February 2012 paper, Cesar to Salvador", "Notarized by Atty. Elaine Gay R. Belen. No owner signs it. Dated after the 15 August 2005 revocation.", [("D7", [1, 2])]),
 ("Exhibit B (T-52540), pp. 5 and 6", "Entry 2016002312: affidavit of loss by Cesar, Atty. Belen, 27 Sep 2016. Entry 2017000693: new owner's duplicate, 16 Mar 2017, on the RTC order of 30 Jan 2017. Entries 2021003235 and 2021003236: sale and partition, 23 Nov 2021.", [("EXB", [5, 6])]),
 ("SP 2156, RTC Branch 41: docket", "Petition of Cesar M. de la Fuente, counsel Atty. Elaine Gay R. Belen, filed 20 Oct 2016; order 30 Jan 2017; certificate of finality 13 Mar 2017.", [("SP", [1])]),
 ("CONDITIONAL. Gloria's original judicial affidavit, p. 10", "S53: 'si Atty. Elaine Belen po ang tumulong at nag-follow up sa mga dokumento para sa transfer.' Excluded at pre-trial; use only if admitted.", [("JAG", [10])]),
 ("Deed of Absolute Sale (Def. Exh. 6)", "p. 1: price 'in hand paid'. p. 2: eCARs of 19 Jun 2020 and 18 Nov 2021.", [("EX6", [1, 2])]),
]

def show(out, src, pg):
    sp = src[pg]; r = sp.rect; rot = sp.rotation
    sw, sh = (r.height, r.width) if rot in (90, 270) else (r.width, r.height)
    p = out.new_page(width=W, height=H)
    aw, ah = W - 24, H - 18 - 34; s = min(aw / sw, ah / sh); tw, th = sw * s, sh * s
    x0 = (W - tw) / 2; y0 = 18 + (ah - th) / 2
    p.show_pdf_page(fitz.Rect(x0, y0, x0 + tw, y0 + th), src, pg)
    return p

brief_html = os.path.join(OUT, "00_BRIEF.html"); brief_pdf = os.path.join(OUT, "00_BRIEF.pdf")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={brief_pdf}", f"file://{brief_html}"], capture_output=True)
out = fitz.open(); out.insert_pdf(fitz.open(brief_pdf))
toc = [[1, "Brief", 1]]
for i, (title, desc, parts) in enumerate(TABS, 1):
    dp = out.new_page(width=W, height=H); toc.append([1, f"Tab {i}. {title}", out.page_count])
    dp.insert_text((54, 120), f"TAB {i}", fontsize=30, fontname="tibo")
    dp.draw_rect(fitz.Rect(54, 132, W - 54, 136), color=(0, 0, 0), fill=(0, 0, 0))
    dp.insert_textbox(fitz.Rect(54, 160, W - 54, 360), title, fontsize=16, fontname="tibo")
    dp.insert_textbox(fitz.Rect(54, 380, W - 54, 700), desc, fontsize=13, fontname="tiro")
    dp.insert_text((54, H - 20), f"SALVADOR PACK · Tab {i} · divider · Civil Case No. 26-360 · prepared for counsel", fontsize=7, fontname="helv", color=(.4, .4, .4))
    k = 1; total = sum(len(pp) for _, pp in parts)
    for key, pages in parts:
        src = fitz.open(F[key])
        for pg in pages:
            if not (1 <= pg <= src.page_count): raise SystemExit(f"tab {i}: page {pg} out of range for {key} ({src.page_count})")
            np_ = show(out, src, pg - 1)
            np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 14), f"SALVADOR PACK  ·  TAB {i}  ·  p. {k} of {total}  ·  source: {LABEL[key]}, p. {pg}  ·  Civil Case No. 26-360  ·  prepared for counsel", fontsize=7.2, fontname="helv", color=(.25, .25, .25))
            k += 1
out.set_toc(toc)
dst = os.path.join(OUT, "SALVADOR_EVIDENCE_PACK_2027-01.pdf")
out.save(dst, garbage=4, deflate=True)
print(dst, out.page_count, "pp", round(os.path.getsize(dst) / 1e6, 1), "MB")
