# How Reimbursement Works — Legal Basis for Recovering the Estate Advances (MWK)

**Question answered:** by what law, and by what procedure, do Jonathan + Patricia get back the
**₱2,005,405.92** (and rising) advanced to recover, administer, and protect the Heirs-of-MWK estate —
and how much of it is charged to Gerry and Marcia, who refused to fund it.

> Statutory provisions below are black-letter PH law (Civil Code / Rules of Court) — accurate as text;
> confirm the current numbering against the official code before filing. **Jurisprudence is named by
> doctrine only — specific G.R. citations must be pulled from lawphil (jurisprudence ingest); none are
> invented here.**

---

## A. Co-ownership — the primary basis (Civil Code)
- **Art. 488** — *"Each co-owner shall have a right to compel the other co-owners to contribute to the
  expenses of preservation of the thing … and to the taxes."* → Gerry and Marcia each owe **1/3** of every
  preservation expense **and every tax** paid. This is the spine of the claim.
- **Art. 489** — repairs/expenses for preservation may be made at the will of one co-owner (notice to the
  others if practicable) — answers "you never agreed": consent isn't required for preservation.
- **Art. 500** — upon **partition**, there is a reciprocal accounting; advances/contributions are settled
  among the co-owners.
- **Arts. 546–548** — a possessor is refunded **necessary expenses** (all possessors) and **useful
  expenses** (possessor in good faith, with a right of retention until paid); luxury expenses are not
  refunded. Backstops the preservation/improvement outlays.

## B. Quasi-contract — Negotiorum Gestio (Civil Code Arts. 2142, 2144–2153)
The cleanest fit for the *refusal*: the property was neglected/abandoned by the other heirs, and Jonathan/
Patricia took charge without their mandate.
- **Art. 2144** — whoever voluntarily takes charge of the management of the neglected business/property of
  another, without mandate, must continue it until the owner can act.
- **Art. 2150** — even where the management was **not ratified** (or was against the owner's will), the owner
  is liable for obligations incurred in his interest and must **reimburse the gestor's necessary and useful
  expenses**, to the extent the owner **benefited**. → Gerry/Marcia benefit from the recovered estate, so
  they must reimburse even though they refused.
- **Art. 22 / Art. 2142** — no one may unjustly enrich himself at another's expense.

## C. Agency — advances under the SPA (Civil Code Arts. 1912–1913, 1918)
- **Art. 1912** — the principal must reimburse the agent for **all advances** made, **with interest from the
  day the advance was made.** → Patricia (principal) reimburses Jonathan's advances **with interest** — and
  the same interest logic supports claiming interest on the estate advances (mirrors the CV 6839 interest).
- **Art. 1913** — principal liable for damages the agent suffered without the agent's fault.
- **Art. 1918** — exceptions (agent acting against instructions, etc.) — none apply here.

## D. Guardianship — once appointed (Rules of Court, Rule 96)
- **§1** — guardian files an inventory of the whole estate within **3 months**.
- **§7** — guardian renders an **account** (receipt-supported).
- **§8** — the guardian is allowed **reasonable expenses** in executing the trust **and compensation**,
  fixed by the court and **chargeable to the estate**. → after 07-27, Jonathan-as-guardian's expenses +
  a court-fixed compensation are paid from the estate.

## E-bis. Presence wholly attributable to the estate → subsistence + COMPENSATION
**Foundational fact (to be sworn + proven):** Jonathan holds **no Philippine citizenship, has no employment
or business in the Philippines, and maintains no residence here** — he is present **solely to recover,
administer, and protect this estate.** Legal consequences:
1. **It rebuts the "personal living" objection.** The one weakness in the lodging/travel/office/subsistence
   categories is the argument that they are personal living, not management. With **no personal purpose in
   the country to offset**, the reasonable cost of his presence is a **cost of the management** (necessary
   expense / Art. 2150 negotiorum) — so categories C/D/G strengthen from "contestable" toward "necessary."
2. **His reasonable subsistence while serving is chargeable** — as a guardian's reasonable expense in
   executing the trust (**Rule 96 §8**) and, pre-appointment, as a necessary expense of the gestio.
3. **His services are separately COMPENSABLE — a second recovery head.** He functions full-time as the de
   facto administrator; **Rule 96 §8** entitles a guardian to **court-fixed compensation for services**
   (and Rule 85 §3 a commission for an administrator). This is *in addition to* expense reimbursement — the
   estate pays for both the outlays and the labor.
**Evidence to establish it:** his passport/visa status (temporary visitor, not resident/worker), absence of
PH TIN-as-employee/business registration, and a sworn declaration that his stay is exclusively for the
estate. This same fact reinforces the guardianship's **absence-amid-peril** theory (the owners are absent;
the sole person present is here only for the estate).

