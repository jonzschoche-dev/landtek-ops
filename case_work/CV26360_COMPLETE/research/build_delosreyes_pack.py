"""Build the evidence pack for Francia Abad de los Reyes (Exh. M), next setting (likely 11 Nov 2026).
Brief (00_BRIEF.html -> PDF via Chrome) + 14 tabs, each a divider page then the source pages,
every page stamped with tab and source page. Output: DELOSREYES_PACK_2026-11/DELOSREYES_EVIDENCE_PACK_2026-11.pdf

  python3 research/build_delosreyes_pack.py
"""
import fitz, os, subprocess

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "DELOSREYES_PACK_2026-11"); os.makedirs(OUT, exist_ok=True)
W, H = 612, 936
DL = "/Users/jonathanzschoche/landtek/drive_local/"
LTC = DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
F = {
 "EXM": DL + "Exhibit M - Complaint - Civil Case No. 26-360.pdf",
 "EXP": DL + "Exhibit P - Complaint - Civil Case No. 26-360.pdf",
 "KJA": LTC + "Legal/Tortilla vs KING etc malicious prosecution.pdf",
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
LABEL = {"EXM": "Exh. M", "EXP": "Exh. P", "KJA": "CC 8563 judicial affidavits (King side)", "EXC": "Exh. C", "EXG": "Exh. G", "K8563": "CC 8563 record (King's copy)",
         "CAPET": "CA-G.R. SP 181607 petition annexes", "CAD": "CA decision file", "CARES": "CA resolution 4 Dec 2025",
         "WARR": "warrant order image", "A1": "Answer Annex 1", "ANS": "Answer"}
# (tab title, description, [(key, [pages])])  pages 1-based
TABS = [
 ("Exhibit M: judicial affidavit of Francia Abad de los Reyes", "Sworn 23 Jan 2026. Her direct testimony. Withdraw Q2 to Q3, the 'kasama na ang mga defendants' clause of Q4, the second sentence of Q7, Q8 and Q9, if she is called.", [("EXM", [1, 2, 3, 4, 5])]),
 ("Exhibit P: her Philippine ID", "Identity and residence, Purok 3, Brgy. San Roque.", [("EXP", [1])]),
 ("Exhibit C: TCT 079-2021002126 and technical description", "The lot in suit, for any location question.", [("EXC", [1, 2])]),
 ("Their Answer, p. 5 (para. 40)", "Occupation since 1975 as renters paying rent through Violeta: fits her fish-drying account.", [("ANS", [5])]),
 ("Her affidavit of 1 July 2020", "Annexed to Mrs. King's prosecutor complaint. Her 2020 sworn account; civil status stated as married. Counsel's hand: prior statement.", [("KJA", [40, 41, 42, 43, 44])]),
 ("Her judicial affidavit in Civil Case 8563 (July 2021)", "Her 2021 sworn account; civil status stated as single; the newspaper. Counsel's hand: prior statement.", [("KJA", [70, 71, 72, 73, 74, 75, 76])]),
 ("Civil Case 8563: caption, paras. 5 and 11, verification", "Co-defendant with Mrs. King (captioned 'Francia Delos Santos'); the tires taken to her property; her signature on the verification. Counsel's hand: bias questions.", [("K8563", [1, 2, 3, 14, 15])]),
 ("Provincial Prosecutor: Joint Resolution, 28 Jul 2020", "Juntilla's robbery and grave threats complaint against 'Francia de Villa' and others, dismissed; the ownership ruling. Counsel's hand: bias questions.", [("CAPET", list(range(54, 63)))]),
 ("Mrs. King's complaint-affidavit, 10 Nov 2020, pp. 2 to 5", "Francia as the 'concerned neighbor and friend' who called on 27 and 30 May 2020; the meeting at the mayor's office. Counsel's hand.", [("K8563", [38, 39, 40, 41])]),
 ("Barangay San Roque certification, 27 May 2020", "The 27 May 2020 incident as recorded. Counsel's hand.", [("K8563", [24])]),
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
    dp.insert_text((54, H - 20), f"DE LOS REYES PACK · Tab {i} · divider · Civil Case No. 26-360 · prepared for counsel", fontsize=7, fontname="helv", color=(.4, .4, .4))
    k = 1; total = sum(len(pp) for _, pp in parts)
    for key, pages in parts:
        src = open_src(key)
        for pg in pages:
            if not (1 <= pg <= src.page_count): raise SystemExit(f"tab {i}: page {pg} out of range for {key} ({src.page_count})")
            np_ = show(out, src, pg - 1)
            np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 14), f"DE LOS REYES PACK  ·  TAB {i}  ·  p. {k} of {total}  ·  source: {LABEL[key]}, p. {pg}  ·  Civil Case No. 26-360  ·  prepared for counsel", fontsize=7.2, fontname="helv", color=(.25, .25, .25))
            k += 1
out.set_toc(toc)
dst = os.path.join(OUT, "DELOSREYES_EVIDENCE_PACK_2026-11.pdf")
out.save(dst, garbage=4, deflate=True)
print(dst, out.page_count, "pp", round(os.path.getsize(dst) / 1e6, 1), "MB")
