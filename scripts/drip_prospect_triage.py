#!/usr/bin/env python3
"""drip_prospect_triage.py — deterministic clean-up of the drip lane after the sweep and the AI pass.

Jonathan, 23 Oct 2026: "our scraper is not very good … there should be hundreds of prospects for a drip". There were
(984 open), but the drip lane was polluted: court steps, lawyer mail and closed ARTA dockets sat beside real office asks,
and one e-mail thread produced the same item five times. This pass routes and merges; it never deletes.

Rules (undecided rows only — a row Jonathan decided is never touched):
  R1 court / clerk / summons / answer / pre-trial / law office / counsel names → lane counsel (Charter §5, X17)
  R2 ARTA, its complaints desk and litigation division → lane hold (cluster closed 25 Aug 2026 on §4(f))
  R2b sourced from a court paper or our own draft (doc_role pleading/order/prime_evidence, or a title naming a complaint,
      draft, exhibit list, affidavit, petition, motion, manifestation, rejoinder) → lane counsel: those "asks" are ours or
      counsel's, not an office's
  R0 already handled (kinds where our answer IS the action: office asks us / reply owed): the prospect's source is an office e-mail (or a letter attached to one), and we wrote back after it,
      in the same thread, or to the same sender on the same subject (a shared word of 5+ letters), never a draft
      → status done ('triage: handled — we wrote <date>, gmail <id>'). Prospects with no mail link are left as they are.
  R2c sourced from OUR OWN paper (our letters/forms signed as attorney-in-fact, playbooks, dossiers, trackers, internal
      work product) → status merged: an ask we already made, or internal, never an office's ask
  R2d by matter: MWK-ARTA-* (cluster closed 25 Aug 2026) → hold; MWK-GUARDIANSHIP / MWK-ESTATE / MWK-CV6839 office-asks and
      court steps (Botor, Agcaoili, court records) → counsel. CV6839 records asks were retired by Jonathan 20 Oct → dismissed
  R4 custodian from the record (office-less rows only; never guessed): an office NAMED in the item's own text wins; else a
      record type whose custodian is fixed by law (title/OCT/TCT → Registry of Deeds, PD 1529; OR/receipt → Treasurer;
      tax declaration/ARP/PIN → Assessor; birth/death/marriage → PSA / civil registrar; survey plan Psd/Csd → DENR / LMS;
      ordinance/resolution → SB Secretary), noted "(by record type)". Rows naming no record at all are fragments of a
      document (headings, narrative) → merged 'triage: fragment, not an ask'
      An office counts only with a custodian verb ("from/held by/issued by the …") or a [TO-OBTAIN from …] tag; record-type
      custodians apply only when the item's title IS a record. Corpus housekeeping (re-OCR, rows, binders) → merged internal.
  R3 same office + same normalized title → status merged into the lowest id (decision_note 'triage: dup of #N')
Each change writes decision_note 'triage: …' so the nightly sweep's upsert keeps the routing.

  python3 scripts/drip_prospect_triage.py [--dry-run]
"""
import argparse
import os
import re

import psycopg2
import psycopg2.extras

from _pgdsn import dsn as _pgdsn  # noqa: E402
DSN = _pgdsn("172.18.0.3:5432" if os.path.isdir("/root/landtek") else "127.0.0.1:15432")
COURT_RX = re.compile(r"(?i)\b(court|mtc|rtc|mctc|judge|clerk of court|branch \d+|summons|pre-?trial|"
                      r"judicial affidavit|subpoena|motion|law offices?|atty\.?|barandon|botor|sese|building official|obo|municipal engineer|balane|torralba|guardianship|solicitor general)\b|\bfile (an |the )?answer\b")
PAPER_RX = re.compile(r"(?i)draft|complaint|exhibit|affidavit|petition|motion|manifestation|rejoinder|pleading|"
                      r"position paper|memorandum|counter|answer|pre-?trial|judicial")
ARTA_RX = re.compile(r"(?i)\barta\b|anti-red tape|complaints handling|litigation division")
STOP = re.compile(r"(?i)\b(the|of|a|an|to|for|and|on|in|by|from|request(s|ed)?|submit|submission|provide|copy|copies)\b")