## E. Estate administration (Rules of Court, Rule 85) — only if an administration route is used
- **§1** accountability · **§3** commission/compensation · **§7** necessary expenses of care/management
  allowed. *(Note: the estate is settled co-ownership per PE-170452, so guardianship — not administration —
  is the vehicle; Rule 85 is a fallback frame.)*

---

## How the money is actually recovered (procedure + priority)
1. **First charge, off the top.** Necessary/preservation expenses and the guardian's court-approved expenses
   come **out of the estate proceeds BEFORE the 3-way distribution** (Rule 96 §8; estate-administration
   principle). Applied to CV 6839, sales, and rentals as a "less: reimbursable advances" line.
2. **Guardianship accounting** (Rule 96 §7/§8) — submit the receipt-backed account (Colen's statement +
   Index of Annexes) for court approval; approved amount paid from the estate.
3. **Partition accounting** (Art. 500) — advances settled among co-owners on partition (the Plan-B path).
4. **Direct action to compel contribution** (Art. 488) — against Gerry/Marcia for their 1/3 shares.
5. **Set-off (the cleanest execution)** — net Gerry's and Marcia's owed contributions **against their
   distributive shares** of CV 6839 / sale proceeds. They fund the fight retroactively, out of their cut.

## Recovery-strength tiers (map to the ledger's `reimburse_basis`)
| Tier | Class | Ledger basis | MWK amount |
|---|---|---|---|
| **1 (strongest)** | Taxes paid — Art. 488 names "the taxes" | `art488_tax` | ₱1,086,080 |
| **1** | Preservation/protection — fees to protect title, records, gov't liaison (Arts. 488, 546) | `art488_preservation` | ₱305,090 |
| **2 → upgraded** | Lodging/travel/office/subsistence — necessary-to-management (Art. 2150 / Rule 96 §8). **The "personal living" objection is rebutted** by Jonathan's wholly-estate-attributable presence (no citizenship/work/residence — §E-bis), so these strengthen toward "necessary." Still reasonableness-scrutinized. | `necessary` / `subsistence_management` | ₱614,236 (+ ongoing subsistence) |
| **separate head** | **Guardian's COMPENSATION for services** (his full-time labor as de facto administrator) — court-fixed, Rule 96 §8 / Rule 85 §3 commission. Distinct from expense reimbursement. | `rule96_compensation` | (future, court-set) |
| add-on | **Interest** on advances — Art. 1912 (from date advanced) | (computed) | (claimable) |

*Two new `reimburse_basis` values for going-forward logging: `subsistence_management` (estate-attributable presence costs) and `rule96_compensation` (his services). Add via `add_expense.py --basis`.*

**Substantiation is the gate:** reimbursement requires **receipts/ORs + reasonableness** — which is exactly
what Colen's Index of Annexes provides. Unsubstantiated advances are weak; keep every OR linked (`--doc`).

## Jurisprudence to pull (lawphil — do NOT cite unverified)
Doctrines to source and add to `jurisprudence_wishlist`: (a) co-owner reimbursement of preservation expenses
+ taxes (Art. 488); (b) negotiorum gestio reimbursement to extent of benefit (Arts. 2144/2150); (c)
guardian's/administrator's expenses + compensation (Rule 96 §8 / Rule 85); (d) interest on an agent's
advances (Art. 1912). Verify each G.R. in-text before any filing.

---

## Keeping the number rising — capability + responsibility
- **Capability (built):** `scripts/add_expense.py` — logs each new advance into `legal_cost_actuals` and
  reprints the live totals; `--report` shows them any time. Basis-tagged so the strong/contestable split
  stays visible. View of record: `v_mwk_reimbursement`.
- **Responsibility (the loop):** (1) **Colen Ibasco** remains the expense-documenter — her Statement +
  Index of Receipts is the source of truth; (2) each new advance (guardianship filing, mandamus, CV 6839
  execution, ongoing RPT) → one `add_expense.py` row citing the OR (`--doc`); (3) reconcile the ledger to
  her latest statement whenever she updates it; (4) at every proceeds event, run `--report` and claim the
  current total as a first charge + set-off against Gerry/Marcia.

*Internal work product — not legal advice for filing; counsel (Botor/Yuzon) adapts. Nothing filed/sent.*
