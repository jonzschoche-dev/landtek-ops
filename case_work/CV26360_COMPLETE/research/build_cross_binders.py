"""Build the physical cross-examination binders for Civil Case 26-360, one PDF per defense witness,
tabbed in the exact order of the Master Trial Playbook, section 5.2. Each tab = one divider page
(the question, the document) followed by the pre-pulled pages, stamped with tab and source page.
Output: CROSS_BINDERS_2026-10/CROSS_BINDER_<witness>.pdf (8.5 x 13) + an index page per binder.

  python3 research/build_cross_binders.py
"""
import fitz, os

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
OUT = os.path.join(ROOT, "CROSS_BINDERS_2026-10"); os.makedirs(OUT, exist_ok=True)
W, H = 612, 936
DL = "/Users/jonathanzschoche/landtek/drive_local/"
TB = DL + "CV26360 - Trial Brief for Atty. Botor (2026-08-30)/"
TI = DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/Evidence/Transfer Investigation/"
SRC = BASE + "/src/"

F = {
 "EX5": DL + "Exhibit 5 - Receipts.pdf",
 "EX6": DL + "Exhibit 6 - Deed of Absolute Sale.pdf",
 "EX7": DL + "Exhibit 7 - Special Power of Attorney dated March 16, 1992.pdf",
 "EX1": DL + "Exhibit 1 - Transfer Certificate of Title No. 079-202100216.pdf",
 "EXB": DL + "Exhibit B to B-4 - Complaint - Civil Case No. 26-360.pdf",
 "ANS": DL + "Answer with Special and Affirmative Defenses and Compulsory Counterclaim.pdf",
 "A1":  DL + "Annex 1 - Special Power of Attorney .pdf",
 "JAS": TB + "C3 - Judicial Affidavit - Salvador Osum Dela Fuente (defense).pdf",
 "JAP": TB + "C4 - Judicial Affidavit - Princess Balane Torralba (defense).pdf",
 "JAE": TB + "C5 - Judicial Affidavit - Engr. Erwin H. Balane (defense).pdf",
 "JAG": TB + "C2 - Judicial Affidavit - Gloria H. Balane (EXCLUDED at pre-trial; admission motion pending).pdf",
 "D7":  TB + "D7 - 2012 SPA Cesar de la Fuente to Salvador (Von) - the unauthorized sub-delegation, Art. 1892.pdf",
 "SP":  TI + "Owners Duplicate Petition.pdf",
 "RD98": TI + "Balane Supporting Docs.partition.titles.pdf",
 "RD96": TI + "Balane Supporting Docs.pdf",
 "K8563": DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/_Needs Review/Civil case 8563 for Damages  malicious prosecutions.pdf",
 "CAPET": DL + "01 - Clients/Heirs of Mary Worrick Keesey- LTC-002/Legal/Court of appeals petition for centriari.pdf",
 "SAL": SRC + "SAL_drive_new_Letter_from_Salvador_Dela_Fuente.pdf",
 "SB86": SRC + "SB_Res_103-86_1986-07-16.pdf",
 "R719": "/Users/jonathanzschoche/landtek/case_work/MWK-001/ARTA_RESOLUTIONS_COMPENDIUM/source/res_719.pdf",
 "R1614": "/Users/jonathanzschoche/landtek/case_work/MWK-001/ARTA_RESOLUTIONS_COMPENDIUM/source/res_1614.pdf",
 "R1378": "/Users/jonathanzschoche/landtek/case_work/MWK-001/ARTA_RESOLUTIONS_COMPENDIUM/source/res_1378.pdf",
 "E706": SRC + "ARTA_endorsement_CSC_0690_0792_doc706.pdf",
 "E3754": SRC + "ARTA_endorsement_OMB_1212_doc3754.pdf",
 "OMB": SRC + "OMB_1st_Indorsement_IC-OC-JUL-26-1214_doc7697.pdf",
 "ERW": DL + "Reply Letter.pdf",
 "EXN": DL + "Exhibit N - Complaint - Civil Case No. 26-360.pdf",
}

