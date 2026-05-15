# ⚡ READ FIRST: /root/landtek/DIRECTIVE.md

This is the authoritative 48-hour playbook (May 12-14, 2026).
Run `cat /root/landtek/DIRECTIVE.md` before answering anything ambiguous from Jonathan.
The directive defines:
- What "go", "status", "extract X", "verify Y", "draft Z" mean
- The accuracy posture (gemini-2.5-flash only, quality 0.8, 2-pass cross-validation)
- Hard stops + safe operations
- The North Star deliverables by May 14 noon Manila

---

# LANDTEK — Evidence-grade RAG database for Philippine property cases

You are Claude Code running on the LandTek VPS. This file is your project memory.
A user is connecting from their phone via Tailscale+Termius. They need quick, decisive answers.

## Active matter (priority context)

**Civil Case No. 26-360 (Zschoche v. Balane)** — accion reinvindicatoria over TCT T-4497
and its derivative titles. Patricia Keesee Zschoche (US, mother of user Jonathan Zschoche)
is plaintiff, represented by Atty. Bonifacio Jr. Barandon (Barandon Law Offices, Daet).
Defendants: Gloria Balane et al. who hold contested TCT T-079-2021002126 (issued 2021 from
cancelled T-52540 via 2016 Deed of Sale executed by Cesar de la Fuente under an SPA
revoked in 2005).

**Pretrial conference notice received April 28, 2026** — confirm date with most recent
Barandon email.

## What this database tracks

Mother title: **TCT T-4497** (Heirs of Mary Worrick Keesey)
- Major derivatives: T-32916 (Lot 2-X-4 Brgy 3), T-32917 (Lot 2-X-6 San Roque),
  T-31298 (lost annotations)
- Under T-32917: 17 sub-subdivisions (Lots 2-X-6-A through 2-X-6-V) → titles
  T-38838, T-47655, T-47656, T-47657, T-48335, T-48336, T-49037, T-49060,
  T-49061, T-49062, T-52354, T-52536-T-52540
- T-30683 (Manguisoc Mercedes) and T-4494 (Cabanbanan San Vicente) are SEPARATE
  properties — NOT verified derivatives of T-4497, treat as own matters

## 20 named transferees (defendants/parties of interest)

Alberto Victa, Ananias Apor, Arnel Mabeza, Aurora Bernardo, Cesar Ramirez,
Delfin Gaulit, Dolores Vela, Edgardo Santiago, Elsa Illigan, Erlinda Tychingco,
Jose Pascual Jr., Librada B. Onrubio, Maria V. Cereza, Mariquita Era,
Pedro Valledor, Rosalina Hansol, Roscoe Leaño, Ruben Ocan, Severino Tenorio Jr.,
**Gloria Balane** (the flagship attack).

## Hallucination-proof discipline (CRITICAL)

Every fact in the database carries a `provenance_level`:
- **verified** = directly cited to a source doc with a quoted excerpt
- **inferred_strong** = LLM-extracted from grounded source, not yet human-verified
- **inferred_weak** = pattern match / co-occurrence, low confidence

**For any legal output (briefs, demand letters, complaints, evidence packs), read ONLY
the `_safe` views** (titles_safe, title_chain_safe, title_transfers_safe, transferees_safe,
entities_safe, doc_entities_safe, transfer_documents_safe, transfer_doc_status_safe).
Anything inference-grade must be marked "PENDING VERIFICATION" in output, never presented
as fact. Hallucinations will kill this project.

## Database access

Postgres in docker container `n8n-postgres-1`:
```
PG_DSN=postgresql://n8n:n8npassword@172.18.0.3:5432/n8n
```
or `docker exec -i n8n-postgres-1 psql -U n8n -d n8n` from shell.

