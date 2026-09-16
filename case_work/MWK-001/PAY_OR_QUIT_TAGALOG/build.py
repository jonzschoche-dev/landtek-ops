#!/usr/bin/env python3
"""Render the Tagalog pay-or-quit (pay-to-stay) demand to PDF.
Pilot: T-52537 / Sps. Delfin & Luisa Gaulit. WORKING TRANSLATION — verify with counsel /
native speaker before any service. Compensation-for-occupation, NOT a lease (runs on
Patricia's 1/3, Art. 487). Nothing served by this script. PH folio (8.5x13)."""
import os
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

OUT = os.path.join(os.path.dirname(__file__), "PAUNAWA_PAY_OR_QUIT_TAGALOG_T52537.pdf")
FOLIO = (8.5 * inch, 13 * inch)

s = getSampleStyleSheet()
body = ParagraphStyle('b', parent=s['Normal'], fontName='Helvetica', fontSize=11, leading=15,
                      alignment=TA_JUSTIFY, spaceAfter=9)
ctr = ParagraphStyle('c', parent=body, fontName='Helvetica-Bold', fontSize=12, alignment=TA_CENTER, spaceAfter=4)
small = ParagraphStyle('sm', parent=body, fontSize=8, textColor='#666666', alignment=TA_CENTER, spaceAfter=12)
lead = ParagraphStyle('l', parent=body, fontName='Helvetica-Bold', spaceAfter=6)

P = [
    (small, "[BURADOR / DRAFT — para sa pagsusuri ng abogado bago ihatid. Hindi pa naihahatid. "
            "Working translation, verify before service.]"),
    (ctr, "PAUNAWA: MAGBAYAD O UMALIS"),
    (ctr, "(Paghingi ng Makatwirang Bayad sa Okupasyon o Kaya'y Pag-alis)"),
    (small, "[Letterhead ng Abogado / Barandon o Adan Botor Law Office] &nbsp;&nbsp; Petsa: ____________"),
    (body, "<b>Para kina:</b> Mag-asawang DELFIN at LUISA GAULIT [o aktuwal na okupante]<br/>"
           "[tirahan / lugar], Barangay 3, Mercedes, Camarines Norte"),
    (body, "<b>Paksa:</b> Ang inyong okupasyon sa Lote 2-X-4-E, sakop ng TCT Blg. T-52537, "
           "nakarehistro sa pangalan ng mga Tagapagmana ni Mary Worrick Keesey."),
    (body, "Mahal na Ginoo at Ginang Gaulit,"),
    (body, "Kami po ay sumusulat sa ngalan ni <b>Patricia Keesey Zschoche</b>, isa sa mga ko-may-ari "
           "ng nasabing ari-arian (mga Tagapagmana ni Mary Worrick Keesey), sa pamamagitan ng <b>LandTek</b>, "
           "ang kaniyang itinalagang tagapamahala at ahente ng ari-arian."),
    (body, "<b>1. Pagmamay-ari.</b> Ang mga Tagapagmana ang rehistradong may-ari sa ilalim ng "
           "<b>TCT Blg. T-52537</b>, at ang deklarado at nagbabayad-buwis na may-ari sa ilalim ng "
           "<b>ARP GR-2014-HH-07-003-00169</b>. Kayo ay nananatili sa ari-arian nang <b>walang titulo o "
           "karapatan</b>, at hanggang ngayon ay sa pahintulot lamang ng may-ari, na sa pamamagitan nito "
           "ay <b>binabawi na</b>."),
    (body, "<b>2. Maaari lamang kayong manatili kung magbabayad sa inyong paggamit.</b> Bilang ko-may-ari, "
           "may karapatan ang aming prinsipal sa makatwirang bayad para sa inyong okupasyon. Binibigyan po "
           "kayo ng pagpipiliang manatili, <b>buwan-buwan</b>, sa pamamagitan ng pagbabayad ng makatwirang "
           "halagang <b>PHP ______ kada buwan</b>, simula ____________, na babayaran sa nakalagda para sa "
           "ko-pag-aari."),
    (body, "<b>3. Ito ay HINDI kontrata ng pag-upa.</b> Ang kasunduang ito ay buwan-buwang pahintulot na "
           "<b>maaaring wakasan anumang oras</b> sa loob ng labinlimang (15) araw na paunawa; ibinibigay "
           "<b>nang walang pagtatalikod sa lahat ng karapatan ng mga may-ari</b>; <b>hindi lumilikha ng "
           "anumang pag-upa o tenancy</b>; at <b>hindi pagkilala sa anumang karapatan ninyo</b>. Hindi rin "
           "nito tinatalikuran ang paghingi ng bayad sa inyong <b>nakaraang</b> okupasyon, na nananatiling "
           "nakalaan."),
    (body, "<b>4. Kung hindi kayo magbabayad o aalis.</b> Kung hindi ninyo babayaran ang buwanang bayad o "
           "kusang aalis sa loob ng labinlimang (15) araw, magsasampa ang mga may-ari ng kaso upang mabawi "
           "ang pag-aari at para sa naipong makatwirang bayad at danyos. Ang anumang istrukturang itinayo "
           "ninyo ay ginawa nang <b>walang pahintulot ng may-ari at walang building permit</b> - sa ilalim "
           "ng <b>Artikulo 449-451 ng Kodigo Sibil</b>, kayo ay <b>tagapagtayo na masamang-loob</b>, na "
           "<b>walang karapatan sa reimbursement at walang karapatang manatili (retention)</b>; sa inyong "
           "pagkukulang, maaaring kunin ng mga may-ari ang istruktura nang walang bayad sa inyo, o ipagiba "
           "ito <b>sa inyong gastos</b>."),
    (body, "<b>5. Pumili sa loob ng labinlimang (15) araw:</b> (a) magbayad ng PHP ______ kada buwan at "
           "manatili nang buwan-buwan; o (b) umalis nang mapayapa. Ang katahimikan o pagtanggi ay "
           "ituturing na pagpiling kasuhan."),
    (body, "Sumasainyo,"),
    (Spacer, None),
    (lead, "____________________________<br/><b>LANDTEK [entity/OPC]</b> - sa pamamagitan ni [Awtorisadong Kinatawan]<br/>"
           "Itinalagang Tagapamahala at Ahente para kay Patricia Keesey Zschoche, ko-may-ari<br/>"
           "<font size=9>(Anumang kaso sa korte ay isasampa ng abogado.)</font>"),
]

doc = SimpleDocTemplate(OUT, pagesize=FOLIO, topMargin=1*inch, bottomMargin=1*inch,
                        leftMargin=1*inch, rightMargin=1*inch,
                        title="Paunawa: Magbayad o Umalis - T-52537")
story = []
for style, text in P:
    if style is Spacer:
        story.append(Spacer(1, 0.25*inch))
    else:
        story.append(Paragraph(text, style))
doc.build(story)
print("wrote", OUT)
