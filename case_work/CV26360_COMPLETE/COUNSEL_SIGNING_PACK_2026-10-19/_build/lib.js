// Shared pleading helpers: 8.5x13 long bond, Times New Roman, Barandon's filed format (01-08 MSJ, 24 Apr 2026).
const d = require('docx');
const { Paragraph, TextRun, Table, TableRow, TableCell, WidthType, BorderStyle, AlignmentType,
        Header, Footer, PageNumber, ShadingType, TabStopType } = d;

const FONT = 'Times New Roman';
const SZ = 24; // 12 pt
const NONE = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const NOB = { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE };
const LINE = { style: BorderStyle.SINGLE, size: 4, color: '000000' };

// "[[...]]" segments render as yellow-highlighted counsel blanks / decisions.
function runs(text, o = {}) {
  const out = [];
  text.split(/(\[\[[\s\S]*?\]\])/).forEach(seg => {
    if (!seg) return;
    if (seg.startsWith('[[')) {
      out.push(new TextRun({ text: '[' + seg.slice(2, -2) + ']', font: FONT, size: o.size || SZ,
        bold: o.bold, italics: o.italics, highlight: 'yellow' }));
    } else {
      // **bold** inside plain text
      seg.split(/(\*\*[^*]+\*\*)/).forEach(s => {
        if (!s) return;
        const b = s.startsWith('**');
        out.push(new TextRun({ text: b ? s.slice(2, -2) : s, font: FONT, size: o.size || SZ,
          bold: o.bold || b, italics: o.italics, underline: o.underline ? {} : undefined }));
      });
    }
  });
  return out;
}

const P = (text, o = {}) => new Paragraph({
  children: runs(text, o),
  alignment: o.align || AlignmentType.JUSTIFIED,
  spacing: { after: o.after ?? 200, line: o.line || 360, before: o.before || 0 },
  indent: o.indent,
  keepNext: o.keepNext,
});
const C = (text, o = {}) => P(text, { ...o, align: AlignmentType.CENTER, after: o.after ?? 0, line: o.line || 240 });
const blank = () => new Paragraph({ children: [], spacing: { after: 0 } });

// numbered body paragraph, first-line indent like counsel's filings
const N = (n, text, o = {}) => P(`${n}.  ${text}`, { ...o, indent: { firstLine: 720 } });
// lettered sub-item, block-indented
const L = (letter, text) => P(`(${letter})  ${text}`, { indent: { left: 720 } });
const Q = (text) => P(text, { indent: { left: 1080, right: 720 }, line: 276 });

function courtHead() {
  return [
    C('Republic of the Philippines'),
    C('MUNICIPAL TRIAL COURT OF MERCEDES', { bold: true }),
    C('Fifth Judicial Region'),
    C('Mercedes, Camarines Norte', { after: 360 }),
  ];
}

const FOR_LINE = 'For: ACCION REIVINDICATORIA, RECOVERY OF POSSESSION, DECLARATION OF NULLITY OF DEED OF ABSOLUTE SALE, CANCELLATION OF TRANSFER CERTIFICATE OF TITLE NO. 079-2021002126 AND DECLARATION OF REAL PROPERTY ARP NO. GR-2023-II-07-001-00256, ACCOUNTING, AND DAMAGES';

