"""Build the evidence pack for Donata Mabeza King (Exh. L), 4 Nov 2026.
Brief (00_BRIEF.html -> PDF via Chrome) + 14 tabs, each a divider page then the source pages,
every page stamped with tab and source page. Output: KING_PACK_2026-11-04/KING_EVIDENCE_PACK_2026-11-04.pdf

  python3 research/build_king_pack.py
"""
import fitz, os, subprocess

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "KING_PACK_2026-11-04"); os.makedirs(OUT, exist_ok=True)
W, H = 612, 936
DL = "/Users/jonathanzschoche/landtek/drive_local/"
LTC = DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
F = {
 "EXL": DL + "Exhibit L - Complaint - Civil Case No. 26-360.pdf",
 "EXQ": DL + "Exhibit Q - Complaint - Civil Case No. 26-360.pdf",
 "EXC": DL + "Exhibit C to C-1 - Complaint - Civil Case No. 26-360.pdf",
 "EXG": DL + "Exhibit G to G-1 - Complaint - Civil Case No. 26-360.pdf",
 "K8563": LTC + "_Needs Review/Civil case 8563 for Damages  malicious prosecutions.pdf",
 "CAPET": LTC + "Legal/Court of appeals petition for centriari.pdf",
 "CAD": LTC + "Legal/Donata King Criminal vs people of the Philippines court of appeals.pdf",
 "CARES": BASE + "/src/CA_resolution_2025-12-04_doc775.pdf",
 "WARR": LTC + "Evidence/Transfer Investigation/History of Transactions/Supporting Docs/IMG-20201215-WA0010.jpg",
 "A1": DL + "Annex 1 - Special Power of Attorney .pdf",
 "ANS": DL + "Answer with Special and Affirmative Defenses and Compulsory Counterclaim.pdf",
}
LABEL = {"EXL": "Exh. L", "EXQ": "Exh. Q", "EXC": "Exh. C", "EXG": "Exh. G", "K8563": "CC 8563 record (King's copy)",
         "CAPET": "CA-G.R. SP 181607 petition annexes", "CAD": "CA decision file", "CARES": "CA resolution 4 Dec 2025",
         "WARR": "warrant order image", "A1": "Answer Annex 1", "ANS": "Answer"}
# (tab title, description, [(key, [pages])])  pages 1-based
TABS = [
 ("Exhibit L: judicial affidavit of Donata Mabeza King", "Sworn 23 Jan 2026. Her direct testimony.", [("EXL", [1, 2, 3, 4])]),
 ("Exhibit Q: her Philippine ID", "Identity and residence, Road 2, Purok 4, Brgy. San Roque.", [("EXQ", [1])]),
 ("Exhibit C: TCT 079-2021002126 and technical description", "The lot in suit, for any location question.", [("EXC", [1, 2])]),
 ("Kasunduan, Ruby Ferrer to Spouses King, 18 May 2015", "The house between Nieves de Leon and Jocelyn Estayo, facing the Mercedes to Daet road; with the rights to the land it stands on. Counsel's hand: the Ferrer question.", [("K8563", [22])]),
 ("Verified Answer of Donata King et al., Civil Case 8563, RTC Br. 41", "8 Jul 2021. Para. 2: Cesar 'stripped of' authority 'way back in 2005'. RTC stamp (p. 1); 'RECEIVED ... AQUINO Law Office ... 09 JUL 2021' (p. 14); verification (p. 15).", [("K8563", list(range(1, 16)))]),
 ("Annexes 1 to 3 of that Answer: Bicol Post, 25 Sep and 2 Oct 2020 (9 Oct masthead)", "The notice of revocation as attached and served. The 9 Oct notice page is omitted here; read the notice text from Exh. G-1 (Tab 7).", [("K8563", [16, 17, 18, 19, 20])]),
 ("Exhibit G and G-1: affidavit of publication and the notice", "Pre-marked in our case. The text of the notice.", [("EXG", [1])]),
 ("Provincial Prosecutor: Joint Resolution, 28 Jul 2020", "'this Office cannot pass upon the issue of ownership ... Parties hereto are advised to file appropriate civil action'. Jomil 'acting on instructions of the owner ... Gloria Balane thru Nelly Juntilla' (p. 7).", [("CAPET", list(range(54, 63)))]),
 ("Provincial Prosecutor: Resolution on reconsideration, 16 Sep 2020", "Same ruling; the 11 Feb 2020 letter of counsel; copy furnished 'Complainant and Respondents', registry receipts of 23 Sep 2020 (p. 3).", [("CAPET", [63, 64, 65, 66])]),
 ("Crim. Case 20-6030, MTC Mercedes: warrant order (27 Nov 2020) and order (6 Jan 2021)", "Remanded to the prosecutor as prematurely filed; warrants recalled; bonds returned to the payor Jomil L. Torralba.", [("WARR", [1]), ("CAPET", [80, 81])]),
 ("Barangay San Roque blotter certifications, May to June 2020", "Entry 2763 (19 May 2020): Princess 'May usapin pa yan'; the May 2020 incidents. Rebuttal against Princess.", [("K8563", [23, 24, 25, 26])]),
 ("Complaint-affidavit of Donata King, 10 Nov 2020", "Her 2020 account. Counsel's hand only.", [("K8563", list(range(37, 45)))]),
 ("The perjury case: MTC Daet decision; RTC Br. 41 acquittal; Court of Appeals decision and resolution", "Convicted 17 May 2023; acquitted 25 Sep 2023; certiorari dismissed 17 Jul 2025; reconsideration denied 4 Dec 2025. Re-direct only if the charge is raised.", [("CAPET", list(range(30, 38))), ("CAPET", [28, 29]), ("CAD", list(range(2, 11))), ("CARES", [1, 2, 3])]),
 ("Their Answer: Annex 1 (Gloria's SPA to Nelly Juntilla, 28 May 2020); p. 9; p. 13", "Juntilla acts for Gloria on this property; Princess and Jomil to testify to no notice of dispute; Juntilla verifies the Answer as Gloria's attorney-in-fact.", [("A1", [1, 2, 3]), ("ANS", [9, 13])]),
]

def open_src(key):
    p = F[key]
    if p.lower().endswith((".jpg", ".jpeg", ".png")):
        img = fitz.open(p); pdf = fitz.open("pdf", img.convert_to_pdf()); return pdf
    return fitz.open(p)

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
    dp.insert_textbox(fitz.Rect(54, 380, W - 54, 640), desc, fontsize=13, fontname="tiro")
    dp.insert_text((54, H - 20), f"KING PACK · Tab {i} · divider · Civil Case No. 26-360 · prepared for counsel", fontsize=7, fontname="helv", color=(.4, .4, .4))
    k = 1; total = sum(len(pp) for _, pp in parts)
    for key, pages in parts:
        src = open_src(key)
        for pg in pages:
            if not (1 <= pg <= src.page_count): raise SystemExit(f"tab {i}: page {pg} out of range for {key} ({src.page_count})")
            np_ = show(out, src, pg - 1)
            np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 14), f"KING PACK  ·  TAB {i}  ·  p. {k} of {total}  ·  source: {LABEL[key]}, p. {pg}  ·  Civil Case No. 26-360  ·  prepared for counsel", fontsize=7.2, fontname="helv", color=(.25, .25, .25))
            k += 1
out.set_toc(toc)
dst = os.path.join(OUT, "KING_EVIDENCE_PACK_2026-11-04.pdf")
out.save(dst, garbage=4, deflate=True)
print(dst, out.page_count, "pp", round(os.path.getsize(dst) / 1e6, 1), "MB")
