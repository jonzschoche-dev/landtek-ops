# Document & Signal Model — DRAFT (extends ONTOLOGY §2.17)

> **STATUS: DRAFT — pending ingestion-agent coordination. NOT yet finalized into `ONTOLOGY.md` §2.17 or §4.**
> This proposal models an extended document/signal/filing architecture as first-class ontology concepts. It is
> **modeling of existing reality**, not new schema — every concept below is grounded in columns/tables that
> already exist (verified live 2026-07-08). No code or DB change is proposed. Once the ingestion agent confirms
> the models are practical for the remediation flow, the concepts graduate into §2.17 and the DRAFT invariants
> (A44–A47) into §4. Builds on §2.17 (`ConnectedDocument`, the 5-signal `ConnectivityGate`, `ProvenanceStamp`)
> and stays strictly aligned with **A41** (all 5 signals) · **A42** (provenance earned) · **A43** (gate fail-closed).

---

## 1. DocumentSignal — a typed connection signal on a document

> **Definition.** A `DocumentSignal` is one typed, per-document fact about how connected/usable a document is,
> produced by a specific stage and carrying its own source. The **5 mandatory signals are the A41
> `ConnectivityGate`**; the model is a *superset* so new signal types can be added without touching the gate.

| Signal (type) | Canonical source (live) | Kind | In the A41 gate? |
|---|---|---|---|
| `text` | `documents.extracted_text` / `text_length` (≥50) | deterministic | ✅ mandatory |
| `ocr_quality` | `ocr_quality.score/flagged` (latest) | deterministic | ✅ mandatory |
| `document_type` | `documents.document_type` ← `document_type_proposals` | deterministic-or-earned | ✅ mandatory |
| `embedded` | 🟢 `corpus_backfill_state.embedded` **(the one canonical source — NOT `rag_local`)** | deterministic | ✅ mandatory |
| `provenance` | 🟢 `documents.model_used` ← a completed `extraction_runs` row | **EARNED** (A42) | ✅ mandatory |
| `tracker_baselined` | `paracale_corpus_watch` (INGESTION §DONE signal 6) | deterministic | ○ optional (not gated) |
| `vision_caption` | `documents.vision_caption` (+ model/at) | earned | ○ optional (not gated) |

**Relationship to A41–A43.** `ConnectedDocument` ⇔ AND of the **5 mandatory** signals (unchanged). Optional
signals (tracker, vision_caption, future) are *additive metadata* — they enrich a doc but **do not change the
gate**. This is the extensibility guarantee: a new signal type is registered here and read where cheapest;
promoting one into the *mandatory* gate is a governance act (a version bump + a new/edited invariant), never
implicit. So A41's definition stays stable while the corpus grows richer.

**Extraction paths & provenance.** Signals arrive from different stages, each stamping its own provenance:
re-OCR (`reocr_gemini` → `extraction_runs` → earns `provenance` + refreshes `text`/`ocr_quality`/`type`/`embedded`
in one txn, A41-safe by construction); deterministic backfill (`corpus_backfill`/§3.5 sweep → the 4 cheap
signals, no `provenance`); classify pass (→ `document_type`). **A signal's source is never fabricated** — the
`provenance` signal in particular is earned-only (A42, guarded by V8 shadow).

---

## 2. DocumentClassification — what a document IS (typed identity + adjudication)

> **Definition.** A `DocumentClassification` is the typed identity of a document (Deed, TCT, Affidavit, Mining
> Permit, Correspondence…) plus the **adjudication trail** that produced it — supporting *both* deterministic
> and LLM classifiers with confidence and source, so no guess is silently promoted to fact.

| Concept | Canonical home (live) | State | Notes |
|---|---|---|---|
| **Committed type** | 🟢 `documents.document_type` (1054 set) | active | the single canonical type per doc; the A41 `document_type` signal |
| **ClassificationProposal** | 🟢 `document_type_proposals` (71: `proposed_type`,`confidence`,`model`,`reason`,`status`) | active | the proposal/audit layer — deterministic map OR an LLM classify pass; carries confidence + which model |
| **ClassificationSource** | 🟡 `document_type_proposals.model` + `documents.classification_json` | partial | deterministic-rule vs LLM-model provenance of the committed type |