function caption() {
  const cell = (children, w) => new TableCell({ children, width: { size: w, type: WidthType.DXA }, borders: NOB,
    margins: { top: 0, bottom: 0, left: 0, right: 120 } });
  const left = [
    P('PATRICIA KEESEY ZSCHOCHE, herein represented by her Attorney-in-fact JONATHAN PAUL ZSCHOCHE,', { align: AlignmentType.LEFT, line: 240, after: 0 }),
    P('Plaintiff,', { align: AlignmentType.LEFT, line: 240, indent: { left: 2160 }, after: 160 }),
    P('– versus –', { align: AlignmentType.LEFT, line: 240, indent: { left: 1080 }, after: 160 }),
    P('SPOUSES EFREN BALANE and GLORIA BALANE, SPOUSES JOMIL TORRALBA and PRINCESS BALANE TORRALBA, and ENGR. ERWIN BALANE and all other person/s deriving rights from them or acting in their behalves,', { align: AlignmentType.LEFT, line: 240, after: 0 }),
    P('Defendants.', { align: AlignmentType.LEFT, line: 240, indent: { left: 2160 }, after: 0 }),
  ];
  const right = [
    P('CIVIL CASE NO. 26-360', { bold: true, align: AlignmentType.LEFT, line: 240, after: 160 }),
    P(FOR_LINE, { align: AlignmentType.LEFT, line: 240, after: 0, size: 20 }),
  ];
  return [
    new Table({ width: { size: 8640, type: WidthType.DXA }, columnWidths: [4800, 3840], borders: NOB,
      rows: [new TableRow({ children: [cell(left, 4800), cell(right, 3840)] })] }),
    P('x - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - x', { align: AlignmentType.LEFT, line: 240, after: 240 }),
  ];
}

const title = (t, sub) => [C(t, { bold: true, after: sub ? 0 : 240 }), ...(sub ? [C(sub, { italics: true, after: 240 })] : [])];

// Signature block exactly as on counsel's filed MSJ of 24 April 2026 (01-08, p. 5).
function signature(dateLine) {
  const S = (t, o = {}) => P(t, { align: AlignmentType.LEFT, line: 240, after: 0, indent: { left: 3600 }, ...o });
  return [
    P(dateLine, { indent: { firstLine: 720 }, before: 120 }),
    blank(), blank(),
    S('BONIFACIO T. BARANDON, JR.', { bold: true }),
    S('Counsel for the Plaintiff'),
    S('IBP O.R. No. 584899 – 01/03/2026'),
    S('IBP Roll No. 40309 – 05/03/1995'),
    S('PTR No. 3034208 W – 01/05/2026'),
    S('MCLE Compliance No. VIII-0013478'),
    S('Valid until 04/14/2028', { after: 200 }),
    S('BARANDON LAW OFFICES', { bold: true }),
    S('Traders’ Road corner Shoppers’ Street'),
    S('Central Plaza Complex, Brgy. Lag-on,'),
    S('Daet, Camarines Norte'),
    S('PLDT Tel. No. (054) 885-11-92'),
    S('Cellphone Nos. 09189074198 & 09209759098'),
    S('E-mail Address: barandon_lawoffice@yahoo.com', { after: 360 }),
  ];
}

function copyFurnished() {
  const S = (t, o = {}) => P(t, { align: AlignmentType.LEFT, line: 240, after: 0, ...o });
  return [
    S('Copy furnished:', { after: 160 }),
    S('ATTY. RONALD RAMOS', { bold: true }),
    S('Counsel for the Defendants'),
    S('Vivencio St., Brgy. II,'),
    S('Daet, Camarines Norte'),
    S('r.a.ramoslawoffice@gmail.com', { after: 240 }),
    P('EXPLANATION (Rule 13, Section 11): [[Counsel: state the mode of service on opposing counsel and, if not personal, the reason.]]', { line: 276 }),
  ];
}

function doc(children, headerText) {
  return new d.Document({
    styles: { default: { document: { run: { font: FONT, size: SZ } } } },
    sections: [{
      properties: { page: { size: { width: 12240, height: 18720 },
        margin: { top: 1440, bottom: 1440, left: 2160, right: 1440, header: 720, footer: 720 } } },
      headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: headerText, font: FONT, size: 16, color: 'C00000', bold: true })] })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20, highlight: 'none' })] })] }) },
      children,
    }],
  });
}

const DRAFT_HDR = 'DRAFT FOR COUNSEL’S REVIEW AND SIGNATURE · NOT FILED · yellow = counsel to complete · remove this header before filing';

module.exports = { d, P, C, N, L, Q, blank, runs, caption, courtHead, title, signature, copyFurnished, doc, DRAFT_HDR, FONT, NOB, LINE };
