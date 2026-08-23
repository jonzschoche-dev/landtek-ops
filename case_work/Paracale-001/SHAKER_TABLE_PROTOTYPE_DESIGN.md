# LAB X Shaker Table — Prototype Engineering Brief (SMBC Mercury-Free Processing System, Casalugan)

**Project:** LAB X — a LandTek project (LandTek is a principal, not just service provider) under **Golden Inocalla Management Services** (Allan Inocalla, Principal). **Site (rev. 2026-08-23):** the **SMBC Mercury-Free Processing System (MFPS), Barangay Casalugan, Paracale** — the ₱29M planetGOLD facility owned and managed by the Samahan ng mga Minero sa Barangay Casalugan, where **Stephen Lloyd is Investor and Operational Partner under SMBC Board Resolution No. 2026-009** (SMBC owns the plant; Stephen holds no equity; net profits 50/50). Site facts per `case_work/NIBDC-001/DEAL_MEMO_PLANET_GOLD_PROCESSING_NIBDC.md` (a draft for negotiation — executed agreement copy still to be obtained). Filed under Paracale-001; keep strictly separated from MWK per the client-separation invariant. Registered in `MASTER_PLAN.md` §7 / §8. Presentation: `LAB_X_SHAKER_TABLE_DESIGN.pdf` (generator `lab_x_deck.py`).
**Design authority:** Stephen Lloyd, head mechanical engineer and designer. **Manpower:** Allan Inocalla supplies the site crew (installation, pad works, riffle fitting) and the table operators. This brief consolidates the starting point; every decision marked **D-n** is his to make or overrule.
**Status:** DRAFT v0.2 — 2026-08-23 (site moved from the Inocalla farm to the SMBC MFPS; Stephen Lloyd as design lead and plant operator). Consolidated from the 2026-08-22 design chat (which drew on ~100 web sources, none vendor-quoted). Nothing here is a measured quote or a test result; cost figures are marked **ESTIMATE / UNQUOTED** throughout.
**Goal:** 10 tonnes/day of gravity feed at the SMBC MFPS plant, mercury-free, built with local fabricators wherever possible. Build **one** full-size prototype first, tune it, then decide on table 2.

**Programme positioning (2026-08-23):** LAB X is part of the UN-backed **planetGOLD** sustainable Minahang Bayan agenda (the MFPS was established under planetGOLD Philippines — UNEP-led, GEF-funded); the partnership's alignment note names the MFPS as the model to replicate regionally. Stephen's and the project's accolades are to spearhead further funding and involvement — **documents-only accolade file (C-21) and funding-line map (C-22) still to compile; nothing asserted without a document.**

**One-sentence position:** A Wilfley/6-S-style table is buildable in Camarines Norte from local mild steel, a locally machined eccentric shaft, and a rubber-lined deck; the three things that decide whether it actually recovers gold are (1) a rigid foundation — **not** spring isolation, (2) an accurately machined asymmetric head motion, and (3) riffle/slope geometry copied from a proven deck and then tuned in the field — and the one thing that decides whether two tables are the right machine at all is an ore test that nobody has run yet.

---

## 1. Engineering review of the design chat — what stands, what doesn't

The earlier chat is a good first pass. Three parts need correcting before anything is fabricated.

### 1a. Drop the spring-isolation design track (the biggest correction)

Roughly a third of the chat computed spring stiffness, natural frequency, transmissibility and damping ratios for isolation mounts, and ended by recommending a mount natural frequency of 2.0–2.5 Hz under a 5 Hz table. **That is HVAC / generator isolation logic and it is the wrong direction for a concentrating table.**

Why: the gold "crawls" because the deck accelerates slowly one way and snaps back the other — the bed of particles slides relative to the deck on the fast return. That only works if the deck's motion in the ground frame is the motion the head motion was designed to produce. Put the whole machine on soft springs and the base moves in antiphase with the deck: with a moving deck-plus-slurry mass around 200–300 kg on a ~600 kg base, the base would absorb a meaningful fraction of the stroke and the stroke shape degrades. The chat itself noticed this ("soft isolation can reduce effectiveness") but kept computing anyway.

**Replacement design rule:** bolt the frame rigidly to a concrete pad sized to many times the machine mass (see §9). Thin rubber pad under the feet *only* if noise to neighbours becomes a problem, and never coil springs. All the transmissibility/damping arithmetic is retired from this design; it is not wrong as physics, it is irrelevant to this machine.

