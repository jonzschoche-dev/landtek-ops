# Verification Playbook — MWK-ARTA-1891 Ombudsman Affidavit (pre-draft work order)

> **Purpose.** This is NOT a draft. It is the exact work order to ground the ARTA-1891
> Ombudsman Complaint-Affidavit in verified record BEFORE any drafting. Per the system's
> provenance discipline (A2 / A20 / Principle 9), a filing may only rest on `verified`
> facts (cited doc + verbatim excerpt). The 1891 dossier currently shows **0 verified
> facts / 0 of 9 docs read** — so the dispositive exhibits must be source-read first.
>
> **Fuel.** Token-free. Run on the local Ollama tier (verify_worker / source_read_facts).
> No API calls, no DB schema change. The DB already has every table the affidavit needs.
>
> **Author.** Recon pass 2026-07-10 (Hermes, DESIGNER window). Not legal advice.

---

## 0. Why this exists before drafting

The affidavit blueprint (`playbooks/ombudsman_1891.json`) is built on ONE dispositive fact:

> *"The officials sat in judgment of complaints against their own offices"* — anchored to
> the LGU's own **6 April 2026 CART minutes** (doc 709 hearing record, doc 711 minutes).

That fact is the spine of the entire conflict-of-interest / grave-misconduct theory
(RA 3019 §3(e)/(f), RA 6713 §4(a)). If 709/711 are not source-read and verified, the
affidavit would be built on inference — which the system forbids for a filing. This
playbook closes that gap first.

---

## 1. The dispositive exhibits — MUST be source-read + verified (P0)

| Doc | What it is (per status memo) | Verified fact(s) it should yield | Status to confirm on VPS |
|---|---|---|---|
| **709** | 6 Apr 2026 CART hearing record — **the dispositive exhibit** | The Mayor + SB members present/participating while the committee disposed of the 7 complaints against their own offices; no inhibition | readable? text present? |
| **711** | 6 Apr 2026 CART minutes of meeting | Same — the official minute reciting presence + participation + the resolutions passed | readable? text present? |
| **708** | Standalone Complaint + Manifestation + Request for Supervisory Review (the operative pleading) | The 3 procedural grounds (COI / inadequate notice / withholding); the specific resolutions 1–6 attacked | readable? (dossier says "unread") |

> These three are non-negotiable. The affidavit cannot be drafted without them verified.

---

## 2. The referral / chronology exhibits — source-read (P1)

Each yields verified facts that frame the "agencies deflected" narrative (the predicate
for the Ombudsman dereliction angle).

| Doc | What it is | Verified fact(s) to yield |
|---|---|---|
| **724** | Formal Demand for Direct Administrative Enforcement → DILG Prov. Dir. Relucio (6 Apr 2026) | The records-obstruction pattern + ₱2.6M Sports Complex spending flag |
| **690 / 687** | CTN SL-2026-0423-1891 (ARTA docket) | The assigned CTN; filing date |
| **705** | ARTA §17(d) referral → DILG (4 May 2026) | Statutory referral; DILG's receipt |
| **688** | ARTA §17(d) referral → CSC (OACL, Atty. Ronquillo) | The RA 6713 track opened |
| **689** | NOR-CTN SL-2026-0423-1891 (CSC) | CSC docket |
| **691** | Gmail — ARTA Referral of Complaint | The referral transmitted |
| **701** | DILG-CART endorsement → RD DILG Region V (Escober) (6 May 2026) | DILG routed to RD; "cascade" posture begins |
| **1086** | DILG Region 5 Notice of Referral (25 May / 2 Jun 2026) | DILG's continuing deflection |
| **1189** | OP Second Manifestation → Exec. Sec. Recto | The escalation to the Office of the President |
| **728** | Letter to Jonathan Zschoche (LGU response) | The LGU's position / the illegal SPA/additional-requirement claim |

---

## 3. The two charge elements — what verified facts prove them

From `ombudsman_1891.json`, the affidavit has two elements. Map each source-read doc to
the element it supports:

