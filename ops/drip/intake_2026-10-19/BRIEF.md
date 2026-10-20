# Drip intake harvest: shared brief (READ-ONLY task)

Goal: list every **officer/office → duty** target that belongs in the drip registry (`office_obligation`).
A target is a public office or officer, or an institution with a legal duty (e.g. Land Bank, SEC, RD, LRA, DENR,
BLGF, CSC, OMB, OP/PACE, DILG, provincial offices, courts' clerks for certified copies), that **owes us an act**
(records, a decision, a fee assessment, an acknowledgment, a certification, enforcement, a ruling) that we
**requested, demanded, filed or paid for**, or are about to.

NOT targets: private litigants (Balane defendants, transferees in the post-1988 audit), our own counsel
(Barandon, Botor), family heirs (Hoppe, Marcia), or Allan. If a court is the forum, the target is only an
administrative ask (e.g. a certified copy or written order from the clerk), not "win the case".

## Rules (hard)
- READ ONLY. Never INSERT, UPDATE or DELETE anything in the DB. Never send, file or draft outward.
- Never invent a date, a period, an email or a doc id. Every field must come from a file or a DB row you read; cite it.
- One row = one officer + one statutory duty + one instrument. Sub-items of the same duty stay together.
- Statute periods: give the rule as written in our files and mark `NEEDS-COUNSEL-VERIFICATION`.
- **Proof of receipt**: search the corpus for proof that THIS instrument reached THIS office: a received-stamped
  copy, LBC/courier POD, registry return card, or an email acknowledgment/reply from the office.
  - DB: `ssh landtek "docker exec n8n-postgres-1 psql -U n8n -d n8n -Atc \"<sql>\""`
  - `documents` (id, case_file, matter_code, document_title, file_name, document_date, extracted_text, summary)
  - `gmail_messages` (id, from_addr, to_addrs, subject, body_plain, received_at, document_id, matter_codes)
  - Report `proof_doc_id` only if it is a `documents.id` AND the text shows receipt (quote ≤25 words).
    Otherwise `proof_doc_id: null` and say what you found (e.g. "email sent 6 Oct, no reply in gmail_messages").
  - A merely sent email/our own draft is NOT proof of receipt. A reply from the office IS.
- Existing registry rows (do NOT duplicate; if your source adds facts to one, return it with `existing_id`):
  1 Mayor Pajarillo §444(b)(1)(x) · 2 Mayor Pajarillo §444(b)(3)(vi) demolition · 3 Abla chartered service OR 7383466 ·
  4 Macale §252 lapse · 5 Teope demand · 6 Olaguera §469(c) records (withdrawn) · 7 Engr. Balane building official
  (counsel route) · 8 Register of Deeds certification of no donation (F-5).
- Matter codes in use: MWK-001, MWK-CV26360, MWK-TCT4497, MWK-CV6839, MWK-GUARDIANSHIP, MWK-ARTA-1891, MWK-ARTA-1212,
  AUTO-ARTA-1378, MWK-OMB-IC-OC-JUL-26-1214, MWK-OP-PETITION, LANDTEK-OPC-FORMATION, PAR-* (Paracale), NIBDC-*.
  Client separation: never mix MWK / Paracale-Inocalla / NIBDC facts in one row.

## Output
Write a JSON array to the file path given in your task. Each element:
```json
{
 "existing_id": null,
 "matter_code": "MWK-001",
 "officer": "Name as in source",
 "office": "Office, place",
 "obligation": "the one duty, ≤200 chars",
 "instrument_ref": "repo path of OUR letter/request/demand (or 'none built')",
 "statutory_basis": "statute as cited in our files",
 "clock_rule": "period as written + NEEDS-COUNSEL-VERIFICATION, or null",
 "consequence_ref": "pre-built consequence (path or forum)",
 "counsel_gate": "e.g. 'Barandon ONLY — CV 26-360 defendant' or null",
 "email": "only if in source", "email_source": "where",
 "sent_or_filed": "YYYY-MM-DD or null", "sent_source": "file/doc/gmail id",
 "proof_doc_id": null, "proof_excerpt": null, "proof_note": "what you checked",
 "rungs": [{"seq":1,"office":"","officer":"","instrument_ref":"","statutory_basis":""}],
 "money_php": null, "money_source": null,
 "hard_date": null, "hard_date_source": null,
 "unblocks": ["matter codes this act would unblock"],
 "admin_complaint_ripeness": "ripe | building | none: one line why",
 "provenance": "verified | inferred_strong",
 "sources": ["paths / doc ids"],
 "notes": "≤300 chars"
}
```
Finish with a ≤150-word summary: the row count, how many have proof, and anything that looked like a target but you excluded, with the reason.
