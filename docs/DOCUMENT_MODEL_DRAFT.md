# Document & Signal Model — DRAFT (extends ONTOLOGY §2.17)

> **STATUS: DRAFT — pending ingestion-agent coordination. NOT yet finalized into `ONTOLOGY.md` §2.17 or §4.**
> This proposal models a **layered** document→signal→semantic→projection architecture (§0) as first-class ontology
> concepts. It is **modeling of existing reality**, not new schema — every concept below is grounded in
> columns/tables that already exist (verified live 2026-07-08). No code or DB change is proposed. The semantic
> layer (Entity/EntityLink/Fact/Relationship, §5) is **already modeled** in §2.2/§2.5/§2.11 — this draft
> *integrates* it, not re-models it. Once the ingestion agent confirms the models are practical, the new concepts
> graduate into §2.17 and the DRAFT invariants (**A44–A49**) into §4. Builds on §2.17 (`ConnectedDocument`, the
> 5-signal `ConnectivityGate`, `ProvenanceStamp`) and stays strictly aligned with **A41** (all 5 signals) ·
> **A42** (provenance earned) · **A43** (gate fail-closed) · **V8** (write-time provenance shadow guard).

---

## 0. Target architecture — the layered frame

The concepts below fit a **layered, decoupled** model: each layer rises from the one under it, carries its own
governance, and changes in one ripple minimally into others. Storage (leo primary · Drive secondary · physical)
is *orthogonal* — a filing concern (§4), not a layer of meaning.

```
 AGENT INTERACTION      safe boundaries · permissions · contextual queries · contributions        (§2.14 coord / A38, future)
        ▲
 GOVERNED PROJECTION    purpose-built safe views per agent/client/task                            (§2.15 ClientProjection / A32–A34)
        ▲
 SEMANTIC / KNOWLEDGE   Entity · EntityLink · Fact · Relationship · DocumentRole                  (§2.2 · §2.5 · §2.11 · §3/§5 below / A1·A2·A19·A20)
        ▲               verified knowledge units, each CITED back to a source signal
 SIGNAL                 DocumentSignal · DocumentClassification · ProvenanceRecord                (§1–§2 below / A41·A42·A43·V8)
        ▲               text · quality · type · embedding · model(earned) · confidence · source
 RAW / SOURCE           original files · scans · messages · images                                (§4 FilingLocation)
```
**Reading it:** the RAW binary lives in a `FilingLocation` (Drive/vault); the **Signal layer** turns it into a
`ConnectedDocument` (5 A41 signals); the **Semantic layer** extracts `Fact`s/`Relationship`s from that connected
text, each **cited back** to the source (so knowledge is never ungrounded — A2/A20); the **Projection layer**
renders only client-safe values (A32); the **Agent layer** queries through governed boundaries. Governance is not
bolted on top — A41–A43 govern the signal layer, A1/A2/A19/A20 the semantic layer, A32–A34 the projection.

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
| **FilingRule** | ○ *(policy — not a table)* | **NET-NEW** | where a doc SHOULD live, by kind: every *received* exhibit → Drive binary + corpus + (court-critical) vault; drafts → corpus only. Turns "organized" into a checkable target |
| **SyncRule** | ○ *(policy)* | **NET-NEW** | how fronts stay aligned: corpus-text ↔ Drive-binary (via `drive_md5_checksum`), Drive ↔ physical (offload policy). A divergence from a `FilingRule`/`SyncRule` is a `DocumentInventory` gap — surfaced, never silent (A46) |

**Governance ties (respect existing invariants).** (a) *Canonical split:* the **corpus** holds canonical
*knowledge* (extracted_text — the citable source, offline-sovereign); **Drive** holds the canonical *binary*
(the PDF/scan). Neither is "the client-facing product" until the exposure gate says so (A11). (b) *Integrity:*
a Drive copy is trustworthy only if `drive_md5_checksum` matches the stored binary — a filing whose checksum
diverges is a flagged inventory gap. (c) *No new exposure:* filing/inventory is internal organization; it does
**not** create a client surface (A11/A32 still govern what a client sees).

---

## 5. Semantic / Knowledge Layer — Entity · EntityLink · Fact · Relationship

> **These are ALREADY first-class concepts in ONTOLOGY (§2.2 Actors, §2.5/§2.11 Facts).** This section does NOT
> re-model them — it places them in the layered architecture and clarifies how they **rise from the signal layer
> and stay cited**, so the corpus is agent-ready. Governance is the existing provenance discipline (A1/A2/A19/A20),
> not new rules.

