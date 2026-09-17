# CSSMA — Minahang Bayan application: amendment of area/sketch plan to include Lot 4 (OCT P-1616) as plant site / Mineral Processing Zone; + landowner's consent. Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

LOT = "Lot 4, Psu-143364, Original Certificate of Title No. P-1616 (Registry of Deeds for Camarines Norte; Free Patent No. 225537, 10 May 1963), 15.2069 hectares (152,069 sq. m.), Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte"

letter = [
    ("c", "<b>CAPACUAN SMALL-SCALE MINERS ASSOCIATION</b>"),
    ("c", "Purok 4, Barangay Capacuan, Paracale, Camarines Norte 4605 · DOLE Registration No. R0500-CN-0417-019-17"),
    ("c", "Allan V. Inocalla, President · 0917 155 4782 · shiraction2@gmail.com"), ("n", ""),
    ("n", "____ September 2026"), ("n", ""),
    ("n", "<b>ENGR. GUILLERMO A. MOLINA JR. IV</b>"), ("n", "Regional Director, Mines and Geosciences Bureau, Regional Office No. V"),
    ("n", "and Chairman, Provincial Mining Regulatory Board of Camarines Norte"), ("n", "Rawis, Legazpi City"), ("n", ""),
    ("n", "Copy: <b>DIRECTOR LARRY HERRADEZ</b>, Mines and Geosciences Bureau, Central Office, North Avenue, Diliman, Quezon City (re our letter of 21 June 2026)"), ("n", ""),
    ("n", "<b>SUBJECT: AMENDMENT OF THE ASSOCIATION'S APPLICATION FOR DECLARATION OF MINAHANG BAYAN (RESUBMITTED 9 JUNE 2026; INTERIM SSMC LETTER OF 21 JUNE 2026) — SUBSTITUTION OF THE APPLIED AREA WITH LOT 4, PSU-143364 (OCT NO. P-1616), 15.2069 HECTARES, BARANGAY SANTA ROSA SUR, JOSE PANGANIBAN, AS THE SOLE MINAHANG BAYAN AREA, WITH THE ASSOCIATION'S CUSTOM MILL AND PROPOSED MINERAL PROCESSING ZONE WITHIN IT</b>"),
    ("n", ""), ("n", "Sir:"),
    ("j", ("On behalf of the Capacuan Small-Scale Miners Association, and further to our resubmitted application for the declaration of a "
           "Minahang Bayan over the Inocalla properties in the Paracale–Jose Panganiban gold district (letter of 9 June 2026 to your Office; "
           "letter of 21 June 2026 to the MGB Central Office for an Interim Small-Scale Mining Contract under DAO No. 2026-08), I respectfully "
           "submit an <b>amendment of the application</b>: the Association hereby <b>substitutes the area applied for</b> — the parcels at Purok 4, Barangay Capacuan, Paracale and the wider Inocalla properties described in our earlier letters — with the following single parcel, which shall be the <b>only</b> area of the Minahang Bayan applied for:")),
    ("j", f"<b>{LOT}</b>, registered solely in my name, Allan Villafria Inocalla. The Association withdraws the Capacuan and other Inocalla-properties parcels from the application; the area applied for is Lot 4 alone."),
    ("j", ("<b>Purpose of the amendment.</b> The Association's members will mine and process within this one parcel. The parcel is also the site of the Association's custom mill — <b>AVI GOLD PROCESSING PLANT</b> (DTI "
           "Business Name No. 8480852, Regional – Region V, issued to me on 11 September 2026), a new mercury-free, cyanide-free gold "
           "gravity-concentration plant of about ten (10) tonnes per day designed to process the ore of the Association's members and of "
           "other registered small-scale miners of the district. Under Section 14 of DAO No. 2022-03, small-scale mineral processing is "
           "undertaken in Mineral Processing Zones under a Mineral Processor's License; under Section 15, the Zone is designated by the local "
           "government unit upon recommendation of the Board; and under Section 4(4)(a) of DAO No. 2026-08, processing under an Interim "
           "Small-Scale Mining Contract is confined to the contract area, or otherwise covered by a Mineral Processor's License within a duly "
           "designated Mineral Processing Zone. Declaring this parcel alone as the Minahang Bayan, with the plant site within it designated as the Mineral Processing Zone, keeps " "the Association's mining and processing inside one contract area of 15.2069 hectares, within the twenty-hectare limit for a " "small-scale mining contract area (DAO No. 2022-03, Section 11), on land whose owner consents.")),
    ("j", "I therefore respectfully request the Board and your Office:"),
    ("j", ("1. To <b>accept the amended sketch plan and technical description</b> (Annex A) substituting Lot 4, Psu-143364 as the sole area applied "
           "for, and to treat the application henceforth as an application for a Minahang Bayan in Barangay Santa Rosa Sur, Municipality of "
           "Jose Panganiban, with the earlier Paracale parcels withdrawn;")),
    ("j", ("2. To <b>recommend to the Municipality of Jose Panganiban the designation of the plant site within Lot 4 as a Mineral Processing "
           "Zone</b> under Section 15 of DAO No. 2022-03, upon declaration of the Minahang Bayan;")),
    ("j", ("3. To note the <b>written consent of the private landowner</b> (Annex B) to the inclusion of the parcel in the Minahang Bayan and to "
           "the establishment of the custom mill thereon, pursuant to Section 26 of DAO No. 2022-03 on the rights of private landowners; and")),
    ("j", ("4. To advise whether the amended area requires re-posting or re-publication and a new field verification, and to accept, in place of "
           "the Paracale endorsements previously filed, the endorsements of the Sangguniang Barangay of Santa Rosa Sur and of the Sangguniang "
           "Bayan of Jose Panganiban, which the Association is securing and will transmit upon adoption; and to apply the same substitution to "
           "the Association's request of 21 June 2026 to the MGB Central Office for an Interim Small-Scale Mining Contract, which is to be read as "
           "covering Lot 4 only.")),
    ("j", ("The parcel is titled private land, alienable and disposable by nature of its free patent; it lies outside any protected area to "
           "the best of my knowledge, and the Association will secure the DENR CENRO certification of land classification and any NCIP "
           "certification your Office requires. As the Board is aware, the Association's application no longer awaits the consent of the "
           "NIBDC exploration-permit applicant, per the MGB letter of 29 July 2026.")),
    ("j", ("Enclosed: (A) amended sketch plan of the Minahang Bayan area prepared by a licensed Geodetic Engineer, showing the existing applied "
           "area and the added Lot 4 with its technical description as certified on OCT No. P-1616; (B) Landowner's Consent and Affidavit of "
           "Allan V. Inocalla; (C) certified true copy of OCT No. P-1616; (D) DTI Certificate of Business Name Registration No. 8480852; "
           "(E) copies of our letters of 9 June 2026 and 21 June 2026.")),
    ("n", ""), ("n", "Respectfully yours,"), ("n", ""), ("n", ""), ("n", ""),
    ("n", "<b>ALLAN V. INOCALLA</b>"), ("n", "President / Authorized Representative, Capacuan Small-Scale Miners Association"),
    ("n", "Owner, Lot 4, Psu-143364 (OCT No. P-1616) · Proprietor, AVI Gold Processing Plant"), ("n", ""),
    ("n", "Received by: ______________________  Position: ______________  Date/Time: ______________"),
]

