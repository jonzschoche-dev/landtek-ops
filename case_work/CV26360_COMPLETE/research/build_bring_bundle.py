"""Bind the documents OUTSIDE the record that Jonathan carries to each trial date and produces only if asked.

Output: BRING_TO_COURT_BUNDLE_2026-10.pdf (8.5 x 13 in): cover sheet (HTML -> PDF via Chrome) + tabbed copies,
each tab with a divider (why it may come up / what to say) and every page stamped TAB n · p. k of N · source page.

Run:  python3 research/build_bring_bundle.py
"""
import fitz, subprocess, os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
LT = os.path.dirname(os.path.dirname(ROOT))
DL = os.path.join(LT, "drive_local")
MWK = os.path.join(DL, "01 - Clients", "Heirs of Mary Worrick Keesey- LTC-002")
TI = os.path.join(MWK, "Evidence", "Transfer Investigation")
W, H = 612, 936
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def clean(s):
    return (s.replace("–", "-").replace("—", "-").replace("₱", "P").replace("“", '"').replace("”", '"')
             .replace("‘", "'").replace("’", "'").replace("…", "...").replace("§", "s.").replace("¶", "par."))


TABS = [
    dict(id=1, title="Transfer Certificate of Title No. T-4497 (Heirs of Mary Worrick Keesey), Registry certified copy, 14 pp.",
         why="The 1992 SPA describes the undivided parcel under T-4497. Ramos may ask whether the power ever covered this lot.",
         say="The power of attorney describes the parcel under T-4497. This lot was carved out of it. (Do not say the SPA never covered the lot; the Registry carried the SPA onto T-52540 in 1996.)",
         parts=[dict(label="TCT T-4497 CTC (doc 25)", source=os.path.join(BASE, "src", "T4497_CTC_doc25.pdf"), pages=list(range(1, 15)))]),
    dict(id=2, title="Tax declarations in the heirs' name for the lot: ARP GR-2014-HH-07-001-00246 (PIN 025-07-001-01-047) and ARP 00247, 2 pp.",
         why="Exhibit D (Gloria's TD 00256) carries the same property index number 025-07-001-01-047. If asked who declared or paid taxes on the lot before 2023.",
         say="The lot stood on the Assessor's roll in the heirs' name until Gloria's declaration replaced it in 2023; the index number is the same.",
         parts=[dict(label="HRS of Mary Worrick Tax Declarations (doc 30)", source=os.path.join(MWK, "Finance", "TAXES Municipal Assesor ", "HRS of  Mary Worrick Tax Declarations.pdf"), pages=[6, 11])]),
    dict(id=3, title="Special Power of Attorney, Cesar M. de la Fuente to Salvador O. dela Fuente, 29 February 2012, 2 pp.",
         why="The receipts in Def. Exh. 5 are signed 'Von dela Fuente'. If asked who Von is or under what authority he signed.",
         say="The receipts are signed Von dela Fuente. This 2012 instrument is Cesar's own appointment of Salvador. The owners never appointed Salvador. (Stop there; the law of substitution is counsel's.)",
         parts=[dict(label="2012 SPA Cesar to Salvador (trial brief D7)", source=os.path.join(DL, "CV26360 - Trial Brief for Atty. Botor (2026-08-30)", "D7 - 2012 SPA Cesar de la Fuente to Salvador (Von) - the unauthorized sub-delegation, Art. 1892.pdf"), pages=[1, 2])]),
    dict(id=4, title="Letter of Salvador ('Von') dela Fuente to the plaintiff's representative, 25 November 2025, 2 pp.",
         why="If asked whether you have communicated with the de la Fuentes, or what Salvador has said about the sale and the owners.",
         say="He wrote to me on 25 November 2025. I have the letter with me. (Do not characterize it; counsel lays the foundation on Salvador's cross under Rule 132 s. 13.)",
         parts=[dict(label="Salvador letter 25 Nov 2025 (doc 1010)", source=os.path.join(BASE, "src", "SAL_drive_new_Letter_from_Salvador_Dela_Fuente.pdf"), pages=[1, 2])]),
    dict(id=5, title="Deed of Confirmation, Cesar M. de la Fuente, 28 March 2017 (Doc. 115/Page 23/Book CXXII, Asis), Registry certified copy Ref. 2022006350, with TCT T-38838, 6 pp.",
         why="If asked whether Cesar 'confirmed' the sale, or about the 2017 instruments and the 2017 owner's duplicate.",
         say="The Registry copy is dated 28 March 2017: after the 2005 revocation, after the 2016 deed, and after the petition for new duplicates. I know only what the page says.",
         parts=[dict(label="Deed of Confirmation CCV (doc 240)", source=os.path.join(TI, "Gloria Balane Fraud (4).pdf"), pages=[1]),
                dict(label="TCT T-38838 (doc 19, via compilation)", source=os.path.join(ROOT, "_superseded", "BAD_FAITH_CANDIDATES_2026-10.pdf"), pages=[99, 100, 101, 102, 103])]),
    dict(id=6, title="Registry of Deeds file of Entry No. 2021003235 (the sale), certified copy Ref. 2025001098, 25 pp: Elevado SPA, BIR eCAR (p. 12), tax clearance, the 15 September 2021 'my property' letter (p. 20), Deed of Confirmation (pp. 16, 25).",
         why="If asked how you know what was filed to register the sale, who processed it, or whether Exhibit H is complete (its page 2, the eCAR, is at p. 12 here).",
         say="These are the Registry's certified copies of the papers filed to register the sale. I obtained them from the Registry in 2025. (Carry the certified original; hand it to counsel, not to the witness stand, unless the court asks.)",
         parts=[dict(label="RD Ref. 2025001098 (doc 369)", source=os.path.join(TI, "Balane Supporting Docs.partition.titles.pdf"), pages=list(range(1, 26)))]),
    dict(id=7, title="Registry of Deeds file of Entry No. 2021003236 (the partition), certified copy Ref. 2025001096, 8 pp: subdivision plan PSD-E2020005406, 'SURVEYED: September 8, 2020'.",
         why="If asked about the 2020 survey or the partition. The Partition-Subdivision Agreement itself is not in this file; it has never been produced to the family.",
         say="The Registry file for the partition entry holds the plan, surveyed 8 September 2020 and approved 6 April 2021. The agreement the title cites is not in the file; we have asked for it.",
         parts=[dict(label="RD Ref. 2025001096 (doc 367)", source=os.path.join(TI, "Balane Supporting Docs.pdf"), pages=list(range(1, 9)))]),
    dict(id=8, title="Special Proceeding No. 2156, RTC Branch 41, Daet: Cesar's petition for new owner's duplicates (October 2016), selected pages, 17 pp.",
         why="If asked whether the owners knew of the sale, or how the 2017 owner's duplicate came to exist. The petition post-dates the deed and does not mention the sale.",
         say="Cesar petitioned for new owner's duplicates after he had signed the deed. The petition does not mention the sale. My mother was not told. (Say only what is on the page.)",
         parts=[dict(label="Spec. Proc. 2156 (doc 677)", source=os.path.join(TI, "Owners Duplicate Petition.pdf"), pages=[2, 3, 4, 5, 6, 7, 8, 10, 11, 27, 32, 41, 44, 45, 49, 52, 57])]),
    dict(id=9, title="Patricia Keesey Zschoche, Affidavit of Loss, 22 February 2023, and her letter to the Provincial Assessor of the same date, 4 pp.",
         why="Ramos may offer the affidavit of loss as the owners 'ratifying' the 2017 duplicate or the sale. The letter shows what the family asserted to the Assessor the same day.",
         say="The affidavit says the owner's duplicate was lost. It says nothing about any sale or partition. My mother will testify to what she meant.",
         parts=[dict(label="Affidavit of Loss 22 Feb 2023 (doc 284)", source=os.path.join(TI, "AFFIDAVIT OF LOSS P.Zschoche 22Feb2023.pdf"), pages=[1, 2]),
                dict(label="Letter to Provincial Assessor 22 Feb 2023 (doc 294)", source=os.path.join(TI, "Provincial Assesor 2023.pdf"), pages=[1, 2])]),
    dict(id=10, title="Agcaoili & Associates letter of 15 August 2019, copy furnished Atty. Elaine R. Belen, Daet, 1 p.",
         why="If asked when the family's lawyers first wrote about Cesar's dealings, or whether anyone in Daet was told.",
         say="The family's counsel wrote on 15 August 2019 and furnished a copy to Atty. Belen in Daet. I have the letter.",
         parts=[dict(label="Agcaoili letter (doc 299)", source=os.path.join(TI, "Reply to JDavis CGrippo re CDelaFuente 15Aug2019.pdf"), pages=[1])]),
    dict(id=11, title="Your written request to the Registry of Deeds for certified copies, 28 April 2025, received 29 April 2025, 3 pp (letter only).",
         why="If asked when and how you obtained the Registry records, or whether you went through proper channels.",
         say="I asked the Registry in writing in April 2025, under my mother's power of attorney, and received certified copies. (Never name any Registry officer as a source.)",
         parts=[dict(label="RD request received 29 Apr 2025 (doc 303)", source=os.path.join(TI, "ROD RECEIVED REQUEST April 29 2025 (1).pdf"), pages=[1, 2, 3])]),
    dict(id=12, title="Your Formal Request for Information to Engr. Erwin H. Balane, Office of the Building Official, 24 January 2026, 3 pp. Part B asks for every building permit, locational clearance and occupancy permit on the subdivided lot (Plan PSD-E2020005406) 'throughout its entire history'.",
         why="If asked whether you ever asked the LGU for the building history of the lot, or what you asked the Municipal Engineer for. The reply at Tab 13 produced no permit, no clearance and no occupancy certificate.",
         say="On 24 January 2026 I asked the Building Official in writing for every permit and clearance ever issued on the lot. I received the letter at Tab 13 and no documents. (That is why the Building Official is on the subpoena list.)",
         parts=[dict(label="FOI request to Engr. Balane 24 Jan 2026 (doc 838)", source=os.path.join(BASE, "src", "FOI_request_to_Erwin_Balane_2026-01-24_doc838.pdf"), pages=[1, 2, 3])]),
    dict(id=13, title="Letter of Engr. Erwin H. Balane, Municipal Engineer, in response to the 24 January 2026 request; dated on its face 'February 5, 2025', 1 p.",
         why="The reply to Tab 12. Ramos may raise the ARTA complaints that followed it to show bias.",
         say="This is his reply to my request. It enclosed no permit, clearance or occupancy certificate. (No comment on its tone; its wording is quoted in the Authority's own resolution at Tab 16.)",
         parts=[dict(label="Erwin letter (doc 773)", source=os.path.join(DL, "Reply Letter.pdf"), pages=[1])]),
    dict(id=14, title="Anti-Red Tape Authority, Resolution of 7 April 2026 in CTN SL-2025-1008-0690 and SL-2025-1104-0792 (Zschoche v. Engr. Erwin H. Balane), recommendations pp. 7-8; Endorsement to the Civil Service Commission Regional Office V, 30 April 2026, 2 pp.",
         why="ONLY IF ASKED about the complaints. The Authority closed its own case and referred Engr. Balane to the Civil Service Commission for the alleged violation of Section 5(a) of R.A. 6713 (duty to act on letters within fifteen working days).",
         say="I complained to the Authority about unanswered records requests. The Authority referred the matter to the Civil Service Commission on its own findings. The referral is the agency's act, not mine. (Say nothing about the merits.)",
         parts=[dict(label="ARTA Res. 7 Apr 2026 (doc 719)", source=os.path.join(LT, "case_work", "MWK-001", "ARTA_RESOLUTIONS_COMPENDIUM", "source", "res_719.pdf"), pages=[7, 8]),
                dict(label="Endorsement to CSC-RO V 30 Apr 2026 (doc 706)", source=os.path.join(BASE, "src", "ARTA_endorsement_CSC_0690_0792_doc706.pdf"), pages=[1, 2])]),
    dict(id=15, title="Anti-Red Tape Authority, Resolution of 1 June 2026 in CTN SL-2026-0128-1212 (Zschoche v. Yapyuco, Ong and Torralba), recommendations pp. 6-7; Endorsement to the Office of the Ombudsman, received 29 July 2026, 2 pp; Office of the Ombudsman, 1st Indorsement IC-OC-JUL-26-1214, 24 August 2026, 1 p.",
         why="ONLY IF ASKED. The Authority referred Councilor Princess B. Torralba (a defendant) to the Ombudsman for the alleged violation of R.A. 6713, and the Ombudsman docketed the 111-page record and forwarded it to the Deputy Ombudsman for Luzon.",
         say="The Authority referred Councilor Torralba to the Ombudsman on its own findings, and the Ombudsman docketed it. I filed a complaint; the agencies decided. (Nothing more; the defense will call it a campaign against the family, so do not argue it.)",
         parts=[dict(label="ARTA Res. 1 Jun 2026 (doc 1614)", source=os.path.join(LT, "case_work", "MWK-001", "ARTA_RESOLUTIONS_COMPENDIUM", "source", "res_1614.pdf"), pages=[6, 7]),
                dict(label="Endorsement to Ombudsman (doc 3754)", source=os.path.join(BASE, "src", "ARTA_endorsement_OMB_1212_doc3754.pdf"), pages=[1, 2]),
                dict(label="Ombudsman 1st Indorsement 24 Aug 2026 (doc 7697)", source=os.path.join(BASE, "src", "OMB_1st_Indorsement_IC-OC-JUL-26-1214_doc7697.pdf"), pages=[1])]),
    dict(id=16, title="Anti-Red Tape Authority, Resolution of 9 September 2026 in CTN SL-2026-0218-1378 (Zschoche v. Engr. Erwin H. Balane), referral discussion and dispositive pp. 8-9.",
         why="ONLY IF ASKED. The Authority quoted the 'overstaying foreigner' sentence of Tab 13 and referred the question of Engr. Balane's administrative liability for it to the Civil Service Commission Region V.",
         say="The Authority quoted his letter and referred it to the Civil Service Commission. I have no finding to report; it is pending. (Do not read the sentence aloud yourself; if the court wants it, it is on the page.)",
         parts=[dict(label="ARTA Res. 9 Sep 2026 (doc 14205)", source=os.path.join(LT, "case_work", "MWK-001", "ARTA_RESOLUTIONS_COMPENDIUM", "source", "res_1378.pdf"), pages=[8, 9])]),
]

