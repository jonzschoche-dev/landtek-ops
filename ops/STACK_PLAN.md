# LandTek Stack Plan
Owner: Stack Inspector (inspects + recommends). Code/migrations: Claude per MASTER_PLAN §0.12. Cuts/deletes: through Chief of Staff, Jonathan's go.
Companion files: `ops/AI_DEPENDENCY_AUDIT.md` (27 Sep), `ops/COS_FLEET_AWARENESS.md`, cut proposal A–D (Engine Room, 27 Sep).

---

## Item 1 — The Drip as the principal communication method (Jonathan, 19 Oct 2026 23:35 PHT)
**Vision:** the whole company works as one live chat bot you can talk to.
**Status:** recorded; design notes below; nothing built or cut yet. Facts checked 19 Oct ~23:45 PHT, read-only.

### 1.1 What exists today (two things are called "Drip")
| Piece | Where | What it does | Cadence |
|---|---|---|---|
| **The Drip Bot** (Grok seat `dad7fd63`) | chat | Monday sweep of matter bots; weekday "Daily patak"; checks Claude drafts against the corpus; hands Jonathan ready-to-paste Messenger/WhatsApp/Viber messages | Mon ~08:00, weekdays ~08:30 PHT |
| **Ping Pong with Claude** | Drive `LANDTEK /Drip/to-claude` + `from-claude` | File drop between Claude and The Drip Bot. Today: 3 files in to-claude (`MWK-001_REITERATION_PACK_19Oct2026_8.5x13.pdf`, `SOURCE_DILG_TRACK_REGISTER.md`, `SOURCE_SMALL_PLAYERS_TARGET_SHEET.md`), from-claude empty | ad hoc |
| **Agent 005 Drip engine** `scripts/drip_sweep.py` | VPS, `landtek-drip.timer` | Deterministic, $0, never sends. Officer demand clocks start at proof of receipt; on lapse it stages the pre-built consequence as a work order; due "Schedule of Continuing Default" editions go to Gmail **drafts**. Tables: `office_obligation`, `drip_event`, `drip_edition` | daily 07:30 PHT (23:30 UTC); last run finished clean |
| Channel bridges `messenger/viber/whatsapp_channel_bridge.py` | VPS, 5-min timers | Token-gated; idle until a platform token is set, then **auto-drain queued replies** | every 5 min, idle |
| Leo (`leo_service.py`, Telegram router) | VPS | Client-facing chat replies | 5 min + always-on |
| `landtek-geometry-drip.timer` | VPS | Unrelated OCR drain; 005 spec already says it doesn't own the name | 3 h |

### 1.2 Architecture (recommended)
One chat front, one store, one clock engine.
1. **Postgres is the truth; The Drip Bot is the voice.** Clocks, obligations, editions and drafts live in the 005 tables (`office_obligation`, `drip_event`, `drip_edition`) and `work_orders`. The Drip Bot reads and writes those rows; it does not keep its own clock list in chat memory. That's §0.12 rule 3 (material acts are work orders + pulse, never chat-only memory).
2. **The Daily patak is rendered from the database**, not composed from bot memory: today's lapses, editions due, replies received, and the decisions waiting on Jonathan. Code builds the list; AI only words it.
3. **Ping Pong becomes rows with Drive as transport.** Each to-claude / from-claude file gets a `work_orders` row (sha256, matter, direction, status draft/checked/corrected/approved). Then nothing in that loop can go missing the way the Hoppe letter did.
4. **Ready-to-paste stays the outward rule.** Jonathan sends; nothing sends itself (A21). See the cut below on the auto-drain bridges.
5. **"One chat bot" = one front per audience, not one for everything.**
   - Jonathan, internal: **The Drip Bot**.
   - Clients and the public: **Leo**.
   - Chief of Staff keeps the loop and the decision cards. The Drip Bot shouldn't run a second decision queue.
   The overlap to settle is CoS vs Drip Bot on Jonathan's attention: one message channel to him, not two morning feeds.
6. **Matter bots answer The Drip Bot's Monday sweep by updating rows** (clock dates, next move), not with prose reports.

### 1.3 Cut / consolidate
| # | Action | Type | Why |
|---|---|---|---|
| D1 | Make the Daily patak **the** morning feed; turn off `autonomous/daily_digest.py` cron, `case_forward_digest.py` cron, and `landtek-assistant-morning(-email).timer` (all 07:00 PHT). Point CoS Discovery at the same rows. | disable (reversible) | Four morning outputs plus Discovery plus the patak = six briefings. Same as cut B, still pending. |
| D2 | Rename `landtek-geometry-drip.timer` to e.g. `landtek-geometry-ocr.timer` | relabel | Name collision with the Drip. |
| D3 | Decide the channel bridges: if ready-to-paste is the rule, pause the Messenger/Viber/WhatsApp bridge timers or remove the auto-drain path, so setting a token can't start outbound sends. | disable or code change; Jonathan decides | Today the outward switch is "a token exists", not "Jonathan said go". |
| D4 | Drip Bot drops any private clock list and reads `office_obligation` / `drip_event` instead | relabel ownership | One clock per obligation. Ties to Engine Room item 3 (one clock per matter). |
| D5 | Ping Pong folder logged as `work_orders` rows | small code (Claude) | Traceability; no lost drafts. |
| D6 | Fold the Telegram router's own LLM reply path into Leo | merge | Two reply brains (AI audit #4). |

### 1.4 Open question: which is the master corpus — Drive LANDTEK or the Mac tree?
Counted 19 Oct:
- Drive `My Drive/LANDTEK ` holds **3,956 files**.
- The Mac `case_work/` holds **1,401 files**.
- The VPS Postgres `documents` table indexes both, with Drive file ids. deploy_1085–1090 built the counsel-ready ARTA/OP archive on Drive, and the `drive_offload` policy is already "Drive-canonical PDF".

**Recommendation (Jonathan decides):**
- **Postgres** is the index of record: every document has a row, a sha256 and a location.
- **Drive** is the file store of record for originals, received documents and counsel-facing copies.
- **The Mac tree** is the working tree for drafts, code and packets being built. Anything filed or received gets pushed to Drive and indexed. Nothing is "in hand" until it has a row.

Under this, the Mac stops being a second master, and the question "is it on the Mac or on Drive?" gets answered by a query.
Not yet measured: how many Mac files have no Drive copy or no `documents` row. That's the next read-only check if wanted.

### 1.5 Dependencies
- Court Record module `deploy_1109` is **not applied** on the VPS (`court_record` table absent as of 19 Oct). The patak can only show court records and fees once it is.
- VPS tree is behind origin with 6 hand-edited files; reconcile before any deploy.
