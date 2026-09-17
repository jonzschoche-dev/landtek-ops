# Standalone, file-ready complaint-affidavit (no annexes) for Barangay Sta. Rosa Sur, 15 Sep 2026.
# Every date is sourced from the corpus (see SOURCES at bottom). Handwritten fields left: Barangay Case No.,
# affiant's ID, the jurat's ID line. Run: python3 build_final.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build import new_doc, para, to_pdf, HERE

def build():
    d = new_doc()
    from docx.shared import Pt, Inches
    st = d.styles["Normal"]; st.font.size = Pt(11.5); st.paragraph_format.space_after = Pt(3)
    sec = d.sections[0]; sec.top_margin = sec.bottom_margin = Inches(0.7)
    para(d, "RECEIVED by Barangay Sta. Rosa Sur\nDate/Time: ____________  By: ______________", align="r", size=9)
    para(d, "Republic of the Philippines\nProvince of Camarines Norte\nMunicipality of Jose Panganiban\nBARANGAY STA. ROSA SUR\nOFFICE OF THE LUPONG TAGAPAMAYAPA",
         bold=True, align="c")
    para(d, "ALLAN VILLAFRIA INOCALLA, for himself and for the benefit of his co-heirs,\nComplainant,", align="l")
    para(d, "- versus -", align="c")
    para(d, "Barangay Case No. ________\nFor: Recovery of possession; stoppage and removal\nof unauthorized rod mill; accounting", align="r")
    para(d, "MAURO C. BOMBITA, SR., MAURO D. BOMBITA, JR., and all persons claiming rights under them,\nRespondents.", align="l")
    para(d, "x - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - x", align="c")
    para(d, "COMPLAINT-AFFIDAVIT", bold=True, align="c", size=14)

    para(d, "I, **ALLAN VILLAFRIA INOCALLA**, of legal age, Filipino, separated, and residing at Purok 4, Barangay Capacuan, "
            "Paracale, Camarines Norte, after being duly sworn, state:")

    body = [
        "I am a son and heir of the late spouses **Vicente Inocalla, Sr.** and **Beatriz Villafria Inocalla**, both deceased. "
        "I am also a brother of the late **Senen V. Inocalla**, who died on **12 February 2021** and left no child. "
        "Her properties therefore pass to her brothers and sisters and to the children of those who died before her, including me.",

        "I bring this complaint as one of the heirs and co-owners, for my own interest and for the benefit of all my co-heirs. "
        "Any co-owner may act to recover and protect common property for the benefit of all.",

        "The land involved is:",
        "(a) **Lot No. 905, Pls-819-D**, a coconut land of about **7.8844 hectares** at Barangay San Rafael, Jose Panganiban, Camarines Norte, "
        "declared for taxation under **ARP No. 021-00470 (GR'23)** in the name of my late sister Senen V. Inocalla, as certified by the "
        "Office of the Provincial Assessor of Camarines Norte on **4 June 2024**; and",
        "(b) the portion occupied by respondents of the land covered by **TCT No. T-2194** (13.3690 hectares), registered in the name of "
        "my father Vicente Inocalla married to Beatriz Villafria, which was assigned to Senen in the judicial partition among us heirs in "
        "Civil Case No. 5825 of the Regional Trial Court, Branch 41, Daet.",

        "Respondents reside at Purok 5, Barangay Sta. Rosa Sur, Jose Panganiban. They occupy about **five (5) hectares of Lot 905** and a "
        "portion of the land covered by TCT No. T-2194.",

        "Of my own knowledge, the Bombita family came to the land as **workers of my late brother Vicente Inocalla, Jr.** "
        "(who died on **11 September 2017**), who employed them in his coconut harvesting and small-scale mining. My parents never made them "
        "tenants. No leasehold contract was ever made with my parents or with us heirs, and to my knowledge none of us heirs has received any "
        "rental or share of the harvest from respondents.",

        "On **11 February 2012**, my family met at the home of my sister Senen with Barangay Councilor Arnel Competente of Sta. Rosa Sur, "
        "Barangay Councilor Luis Salen of Capacuan, and a surveyor. Among the matters taken up was \"a trespassing/eviction issue of Mauro "
        "Bombita and several of his family members,\" as stated in the written summation of that meeting signed by the two councilors.",

        "On **3 October 1979**, my father executed a sworn statement that the land covered by TCT No. T-2194 \"is not tenanted; nor portion "
        "thereof is devoted to rice or corn cultivation,\" which was inscribed on the title on **16 October 1979**. By Order dated "
        "**14 April 2008** in A-9999-05-EXE-096-03, the Secretary of Agrarian Reform **excluded the land covered by TCT No. T-2194 from "
        "agrarian reform coverage as mineral land**.",

        "I am aware that respondent Mauro C. Bombita, Sr. filed a case claiming to be a tenant against my late sister Senen alone "
        "(PARAD Case No. D-0502-RL-0015-2016 / DARAB Case Nos. 19415 and 19415-A, later CA-G.R. SP No. 167314). "
        "The estate of my parents and we, the other heirs, were not parties to that case. We do not recognize any tenancy by respondents binding "
        "on us, and we reserve all our rights. As recited in the pleadings of that case, respondent Mauro C. Bombita, Sr., in his Answer dated "
        "6 June 2016, admitted the ownership of my sister Senen over the property. In any event, **nothing in that case allows respondents to build or operate an ore-processing mill, to mine, "
        "or to use the land for anything other than farming.**",

        "On several occasions, when we heirs went to harvest coconuts on Senen's land, respondent Mauro C. Bombita, Sr. and his sons stopped "
        "the harvest, claiming to be tenants.",

        "At present, respondents, and persons acting with them, are **constructing a rod mill for grinding and processing gold ore on Lot 905**, "
        "**without the knowledge or consent of the heirs**. A rod mill is an ore-processing facility, not farming. The heirs never consented "
        "to any structure or mineral processing on the land.",

        "I respectfully ask the Lupon, through mediation, to require respondents to:",
        "(1) **immediately STOP** constructing and operating the rod mill, and **REMOVE** the mill, its equipment, tanks and tailings from the land "
        "within fifteen (15) days;",
        "(2) **STOP** all mining, tunneling, tree-cutting and other non-farming use of the land;",
        "(3) **VACATE and peacefully SURRENDER** to the heirs the portions of Lot 905 and of the land covered by TCT No. T-2194 that they occupy, "
        "within a period to be agreed;",
        "(4) until they vacate, **not bring in** other persons, **not build** any new structure, and **not obstruct** the heirs' entry and harvest; and",
        "(5) **render a written accounting** of all coconuts, copra and other produce, and of any ore, taken from the land from "
        "**12 February 2021** to date.",

        "I also respectfully ask the Barangay to (a) conduct an **ocular inspection** of the rod mill and record its findings, and (b) state "
        "whether any **barangay clearance or permit** was issued for its construction or operation.",

        "If no settlement is reached, I ask that a **Certification to File Action** be issued so that the heirs may bring the proper case "
        "before the proper court or agency.",

        "I execute this affidavit to attest to the truth of the foregoing, for the barangay proceedings, and for any other lawful purpose.",
    ]
    n = 0
    for t in body:
        if t.startswith("("):
            para(d, t, indent=0.5)
        else:
            n += 1; para(d, f"{n}. {t}")

    for p_ in d.paragraphs[-3:]: p_.paragraph_format.keep_with_next = True
    p_ = para(d, "IN WITNESS WHEREOF, I sign this on **15 September 2026** at Barangay Sta. Rosa Sur, Jose Panganiban, Camarines Norte.")
    p_.paragraph_format.keep_with_next = True
    p_ = para(d, "\n\n______________________________\nALLAN VILLAFRIA INOCALLA\nAffiant\nID: ______________________", align="r")
    p_.paragraph_format.keep_with_next = True; p_.paragraph_format.keep_together = True
    para(d, "SUBSCRIBED AND SWORN to before me this **15th day of September 2026** at Barangay Sta. Rosa Sur, Jose Panganiban, "
            "Camarines Norte, affiant exhibiting to me his ______________________ No. ______________________.").paragraph_format.keep_with_next = True
    para(d, "\n______________________________\nPunong Barangay\nBarangay Sta. Rosa Sur, Jose Panganiban", align="r")

    out = os.path.join(HERE, "05_COMPLAINT_AFFIDAVIT_FINAL_Sta_Rosa_Sur_2026-09-15.docx")
    d.save(out); return to_pdf(out)