**Recommendation (the `document_type` evolution the task asks for).** Keep the two layers distinct and let it
scale: `document_type_proposals` **is** the robust `DocumentClassification` model — an LLM proposal lands there
with `confidence`+`model`+`reason`+`status='proposed'`; a deterministic map can also land a high-confidence
proposal; **adjudication** (`status='committed'`) is what writes `documents.document_type`. This mirrors A19
(inbox ≠ ledger) for *classification*: **an LLM type is a proposal until adjudicated, never auto-committed as
fact.** Adding a new classifier (a new local model, a new deterministic rule) = a new proposal source — zero
structural change. The Paracale work (deploy_782, 71 typed via local-qwen proposals → committed) is exactly
this loop; the model just names it.

---

## 3. DocumentRole — what a document DOES, per context

> **Definition.** A `DocumentRole` is the *purpose a document serves* — and it is **context-dependent**: the same
> Deed is *Title Evidence* in one matter and mere *Correspondence* in another. Role (what it proves) is distinct
> from Classification (what it is).

| Concept | Canonical home (live) | State | Notes |
|---|---|---|---|
| **Intrinsic role** | 🟢 `documents.doc_role` (977) + `exhibit_tier` (1579) | active | the doc's global default purpose + evidentiary weight |
| **Contextual role** | 🟡 `document_matter_links.relation_kind` (per doc-matter link) | partial | the role a doc plays **in a specific matter's theory** — the context dimension |
| **StrategicRelevance** | 🟡 `documents.strategic_relevance` | partial | how strongly the role advances a matter |

**Why the Classification/Role split matters (and is extensible).** Classification answers *"what is this?"*
(one answer, stable); Role answers *"what does it prove, here?"* (many answers, per matter). A `Mining Permit`
(classification) plays the role of *permit-standing evidence* in a Paracale mining matter and *nothing* in an
MWK title matter. Modeling role on `document_matter_links` (not globally) keeps it client-scoped by construction
(rides A5) and lets a new role appear without reclassifying the document. New roles (Title Evidence, Contract,
Correspondence, Permit, Fraud Indicator…) are a controlled vocabulary on `relation_kind` — additive.

---

## 4. DocumentFiling · FilingLocation · DocumentInventory — organized storage across fronts

> **Definition.** `FilingLocation` = a place a copy of a document can live; `DocumentFiling` = the placement of a
> copy in a location (with an integrity checksum); `DocumentInventory` = the cross-layer view of *which* layers
> hold a given document. This is the "leo.hayuma.org primary + Google Drive secondary/offline + physical" model.

| Concept | Canonical home (live) | State | Notes |
|---|---|---|---|
| **FilingLocation — online/primary** | 🟢 the corpus (`documents` row) served via leo.hayuma.org `/files/c` | active | primary ACCESS + canonical KNOWLEDGE (extracted_text) |
| **FilingLocation — Drive/secondary** | 🟢 `documents.drive_file_id`/`drive_folder_id`/`drive_link`/`drive_md5_checksum` (1048) | active | canonical BINARY + offline copy (per drive-canonical-storage policy) |
| **FilingLocation — physical vault** | 🟡 `documents.vault_section`/`vault_number`/`vault_location` | partial | the paper original's shelf location |
| **FilingLocation — digital scan** | 🟡 `documents.digital_scan_id` / `canonical_filename` | partial | the master scan identity |
| **DocumentInventory** | ○ *(derivable from the columns; no unified view yet)* | **NET-NEW (view only)** | per doc: in-corpus? Drive-backed? vault-located? — the routine-inventory readout |

