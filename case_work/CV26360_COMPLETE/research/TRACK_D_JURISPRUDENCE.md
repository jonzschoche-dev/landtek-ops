# Track D: Controlling Jurisprudence, CV 26-360 (Zschoche v. Balane)

**Status:** research only, for counsel (Atty. Barandon). Not filed. Not sent. Prepared 2026-10-13.
**Verification rule applied:** a case appears under VERIFIED only if its decision text was fetched from lawphil.net today or read from the LandTek law library (`legal_authorities.full_text`), **and** both the G.R. number and the quoted words were found in that text. "Lib #" is the `legal_authorities.id`; the text is chunked in `legal_chunks` under the same citation. Statutory text is from lawphil's copies of RA 386 (Civil Code) and PD 1529, fetched today.
**Ingested today** through `scripts/ingest_jurisprudence.py`, with the G.R. number checked in the text before embedding, 15/15 OK: Lib #66–80 (Yoshizaki, Yabut, San Pedro, Central Surety, Strait Times, New Durawood, Demetriou, Rexlon, Ciruelas, VSC, Esguerra, NHA v. Manila Seedling, Vallido, Olegario, Chua). Each is linked to `MWK-CV26360` in `matter_authorities`.

**Fact inputs.** The case facts come from the task brief. Anything I checked in the corpus is cited by doc id. Anything not checked is marked *[PENDING VERIFICATION]*.

---

## Read this first: three cracks on our side that this research found

1. **The "negotiate-only" framing of Prong A is vulnerable.** The certified true copy of the 16 Mar 1992 SPA (doc 416, an LRA CTC; the OCR is garbled) reads, in substance: *"to negotiate for the sale of the above-described real estate property in favor of third persons in possession [under] CONTRACTS TO SELL executed by the previous administrator, MR. BEN LLAMANZARES and/or to those who have paid their down payments … Said sale shall be upon such terms … after prior consultation with us, and to sign and execute the necessary documents … as well as to receive the proceeds of the aforementioned sale."*
   - Because the SPA also grants the power to sign documents and receive the proceeds, the defense will say a sale is "a necessary ingredient of the act" (Cosmic Lumber/Yoshizaki language).
   - **The stronger Prong A** is this: the power is confined to a **defined class of buyers** and to a **prior-consultation condition**. The sale to Balane falls outside the SPA **as written**, so neither Art. 1900 nor Art. 1902 can protect her. See P3–P5.
2. **The SPA clause is ambiguous on its face.** "Third persons in possession" could be read on its own, which would make an occupant like Balane fall inside the class. Counsel needs a clean, legible CTC of doc 416 ¶7 before arguing the class limit. *[PENDING VERIFICATION: exact wording of ¶7]*
3. **Our Art. 1922 position is internally inconsistent.** We cannot argue both that (a) Art. 1922 does not apply because de la Fuente's powers were special, not general, and (b) the 2020 newspaper publication was "sufficient warning" under Art. 1922.
   - Recommended order: lead with "outside the SPA as written, so revocation is irrelevant" (P4/P5).
   - Argue the 2020 publication only **in the alternative**, as a fact bearing on good faith before registration (P2, Duenas). Do not argue it as an Art. 1922 effect.

A fourth issue is housekeeping in our own law library. **Lib #13, *Tolentino v. Latagan*, G.R. 179874 (22 Jun 2015)**, is linked to MWK-CV26360 under `forged_deed_void` as if it helped us. It does not. The Court there **affirmed that the buyer Maria was an innocent purchaser for value** and denied the owners' petition. It is adverse authority the defense may cite. Re-label it; do not cite it for us.

---

## P1. Burden of proof and the definition of an innocent purchaser for value (IPV)

**Rule.** A buyer who claims to be an innocent purchaser for value must prove it. Pointing to the presumption of good faith is not enough.

**Verified authorities**
- **Heirs of Bucton v. Spouses Go**, G.R. No. 188395, **20 Nov 2013**, Perez, J. (2nd Div.). Lib #16, https://lawphil.net/judjuris/juri2013/nov2013/gr_188395_2013.html
  > "An innocent purchaser for value is one who buys the property of another without notice that some other person has a right to or interest in it, and who pays a full and fair price at the time of the purchase or before receiving any notice of another persons claim. The burden of proving the status of a purchaser in good faith and for value lies upon one who asserts that status. This onus probandi cannot be discharged by mere invocation of the ordinary presumption of good faith."
