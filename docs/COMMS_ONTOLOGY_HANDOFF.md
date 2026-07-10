# GovernanceHandoff → Ontology Desk — Communications Layer marker updates (post-deploy_823/824/827/828)

**From:** Fable (comms execution desk) · 2026-07-10
**To:** Ontology desk (ONTOLOGY.md is in-flight in your working tree — apply these with your next version bump; comms desk no longer edits the ontology layer per standing rule)
**Nothing here is enforcement** — all markers reflect state that is ALREADY live and verified on the DB.

## 1. A25 marker — Part 2 UNBLOCKED (the deploy_733-style blocker is resolved)

- `channel_users.entity_id` (FK→`entities`) is **live** (deploy_824 applied 2026-07-10) — the person-key
  the V7 spec §4 was blocked on.
- `v_ontology_channel_person_cross` (the A25(b) cross-channel detector) is **live and returns 0**.
- Five identities bound (grounded, not guessed): ARTA→entity 2362 · Loida E. Macale→39 ·
  Barandon Law Offices→2390 · Pamela Bianca Cruz→10327 (new, `inferred_strong`, envelope-grounded
  gmail 102550) · Jonathan email identity→operator. All four externals scoped `MWK-001`;
  roles honest (`counterparty` for agency/LGU, `counsel` for our-side lawyers); `authorized=false` kept.
- Suggested A25 marker text: 🟡 asserted/shadow → *"Part 1 validity live (V7 shadow); **Part 2 detector
  live** (`entity_id` deploy_824, person-cross view, 0 violations); trigger-enforcement still pending
  the V7 roadmap (log→…→block post-Aug-12)."*

## 2. UnifiedClientPersona re-point (conversation_context was DROPPED in deploy_804)

§2.14's UnifiedClientPersona row still names `conversation_context`/`conversation_chunks` as the
(dormant) cross-channel memory home — those tables no longer exist. Canonical homes now:
- **`v_comms_interactions`** (deploy_823) — every interaction, all channels, one view
  (channel_messages ∪ leo_interactions ∪ outbound_messages; 4,945 rows live).
- **`v_comms_relationship`** (deploy_823) — per-party rollup (first/last seen, channels used, volumes).
- `chat_notes` · `client_history` · `channel_users.entity_id` remain as-is.
Views-first per the greenlit decision; a thin projection table is a future call, not needed for the marker.

## 3. Register in coverage

New named objects for `ontology_check.py --coverage` awareness (views, not concept stores):
`v_comms_interactions` · `v_comms_relationship` · `v_ontology_channel_person_cross`. New guard (concept:
Truth&Reconciliation, §2.13-adjacent): `trg_reocr_reground_guard` on `documents` (deploy_830) — re-OCR
that un-grounds a verified fact now auto-demotes it to `inferred_strong` + logs `REOCR_UNGROUNDED_FACT_DEMOTED`.

## 4. For the record (comms desk actions already taken, truth-layer relevant)

- Onboarding templates de-falsified (deploy_828 cluster): "Landtek Law / property-law practice" →
  "LandTek, land & property services company"; "Atty. Jonathan Zschoche" → "Jonathan Zschoche";
  explicit "LandTek is not a law firm; litigation handled by engaged counsel (Atty. Barandon)".
  17 queued outbound rows carrying the old false claims quarantined (`superseded_bad_template`) —
  **nothing had sent** (external switch held throughout; A26 verified working).
- Messenger is now **LIVE** (deploy_832 wiring + operator-provisioned page token + nginx webhook;
  first real two-way 2026-07-10) — §2.14 CommunicationChannel row: Messenger ○ not-built → 🟢 live.
- Operator-name scrub (deploy_837): the operator's real name removed from ALL user-facing replies
  across every channel (inbound contacts incl. counterparties must not learn who runs the system) —
  this is the first concrete instance of a **CommunicationPolicy** rule (see §5) and wants to become
  a machine-checkable guard, not a one-off code edit.

---

## 5. PROMPT → Ontology Agent — model the *living, breathing* chat→corpus feedback loop

**Objective.** Today ongoing conversations are *logged more than ingested*: messages land in
`channel_messages`/`channel_users` and the spine views (§2) can show history, but chats do not yet become
governed, citable knowledge that updates truth, client models, and how agents speak. Model the concepts +
invariants that close the loop — chat → signal → (grounded) fact → durable client memory → future agent
behaviour — so the corpus *breathes*. **Doc-only, same discipline as the V-series prep.**