for t in TABS:
    for k in ("title", "why", "say"):
        t[k] = clean(t[k])
    for p in t["parts"]:
        p["label"] = clean(p["label"])

html = os.path.join(ROOT, "BRING_TO_COURT_BUNDLE_2026-10.html")
tmp = os.path.join(BASE, "_bring_cover.pdf")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={tmp}", "file://" + html],
               check=True, capture_output=True)
out = fitz.open()
cover = fitz.open(tmp)
out.insert_pdf(cover)
toc = [[1, "Cover: how to use these on the stand", 1]]


def normalize(src_doc, pg_index):
    sp = src_doc[pg_index]
    r = sp.rect
    rot = sp.rotation
    sw, sh = (r.height, r.width) if rot in (90, 270) else (r.width, r.height)
    np_ = out.new_page(width=W, height=H)
    margin_top, margin_bottom = 18, 34
    avail_w, avail_h = W - 24, H - margin_top - margin_bottom
    s = min(avail_w / sw, avail_h / sh)
    tw, th = sw * s, sh * s
    x0 = (W - tw) / 2
    y0 = margin_top + (avail_h - th) / 2
    np_.show_pdf_page(fitz.Rect(x0, y0, x0 + tw, y0 + th), src_doc, pg_index, rotate=0)
    return np_