if __name__ == "__main__":
    import fitz
    f = build(); print(f, len(fitz.open(f)), "pages")

# SOURCES (every date/fact in the affidavit)
# Senen d. 12 Feb 2021 ............ doc 652 (NBI report), doc 478/1317
# Senen left no child ............. INOCALLA_HEIR_ROSTER.md §3 [O] + Jonathan 2026-09-14
# Allan separated / residence ..... doc 1326 (Allan's 2 May 2026 statement), Omni SPA doc 647
# Lot 905 / ARP 021-00470 / 4 Jun 2024 ... doc 1493 (Provincial Assessor cert); Lot No. 905, Pls-819-D: doc 14085
# T-2194 / partition CC 5825 Br.41 ... doc 1161 pp12-16 (CTC), doc 671 p3
# ~5 ha of Lot 905 ................ doc 14085 (Mauro Sr.'s Answer as recited)
# Vicente Jr. d. 11 Sep 2017 ...... doc 1302 (death certificate)
# Bombitas as Vicente Jr.'s workers  doc 1326 (Allan's own statement)
# 11 Feb 2012 meeting ............. doc 1405
# 3 Oct / 16 Oct 1979 sworn stmt .. doc 1161 (T-2194 memorandum of encumbrances)
# 14 Apr 2008 DAR order ........... doc 1611 pp9-14; docs 1394, 1447
# Prior case dockets; Mauro Sr. admitted ownership ... doc 14085
# Harvest obstruction ............. docs 526, 644 (Allan's written account)
# Rod mill on Lot 905 ............. Jonathan 2026-09-14 [O]
# Hearing date/place .............. Jonathan 2026-09-14 (mediation "tomorrow", Sta. Rosa Sur)
