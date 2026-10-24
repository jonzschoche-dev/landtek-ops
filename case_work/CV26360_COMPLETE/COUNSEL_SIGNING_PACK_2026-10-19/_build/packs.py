"""Assemble one cross-reference PDF pack per counsel draft:
cover (status, what counsel must do) -> cross-reference table (every figure -> tab/page/check) ->
the draft -> source tabs, each source page stamped "TAB n" and bookmarked."""
import fitz, html, sys, os

CF = '/Users/jonathanzschoche/landtek/case_work/CV26360_COMPLETE/CASE_FILE'
SCR = sys.argv[1]
OUT = sys.argv[2]
SRC = f'{SCR}/src'
P, D, J, O = (f'{CF}/02_PLAINTIFF_EXHIBITS', f'{CF}/03_DEFENSE_EXHIBITS',
              f'{CF}/04_JUDICIAL_AFFIDAVITS', f'{CF}/01_PLEADINGS_ORDERS')
W, H = 612, 936  # 8.5 x 13 in

# check codes
IMG, TXT, DESK, OUTS = ('IMG', 'TXT', 'DESK', 'OUT')
LEGEND = {IMG: ('#1b7f3b', 'Checked against the page image, 19 Oct'),
          TXT: ('#1b7f3b', 'Checked against the page text layer, 19 Oct'),
          DESK: ('#9a6700', 'Cited by the case desk; not re-checked'),
          OUTS: ('#b42318', 'Source not in this pack: verify before filing')}

CSS = """
body{font-family:serif;font-size:10pt;line-height:1.3}
h1{font-size:15pt;margin:0 0 4pt 0} h2{font-size:11.5pt;margin:12pt 0 4pt 0}
p{margin:0 0 6pt 0} .s{font-size:8.5pt;color:#444}
table{border-collapse:collapse;width:100%} td,th{border:0.5pt solid #888;padding:2.5pt 4pt;vertical-align:top;font-size:8.5pt}
th{background:#e7e6e6;text-align:left} .box{border:1pt solid #b42318;padding:6pt;margin:6pt 0}
li{margin-bottom:3pt}
"""

def story_pages(doc, body):
    """Render HTML into 8.5x13 pages appended to doc; return page count."""
    import io
    story = fitz.Story(html=f'<html><body>{body}</body></html>', user_css=CSS)
    where = fitz.Rect(54, 54, W - 54, H - 54)
    bio = io.BytesIO()
    writer = fitz.DocumentWriter(bio)
    more = True
    while more:
        dev = writer.begin_page(fitz.Rect(0, 0, W, H))
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    tmp = fitz.open('pdf', bio.getvalue())
    doc.insert_pdf(tmp)
    return len(tmp)

def esc(s): return html.escape(s)