# (witness title, note, [ (tab title / the question, document description, [(key, [pages])...]) ])
BINDERS = [
 ("SALVADOR OSUM DELA FUENTE", "Defense witness; sponsor of Exhibit 5; the 'class' witness. Playbook 5.2, in order.", [
  ("TAB 1. Is a monthly bill to an 'Occupant' rent?", "Exhibit 5: 'HEIRS OF MARY W. KEESEY ESTATE' receipts with 'Occupant's Name' and 'Payment for the month of' (2007; 2013-2014).", [("EX5",[9,10,11,23,24,25,26,27])]),
  ("TAB 2. Who registered TIN 160-902-582 and ordered the 1998 printing of the receipt books? Did any owner?", "Exhibit 5, p. 9: form imprint 'TIN-160-902-582-Non Vat ... 4C's Press-Daet, CN Auth. No. 451-1998'.", [("EX5",[9])]),
  ("TAB 3. Why do Nos. 0218 and 0219 (Nov 2016) follow Nos. 0221-0223 (Sep-Oct 2016)? Why is No. 0226 (30 Jan 2017) after No. 0227 (7 Jan)? Were these written at the time of payment?", "Exhibit 5, pp. 30-33.", [("EX5",[30,31,32,33])]),
  ("TAB 4. Was the P250,000 'in hand paid' on 29 September 2016? Then what is Receipt No. 0228, 'Full payment', of February 2017?", "Deed of Absolute Sale (Def. Exh. 6, p. 1); Exhibit 5, p. 33.", [("EX6",[1]),("EX5",[33])]),
  ("TAB 5. S31: the owners never came home; your father dealt with the Agcaoili law office in Manila. Did anyone consult the owners before selling to Mrs. Balane? Could they have been reached?", "Salvador JA, p. 6 (S30-S32).", [("JAS",[6])]),
  ("TAB 6. S29: 'others' processed the transfer. Who paid the BIR on 15 June 2020, three years after your father died? Who presented the papers in November 2021?", "Salvador JA, p. 6 (S29); Def. Exh. 6, p. 2 (eCARs of 19 Jun 2020 and 18 Nov 2021).", [("JAS",[6]),("EX6",[2])]),
  ("TAB 7. January 2017, Spec. Proc. 2156: your father swore HE was in possession. Who was living on the 2,587 sqm?", "Spec. Proc. 2156 transcript, p. 9 (SP p. 45): 'Q: ... person in actual possession ...? A: I, Your Honor.'", [("SP",[45])]),
  ("TAB 8. The 29 February 2012 paper: your father's signature? Did any owner sign or know of it? Where is the power to sell? Who notarized it? (Argue 'nothing left to substitute'; never 'substitution forbidden'.)", "SPA Cesar M. de la Fuente to Salvador O. dela Fuente, 29 Feb 2012, Notary Elaine Gay R. Belen, Doc. 55/Pg. 17/Bk. IX/2012.", [("D7",[1,2])]),
  ("TAB 9. FOUNDATION (Rule 132, Sec. 13): show the letter; fix date and place; 'Did you write and sign this?'; let him explain. Then: which Llamanzares CONTRACT OF SALE or receipt did the Balanes hold? What documents did you issue to the other families on this lot, and what did they pay you for?", "Letter of Von dela Fuente, 25 Nov 2025, 2 pp., signed.", [("SAL",[1,2])]),
  ("TAB 10. DEMAND THE ORIGINALS of these receipts (faint day/year digits).", "Exhibit 5, pp. 2, 22, 32, 33.", [("EX5",[2,22,32,33])]),
 ]),
 ("PRINCESS BALANE TORRALBA", "Defense witness; Municipal Councilor. Playbook 5.2, in order.", [
  ("TAB 1. S10: 'no part in the sale except the survey.' About 45 receipts are in your name, 2007-2012, including P15,000 'partial payment for lot'.", "Exhibit 5, pp. 9-12, 22; Princess JA, p. 3 (S10).", [("JAP",[3]),("EX5",[9,10,11,12,22])]),
  ("TAB 2. The 29 December 2006 survey receipt you paid: 'lot OWNED BY THE HEIRS OF WORRICK KEESEY'.", "Exhibit 5, p. 1.", [("EX5",[1])]),
  ("TAB 3. S11: 'no objection from anyone, ever.' Your mother's 28 May 2020 SPA 'to institute or file action ... and defend me.' Mrs. King's sworn account that you said in 2020 'May usapin pa yan.'", "Answer Annex '1' (Gloria -> Nelly Juntilla SPA, 28 May 2020); King complaint-affidavit, 10 Nov 2020 (CC 8563 record, p. 37).", [("JAP",[3]),("A1",[1,2,3]),("K8563",[37])]),
  ("TAB 4. Which structures went up after September 2016? Who paid? Under what permit?", "Insert the Building Official's return here when received (Playbook 6.2, item 4).", []),
  ("TAB 5. BIAS, ONLY IF SHE CLAIMS NEUTRALITY. One question, then stop.", "ARTA Resolution 1 Jun 2026 (CTN SL-2026-0128-1212), dispositive page; Endorsement to the Ombudsman; Ombudsman 1st Indorsement IC-OC-JUL-26-1214 (24 Aug 2026).", [("R1614",[6]),("E3754",[1]),("OMB",[1])]),
 ]),
 ("ENGR. ERWIN H. BALANE", "Defense witness; Municipal Engineer and Building Official. Playbook 5.2, in order.", [
  ("TAB 1. S14/S23: you saw Cesar show the SPA 'as proof he was authorized to sell.' Did you read paragraph 7? Whose contracts to sell? Whose down payments? Whose consultation?", "1992 SPA, p. 3 (paragraphs 6-9); Erwin JA, pp. 4-5 (S14-S16, S23).", [("EX7",[3]),("JAE",[4,5])]),
  ("TAB 2. S16: you requested the 2026 certified copies and keep the family's papers. Where is the owner's duplicate of T-2021002127? Who held the T-52540 duplicate issued in 2017 when it was surrendered in 2021?", "Exhibit B, p. 5 (Entry 2017000693, new duplicate); Def. Exh. 1 (TCT 079-2021002126).", [("EXB",[5]),("EX1",[1,2])]),
  ("TAB 3. You appear nowhere on the 2020 plan or the Registry files. Who told Engr. Mangiga the owners consented on 8 September 2020?", "Plan (LRA) PSD-E2020005406: title block and GE certification (RD Ref. 2025001096, pp. 2, 4, 6).", [("RD96",[2,4,6])]),
  ("TAB 4. Does your office hold a building permit or certificate of occupancy for any structure your family built on this lot? Who signed the application as owner? Will you produce them?", "Insert the Building Official's return or no-record certification here (Playbook 6.2, item 4). PD 1096, Sec. 301.", []),
  ("TAB 5. ONLY IF HE CLAIMS GOOD FAITH TOWARD THE OWNERS' REPRESENTATIVE: the 5 Feb 2026 letter; the two CSC referrals.", "Letter of Engr. Balane (dated 'February 5, 2025'); ARTA Resolution 7 Apr 2026 dispositive page + CSC endorsement; ARTA Resolution 9 Sep 2026 dispositive page.", [("ERW",[1]),("R719",[7]),("E706",[1]),("R1378",[9])]),
 ]),
 ("GLORIA H. BALANE (CONDITIONAL: only if her affidavit is admitted and she appears)", "Her affidavit was EXCLUDED at pre-trial; motion to admit pending. Nothing in it may be used unless admitted. Playbook 5.2, in order.", [
  ("TAB 1. S43: no contact with the owners, ever.", "Gloria JA, p. 8 (S43).", [("JAG",[8])]),
  ("TAB 2. S33, S50: deed after full payment. Against Receipt No. 0228, February 2017.", "Gloria JA, pp. 7, 10; Exhibit 5, p. 33.", [("JAG",[7,10]),("EX5",[33])]),
  ("TAB 3. S57: no notice of dispute before her title. Against her own 28 May 2020 SPA to sue and be sued.", "Gloria JA, p. 11; Answer Annex '1'.", [("JAG",[11]),("A1",[1,2,3])]),
  ("TAB 4. S59: Barangay Kagawad 1997-2004; Konsehal 2004-2017.", "Gloria JA, p. 11. (COMELEC / SB Secretary certification to insert when obtained.)", [("JAG",[11])]),
  ("TAB 5. S63-S64: first learned in August 2025. Against 'my property ... T-52540' sworn 15 Sep 2021 and the pleading received by her side 9 Jul 2021. Were you in Daet on 15 September 2021?", "Gloria JA, p. 12; Gloria -> Elevado SPA (RD Ref. 2025001098, p. 4 of 4); King Verified Answer p. 1 and p. 14 (Aquino receipt stamp).", [("JAG",[12]),("RD98",[20]),("K8563",[1,14])]),
 ]),
 ("EFREN BALANE and JOMIL TORRALBA", "If called. Playbook 5.2.", [
  ("TAB 1. EFREN: SB Mercedes Resolution No. 103-86 (16 Jul 1986): 'Hon. Efren Balane - Acting Kagawad' present; resolution recites 'Mary Worrick Keesey, represented by her Attorney-In-Fact, Mr. Benjamin Llamanzares'. VERIFY IDENTITY before use; certified copy to obtain.", "SB Res. 103-86, pp. 1-2 (copy).", [("SB86",[1,2])]),
  ("TAB 2. EFREN: the 2003 and 2005 receipts are in your name.", "Exhibit 5, pp. 2-3.", [("EX5",[2,3])]),
  ("TAB 3. JOMIL: ONE QUESTION. In 2020 you posted P180,000 in cash bonds in a case before this court over who had the right to this land. Stop.", "Order of 6 Jan 2021, Crim. Case 20-6030 (CA record pp. 80-81).", [("CAPET",[80,81])]),
  ("TAB 4. (Context only, not for questions) Shirley D. De Leon, Exh. N: the 2020 eviction attempt and the boarded-up door.", "Exhibit N.", [("EXN",[1,2,3,4,5])]),
 ]),
]