### 1b. "Two tables for 10 tpd" depends on where the table sits in the circuit

A full-size table is a **cleaner**, not usually a rougher, at this tonnage. Two circuits are possible:

| Circuit | What the table sees | Tables needed |
|---|---|---|
| **A — table as primary concentrator** | the whole classified 10 tpd (≈0.5–0.6 t/h over 18–20 h) | 2 (one is marginal with zero redundancy) |
| **B — rougher ahead of the table** (centrifugal bowl or spiral/helix → table cleans the concentrate) | a few % of plant tonnage | 1, with capacity to spare |

The planetGOLD mercury-free plant in Paracale reportedly runs B (centrifuge + helix + table) at ~3.5 tpd. The chat assumed A. **D-1 (Stephen/Allan): which circuit?** The prototype is the same machine either way, so this does not block fabrication — it decides whether table 2 is ever built and what goes upstream.

### 1c. Nobody has characterised the ore

Everything above assumes free-milling gold liberated below ~2 mm. Paracale deposits are commonly sulfide-associated; if a large share of the gold is locked in pyrite/arsenopyrite, gravity alone recovers a fraction of it regardless of how well the table is built. **Before cutting steel:** take a representative 20–50 kg sample, stage-grind, and run a gravity-recoverable-gold (pan/lab-table) test. This tells you the target size distribution, and therefore stroke, speed, slope and riffle height — the numbers in §8 are starting points *until the test exists*.

### 1d. What stands

Deck geometry, the eccentric-shaft spec, the materials list, the local-sourcing map, riffle principles, the build sequence and the cost envelope all survive review and are carried forward below, tightened.

---

## 2. Design basis (plain language)

| Item | Prototype target | Note |
|---|---|---|
| Deck | ≈ 4.5 m long × 1.8 m wide at the head end, concentrate end slightly narrower | standard full-size 6-S class |
| Deck construction | welded steel skeleton + 8–12 mm abrasion-grade rubber/EPDM lining + tapered riffles | FRP deck deferred to table 2 |
| Capacity | 0.5–1.2 t/h of ≤2 mm feed, 15–30 % solids | depends heavily on feed size |
| Stroke | adjustable 8–22 mm; commission at 12–16 mm | |
| Frequency | 240–360 strokes/min; commission at 280–320 | |
| Cross (side) slope | adjustable 0–8°; commission at ~3° | screw jacks |
| End slope | level to concentrate end raised ≤ 1° | tuning parameter |
| Drive | 1.1–1.5 kW electric via V-belt to eccentric shaft + toggle/pitman head motion | VFD strongly recommended |
| Empty weight | ≈ 600–900 kg | weigh the finished unit |
| Footprint with launders | ≈ 6 m × 3 m + working space both long sides | |
| Water | ≈ 1–3 m³/h wash + feed water, recycled | settling pond or tank |
| Power | 220 V; single-phase OK if a 1-phase-in / 3-phase-out VFD is used | see D-3 |
| Operator | 1 person once tuned | |

**Expected output when fed clean, classified material:** a high-grade gold concentrate off the end of the deck (re-clean on the same table at lower feed, or on a small cleaner table), a middlings stream to re-feed, and clean tailings off the long side. Well-tuned tables of this class routinely recover the majority of free gold down to fine sizes; the actual recovery number comes from the ore test, not from this document.

---

## 3. Decisions for Stephen

| # | Decision | Default if not overruled |
|---|---|---|
| D-1 | Circuit A (table roughs) or B (rougher upstream, table cleans) | Build prototype either way; decide before table 2 |
| D-2 | Deck size: full 4.5 m or a 3–3.5 m "half" unit for the prototype | Full size — the head motion is the hard part and is the same cost either way |
| D-3 | Motor: 3-phase 1.1 kW + VFD (needs 3-phase supply or 1-ph-in VFD) vs single-phase 1.5 HP fixed speed | 3-phase motor + single-phase-input VFD; confirm the MFPS plant supply phase and spare capacity (C-8) |
| D-4 | Head motion: copy a 6-S toggle/spring mechanism vs simpler eccentric + pitman + rubber return | Copy 6-S geometry — measure a reference unit (§12) |
| D-5 | Deck support: leaf-spring flexures vs rocker/pivot stands | Flexures (fewer wear parts) |
| D-6 | Deck lining: local conveyor-grade rubber vs imported Linatex-class | Local rubber for the prototype; note wear rate |
| D-7 | Riffle material: hardwood (tapered by jig) vs rubber strip vs aluminium bar | Hardwood for the prototype (§7) |
| D-8 | Foundation: cast-in concrete pad vs heavy steel skid | Concrete pad at the final site (§9) |