def build(spec):
    # pass 1: count front-matter pages so pack page numbers in the table are right
    def front(tab_start):
        tabs = ''.join(f"<tr><td>{t['tab']}</td><td>{esc(t['title'])}</td><td>{esc(os.path.basename(t['path']) if t['path'].startswith('case_work') else t['path'])}</td>"
                       f"<td>{t['pages_label']}</td><td>{tab_start.get(t['tab'],'')}</td></tr>" for t in spec['tabs'])
        rows = ''.join(
            f"<tr><td>{i}</td><td>{esc(r[0])}</td><td>{esc(r[1])}</td><td>{esc(r[2])}</td>"
            f"<td style='color:{LEGEND[r[3]][0]}'><b>{r[3]}</b>{(' · ' + esc(r[4])) if len(r) > 4 and r[4] else ''}</td></tr>"
            for i, r in enumerate(spec['xref'], 1))
        legend = ' · '.join(f"<b style='color:{c}'>{k}</b> {esc(v)}" for k, (c, v) in LEGEND.items())
        counts = {k: sum(1 for r in spec['xref'] if r[3] == k) for k in LEGEND}
        body = f"""
<p class='s'>Civil Case No. 26-360 · MTC Mercedes · Zschoche v. Balane · prepared 19 Oct 2026 for Atty. Barandon · INTERNAL · NOT FILED · NOT SENT</p>
<h1>{esc(spec['title'])}</h1>
<p>{spec['what']}</p>
<div class='box'><b>Counsel to decide or complete before signing</b><ol>{''.join('<li>'+x+'</li>' for x in spec['todo'])}</ol></div>
<h2>How to use this pack</h2>
<p>The draft follows at pack page {spec['_draft_page']}. Yellow text in the draft marks a blank or a decision for counsel. Every figure in the draft is listed below with the tab and source page where it can be read. Each source page carries a red <b>TAB</b> stamp at the top and a bookmark. The Word file for editing is <b>{esc(spec['docx'])}</b>, in the same folder.</p>
<p class='s'>Check status: {counts[IMG]+counts[TXT]} checked on the source page · {counts[DESK]} cited by the desk only · {counts[OUTS]} with the source outside this pack.<br/>{legend}</p>
<h2>Tabs</h2>
<table><tr><th>Tab</th><th>Document</th><th>File</th><th>Source pages</th><th>Pack page</th></tr>{tabs}</table>
<h2>Cross-reference: every figure in the draft</h2>
<table><tr><th>#</th><th>Draft</th><th>Figure or fact</th><th>Where to read it</th><th>Check</th></tr>{rows}</table>
"""
        return body

    tmp = fitz.open()
    spec['_draft_page'] = '?'
    nfront = story_pages(tmp, front({}))
    draft = fitz.open(spec['draft_pdf'])
    start = nfront + 1
    spec['_draft_page'] = start
    p = start + len(draft)
    tab_start = {}
    for t in spec['tabs']:
        tab_start[t['tab']] = p
        p += len(t['pages'])
    out = fitz.open()
    n2 = story_pages(out, front(tab_start))
    assert n2 == nfront, (n2, nfront)
    toc = [[1, 'Cover and cross-reference', 1], [1, 'DRAFT: ' + spec['short'], start]]
    out.insert_pdf(draft)
    for k in range(len(draft)):
        pg = out[start - 1 + k]
        r = pg.rect
        box = fitz.Rect(r.width / 2 - 30, r.height - 52, r.width / 2 + 30, r.height - 30)
        pg.draw_rect(box, color=None, fill=(1, 1, 1), overlay=True)
        assert pg.insert_textbox(box + (0, 2, 0, 4), str(k + 1), fontsize=10, fontname='tiro', align=1, overlay=True) >= 0
    for t in spec['tabs']:
        src = fitz.open(t['path_abs'])
        toc.append([1, f"TAB {t['tab']} · {t['title']}", len(out) + 1])
        for sp in t['pages']:
            out.insert_pdf(src, from_page=sp - 1, to_page=sp - 1)
            pg = out[-1]
            r = pg.rect
            label = f"TAB {t['tab']} · {t['title']} · source p. {sp} of {len(src)}"
            band = fitz.Rect(0, 0, r.width, 20)
            m = pg.derotation_matrix
            pg.draw_rect(band * m, color=None, fill=(1, 1, 1), fill_opacity=0.85, overlay=True)
            rc = pg.insert_textbox(fitz.Rect(6, 3, r.width - 6, 22) * m, label, fontsize=8.5, fontname='hebo',
                              color=(0.7, 0.1, 0.1), align=0, overlay=True, rotate=pg.rotation)
            assert rc >= 0, ('stamp overflow', label)
    # pack page numbers bottom-right on every page
    for i, pg in enumerate(out, 1):
        r = pg.rect
        pg.insert_textbox(fitz.Rect(r.width - 160, r.height - 18, r.width - 8, r.height - 2) * pg.derotation_matrix,
                          f"Pack p. {i} of {len(out)}", fontsize=7.5, fontname='helv', color=(0.3, 0.3, 0.3), align=2,
                          overlay=True, rotate=pg.rotation)
    out.set_toc(toc)
    out.set_metadata({'title': spec['title'], 'author': 'LandTek for Atty. Barandon (draft)', 'subject': 'CV 26-360 counsel pack'})
    dest = f"{OUT}/{spec['pdf']}"
    # downscale scans to ~150 dpi (8.5x13 at 150 dpi ~ 1275x1950 px) so packs travel by e-mail
    from PIL import Image
    import io as _io
    done = set()
    for pg in out:
        for img in pg.get_images(full=True):
            x = img[0]
            if x in done: continue
            done.add(x)
            w, h = img[2], img[3]
            if max(w, h) <= 2000: continue
            try:
                pix = fitz.Pixmap(out, x)
                if pix.alpha or pix.n > 3: pix = fitz.Pixmap(fitz.csRGB, pix)
                im = Image.frombytes('RGB' if pix.n == 3 else 'L', (pix.width, pix.height), pix.samples)
                f = 2000 / max(w, h)
                im = im.resize((int(w * f), int(h * f)), Image.LANCZOS)
                b = _io.BytesIO(); im.save(b, 'JPEG', quality=70)
                pg.replace_image(x, stream=b.getvalue())
            except Exception as e:
                print('skip image', x, e)
    out.save(dest, garbage=4, deflate=True)
    print(dest, len(out), 'pp')