**Governance ties (respect existing invariants).** (a) *Canonical split:* the **corpus** holds canonical
*knowledge* (extracted_text — the citable source, offline-sovereign); **Drive** holds the canonical *binary*
(the PDF/scan). Neither is "the client-facing product" until the exposure gate says so (A11). (b) *Integrity:*
a Drive copy is trustworthy only if `drive_md5_checksum` matches the stored binary — a filing whose checksum
diverges is a flagged inventory gap. (c) *No new exposure:* filing/inventory is internal organization; it does
**not** create a client surface (A11/A32 still govern what a client sees).

---

## 5. DRAFT invariants (propose as A44–A47 — NOT yet added to §4)

- **A44 (signal extensibility)** — The A41 `ConnectivityGate` is exactly the **5 mandatory** `DocumentSignal`s;
  a new signal type is additive metadata and never enters the gate except by an explicit governance promotion
  (version bump + invariant edit). *Protects A41's stability as the corpus grows.*
- **A45 (classification is a proposal until adjudicated)** — An LLM/deterministic `document_type` is written to
  `document_type_proposals` with confidence + source; only an adjudicated proposal (`status='committed'`) sets
  `documents.document_type`. No classifier auto-writes the canonical type as fact. *Classification analogue of A19.*
- **A46 (filing integrity)** — A `DocumentFiling` copy in a non-corpus location (Drive/vault) must be
  reconcilable to the corpus (checksum for binary; the corpus holds the citable knowledge). A divergent or
  missing checksum is an inventory gap, never silent. *Rides offline-sovereignty.*
- **A47 (role is client-scoped)** — A contextual `DocumentRole` (`relation_kind`) is per doc-matter link and
  therefore inherits client separation; a role never crosses a document into another client's theory. *Extends A5.*

---

## 6. Current-issue recommendations (Task 3)

- **Embedding divergence (W3).** ONTOLOGY §2.17 already declares `corpus_backfill_state.embedded` the ONE
  canonical `embedded` signal (not `rag_local`). The 1489 vs 1492 gap = 3 docs with `rag_local` chunks whose
  `corpus_backfill_state.embedded` isn't set. **Ontology stance:** the gate reads the canonical source only;
  the fix is *reconciliation* — the embedder must set `corpus_backfill_state.embedded=true` when it writes
  `rag_local` (MASTER_PLAN §6B W3). No model change needed; this DRAFT just reaffirms the single-source rule
  and adds A46's spirit (a signal has one canonical source; a divergent secondary is a tracked gap, not truth).
- **`document_type` → `DocumentClassification`.** Adopt §2 above: `document_type_proposals` as the confidence +
  source + adjudication layer, `documents.document_type` as the committed canonical. Already how Paracale was
  done — the model formalizes it and A45 governs it.

## 7. Coordination handoff → ingestion agent (before finalization)

**Requested confirmation (so these graduate into §2.17 accurately):**
1. Is `document_type_proposals.status` the actual proposed→committed adjudication field, and does the classify
   pass always route through it (never writing `documents.document_type` directly)? (Confirms A45.)
2. For `DocumentRole`: is `document_matter_links.relation_kind` the right per-matter role slot, or is role
   carried elsewhere in the remediation flow?
3. For `DocumentInventory`: do you want a derived **view** (`v_document_inventory`) as the routine-inventory
   readout, and which layers must it cover (corpus/Drive/vault/scan)? (View-only, no new table — your call to build.)
4. Any signal beyond the 5 you already treat as connection-relevant (so we register it as optional, per A44)?

**What does NOT change for you:** the A41 5-signal gate, `_connect_verify`, and the earned-provenance rule are
untouched — this model *names* what you built, it doesn't alter the flow. **Nothing here is code; nothing is
finalized until you confirm.** On your sign-off I graduate §1–§4 into ONTOLOGY §2.17 and A44–A47 into §4, and
update `ONTOLOGY_ALIGNMENT.md`.

---
*DRAFT prepared 2026-07-08 by the ontology desk. Grounded against the live schema. Companion: `ONTOLOGY.md` §2.17,
`docs/INGESTION_DIRECTIVE.md`, `MASTER_PLAN.md` §6B.*