for t in TABS:
    total = sum(len(p["pages"]) for p in t["parts"])
    p = out.new_page(width=W, height=H)
    start = out.page_count
    p.insert_text((54, 120), f"TAB {t['id']}", fontsize=30, fontname="tibo")
    p.draw_rect(fitz.Rect(54, 132, W - 54, 136), color=(0, 0, 0), fill=(0, 0, 0))
    y = 162
    for label, key in [("Document", "title"), ("Why it may come up", "why"), ("What you say if asked", "say")]:
        p.insert_text((54, y), label.upper(), fontsize=9, fontname="hebo", color=(.35, .35, .35))
        y += 9
        txt = t[key]
        lines = max(1, int(len(txt) / 72) + 1)
        box_h = min(320, lines * 19 + 16)
        p.insert_textbox(fitz.Rect(54, y, W - 54, y + box_h), txt, fontsize=13, fontname="tiro", align=0)
        y += box_h + 12
    p.insert_text((54, y + 6), "PAGES IN THIS TAB", fontsize=9, fontname="hebo", color=(.35, .35, .35))
    y += 22
    k = 1
    for part in t["parts"]:
        pr = part["pages"]
        rng = f"{k}" if len(pr) == 1 else f"{k} to {k + len(pr) - 1}"
        line = f"Tab pp. {rng}:  {part['label']}, source pp. {', '.join(str(x) for x in pr)}"
        p.insert_textbox(fitz.Rect(54, y, W - 54, y + 44), line, fontsize=10.5, fontname="tiro", align=0)
        y += 32 if len(line) > 90 else 17
        k += len(pr)
    p.insert_text((54, H - 20), f"Tab {t['id']} divider  ·  Zschoche v. Balane, Civil Case No. 26-360  ·  documents outside the record, carried by the witness  ·  not for filing",
                  fontsize=7, fontname="helv", color=(.4, .4, .4))
    k = 1
    for part in t["parts"]:
        src = fitz.open(part["source"])
        for pg in part["pages"]:
            if not (1 <= pg <= src.page_count):
                raise SystemExit(f"Tab {t['id']}: page {pg} out of range for {part['source']} ({src.page_count} pp)")
            np_ = normalize(src, pg - 1)
            np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
            np_.insert_text((54, H - 14), f"TAB {t['id']}  ·  p. {k} of {total}  ·  source: {part['label']}, p. {pg}  ·  Zschoche v. Balane, Civil Case No. 26-360  ·  outside the record, not marked",
                            fontsize=7.2, fontname="helv", color=(.25, .25, .25))
            k += 1
    toc.append([1, f"Tab {t['id']}: {t['title'][:90]}", start])

out.set_toc(toc)
out.set_metadata({"title": "Zschoche v. Balane, Civil Case No. 26-360: documents outside the record, carried by the witness", "author": "", "subject": "14 Oct 2026"})
dest = os.path.join(ROOT, "BRING_TO_COURT_BUNDLE_2026-10.pdf")
out.rewrite_images(dpi_threshold=160, dpi_target=140, quality=62, lossy=True, lossless=True)
out.save(dest, garbage=4, deflate=True, deflate_images=True, deflate_fonts=True)
print("cover pages", cover.page_count, "| total", out.page_count, "|", os.path.getsize(dest) // 1024, "KB ->", dest)