def tab(n, title, path, pages=None, label=None):
    total = len(fitz.open(path))
    pages = pages or list(range(1, total + 1))
    rel = os.path.relpath(path, '/Users/jonathanzschoche/landtek') if path.startswith('/Users') else path
    return {'tab': n, 'title': title, 'path_abs': path, 'pages': pages,
            'path': rel if not path.startswith(SRC) else label,
            'pages_label': f"{pages[0]}–{pages[-1]}" if pages == list(range(pages[0], pages[-1] + 1)) and len(pages) > 1 else ', '.join(map(str, pages))}

REG = 'Corpus doc 369: Registry of Deeds certified file, Ref. 2025001098 (Drive)'
specs = []

# ───────────── PACK 1: subpoenas ─────────────
specs.append({
 'title': 'Pack 1: Request for Issuance of Subpoenas', 'short': 'Request for Issuance of Subpoenas',
 'docx': '01_Request_for_Subpoenas_DRAFT.docx', 'pdf': '01_Request_for_Subpoenas_PACK.pdf',
 'draft_pdf': f'{SCR}/pdf/01_Request_for_Subpoenas_DRAFT.pdf',
 'what': 'Subpoenas duces tecum and ad testificandum to ten public custodians (Registry, OCC notarial, DENR, Building Official, Assessor, BIR, Provincial Treasurer, Prosecutor, BFP/CANORECO/Barangay, COMELEC/SB). Text is the desk draft of 13 Oct, unchanged in substance; the signature block now carries counsel’s 2026 particulars as filed on 24 April 2026.',
 'todo': ['<b>Decision (c), due 21 Oct:</b> custodians in the case-in-chief (2 Dec, as drafted) or held for rebuttal. Rule 30 §5(f) risk: records held back may be excluded as not proper rebuttal.',
          '<b>Item (b)(iv):</b> the draft asks for “the order of November 2016” in Spec. Proc. 2156. Two orders exist: the 2156 record lists an “Order dated November 4, 2016” as petitioner’s Exhibit B (Tab 5, registry p. 6), and Exh. B p. 5 (Tab 2) shows the new owner’s duplicate issued on an RTC Br. 41 order dated <b>30 January 2017</b>. Name both dates.',
          '<b>Item (j):</b> Gloria’s terms (Kagawad 1997–2004; SB 2004–2017) are cited “as she has alleged.” If the only source is her <i>excluded</i> judicial affidavit, cite another source or drop the dates.',
          '<b>Item (d):</b> the 24 Jan 2026 written request to the Building Official is not in this pack. Attach Jonathan’s copy or drop the sentence.',
          'Explanation of service (Rule 13 §11) and the filing date.'],
 'tabs': [tab(1, 'Order of 4 Sep 2026 (trial dates)', f'{O}/01-14_Judge_Cu_Orders_6Feb_11Mar_12Mar_4Sep_2026.pdf'),
          tab(2, 'Exh. B: TCT T-52540 with memorandum of encumbrances', f'{P}/Exh_B_to_B-4.pdf'),
          tab(3, 'Exh. C: TCT 079-2021002126 (plan PSD-E2020005406)', f'{P}/Exh_C_to_C-1.pdf'),
          tab(4, 'Exh. H: Deed of Absolute Sale, 29 Sep 2016', f'{P}/Exh_H.pdf'),
          tab(5, 'Registry file Ref. 2025001098 (selected pages)', f'{SRC}/doc369.pdf', [6, 7, 8, 9, 10, 12, 14, 15, 16, 20, 21], REG),
          tab(6, 'Provincial Prosecutor, Joint Resolution (NPS-V-09-INV-2020F-00383 / 2020G-00417)', f'{SRC}/doc581.pdf', list(range(54, 66)), 'Corpus doc 581: CA petition annexes, PPO certified copy (Drive)'),
          tab(7, 'Exh. D: ARP GR-2023-II-07-001-00256', f'{P}/Exh_D_to_D-1.pdf')],
 'xref': [
  ['¶1', 'Plaintiff dates 14 Oct, 4 Nov, 11 Nov, 2 Dec, 9 Dec 2026; defense 13 Jan, 3 Feb, 10 Feb, 3 Mar, 10 Mar 2027; “final and intransferable …”', 'Tab 1 (4 Sep order); also 01-15 photo', IMG],
  ['3(a)', 'Entry Nos. 2021003235 and 2021003236, both 23 Nov 2021', 'Tab 2, Exh. B pp. 5–6', IMG],
  ['3(a)', 'Partition-Subdivision Agreement 15 Mar 2017, Doc. 402, Pg. 81, Bk. CXXII, s. 2017, Asis', 'Tab 2, Exh. B p. 6 (Entry 2021003236)', IMG],
  ['3(a)', 'SPA Gloria H. Balane → Karen Gay A. Elevado, dated 15 Sep 2021', 'Tab 5, registry p. 20', TXT, 'grantee confirmed; date not legible in text layer, read the image'],
  ['3(a)', 'Owner’s duplicate of T-52540 issued under Entry 2017000693', 'Tab 2, Exh. B p. 5 (16 Mar 2017)', IMG],
  ['3(b)', 'Asis Doc. 304, Pg. 61, Bk. CXVI, s. 2016 (the deed)', 'Tab 4, Exh. H; Tab 2, Exh. B p. 6', IMG],
  ['3(b)', 'Asis Doc. 115, Pg. 23, Bk. CXXII, s. 2017 (Deed of Confirmation, 28 Mar 2017)', 'Tab 2, Exh. B p. 6; Tab 5, registry p. 16', IMG],
  ['3(b)', 'Belen Doc. 560, Pg. 112, Bk. XI, s. 2016 (Affidavit of Loss, 27 Sep 2016)', 'Tab 2, Exh. B p. 5 (Entry 2016002312)', IMG],
  ['3(b)', 'Belen Doc. 55, Pg. 17, Bk. IX, s. 2012 (Cesar → Salvador SPA, 29 Feb 2012)', 'Not in pack; trial-brief folder D7 per 12 Oct memo', OUTS],
  ['3(b)', 'Doc. 019, Pg. 04, Bk. XIV, s. 2021 (Elevado SPA notarial)', 'Tab 5, registry p. 20', DESK, 'notary name faint per playbook'],
  ['3(b)', 'Spec. Proc. 2156 order “of November 2016”; certificate of finality 13 Mar 2017', 'Tab 5, registry pp. 6–10 (4 Nov 2016 order listed, p. 6); Exh. B p. 5 (30 Jan 2017 order)', IMG, 'finality date 13 Mar 2017 not re-checked; see counsel item 2'],
  ['3(b)', 'Civil Case 8563: Verified Answer received 9 Jul 2021', 'Not in pack; corpus doc 586 / KING_CASES_DIG', OUTS],
  ['3(c)', 'Plan (LRA) PSD-E2020005406; survey 8 Sep 2020; approved 6 Apr 2021; Engr. Christopher D. Mangiga', 'Tab 3, Exh. C p. 2', IMG],
  ['3(c)', 'Plan certificate “with the full knowledge and consent of the owner(s)”', 'Not in pack; plan sheet (playbook Annex O)', OUTS],
  ['3(c)', 'Cesar M. de la Fuente died 21 June 2017', 'Not in pack; PSA certificate still to obtain', OUTS],
  ['3(d)', 'Written request to the Building Official 24 Jan 2026, declined', 'Not in pack', OUTS, 'see counsel item 4'],
  ['3(e)', 'ARP 00246 and 00274 (owners’ declarations)', 'Tab 5, registry pp. 12, 14, 15', TXT],
  ['3(e)', 'ARP 00276 cancelled by Gloria’s ARP 00256 (27 Jul 2023)', 'Tab 7, Exh. D p. 1', IMG],
  ['3(e)', 'Letter request of 21 Sep 2021 revising ARP 00274', 'Tab 5, registry p. 15 (the ARP itself)', DESK],
  ['3(f)', 'eCAR 201900074035, 19 Jun 2020, under T-38838', 'Tab 5, registry p. 12', TXT],
  ['3(f)', 'eCAR 201900675224, 18 Nov 2021, under T-52540; same payment date 15 Jun 2020', 'Tab 5, registry pp. 12, 21; Exh. B p. 6', TXT],
  ['3(g)', 'OR 0585696, 24 Jun 2020: tax ₱12,547, surcharge ₱3,137, interest ₱11,292, total ₱27,276', 'Tab 5, registry p. 14', TXT],
  ['3(h)', 'NPS-V-09-INV-2020F-00383 and 2020G-00417', 'Tab 6, doc 581 p. 54', TXT],
  ['3(h)', 'Counsel’s letter of 11 Feb 2020', 'Tab 6, doc 581 p. 65 (the resolution refers to it)', TXT],
  ['3(j)', 'Gloria: Kagawad 1997–2004; SB Member 2004–2017 “as she has alleged”', 'Not in pack', OUTS, 'see counsel item 3'],
  ['3(j)', 'SB Resolution No. 103-86, 16 Jul 1986', 'Not in pack; corpus', OUTS],
 ]})

