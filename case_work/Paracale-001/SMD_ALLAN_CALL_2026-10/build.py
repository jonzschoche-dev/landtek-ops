# Kristyle's call sheet: DENR R5 SMD, Allan V. Inocalla's survey-record requests (Ref SMD-SCS-INC-26-172 + 24 Sep supplement). Run: python3 build.py
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

ss = getSampleStyleSheet()
N = ParagraphStyle('N', parent=ss['Normal'], fontName='Helvetica', fontSize=9.6, leading=12.4, spaceAfter=3)
S = ParagraphStyle('S', parent=N, fontSize=8.4, leading=10.4, spaceAfter=0)
SAY = ParagraphStyle('SAY', parent=N, leftIndent=10, borderPadding=(5, 6, 5, 6), backColor=colors.HexColor('#EEF3F8'),
                     borderColor=colors.HexColor('#B9CCE0'), borderWidth=0.6, spaceBefore=9, spaceAfter=9)
H1 = ParagraphStyle('H1', parent=N, fontName='Helvetica-Bold', fontSize=14.5, leading=18, spaceAfter=2)
H2 = ParagraphStyle('H2', parent=N, fontName='Helvetica-Bold', fontSize=11, leading=14, spaceBefore=9, spaceAfter=3,
                    textColor=colors.HexColor('#1F3A5A'))
B = '_' * 14

def say(t): return Paragraph('<i>Say:</i> "' + t + '"', SAY)
def grid(rows, widths, head=True):
    t = Table([[Paragraph(str(c), S) for c in r] for r in rows], colWidths=widths, repeatRows=1 if head else 0)
    st = [('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#9AA5B1')), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
          ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]
    if head: st.append(('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDE6EF')))
    t.setStyle(TableStyle(st)); return t

box = '[ ] Yes  [ ] No  [ ] ?'
W = [0.7*cm, 6.9*cm, 2.6*cm, 2.6*cm, 1.7*cm, 2.9*cm]

