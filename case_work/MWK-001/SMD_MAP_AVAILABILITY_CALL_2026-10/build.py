# Kristyle's call sheet: DENR R5 SMD, check availability of the MWK maps requested 5-7 Oct 2026. Run: python3 build.py
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether

ss = getSampleStyleSheet()
N = ParagraphStyle('N', parent=ss['Normal'], fontName='Helvetica', fontSize=9.6, leading=12.4, spaceAfter=3)
S = ParagraphStyle('S', parent=N, fontSize=8.4, leading=10.4, spaceAfter=0)
SAY = ParagraphStyle('SAY', parent=N, leftIndent=10, borderPadding=(5, 6, 5, 6), backColor=colors.HexColor('#EEF3F8'),
                     borderColor=colors.HexColor('#B9CCE0'), borderWidth=0.6, spaceBefore=3, spaceAfter=7)
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
plans = [
    ('1', 'Psd-05-008861', 'Lot 2-X-1 (TCT T-23796)'),
    ('2', 'Pcs-051607-000932', 'Lot 2-X-1-B + T-32912/32913/32914 (consolidation, approved 21 Jan 1994)'),
    ('3', 'Psd-05-023697', 'Lot 2, Pcs-051607-000932 (TCT T-45616)'),
    ('4', 'Psd-05-017527', 'Lot 2-X-4 (TCT T-32916)'),
    ('5', 'Psd-051607-014971', 'Lot 2-X-6 (TCT T-32917): Lots 2-X-6-A to V'),
    ('6', 'Psd-05-019929', 'Lot 2-X-6-I (TCT T-38838)'),
    ('7', 'Psd-05-026197', 'Lot 2-X-6-I-4 (TCT T-49061)'),
    ('8', 'Psd-05-025374', 'Lot 2-X-6-N (TCT T-47656)'),
    ('9', 'Psd-05-026614', 'Lot 2-X-6-R (TCT T-49037)'),
    ('10', 'Lot 2-X-6-T plan: number unconfirmed', 'Lot 2-X-6-T (TCT T-47657). Titles read it as "Psd-05-0500..." or "Psd-358645". Ask SMD for the correct number.'),
]
W = [0.8*cm, 3.6*cm, 5.5*cm, 2.6*cm, 1.8*cm, 3.1*cm]
WC = [0.7*cm, 6.9*cm, 2.6*cm, 2.6*cm, 1.7*cm, 2.9*cm]