- **Duenas v. Metrobank**, G.R. No. 209463, **29 Nov 2022**, Hernando, J., **En Banc**. Lib #39, https://lawphil.net/judjuris/juri2022/nov2022/gr_209463_2022.html
  > "It is the party who claims to be an innocent purchaser for value who has the burden of proving such assertion, and it is not enough to invoke the ordinary presumption of good faith."
- **Spouses Vallido v. Spouses Pono**, G.R. No. 200173, **15 Apr 2013**, Mendoza, J. (3rd Div.). Lib #78, https://lawphil.net/judjuris/juri2013/apr2013/gr_200173_2013.html
  > "The burden of proving good faith lies with the second buyer (petitioners herein) which is not discharged by simply invoking the ordinary presumption of good faith."

**How it maps.** With her Judicial Affidavit excluded (doc 1089, per spine §1), Balane has no direct evidence to carry this burden. The presumption cannot carry it for her.

**What the defense will cite, and our answer.** They will cite Civil Code **Art. 527**: *"Good faith is always presumed, and upon him who alleges bad faith on the part of a possessor rests the burden of proof."*
- Art. 527 governs **possessors**.
- Bucton and Duenas govern the **IPV status** a Torrens buyer claims. That status is an affirmative claim, and the burden is on the claimant.

---

## P2. Good faith must continue until registration

**Rule.** A buyer must still be in good faith when the deed is registered. Notice of a defect acquired before registration defeats good faith.

**Verified authorities**
- **Duenas v. Metrobank** (En Banc, above):
  > "The Court now holds that buyers of registered land must be continuing purchasers for value and in good faith until the registration of the conveyance. In the event a buyer of registered land who has yet to register the conveyance is made aware of any claim or interest of some other person in the property, or of any defect or restriction in the title of the seller or in his or her capacity to convey title, the buyer shall no longer be considered to be in good faith even if he or she subsequently registers the conveyance."
  - The Court applied this to a 1994 registration. Nothing in the decision limits it to future cases.
- **Vallido v. Pono** (above):
  > "the registration of a later sale must be done in good faith to entitle the registrant to priority in ownership over the vendee in an earlier sale."
- **PD 1529 §51** (statute):
  > "The act of registration shall be the operative act to convey or affect the land insofar as third persons are concerned"

**How it maps.** The timeline:
- Sale: 29 Sep 2016.
- Revocation published: Sept–Oct 2020.
- Agent's death: 21 Jun 2017.
- Registration: 23 Nov 2021, about five years after the sale.

Any notice Balane received between 2016 and 23 Nov 2021 defeats her good faith. That includes the 2020 publication, any demand from the heirs, and the agent's death. *[PENDING VERIFICATION: what notice Balane actually had before 23 Nov 2021. The publication alone shows constructive notice at best.]*

**What the defense will cite, and our answer.**
- They will say Duenas involved an **annotated lis pendens** (registry notice), while a newspaper item is not being "made aware."
- Our answer: Duenas's test also covers awareness of "any defect or restriction … in [the seller's] capacity to convey title." In addition, the 1992 SPA with its class limit had been **annotated on T-52540 since 1996** (per the Oct-2026 testimony-prep record *[re-verify against the T-52540 CTC]*). PD 1529 §52 makes that registry notice:
  > "Every conveyance … instrument or entry affecting registered land shall, if registered … be constructive notice to all persons from the time of such registering"

---

## P3. A buyer from an agent must inquire into the agent's authority and read the SPA

**Rule.** A person buying from an agent rather than the registered owner must find out the agent's actual authority, which means reading the SPA and, where possible, asking the owners. Failing to do so means the buyer is not in good faith.

**Verified authorities**
- **Bucton v. Go** (above). This is our closest factual match.
  > "this protection is not extended to a purchaser who is not dealing with the registered owner of the land. In case the buyer does not deal with the registered owner of the real property, the law requires that a higher degree of prudence be exercised by the purchaser."

  Applying it, the Court said:
  > "An ordinary prudent man in this situation would have first inquired with the registered owner if he is indeed selling his property and if he authorized the purported agent to negotiate and to sell the said property on his behalf. It is inconceivable for the Spouses Go to have been without any opportunity to contact Felix before the transaction, given that the Spouses Go personally knew the Buctons"