def show(out, src, pg):
    sp = src[pg]; r = sp.rect; rot = sp.rotation
    sw, sh = (r.height, r.width) if rot in (90, 270) else (r.width, r.height)
    p = out.new_page(width=W, height=H)
    aw, ah = W - 24, H - 18 - 34; s = min(aw / sw, ah / sh); tw, th = sw * s, sh * s
    x0 = (W - tw) / 2; y0 = 18 + (ah - th) / 2
    p.show_pdf_page(fitz.Rect(x0, y0, x0 + tw, y0 + th), src, pg)
    return p

for witness, note, tabs in BINDERS:
    out = fitz.open()
    # index page
    p = out.new_page(width=W, height=H)
    p.insert_text((54, 90), "CROSS-EXAMINATION BINDER", fontsize=20, fontname="tibo")
    p.insert_text((54, 116), witness, fontsize=14, fontname="tibo")
    p.insert_textbox(fitz.Rect(54, 126, W - 54, 170), note + "  Zschoche v. Balane, Civil Case No. 26-360, MTC Mercedes. Prepared for counsel, 13 Oct 2026.", fontsize=10, fontname="tiro")
    y = 180
    for i, (q, d, parts) in enumerate(tabs, 1):
        txt = q.replace("TAB %d. " % i, "")
        r = p.insert_textbox(fitz.Rect(54, y, W - 54, y + 120), f"TAB {i}.  {txt}", fontsize=9.6, fontname="tibo")
        y += min(120, (len(txt) // 95 + 1) * 12 + 4)
        p.insert_textbox(fitz.Rect(70, y, W - 54, y + 60), d, fontsize=9, fontname="tiro", color=(.25, .25, .25))
        y += min(60, (len(d) // 100 + 1) * 11 + 8)
        if y > H - 120:
            p = out.new_page(width=W, height=H); y = 72
    toc = [[1, "Index", 1]]
    for i, (q, d, parts) in enumerate(tabs, 1):
        dp = out.new_page(width=W, height=H); start = out.page_count
        dp.insert_text((54, 120), f"TAB {i}", fontsize=30, fontname="tibo")
        dp.draw_rect(fitz.Rect(54, 132, W - 54, 136), color=(0, 0, 0), fill=(0, 0, 0))
        dp.insert_text((54, 160), "THE QUESTION", fontsize=8.5, fontname="hebo", color=(.35, .35, .35))
        dp.insert_textbox(fitz.Rect(54, 168, W - 54, 420), q.replace("TAB %d. " % i, ""), fontsize=13, fontname="tibo")
        dp.insert_text((54, 440), "THE DOCUMENT", fontsize=8.5, fontname="hebo", color=(.35, .35, .35))
        dp.insert_textbox(fitz.Rect(54, 448, W - 54, 620), d, fontsize=11.5, fontname="tiro")
        if not parts:
            dp.insert_textbox(fitz.Rect(54, 640, W - 54, 700), "[ Leave this tab open for the subpoena return. ]", fontsize=11, fontname="tiro", color=(.4, .4, .4))
        dp.insert_text((54, H - 20), f"{witness} · Tab {i} · divider · Civil Case No. 26-360 · prepared for counsel", fontsize=7, fontname="helv", color=(.4, .4, .4))
        k = 1; total = sum(len(pp) for _, pp in parts)
        for key, pages in parts:
            src = fitz.open(F[key])
            for pg in pages:
                if not (1 <= pg <= src.page_count): raise SystemExit(f"{witness} tab {i}: page {pg} out of range for {key}")
                np_ = show(out, src, pg - 1)
                np_.draw_rect(fitz.Rect(0, H - 30, W, H), color=(1, 1, 1), fill=(1, 1, 1))
                np_.insert_text((54, H - 14), f"{witness.split(' (')[0]}  ·  TAB {i}  ·  p. {k} of {total}  ·  source: {key}, p. {pg}  ·  Civil Case No. 26-360  ·  prepared for counsel", fontsize=7.2, fontname="helv", color=(.25, .25, .25))
                k += 1
        toc.append([1, f"Tab {i}: {q[:80]}", start])
    out.set_toc(toc)
    out.rewrite_images(dpi_threshold=140, dpi_target=120, quality=58, lossy=True, lossless=True)
    name = witness.split(" (")[0].replace(" ", "_").replace(".", "").replace("/", "-")
    dest = os.path.join(OUT, f"CROSS_BINDER_{name}.pdf")
    out.save(dest, garbage=4, deflate=True, deflate_images=True)
    print(f"{out.page_count:4d} pp  {os.path.getsize(dest)//1024:6d} KB  {dest}")
