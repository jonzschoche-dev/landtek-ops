#!/usr/bin/env node
/**
 * render_pleading.js — LandTek pleading renderer
 *
 * Turns a working draft in Markdown (the single source of truth, kept under
 * case_work/<matter>/) into a Philippine trial-court filing-format .docx.
 * The draft is never duplicated: edit the .md, re-render.
 *
 * Page and type follow the Efficient Use of Paper Rule (A.M. No. 11-9-4-SC):
 *   13" x 8.5" long bond · 14-pt · single-spaced, 1.5 spaces between paragraphs
 *   margins: left 1.5" · top 1.2" · right 1.0" · bottom 1.0" · pages numbered
 * (Counsel should confirm the current text of the rule before filing.)
 *
 * Draft markers carried over from the source, all deletable in one pass:
 *   ( ? ) / ( hint ? )   -> a fill-in blank, plus the hint as a gray note
 *   [V ...] [O ...]      -> provenance tag, rendered as a gray note
 *   {{...}}              -> drafter's note to counsel, rendered as a gray note
 * Source files use the bracket glyphs; see NOTE_OPEN/NOTE_CLOSE below.
 *
 * Source directives (HTML comments — invisible when the .md is read):
 *   <!-- align:right -->   next block is indented right (signature blocks)
 *   <!-- align:center -->  next block is centered
 *   <!-- pagebreak -->     page break here
 *   <!-- filing:skip -->   ... <!-- /filing:skip --> omit from the filing copy
 *   <!-- section:NAME -->  ... <!-- /section --> one execution copy among several
 *                          in one source file; select it with "section" in the job.
 *                          With "section" set, everything outside it is dropped.
 *
 * Usage: node scripts/render_pleading.js <job.json> [more.json ...]
 */

const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, Footer, PageNumber, PageBreak,
} = require('docx');

// ---------- page geometry (DXA: 1440 = 1 inch) ----------
const IN = 1440;
const PAGE = { width: Math.round(8.5 * IN), height: 13 * IN };
const MARGIN = { top: Math.round(1.2 * IN), right: 1 * IN, bottom: 1 * IN, left: Math.round(1.5 * IN) };
const CONTENT_W = PAGE.width - MARGIN.left - MARGIN.right; // 8640

const BODY_SIZE = 28;      // 14 pt, in half-points
const NOTE_SIZE = 20;      // 10 pt gray notes
const TABLE_SIZE = 20;     // tables need to fit
const NOTE_COLOR = '7A7A7A';
const LINE_SINGLE = 240;
const PARA_GAP = 360;      // 1.5 lines between paragraphs
const BLANK = '__________';

const NOTE_OPEN = '⟦';   // ⟦
const NOTE_CLOSE = '⟧';  // ⟧

// ---------- inline formatting ----------

/** Drop markup that must never survive into the rendered document. */
const cleanInline = (s) => s
  .replace(/\*\*/g, '')
  .replace(/(^|[\s(])\*([^*]+)\*/g, '$1$2')
  .replace(/`/g, '')
  .trim();

/** Strip drafter's-note spans out of a string; returns [clean, notes[]]. */
function extractNotes(s) {
  const notes = [];
  const rx = new RegExp(NOTE_OPEN + '([\\s\\S]*?)' + NOTE_CLOSE, 'g');
  const clean = s.replace(rx, (_, inner) => { notes.push(inner.trim()); return ''; });
  return [clean.replace(/\s{2,}/g, ' ').trim(), notes];
}

/** Split a source line into styled runs, converting draft markers to notes/blanks. */
function runs(text, opts = {}) {
  const base = { size: opts.size || BODY_SIZE };
  const out = [];
  const push = (t, extra = {}) => {
    const v = t.replace(/`/g, '');
    if (v) out.push(new TextRun({ text: v, ...base, ...extra }));
  };
  const note = (t) => out.push(new TextRun({
    text: cleanInline(t), size: NOTE_SIZE, italics: true, color: NOTE_COLOR,
  }));

  // Tokenise on the markers we care about. Order matters: notes before parens.
  const pattern = new RegExp(
    `(\\*\\*[^*]+\\*\\*)` +                       // **bold**
    `|(\\*[^*\\n]+\\*)` +                         // *italic*
    `|(${NOTE_OPEN}[\\s\\S]*?${NOTE_CLOSE})` +    // drafter's note
    `|(\\[(?:V|O|inferred_strong|inferred_weak)\\b[^\\]]*\\])` + // provenance tag
    `|(\\([^()]*\\?[^()]*\\))`,                   // ( ? ) blank, no nesting
    'g'
  );

  let last = 0, m;
  while ((m = pattern.exec(text)) !== null) {
    push(text.slice(last, m.index));
    last = pattern.lastIndex;
    const [tok, bold, ital, drafter, prov, blank] = m;
    if (bold) push(bold.slice(2, -2), { bold: true });
    else if (ital) push(ital.slice(1, -1), { italics: true });
    else if (drafter) note(' [' + drafter.slice(1, -1).trim() + '] ');
    else if (prov) note(' ' + prov + ' ');
    else if (blank) {
      // ( ? ) -> bare blank; ( hint ? ) -> blank + the hint as a note
      const inner = tok.slice(1, -1).replace(/\?/g, '').trim().replace(/^[—–-]\s*/, '');
      push(BLANK, { bold: false });
      if (inner) note(' [' + inner + '] ');
    } else push(cleanInline(tok) === tok ? tok : cleanInline(tok));
  }
  push(text.slice(last));
  return out.length ? out : [new TextRun({ text: '', ...base })];
}