Key tables:
- `documents` — 388 indexed legal documents in MWK-001 case_file
- `titles` — 45 TCTs in the title map
- `title_chain` — parent → derivative title edges with provenance_level
- `title_transfers` — 41 transfer events (15 verified, 26 placeholders)
- `transferees` — 20 named persons
- `instruments_on_title` — per-encumbrance executor + notary breakdown (the void-SPA query lives here)
- `entities` — 2,506 people/orgs/refs
- `extraction_chunks` — RAG chunks (one per field/encumbrance/fraud_indicator/full_text per doc)
- `extraction_contract` — versioned extraction schemas (current: tct_v3_canonical)
- `fraud_indicators` — visual anomalies flagged on title docs
- `doc_requirements_law` — 36 PH property law rules
- `transfer_doc_status` — 486 per-transfer rule evaluations (the evidence-gap engine)
- `case_threads` — 5 threads, Thread 5 is RD Camarines Norte title-history thread
- `gmail_messages` — ingested case-relevant emails

Useful views: `transfer_completeness`, `evidence_action_list`, `evidence_status_per_transferee`,
`instruments_under_authority` (the revoked-SPA query).

## Credentials and external services

Env file: `/root/landtek/.env` (chmod 600). Contains:
- `GEMINI_API_KEY` — for vision OCR (uses gemini-2.5-flash, fallback 2.0-flash)
- `GMAIL_REFRESH_TOKEN` — for Gmail API access to jonzschoche@gmail.com
- Postgres password etc.

Drive Service Account: `/root/landtek/google-creds.json`
- Email: `leolandtek-docai@landtek.iam.gserviceaccount.com`
- The LANDTEK Drive folder is shared with this SA (folder ID `1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP`)
- 864 PDFs accessible, 329 of them are MWK-001 with `drive_file_id` populated

Heightened OCR runner: `/root/landtek/heightened_ocr/` — uses Gemini PDF-native extraction
against contract `tct_v3_canonical` (`/root/landtek/heightened_ocr/prompt_tct_v3_canonical.txt`).

Leo tools Flask service: `/root/landtek/leo_tools/server.py` on port 8765. Exposes
`/api/get_entity`, `/api/fuzzy_find_entity`, `/api/get_thread`, `/api/list_threads`,
`/api/query_documents`, `/api/pending_entity_types`. n8n calls these.

## Deploy pipeline (how to push a change)

This VPS has a `cowork-bridge` daemon that polls a GitHub repo every 30s.
Push a shell script to:
```
git@github.com:jonzschoche-dev/leolandtek-deploys.git → inbox/NNN_name.sh
```
or via the local clone at `/opt/cowork-bridge/repo`. The daemon executes the script with a
30-min timeout and writes output to `outbox/`.

To run a one-shot command on the VPS, you can also just use the Bash tool — you have
direct shell access. The deploy pipeline is for batch/scheduled work that needs auditing.

Daemon control: `systemctl status cowork-bridge` / `systemctl restart cowork-bridge`
Log: `/var/log/cowork-bridge.log`

## n8n + Leo

n8n at port 5678 (workflow ID `vSDQv1vfn6627bnA` = "Leos Workflow"). Triggered by Telegram
bot @LeoLandTekBot. Tool nodes hit the leo-tools Flask above. Thread #5 scope discipline
is enforced via `thread_scope_sql` predicate.

## Current operational state (snapshot)

- 388 documents indexed, 329 with drive_file_id
- 6 TCTs fully extracted via heightened Gemini OCR (T-32917, T-32916, T-52540 ×2, T-32915, +1)
- 28+ encumbrances on T-32917 captured with executor + notary
- 6 fraud_indicators flagged
- 40 case-relevant emails ingested (Civil Case 26-360 thread visible)
- ~85 TCTs still queued for heightened extraction

## Recommended first actions when user connects from phone

1. Read this file (you just did)
2. Run `psql ... -c "SELECT * FROM transfer_completeness ORDER BY completeness_pct ASC LIMIT 5"` to see most-incomplete transfers
3. Ask user what they want to do today

## Critical do-nots

- Don't present inference-grade data as fact in legal output
- Don't make up TCT relationships — verify via title_chain WHERE provenance_level='verified'
- Don't assume Cabanbanan/San Vicente land is part of the T-4497 case (it's a separate matter)
- Don't run unauthenticated Gemini calls in tight loops (use the fallback key on 429)
