#!/usr/bin/env python3
"""Render the Provincial packet (cover letter + Petition + Annex R) to one folio PDF
via headless Chrome. Strips INTERNAL sections, blockquote notes and [OPERATOR] tags.
Usage: python3 render_provincial_packet.py
"""
import re, subprocess, html, pathlib

MWK = pathlib.Path("/Users/jonathanzschoche/landtek/case_work/MWK-001")
SRC_MAIN = MWK / "DEMAND_PROVINCIAL_OVERSIGHT_2026-09.md"
SRC_R = MWK / "RECORDS_RELEASE_SCHEDULE_2026-09.md"
OUT_HTML = MWK / "PROVINCIAL_PACKET_2026-09.html"
OUT_PDF = MWK / "PROVINCIAL_PACKET_2026-09.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`\[(OPERATOR|HUMAN VERIFY|OCR)[^\]]*\]`", "", s)
    s = re.sub(r"\[(OPERATOR|HUMAN VERIFY|OCR)[^\]]*\]", "", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", s, flags=re.S)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s, flags=re.S)
    return s


def strip_internal(text):
    i = text.find("\n# INTERNAL")
    return text[:i] if i >= 0 else text


def md_to_html(text, drop_h1=()):
    out, para, table, lst = [], [], [], None

    def flush_para():
        nonlocal para
        if para:
            t = " ".join(x.strip() for x in para)
            if t.strip():
                out.append(f"<p>{inline(t)}</p>")
            para = []

    def flush_table():
        nonlocal table
        if table:
            rows = [r for r in table if not re.match(r"^\|?\s*-{2,}", r.strip("| "))]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
            if cells:
                h = "".join(f"<th>{inline(c)}</th>" for c in cells[0])
                b = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
                out.append(f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>")
            table = []

    def close_list():
        nonlocal lst
        if lst:
            out.append(f"</{lst}>"); lst = None

    lines = text.splitlines()
    for ln in lines:
        s = ln.rstrip()
        if s.startswith(">"):
            continue
        if s.strip() == "---":
            flush_para(); flush_table(); close_list(); continue
        if s.startswith("|"):
            flush_para(); close_list(); table.append(s); continue
        else:
            flush_table()
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            flush_para(); close_list()
            lvl, t = len(m.group(1)), m.group(2)
            if lvl == 1:
                if any(t.startswith(d) for d in drop_h1):
                    continue
                out.append(f'<h1 class="brk">{inline(t)}</h1>')
            else:
                out.append(f"<h{lvl}>{inline(t)}</h{lvl}>")
            continue
        m = re.match(r"^\s{0,4}(\d+)\.\s+(.*)", s)
        if m and not para:
            if lst != "ol":
                close_list(); out.append("<ol>"); lst = "ol"
            out.append(f"<li>{inline(m.group(2))}</li>"); continue
        m = re.match(r"^\s*-\s+(.*)", s)
        if m and not para:
            if lst != "ul":
                close_list(); out.append("<ul>"); lst = "ul"
            out.append(f"<li>{inline(m.group(1))}</li>"); continue
        m = re.match(r"^\s{2,}\(([a-z])\)\s+(.*)", s)
        if m:
            flush_para()
            out.append(f'<p class="sub">({m.group(1)}) {inline(m.group(2))}</p>'); continue
        if lst and s.startswith("   ") and s.strip():
            # re-inline the whole item so bold/italic spans survive the line break
            prev = out[-1]
            raw = re.sub(r"</?[bi]>", lambda m: "**" if m.group(0) in ("<b>", "</b>") else "*", prev[4:-5])
            raw = html.unescape(raw)
            out[-1] = "<li>" + inline(raw + " " + s.strip()) + "</li>"; continue
        if not s.strip():
            flush_para(); close_list(); continue
        # address / signature blocks: keep line breaks for short bold/plain lines
        if re.match(r"^(\*\*[A-Z].*|\*Copy furnished:\*|\*Attention.*|Provincial .*|Republic of the Philippines|Province of Camarines Norte|Municipal Hall.*|jonzschoche@.*|Attorney-in-Fact.*|Heir, Estate.*|Dasmariñas.*|Respectfully,|\*\*TO:\*\*|___ September 2026|Dear Governor.*|\*Enclosure.*)", s) and len(s) < 260 and s.count("**") % 2 == 0 and not (s.startswith("**") and s.rstrip().endswith((".", ":")) and s.count("**") == 2 and len(s) > 90):
            flush_para()
            out.append(f'<p class="line">{inline(s)}</p>'); continue
        para.append(s)
    flush_para(); flush_table(); close_list()
    return "\n".join(out)


main = strip_internal(SRC_MAIN.read_text())
annex = strip_internal(SRC_R.read_text())
_all = md_to_html(main, drop_h1=("PROVINCIAL PACKET", "COVER LETTER"))
_cut = _all.index('<h1 class="brk">')
body = '<div class="cover">' + _all[:_cut] + '</div>' + _all[_cut:] + md_to_html(annex)

CSS = """
@page { size: 8.5in 13in; margin: 1in 1in 0.9in 1in; }
body { font-family: 'Times New Roman', Times, serif; font-size: 12pt; line-height: 1.32; color: #000; }
h1 { font-size: 14pt; text-align: center; margin: 0 0 14pt 0; letter-spacing: .3px; }
h1.brk { page-break-before: always; }
h2 { font-size: 12pt; margin: 16pt 0 6pt 0; text-transform: uppercase; }
h3 { font-size: 12pt; margin: 12pt 0 4pt 0; }
p { margin: 0 0 9pt 0; text-align: justify; }
p.line { margin: 0; text-align: left; }
p.line + p:not(.line) { margin-top: 9pt; }
p.sub { margin: 0 0 5pt 0.6in; }
ol, ul { margin: 0 0 9pt 0.35in; padding: 0; }
li { margin-bottom: 5pt; text-align: justify; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; line-height: 1.2; margin: 6pt 0 12pt 0; table-layout: fixed; }
th, td { border: 0.5pt solid #000; padding: 3pt 4pt; vertical-align: top; word-wrap: break-word; }
th { background: #eee; text-align: left; }
tr { page-break-inside: avoid; }
.cover { font-size: 11pt; line-height: 1.25; }
.cover p { margin-bottom: 7pt; }
"""
OUT_HTML.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>Provincial Packet</title><style>{CSS}</style></head><body>{body}</body></html>")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={OUT_PDF}", str(OUT_HTML)], check=True, capture_output=True, timeout=120)
print(OUT_PDF, OUT_PDF.stat().st_size)