- **San Pedro v. Ong**, G.R. No. 177598, **17 Oct 2008**, Chico-Nazario, J. Lib #68, https://lawphil.net/judjuris/juri2008/oct2008/gr_177598_2008.html
  > "every person dealing with an agent is put upon inquiry, and must discover upon his peril the authority of the agent, and this is especially true where the act of the agent is of unusual nature. If a person makes no inquiry, he is chargeable with knowledge of the agents authority, and his ignorance of that authority will not be any excuse."
- **Yoshizaki v. Joy Training Center of Aurora**, G.R. No. 174978, **31 Jul 2013**, Brion, J. Lib #66, https://lawphil.net/judjuris/juri2013/jul2013/gr_174978_2013.html
  > "persons dealing with an agent must ascertain not only the fact of agency, but also the nature and extent of the agents authority. … a person dealing with an agent is put upon inquiry and must discover on his own peril the authority of the agent."
- **Spouses Yabut v. Nachbaur**, G.R. No. 243470, **12 Jan 2021**, Carandang, J. Lib #67, https://lawphil.net/judjuris/juri2021/jan2021/gr_243470_2021.html
  > "First, respondent was merely dealing with an attorney-in-fact. Despite the presence of an alleged SPA from the registered owners, respondent should have inquired with the registered owners as to the extent of the authority of the attorney-in-fact, especially when the property is co-owned by two persons."
- **Bautista-Spille v. NICORP**, G.R. No. 214057, **19 Oct 2015**, Mendoza, J. Lib #10, https://lawphil.net/judjuris/juri2015/oct2015/gr_214057_2015.html
  > "The well-settled rule is that a person dealing with an assumed agent is bound to ascertain not only the fact of agency but also the nature and extent of the agent's authority. The law requires a higher degree of prudence from one who buys from a person who is not the registered owner."
- **Heirs of Sarili v. Lagrosa**, G.R. No. 193517, **15 Jan 2014**, Perlas-Bernabe, J. Lib #15, https://lawphil.net/judjuris/juri2014/jan2014/gr_193517_2014.html
  > "The buyer also has the duty to ascertain the identity of the person with whom he is dealing with and the latters legal authority to convey the property."