NAMED = [  # (pattern in the item's text, office) — first match wins
    (r"registry of deeds|register of deeds|registrar of deeds|\bRD\b", "Registry of Deeds, Camarines Norte"),
    (r"provincial assessor|magana", "Provincial Assessor"), (r"municipal assessor|abla", "Municipal Assessor"),
    (r"provincial treasurer", "Provincial Treasurer"), (r"municipal treasurer|macale|\bMTO\b", "Municipal Treasurer"),
    (r"\bLRA\b|land registration authority", "LRA"), (r"\bPENRO\b", "DENR-PENRO Camarines Norte"),
    (r"\bCENRO\b", "DENR-CENRO"), (r"\bDENR\b|\bLMS\b|surveys and mapping", "DENR Region V"),
    (r"\bBIR\b|internal revenue", "BIR RDO 64"), (r"\bPSA\b|civil registr|\bLCR\b", "PSA / civil registrar"),
    (r"sangguniang|\bSB\b|olaguera", "SB Secretary"), (r"\bMLGOO\b|guerrero", "DILG MLGOO"), (r"\bDILG\b", "DILG"),
    (r"\bCOA\b|commission on audit", "COA"), (r"land ?bank|\bLBP\b", "Land Bank"), (r"\bDAR\b", "DAR"),
    (r"clerk of court|\bOCC\b|notarial", "RTC Office of the Clerk of Court, Daet"), (r"ombudsman", "Ombudsman"),
    (r"\bCSC\b|civil service", "CSC"), (r"malaca|\bMRO\b|\bO\.?P\.?\b", "Malacañang Records Office"),
    (r"\bBLGF\b", "BLGF Region V"), (r"\bLBC\b", "LBC"), (r"barangay", "Barangay"), (r"\bmayor\b", "Mayor"),
    (r"building permit|\bOBO\b|\bMEO\b", "Municipal Engineer / OBO")]
BY_TYPE = [
    (r"\b(TCT|OCT|title)\b|T-\d{3,}|patent", "Registry of Deeds, Camarines Norte (by record type)"),
    (r"\bO\.?R\.? (no|number)|official receipt", "Municipal Treasurer (by record type)"),
    (r"tax declaration|\bTD\b|\bARP\b|\bPIN\b", "Assessor (by record type: municipal or provincial)"),
    (r"birth|death|marriage|cenomar", "PSA / civil registrar (by record type)"),
    (r"\b(Psd|Csd|Psu|Cad)-|survey plan|subdivision plan", "DENR Region V / LMS (by record type)"),
    (r"ordinance|resolution no", "SB Secretary (by record type)")]
FRAGMENT_RX = re.compile(r"(?i)^\s*(serves:|§|provenance|r\.a\.|plus interest|\d+\.\s*gaps|gap to confirm|estate posture|"
                         r"carp transfers|interest portion|evidence spine|non-conforming)|not found in corpus")


CUST_VERB = r"(?:from|at|of|ask|asks|request(?:ed)?(?: of| from)?|custodian:?|held by|holds?|kept (?:by|at)|issued by|with)\s+(?:the\s+)?(?:[\w.'’-]+\s+){0,2}?"
RECORD_HEAD_RX = re.compile(r"(?i)^\s*(\d+[.)]\s*)?\**\s*(a\s+)?(certified (true )?cop(y|ies)|copy of|ctc|tax declaration|\bTD\b|"
                            r"\bARP\b|\bTCT\b|\bOCT\b|O\.?R\.? no|official receipt|certificat|approved plan|plan\b|"
                            r"death|birth|marriage|cenomar|resolution no|ordinance|deed\b|patent)")
INTERNAL_RX = re.compile(r"(?i)\bdocs? \d|\brows? \d|re-?ocr|\bOCR\b|ingest|corpus|binder|metadata|chain edge|source document|"
                         r"drive (legal )?copy|canonical archive|caption|honest ledger|prepared (by|\d)")


def custodian(text, title):
    for rx, office in NAMED:   # named WITH a custodian verb: "from the Registry of Deeds", "held by the Treasurer"
        if re.search(CUST_VERB + "(?:" + rx + ")", text, re.I) or re.search(r"\[TO-OBTAIN from[^\]]*(?:" + rx + ")", text, re.I):
            return office
    if RECORD_HEAD_RX.search(title or "") or re.match(r"(?i)\s*request", title or ""):   # the item IS a record (or asks for one): its custodian is fixed by law
        for rx, office in BY_TYPE:
            if re.search(rx, title, re.I):
                return office
    return None


def words(t):
    return {w for w in re.findall(r"[a-z0-9-]{5,}", (t or "").lower())} - {"request", "letter", "copies", "certified", "please", "follow", "jonathan", "zschoche", "mercedes", "camarines", "norte", "keesey", "worrick"}


