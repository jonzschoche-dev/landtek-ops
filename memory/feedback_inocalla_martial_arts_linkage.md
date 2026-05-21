# Feedback rule: Arnis / martial arts docs = Allan Inocalla / Paracale client

**Filed:** 2026-05-21 (Jonathan correction during deploy_257 wrap-up)

## What happened

Across deploys 244, 252, 253 and the manual audit, I left 7 docs flagged as
`status='proposed'` `flag_unrelated` at ≥0.95 LLM confidence:

  doc#385, 386, 387, 388, 405, 489, 491, 492, 493, 536, 546

The LLM described each as Sport Arnis, Filipino martial arts, Eskrima,
Kalisteniks, Barangay Tanod training, etc. — and I treated them as
"genuinely not-MWK", leaving them parked.

**Jonathan corrected this:** all arnis / martial arts files are
Allan Inocalla / Paracale client material. The Inocalla family runs a
martial-arts business (Sport Arnis Canada, Maharlika Filipino Martial Arts
World Federation, Camarines Norte Barangay Tanod training programs)
through Datu Shishir Inocalla / GM Shishir Inocalla / Master Shishir
Inocalla and GM Jesus Inocalla.

## The platform lesson

**A doc that's clearly not-MWK isn't necessarily not-anyone.** The LLM
correctly identified that Sport Arnis Canada material doesn't belong in
MWK's chain, but the only output options were `assign_matter` (one of MWK's
17 matters) / `flag_unrelated` / `keep_unscoped`. The cross-client question
"is this another client's matter?" had no path through.

Structural fix should be: when an LLM proposes `flag_unrelated` against
client X, the platform should automatically cross-check whether the doc
belongs to ANY other registered client BEFORE finalizing the verdict.

## Cross-client routing rules (encoded for future agents)

- "arnis", "eskrima", "kalisteniks", "martial arts", "barangay tanod"
  training programs, "sport arnis", "Maharlika Filipino Martial Arts
  World Federation", or any "Datu / GM / Master Shishir Inocalla" content
  → Paracale-001 / Allan Inocalla
- Inocalla family civil cases (Vicente, Jesus, Senen, Cipriana, Marilou,
  Herbert, Allan, Cesar Inocalla; surname "Cambronero") → Paracale-001
- Capacuan small-scale mining, Paracale Gold Corporation, MGB inquiries
  → Paracale-001 / PAR-CAPACUAN
- Allan Inocalla as authorized agent for Northern Island Builders →
  Paracale-001 (or MWK if the doc has Zschoche / Keesey signature
  evidence; check both)

## What was done in deploy_258

- Created matter `PAR-MARTIAL-ARTS` for Inocalla family Arnis business
- Reclassified 9 docs to `case_file='Paracale-001', matter_code='PAR-MARTIAL-ARTS'`
  (481, 486, 487, 488, 489, 491, 492, 493, 536)
- Reclassified doc#514 to `PAR-CV13-131220` (Inocalla civil case)
- Populated PAR keystone_entities with Allan, Shishir, Jesus
- Consolidated 6 alias entries under those 3 canonicals
- Superseded 9-10 wrong LLM flag_unrelated proposals
- Filed this memory rule
- Added `test_inocalla_martial_arts.py` regression test

## Open follow-up

- Verify whether Shishir Allan Inocalla (#8708) IS Allan V. Inocalla
  (#7983) — same person with Datu name, or separate brother/relative?
  If same: merge canonicals.
- Build cross-client routing into the entity-graph guard (deploy_252)
  so flag_unrelated proposals are first cross-checked against ALL
  registered clients' graphs, not just the proposing client's.
