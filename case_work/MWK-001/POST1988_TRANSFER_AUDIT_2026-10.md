# MWK Post-1988 Transfer Audit: Barangays 1, 3 and 5, Mercedes (2026-10-05)

> INTERNAL WORKING FILE. Nothing here has been sent or filed. No database rows were changed.
> Companion data: `POST1988_TRANSFER_AUDIT_2026-10.csv` (48 rows, one per transfer, all columns).
> Rule tested: Mary Worrick Keesey died 17 Mar 1988. After that date, nothing could leave her
> declarations or titles without (a) a deed she or her agent signed while she was alive, or (b) a deed
> signed by the heirs or an agent they authorized to sell.
> Provenance: **verified** = a quoted line from the source document, or a `*_safe` view row.
> **inferred_strong** = read from an Assessor certification or an OCR'd RD copy; the signer or date is
> not yet confirmed on the original. Everything not marked verified is **PENDING VERIFICATION**.

## 1. Answer

I found **48 transfers recorded on or after 17 Mar 1988**: 25 in Barangay 1, 11 in Barangay 3 and 8 in
Barangay 5. Another 4 appear only as T-4497 annotations with no barangay stated.

| Bucket | Count | Rows |
|---|---|---|
| **A**: no instrument | **2** | PNP Lot 402-B (2018) and the Municipality's Lot 402-A (2022) |
| **B**: instrument signed without authority | **4** | Balane, Hansol, Elsa O. Iligan (2017/2018), Victa's 310 sqm enlargement (2007) |
| **U**: cannot be decided yet | **32** | the signer and/or the deed date is not in the corpus |
| **D**: untitled ground plus long possession | **0** | every private transfer audited sits on titled land (T-4497 or a derivative). Rows B5-07 and B5-08 carry a D-risk flag. |
| **C**: authorized instrument | **10** | lifetime deeds (1975–1987) that were only *recorded* after 1988, plus the 1980 road-lot donation |

**Bottom line:** there are 6 actionable rows today (A ×2, B ×4). By roll or deed year, 25 of the 32 U
rows fall inside the window when de la Fuente's 1992 SPA was in force (Mar 1992 to Aug 2005). For those,
once the signer is confirmed as de la Fuente, one fact decides the bucket: did the buyer hold a
Llamanzares contract to sell or a down-payment receipt? No such contract or roster exists in the corpus.
The other 7 U rows are six roll entries from 1988 to 1991, plus Valledor. For the 1989–1991 deeds, any
agent who signed between 17 Mar 1988 and Aug 1991 had no heirs' authority at all. The 1991 SPA (docs
82/35) does not contain one sell, sale, convey or donate term.

**Authority instruments, as checked on the text:**

| Instrument | Sale power? |
|---|---|
| 1991 Agcaoili SPA (docs 82/35) | **None.** Its powers are control and supervision, taxes, collection and representation. |
| 1992 Munda SPA (doc 246, and docs 329/416) | Sale only of **T-4497 Lot 2** (139,132 sqm), only to Llamanzares contract-to-sell holders, and only "after prior consultation". |
| 2005 Buenaventura SPA (docs 281/292) | **None.** "Sale"/"sold" appear only in the power to *sue over* unauthorized sales (OCR keyword check). |
| 2012 "Von" SPA (doc 38) | This is **not an heirs' instrument.** Cesar M. de la Fuente himself delegated his *management* powers to his son Salvador O. dela Fuente (20 Feb 2012, NP Elaine Gay R. Belen, Doc 59 s.2012). No sale power is recited. It was made 7 years after his own authority was revoked. |

## 2. Tables by bucket

### A: no instrument (remedy: Assessor's administrative correction)

| Row | Brgy | Declaration | Year | Holder | sqm | Basis stated | Docs |
|---|---|---|---|---|---|---|---|
| B5-07 | 5 | ARP 005-00209 → **005-00220** | 2018 | Philippine National Police | 800 | revised "to cite OCT 2018000090" (special patent) | 150, 1205, 151 |
| B5-08 | 5 | ARP 005-00054 → **005-00236** (Lot 402-A) | 2022 | Municipality of Mercedes | 973 | "based on certification issued by DENR" | 152 |