**Ground rules (non-negotiable — this is why prior drafts had to be reconciled):**
- **Continue the A-series from the current max** (A75 as of 2026-07-11 — *verify live*, `grep '^| A' ONTOLOGY.md`).
  **Never reuse or renumber.** (The A20–A23 comms collision cost a whole reconciliation pass; don't repeat it.)
- **Reuse, don't reinvent.** Build on what exists: §2.14 Communications (A25–A31), §2.15 Client Projection
  (A32–A34), DocumentSignal/Classification/Role (A44–A49), the spine views (`v_comms_interactions`/
  `v_comms_relationship`, deploy_823), `channel_users.entity_id` (deploy_824). The dead
  `conversation_context` re-point (§2) is the **first concrete unblock** — do it as part of this.
- **Honest states.** Nearly all of this is **○ planned** / 🟡 partial today — mark it so; do not overstate.
- **Shadow-first, mechanical.** Any new invariant graduates documented→asserted→shadow→block, like V4/V6/V7.
- **Chats are DATA, never instructions or truth** (carry the A66 / S1–S4 doctrine into this domain).

**Concepts to model (map each to a candidate home + honest state; propose 2–3 invariants per cluster):**

| Concept | Essence | Candidate home | Notes for the model |
|---|---|---|---|
| **Message / MessageSignal** | every chat/email as a first-class signal source | `channel_messages` + a `message_signals` extraction (analogue of DocumentSignal A44–A49) | ○ — the generalization DocumentSignal already gives you a template |
| **Conversation / MessageThread** | multi-turn intent, decisions, commitments over time | extend **CrossChannelThread** (§2.14); `v_comms_interactions` is the raw feed | ○ — richer than the current thread stub |
| **ClientInteractionMemory / CommunicationState** | durable governed per-client memory: preferred tone/language(Taglish/EN/FIL)/timing, open loops, commitments, sensitivity | **the re-point for the dropped `conversation_context`** → backs **UnifiedClientPersona (A28)** | 🟡 **HIGHEST leverage** — it is also the input the comms-desk StylePersonalizer is blocked on |
| **CommunicationPolicy / ClientCommunicationGuidelines** | versioned, machine-checkable rules for how an agent may speak (tone · disclosure limits · escalation triggers · no internal jargon · **no operator name** — deploy_837 is the seed rule) | new; enforced at the PlatformCoordinator / outward chokepoint (A21/A26) | ○ — render-audit pattern like A32; shadow→block for high-risk channels |
| **GoalAlignment / PriorityResolution + DiscernmentRule** | explicit model for company goal vs client need vs legal/ethical constraint, with a conflict-resolution **owner** + audit | new | ○ — "when client urgency conflicts with legal risk → prefer X", reviewable |
| **ConversationDerivedFact** | a Fact specialization carrying chat provenance + **recency weighting** | specialize the fact ledger; rides A2/A20 grounding + A65 arrow-of-time | ○ — **critical invariant:** never `verified` without the same excerpt-grounding gate; newer supersedes older |
| **AttachmentLink** | Message → Document, so chat attachments enter the DocumentSignal/remediation pipeline (A41–A48) | new edge | ○ — property evidence often arrives as a chat attachment; must not orphan |
| **RelationshipTrajectory** | how trust/urgency/risk/satisfaction evolve | feeds off `v_comms_relationship` | ○ medium — derived, not a new truth store |

**Suggested invariant themes for A76+ (author honestly, 🟡/○):**
1. **Persona/memory continuity** — a client's `ClientInteractionMemory` is keyed to `client_code`/`entity_id`
   and never re-initialised per channel (gives A28 a live backing instead of the dead table).
2. **Policy-enforced communication** — every outbound to a client passes a machine-checkable
   `CommunicationPolicy` (tone/disclosure/no-operator-identity), shadow→block; the deploy_837 scrub is the
   first rule instance.
3. **Chat-derived fact provenance** — a `ConversationDerivedFact` is DATA: never `verified` without a
   grounded excerpt (A2/A20), and a later fact supersedes an earlier one (A65). Chats never auto-mutate truth.
4. **Goal-conflict has an owner** — any company-vs-client priority conflict resolves through a named,
   audited `DiscernmentRule`, never silently by the agent.
5. **Chat attachments are governed evidence** — an `AttachmentLink` routes a chat attachment into the
   document signal/remediation pipeline; no attachment stays an untracked blob.

**Closes the loop with the comms desk:** ClientInteractionMemory + CommunicationPolicy are exactly the two
inputs the StylePersonalizer (per-recipient style engine) needs — modeling them here unblocks that build.