story = [
    Paragraph('Call sheet: DENR Region V, Surveys and Mapping Division', H1),
    Paragraph('For <b>Kristyle</b> · prepared 7 October 2026 · <b>Allan V. Inocalla</b> (registered owner, OCT P-1616), Paracale / Jose Panganiban, Camarines Norte', N),
    Spacer(1, 4),
    grid([['Call', '<b>SMD Hotline 0917 139 0360</b>, or <b>0956 241 2769</b> (from SMD\'s own auto-acknowledgment email)'],
          ['When', '<b>Monday to Thursday, 7:00 AM to 6:00 PM only.</b> Closed Fridays.'],
          ['Ask for', 'Land Records Section, <b>Window 3</b>'],
          ['Reference', '<b>SMD-SCS-INC-26-172</b> (SMD\'s letter to Mr. Inocalla of 22 September 2026)'],
          ['Calling for', 'Mr. <b>Allan V. Inocalla</b>, through Mr. <b>Jonathan Zschoche</b>, whom Mr. Inocalla authorized in writing on 3 September 2026'],
          ['Goal', 'Confirm the <b>ready records are still held</b> for pickup, the <b>fee</b>, and <b>who may pick up</b>. Then check whether the <b>24 September supplementary request</b> (two related plans) was received and whether those plans are available.']],
         [2.6*cm, 14.8*cm], head=False),

    Paragraph('Ground rules', H2),
    Paragraph('1. You are only <b>checking availability, fees and pickup</b>. Do not pay or promise payment on the phone. SMD does not take e-payment, so fees are paid at pickup.', N),
    Paragraph('2. Do not agree to drop or change any request. If they suggest it: <i>"I\'ll pass that to Mr. Zschoche and Mr. Inocalla."</i>', N),
    Paragraph('3. Get the <b>name and position</b> of the person you talk to, and ask them to <b>confirm by email to jonathan@hayuma.org</b>. That address is the one in this email thread. Mr. Inocalla (shiraction2@gmail.com) is copied.', N),
    Paragraph('4. <b>This call is for Mr. Inocalla only.</b> Do not mention the Keesey / Mercedes requests. If you also have to call about those, end this call first, or say clearly that it is a separate matter.', N),

    Paragraph('1. Opening', H2),
    say('Good morning po. This is Kristyle, calling on behalf of Mr. Allan Inocalla, the registered owner of OCT P-1616, through Mr. Jonathan Zschoche. '
        'It\'s about your Reference Code SMD-SCS-INC-26-172, the request for survey plan Psu-143364, Lot 4, and the GPPC for BLBM No. 1 in Paracale.'),

    Paragraph('2. The records already ready for release (your email of 22 September)', H2),
    Paragraph('SMD emailed on 22 September that these are ready at Window 3, Land Records Section, for a fee of <b>PHP 125.00</b>. '
              'Their letter said the items were enclosed, but only the letter was attached to the email.', N),
    say('Are these records still being held for pickup at Window 3?'),
    grid([['', 'Record', 'Still held?', 'Certified?', 'Fee', 'Notes'],
          ['a', '<b>GPPC Certification</b> for BLBM No. 1, Bo. Batobalani', box, box, '', ''],
          ['b', 'Certified copy of survey plan <b>Psu-143364</b> (Lot 4, OCT P-1616)', box, box, '', ''],
          ['c', '<b>Lot data computation</b> of Lot 4, Psu-143364', box, box, '', '']], W),
    Paragraph('<b>Ask:</b> Does the PHP 125.00 cover all three items? If not, what is the total?', N),

    Paragraph('3. The supplementary request of 24 September (two related plans)', H2),
    Paragraph('On 24 September, in the same email thread, we asked for two more plans. SMD\'s reply that day only covered payment and pickup. '
              'It did not say whether these plans were found.', N),
    say('On 24 September we also asked, in the same thread, for two related survey plans of the Inocalla family land, with their lot data computations. '
        'Did your office receive that, and are those plans on file?'),
    grid([['', 'Plan', 'On file?', 'Certified?', 'Fee', 'Ready by / notes'],
          ['d', '<b>Psu-143364 Amd.</b> (the amended plan). It covers Lot 1 (OCT P-1615), Lot 7 (OCT P-1516) and Lot 8 (OCT P-1617). With the lot data computations.', box, box, '', ''],
          ['e', '<b>Psu-143363</b> and/or <b>Psu-143363 Amd.</b> Lot 5 is covered by TCT T-20757. With the lot data computations.', box, box, '', '']], W),
    Paragraph('<b>Also ask:</b> Did the supplement get its own reference code? If either plan is <b>not on file</b>, where should we look for it '
              '(PENRO / CENRO Camarines Norte, or the Land Management Bureau)? Can SMD certify that it isn\'t on file? '
              'Can d and e be released <b>together with</b> a to c in one pickup?', N),

    Paragraph('4. Pickup', H2),
    Paragraph('Mr. Inocalla\'s representative, <b>Mr. Marlon Malaluan</b>, would pick up. He has Mr. Inocalla\'s written authorization dated 5 October 2026, '
              'which covers DENR Surveys and Mapping. The authorization is <b>not notarized</b>.', N),
    say('Mr. Inocalla\'s representative, Mr. Marlon Malaluan, will pick up. He\'ll bring Mr. Inocalla\'s signed authorization, a copy of Mr. Inocalla\'s ID, '
        'and his own valid ID. Is that enough, or does the authorization need to be notarized?'),
    grid([['Total fee for everything that is ready', B + B],
          ['Authorization accepted without notarization?', '[ ] Yes  [ ] No: needs ' + B],
          ['Anything else to bring (request slip, the 22 Sep letter, IDs)?', B + B],
          ['Expected ready date for d and e', B + B],
          ['Can everything be released in one pickup?', '[ ] Yes  [ ] No']],
         [8.5*cm, 8.9*cm], head=False),

    Paragraph('5. Closing', H2),
    say('Thank you very much po, your office has been very helpful. May I have your name and position for our record? '
        'And could you please confirm the fee and the pickup arrangement by email to jonathan@hayuma.org?'),

    Paragraph('Call record', H2),
    grid([['Date and time of call', B + B, 'Number used', B],
          ['Spoke to (name)', B + B, 'Position', B],
          ['They will email confirmation?', '[ ] Yes  [ ] No', 'Anything they asked of us', B]],
         [3.6*cm, 5.2*cm, 3.6*cm, 5.0*cm], head=False),
    Spacer(1, 6),
    Paragraph('<b>After the call:</b> send Jonathan a photo of this sheet, or type up the answers, the same day. Do not send Mr. Malaluan to Legazpi until SMD confirms '
              'the records are held and his authorization will be accepted. Everything he receives goes to Mr. Inocalla.', N),
]

doc = SimpleDocTemplate('SMD_ALLAN_INOCALLA_CALL_SHEET_Kristyle.pdf', pagesize=letter, leftMargin=2.1*cm, rightMargin=2.1*cm,
                        topMargin=1.6*cm, bottomMargin=1.5*cm, title='SMD call sheet: Allan Inocalla (Kristyle)', author='LandTek')
foot = lambda c, d: (c.setFont('Helvetica', 7.5), c.drawRightString(letter[0]-2.1*cm, 1*cm, f'Inocalla · SMD call sheet · page {d.page}'))
doc.build(story, onFirstPage=foot, onLaterPages=foot)
print('built')