const para = (children, o = {}) => new Paragraph({
  children,
  alignment: o.alignment,
  spacing: { after: o.after === undefined ? PARA_GAP : o.after, line: LINE_SINGLE },
  indent: o.indent,
  border: o.border,
  keepNext: o.keepNext,
  pageBreakBefore: o.pageBreakBefore,
});

const line = (text, o = {}) => para(runs(text, o), o);

// ---------- tables ----------

function splitRow(raw) {
  return raw.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

function buildTable(rows) {
  const header = splitRow(rows[0]);
  const bodyRows = rows.slice(2).map(splitRow); // rows[1] is the --- separator
  const n = header.length;
  const colW = Math.floor(CONTENT_W / n);
  const widths = Array(n).fill(colW);
  widths[n - 1] = CONTENT_W - colW * (n - 1); // absorb rounding

  const cell = (txt, isHeader, w) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: isHeader ? { type: ShadingType.CLEAR, fill: 'EDEDED' } : undefined,
    margins: { top: 60, bottom: 60, left: 90, right: 90 },
    children: [new Paragraph({
      children: runs(txt, { size: TABLE_SIZE }).map((r) => r),
      spacing: { after: 0, line: LINE_SINGLE },
    })],
  });

  const mk = (cells, isHeader) => new TableRow({
    tableHeader: isHeader,
    children: cells.slice(0, n).concat(Array(Math.max(0, n - cells.length)).fill(''))
      .map((c, i) => cell(isHeader ? c.replace(/\*\*/g, '') : c, isHeader, widths[i])),
  });

  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_W, type: WidthType.DXA },
    rows: [mk(header, true)].concat(bodyRows.map((r) => mk(r, false))),
  });
}

// ---------- caption ----------

function captionBlock(job) {
  if (!job.court || !job.court.length) return [];   // non-pleading (index, tab sheets)
  const kids = [];
  for (const l of job.court) {
    kids.push(line(l, { alignment: AlignmentType.CENTER, after: 0 }));
  }
  kids.push(para([new TextRun({ text: '', size: BODY_SIZE })], { after: PARA_GAP }));

  const leftW = Math.round(CONTENT_W * 0.6);
  const rightW = CONTENT_W - leftW;
  const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const noBorders = { top: none, bottom: none, left: none, right: none,
    insideHorizontal: none, insideVertical: none };

  const stack = (arr, o = {}) => arr.map((t) => (t === ''
    ? para([new TextRun({ text: '', size: BODY_SIZE })], { after: 0 })
    : line(t, { after: 0, ...o })));

  kids.push(new Table({
    columnWidths: [leftW, rightW],
    width: { size: CONTENT_W, type: WidthType.DXA },
    borders: noBorders,
    rows: [new TableRow({
      children: [
        new TableCell({
          width: { size: leftW, type: WidthType.DXA },
          borders: noBorders,
          margins: { right: 180 },
          children: stack(job.captionLeft, { alignment: AlignmentType.JUSTIFIED }),
        }),
        new TableCell({
          width: { size: rightW, type: WidthType.DXA },
          borders: noBorders,
          children: stack(job.captionRight),
        }),
      ],
    })],
  }));

  kids.push(line('x' + '- '.repeat(28) + 'x', { after: PARA_GAP }));
  return kids;
}