---

## 4. Fabricator brief (one page, plain language — hand this to the shop)

We are building a gold shaking table about 4.5 m long and 1.8 m wide. It is a flat steel deck, covered with thick rubber with thin raised strips (riffles) on it, that shakes back and forth about 300 times a minute with a short 12–16 mm stroke. Heavy gold moves along the strips to one end; sand washes off the side with water.

What the shop builds:

1. **A heavy base frame** from 150 × 75 (or 200 × 75) mild-steel channel and 50–65 mm angle, with four (or six) feet drilled for M16–M20 anchor bolts. It must be stiff — no flexing when you stand on a corner — and square.
2. **A deck skeleton**: a welded frame of flat bar and angle, skinned with 3–4 mm plate or 6 mm marine ply, that stays flat to within ~2 mm over its length. The rubber sheet is glued and bolted on top later.
3. **Deck supports**: four to six flexure legs (spring steel strip or stacked leaf) or pivoting rocker stands that let the deck move only lengthwise, plus screw jacks to tilt the deck sideways and lengthwise while it runs.
4. **The head-motion box**: a steel housing carrying the eccentric shaft on two pillow-block bearings, a connecting rod, a toggle/rocker arm and a return spring, with a hand-wheel or threaded stop to change the stroke. The eccentric shaft itself is a separate job for a lathe shop (§6).
5. **A motor mount** on slotted rails for belt tension, guard over belt and pulley.
6. **Feed box, wash-water pipe and three collection troughs** (concentrate, middlings, tailings) from plate, PVC or stainless.
7. **Paint**: primer + industrial topcoat, because everything sits wet.

Tolerances that matter: the deck must be flat; the eccentric shaft journals must run true; the frame must not rack. Nothing else is precision work.

---

## 5. Bill of materials — one prototype table

Costs are **ESTIMATE / UNQUOTED** (mid-2026 web-research ranges from the design chat). Replace with real quotes as they arrive — that is the purpose of the last column.

| Category | Items | Qty (approx.) | Likely source | Est. ₱ | Quote |
|---|---|---|---|---|---|
| Structural steel | C-channel 150×75 / 200×75; SHS 50×50×3; angle 50×50×5 and 65×65×6; plate 6–10 mm; flat bar | 450–550 kg | Daet steel yards (e.g. Double R Steel) or QC/Manila service centres | 35,000–48,000 | |
| Deck skin | 3–4 mm plate or 6 mm marine ply on skeleton | ≈ 8 m² | same | incl. above | |
| Deck lining | abrasion-grade rubber / EPDM 8–12 mm | 12–15 m² | Matlex, Dela Torre & Co., conveyor-rubber suppliers (Manila) | 18,000–35,000 | |
| Riffles | hardwood strips (or rubber strip) + adhesive + SS screws | ≈ 45–50 riffles, 1–4 m each | local lumber / hardware | 3,000–8,000 | |
| Motor | 1.1 kW 3-ph 4-pole TEFC (or 1.5 HP 1-ph) | 1 | industrial motor houses, QC/Manila | 6,000–15,000 | |
| VFD | 1.5 kW, 1-ph 220 V in / 3-ph out | 1 | same / online industrial sellers | 5,000–10,000 | |
| Pulleys + belt | heavy driven pulley (acts as flywheel), motor pulley, B-section V-belt | 1 set | local casting/machining or stock | 3,000–8,000 | |
| Eccentric shaft | AISI 1045 / S45C bar, machined to §6 | 1 | lathe shop, Daet/Paracale/Naga/QC | 8,000–18,000 | |
| Bearings | UCP pillow blocks for Ø45–55 journals; big-end bearing or bronze bush | 4–6 | industrial hardware | 2,000–6,000 | |
| Head motion parts | connecting rod, toggle/rocker, return spring, stroke adjuster, housing | 1 set | fabricator + lathe shop | 6,000–12,000 | |
| Deck supports | flexure strips or rocker stands; 4–6 screw jacks M16–M20 | 1 set | fabricator | 4,000–8,000 | |
| Feed/water/launders | feed box, spray bar with valves, 3 launders, hose, drains | 1 set | fabricator + plumbing supply | 5,000–10,000 | |
| Anchors + hardware | M16–M20 anchor bolts, fasteners, grease nipples | assorted | hardware | 3,000–6,000 | |
| Finish | primer, topcoat, sealant, epoxy | | hardware | 3,000–5,000 | |
| Fabrication labour | cutting, welding, assembly, fitting | | one primary shop | 45,000–75,000 | |
| **Total, one table** | | | | **≈ 145,000–260,000** | |

