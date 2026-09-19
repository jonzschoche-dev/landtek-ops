# Overlays the answers from BIR_1901_FILL_KEY.md onto the scanned blank BIR Form 1901.
# The source scan has no AcroForm fields, so every entry is placed by coordinate.
# Run: python3 fill_form.py [path/to/blank_1901.pdf]
import sys, io, os
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.pdfgen import canvas

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads/Application (1).pdf")
OUT = "BIR_1901_AVI_FILLED_2026-09.pdf"

# Rendering scales used to read the coordinates off the page images:
#   pages 1, 2 : 500 dpi over a 156 x 241 pt mediabox -> 6.9487 px/pt
#   page  3    : 120 dpi over a 612 x 1008 pt mediabox -> 1.66667 px/pt
PX = {0: 6.9487, 1: 6.9487, 2: 1.66667}
PH = {0: 241.0, 1: 241.0, 2: 1008.0}

# (page_index, x_px, baseline_y_px, text, size_pt, max_width_px)
E = [
 # ---------------- PAGE 1 ----------------
 (0,  53,  306, "X", 4.2, None),                       # 1  Registering Office - Head Office
 (0, 395,  370, "200-031-253", 4.0, 270),              # 4  TIN (existing)
 (0,  54,  416, "X", 4.2, None),                       # 6  Single Proprietorship Only (Resident Citizen)
 (0,  50,  646, "INOCALLA", 4.2, 250),                 # 7  Last name
 (0, 330,  646, "ALLAN", 4.2, 240),                    # 7  First name
 (0, 605,  646, "VILLAFRIA", 4.2, 220),                # 7  Middle name
 (0, 131,  719, "X", 4.2, None),                       # 8  Male
 (0, 454,  719, "X", 4.2, None),                       # 9  Single
 (0, 395,  757, "01/12/1955", 3.8, 180),               # 10 Date of birth
 (0, 800,  754, "PARACALE, CAMARINES NORTE", 3.4, 228),# 11 Place of birth
 (0, 232,  782, "BEATRIZ D. VILLAFRIA", 3.8, 285),     # 12 Mother's maiden name
 (0, 697,  782, "VICENTE LUNA INOCALLA", 3.8, 315),    # 13 Father's name
 (0, 137,  810, "FILIPINO", 3.8, 380),                 # 14 Citizenship
 (0, 430,  869, "PUROK 4", 3.4, 140),                  # 16 Residence - Lot/Block/House No.
 (0,  54,  915, "CAPACUAN", 3.4, 210),                 # 16 Barangay
 (0, 460,  915, "PARACALE", 3.4, 225),                 # 16 Municipality/City
 (0, 704,  915, "CAMARINES NORTE", 3.4, 196),          # 16 Province
 (0, 924,  915, "4605", 3.4, 85),                      # 16 ZIP
 (0, 410,  971, "LOT 4, PSU-143364", 3.0, 130),        # 17 Business - Lot/Block/House No.
 (0, 583,  971, "(OCT NO. P-1616)", 3.2, 190),           # 17 Street Name
 (0,  54, 1018, "SANTA ROSA SUR", 3.4, 210),           # 17 Barangay
 (0, 460, 1018, "JOSE PANGANIBAN", 3.4, 225),          # 17 Municipality/City
 (0, 704, 1018, "CAMARINES NORTE", 3.4, 196),          # 17 Province
 (0, 924, 1018, "4606", 3.4, 85),                      # 17 ZIP
 (0, 560, 1073, "REGISTRATION OF BUSINESS (EXISTING TIN)", 3.2, 450),  # 20 Purpose
 (0,  44, 1134, "DRIVER'S LICENSE", 3.2, 120),         # 21 ID type
 (0, 178, 1134, "X01-11-002246", 3.2, 142),            # 21 ID number
 (0, 572, 1134, "01/12/2033", 3.4, 200),               # 21 Expiry date
 (0, 792, 1134, "LTO", 3.4, 75),                       # 21 Issuer
 (0, 910, 1134, "PHILIPPINES", 3.2, 118),              # 21 Place of issue
 (0, 355, 1186, "X", 4.2, None),                       # 22 Mobile Number
 (0, 350, 1206, "0917 155 4782", 3.4, 128),            # 22 Mobile
 (0, 500, 1206, "shiraction2@gmail.com", 3.4, 510),    # 22 Email
 (0, 863, 1233, "X", 4.2, None),                       # 23 8% option - No
 (0,  55, 1296, "X", 4.2, None),                       # 24 Micro (under P3M)
 (0,  45, 1572, "RAMOS", 4.0, 250),                    # 30 Representative - last name
 (0, 318, 1572, "RAMON", 4.0, 265),                    # 30 first name
 (0, 608, 1572, "R.", 4.0, 215),                       # 30 middle name
 # ---------------- PAGE 2 ----------------
 (1, 356,  145, "X", 4.2, None),                       # 32 Address Type - Residence
 (1, 430,  215, "PUROK 4", 3.4, 122),                  # 33 Lot/Block/House No.
 (1,  54,  260, "CAPACUAN", 3.4, 190),                 # 33 Barangay
 (1, 455,  260, "PARACALE", 3.4, 208),                 # 33 Municipality/City
 (1, 694,  260, "CAMARINES NORTE", 3.4, 212),          # 33 Province
 (1, 924,  260, "4605", 3.4, 80),                      # 33 ZIP
 (1, 349,  308, "X", 4.2, None),                       # 34 Mobile Number
 (1, 500,  335, "monraso1959@gmail.com", 3.4, 505),    # 34 Email
 (1, 136,  452, "AVI GOLD PROCESSING PLANT", 3.6, 530),# 36 Primary - Trade/Business Name
 (1, 686,  452, "DTI", 3.6, 315),                      # 36 Regulatory Body
 (1, 136,  546, "8480852", 3.6, 150),                  # 36 Business Registration Number
 (1, 305,  546, "09/11/2026", 3.6, 178),               # 36 Business Registration Date
 (1, 686,  546, "GOLD ORE PROCESSING", 3.6, 315),      # 36 Line of Business
 # ---------------- PAGE 3 ----------------
 (2, 124,  275, "X", 11, None),                        # 41A BIR Printed Invoices - Yes
 (2, 545,  275, "X", 11, None),                        # 41B NON-VAT
 (2, 700,  278, "1", 11, None),                        # 41C No. of booklets
 (2, 330, 1180, "ALLAN VILLAFRIA INOCALLA", 10, 210),   # 46 Declaration - printed name
 (2, 312, 1385, "200-031-253", 9, 205),                # 47 TIN
 (2, 548, 1385, "00000", 9, 105),                      # 47 Branch code
 (2, 830, 1385, "2026", 9, 165),                       # 49 For the year
 (2, 402, 1415, "INOCALLA, ALLAN VILLAFRIA", 9, 595),  # 50 Taxpayer's name
]

src = PdfReader(SRC)
writer = PdfWriter()
by_page = {}
for e in E:
    by_page.setdefault(e[0], []).append(e)

from reportlab.pdfbase.pdfmetrics import stringWidth
for i, page in enumerate(src.pages):
    w = float(page.mediabox.width); h = float(page.mediabox.height)
    if i in by_page:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(w, h))
        c.setFillColorRGB(0, 0, 0)
        s = PX[i]
        for _, xpx, ypx, text, size, maxw in by_page[i]:
            f = "Helvetica-Bold" if text == "X" else "Helvetica"
            while maxw and stringWidth(text, f, size) > maxw / s and size > 1.4:
                size -= 0.1
            c.setFont(f, size)
            c.drawString(xpx / s, PH[i] - ypx / s, text)
        c.save(); buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    # scale every page to 612 pt wide so it prints at full size
    if abs(w - 612) > 1:
        k = 612.0 / w
        page.add_transformation(Transformation().scale(k, k))
        page.mediabox.upper_right = (612, h * k)
        page.mediabox.lower_left = (0, 0)
    writer.add_page(page)

with open(OUT, "wb") as fh:
    writer.write(fh)
print("wrote", OUT, "-", len(E), "entries over", len(src.pages), "pages")