**Element A — Manifest partiality via sustained, cross-department records refusal**
(RA 3019 §3(e)/(f); RA 6713 §4(a))
- Proven by: 724 (demand + obstruction), 728 (illegal SPA requirement), 708/709/711
  (the CART's own record of refusal), the follow-up trail (701/1086) showing no written
  disposition.

**Element B — Operative directive with no basis in law** (RA 11032 §21(b))
- Proven by: 728 (SPA-from-all-heirs + proof-of-legal-personality requirement not in the
  Citizen's Charter) + 724. This is the *additional-requirement* violation — cleanest
  statutory hook because it's textually prohibited.

> **Dispositive frame (the lead):** doc 709 + 711 — officials sat on the body that
> adjudicated complaints against their own offices and did not inhibit. This is the
> spine; Elements A/B are the supporting charges.

---

## 4. The law — already embedded, no fetch needed

Per ONTOLOGY A53 (law-completeness check 59/59, 0 gap): RA 3019, RA 6713, RA 11032,
PD 1529, RA 6657, RA 7942, LGC, Civil Code, RPC, Constitution are all locally embedded
and retrievable by `legal_authority.retrieve(forum, q)`. The affidavit's statutory cites
are available offline. The only law-side caution (from memo_1891_status §3): *"Statutory
text is verify-vs-official; MC numbers are quoted from the complaint, doc:708"* — so
confirm ARTA MC 2020-07 / 2021-08 / 2021-11 against official copies before filing.

---

## 5. Gaps to close (from the playbook + dossier)

1. **Confirm each elective respondent's identity + term of office** (Mayor Pajarillo and
   the named SB members who sat on the CART). Elective = Ombudsman forum; appointive =
   parallel CSC track (RA 6770 vs RA 6713). Charge each in the correct forum.
2. **Produce 709 + 711 as the named annexes** — the dispositive exhibit. If not yet in
   corpus with readable text, this is the #1 blocker.
3. **Pin the per-office request letters as annexes** (Assessor request 27 May 2025;
   Treasurer request 28 May 2025) in received/stamped form — the predicate for Element A's
   "sustained refusal" across departments.
4. **Affidavit affiant** — who swears it? (Jonathan as attorney-in-fact for Patricia, per
   the CV-26360 pattern.) Confirm.

---

## 6. How to run this (token-free, on the VPS EXECUTOR)

```bash
# 1) confirm the dispositive exhibits are in corpus + readable
python3 scripts/source_read_facts.py --matter MWK-ARTA-1891 --dry   # lists unread docs

# 2) earn verified facts from the operative + dispositive docs (local Ollama, $0)
python3 scripts/verify_worker.py --matter MWK-ARTA-1891 --limit 20 --go

# 3) re-read the 9 docs the dossier flagged (parallel sweep)
python3 scripts/verify_worker.py --docs 708,709,711,724,701,705,688,1189,728 --go

# 4) regenerate the dossier so the INDEX reflects new verified depth
python3 scripts/case_dossier.py --all
```

> Do NOT enable `landtek-reocr-sweep` (metered Gemini). If 709/711 are OCR-garbled, use
> `reocr_local.py` (owned qwen2.5vl, $0) — already the default local path.

---

## 7. Exit criteria — when drafting may begin

The affidavit may be drafted ONLY when:
- [ ] doc 709 + 711 source-read and verified (the dispositive COI fact quoted verbatim)
- [ ] doc 708 source-read and verified (the 3 procedural grounds)
- [ ] Element A + Element B each backed by ≥1 verified fact with excerpt
- [ ] RA 11032 §21(b), RA 3019 §3(e)/(f), RA 6713 §4(a) confirmed retrievable from embedded law
- [ ] respondents' elective/appointive status confirmed (forum split)
- [ ] 1891 dossier shows >0 verified facts (re-run case_dossier.py)

Until then: **design only.** Drafting now = inference-grade filing = forbidden.

---

*Recon artifact — no affidavit text, no DB changes. Next step is your call: run §6 on the
VPS, or decide on the DB question first.*