Realistic mid-point with local labour: **₱160,000–190,000** per the design chat — treat as a planning number only until three lines above carry real quotes. Excluded: concrete pad (§9), water tank/pump, feed preparation (screen/mill), site electrical run.

---

## 6. Eccentric shaft — machining specification (give to the lathe shop)

**Material:** AISI 1045 / S45C or local equivalent medium-carbon steel, round bar. Optional quench & temper to 28–35 HRC; acceptable to run as-machined if good sealed bearings are used.

**Overall length:** 300–450 mm to suit the head-motion housing width (fix after housing design). Leave stock at both ends for centres.

| Feature | Dimension | Tolerance / finish |
|---|---|---|
| Main journals (×2) | Ø50 mm (range Ø45–55), 40–60 mm long each | h6/g6 to bearing bore; Ra ≤ 0.8 µm (ground preferred); concentric to each other ≤ 0.03 mm TIR |
| Eccentric lobe | Ø60–80 mm × 40–60 mm wide | offset (throw) **8 mm** initial (range 4–12.5); offset held ±0.05 mm; parallel to main axis |
| Drive end | keyed for pulley; key 12×8 or to suit Ø; shoulder or lock-nut for axial retention | |
| Counterweight provision | drilled/tapped boss or bolt pattern opposite the lobe for bolt-on plates | adjustable in the field |
| Lubrication | grease-nipple hole to big-end if plain bush used | |

**Sequence:** rough-turn between centres → finish main journals → offset centres (or CNC) and turn the lobe → mill keyway → drill/tap → deburr → check offset and runout with a dial indicator → heat-treat if specified → final grind journals.

**Why 8 mm:** with a simple eccentric + pitman that gives ~16 mm deck stroke; with a toggle head motion the linkage modifies it and the stroke adjuster handles the rest. 8 mm sits inside the working range for both.

**Balance:** static balance with the bolt-on counterweight first; a heavy driven pulley (flywheel) smooths the rest. Two-plane dynamic balancing is not required at ~300 rpm if the journals are true and the frame is anchored.

---

## 7. Riffles — design and how to fabricate the taper locally

### 7a. Layout (for a ≈ 4.5 × 1.8 m deck)

| Parameter | Spec |
|---|---|
| Direction | parallel to the long axis = the direction of shake |
| Pitch | 30–35 mm centre-to-centre (use 32 mm) |
| Width | 8–10 mm |
| Height | 8–10 mm at the head (feed) end → tapering to ~1–2 mm (feather) at the riffle's own end |
| Count | riffled band ≈ 1.5 m wide ÷ 32 mm ≈ **45–48 riffles** |
| Lengths | **longest on the lower (tailings) edge**, ≈ 4.0 m; shortest near the upper (wash-water) edge, ≈ 1.0 m; riffle ends lie on a straight diagonal line between those two points |
| Cleaning plane | the unriffled triangle this leaves at the upper concentrate corner (roughly a quarter to a third of the deck) — this is where fine heavies get their final wash; **do not riffle it** |
| Removable | yes — screws not just glue, so height and pitch can be changed during tuning |

The taper is what makes the table selective: each riffle is a successively lower barrier, lights wash over and off, heavies keep crawling. Riffles of uniform height concentrate poorly.

**Strong recommendation before finalising any of this:** photograph and measure the riffle layout of an operating 6-S deck and copy it — if the MFPS gravity circuit carries one, Stephen measures it in-house (C-17). The numbers above are textbook-class; the reference deck is proven on local ore.

### 7b. Fabricating tapered riffles — Method A, hardwood (prototype default, D-7)

