---
name: feedback-stage-transition-intake
description: "When a case stage transition happens (pretrial done, trial done, etc.) Leo must auto-fire a structured intake request to the client for the predictable post-stage artifacts"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

**Rule:** When a deadline auto-completes (event has occurred), Leo must immediately fire a structured intake request listing the post-stage artifacts the client should upload. Don't wait to be asked. Don't ask vague questions. Issue a *checklist*.

**Why:** Jonathan, 2026-05-16: *"claude should know what happens at a pretrial and be flagging the client to upload the data and give a report, provide receipts etc"*. The procedural calendar of a PH civil case is deterministic — Leo should anticipate every artifact that flows from a stage transition and request it the moment the stage flips. Failure to do this means evidence drifts unrecorded, deadlines slip, and the case rots.

**How to apply:**

Per PH Rules of Court, each stage transition produces predictable artifacts. When a stage flips (deadline auto-completes per [[feedback_legal_status_awareness]]), fire a Telegram intake matching the stage:

| Stage transition | Required intake from client |
|---|---|
| **Pre-Trial → Post-Pre-Trial** | (a) **Pre-Trial Order** (the court's roadmap with stipulations + trial dates) ← MOST CRITICAL; (b) Receipts for fees paid; (c) Brief report of outcome + adverse rulings + settlement offers; (d) Trial date(s) extracted from order; (e) Any new exhibits identified |
| **Trial concluded → Decision pending** | (a) Decision (when issued); (b) Full trial transcript; (c) Witness fees + transportation receipts; (d) Any motions for reconsideration drafted |
| **Decision → Appeal window** | (a) Decision in hand; (b) Notice of Appeal filed (or strategic decision not to); (c) Date judgment received (15-day appeal clock starts) |
| **Notice of Appeal → Appellate brief** | (a) Notice of Appeal copy; (b) Appellate brief draft/final; (c) Filing receipts; (d) Brief filing deadlines per court |
| **Motion filed → Court action** | (a) Comment/opposition filed (or note that none); (b) Court order on motion |
| **Hearing scheduled** | (a) Subpoena copies; (b) Witness list confirmed; (c) Exhibits prepared |

**Intake template (Telegram):**
```
📋 STAGE TRANSITION DETECTED — {case_file}: {stage_before} → {stage_after}

Detected by: {evidence_doc} dated {date}

Please upload the following so the case file stays complete:
  1. {required_item_1}
  2. {required_item_2}
  ...

Reply with /skip <n> if item N doesn't apply or doesn't exist yet.
Reply with the doc directly to ingest.
```

**Implementation:**
- Hook into the auto-complete path in `deadline_sentinel.py` — when a deadline goes from pending to completed, look up the intake template for that stage and fire it.
- Add a `stage_intake_requirements` table or a static dict in code keyed by deadline_type/stage.
- Track received vs missing items in `stage_intake_status` so the system knows what's still pending.
- Re-prompt at T+3 days if items are still missing.

**Anti-pattern:** Don't issue a vague "please upload anything related to the pretrial." Give the *itemized checklist* derived from PH Rules. The client knows exactly what they have.