// ---------- the draft banner ----------

function draftBanner(job) {
  if (job.noBanner) return [];
  const b = { style: BorderStyle.SINGLE, size: 6, color: '999999' };
  return [
    new Paragraph({
      border: { top: b, bottom: b, left: b, right: b },
      spacing: { after: PARA_GAP, line: LINE_SINGLE },
      shading: { type: ShadingType.CLEAR, fill: 'F4F4F4' },
      children: [
        new TextRun({ text: 'DRAFT — NOT FOR FILING IN THIS FORM. ', bold: true, size: 22 }),
        new TextRun({
          text: 'Prepared by LandTek as work product for counsel. No counsel of record has adopted it. '
            + 'Before filing: fill every ' + BLANK + ' blank, delete every gray italic note, delete this box, '
            + 'and verify all rule and case citations. ',
          size: 22,
        }),
        new TextRun({
          text: 'Page set-up follows A.M. No. 11-9-4-SC (13" x 8.5", 14-pt, margins L1.5/T1.2/R1.0/B1.0).',
          size: 22, italics: true,
        }),
      ],
    }),
  ];
}

// ---------- body parser ----------

function parseBody(md, job) {
  const all = md.split(/\r?\n/);
  // Body starts after the caption divider (x----x) if present, else at the top.
  let i = all.findIndex((l) => /^x[-\s]{3,}x\s*$/.test(l.trim()));
  i = i === -1 ? 0 : i + 1;

  const out = [];
  let mode = null;      // alignment mode, persists until reset or the next heading
  let skipping = false;
  let firstH2 = true;
  let section = null;   // current <!-- section:NAME -->
  const wantSection = job.section || null;

  const alignFor = () => {
    if (mode === 'right') return { indent: { left: Math.round(CONTENT_W * 0.42) }, alignment: AlignmentType.LEFT };
    if (mode === 'center') return { alignment: AlignmentType.CENTER };
    return {};
  };

  while (i < all.length) {
    const raw = all[i];
    const t = raw.trim();

    // directives
    const c = t.match(/^<!--\s*(.+?)\s*-->$/);
    if (c) {
      const d = c[1];
      if (d === 'filing:skip') skipping = true;
      else if (d === '/filing:skip') skipping = false;
      else if (d === '/section') section = null;
      else if (d.startsWith('section:')) section = d.slice(8);
      else if (d === 'pagebreak') out.push(new Paragraph({ children: [new PageBreak()] }));
      else if (d === 'align:reset') mode = null;
      else if (d.startsWith('align:')) mode = d.slice(6);
      i++; continue;
    }
    if (skipping) { i++; continue; }
    if (wantSection && section !== wantSection) { i++; continue; }

    if (!t) { i++; continue; }
    if (/^---+$/.test(t)) { i++; continue; }
    if (t.startsWith('> ')) { i++; continue; }        // drafter blockquote header
    if (t.startsWith('# ')) { i++; continue; }        // doc title lives in the caption

    // tables
    if (t.startsWith('|')) {
      const rows = [];
      while (i < all.length && all[i].trim().startsWith('|')) { rows.push(all[i]); i++; }
      if (rows.length >= 3) {
        out.push(buildTable(rows));
        out.push(para([new TextRun({ text: '', size: 12 })], { after: PARA_GAP }));
      }
      continue;
    }

    // headings
    if (t.startsWith('## ') || t.startsWith('### ')) {
      const h2 = t.startsWith('## ');
      const [clean, notes] = extractNotes(t.replace(/^#{2,3}\s+/, '').trim());
      out.push(new Paragraph({
        alignment: AlignmentType.CENTER,
        pageBreakBefore: h2 && !firstH2,
        keepNext: true,
        spacing: { after: notes.length ? 120 : PARA_GAP, before: h2 ? 0 : 120, line: LINE_SINGLE },
        children: [new TextRun({
          text: cleanInline(clean).toUpperCase(),
          bold: true,
          underline: h2 ? {} : undefined,
          size: BODY_SIZE,
        })],
      }));
      for (const n of notes) {
        out.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: PARA_GAP, line: LINE_SINGLE },
          children: [new TextRun({
            text: '[' + cleanInline(n) + ']', size: NOTE_SIZE, italics: true, color: NOTE_COLOR,
          })],
        }));
      }
      if (h2) firstH2 = false;
      mode = null; i++; continue;
    }

    // bullet / dash item
    if (/^[-*]\s+/.test(t)) {
      out.push(line(t.replace(/^[-*]\s+/, '— '), {
        indent: { left: 720, hanging: 360 }, alignment: AlignmentType.JUSTIFIED,
      }));
      i++; continue;
    }

    // numbered pleading paragraph: 1.1. / 4.6. / (a) / 1.
    const numbered = /^(\d+\.\d*\.?|\([a-z]\)|\d+\.)\s+/.test(t);
    const opts = Object.assign(
      { alignment: numbered ? AlignmentType.JUSTIFIED : AlignmentType.JUSTIFIED },
      alignFor()
    );
    if (numbered && !mode) opts.indent = { firstLine: 720 };
    out.push(line(t, opts));
    i++;
  }
  return out;
}

