# The improvements are a tax question, and that changes the forum

> Working note, 16 September 2026, from Jonathan's point: *improvements directly affect the taxes we
> pay; unpermitted structures with no proof of occupancy are erroneously declared — hence adversely
> affecting our tax rate.* Statutory text pulled verbatim from the law library, not from memory.
> `[V]` verified from source · `[I]` inference from corpus arithmetic · `[TO-VERIFY]` open.

## Why this is the better track

Every records-shaped request in this cluster has died on the same wall: ARTA §4(f), "not a government
service" — five dockets, five closures (`project-arta-cluster-positioned-to-lose`). A **taxpayer's
assessment protest is not a records request.** Jonathan is the person in whose name the Municipality
itself declared these parcels, and who has paid the tax. Standing is unimpeachable, the forum is the
LBAA and BLGF rather than ARTA, and the clocks are statutory. The improvements point moves the fight
out of the forum we keep losing in.

## The mechanism, verified

**Real property tax is levied on land *and* improvements**, and the duty to declare an improvement
falls on the person who makes it:

> **R.A. 7160 §202.** *"It shall be the duty of all persons, natural or juridical, owning or
> administering real property, **including the improvements therein**… to prepare… and file with the
> provincial, city or municipal assessor, a sworn statement declaring the true value of their
> property…"* `[V]`
>
> **§203.** *"It shall also be the duty of any person… **making any improvement on real property**,
> to prepare… and file… a sworn statement declaring the true value of subject property, within sixty
> (60) days after the acquisition of such property or **upon completion or occupancy of the
> improvement, whichever comes earlier**."* `[V]`

And the Building Official is wired by statute to the Assessor:

> **§210.** *"Any public official or employee who may now or hereafter be required by law or
> regulation to issue to any person **a permit for the construction… of a building, or permanent
> improvement on land**… shall transmit a copy of such permit or certificate **within thirty (30)
> days of its issuance, to the assessor** of the province, city or municipality where the property is
> situated."* `[V]`

## The pincer

These two provisions close on the same officer. For every structure on the estate's parcels:

- **If a permit was issued** → §210 obliged the Building Official to transmit it to the Assessor
  within 30 days → the improvement should appear on the assessment roll.
- **If the improvement is not on the roll** → either **no permit issued** (P.D. 1096 §301 violation by
  the builder, unenforced by the Building Official), **or** a permit issued and the **§210 transmittal
  failed** (R.A. 7160 §210 violation by that same Building Official).

There is no third branch. Whichever is true, the same office is answerable — and the answer is
mechanical, not argumentative. This is the cleanest item we have, because it cannot be met by a
characterisation.

## Which branch are we actually in? The arithmetic already hints

`ESTATE_DECLARED_PARCELS_2026-09.md` records that on **27 of the 29** parcels declared in the heirs'
names, `area × ₱970/sq m` reproduces the Municipality's declared market value **to the peso**.

A declared market value that is exactly land area × a land unit rate **contains no building
component.** `[I — strong]` So the estate's declarations appear to be **land-only**, and the
structures standing on those parcels are **undeclared improvements**: nobody is paying RPT on them,
and the Municipality has let them escape the roll — while the registered owners pay on the ground
beneath them.

`[TO-VERIFY]` Confirm from the face of the ARPs, which carry separate Land and Improvement blocks
plus a Classification / Actual Use field. The arithmetic is strong but it is inference; the ARP face
is proof. The improvement and structural records are the ones the Municipal Assessor has withheld
[doc 2388] — which is now not merely an access grievance but a **fiscal injury**, since the heirs
cannot verify what they are being taxed on.

## The rate point — Jonathan is right, and here is the size of it

Two distinct mechanisms, both verified:

**(a) Actual use drives the assessment level.** Assessment levels for **land** under §218(a) `[V]`:

| Class | Assessment level |
|---|---|
| **Residential** | **20%** |
| Agricultural | 40% |
| **Commercial** | **50%** |
| Industrial | 50% |

If unpermitted **commercial** structures operate on the estate's parcels and the Assessor classifies
by actual use, the land moves from 20% to 50% — **2.5× the assessed value on the same market value,
and therefore 2.5× the tax** — driven entirely by a use the owners never authorised and that no
permit sanctions. The corpus already records *"numerous private and informal structures — residential
**and commercial**"* [doc 2853]. `[TO-VERIFY: the classification actually carried on each ARP.]`

**(b) Unpermitted construction is an express trigger to reassess upward.**

> **§220.** *"…the assessment of real property shall not be increased oftener than once every three
> (3) years **except in case of new improvements substantially increasing the value of said property
> or of any change in its actual use**."* `[V]`

So the general three-year shield does not protect the heirs against an increase caused by somebody
else's building. And §221 lets a reassessment for *"a major change in its actual use"* be made within
90 days of the cause.

**The asymmetry is the point.** Unpermitted structures can raise what the heirs pay — through
classification and through §220 — while the structures themselves sit off the roll paying nothing.
The owners carry the rate consequence of a use they never consented to; the occupants carry none of
the tax.

## The remedies this opens

| Remedy | Provision | Clock | Note |
|---|---|---|---|
| **Appeal to the LBAA** — assessment not satisfied | §226 | **60 days from receipt of the written notice of assessment** `[V]` | *"Any owner or person having legal interest… who is not satisfied with the action of the… assessor in the assessment of his property"* — petition under oath, with tax declarations attached |
| **Refund / credit of excessive collection** | §253 | **2 years** from entitlement; treasurer decides in 60 days `[V]` | *"When an assessment… is found to be **illegal or erroneous** and the tax is accordingly reduced or adjusted…"* — Jonathan's word "erroneously" is the statute's own word |
| **Back taxes on the undeclared improvements** | §222 | up to **10 years** prior to initial assessment `[V]` | Runs against the *occupants*, not the estate — and gives the LGU a fiscal reason to act |
| **Assessor must declare where the owner will not** | §204 `[TO-VERIFY text]` | — | Removes the "nobody filed" excuse |
| **BLGF supervisory review** | existing lane | — | `BLGF_RPT_ESCALATION_SPINE.md` is already open; this is a new, stronger item for it |

## What to do with it

1. **Pull the ARP faces** for the 29 parcels — Land block, Improvement block, Classification / Actual
   Use, assessment level. This single step decides whether the claim is *"we are over-assessed"*
   (branch a) or *"the structures escape tax entirely"* (branch b). Both are good; they go to
   different forums. The Provincial Assessor has produced records before and is the path of least
   resistance.
2. **Add §210 as item 3 of the DPWH letter** — done, in
   `DPWH_NBC_ENFORCEMENT_REQUEST_2026-09_rev2.md`.
3. **Add the same item to the BLGF lane**, where it is an assessment-operations question rather than
   a building question: the roll omits improvements that Section 210 should have placed on it.
4. **Do not plead the rate injury until the ARP classification is in hand.** The mechanism is
   verified; the application to these parcels is not yet. Pleading a 20%→50% injury that the ARPs do
   not show would be the one impeachable sentence in an otherwise mechanical case.

## Note on the phrasing

Jonathan's *"erroneously declared"* is precise and worth keeping: **§253 uses "illegal or erroneous"**
as the statutory trigger for repayment. That is the word the forum is listening for. Use it.
