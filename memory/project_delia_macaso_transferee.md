---
name: delia-macaso-transferee
description: "doc#590 transferee is Delia Macaso (not Vacaseo); 2002 pre-revocation deed from Cesar dela Fuente"
metadata: 
  node_type: memory
  type: project
  originSessionId: bd418b71-6636-441c-8ebd-97897cec3394
---

doc#590 is a 2002-04-06 Deed of Absolute Sale by Cesar dela Fuente (as Atty.-in-Fact under his pre-2005-revocation SPA) to **Delia Macaso** of land in Mercedes, Camarines Norte. Status: executed_notarized. Earlier OCR misread the surname as "Vacaseo" — propagated through bible event log lines and analyst_memos before Jonathan corrected 2026-05-19.

**Why:** Macaso is a 2002 transferee NOT on the original 20-named-defendants list for CV-26360 (Balane chain). Pre-revocation conveyance, so the void-SPA theory does NOT automatically void this deed. But it's a separate party-in-interest that may matter for full title-chain quiet.

**How to apply:** 
- Treat all corpus references to "Vacaseo" as OCR misreads of "Macaso" (post-processor regex now catches this auto-correction on future regens).
- Delia Macaso is a 2002 transferee, NOT on the CV-26360 defendant set, NOT triggered by the fraud_signal_detector (correctly — pre-revocation).
- If a question arises about the 2002 disposition or chain-of-title quiet for the Macaso parcel, flag for human review rather than auto-asserting validity.