consent = [
    ("n", "REPUBLIC OF THE PHILIPPINES )"), ("n", "PROVINCE OF CAMARINES NORTE ) S.S."), ("n", "______________________ )"), ("n", ""),
    ("c", "<b>ANNEX B — LANDOWNER'S CONSENT AND AFFIDAVIT</b>"),
    ("c", "(Declaration of Lot 4, Psu-143364, OCT No. P-1616 as the Minahang Bayan applied for by the Capacuan Small-Scale Miners Association, and establishment of a custom mill thereon)"), ("n", ""),
    ("j", ("I, <b>ALLAN VILLAFRIA INOCALLA</b>, of legal age, Filipino, born 12 January 1955 at Paracale, Camarines Norte, with residence at Purok 4, "
           "Barangay Capacuan, Paracale, Camarines Norte, after having been duly sworn in accordance with law, depose and state:")),
    ("j", f"1. That I am the sole registered owner of <b>{LOT}</b>, as shown by the certified true copy of the title attached hereto, and that the parcel is free from any subsisting mortgage, lease or adverse claim to my knowledge;"),
    ("j", ("2. That I hereby <b>consent</b> to the declaration of the said parcel, as the sole area applied for by the Capacuan Small-Scale Miners "
           "Association, as a People's Small-Scale Mining Area (Minahang Bayan) under Republic Act No. 7076 and DAO No. 2022-03, "
           "and to its designation, in whole or in part, as a Mineral Processing Zone under Section 15 of DAO No. 2022-03;")),
    ("j", ("3. That I further consent to, and shall myself undertake through my sole proprietorship AVI Gold Processing Plant (DTI Business Name "
           "No. 8480852), the establishment and operation on the parcel of a custom mill using gravity concentration only, without mercury or "
           "cyanide, for the processing of ore of the Association's members and other registered small-scale miners, subject to the issuance of "
           "the Environmental Compliance Certificate, the Mineral Processor's License or Mineral Processing Permit, and the permits of the "
           "Municipality of Jose Panganiban;")),
    ("j", ("4. That this consent is given freely as landowner under Section 26 of DAO No. 2022-03, without prejudice to my rights as owner, and "
           "that no compensation is claimed by me from the Association for the use of the parcel as processing site, the same being my own "
           "undertaking; and")),
    ("j", "5. That I execute this affidavit to attest to the truth of the foregoing and for submission to the Provincial Mining Regulatory Board of Camarines Norte, the Mines and Geosciences Bureau and the Municipality of Jose Panganiban."),
    ("j", "IN WITNESS WHEREOF, I have hereunto set my hand this ____ day of ____________ 2026 at ______________, Camarines Norte."),
    ("n", ""), ("n", ""), ("n", ""), ("n", "<b>ALLAN VILLAFRIA INOCALLA</b>"), ("n", "Affiant / Landowner · TIN 200-011-253 · ID: ______________________ No. ______________"), ("n", ""),
    ("j", ("SUBSCRIBED AND SWORN to before me this ____ day of ____________ 2026 at ______________, Camarines Norte, affiant exhibiting to me his "
           "______________________ No. ______________ issued on __________ at __________.")),
    ("n", ""), ("n", ""), ("n", "NOTARY PUBLIC"), ("n", "Doc. No. ____; Page No. ____; Book No. ____; Series of 2026."),
]

