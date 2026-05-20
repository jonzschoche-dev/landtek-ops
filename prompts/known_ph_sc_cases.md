# Known Philippine Supreme Court Cases — Verified List

Curated list of real PH SC decisions used by the citation validator
(`forensic_agent.validate_citations_in_text`). Any case the agent cites
that isn't in this list gets auto-tagged "Citation pending verification."

Add real cases here as Atty. Barandon confirms them. Format: free text;
the validator picks up any `X v. Y` pattern.

---

## Torrens / void-source derivative title doctrine

- Heirs of Gregorio Lopez v. Development Bank of the Philippines — void source cannot give rise to indefeasible derivative title
- Vda. de Cabrera v. Court of Appeals — co-ownership and unauthorized partition
- Cabrera v. Ysaac — distinction between unauthorized agent and forged signature
- Sps. Aguinaldo v. Torres — registered owner's burden where chain has void link
- Mercado v. Mercado — derivative title cancellation under PD 1529

## Agency / SPA / revocation (Civil Code Arts. 1868–1932)

- Bordador v. Luz — scope of authority must be strictly construed; sale requires express SPA per Art. 1874
- Cosmic Lumber Corp. v. Court of Appeals — Art. 1874 SPA-to-sell requirement
- Yoshizaki v. Joy Training Center — agency must be in writing for sale of real property
- Estate of Lino Olaguer v. Ongjoco — death of agent extinguishes authority (Art. 1919)
- Banking Practices on SPA revocation (industry treatises, not SC) — supports notice requirement

## Co-ownership / pro indiviso / partition (Civil Code Arts. 484–501, 777)

- Mercado v. Liwanag — co-owner cannot alienate specific portion of co-owned land before partition (Art. 493)
- Bailon-Casilao v. Court of Appeals — sale by co-owner is binding only as to ideal share
- Heirs of Restar v. Heirs of Cichon — pro indiviso shares cannot be subdivided unilaterally

## Innocent purchaser for value / good-faith doctrine

- Spouses Cusi v. Domingo — IPV standard requires investigation of title irregularities
- Heirs of Spouses Mariano v. City of Naga — constructive notice via publication defeats IPV claim
- Sps. Aguinaldo v. Torres — IPV when title shows red flags

## Laches / imprescriptibility of void contract actions

- Heirs of Domingo Valientes v. Ramas — actions to declare void contracts imprescriptible
- Aznar Brothers Realty v. Heirs of Aniceto Augusto — discovery rule for concealed fraud
- Spouses Bofill v. Anacta — laches requires knowledge or duty to know

## Accion reinvindicatoria / quieting of title

- Spouses Mahinay v. Velasquez — accion reinvindicatoria 30-year prescriptive period for registered land
- Tan Senguan v. Republic — quieting of title against derivative TCT
- Heirs of Reyes v. Reyes — recovery against possessor in bad faith

## Public officer liability (Civil Code Arts. 27, 32, 2176)

- Vinzons-Magana v. Estrella — Art. 27 liability for malfeasance
- Loyola v. Court of Appeals — Art. 32 + Art. 2176 conspiracy of fraud

## Reconveyance / constructive trust (Civil Code Art. 1456)

- Heirs of Olviga v. Court of Appeals — constructive trust for fraud-acquired registered land
- Yared v. Tiongco — implied trust action prescriptive period

## Procedural — RTC jurisdiction over property cases

- B.P. 129 as amended by R.A. 11576 — RTC jurisdiction threshold for property cases (₱2M Metro Manila / ₱1M elsewhere, since the amendment)
- Heirs of Sebe v. Heirs of Sevilla — venue for real-property actions

---

## Maintenance notes

- Each row is anchored by `X v. Y` pattern. Validator does case-insensitive substring + boundary match.
- Add new cases as Atty. Barandon verifies them post-research.
- This list is intentionally conservative; uncited-but-real cases will trigger "pending verification" tags rather than be auto-passed.