| Concept | Canonical home (live) | State | Role in the layered model |
|---|---|---|---|
| **Entity** | 🟢 `entities` (4820; `canonical_id` merge graph, `provenance_level`, A15 DAG) | active | the real-world actor/org/ref — one canonical node per real thing |
| **EntityLink** | 🟢 `doc_entities` (8928; `doc_id`+`role`+`provenance_level`) | active | a document *mentions* an entity in a performative `role` — the edge from **signal layer → semantic layer** |
| **Fact** | 🟢 `matter_facts` (13,543; `source_id`+`excerpt`+`provenance_level`+`confidence`) | active | a citable claim EXTRACTED from a `ConnectedDocument`'s text, tiered + quoted (A2/A20) |
| **Relationship** | 🟢 `title_chain` (107) · `knowledge_graph_triples` (74) · `cross_matter_links` (3) · 🌱 `entity_relationships` (0) | active/partial | typed edges between entities/titles/facts — the signature title subgraph is 🟢; the generic KG-triple + entity_relationships layers are underused |

**How the semantic layer stays governed and agent-ready:**
1. **Rise-from-signals + cited-down.** A `Fact` exists only because a `ConnectedDocument` had a usable `text`
   signal; it carries `source_id` (the document) + a verbatim `excerpt`, so it is never ungrounded (A2/A20, the
   `enforce_provenance_facts` trigger). **The signal layer's A41 is what makes the semantic layer trustworthy** —
   a fact from a half-connected doc would be un-citable. This is the through-line the architecture makes explicit.
2. **Provenance tier is the retrieval contract.** Every semantic unit has a `provenance_level`; agentic retrieval
   reads `verified`/`operator` as fact and inference tiers as candidate (A19: `proposed_facts` is an inbox, never
   quoted). Contextual retrieval = "give me the *verified* facts + their source docs for matter X."
3. **Client-scoped by construction.** Entities merged across clients need the cross-client allowlist (A16);
   facts can't cite a cross-client doc (A5/V4). So agentic reasoning inherits isolation for free.
4. **DocumentRole (§3) is the semantic layer's view of a document** — not what a doc *is* (classification) but
   what it *proves* in a matter's theory; it's the bridge from a `ConnectedDocument` to a `Fact`/keystone.

**Agentic reasoning & retrieval (the top two layers, ○ future).** The **Governed Projection** layer (§2.15
ClientProjection, A32–A34) already exists for the *client* surface; an **agent-facing** projection is its analogue
— purpose-built safe views (e.g. `v_agent_matter_context`: verified facts + roles + source docs for a matter,
provenance-labelled, client-scoped). The **Agent Interaction** layer (permissions/boundaries/contributions) is
planned — an agent *contributing* a fact must route it through the same write-gate (proposed → adjudicated →
verified), never write `verified` directly. These stay ○ until built; naming them reserves the governed locus.

---

## 6. DRAFT invariants (propose as A44–A49 — NOT yet added to §4)

- **A44 (signal extensibility)** — The A41 `ConnectivityGate` is exactly the **5 mandatory** `DocumentSignal`s;
  a new signal type is additive metadata and never enters the gate except by an explicit governance promotion
  (version bump + invariant edit). *Protects A41's stability as the corpus grows.*
- **A45 (classification is a proposal until adjudicated)** — An LLM/deterministic `document_type` is written to
  `document_type_proposals` with confidence + source; only an adjudicated proposal (`status='committed'`) sets
  `documents.document_type`. No classifier auto-writes the canonical type as fact. *Classification analogue of A19.*
- **A46 (filing integrity + outward gating)** — A `DocumentFiling` copy in a non-corpus location must be
  reconcilable to the corpus (checksum for binary; the corpus holds the citable knowledge); a divergent/missing
  checksum is an inventory gap, never silent. **And: a filing write/rename to leo.hayuma.org is an OUTWARD action
  (client-facing front) — it is held behind the exposure gate (A11/A21); Drive/vault filing is internal.**
  *Rides offline-sovereignty + no-external-exposure.*
- **A47 (role is client-scoped)** — A contextual `DocumentRole` (`relation_kind`) is per doc-matter link and
  therefore inherits client separation; a role never crosses a document into another client's theory. *Extends A5.*
- **A48 (semantic rises from connected + cited)** — A `Fact`/`Relationship` may be extracted only from a
  `ConnectedDocument` (A41) and must carry a `source_id`/`source_doc_id` (+ verbatim `excerpt` for `verified`);
  knowledge from a half-connected doc is un-citable. *Reaffirms A2/A20 at the signal→semantic boundary — the
  architecture's load-bearing link.*
- **A49 (agentic contribution is gated)** — An agent (or any projection) may CONTRIBUTE to the semantic layer only
  through the propose→adjudicate→verified write-gate; none writes a `verified` `Fact`/`Relationship` directly, and
  none reads a sub-`verified` tier out as settled fact. *Extends A19 to the future Agent Interaction layer.*

---

## 7. Current-issue recommendations (Task 3)

