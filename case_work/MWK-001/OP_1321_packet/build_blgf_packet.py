#!/usr/bin/env python3
"""Bind the BLGF RO-V supervision packet: letter+AnnexA + Annexes B-H, 8.5x13."""
import os
from pypdf import PdfReader, PdfWriter
from build_op_packet import normalize, stamp, jpeg_to_pdf_page, S
from reportlab.platypus import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
MWK = os.path.dirname(HERE)
SRC = os.path.join(HERE, "source")

ANNEXES = [
    ("B", "Municipal Assessor's letter, 16 June 2025", [("jpeg", os.path.join(SRC, "AnnexC_doc895_16jun_letter.jpeg"))]),
    ("C", "ARTA Resolution, 25 August 2026 (CTN SL-2026-0209-1321), resolution proper", [("trim11", os.path.join(SRC, "AnnexA_resolution_part1.pdf"))]),
    ("D", "Specimen productions of the Provincial Assessor's Office",
     [("pdf", os.path.join(SRC, "AnnexE_doc561_TD1693.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc115_ledger_brgy5.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc116_ledger_brgy1.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc467_brgy5_arps.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc151_munhall_arp.pdf")),
      ("pdf", os.path.join(SRC, "AnnexE_doc105.pdf"))]),
    ("E", "Email to the Municipal Assessor, 1 October 2025", [("pdf", os.path.join(HERE, "AnnexD_email.pdf"))]),
    ("F", "Municipal Assessor's Counter-Affidavit, sworn 28 May 2026", [("pdf", os.path.join(SRC, "AnnexF_doc1046_counter_affidavit.pdf"))]),
    ("G", "CART Resolution No. 6, s. 2026 (6 April 2026)", [("pdf", os.path.join(SRC, "SuppB_CART_Res6.pdf"))]),
    ("H", "Escalation letter of 29 June 2026 and follow-up of 13 July 2026 (with Annexes A-E), as transmitted",
     [("pdf", os.path.join(SRC, "BlgfH_escalation_29jun.pdf")), ("pdf", os.path.join(SRC, "BlgfH_followup_13jul.pdf"))]),
    ("I", "BLGF Regional Office V written declination, 24 August 2026 (released 3 September 2026)",
     [("trim1", os.path.join(SRC, "AnnexI_BLGF_ROV_declination_24Aug.pdf"))]),
]

out = PdfWriter()
for pg in PdfReader(os.path.join(MWK, "JOINT_SUPERVISION_BLGF_MAGANA.pdf")).pages:
    out.add_page(normalize(pg))

for letter, desc, parts in ANNEXES:
    pages = []
    for kind, src in parts:
        if kind == "pdf":
            pages += list(PdfReader(src).pages)
        elif kind == "trim11":
            r = PdfReader(src)
            pages += [r.pages[i] for i in range(11)]
        elif kind == "trim1":
            pages += [PdfReader(src).pages[0]]
        else:
            pages.append(jpeg_to_pdf_page(src))
    for pg in pages:
        out.add_page(stamp(normalize(pg), letter))
    print(f"Annex {letter}: {len(pages)} pp")

OUT = os.path.join(MWK, "BLGF_CO_Supervision_Packet_8.5x13.pdf")
with open(OUT, "wb") as f:
    out.write(f)
r = PdfReader(OUT)
sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages}
print("BOUND:", OUT, len(r.pages), "pp, sizes:", sizes)