1. **Timber:** a dense, water-stable hardwood — yakal or molave if obtainable; otherwise strips ripped from 12 mm marine plywood (laminations resist swelling). Not coco lumber (splits, swells).
2. **Rip** strips 10 mm wide × 12 mm high, oversize in length. Cut one per riffle to its layout length plus 50 mm.
3. **Mark the taper:** on each strip, mark full height (10 mm) at the head end and 1.5 mm at the far end; join with a straight-edge. Because riffle lengths differ, each riffle has its own taper rate — the line does that automatically.
4. **Cut the taper:** band saw along the line, then true up with a hand plane or on a belt sander. Faster for a batch: a planer sled — a long flat board with an adjustable shim under one end — run through a thickness planer; set the shim so the strip's far end comes out at 1.5 mm. Check three strips with a vernier before doing the rest.
5. **Seal:** two coats of epoxy or marine varnish on all faces, ends especially. Unsealed wood swells, lifts and traps gold.
6. **Fix to the deck:** bead of polyurethane adhesive (Sikaflex-class) under the strip + stainless countersunk screws every 250–300 mm, through the riffle and the rubber into the steel skeleton (drill and tap M4/M5 in a backing flat bar, or fit rivnuts). Screw heads set below the riffle top so they never stand proud of the feather end.
7. **Lay out on the deck** with a chalk line and a 32 mm spacer block; fix the longest (lower-edge) riffle first and work up.

### 7c. Alternatives

- **Method B — rubber strips:** cut 10 mm strips from the same lining sheet with a straight-edge and knife; taper by belt-sanding against a tapered fence, or use a **stepped** taper (10 / 7 / 4 / 2 mm sections) bonded with contact cement. Best wear life, slowest to make accurately; good for table 2 once the layout is proven.
- **Method C — aluminium flat bar 3 × 10 mm** ground to a taper: durable but heavy, noisy and laborious. Not recommended.
- **Method D — riffles moulded into an FRP deck:** the commercial standard; defer until the geometry is proven on the prototype.

---

## 8. Deck slope and operating settings

Three slopes/motions are adjustable. Start values below are published 6-S / Wilfley-class ranges; the ore test (§1c) narrows them.

| Feed class | Cross slope (side) | Stroke | Strokes/min | Wash water | Feed solids |
|---|---|---|---|---|---|
| Coarse sand 0.5–2 mm | 4–6° | 16–22 mm | 240–280 | higher (≈2–3 m³/h) | 20–30 % |
| Fine sand 0.1–0.5 mm | 2.5–4° | 11–16 mm | 280–320 | medium (≈1.5–2 m³/h) | 20–25 % |
| Slimes < 0.1 mm | 1–2.5° | 8–12 mm | 320–360 | low (≈1–1.5 m³/h) | 15–20 % |

**End (longitudinal) slope:** start level along the riffles; raise the concentrate end in small steps (never more than ~1°) only if lights are reaching the concentrate end. The shake conveys heavies uphill; lights cannot climb — that is what makes a slight rise selective.

**Rule of thumb on cross slope vs water:** slope and wash water do the same job (pushing lights across and off). Use slope first, water second; too much water washes fine gold away, too little lets sand ride the riffles to the concentrate end.

### 8a. Field tuning procedure (commissioning)

1. **Level** the deck both ways with a long spirit level laid on the riffle tops. Record jack positions.
2. **Dry run** at the lowest speed: check the stroke with a pencil-and-card trace, listen for knock, feel the bearings, tune the counterweight until the frame is quiet.
3. **Water only:** set cross slope ~3°, open the wash bar; the sheet of water must flow evenly across every riffle with no dry strips and no channelling. Fix the spray bar before feeding anything.
4. **Feed low** (a third of target) with classified material. Within minutes a diagonal band forms: heavies (dark/bright line) hugging the riffle ends toward the concentrate corner, lights fanning off the lower edge.
5. **Read the band and adjust one thing at a time:**
   - heavies reaching the tailings edge → less cross slope or less water;
   - sand reaching the concentrate end → more cross slope / more water / slightly raise the concentrate end;
   - band smeared, no clean line → shorter, faster stroke (fines) or longer, slower stroke (coarse);
   - riffles packing solid → stroke too short or feed too thick.
6. **Raise feed** stepwise until the band starts to smear, then back off ~20 %. That is the table's real capacity on that ore.
7. **Log every setting** (jack turns, VFD Hz, stroke, water valve position, feed rate) with a photo of the band. These become the setup sheet for table 2.

---

## 9. Foundation (replaces the isolation section)