D-risk flag: both lines descend from the Municipality's 1954 TD 1699 (≈72 years). If Lot 402 is held as
untitled ground, possession is the Municipality's argument. This is already covered by the DENR/Assessor
packet (deploy_1103/1104).

### B: instrument without authority (remedy: court declaration of nullity, then cancellation)

| Row | Transferee | sqm / title | Instrument | Signer → authority | Why no authority | Docs |
|---|---|---|---|---|---|---|
| B1-16 | Gloria H. Balane | 2,587 / 079-2021002126 | DOS 29 Sep 2016, Doc 304, NP Asis | de la Fuente → 1992 SPA | signed 11 years after the 15 Aug 2005 revocation; buyer outside the contract-to-sell class | 233, 1242, safe id 36 |
| B1-12 | Rosalina M. Hansol | 494 / T-50192 | DOS, P74,100 (date line blank) | de la Fuente → **1991** Agcaoili SPA | that SPA has no power to sell | 413, 82, 412 |
| B1-17 | Elsa O. Iligan | 372 / 079-2018001329 | "SALE EXECUTED BY CESAR M. DE LA FUENTE, IN FAVOR OF ELSA O. ILIGAN" (Doc 093 s.2017, NP Belen), dated 22 Apr 2017 | de la Fuente → 1992 SPA | 12 years after revocation; registered 2 Aug 2018, after his death; resold 2022 | 46, 323, 322 |
| B1-22 | Alberto Victa (+310 sqm) | 700 → 1,010 / T-47657 | Affidavit of Confirmation, June 2007: "enlargement of 310 sq. m." | de la Fuente → 1992 SPA | made after the 2005 revocation | 590 |

### U: undetermined (the record that decides each row)