annexA = [
    ("c", "<b>ANNEX A — AMENDED SKETCH PLAN AND TECHNICAL DESCRIPTION (to be prepared by a licensed Geodetic Engineer)</b>"), ("n", ""),
    ("j", "Contents required: (1) for reference only, the area as filed on 9 June 2026 (Purok 4, Barangay Capacuan, Paracale), marked WITHDRAWN; (2) the substituted and sole area — Lot 4, Psu-143364, OCT No. P-1616 — plotted from the technical description certified on the title (tie-line from BLLM No. 1, Batobalani, Paracale; 15 corners; 152,069 sq. m.), with geographic coordinates (WGS 84 / PRS 92) of each corner; (3) the proposed Mineral Processing Zone within Lot 4 (plant footprint, initial 5,000 sq. m., to be fixed by the site plan); (4) municipal and barangay boundaries (Paracale / Jose Panganiban; Capacuan / Santa Rosa Sur); (5) overlay against EXPA-000250-V and any other tenement, and the DENR land-classification map; (6) scale, north arrow, legend, and the Geodetic Engineer's name, PRC number, signature and seal."),
    ("j", "Note: the technical description on the title copies in hand (docs 633/639) is legible only in part on scan; the Geodetic Engineer must work from a fresh certified true copy of OCT No. P-1616 from the Registry of Deeds, not from a retyping."),
]

def build_docx(path):
    doc = Document()
    for s in doc.sections:
        s.top_margin = s.bottom_margin = Inches(0.9); s.left_margin = s.right_margin = Inches(1.0)
    doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11.5)
    def para(k, t):
        p = doc.add_paragraph(); r = p.add_run(t.replace('<b>','').replace('</b>','')); r.bold = '<b>' in t
        p.alignment = {'c': WD_ALIGN_PARAGRAPH.CENTER, 'j': WD_ALIGN_PARAGRAPH.JUSTIFY}.get(k, None)
        p.paragraph_format.space_after = Pt(6 if k == 'j' else 0)
    for k, t in letter: para(k, t)
    doc.add_page_break()
    for k, t in annexA: para(k, t)
    doc.add_page_break()
    for k, t in consent: para(k, t)
    doc.save(path)

def build_pdf(path):
    ss = getSampleStyleSheet()
    J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=11, leading=14.5, alignment=TA_JUSTIFY, spaceAfter=6)
    L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0); C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=0)
    sty = {'c': C, 'j': J, 'n': L}
    story = [Paragraph(t or "&nbsp;", sty[k]) for k, t in letter] + [PageBreak()] + \
            [Paragraph(t or "&nbsp;", sty[k]) for k, t in annexA] + [PageBreak()] + \
            [Paragraph(t or "&nbsp;", sty[k]) for k, t in consent]
    SimpleDocTemplate(path, pagesize=A4, leftMargin=2.3*cm, rightMargin=2.3*cm, topMargin=2*cm, bottomMargin=2*cm).build(story)

build_docx("CSSMA_MB_AREA_AMENDMENT_LOT4_OCT_P-1616.docx"); build_pdf("CSSMA_MB_AREA_AMENDMENT_LOT4_OCT_P-1616.pdf"); print("built")