# ───────────── PACK 2: motion to resolve ─────────────
specs.append({
 'title': 'Pack 2: Motion to Resolve the Motion to Render Summary Judgment', 'short': 'Motion to Resolve (with Annex A)',
 'docx': '02_Motion_to_Resolve_SJ_DRAFT.docx', 'pdf': '02_Motion_to_Resolve_SJ_PACK.pdf',
 'draft_pdf': f'{SCR}/pdf/02_Motion_to_Resolve_SJ_DRAFT.pdf',
 'what': 'Asks the court to rule on the April summary-judgment motion and, in the alternative, to fix the 19 undisputed facts in Annex A under Rule 35 §4 (2019 text, quoted from A.M. No. 19-10-20-SC).',
 'todo': ['<b>File only if the motion is still unresolved.</b> The 13 May 2026 pre-trial order is not in our file. If it resolved the motion, drop this pack.',
          '<b>Corrected ¶1:</b> the earlier draft said the defendants’ Comment/Opposition was “received on 27 April.” Their own Comment (Tab 2, p. 1) says <i>they</i> received our motion on 27 April; it is dated 4 May 2026. The draft now says so.',
          '<b>Reply:</b> a draft Reply to the Comment exists in the corpus (doc 390). If one was filed, its date is the date of submission; insert it in ¶1.',
          '<b>Annex A:</b> check the Answer paragraph numbers (Tab 3) against the filed copy; facts 4, 13, 16 and 19 rest on the Answer only.',
          'Rule 15 notice or submission, service and filing date.'],
 'tabs': [tab(1, 'Plaintiff’s Motion to Render Summary Judgment, 24 Apr 2026', f'{O}/01-08_Motion_Summary_Judgment.pdf'),
          tab(2, 'Defendants’ Comment/Opposition to the MSJ, 4 May 2026', f'{SRC}/doc391.pdf', None, 'Corpus doc 391 (Drive): not in CASE_FILE'),
          tab(3, 'Answer with Counterclaim', f'{O}/01-04_Answer_with_Counterclaim.pdf'),
          tab(4, 'Orders of 6 Feb, 11 Mar, 12 Mar, 4 Sep 2026 (no ruling on the MSJ)', f'{O}/01-14_Judge_Cu_Orders_6Feb_11Mar_12Mar_4Sep_2026.pdf'),
          tab(5, 'Exh. B: TCT T-52540', f'{P}/Exh_B_to_B-4.pdf'),
          tab(6, 'Exh. C: TCT 079-2021002126', f'{P}/Exh_C_to_C-1.pdf'),
          tab(7, 'Exh. D: ARP 00256', f'{P}/Exh_D_to_D-1.pdf'),
          tab(8, 'Exh. E: SPA of 16 Mar 1992', f'{P}/Exh_E.pdf'),
          tab(9, 'Exh. F: revocation, 15 Aug 2005', f'{P}/Exh_F.pdf'),
          tab(10, 'Exh. G and G-1: Bicol Post publication', f'{P}/Exh_G_to_G-1.pdf'),
          tab(11, 'Exh. H: Deed of Absolute Sale, 29 Sep 2016', f'{P}/Exh_H.pdf'),
          tab(12, 'Exh. J and J-1: demand and receipt', f'{P}/Exh_J_to_J-1.pdf'),
          tab(13, 'Def. Exh. 5: receipts (pp. 1–3 and 31–33)', f'{D}/Def_Exh_5_Receipts.pdf', [1, 2, 3, 31, 32, 33]),
          tab(14, 'Def. Exh. 7: SPA of 16 Mar 1992 (defense copy)', f'{D}/Def_Exh_7_SPA_1992-03-16.pdf'),
          tab(15, 'Registry file Ref. 2025001098 p. 16: Deed of Confirmation', f'{SRC}/doc369.pdf', [16], REG)],
 'xref': [
  ['¶1', 'MSJ filed 24 April 2026', 'Tab 1, p. 5 (“Most respectfully filed. 24 April 2026”)', TXT],
  ['¶1', 'Defendants received the MSJ 27 April 2026; their Comment/Opposition dated 4 May 2026', 'Tab 2, pp. 1 and last', TXT],
  ['¶2', 'Three months from submission: from 4 May 2026, lapsed about 4 Aug 2026', 'Arithmetic from Tab 2; Const. Art. VIII §15', TXT, 'later if a reply was filed'],
  ['¶3', 'No ruling on the MSJ in the orders held', 'Tab 4 (13 May pre-trial order not held)', DESK],
  ['¶4–5', 'Rule 35 §§3–4 as amended (A.M. No. 19-10-20-SC, eff. 1 May 2020)', 'Quoted from lawphil; Grok handoff 19 Oct', DESK],
  ['A-1', 'T-52540, Lot 2-X-6-I-4-C, 28,891 sq m, Hoppe/Zschoche/Keesey', 'Tab 5 p. 1; area also Tab 15', DESK, 'area confirmed on Tab 15'],
  ['A-2', 'SPA 16 Mar 1992, ¶7 text', 'Tab 8; Tab 14 p. 3', DESK],
  ['A-3', 'SPA annotated 21 Jun 1996, Entry PE-196220-227-21', 'Tab 5, p. 3', IMG],
  ['A-4', 'Occupancy from 1975; rent to Llamanzares via Violeta', 'Tab 3, Answer ¶¶40, 43, 44', DESK],
  ['A-5', 'Revocation 15 Aug 2005, Los Angeles consulate', 'Tab 9', DESK],
  ['A-6', 'Bicol Post 25 Sep, 2 Oct, 9 Oct 2020', 'Tab 10', IMG],
  ['A-7', 'Deed 29 Sep 2016: 2,587 sq m; ₱250,000 “in hand paid”; Doc. 304, Pg. 61, Bk. CXVI, s. 2016', 'Tab 11; Tab 5 p. 6', IMG],
  ['A-8', 'Nine post-deed receipts: 0222 ₱60,000; 0223 ₱10,000; 0219 ₱50,000; 0218 ₱20,000; 0224 ₱40,000; 0225 ₱30,000; 0227 ₱2,000; 0226 ₱3,000; 0228 “Full payment”', 'Tab 13, Def. Exh. 5 pp. 31–33', IMG, 'total ₱219,000 incl. 0228 ₱4,000; 0221 (20 Sep 2016, ₱50,000) is pre-deed'],
  ['A-9', 'Deed of Confirmation 28 Mar 2017, Doc. 115, Pg. 23, Bk. CXXII, s. 2017', 'Tab 5 p. 6; Tab 15', IMG],
  ['A-10', 'Partition-Subdivision Agreement 15 Mar 2017, Doc. 402; plan PSD-E2020005406', 'Tab 5 p. 6', IMG],
  ['A-11', 'Survey 8 Sep 2020; approved 6 Apr 2021', 'Tab 6 p. 2', IMG],
  ['A-12', 'Registered 23 Nov 2021, Entries 2021003235–36; TCTs 079-2021002126 and -2127 issued', 'Tab 5 pp. 5–6', IMG],
  ['A-13', 'Gloria’s SPA to Nelly Juntilla, Toronto, 28 May 2020', 'Tab 3, Answer Annex “1”', DESK],
  ['A-14', 'ARP 00256 assessed value ₱257,670', 'Tab 7', IMG, 'below the ₱400,000 MTC ceiling'],
  ['A-15', 'Demand to vacate received 22 Aug 2025', 'Tab 12, Exh. J-1', DESK],
  ['A-16', 'Rooms rented out by the defendants', 'Tab 3, Answer ¶27', DESK],
  ['A-17', 'Only down-payment receipt: 6 Jan 2005, Efren Balane, ₱20,000, “Von dela Fuente”; earliest receipt 25 Oct 2003', 'Tab 13, pp. 2–3', DESK],
  ['A-18', 'Villafuerte Receipt No. 0460, 29 Dec 2006, Princess Balane, ₱3,000', 'Tab 13, p. 1', DESK],
  ['A-19', '“Gloria checked the SPA, the Registry of Deeds records …”', 'Tab 3, Answer ¶44(h)', DESK],
 ]})

