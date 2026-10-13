"""Build MEMO_TO_BARANDON_2026-10-12.pdf: memo body (HTML via Chrome) + Annex 3 (subpoena request) + Annex 4 (War of the Statutes). 8.5x13."""
import fitz, subprocess, os
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__))); W,H=612,936
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
def pdf(html, out): subprocess.run([CH,"--headless=new","--disable-gpu","--no-pdf-header-footer",f"--print-to-pdf={out}","file://"+html],capture_output=True)
body=os.path.join(R,"research/_memo_body.pdf"); pdf(os.path.join(R,"MEMO_TO_BARANDON_2026-10-12.html"), body)
out=fitz.open(); out.insert_pdf(fitz.open(body))
def divider(label, text):
    d=out.new_page(width=W,height=H); d.insert_text((54,140),label,fontsize=26,fontname="tibo"); d.draw_rect(fitz.Rect(54,152,W-54,156),color=(0,0,0),fill=(0,0,0)); d.insert_textbox(fitz.Rect(54,176,W-54,360),text,fontsize=12.5,fontname="tiro")
divider("Annex 3","Draft Request for Issuance of Subpoenas Duces Tecum and Ad Testificandum (Rule 21; Judicial Affidavit Rule, Section 5), ten custodians, returnable December 2, 2026. For counsel's signature; not filed. See A8.")
out.insert_pdf(fitz.open(os.path.join(R,"SUBPOENA_REQUEST_2026-10/SUBPOENA_REQUEST_2026-10.pdf")))
divider("Annex 4","War of the Statutes: the provisions each side will cite, section by section, with the exact words, the exhibit that fits each, what the court will key in on, and the expected result; the procedural rules she enforces; the statute spine of the memorandum. See C12 for the plain-language version.")
out.insert_pdf(fitz.open(os.path.join(R,"WAR_OF_THE_STATUTES_2026-10.pdf")))
dest=os.path.join(R,"MEMO_TO_BARANDON_2026-10-12.pdf"); out.save(dest,garbage=3,deflate=True)
t=''.join(p.get_text() for p in out); print(out.page_count,"pp",{(round(p.rect.width),round(p.rect.height)) for p in out},"| C12:", "C12." in t, "| Annex 4:", "Annex 4" in t)