def norm(t):
    return re.sub(r"\s+", " ", STOP.sub(" ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()))).strip()


OURS_RX = r"(jonzschoche|hayuma\.org|jonpeezee)"

OURS_DOC_SQL = r"""
SELECT d.id FROM documents d
 WHERE d.id IN (SELECT DISTINCT unnest(evidence_doc_ids) FROM drip_prospect WHERE status = 'new' AND lane = 'drip')
   AND (coalesce(d.document_title, d.original_filename, '') ~* '^(zschoche_|mwk[-_]|master_|complete_)|playbook|dossier|tracker|steering|drip|work.?product|briefing|red.?team|directive|binder|hearing.?card|strategy'
        OR left(coalesce(d.extracted_text, ''), 800) ~* '(internal work product|prepared for (lead )?(trial )?counsel|nothing in it has been (filed|sent))'
        -- an e-mail is ours only when WE are the sender (office replies quote our signature at the bottom)
        OR (coalesce(d.document_title, '') ~* '^email' AND left(coalesce(d.extracted_text, ''), 400) ~* 'From: [^\n]*(zschoche|hayuma|jonpeezee)')
        -- a letter is ours when it carries our capacity line and never addresses us (incoming letters say "Dear Mr. Zschoche")
        OR (coalesce(d.document_title, '') !~* '^email'
            AND coalesce(d.extracted_text, '') ~* 'attorney-in-fact (for|of) patricia keesey zschoche'
            AND coalesce(d.extracted_text, '') !~* 'dear (mr\.?|sir|mister) (jonathan |paul )*zschoche'
            AND coalesce(d.extracted_text, '') !~* 'copy furnished:?\s*(mr\.?\s*)?jonathan'))
"""

HANDLED_SQL = r"""
WITH p AS (
  SELECT p.id, p.source_ref, p.evidence_doc_ids[1] AS doc FROM drip_prospect p
   WHERE p.status = 'new' AND p.lane = 'drip' AND p.decided_at IS NULL
     AND p.kind IN ('ai:office_asks_us', 'ai:reply_owed_by_office', 'office_asks_us')
     AND (p.decision_note IS NULL OR p.decision_note LIKE 'triage:%%')),
src AS (
  SELECT p.id, coalesce(
    CASE WHEN p.source_ref LIKE 'gmail_messages:%%' THEN split_part(p.source_ref, ':', 2)::bigint END,
    (SELECT g.id FROM gmail_messages g JOIN documents d ON d.id = p.doc
      WHERE g.id = nullif(substring(d.file_path FROM '/em([0-9]+)_'), '')::bigint),
    (SELECT g.id FROM gmail_messages g JOIN email_documents e ON e.message_id = g.message_id WHERE e.doc_id = p.doc LIMIT 1),
    (SELECT g.id FROM gmail_messages g WHERE g.document_id = p.doc LIMIT 1),
    (SELECT g.id FROM gmail_messages g JOIN documents d ON d.id = p.doc
      WHERE g.message_id = substring(d.file_path FROM 'gmail/([0-9a-f]{16})__')),
    (SELECT g.id FROM gmail_messages g JOIN documents d ON d.id = p.doc
      WHERE g.message_id = substring(d.extracted_text FROM 'Gmail message: ([0-9a-f]{16})'))) AS gid
  FROM p),
m AS (
  SELECT s.id, g.thread_id, g.received_at, g.subject,
         lower(substring(g.from_addr FROM '[A-Za-z0-9._%%+-]+@[A-Za-z0-9.-]+')) AS sender
    FROM src s JOIN gmail_messages g ON g.id = s.gid
   WHERE g.from_addr !~* %(ours)s)
SELECT m.id, m.subject AS src_subject, r.id AS reply_id, r.received_at AS replied_at, r.subject, r.same_thread
  FROM m CROSS JOIN LATERAL (
    SELECT o.id, o.received_at, o.subject, o.thread_id = m.thread_id AS same_thread FROM gmail_messages o
     WHERE o.from_addr ~* %(ours)s AND o.received_at > m.received_at
       AND NOT (coalesce(o.labels::text, '') ~ 'DRAFT')
       AND (o.thread_id = m.thread_id
            OR lower(coalesce(o.to_addrs::text, '') || ' ' || coalesce(o.cc_addrs::text, '')) LIKE '%%' || m.sender || '%%')
     ORDER BY o.received_at LIMIT 20) r
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    c = psycopg2.connect(DSN)
    cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT d.id FROM documents d WHERE d.doc_role IN ('pleading','order_resolution','prime_evidence')
                      OR coalesce(d.document_title, d.original_filename, '') ~* %s""", (PAPER_RX.pattern,))
    papers = {r["id"] for r in cur.fetchall()}
    cur.execute(OURS_DOC_SQL)
    ours = {r["id"] for r in cur.fetchall()}
    cur.execute("""SELECT id, title, detail, office, lane, evidence_doc_ids, matter_code, kind FROM drip_prospect
                    WHERE status = 'new' AND lane = 'drip' AND decided_at IS NULL
                      AND (decision_note IS NULL OR decision_note LIKE 'triage:%%') ORDER BY id""")
    rows = cur.fetchall()
    cur.execute(HANDLED_SQL, {"ours": OURS_RX})
    handled = {}
    for h in cur.fetchall():
        if h["id"] in handled:
            continue
        if h["same_thread"] or (words(h["src_subject"]) & words(h["subject"])):
            handled[h["id"]] = h
    moves, seen, merged, done, dismiss, assign = [], {}, [], [], [], []
    for r in rows:
        if r["id"] in handled:
            h = handled[r["id"]]
            done.append((r["id"], f"triage: handled — we wrote {h['replied_at']:%Y-%m-%d}, gmail_messages {h['reply_id']}"))
            continue
        hay = f"{r['office'] or ''} {r['title'] or ''}"
        mc = r["matter_code"] or ""
        if mc.startswith("MWK-ARTA-"):
            moves.append((r["id"], "hold", "triage: ARTA cluster closed 25 Aug 2026"))
            continue
        if mc == "MWK-CV6839" and r["kind"] == "ai:records_request":
            dismiss.append((r["id"], "triage: CV6839 records asks retired by Jonathan 20 Oct 2026"))
            continue
        if mc in ("MWK-GUARDIANSHIP", "MWK-ESTATE", "MWK-CV6839") and r["kind"] in ("ai:office_asks_us", "ai:litigation_step", "ai:reply_owed_by_office"):
            moves.append((r["id"], "counsel", f"triage: {mc} court/law-firm item"))
            continue
        if COURT_RX.search(hay):
            moves.append((r["id"], "counsel", "triage: court/counsel item"))
            continue
        if ours.intersection(r["evidence_doc_ids"] or []):
            merged.append((r["id"], "our own paper"))
            continue
        if papers.intersection(r["evidence_doc_ids"] or []):
            moves.append((r["id"], "counsel", "triage: from a court paper / our own draft"))
            continue
        if ARTA_RX.search(hay):
            moves.append((r["id"], "hold", "triage: ARTA cluster closed 25 Aug 2026"))
            continue
        if (r["office"] or "").strip().lower() in ("", "null", "none"):
            text = f"{r['title'] or ''} {(r['detail'] or '')[:400]}"
            if FRAGMENT_RX.search(r["title"] or ""):
                merged.append((r["id"], "fragment"))
                continue
            if INTERNAL_RX.search(r["title"] or ""):
                merged.append((r["id"], "internal"))
                continue
            off = custodian(text, r["title"] or "")
            if off:
                assign.append((r["id"], off))
            elif r["kind"] == "to_obtain":
                merged.append((r["id"], "fragment"))
                continue
        k = (norm(r["office"])[:40], norm(r["title"])[:80])
        if k[1] and k in seen:
            merged.append((r["id"], seen[k]))
        else:
            seen[k] = r["id"]
    print(f"{len(rows)} open drip prospects · {len(done)} already handled · {sum(1 for m in moves if m[1]=='counsel')} → counsel · "
          f"{sum(1 for m in moves if m[1]=='hold')} → hold · {len(merged)} merged as duplicates · {len(dismiss)} dismissed · {len(assign)} custodians assigned · "
          f"{len(rows) - len(moves) - len(merged) - len(done) - len(dismiss)} stay in the drip lane")
    if a.dry_run:
        return
    for pid, lane, note in moves:
        cur.execute("UPDATE drip_prospect SET lane=%s, decision_note=%s WHERE id=%s", (lane, note, pid))
    for pid, off in assign:
        cur.execute("UPDATE drip_prospect SET office=%s, decision_note=%s WHERE id=%s", (off, "triage: custodian from the record", pid))
    for pid, note in dismiss:
        cur.execute("UPDATE drip_prospect SET status='dismissed', decision_note=%s WHERE id=%s", (note, pid))
    for pid, note in done:
        cur.execute("UPDATE drip_prospect SET status='done', decision_note=%s WHERE id=%s", (note, pid))
    for pid, keep in merged:
        note = {"our own paper": "triage: from our own paper (already asked, or internal)",
                "fragment": "triage: fragment of a document (heading/narrative), not an ask",
                "internal": "triage: internal corpus housekeeping (OCR/ingest/rows), not an office ask"}.get(keep, f"triage: dup of #{keep}")
        cur.execute("UPDATE drip_prospect SET status='merged', decision_note=%s WHERE id=%s", (note, pid))
    c.commit()


if __name__ == "__main__":
    main()