# ───────────── PACK 3: replacement JAs ─────────────
specs.append({
 'title': 'Pack 3: Motion for Leave to Submit Compliant Replacement Judicial Affidavits (conditional)', 'short': 'Motion for Leave: Replacement JAs',
 'docx': '03_Motion_Leave_Replacement_JAs_DRAFT.docx', 'pdf': '03_Motion_Leave_Replacement_JAs_PACK.pdf',
 'draft_pdf': f'{SCR}/pdf/03_Motion_Leave_Replacement_JAs_DRAFT.pdf',
 'what': 'CONDITIONAL. The stamp under the jurats of Exhs. L, M and N (sworn 23 Jan 2026) reads “Admin Matter No. 2023-424 valid until 12/31/2025.” If no 2026 commission covered that date, JA Rule §3(f) and §10(c) allow one replacement submission before the witnesses testify, with a fine of ₱1,000 to ₱5,000 payable by counsel. If a commission did cover it, this motion is not needed.',
 'todo': ['<b>Decision (b), due 21 Oct:</b> was there a notarial commission covering 23 Jan 2026? If yes, record its number and drop this pack.',
          'If no: re-swear the three neighbours word for word before a commissioned notary (Atty. Darren J. Andrade’s commission runs to 31 Dec 2026, per his stamp on Tab 1 p. 4), re-execute the §4 attestation, and file by <b>Fri 30 Oct</b> for the 4 Nov setting.',
          'Exh. K (Jonathan’s JA) bears the same stamp (Tab 4). He testified on 14 Oct, and §10(c) speaks of submission “before the hearing or trial.” Counsel to decide whether K needs any step.',
          'Fill paragraphs 3, 5 and 6 (the commission fact, the notary, the date of service of summons) and the Rule 15 notice.'],
 'tabs': [tab(1, 'Exh. L: JA of Donata Mabeza King (filed)', f'{J}/JA_Exh_L_Donata_King_(filed).pdf'),
          tab(2, 'Exh. M: JA of Francia de los Reyes (filed)', f'{J}/JA_Exh_M_Francia_de_los_Reyes_(filed).pdf'),
          tab(3, 'Exh. N: JA of Shirley De Leon (filed)', f'{J}/JA_Exh_N_Shirley_De_Leon_(filed).pdf'),
          tab(4, 'Exh. K: JA of Jonathan Zschoche, jurat page', f'{P}/Exh_K.pdf', [14]),
          tab(5, 'Order of 4 Sep 2026 (settings)', f'{O}/01-15_Order_2026-09-04_trial_dates.pdf' if os.path.exists(f'{O}/01-15_Order_2026-09-04_trial_dates.pdf') else f'{O}/01-14_Judge_Cu_Orders_6Feb_11Mar_12Mar_4Sep_2026.pdf')],
 'xref': [
  ['¶1', 'L, M, N subscribed and sworn at Daet on 23 Jan 2026', 'Tab 1 p. 4; Tab 2 p. 5; Tab 3 p. 5', DESK, 'L checked on image'],
  ['¶3', 'Stamp: “Admin Matter No. 2023-424 valid until 12/31/2025”', 'Tab 1 p. 4 (also Tabs 2, 3, 4)', IMG, 'L read; M, N, K per desk appendix'],
  ['¶2', 'Settings 4 Nov, 11 Nov, 2 Dec, 9 Dec 2026', 'Tab 5', IMG],
  ['¶3', 'JA Rule §3(f): jurat with signature of the notary who administers the oath', 'A.M. No. 12-8-8-SC, lawphil copy in 06_LAW/LAW_SOURCES_lawphil.tgz (jar.html)', TXT],
  ['¶4', 'JA Rule §10(c), quoted in full', 'Same source', TXT],
  ['¶5', 'Atty. Darren J. Andrade commission “2025-3, until December 31, 2026”', 'Tab 1 p. 4 (attestation jurat)', IMG],
 ]})

for s in specs:
    build(s)