/** One page per annex: a big tab sheet for the physical binder. */
function tabSheets(job) {
  if (!job.tabSheets || !job.tabSheets.length) return [];
  const out = [];
  job.tabSheets.forEach((t, idx) => {
    const [letter, ...rest] = t.split('|');
    out.push(new Paragraph({
      children: idx === 0 ? [] : [new PageBreak()],
      spacing: { after: 0 },
    }));
    out.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 2600, after: 400, line: LINE_SINGLE },
      children: [new TextRun({ text: 'ANNEX "' + letter.trim() + '"', bold: true, size: 96 })],
    }));
    out.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 200, line: LINE_SINGLE },
      children: runs(rest.join('|').trim(), { size: 28 }),
    }));
    out.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { line: LINE_SINGLE },
      children: [new TextRun({
        text: 'Intestate Estates of Sps. Vicente Inocalla, Sr. and Beatriz Villafria Inocalla',
        italics: true, size: 20, color: NOTE_COLOR,
      })],
    }));
  });
  return out;
}

// ---------- document ----------

function build(job) {
  const children = []
    .concat(draftBanner(job))
    .concat(captionBlock(job))
    .concat(job.source ? parseBody(fs.readFileSync(job.source, 'utf8'), job) : [])
    .concat(tabSheets(job));

  return new Document({
    creator: 'LandTek', title: job.docTitle || '', description: 'Draft pleading — not for filing',
    styles: { default: { document: { run: { font: job.font || 'Times New Roman', size: BODY_SIZE } } } },
    sections: [{
      properties: { page: { size: PAGE, margin: MARGIN } },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            spacing: { before: 120 },
            children: [
              new TextRun({ text: (job.footer || job.docTitle || '') + '  —  page ', size: 18, color: '666666' }),
              new TextRun({ children: [PageNumber.CURRENT], size: 18, color: '666666' }),
              new TextRun({ text: ' of ', size: 18, color: '666666' }),
              new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18, color: '666666' }),
              new TextRun({ text: job.noBanner ? '' : '  —  DRAFT', size: 18, color: '666666' }),
            ],
          })],
        }),
      },
      children,
    }],
  });
}

async function main() {
  const jobs = process.argv.slice(2);
  if (!jobs.length) { console.error('usage: render_pleading.js <job.json> [...]'); process.exit(1); }
  for (const jf of jobs) {
    const job = JSON.parse(fs.readFileSync(jf, 'utf8'));
    const dir = path.dirname(path.resolve(jf));
    if (job.source) job.source = path.resolve(dir, job.source);
    job.output = path.resolve(dir, job.output);
    fs.mkdirSync(path.dirname(job.output), { recursive: true });
    const buf = await Packer.toBuffer(build(job));
    fs.writeFileSync(job.output, buf);
    console.log('wrote', job.output, (buf.length / 1024).toFixed(0) + 'KB');
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