| Rows | Who (sqm, roll year) | What we have | What decides it |
|---|---|---|---|
| B5-02..06 | Rafer 315 ('89), Tuibuen 182 ('90), Roxas 182 ('90; TD jurat 1989), Sabino 820 ('93), Olivar 284 ('98) | ledger memo "DOS" only (doc 115); no T-4497 annotation found | the deeds: date and signer. Lifetime = C. 1988–Aug 1991 by any agent = B. 1992–2005 = the contract-to-sell test |
| B3-01..02 | Bares 215 ('88), Sps. Cruz 185 ('89) | roll memo only (doc 1241) | the deed date: before or after 17 Mar 1988 |
| B3-03, -04, -06..-09 | Onrubia 163 ('91) & 34 ('99), Bana 279 ('95), Bernardo 116 ('99), Cadag 376 ('99), Tenorio 820 ('01) | roll memo with notary and series; "SPA submitted" on three | deed signer, plus whether the buyer held a Llamanzares contract to sell |
| B1-02, -05, -06, -19, -20 | Leaño 1,384, Tychingco 265, Pascual 629, Bayani 86, Santiago 2,879 | registered DOS (1992–93) + de la Fuente "confirmations"; RD says the files were lost (doc 353) | DOS signer and the contract-to-sell test |
| B1-08, -13, -18, -21, -23 | Ramirez 121, Vela 1,344, Pascual 432, Victa 700, Nacasa 1,572 | **de la Fuente deeds in hand** (doc 590), all before 2005 | **contract-to-sell test only.** If no Llamanzares contract, these move to B. |
| B1-15 | Era 598 | DOS 28 Apr 2005 (3.5 months before revocation) | signer, and the contract-to-sell test |
| B1-03, -04, -07, -09..-11, -14; T-04 | Leaño 953 & 234, Pascual 334, Ocan 803, Cereza 134 & 88, Mabeza 298, Valledor | deduction remark or title only | everything: the deed itself |

### C: authorized (stands)

| Row | Transferee | sqm | Lifetime instrument | Recorded after 1988 as | Docs |
|---|---|---|---|---|---|
| B5-01 | Sps. Blancada | 222 | Deed of Final Sale 21 Mar 1987 (TD jurat 26 Mar 1987) | roll 1989 | 115, 39 |
| B3-05 | Jaime C. King Jr. | 1,113→906 | DOS s.1978 (NP Alegre) | roll 1995 | 1241 |
| B3-10 | Cristina Capistrano | 557 | DOS 15 Jan 1979 | title 2003, roll 2018 | 21, 1241 |
| B1-01 | Elsa Iligan | 300 | DOS s.1981 (first presented 1986) | roll 1989; T-36668 in 1995 | 39, 21, 1242 |
| B1-24 | Elena Vergara | 339 | DOS 8 Apr 1981 | registered 1990; T-33350 in 1993 | 39, 21 |
| T-01 / T-02 | Pascual Sr. & Jr. / Navarro | 3,325 / 310 | DOS 14 Nov 1978 | registered 1992 | 39 |
| T-03 | Rogelio Yasis | 223 | DOS 1975 + Llamanzares confirmation | title 2010 | 39, 590, 27 |
| B1-25, B3-11 | Municipality (road lots) | 7,132 + 2,392 | Deed of Donation 14 Apr 1980 | roll (undated, 1985–93); Road Lot 2 on T-32917 in 1995 | 301, 21 |

Every C row except the road lots is **inferred_strong**: the annotation does not name the signer. Confirm
that MWK or her agent Llamanzares (1976 POA, 1982 GPA) signed.

## 3. Records that decide the U rows

1. **Municipal Assessor (Gemma P. Abla):**
   - the transfer folders, meaning the deeds and SPAs "submitted", for Brgy 5 TDs 005-0129, -0142,
     -0143, the Sabino TD, and -0188;
   - for Brgy 3 TDs 003-0093, -0094-A, -0220-A, -0239, -0252, -0256, -0261 and -0247;
   - for Brgy 1 TDs 001-0055, -00066, -00229, -0233, -00208, -00231/-00232 and every "sold to"
     remark-only deduction;
   - a **certified Brgy 5 history**, since doc 115 is a handwritten transcription;
   - the basis documents for ARP 005-00220 and 005-00236.
2. **Provincial Assessor:** the RPA Form 1 originals for the Brgy 5 1989–1998 TDs. The owner's jurat
   and the "transferred by virtue of" memo date each deed (compare TD 005-0123).
3. **RD Camarines Norte:**
   - certified deeds and primary-entry-book pages for each PE cited in the CSV;
   - a name search on T-4497 / T-4501 for Rafer, Tuibuen, Roxas, Sabino and Olivar;
   - whether a title issued for Victa's 1,010 sqm, and whether Nacasa's sale was registered;
   - the root deeds for Valledor (T-51640), Cereza (T-51639), Mabeza (T-53602) and Ocan (T-46038).
4. **Notarial archives (RTC Daet, Office of the Clerk of Court):** where the RD files were lost (doc
   353), the notarial registers give the vendor and the capacity. Request the books of:
   - E. B. de Jesus, 1992–2000;
   - J. S. Subia, 1992;
   - A. O. Yanto, 1994, 2000 and 2004;
   - A. RC de Jesus, 2005;
   - J. R. Alegre, 1978;
   - A. Mago, 1979 and 1981;
   - E. G. R. Belen, 2017.
5. **Heirs / estate file:** any Llamanzares contract-to-sell or down-payment roster, and any record of
   the "prior consultation" the 1992 SPA requires. Together with the signer, this item decides the 25 U rows in the 1992–2005 window.

## 4. Data-quality notes

1. **Blancada:**
   - the ledger records the transfer in 1989;
   - the TD jurat is 26 Mar 1987;
   - the RD annotation reads "21 Mar 1967 / presented 2 Apr 1967", which is OCR; it falls between 1983
     and 1988 entries, so read it as 1987.
   This was a lifetime sale entered late. Separately, the Blancadas **quitclaimed the 222 sqm back to MWK
   on 4 Aug 1993** (PE-170478), but no roll entry returns it to the heirs.
2. **TD 4817 (8,951.22 sqm, Municipality) is pre-1988 (1966).** The Brgy 1 history remark reads
   "Declared by virtue of Deed of Donation executed by Mary Worrick Keesey and Manuel Garido, per Doc. No.
   23 Page No. 69", and the 1953 deed is doc 279. This **corrects** the reconciliation's "none recorded"
   (BRGY5_TAXDEC_RECONCILIATION §4). It belongs in pre-1988 context, not this audit.
3. **Iligan 372:** the roll says the deed was notarized by Belen and "dated July 30, 2018". The RD
   annotation says Doc 093 s.2017, **22 Apr 2017**.
4. **Balane roll remark:** it conflates the 2016 deed, the 2017 series and the 18 Nov 2021 CAR date.
   Five deed versions exist; doc 233 is the operative one.
5. **Hansol date:** doc 413's `doc_date` (22 Aug 1991) is the SPA's date. The deed's date line is blank.
6. **Brgy 1 roll years are effectivity years of the heirs' remaining-portion TD, not sale dates.**
   Several are out of sequence: Victa "1990" after 2003 entries, and 001-00244/-00245 "1990". Nine sales
   appear only as deduction remarks, with no buyer TD.
7. **Area conflicts:**
   - Iligan: 300 (roll) / 390 (T-4497 annotation, "Lisa C. Itilsan") / 500 (titles table, T-36668);
   - Leaño: 1,384 / 1,394 / 1,295;
   - King: 1,113 corrected to 906.
8. **Road Lot 5 (1,266 sqm)** is declared in both the Brgy 1 (001-00050) and Brgy 3 (003-0089) histories.
9. **Roxas vs "Ronas":** the ledger and TD 005-0143 differ on the name. The TD cancels 005-0130; it
   carries an owner's jurat from 1989 and names MWK as the previous owner. Sabino has no TD number on the
   ledger.
10. **Brgy 5 is titled:** the Blancada parcel on the same Moreno St strip is annotated on T-4497
    ("tituladong lupain"). The Brgy 5 TDs still leave the title line blank, and TD 1693 cites T-111. Treat
    the strip as T-4497 land, PENDING confirmation, so prescription (Arts. 1134/1137) does not run (PD 1529
    §47).
11. **Not out-of-MWK transfers:**
    - Gaulit (TCT 2010000694) bought from Yasis;
    - Valledor's 2012 entries are his own heirs' settlement and sale;
    - 001-0065 (1993) is the heirs' own extrajudicial settlement "upon representation of Mr. de la
      Fuente".
12. **Watch list (segregations still in MWK's name, which may signal pending sales):**
    - 264 sqm "Gloriosa Valencia" (MATC 2019-0503);
    - 126 sqm Brgy 3 "per SPA and demand letter" (2013);
    - several PATC/MATC segregations between 2013 and 2017.
13. **Client separation:** the `titles` table mixes Inocalla titles (doc 634) into MWK rows. They were
    ignored. Doc 525 was ignored. T-30683 and T-4494 were excluded.

### Pre-1988 context (not audited)

| Year | Record | Transferee | sqm | Stated basis |
|---|---|---|---|---|
| 1954 | TD 1699 (Brgy 5) | Municipality | 3,675.72 | "Deed of Donation"; only an unsigned retyped copy has been produced |
| 1966 | TD 4817 → today's ARP 005-00045 | Municipality | 8,951.22 | 1953 Deed of Donation, MWK + Manuel Garrido (doc 279) |
| 1961–1985 | Brgy 5 TDs | Pasquin 720, Montemayor 570, Aguilar 379, Bautista 409 | | DOS |
| 1975–1983 | Brgy 1 TDs | Ferrer, Sision ×2, Bernal, Yao, Encinas, Zaballero, Abiog, Echinique, Waje, Espinosa, Casyao, Aboga, Vergara (roll) | | DOS (1975, NP Mago) |
| 1983–1987 | Brgy 3 TDs | de Leon 98, H. Bernardo 204, Rodriguez 272 | | DOS |