story = [
    Paragraph('Call sheet: DENR Region V, Surveys and Mapping Division', H1),
    Paragraph('For <b>Kristyle</b> · prepared 7 October 2026 · Heirs of Mary Worrick Keesey (MWK), Mercedes, Camarines Norte', N),
    Spacer(1, 4),
    grid([['Call', '<b>SMD Hotline 0917 139 0360</b>, or <b>0956 241 2769</b> (from SMD\'s own auto-acknowledgment email)'],
          ['When', '<b>Monday to Thursday, 7:00 AM to 6:00 PM only.</b> Closed Fridays.'],
          ['Ask for', 'Land Records Section (Window 3), or whoever handles requests for certified copies of survey plans'],
          ['Calling for', 'Mr. <b>Jonathan Paul Zschoche</b>, attorney-in-fact of Patricia Keesey Zschoche, heir of Mary Worrick Keesey'],
          ['Goal', 'Find out <b>which maps they actually have</b>, whether certified copies can be issued, the fee, and when they will be ready. Also get the <b>date they received</b> each of our three emails.']],
         [2.6*cm, 14.8*cm], head=False),

    Paragraph('Ground rules', H2),
    Paragraph('1. You are only <b>checking availability, receipt and fees</b>. Do not discuss Lot 402, the PNP patent or the Municipality\'s claim. If they ask: <i>"Mr. Zschoche has explained everything in his letter, and he will reply in writing."</i>', N),
    Paragraph('2. Do not agree to drop, change or shorten any request. If they suggest it: <i>"I\'ll pass that to Mr. Zschoche."</i>', N),
    Paragraph('3. Do not pay or promise payment on the phone. SMD does not take e-payment, so fees are paid at pickup.', N),
    Paragraph('4. Get the <b>name and position</b> of the person you talk to. At the end, ask them to <b>confirm by email to jonzschoche@gmail.com</b>.', N),
    Paragraph('5. This call is for MWK only. Do not bring up any other client\'s request.', N),

    Paragraph('1. Opening', H2),
    say('Good morning po. This is Kristyle, calling for Mr. Jonathan Zschoche, attorney-in-fact for the heirs of Mary Worrick Keesey of Mercedes, '
        'Camarines Norte. We emailed three requests to your office this week, addressed to ARD Ronnel Astor. I\'m calling to confirm you received them, '
        'and to check whether the maps we asked for are available.'),

    Paragraph('2. Were our emails received?', H2),
    Paragraph('All three were sent to smd.r5@denr.gov.ph. Ask for the <b>date received</b> and any <b>reference code</b> for each one.', N),
    grid([['Sent', 'What it is', 'Received? (date)', 'Reference code'],
          ['Mon 5 Oct, 4:48 PM', 'Reply on <b>Lot 402</b>, in the thread <b>Ref. DENR-TS-OSS-2026-1092</b>', B, B],
          ['Tue 6 Oct', 'Request for <b>certified copies of 10 subdivision plans in Lot 2-X, (LRC) Psd-256008</b>', B, B],
          ['Wed 7 Oct', 'Request for <b>Cad 1186-D, Case 5</b> (Mercedes Cadastre) map sheets and lot data, Lots 401 to 405', B, B]],
         [2.8*cm, 8.2*cm, 3.2*cm, 3.2*cm]),
    say('Could you please confirm the date each one was received, and send us an acknowledgment by email?'),

    KeepTogether([Paragraph('3. Cadastral map: Cad 1186-D, Case 5 (most important)', H2),
    say('For Cad 1186-D, Case 5, Mercedes, Barangay V (Poblacion), does your office have the following, and can you issue certified copies?'),
    grid([['', 'Record', 'Available?', 'Certified copy?', 'Fee', 'Ready by / notes'],
          ['a', 'Map sheet(s) showing <b>Lots 401, 402, 403, 404, 405</b> and the adjoining titled lot, Lot 2-A, (LRA) Psd-221861', box, box, '', ''],
          ['b', '<b>Lot data computation and technical descriptions</b> of Lots 401 to 405 as originally surveyed (Lot 402 before it was split into 402-A and 402-B)', box, box, '', ''],
          ['c', '<b>Approval date</b> of Cad 1186-D, Case 5, and the approving officer', box, box, '', ''],
          ['d', '<b>List of claimants</b> (survey claimant record) for Lots 401 to 405', box, box, '', ''],
          ['e', 'Csd-05-019916-D (the 402-A / 402-B subdivision plan), with its lot data computation. This was asked for in the 5 Oct Lot 402 letter.', box, box, '', '']],
         WC)]),
    Paragraph('<b>Also ask:</b> Is "Case 5" the correct case number for Barangay V? If SMD does not keep any of these records, <b>which office does</b> '
              '(PENRO / CENRO Camarines Norte, the Land Management Bureau in Manila, or another office), and who should we write to?', N),

    KeepTogether([
        Paragraph('4. The 10 subdivision plans in Lot 2-X', H2),
        say('For our 6 October request, can you check which of these approved plans are on file in your office, and whether you can issue certified copies with the lot data computation?'),
        grid([['#', 'Plan', 'Lot subdivided', 'On file?', 'Fee', 'Ready by / notes']] +
             [[n, f'<b>{p}</b>', l, box, '', ''] for n, p, l in plans], W)]),
    Paragraph('If any plan is <b>not on file</b>, ask: <i>"Where should we look for it?"</i> Also ask: <i>"Can your office issue a certification that it isn\'t on file?"</i>', N),

    Paragraph('5. Fees and pickup', H2),
    grid([['Total fee for everything that is available', B + B],
          ['Can all of it be released together in one pickup?', '[ ] Yes  [ ] No'],
          ['Expected ready date', B + B],
          ['Who can pick up? Is a representative with Mr. Zschoche\'s SPA and a valid ID enough?', B + B],
          ['Anything to bring (request slip, reference letter, IDs)?', B + B]],
         [8.5*cm, 8.9*cm], head=False),

    Paragraph('6. Closing', H2),
    say('Thank you very much po. May I have your name and position for our record? And could you please confirm the received dates and the fees by email to jonzschoche@gmail.com?'),

    Paragraph('Call record', H2),
    grid([['Date and time of call', B + B, 'Number used', B],
          ['Spoke to (name)', B + B, 'Position', B],
          ['They will email confirmation?', '[ ] Yes  [ ] No', 'Anything they asked of us', B]],
         [3.6*cm, 5.2*cm, 3.6*cm, 5.0*cm], head=False),
    Spacer(1, 6),
    Paragraph('<b>After the call:</b> send Jonathan a photo of this sheet, or type up the answers, the same day. A received date told by phone is only a lead. '
              'The 15-day clock starts from the <b>written</b> acknowledgment or reply, never from the send date.', N),
]

doc = SimpleDocTemplate('SMD_MAP_AVAILABILITY_CALL_SHEET_Kristyle.pdf', pagesize=letter, leftMargin=2.1*cm, rightMargin=2.1*cm,
                        topMargin=1.6*cm, bottomMargin=1.5*cm, title='SMD map availability call sheet (Kristyle)', author='LandTek')
doc.build(story, onLaterPages=lambda c, d: (c.setFont('Helvetica', 7.5), c.drawRightString(letter[0]-2.1*cm, 1*cm, f'MWK · SMD call sheet · page {d.page}')),
          onFirstPage=lambda c, d: (c.setFont('Helvetica', 7.5), c.drawRightString(letter[0]-2.1*cm, 1*cm, f'MWK · SMD call sheet · page {d.page}')))
print('built')
