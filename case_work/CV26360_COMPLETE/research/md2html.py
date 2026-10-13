"""Minimal Markdown -> HTML for the LandTek case files (headings, paragraphs, bold/italic, tables,
bullet and numbered lists, blockquotes, horizontal rules). No external dependencies.

  python3 research/md2html.py IN.md OUT.html "Title"
"""
import re, sys, html

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = s.replace("&amp;rarr;", "&rarr;")
    return s

def convert(md):
    lines = md.splitlines()
    out, i, n = [], 0, len(lines)
    para = []
    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(x.strip() for x in para)) + "</p>")
            para.clear()
    while i < n:
        ln = lines[i]
        st = ln.strip()
        if not st:
            flush_para(); i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", st)
        if m:
            flush_para(); lvl = len(m.group(1)); out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>"); i += 1; continue
        if re.match(r"^-{3,}$", st):
            flush_para(); out.append("<hr>"); i += 1; continue
        if st.startswith("|"):
            flush_para()
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip()); i += 1
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            hdr = cells[0]; body = cells[2:] if len(cells) > 1 and re.match(r"^\|?\s*:?-{2,}", rows[1]) else cells[1:]
            t = ["<table>", "<tr>" + "".join(f"<th>{inline(c)}</th>" for c in hdr) + "</tr>"]
            for r in body:
                t.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            t.append("</table>"); out.extend(t); continue
        if st.startswith(">"):
            flush_para(); q = []
            while i < n and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip()); i += 1
            paras, cur = [], []
            for x in q:
                if x == "":
                    if cur: paras.append(" ".join(cur)); cur = []
                else: cur.append(x)
            if cur: paras.append(" ".join(cur))
            out.append("<blockquote>" + "".join(f"<p>{inline(p)}</p>" for p in paras) + "</blockquote>"); continue
        if re.match(r"^[-*]\s+", st):
            flush_para(); items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                item = re.sub(r"^\s*[-*]\s+", "", lines[i]); i += 1
                while i < n and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) and not lines[i].strip().startswith(("|", "#", ">")):
                    item += " " + lines[i].strip(); i += 1
                items.append(item)
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>"); continue
        if re.match(r"^\d+\.\s+", st):
            flush_para(); items = []
            while i < n and re.match(r"^\s*\d+\.\s+", lines[i]):
                item = re.sub(r"^\s*\d+\.\s+", "", lines[i]); i += 1
                while i < n and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) and not lines[i].strip().startswith(("|", "#", ">")):
                    item += " " + lines[i].strip(); i += 1
                items.append(item)
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>"); continue
        para.append(ln); i += 1
    flush_para()
    return "\n".join(out)

CSS = """@page{size:8.5in 13in;margin:0.9in 0.85in 0.85in 0.85in}
body{font-family:'Times New Roman',Times,serif;font-size:11pt;line-height:1.38;color:#000;margin:0}
h1{font-size:17pt;text-align:center;margin:0 0 4pt 0}h2{font-size:12.5pt;margin:18pt 0 6pt 0;border-bottom:1.2px solid #000;padding-bottom:2pt;page-break-after:avoid}
h3{font-size:11.5pt;margin:13pt 0 4pt 0;page-break-after:avoid}p{margin:0 0 6pt 0;text-align:justify}
table{border-collapse:collapse;width:100%;margin:4pt 0 10pt 0}th,td{border:.6px solid #000;padding:3pt 4.5pt;vertical-align:top;font-size:9.6pt;line-height:1.3;text-align:left}
th{background:#efefef}tr{page-break-inside:avoid}blockquote{margin:6pt 14pt;padding:6pt 10pt;border:1px solid #000;font-size:10.4pt}
blockquote p{margin:0 0 5pt 0}ul,ol{margin:2pt 0 7pt 18pt;padding:0}li{margin:0 0 3pt 0;text-align:justify}hr{border:0;border-top:.8px solid #000;margin:12pt 0}code{font-family:inherit}"""

if __name__ == "__main__":
    src, dst, title = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "Document")
    body = convert(open(src, encoding="utf-8").read())
    open(dst, "w", encoding="utf-8").write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>")
    print("wrote", dst)