- **Concrete pad** at the final site: ≈ 5.5 m × 2.5 m × 0.3 m (≈ 4 m³, ≈ 10 t) — an order of magnitude more than the machine, which is what keeps the stroke honest. Reinforce with a single mat; cast in M16–M20 anchor bolts from the frame template; level the top to ±3 mm.
- **Drainage:** slope the surrounding slab to a sump; the tailings launder must run away freely.
- **Portable alternative (D-8):** a steel skid of ≥ 1.5 t with the frame welded down, pinned to the ground — acceptable for trials, not for production.
- **Rubber:** 10–15 mm industrial pad under the feet *only* if structure-borne noise is a problem. **No coil springs.**

---

## 10. Build and commissioning sequence

1. Ore sample → gravity-recoverable-gold test (§1c). *Can run in parallel with steel fabrication; must finish before riffles are cut.*
2. Visit and measure the reference 6-S deck and head motion (§12). Photograph riffle layout, deck supports, toggle geometry.
3. Stephen freezes dimensions and issues shop sketches (frame, deck skeleton, head-motion housing, eccentric shaft per §6).
4. Lathe shop: eccentric shaft (critical path, longest lead).
5. Fabricator: base frame → deck skeleton → supports and jacks → head-motion housing → motor mount → launders.
6. Bond rubber lining; cut, seal and fit riffles (§7).
7. Dry-run and balance on the shop floor; fix pulley/belt/guard.
8. SMBC written consent; cast the pad inside/beside the MFPS (cure ≥ 7 days before loading).
9. Set the table, anchor, plumb water, wire motor + VFD + emergency stop.
10. Wet commissioning per §8a; record the setup sheet.
11. Decide table 2 (D-1) from measured capacity and recovery.

---

## 11. Cost envelope (ESTIMATE / UNQUOTED)

| Item | ₱ |
|---|---|
| One prototype table, materials + local fabrication (§5) | 145,000–260,000 (planning mid-point 160,000–190,000) |
| Concrete pad, anchors, drainage | separate — local quote |
| Water tank/pump, feed screen, site electrical | separate |
| Second table, if D-1 → circuit A | ≈ same again, less design time |

Imported 6-S units were cited in the chat at roughly USD 1,500–3,500 FOB before freight, duty and delay — the local build is cheaper, repairable on site, and builds the skill to make table 2.

---

## 12. Open items / to verify

| # | Item | Owner |
|---|---|---|
| 1 | Ore sample and gravity test — size distribution, free vs locked gold | Allan / Stephen |
| 2 | Power at the MFPS: phase, voltage, spare capacity for two 1.5 kW drives (the plant already has supply) | Stephen |
| 3 | Reference unit: does the MFPS gravity circuit carry a shaking table (reported centrifuge + helix + table)? If so Stephen measures it in-house; else arrange a visit elsewhere | Stephen |
| 4 | Three fabrication quotes (steel + labour), one lathe-shop quote for the shaft, one rubber quote | Stephen |
| 5 | MFPS water and tailings/settling capacity for the added tables | Stephen |
| 6 | Consents: executed Operational Partnership Agreement copy; SMBC written consent to install; added tables inside the MFPS permits/ECC (PMRB / MGB-V) | Stephen / Jonathan |
| 7 | Role of the tables (main-circuit cleaner vs the deal memo §5 toll-basis secondary station) and title to them (GIMS / SMBC / investor group) | Allan / Stephen |
| 8 | Marlon Malaluan's operating role (named operator in the draft memo; not in Res. 2026-009) | Stephen |
| 9 | Allan-supplied manpower: headcount, skills (welder / fitter / mason / operators), cost basis (in-kind vs paid), availability date | Allan |
| 10 | Accolade file — Stephen's and the project's credentials/recognitions, verified documents only | Stephen / Allan |
| 11 | Funding and involvement lines (planetGOLD / UN-GEF follow-on, DENR-MGB / PMRB / LGU, investors, TSX-V path, NGOs): programme name/phase, who leads each | Allan / Stephen / Jonathan |

---

*Document history:* v0.1 2026-08-23 — consolidated from the design chat, isolation track retired, circuit/ore-test gates added, riffle fabrication and slope settings written up. v0.2 2026-08-23 — site moved to the SMBC MFPS (Casalugan), Stephen Lloyd spotlighted as design lead + operating partner, consent/title/inventory open items added; LAB X deck generated. Next revision after Stephen's D-1…D-8 calls.