- **Duenas** (En Banc), and restated in **Chua v. Republic**, G.R. No. 253305, **2 Aug 2023**, Hernando, J. (Lib #80). This is the three-condition test:
  > "Such degree of proof of good faith, however, is sufficient only when the following conditions concur: first, the seller is the registered owner of the land; second, the latter is in possession thereof; and third, at the time of the sale, the buyer was not aware of any claim or interest of some other person in the property, or of any defect or restriction in the title of the seller or in his capacity to convey title to the property. Absent one or two of the foregoing conditions, then the law itself puts the buyer on notice and obliges the latter to exercise a higher degree of diligence"
- **Vallido v. Pono** names the absence of the owner's duplicate as a warning sign:
  > "Second, during the sale on July 4, 1990, Martino did not have the owners duplicate copy of the title."
- **Cosmic Lumber v. CA**, G.R. No. 114311, **29 Nov 1996**, Bellosillo, J. Lib #1. Cosmic Lumber is cited for **P4** (express authority), not P3.
- **Alcantara v. Nido**, G.R. No. 165133, **19 Apr 2010**, Carpio, J. (a Resolution). Lib #2. Also cited for **P4**.

**How it maps.** Balane fails two of the three Duenas conditions, and on her own affidavit she fails the third as well:
- The seller (de la Fuente) was **not** the registered owner.
- He was **not** in possession. She was, as a tenant.
- Two days before the sale he swore the owner's duplicate was **lost**, the same red flag the Court identified in Vallido.
- On her own affidavit she had **zero contact with the owners** (T43) and relied on the agent's word (T30/T56). These references are per spine §2d, from doc 1089. *[PENDING VERIFICATION: re-quote from the received copy of doc 1089]*
- She paid rent to the owners' side, so she knew who they were. That is Bucton almost exactly.

**What the defense will cite, and our answer.** They will cite **Sarili**, same paragraph:
> "If the proof of capacity consists of a special power of attorney duly notarized, mere inspection of the face of such public document already constitutes sufficient inquiry."

Our answers:
1. Inspecting the face of this SPA reveals both the class limit and the prior-consultation condition. A face reading defeats her rather than protecting her.
2. Yabut (2021) holds that an SPA does not excuse the buyer from inquiring with the registered owners.
3. Sarili itself held the buyers liable.

They may also cite **Tolentino v. Latagan** (Lib #13), where the buyer was upheld as an IPV. The distinction: in Tolentino the buyer dealt with a seller who held title, not with an agent.

---

## P4. Authority to sell land must be written, express, and strictly construed; a sale outside the SPA's object is void

**Rule.** An agent can sell land only under a written SPA that expressly covers the sale. Courts read SPAs strictly, and a sale outside the authority granted is void.

**Statute** (RA 386, verbatim):
- **Art. 1874:** "When a sale of a piece of land or any interest therein is through an agent, the authority of the latter shall be in writing; otherwise, the sale shall be void."
- **Art. 1877:** "An agency couched in general terms comprises only acts of administration, even if the principal should state that he withholds no power…"
- **Art. 1878(5):** SPA required "To enter into any contract by which the ownership of an immovable is transmitted or acquired either gratuitously or for a valuable consideration"
- **Art. 1898:** "If the agent contracts in the name of the principal, exceeding the scope of his authority, and the principal does not ratify the contract, it shall be void if the party with whom the agent contracted is aware of the limits of the powers granted by the principal."

**Verified authorities**
- **Cosmic Lumber v. CA** (above):
  > "For the principal to confer the right upon an agent to sell real estate, a power of attorney must so express the powers of the agent in clear and unmistakable language. When there is any reasonable doubt that the language so used conveys such power, no such construction shall be given the document. … Villamil-Estrada acted without or in obvious authority. The sale ipso jure is consequently void."
- **Bautista-Spille v. NICORP** (above):
  > "It is a general rule that a power of attorney must be strictly construed, and courts will not infer or presume broad powers from deeds which do not sufficiently include property or subject under which the agent is to deal."
- **Yoshizaki** (above):
  > "The special power of attorney mandated by law must be one that expressly mentions a sale or that includes a sale as a necessary ingredient of the authorized act."
- **Alcantara v. Nido** (above):
  > "Without an authority in writing, respondent cannot validly sell the lot to petitioners. Hence, any 'sale' in favor of the petitioners is void."
- **MCIAA v. Unchuan**, G.R. No. 182537, **1 Jun 2016**, Mendoza, J. Lib #12, https://lawphil.net/judjuris/juri2016/jun2016/gr_182537_2016.html
  > "The rule is that a void contract produces no effect either against or in favor of anyone and cannot be ratified. Similarly, laches will not set in against a void transaction, as in this case, where the agent did not have a special power of attorney to dispose of the lots"

**How it maps.** The SPA (doc 416) authorizes a sale only to a defined class and only after consulting the owners.
- Read strictly (Bautista-Spille), a sale to someone outside the class without consultation was never authorized.
- Because the SPA was annotated on the title since 1996 (PD 1529 §52), Balane is charged with knowing its limits. Art. 1898 makes the sale **void** where the buyer "is aware of the limits."

**What the defense will cite, and our answer.**
- **Art. 1403(1)**, verified text: "Those entered into in the name of another person by one who has been given no authority or legal representation, or who has acted beyond his powers" are **unenforceable, unless ratified**, not void. The defense will add Art. 1910 (tacit ratification) and argue the heirs ratified by accepting rent or by long inaction.
- **Art. 1900**: acts "within the terms of the power of attorney, as written" bind the principal as to third persons.
- **Art. 1902**: "Private or secret orders … do not prejudice third persons who have relied upon the power of attorney".

Our answers:
1. **Cosmic Lumber** treated an act outside an existing SPA as "ipso jure … void."
2. **Art. 1898** makes the contract void where the buyer knew the limits, and the annotation charges her with that knowledge.
3. The class limit and consultation condition are **in the written SPA** and annotated on the title. They are neither "secret orders" (Art. 1902) nor outside "the terms … as written" (Art. 1900).
4. Ratification is negated by the 2005 revocation and the 2020 publication.

---

## P5. Art. 1921: revocation and "specified persons"

**Rule.** Art. 1921 protects only the specific people the agent was appointed to deal with. If the buyer was never in that class, revocation does not matter, because the sale was never authorized in the first place.

**Statute** (verbatim):
- **Art. 1921:** "If the agency has been entrusted for the purpose of contracting with specified persons, its revocation shall not prejudice the latter if they were not given notice thereof."
- **Art. 1922:** "If the agent had general powers, revocation of the agency does not prejudice third persons who acted in good faith and without knowledge of the revocation. Notice of the revocation in a newspaper of general circulation is a sufficient warning to third persons."

**Verified authority (closest found)**
- **Central Surety & Insurance Co. v. C.N. Hodges**, G.R. No. L-28633, **30 Mar 1971**, Concepcion, C.J. Lib #69, https://lawphil.net/judjuris/juri1971/mar1971/gr_28633_1971.html
  - The Court applied Art. 1922 because the agent had authority to represent the principal:
    > "not with a particular person, but with the public in general"
  - It held:
    > "Article 1922 applies whenever an agent has general powers, not merely when the principal has published the same"
  - This is the Court recognizing the line between general-public agency (Art. 1922) and particular-person agency (Art. 1921).
- **No Supreme Court decision applying Art. 1921 itself was found.** See the UNVERIFIED list. The Art. 1921 argument therefore rests on the statute's text plus Hodges.

**How it maps.**
- Art. 1921 protects only the **"specified persons,"** here the Llamanzares contract-to-sell holders and part-payers.
- If Balane is outside that class (a tenant paying ₱50/mo rent, per spine §2d), Art. 1921 gives her nothing. The sale to her was never within the agency, so revocation and notice are irrelevant.
- Art. 1922 does not apply either, because de la Fuente held special, class-limited powers, not general ones (Hodges).

**What the defense will cite, and our answer.** They will cite **PD 1529 §64**, quoted verbatim in *Republic v. Ciruelas*, G.R. 239505 (Lib #74):
> "Any instrument revoking such power of attorney shall be registered in like manner."

Their argument: the revocation was never annotated, so as a buyer relying on the title she is protected.

Our answers:
1. §64 registration only matters for a sale **within** the power. Hers was outside it (P4).
2. *Ciruelas* itself treats §64 registration as a notice device, not a condition of validity. It holds that §64 "does not state that the registration of an SPA is a prerequisite to its validity".
3. Risk: the defense will try to place her inside the class through the "third persons in possession" reading. See the Read-first section, item 2.

---

## P6. Tenant estoppel (Art. 1436) and possession not in the concept of owner (Arts. 525, 540)

**Rule.** A lessee cannot deny the lessor's title while in possession. Possession held as a lessee or by the owner's tolerance is not possession as owner, so it can never ripen into ownership.

**Statute** (verbatim):
- **Art. 1436:** "A lessee or a bailee is estopped from asserting title to the thing leased or received, as against the lessor or bailor."
- **Art. 525:** possession is "either in the concept of owner, or in that of the holder of the thing or right to keep or enjoy it, the ownership pertaining to another person."
- **Art. 540:** "Only the possession acquired and enjoyed in the concept of owner can serve as a title for acquiring dominion."

**Verified authorities**
- **VSC Commercial Enterprises v. CA**, G.R. No. 121159, **16 Dec 2002**, Austria-Martinez, J. Lib #75, https://lawphil.net/judjuris/juri2002/dec2002/gr_121159_2002.html
  > "the private respondents, as lessees, who had undisturbed possession for the entire term under the lease, are estopped to deny their landlords title, or to assert a better title not only in themselves, but also in some third person, including the State, while they remain in possession of the leased premises and until they surrender possession to the landlord."
- **Esguerra v. Manantan**, G.R. No. 158328, **23 Feb 2007**, Quisumbing, J. Lib #76, https://lawphil.net/judjuris/juri2007/feb2007/gr_158328_2007.html
  > "mere possession with a juridical title, such as by a usufructuary, a trustee, a lessee, an agent or a pledgee, not being in the concept of an owner, cannot ripen into ownership by acquisitive prescription, unless the juridical relation is first expressly repudiated and such repudiation has been communicated to the other party."
- **Olegario v. Mari**, G.R. No. 147951, **14 Dec 2009**, Del Castillo, J. Lib #79, https://lawphil.net/judjuris/juri2009/dec2009/gr_147951_2009.html
  > "Acts of a possessory character performed by one who holds the property by mere tolerance of the owner are clearly not in the concept of an owner and such possessory acts, no matter how long continued, do not start the running of the period of prescription."
- **NHA v. Manila Seedling Bank Foundation**, G.R. No. 183543, **20 Jun 2016**, Sereno, C.J. Lib #77:
  > "We have ruled that a person whose occupation of realty is by sheer tolerance of the owner is not a possessor in good faith."

**How it maps.** "Occupancy since 1975" gives her no ownership equity. Possession as a rent-payer (spine §2d, T18–19) is not possession in the concept of owner (Arts. 525/540, Esguerra, Olegario), so it cannot be tacked onto her title. The rent receipts are themselves her **actual knowledge** of who the owners were (feeds P3/Bucton).

**What the defense will cite, and our answer.** Calibrate this point carefully. It is not a knockout.
- Tenant estoppel bars a lessee from **denying** the lessor's title.
- Balane does not deny the heirs' title. She claims to have **derived** it from them through their agent.
- VSC also limits the estoppel to "while they remain in possession."

So use Art. 1436 and Arts. 525/540 to (a) kill any ownership-by-possession theory and (b) prove her knowledge of the owners. Do **not** use them as a stand-alone bar to her deed.

---

## P7. Replacement owner's duplicate (PD 1529 §109)

**Rule.** If the owner's duplicate was not actually lost, the court that ordered a replacement had no jurisdiction and the replacement is void. Proof of loss requires a full hearing.

**Statute (§109, verbatim):** "Upon the petition of the registered owner or other person in interest, the court may, after notice and due hearing, direct the issuance of a new duplicate certificate"

**Verified authorities**
- **Strait Times, Inc. v. CA**, G.R. No. 126673, **28 Aug 1998**, Panganiban, J. Lib #70, https://lawphil.net/judjuris/juri1998/aug1998/gr_126673_1998.html
  > "It is judicially settled that a trial court does not acquire jurisdiction over a petition for the issuance of a new owner's duplicate certificate of title, if the original is in fact not lost but is in the possession of an alleged buyer. Corollarily, such reconstituted certificate is itself void once the existence of the original is unquestionably demonstrated. Nonetheless, the nullity of the reconstituted certificate does not by itself settle the issue of ownership"
- **Demetriou v. CA**, G.R. No. 115595, **14 Nov 1994**, Mendoza, J. Lib #72:
  > "if a certificate of title has not been lost but is in fact in the possession of another person, the reconstituted title is void and the court rendering the decision has not acquired jurisdiction. Consequently the decision may be attacked any time."
- **New Durawood v. CA**, G.R. No. 111732, **20 Feb 1996**, Panganiban, J. Lib #71. It reiterates the Serra Serra/Demetriou rule in the same words.
- **Rexlon Realty v. CA**, G.R. No. 128412, **15 Mar 2002**, De Leon, Jr., J. Lib #73:
  > "respondent Davids act of misrepresentation, though not constituting extrinsic fraud, is still an evidence of absence of jurisdiction."
- **Republic v. Ciruelas**, G.R. No. 239505, **17 Feb 2021**, Delos Santos, J. Lib #74:
  > "The second paragraph contemplates the conduct of a full-blown hearing wherein petitioner must prove the fact of loss or theft through preponderant evidence."
  - The same decision holds the registered owner "is the real party-in-interest, who should initiate an action under Section 109".

**How it maps.** The jurisdictional-nullity line applies **only if we can show the original was not in fact lost**, meaning it was held by de la Fuente, Balane or another person.
- The family's position is that it **never** held the duplicate. Patricia's 22 Feb 2023 affidavit (doc 187) says the duplicates stayed with Llamanzares and then Cesar *[PENDING VERIFICATION: re-quote doc 187]*. That is consistent with Cesar holding it, but it does not prove he did.
- Without that proof, use the replacement as **evidence of bad faith**: the loss affidavit sworn two days before the sale, an agent whose authority had been revoked in 2005 acting as petitioner, and no notice to the registered owners. Do not plead the replacement as a stand-alone nullity.

**What the defense will cite, and our answer.**
- **Rexlon**: the CA ruling quoted in Rexlon held that posting the notice in public places met §109's "minimum requirement of notice and hearing." The Supreme Court in Rexlon nonetheless voided the replacement because the original was not lost. So a defense citing that passage is quoting the reversed CA ruling.
- **Strait Times**: nullity of the duplicate "does not by itself settle the issue of ownership."
- **Forum.** Strait Times, Demetriou and Rexlon reached the Supreme Court through **CA annulment petitions** against the RTC order. An MTC is unlikely to annul an RTC Br. 41 order. Treat a Rule 47 petition in the CA as a **separate, sequenced lever**, and flag the blowback risk: losing it would hand the defense a "regular reissuance" finding. *[forum rule itself: see UNVERIFIED]*

---

## P8. Void contracts: imprescriptible, not ratifiable, and not cured by registration

**Rule.** An action to declare a void contract does not prescribe, a void contract cannot be ratified, and registering a void deed does not make it valid.

**Statute** (verbatim):
- **Art. 1410:** "The action or defense for the declaration of the inexistence of a contract does not prescribe."
- **PD 1529 §53** (forged deed or forged duplicate): "any subsequent registration procured by the presentation of a forged duplicate certificate of title, or a forged deed or other instrument, shall be null and void."

**Verified authorities**
- **MCIAA v. Unchuan** (P4). It is the most on-point because it concerns an **agent without an SPA**:
  > "a void contract produces no effect either against or in favor of anyone and cannot be ratified. Similarly, laches will not set in against a void transaction … In fact, Article 1410 of the Civil Code specifically provides that an action to declare the inexistence of a void contract does not prescribe."
- **Heirs of Gonzales v. Spouses Basas**, G.R. No. 206847, **15 Jun 2022**, Hernando, J. Lib #40, https://lawphil.net/judjuris/juri2022/jun2022/gr_206847_2022.html
  > "One can sell only what he owns or is authorized to sell, and the buyer can acquire no more right than what the seller can transfer legally."

  It also quotes *Sabitsana*:
  > "Registration does not vest title; it is merely the evidence of such title. Our land registration laws do not give the holder any better title than what he [or she] actually has."
- **Heirs of Tulauan v. Mateo**, G.R. No. 248974, **7 Sep 2022**, Inting, J. Lib #3. It distinguishes reconveyance based on fraud (10 years) from an action resting on an inexistent contract, which under Art. 1410 "does not prescribe."

**How it maps.** If the 2016 deed is void (P4), TCT 079-2021002126 rests on nothing. Registration in 2021 adds nothing (Gonzales), and neither prescription nor laches runs against the action (Unchuan).

**What the defense will cite, and our answer.**
- **Bucton** itself: "a forged deed can become a source of a valid title when the buyers are in good faith."
- **PD 1529 §53** protects "any innocent holder for value."

Our answer: that protection depends on the IPV status Balane cannot prove (P1–P3). The 10-year reconveyance clock (Tulauan) is a non-issue either way, since registration was in 2021.

---

## P9. Consequences of bad faith that shape the remedy

**Rule.** A builder or possessor in bad faith loses improvements without indemnity, must return the fruits, and can be made to pay exemplary damages and attorney's fees.

**Statute** (verbatim):
- **Art. 449:** "He who builds, plants or sows in bad faith on the land of another, loses what is built, planted or sown without right to indemnity."
- **Art. 450:** owner may demand demolition at the builder's expense "or he may compel the builder or planter to pay the price of the land"
- **Art. 451:** "the landowner is entitled to damages from the builder, planter or sower."
- **Art. 549:** "The possessor in bad faith shall reimburse the fruits received and those which the legitimate possessor could have received…"
- **Art. 2229:** exemplary damages are "imposed, by way of example or correction for the public good"
- **Art. 2232:** "In contracts and quasi-contracts, the court may award exemplary damages if the defendant acted in a wanton, fraudulent, reckless, oppressive, or malevolent manner."
- **Art. 2208:** attorney's fees allowed "(1) When exemplary damages are awarded; (2) When the defendant's act or omission has compelled the plaintiff to litigate … (5) Where the defendant acted in gross and evident bad faith in refusing to satisfy the plaintiff's plainly valid, just and demandable claim; … (11) In any other case where the court deems it just and equitable"

**Verified authorities**
- **Duenas** (En Banc). Its disposition is the template for our prayer:
  - On improvements: "Due to MBTC's bad faith, it forfeits what it has built on 60% of the subject three lots without any right to be paid indemnity."
  - On exemplary damages: "We hold that AFRDI and MBTC's bad faith that resulted in the deprivation of petitioners' right to lawfully use and possess their property for a considerable number of years made them liable for exemplary damages."
  - It also sustained attorney's fees because petitioners "were compelled to litigate."
  - It remanded for necessary expenses only.
- **Sarili v. Lagrosa**: the Court remanded "for the proper application of Article 449 in relation to Articles 450 451 452 and the first paragraph of Article 546" to the house the bad-faith buyers built, and sustained attorney's fees and litigation expenses.
- **NHA v. Manila Seedling Bank** (Lib #77):
  > "Under Article 549 in relation to Articles 546 and 443 of the Civil Code, a possessor in bad faith has a specific obligation to reimburse the legitimate possessor for everything that the former received, and that the latter could have received had its possession not been interrupted."

**How it maps.** A bad-faith finding unlocks four things: forfeiture or removal of improvements built after 2016, accounting for fruits or reasonable compensation, exemplary damages, and attorney's fees. *[Counsel to check the MTC jurisdictional cap on damages under Summary Procedure. Not researched here.]*

**What the defense will cite, and our answer.** They will cite **Art. 448** (builder in good faith: indemnity and right of retention), **Art. 546** (reimbursement of necessary expenses, owed even to a bad-faith possessor; Duenas remanded for this), and **Art. 528** (good faith is lost only from the moment facts show awareness).

Our answer: the P1–P3 record makes her a bad-faith buyer from the outset. At the latest, she was in bad faith from notice before registration (Duenas).

---

## P10. Heightened diligence for public officials or persons with special knowledge

**Rule.** No decision was found that raises the standard of diligence because the buyer is a public official.

**Verified substitute** (use instead of a "public official" rule):
- **Bucton**: the Court weighed the buyer's **personal acquaintance** with the owners, finding it "inconceivable" that the buyers lacked an opportunity to contact them.
- **Bucton's general exception**: a buyer with "actual knowledge of facts and circumstances that would impel a reasonably cautious man to make such inquiry" is not protected.

**How it maps.** Argue her position as a sitting councilor (T59) as a fact bearing on **actual knowledge and opportunity to inquire**, the way Bucton used personal acquaintance. Do not argue it as a separate higher legal standard.

---

## UNVERIFIED: do not cite

| Item | Why it is not verified |
|---|---|
| Any SC decision applying **Art. 1921** "specified persons" | Two searches found none. The argument rests on the statute's text plus *Central Surety v. Hodges*. |
| Any SC decision imposing **heightened diligence on public officials or councilors** as buyers | None found (P10). |
| *Nobleza v. Nuega*, G.R. 193038 (2015) | lawphil fetch missed in all months. Known only as cited inside Duenas. |
| *Sigaya v. Mayuga*; *Serra Serra v. CA* (195 SCRA 482, 1991); *Spouses Sabitsana v. Muertegui*; *Pilapil v. CA*; *Dizon v. CA* | Known only as quoted inside verified decisions. Cite only "as quoted in" the verified case. |
| *Uy v. CA / Spouses De Guzman* (burden of good faith) | G.R. number not confirmed. Not fetched. |
| "Good faith ceases upon service of summons" (Art. 528; *Tacas v. Tobon*, G.R. L-36789, City of Dagupan G.R. L-27876) | Digest-only sources. Not fetched. |
| "Registered owner is always an interested party who must be notified in a §109 petition" | Commentary claim, no decision located. §109 text says only "after notice and due hearing." |
| Forum rule: MTC cannot annul an RTC §109 order; annulment goes to CA (Rule 47); void judgment open to collateral attack | Rules of Court / jurisprudence not fetched today. Demetriou's "may be attacked any time" is verified, but not as to forum. |
| *Domingo v. Reed*, G.R. 157701 (9 Dec 2005) | Fetched, but the holding on the notarized SPA was not confirmed in text. Do not cite yet. |
| *Danon v. Brimo* (1921), *Rallos v. Felix Go Chan* | Not fetched; not needed. |
| *Rufloe v. Burgos*, G.R. 143573 (30 Jan 2009) | Fetched; no holding extracted for these propositions. Do not cite. |

## Human actions (owner / deadline)

1. **Atty. Barandon, before the next MTC setting (14 Oct 2026).** Obtain a legible CTC of the 1992 SPA ¶7 (doc 416 OCR is garbled). Lock the reading of "third persons in possession … contracts to sell … Llamanzares … after prior consultation with us." Prong A depends on it.
2. **Jonathan, this week.** Confirm whether anyone (the heirs' side, Balane, the RD file) can show where the original T-52540 owner's duplicate was in Sept 2016. This decides whether P7 is a nullity argument or only a badge of bad faith.
3. **Counsel.** Decide whether to recast Prong A (negotiate-only) to the class-limit and consultation-condition theory, and whether to drop Art. 1922 publication as an "effect" argument (Read-first, items 1 and 3).
4. **LandTek (librarian).** Re-label Lib #13 (*Tolentino v. Latagan*) in `matter_authorities` as adverse authority.
