"""Minimal HTML -> Markdown for this case's own documents (h1-h3, p, ul/ol/li, table, b/i, br, div.box)."""
import re
from html.parser import HTMLParser


class MD(HTMLParser):
    def __init__(self):
        super().__init__()
        self.out = []; self.cell = None; self.row = None; self.table = None; self.list = []; self.li_n = 0; self.skip = False

    def _inline(self, s):
        if self.cell is not None: self.cell += s
        else: self.out.append(s)

    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'head', 'title', 'script'): self.skip = True
        elif tag == 'h1': self.out.append('\n# ')
        elif tag == 'h2': self.out.append('\n\n## ')
        elif tag == 'h3': self.out.append('\n\n### ')
        elif tag == 'p': self._inline(' ' if self.cell is not None else '\n\n')
        elif tag == 'div' and any(k == 'class' and v and 'box' in v for k, v in attrs): self.out.append('\n\n> ')
        elif tag in ('ul', 'ol'): self.list.append(tag); self.li_n = 0
        elif tag == 'li':
            self.li_n += 1
            self._inline(('; ' if self.li_n > 1 else '') if self.cell is not None else '\n' + ('- ' if self.list and self.list[-1] == 'ul' else f'{self.li_n}. '))
        elif tag == 'b': self._inline('**')
        elif tag == 'i': self._inline('_')
        elif tag == 'br': self._inline(' ' if self.cell is not None else '  \n')
        elif tag == 'table': self.table = []
        elif tag == 'tr': self.row = []
        elif tag in ('td', 'th'): self.cell = ''

    def handle_endtag(self, tag):
        if tag in ('style', 'head', 'title', 'script'): self.skip = False
        elif tag == 'b': self._inline('**')
        elif tag == 'i': self._inline('_')
        elif tag in ('ul', 'ol'):
            if self.list: self.list.pop()
            if self.cell is None: self.out.append('\n')
        elif tag in ('td', 'th'):
            if self.row is not None:
                self.row.append(self.cell.strip().replace('|', '\\|').replace('\n', ' '))
            self.cell = None
        elif tag == 'tr':
            if self.table is not None and self.row is not None: self.table.append(self.row)
            self.row = None
        elif tag == 'table':
            if self.table:
                w = max(len(r) for r in self.table)
                rows = [r + [''] * (w - len(r)) for r in self.table]
                lines = ['| ' + ' | '.join(rows[0]) + ' |', '|' + '|'.join(['---'] * w) + '|'] + ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]
                self.out.append('\n\n' + '\n'.join(lines) + '\n')
            self.table = None

    def handle_data(self, data):
        if self.skip: return
        if self.cell is not None: self.cell += data
        else: self.out.append(data)

    def text(self):
        t = ''.join(self.out)
        t = re.sub(r'[ \t]+', ' ', t)
        t = re.sub(r'\n{3,}', '\n\n', t)
        return t.strip() + '\n'


def html_to_md(html):
    m = MD(); m.feed(html); return m.text()
