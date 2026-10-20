#!/usr/bin/env python3
"""drip_stager.py — Mac side of the drip: turns "make the draft" into an UNSENT draft. NEVER SENDS. NEVER PRINTS.

For every drip_instrument in status 'ready_for_draft' (Jonathan's word recorded as approval_ref):
  1. Builds the letter PDF (14 pt, 8.5x13) from its markdown; fills a '___' date line with today's date.
     E-mail: e-signed + SPA as Annex "A".   Paper: unsigned print set (2 copies: original + receiving copy) + task card.
  2. E-mail: saves an unsent draft in the Mail.app account of the thread's origin (send_account), as a reply in the
     thread when reply_subject is known, else a new message; To/Cc from the record. Verifies it sits in Drafts with
     the attachment.  Paper: writes the print set + a Kristyle task card next to the letter (no printing).
  3. Records it: status 'draft_staged', file_path, work order note, drip_event 'staged'.
Anything missing (recipient, letter file, account) → left 'ready_for_draft' with a work-order note; nothing guessed.

  python3 scripts/drip_stager.py            # one pass (the LaunchAgent runs this)
  python3 scripts/drip_stager.py --dry      # build PDFs + print the plan; no Mail.app, no DB writes
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

import psycopg2
import psycopg2.extras

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MWK = os.path.join(REPO, "case_work", "MWK-001")
sys.path.insert(0, os.path.join(MWK, "DENR_ASSESSOR_PACKET_2026-10"))
sys.path.insert(0, os.path.join(MWK, "OP_1321_packet"))
from build_op_packet import render_md, normalize, stamp  # noqa: E402
import build_packet  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@127.0.0.1:15432/n8n")
SPA = {"MWK-001": os.path.join(MWK, "SCHEDULE_SERVICE_LGU_2026-10", "source", "A4_SPA_apostilled.pdf")}
ACCOUNT = {"jonzschoche@gmail.com": "Google", "jonathan@hayuma.org": "jonathan@hayuma.org"}


def esign(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    for page in doc:
        hits = page.search_for("JONATHAN PAUL ZSCHOCHE")
        resp = page.search_for("Respectfully yours,") or page.search_for("Respectfully,")
        if hits and resp:
            name, r = hits[-1], resp[-1]
            h = name.y0 - r.y1 + 6
            w = h * 2383 / 1266
            box = fitz.Rect(name.x0 - 4, name.y0 - h + 4, name.x0 - 4 + w, name.y0 + 4)
            page.insert_image(box, filename=build_packet.SIG_IMG, overlay=True)
            doc.save(pdf_path + ".tmp")
            doc.close()
            os.replace(pdf_path + ".tmp", pdf_path)
            return True
    raise RuntimeError("no signature block")


def build_pdf(md_path, client, paper, today):
    text = open(md_path, encoding="utf-8").read()
    dated = re.sub(r"^_+\s+(?:\w+\s+)?20\d\d$", today, text, count=1, flags=re.M)
    if dated != text:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(dated)
    m = re.search(r"\*\*Re:\s*(.+?)\*\*", dated)
    re_line = m.group(1).strip() if m else os.path.basename(os.path.dirname(md_path))
    sal = re.search(r"^(Dear [^\n:]+):", dated, re.M)
    footer = "Zschoche — " + re_line[:90]
    tmp = render_md(md_path, md_path.replace(".md", "_tmp.pdf"), footer, letter_mode=True)
    if not paper:
        esign(tmp)
    letter = [normalize(p) for p in PdfReader(tmp).pages if (p.extract_text() or "").strip()]
    annex = [stamp(normalize(p), "A") for p in PdfReader(SPA[client]).pages] if client in SPA else []
    pages = (letter + annex) * (2 if paper else 1)
    w = PdfWriter()
    for p in pages:
        w.add_page(p)
    tag = "PRINTSET_2copies_unsigned" if paper else "signed"
    out = os.path.join(os.path.dirname(md_path), f"Zschoche_{os.path.basename(os.path.dirname(md_path))}_{today.replace(' ', '')}_{tag}.pdf")
    with open(out, "wb") as f:
        w.write(f)
    os.remove(tmp)
    return out, re_line, (sal.group(1) if sal else "Good day")


APPLESCRIPT = r'''
on run argv
  set acctName to item 1 of argv
  set toAddr to item 2 of argv
  set ccList to item 3 of argv
  set replySubj to item 4 of argv
  set newSubj to item 5 of argv
  set bodyText to item 6 of argv
  set pdfPath to item 7 of argv
  tell application "Mail"
    set acct to account acctName
    set target to missing value
    if replySubj is not "" then
      repeat with mb in (mailboxes of acct)
        if name of mb is in {"INBOX", "All Mail"} and target is missing value then
          set ms to (messages of mb whose subject contains replySubj)
          if (count of ms) > 0 then set target to item 1 of ms
        end if
      end repeat
    end if
    if target is not missing value then
      set r to reply target with opening window
    else
      set r to make new outgoing message with properties {subject:newSubj, visible:true}
      tell r to make new to recipient at end of to recipients with properties {address:toAddr}
    end if
    delay 1
    set em to (get email addresses of acct)
    set fn to (get full name of acct)
    set sender of r to fn & " <" & (item 1 of em) & ">"
    if ccList is not "" then
      set AppleScript's text item delimiters to ","
      repeat with c in (text items of ccList)
        tell r to make new cc recipient at end of cc recipients with properties {address:(c as string)}
      end repeat
      set AppleScript's text item delimiters to ""
    end if
    set content of r to bodyText
    tell content of r to make new attachment with properties {file name:(POSIX file pdfPath) as alias} at after last paragraph
    delay 2
    set savedSubj to (get subject of r)
    save r
    delay 3
    close r saving no
    return "saved:" & savedSubj
  end tell
end run
'''


def stage_mail(acct, to, cc, reply_subj, subj, body, pdf):
    p = subprocess.run(["osascript", "-", acct, to or "", ",".join(cc or []), reply_subj or "", subj, body, pdf],
                       input=APPLESCRIPT, capture_output=True, text=True, timeout=180)
    if p.returncode != 0 or "saved:" not in p.stdout:
        raise RuntimeError((p.stderr or p.stdout).strip()[-400:])
    return p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    today = datetime.date.today().strftime("%-d %B %Y")
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT i.*, sp.ladder, sp.matter_code FROM drip_instrument i LEFT JOIN step_plan sp ON sp.id=i.step_plan_id
                    WHERE i.status='ready_for_draft' AND i.approval_ref IS NOT NULL ORDER BY i.id""")
    for i in cur.fetchall():
        md = os.path.join(REPO, i["file_path"]) if i["file_path"] and i["file_path"].endswith(".md") else None
        acct = ACCOUNT.get(i["send_account"] or "")
        paper = (i["send_account"] == "paper")
        problem = None
        if not md or not os.path.isfile(md):
            problem = "letter markdown not found"
        elif not paper and not acct:
            problem = f"no Mail.app account for send_account={i['send_account']!r}"
        elif not paper and not (i["to_address"] or i["reply_subject"]):
            problem = "no recipient: set to_address or reply_subject"
        if problem:
            print(f"#{i['id']} SKIP: {problem}")
            if not a.dry:
                cur.execute("""UPDATE work_orders SET title=left(title,300)||%s, updated_at=now()
                                WHERE kind='drip_stage_draft' AND target_ref=%s AND title NOT LIKE %s""",
                            (f" — STAGER BLOCKED: {problem}", f"drip_instrument:{i['id']}", f"%{problem}%"))
                c.commit()
            continue
        pdf, re_line, sal = build_pdf(md, i["client_code"], paper, today)
        if a.dry:
            print(f"#{i['id']} DRY: {'paper print set' if paper else acct} → {i['to_address'] or '(reply in thread)'} "
                  f"cc {i['cc_addresses'] or '—'} | {pdf}")
            continue
        if paper:
            card = os.path.join(os.path.dirname(md), f"TASK_CARD_{os.path.basename(os.path.dirname(md))}.md")
            with open(card, "w") as f:
                f.write(f"# Service task: {i['ladder']} (#{i['id']})\n\n- Print: `{os.path.basename(pdf)}` "
                        "(2 copies: original + receiving copy), 8.5x13, 14 pt. **Print only on Jonathan's print go.**\n"
                        "- Sign the original in ink above the name.\n- Serve by hand; get the office's RECEIVED stamp "
                        "(date, time, name) on the receiving copy.\n- Photograph the stamped copy the same day and send it "
                        "in for ingest. The clock starts from that stamp.\n")
            where = f"print set {pdf} + {card}"
        else:
            subj = ("Re: " + i["reply_subject"]) if i["reply_subject"] else re_line
            body = (f"{sal},\n\nGood day. Please find attached my letter of {today}, with the Special Power of Attorney "
                    "as Annex \"A\".\n\nThank you very much for your time and assistance.\n\nRespectfully yours,\n"
                    "Jonathan Paul Zschoche\nAttorney-in-Fact for Patricia Keesey Zschoche\n0966-698-1448 | jonzschoche@gmail.com\n")
            if i.get("is_test"):
                subj = "[TEST DRIP — do not send] " + subj
            where = stage_mail(acct, i["to_address"], i["cc_addresses"], i["reply_subject"], subj, body, pdf)
        cur.execute("""UPDATE drip_instrument SET status='draft_staged', file_path=%s, updated_at=now() WHERE id=%s""",
                    (os.path.relpath(pdf, REPO), i["id"]))
        cur.execute("""UPDATE work_orders SET status='awaiting_handoff', title=left(title,300)||%s, updated_at=now()
                        WHERE kind='drip_stage_draft' AND target_ref=%s""",
                    (" — STAGED; Jonathan to review + Send" if not paper else " — PRINT SET READY; print on Jonathan's go",
                     f"drip_instrument:{i['id']}"))
        cur.execute("INSERT INTO drip_event (kind, detail) VALUES ('staged', %s)",
                    (json.dumps({"instrument": i["id"], "where": where, "test": bool(i.get("is_test"))}),))
        c.commit()
        print(f"#{i['id']} STAGED: {where}")


if __name__ == "__main__":
    sys.exit(main())