- **Embedding divergence (W3).** ONTOLOGY §2.17 already declares `corpus_backfill_state.embedded` the ONE
  canonical `embedded` signal (not `rag_local`). The 1489 vs 1492 gap = 3 docs with `rag_local` chunks whose
  `corpus_backfill_state.embedded` isn't set. **Ontology stance:** the gate reads the canonical source only;
  the fix is *reconciliation* — the embedder must set `corpus_backfill_state.embedded=true` when it writes
  `rag_local` (MASTER_PLAN §6B W3). No model change needed; this DRAFT just reaffirms the single-source rule
  and adds A46's spirit (a signal has one canonical source; a divergent secondary is a tracked gap, not truth).
- **`document_type` → `DocumentClassification`.** Adopt §2 above: `document_type_proposals` as the confidence +
  source + adjudication layer, `documents.document_type` as the committed canonical. Already how Paracale was
  done — the model formalizes it and A45 governs it.

## 8. Coordination handoff → ingestion agent (before finalization)

**Requested confirmation (so these graduate into §2.17 accurately):**
1. **Classification (A45):** is `document_type_proposals.status` the proposed→committed adjudication field, and
   does the classify pass always route through it (never writing `documents.document_type` directly)?
2. **Role (A47):** is `document_matter_links.relation_kind` the right per-matter role slot, or is role carried
   elsewhere in the remediation flow?
3. **Inventory (A46):** want a derived **view** (`v_document_inventory`) as the routine-inventory readout, covering
   which layers (corpus/Drive/vault/scan)? View-only, no new table — your call to build.
4. **Signals (A44):** any signal beyond the 5 you already treat as connection-relevant (register as optional)?
5. **Semantic rise (A48):** does the fact/entity extraction step already require a `ConnectedDocument` (all 5
   signals) before harvesting, or can it run on partially-connected docs? (Confirms the signal→semantic gate.)
6. **Relationship home:** `entity_relationships` is empty (0) — is it the intended generic relationship store, or
   is `knowledge_graph_triples` the canonical one? (Avoids modeling a dead table as canonical.)

**What does NOT change for you:** the A41 5-signal gate, `_connect_verify`, and the earned-provenance rule are
untouched — this model *names* what you built, it doesn't alter the flow. **Nothing here is code; nothing is
finalized until you confirm.** On your sign-off I graduate §1–§4 into ONTOLOGY §2.17 and A44–A47 into §4, and
update `ONTOLOGY_ALIGNMENT.md`.

---

## 9. Reconciliation with the ingestion agent's proposal (deploy_785)

The ingestion layer **independently drafted a convergent architecture** (`INGESTION_DIRECTIVE.md` §ARCHITECTURE
DIRECTION) — strong validation that the model is right, not invented. The two agree on ProvenanceRecord
(`extraction_runs`), an extensible signals store, W3 embed unification, and held external-facing filing. **Two
refinements from their proposal are ADOPTED into this draft:**

1. **Classification + Role unify into one `document_classifications` table** (their design): `doc_id · dimension
   (type|role) · value · method (deterministic|llm|human) · model · confidence · status`, with
   `documents.document_type`/`doc_role` becoming **caches of the accepted row**. This is cleaner than my split
   §2/§3 — one governed adjudication store for *both* what-a-doc-is and its *intrinsic* role, A45 governing all of
   it. (The **contextual, per-matter** role stays on `document_matter_links.relation_kind`, A47 — that's a
   different axis: intrinsic identity vs role-in-a-matter's-theory.)
2. **leo.hayuma.org filing writes are OUTWARD actions** (their governance point, sharper than mine): leo is the
   client-facing front, so a `DocumentFiling` write/rename to it is an outward, hard-to-reverse action — it rides
   **A11/A21** and is **held behind the exposure gate**. Drive/vault filing is internal; leo filing is not. A46
   below is updated to carry this.

**Their concrete extensible stores** (`document_signals` shadow table · `document_classifications`) are the
*implementation* of my §1 A44 (signal extensibility) and §2 A45 (classification-as-proposal) — additive,
shadow-first, no `documents ALTER`, gate untouched, rollback = DROP. **This draft's additions on top of theirs:**
the layered frame (§0), the **semantic layer** (§5, Entity/Fact/Relationship + A48 signal→semantic-rise), and the
**agentic layer** (A49). Together = one converged model: their signal/classification/filing *stores* + this desk's
layered frame + semantic/agent *invariants*.

**Remaining coordination (§8):** their proposal answers Q1 (classification adjudication = `document_classifications.status`),
Q3 (DocumentInventory = a view + sync sentinel), Q4 (`document_signals` for new signals). Still open: **Q5** (does
extraction require a ConnectedDocument first — A48) and **Q6** (`entity_relationships` empty vs `knowledge_graph_triples`
canonical). These two graduate the model into §2.17/§4 once confirmed.

---
*DRAFT prepared 2026-07-08 by the ontology desk. Grounded against the live schema. Reconciled with the ingestion
agent's convergent proposal (deploy_785). Companion: `ONTOLOGY.md` §2.17, `docs/INGESTION_DIRECTIVE.md`, `MASTER_PLAN.md` §6B.*
