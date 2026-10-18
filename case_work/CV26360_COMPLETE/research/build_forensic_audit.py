"""Build FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18.html/.pdf and the ledger CSV from balane_receipts_ledger.py."""
import csv, os, subprocess, datetime as dt, collections
from balane_receipts_ledger import LEDGER

BASE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(BASE)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def D(s):
    p = s.split('-'); return dt.date(int(p[0]), int(p[1]), int(p[2]) if len(p) > 2 else 1)
def P(n): return "₱{:,.0f}".format(n)

rows = [r for r in LEDGER if r[1] != 'S']
REV, DEED = dt.date(2005, 8, 15), dt.date(2016, 9, 29)
total = sum(r[5] for r in rows)
pre = sum(r[5] for r in rows if D(r[3]) <= REV)
mid = sum(r[5] for r in rows if REV < D(r[3]) <= DEED)
post = sum(r[5] for r in rows if D(r[3]) > DEED)
small = [r for r in rows if r[5] <= 2000]
from_nov14 = sum(r[5] for r in rows if D(r[3]) >= dt.date(2014, 11, 17))
y2016_17 = sum(r[5] for r in rows if D(r[3]) >= dt.date(2016, 1, 1))
by_payor = collections.defaultdict(lambda: [0, 0])
for r in rows:
    k = "Gloria (written 'Golly', 'Mrs. Golly', 'Gloria', 'Gloria H.')" if ('Gol' in r[4] or 'Gloria' in r[4]) else r[4]
    by_payor[k][0] += 1; by_payor[k][1] += r[5]
by_year = collections.defaultdict(lambda: [0, 0])
for r in rows:
    by_year[r[3][:4]][0] += 1; by_year[r[3][:4]][1] += r[5]
forms = collections.Counter(r[1] for r in rows)
rentfmt = [r for r in rows if r[1] == 'E' and any(m in r[6] for m in ['2007', '2013', '2014'])]
BIR = 287866.73 + 77478.08
TAXES_2020 = BIR + 27276.00
RPT_2016 = 2193.80 * 3 + 4015.02 + 3613.53

# ---------- CSV ----------
with open(os.path.join(BASE, "balane_receipts_ledger.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["pdf_page", "form", "serial", "date", "payor", "amount_php", "purpose_as_written", "signatory", "auditor_flag"])
    for r in LEDGER: w.writerow(r)

def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

ledger_rows = "\n".join(
    f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td><td>{esc(r[4])}</td><td style='text-align:right'>{r[5]:,}</td><td>{esc(r[6])}</td><td>{r[7]}</td><td>{esc(r[8])}</td></tr>"
    for r in LEDGER)
payor_rows = "\n".join(f"<tr><td>{esc(k)}</td><td style='text-align:right'>{v[0]}</td><td style='text-align:right'>{P(v[1])}</td></tr>" for k, v in sorted(by_payor.items(), key=lambda x: -x[1][1]))
year_rows = "\n".join(f"<tr><td>{y}</td><td style='text-align:right'>{v[0]}</td><td style='text-align:right'>{P(v[1])}</td></tr>" for y, v in sorted(by_year.items()))

HTML = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Forensic audit plan, Balane payments</title>
<style>
 @page {{ size: 8.5in 13in; margin: 0.8in 0.75in 0.8in 0.75in; }}
 body {{ font-family: "Times New Roman", Times, serif; font-size: 12.5pt; line-height: 1.33; color:#000; margin:0; }}
 h1 {{ font-size: 18pt; margin: 0 0 3pt 0; }} .sub {{ font-size: 11pt; color:#222; margin: 0 0 10pt 0; }}
 h2 {{ font-size: 14pt; margin: 14pt 0 5pt 0; border-bottom: 1.2px solid #000; padding-bottom: 2pt; page-break-after: avoid; }}
 h3 {{ font-size: 12.5pt; margin: 9pt 0 4pt 0; page-break-after: avoid; }}
 p {{ margin: 0 0 7pt 0; }} ul, ol {{ margin: 2pt 0 8pt 20pt; padding: 0; }} li {{ margin: 0 0 4pt 0; }}
 table {{ border-collapse: collapse; width: 100%; margin: 3pt 0 9pt 0; }}
 th, td {{ border: 0.7px solid #000; padding: 3pt 5pt; vertical-align: top; font-size: 10.5pt; line-height: 1.25; text-align: left; }}
 th {{ background: #efefef; }} tr {{ page-break-inside: avoid; }}
 .box {{ border: 1.5px solid #000; padding: 8pt 11pt; margin: 4pt 0 10pt 0; }}
 .small {{ font-size: 10.5pt; color:#222; }} .pb {{ page-break-before: always; }}
 table.ledger th, table.ledger td {{ font-size: 8.6pt; padding: 2pt 3pt; line-height: 1.2; }}
</style></head><body>

<h1>Forensic accounting audit plan: the Balane payments</h1>
<p class="sub">Civil Case No. 26-360, Zschoche v. Balane · prepared 18 October 2026 for Jonathan and counsel · internal, not for filing · every figure below is read from a page image and cited to it; nothing is taken from the defense's summaries.</p>

<div class="box">
<p><b>What the money says, in one paragraph.</b> The defendants' own receipts (Def. Exh. 5) show {len(rows)} payments totalling {P(total)} to Cesar de la Fuente's side between October 2003 and February 2017. Their deed recites a price of ₱250,000 "in hand paid" on 29 September 2016. The receipts cannot be squared with that price on any reading: {P(post)} was receipted after the deed, ending in a "Full payment" slip of February 2017; {P(from_nov14)} was receipted from November 2014 onward, which already exceeds the price by {P(from_nov14 - 250000)}; and if the 89 monthly slips of ₱2,000 or less ({P(sum(r[5] for r in small))}) were price instalments, as the defense says, the overpayment grows to {P(total - 250000)}. Not one peso is shown reaching an owner. The money that can be traced went to taxes, penalties and fees in 2016 and 2020 (about {P(TAXES_2020 + RPT_2016)}), most of it penalties for a deed registered four years late. The population is complete enough to audit, and the anomalies in it are the kind a fraud examiner tests first: receipts out of serial order, a price recital contradicted by the payer's own receipts, and a ledger that the defense says exists but has never produced.</p>
</div>

<h2>1. First principles: how a fraud examination of payments is run</h2>
<p>A forensic accountant does not start from the story. The method, in the order it is applied here:</p>
<ol>
<li><b>Predication and hypotheses.</b> State what the money is said to prove, then frame each claim as a hypothesis that evidence can confirm or refute. The defense's claims: a 1980s down payment to Llamanzares (membership in the SPA's class); a ₱250,000 price paid in instalments and completed before the deed; receipts issued in the estate's name (ratification by the owners); and taxes and arrears paid as an owner would. Our hypotheses are in Part 2.</li>
<li><b>Define the population.</b> Identify every record that should exist for the claims (receipts, stubs, ledgers, bank records, tax receipts, the deed) and what portion is actually in hand. Audit the whole population, not a sample: here it is {len(LEDGER)} slips on 33 pages.</li>
<li><b>Provenance and custody.</b> For each record: who created it, who kept it, how it reached the file. A receipt kept by the payer proves payment to the collector, not receipt by the principal.</li>
<li><b>Transcribe and classify.</b> One row per document, read from the image, with the exact words written, the form used, the serial number, the signatory. Classify by purpose (rent, price, tax, other) only on what the slip itself says.</li>
<li><b>Test the documents</b> for existence, occurrence, authorization, completeness, cut-off, classification, valuation and sequence (Part 4). Words against figures; serial numbers against dates; forms against the dates they were printed; signatures against each other.</li>
<li><b>Reconcile to independent sources.</b> The deed's price; the BIR's eCAR values; the Treasurer's tax ledger; the surveyor's receipt. Agreement between the payer's and the payee's records is evidence; disagreement is a finding.</li>
<li><b>Trace source and application.</b> Where the money came from matters less here than where it went: owners, taxes, the agent, his son. Every peso is assigned to a destination or to "unknown."</li>
<li><b>Report findings as facts tied to pages,</b> separate from inferences, with the gaps listed. No adjective substitutes for a reconciliation. Standards drawn on: the fraud-theory approach of the fraud examiners' profession, the auditor's response to fraud risk in the Philippine Standards on Auditing (PSA 240), and the Tax Code rules on official receipts (Appendix B). The first two are stated in substance; the Tax Code sections are quoted from lawphil.</li>
</ol>

<h2>2. Hypotheses to test</h2>
<table>
<tr><th style="width:5%">#</th><th style="width:45%">Hypothesis</th><th>Status after this review of the papers in hand</th></tr>
<tr><td>H1</td><td>The ₱250,000 price was not paid before the deed of 29 September 2016; the recital "in hand paid" was false when signed.</td><td><b>Supported by their own receipts.</b> {P(post)} receipted after the deed; "Full payment" on 14 February 2017 (p. 33).</td></tr>
<tr><td>H2</td><td>No payment reached any registered owner; everything went to Cesar, Salvador, taxes or fees.</td><td><b>Consistent with every record.</b> No owner signature, bank record or remittance exists; Salvador swears the money went to his father, part of it to taxes (S23 to S25). Patricia's denial is first-hand; the rest is to be proved from Cesar's books and bank records (Part 7).</td></tr>
<tr><td>H3</td><td>There was no down payment to Llamanzares in the 1980s; the earliest payment is October 2003, the only "Down payment" is January 2005.</td><td><b>Supported.</b> No receipt, stub or ledger before 2003 (pp. 2 to 3). The defense itself says the 1980s payment has no receipt and sits in a ledger it does not hold (Part 6).</td></tr>
<tr><td>H4</td><td>The ₱2,000 monthly payments were rent, not instalments on a price.</td><td><b>Supported on the face of the documents.</b> Fifteen estate receipts name the month paid for; 89 slips are ₱2,000 or less at monthly intervals for eleven years; no slip shows a balance; the ₱250,000 was separately paid in 2016 to 2017.</td></tr>
<tr><td>H5</td><td>The receipts were not all written when the payments were made.</td><td><b>Indicated, not proved.</b> Serial numbers run against dates in 2014, 2016 and 2017; 80 serials (0137 to 0216) are absent between May and August 2016; one "Start 10k" note in another hand. Needs the stubs and a document examiner (Part 7).</td></tr>
<tr><td>H6</td><td>The "Heirs of Mary W. Keesey Estate" was registered with the BIR as a taxpayer issuing official receipts by the agent, without the owners' knowledge.</td><td><b>Indicated.</b> TIN 160-902-582 and printing authority 451-1998 appear on every estate receipt; the 2020 tax certificate treats the sale under withholding tax rather than capital gains tax. Who registered the TIN is a BIR record (Part 7).</td></tr>
<tr><td>H7</td><td>The true consideration exceeded ₱250,000, or the deed price was set below what was actually paid.</td><td><b>Open.</b> {P(from_nov14)} from November 2014 and {P(y2016_17)} in 2016 to 2017 exceed the price. Salvador's explanation (part went to real property tax and "estate tax") is tested in Part 5; the estate tax had been paid in full in 1991 (Exh. E ¶5).</td></tr>
</table>

<h2>3. The population: what was counted</h2>
<p>Defendants' Exhibit 5 is 33 pages holding {len(LEDGER)} slips: one surveyor's receipt (p. 1) and {len(rows)} receipts issued by Cesar's side. The full ledger is Appendix A; the CSV is in the research folder.</p>
<table>
<tr><th>Measure</th><th style="width:22%">Figure</th><th>Note</th></tr>
<tr><td>Receipts to the collector, total</td><td>{len(rows)} slips, {P(total)}</td><td>Oct 2003 to Feb 2017</td></tr>
<tr><td>Before the revocation (to 15 Aug 2005)</td><td>{P(pre)}</td><td>Includes the only "Down payment," ₱20,000 on 6 Jan 2005 (p. 3)</td></tr>
<tr><td>Revocation to deed (16 Aug 2005 to 29 Sep 2016)</td><td>{P(mid)}</td><td>Eleven years of collections by a revoked agent's son</td></tr>
<tr><td>After the deed (30 Sep 2016 to Feb 2017)</td><td>{P(post)}</td><td>Nine slips; the price recited as already paid</td></tr>
<tr><td>Slips of ₱2,000 or less</td><td>{len(small)} slips, {P(sum(r[5] for r in small))}</td><td>Monthly pattern 2005 to 2014</td></tr>
<tr><td>Estate-form receipts naming the month paid for</td><td>{len(rentfmt)} slips, {P(sum(r[5] for r in rentfmt))}</td><td>"Payment for the month of: March 2007," etc. (pp. 9 to 11, 23 to 27)</td></tr>
<tr><td>Receipted from 17 Nov 2014 onward</td><td>{P(from_nov14)}</td><td>Exceeds the price by {P(from_nov14 - 250000)}</td></tr>
<tr><td>Receipted in 2016 to 2017</td><td>{P(y2016_17)}</td><td>Exceeds the price by {P(y2016_17 - 250000)}</td></tr>
<tr><td>Printed estate receipts (form E)</td><td>{forms['E']} slips</td><td>Serials 0019 to 0228 from a book printed in 1998 (ATP 451-1998)</td></tr>
<tr><td>Generic pads (forms G1 to G4)</td><td>{forms['G1'] + forms['G2'] + forms['G3'] + forms['G4']} slips</td><td>Unnumbered; four different stationery designs</td></tr>
<tr><td>Signed "Von dela Fuente" in writing</td><td>4 slips (2003 to 2005)</td><td>All others carry the stylized "S. dela Fuente" signature</td></tr>
</table>
<h3>By payor</h3>
<table><tr><th>Payor as written</th><th style="width:12%">Slips</th><th style="width:18%">Amount</th></tr>{payor_rows}</table>
<h3>By year</h3>
<table><tr><th>Year</th><th style="width:12%">Slips</th><th style="width:18%">Amount</th></tr>{year_rows}
<tr><td colspan="3" class="small">Gaps with no receipt at all: Sep to Dec 2007; Mar 2010; Sep to Nov 2010; Jan 2011; Aug 2011 to Dec 2011; Feb 2012 to Jun 2013 (17 months); the whole of 2015 and Jan to Feb 2016 (14 months).</td></tr></table>

<h2>4. Document tests and the exceptions found</h2>
<table>
<tr><th style="width:4%">#</th><th style="width:30%">Finding</th><th>Pages and particulars</th><th style="width:18%">Test</th></tr>
<tr><td>E1</td><td>The deed's price recital is contradicted by the payer's own receipts</td><td>Deed of 29 Sep 2016: ₱250,000 "to me in hand paid" (Registry file p. 11; Exh. H). Receipts after that date: 0222 ₱60,000 (30 Sep), 0223 ₱10,000, 0219 ₱50,000, 0218 ₱20,000, 0224 ₱40,000, 0225 ₱30,000, 0227 ₱2,000, 0226 ₱3,000, 0228 "Full payment" (pp. 31 to 33): {P(post)}</td><td>Cut-off</td></tr>
<tr><td>E2</td><td>Receipts exceed the price</td><td>{P(from_nov14)} from 17 Nov 2014; {P(total)} in all. The slips show no running balance; the "Partial / Balance" lines are blank on every form that has them</td><td>Reconciliation</td></tr>
<tr><td>E3</td><td>Serial numbers run against dates</td><td>0122 (30 Jun 2014) before 0121 (31 Jul 2014); 0132 (9 Oct 2014) before 0124, 0128, 0130 (Oct to Dec 2014); 0129 dated 31 Mar 2016 between 0128 (Nov 2014) and 0130 (Dec 2014); 0219 (18 Nov 2016) and 0218 (27 Nov 2016) after 0220 to 0223 (Sep to Oct 2016); 0227 (7 Jan 2017) before 0226 (30 Jan 2017)</td><td>Sequence</td></tr>
<tr><td>E4</td><td>Eighty serials unaccounted for in 2016</td><td>0136 (21 May 2016) is followed by 0217 (7 Aug 2016). A book of 50 leaves in duplicate (the imprint reads "25 Bks. (50x2) 0001-1250") does not skip 80 numbers for one payer; either other payers were receipted from the same book, or the numbers were used elsewhere</td><td>Sequence, completeness</td></tr>
<tr><td>E5</td><td>Two serials far apart used the same day</td><td>0019 and 0061, both 28 Mar 2007 (p. 9); 0019 for ₱5,000 "for lot," 0061 for ₱2,000 "March 2007"</td><td>Sequence</td></tr>
<tr><td>E6</td><td>Words and figures differ on the "Full payment" receipt</td><td>0228 (p. 33): words read "Four Thousand Pesos"; the figure, in a hand that writes 5 as a check mark (compare 0219, 0134), reads 4,000 or 5,000. Either way the slip is the last and smallest payment</td><td>Valuation</td></tr>
<tr><td>E7</td><td>Rent format on the estate's own forms</td><td>"Payment for the month of" filled with a month on 15 slips, 2007 and 2013 to 2014 (pp. 9 to 11, 23 to 27); the printed form itself is a rent form (Occupant's Name; Payment for the month of)</td><td>Classification</td></tr>
<tr><td>E8</td><td>The collector's forms changed five times</td><td>Four generic pad designs (2003 to 2012) and the printed estate book (2007, 2011, 2013 onward); the estate book was in use in March 2007 (0019, 0061) yet generic pads were used again from 2008 to 2012</td><td>Existence, occurrence</td></tr>
<tr><td>E9</td><td>The estate book predates nothing: printed 1998</td><td>Imprint on every estate receipt: "RD64-016-99 25 Bks. (50x2) 0001-1250 · 4C's Press-Daet, CN Auth. No. 451-1998." No genuine receipt from this book can be older than 1998; none in the exhibit is older than 2007. Under Revenue Regulations No. 18-2012, receipt stock printed before 2013 stayed valid only to 30 June 2013 (extended to 30 August 2013 by Revenue Memorandum Circular No. 44-2013) [secondary sources; primary text to be obtained from the BIR]. Thirty-four estate-form receipts in the exhibit (0106 to 0228) are dated after 30 June 2013, on 1998 stock. That bears on the issuer's compliance and on whether a book kept past its validity was kept for one payer; it does not by itself date any entry</td><td>Occurrence</td></tr>
<tr><td>E10</td><td>A marginal note in another hand</td><td>"Start 10k-" above the receipt of 27 Jun 2009 (p. 16), in different ink and hand from the collector's</td><td>Document integrity</td></tr>
<tr><td>E11</td><td>Two signatories, one name</td><td>Four early slips carry the written name "Von dela Fuente"; all others a stylized signature. Salvador swears he issued the receipts (S19 to S22). Whether both are his hand is a question for him and, if needed, an examiner. The only paper appointing Salvador is Cesar's "delegation" of 29 February 2012 (Belen, Doc. 55/Pg. 17/Bk. IX/2012): it post-dates the 15 August 2005 revocation, refers to the 1991 power, carries no owner's signature, and cannot reach the 2003 to 2011 receipts. The point is framed as "no appointment before 2012 and nothing left to delegate after 2005," never as "no power to delegate" (Art. 1892 permits substitution unless prohibited)</td><td>Authorization</td></tr>
<tr><td>E12</td><td>Payor names shift</td><td>Efren (2003 to 2005), "Golly" and "Mrs. Golly" (2005 to 2007, 2011, 2013 to 2016), Princess (2007 to 2012), Ferdinand once (₱8,000, 1 Jun 2008), "Gloria H. Balane" from November 2014. Identity of "Golly" is to be put to the witnesses, not assumed</td><td>Attribution</td></tr>
<tr><td>E13</td><td>The 31 March 2016 coincidence</td><td>0129, ₱40,000 from Gloria, dated 31 Mar 2016 (p. 29). The Treasurer's ledger shows the lot's real property tax for 2012 to 2016 paid in one transaction on 31 Mar 2016 under OR 0033800, {P(RPT_2016)} in all (Registry file p. 13). Salvador swears part of the Balane money went to "amelyar" (S24)</td><td>Source and application</td></tr>
<tr><td>E14</td><td>Taxes paid in 2020 exceed the price</td><td>BIR eCARs (Registry file p. 12): selling price ₱250,000; fair market value ₱2,509,390; zonal ₱1,552,200; amounts paid 15 Jun 2020: ₱287,866.73 and ₱77,478.08 (the capital gains column reads "EXEMPT"). Provincial transfer tax 24 Jun 2020: ₱27,276, of which ₱14,429 is surcharge and interest (p. 21). Total {P(TAXES_2020)}, paid three years and nine months after the deed. The Tax Code requires the return on a sale of real property "within thirty (30) days following each sale or other disposition" (NIRC §51[C][2][b], lawphil). The two certificates carry numbers 201900074035 (19 Jun 2020, T-38838) and 201900675224 (18 Nov 2021, T-52540); both show the same payment date of 15 Jun 2020</td><td>Reconciliation</td></tr>
<tr><td>E16</td><td>Two TINs: the estate's and Cesar's</td><td>Every estate receipt prints TIN 160-902-582 for "Heirs of Mary W. Keesey Estate." Cesar's own TIN on the Deed of Confirmation of 28 Mar 2017 is 160-901-502 (Registry file p. 16, "TIN No. 160-901-502, Atty-in-fact of Owner"). The receipts were issued under a taxpayer registration separate from the agent's own, in the estate's name; who registered it is a BIR record (P4)</td><td>Authorization</td></tr>
<tr><td>E15</td><td>The first eCAR names a dead title</td><td>eCAR 201900074035 of 19 Jun 2020 is issued against T-38838, cancelled in 1999; eCAR 201900675224 of 18 Nov 2021 re-issues against T-52540, same figures, same payment date (p. 12)</td><td>Existence</td></tr>
</table>

<h2>5. Reconciliations</h2>
<h3>R1. Price against receipts</h3>
<table>
<tr><th>Reading of the defense's claim</th><th style="width:22%">Receipts that fit it</th><th>Result</th></tr>
<tr><td>Every receipt was an instalment on the ₱250,000 price (Answer ¶44[f]; Salvador S20)</td><td>{P(total)}</td><td>Overpaid by {P(total - 250000)}. Impossible unless the price was far higher than the deed states</td></tr>
<tr><td>The monthly ₱2,000 slips were rent; the price was paid from November 2014</td><td>{P(from_nov14)}</td><td>Overpaid by {P(from_nov14 - 250000)}. Salvador's tax explanation covers {P(RPT_2016)} of it (E13); the "estate tax" he mentions had been paid in full by 4 Dec 1991 (Exh. E ¶5)</td></tr>
<tr><td>The price was paid only in 2016 to 2017</td><td>{P(y2016_17)}</td><td>Overpaid by {P(y2016_17 - 250000)}, and {P(post)} of it came after the deed said the price was already paid</td></tr>
<tr><td>Gloria's own account: a ₱3,000 down payment in the 1980s, credited by Cesar (S21, S32)</td><td>None</td><td>No receipt, no stub, no ledger in hand; the only "Down payment" is ₱20,000 in 2005 to Salvador</td></tr>
</table>
<h3>R2. Where the money went (source and application)</h3>
<table>
<tr><th>Destination</th><th style="width:20%">Amount</th><th>Evidence</th></tr>
<tr><td>Registered owners (Hoppe, Zschoche, Keesey)</td><td>₱0 shown</td><td>No owner signature, remittance or bank record in any paper; Patricia to testify she received nothing; Salvador: "ibinibigay ko po iyon sa aking ama" (S23)</td></tr>
<tr><td>Real property tax on the lot, 2012 to 2016 arrears</td><td>{P(RPT_2016)}</td><td>Paid 31 Mar 2016, Treasurer's ledger (Registry file p. 13); same day as receipt 0129</td></tr>
<tr><td>Real property tax 2017 to 2021</td><td>about ₱18,000</td><td>Paid each January, ORs listed in the Treasurer's ledger; payor names to be obtained</td></tr>
<tr><td>BIR, 15 Jun 2020</td><td>{P(BIR)}</td><td>eCAR values (p. 12). On a ₱2,509,390 base the basic taxes would be far lower; the balance is surcharge and interest for late payment</td></tr>
<tr><td>Provincial transfer tax, 24 Jun 2020</td><td>₱27,276</td><td>OR 0585696 (p. 21): tax ₱12,547, surcharge ₱3,137, interest ₱11,292, fees ₱300</td></tr>
<tr><td>Surveyor, 29 Dec 2006</td><td>₱3,000</td><td>Villafuerte professional receipt 0460 (p. 1), "lot owned by the Hrs of Worrick Keesey"</td></tr>
<tr><td>Cesar de la Fuente, Salvador, or unknown</td><td>the remainder of {P(total)}</td><td>No accounting exists; the agent's books, if any, are with his estate or with the Agcaoili office (Part 6)</td></tr>
</table>
<p class="small">The Balanes' total outlay on the papers in hand is therefore about {P(total + TAXES_2020)} before registration fees, on a deed that says the lot cost ₱250,000. That is not the arithmetic of a ₱250,000 purchase. It is the arithmetic of eleven years of rent, a 2016 to 2017 price near ₱330,000, and ₱390,000 of taxes and penalties caused by registering a dead agent's deed four years late.</p>

<h2>6. The ledger book they say exists</h2>
<p><b>What the defense says.</b> Gloria's excluded affidavit: the ₱3,000 down payment was paid to Manuel Violeta in three instalments of ₱1,000; "Wala pong ibinigay na resibo noon si Manuel Violeta, pero sinabi niya at nakita namin na itinala niya ang mga bayad sa kaniyang brown columnar book" (S21 to S22); and, "ayon kay Cesar M. de la Fuente," the book was turned over to Cesar and later to the Agcaoili Law Office (S24). The Answer pleads the same payment (¶40) without the book.</p>
<p><b>What follows for the audit.</b></p>
<ul>
<li><b>It is the only record offered for the fact that puts Gloria inside the SPA's class.</b> Without it, the class claim rests on her word about events forty years ago, relayed through a dead man's statement about where the book went.</li>
<li><b>If the book exists, it is a rent ledger.</b> A columnar book kept by the administrator's collector records what tenants paid. The entry the defense needs would have to say "down payment," not "rent." Whoever holds it, its entries for the Balanes are either absent or are the strongest proof that they paid rent.</li>
<li><b>Its stated custody runs to the plaintiff's own former counsel.</b> That is dangerous in both directions. If it is at the Agcaoili office and shows rent, it ends the class claim. If it cannot be found, the defense will argue suppression. The audit therefore locates it first, before anyone asks for it in court.</li>
<li><b>Cesar's own books are the second ledger.</b> Salvador says he handed every payment to his father (S23). A collector who issued numbered official receipts in a registered taxpayer's name had a cash book or at least the duplicate leaves. The Tax Code requires receipts "prepared at least in duplicate" (Appendix B). The duplicates, the unused leaves and the other 25 booklets of the 1998 printing are the audit trail of every peso and of every other buyer.</li>
</ul>
<h3>6A. If a ledger surfaces: what it must be</h3>
<ul>
<li><b>Llamanzares-era, in Violeta's hand.</b> To help the defense it must show a down payment to Llamanzares before Cesar's SPA of 16 March 1992, because that is what paragraph 7 requires ("down-payments or partial payments therefor to the latter"). Entries in any later hand, or any later ink or paper, are not that.</li>
<li><b>Salvador cannot vouch for it.</b> He had no knowledge of the property in the Llamanzares years; his own affidavit dates his first contact to "noong bandang 1992," when he and his father went to collect Llamanzares's papers (S14 to S15). He can speak only to what was handed over then, and to where it went.</li>
<li><b>Custody is the open question.</b> Gloria's account is that the book went to Cesar and then to the Agcaoili office (S24). P1 asks the Agcaoili office; on cross, Salvador is asked what papers were collected from Llamanzares in 1992, whether a columnar book was among them, and where it is now.</li>
</ul>
<p><b>Procedures:</b> P1, P2 and P8 below.</p>

<h2>7. Procedures, in the order they are run</h2>
<p class="small">Each procedure names the record, where it is, who asks, the alert risk to the defense, and the hypothesis it serves. "Quiet" means obtained now in Jonathan's own name or through the family, with no court filing; "rebuttal" means by subpoena after the defense rests, as the trap route requires.</p>
<table>
<tr><th style="width:4%">#</th><th style="width:30%">Procedure</th><th style="width:22%">Source and who asks</th><th style="width:8%">Alert</th><th>Serves</th></tr>
<tr><td>P1</td><td>Find the "brown columnar book." Ask Atty. Agcaoili-Orena's office, in writing, whether any ledger, cash book or papers of Manuel Violeta or Cesar de la Fuente were ever turned over to it, and what they show for the Balanes</td><td>Agcaoili &amp; Associates; Patricia and Jonathan</td><td>None</td><td>H3, H4; closes the suppression argument before it is made</td></tr>
<tr><td>P2</td><td>Fix Violeta and Llamanzares: dates of death (PSA), years of service, and any family member holding records</td><td>PSA; the family; Mercedes civil registrar</td><td>None</td><td>H3; anchors against any late "ledger" witness</td></tr>
<tr><td>P3</td><td>Treasurer's official receipts for the lot's real property tax, 2012 to 2021: the payor named on each OR (0033800 of 31 Mar 2016; 0032388; 8672529; 0532865; 0046725; 0048923)</td><td>Municipal Treasurer, Mercedes; Jonathan as owner's attorney-in-fact (the Treasurer's office is an ARTA respondent's office)</td><td>Moderate; defer to rebuttal if the office is hostile</td><td>H2, H7; tests Salvador's "amelyar" explanation and Answer ¶44(i)</td></tr>
<tr><td>P4</td><td>BIR registration of TIN 160-902-582: who registered "Heirs of Mary W. Keesey Estate," when, under what authority; the Authority to Print 451-1998 and the printer's logbook at 4C's Press, Daet</td><td>BIR RDO 64, Talisay; 4C's Press. Rebuttal subpoena; the printer's logbook may be asked for quietly</td><td>Low (printer); subpoena (BIR)</td><td>H6; shows the agent registered the estate as a business without the owners</td></tr>
<tr><td>P5</td><td>BIR dockets of the two eCARs: who filed and paid on 15 Jun 2020, on what forms, the computation (basic tax, surcharge, interest), and why the first was issued against T-38838</td><td>BIR RDO 64; rebuttal subpoena</td><td>Subpoena</td><td>H2, E14, E15; fixes who paid {P(BIR)} and on what instructions</td></tr>
<tr><td>P6</td><td>Provincial Treasurer OR 0585696 and its computation sheet; who presented the deed on 24 Jun 2020</td><td>Provincial Treasurer, Daet; quiet request or rebuttal subpoena</td><td>Low</td><td>H2; the processor's identity (Elevado)</td></tr>
<tr><td>P7</td><td>Asis notarial register for Doc. 304/Pg. 61/Bk. CXVI/2016 (the deed) and Doc. 115/Bk. CXXII/2017 (the confirmation): the price and parties as recorded, and who appeared</td><td>Clerk of Court, RTC Daet, notarial section; quiet certified copy</td><td>Low</td><td>H1, H7; whether the register records the same price</td></tr>
<tr><td>P8</td><td>Demand on cross, and by rebuttal subpoena to Salvador, for the duplicate leaves of every receipt in Exh. 5, the unused leaves, the other booklets of the 1998 printing, and any cash book of his father</td><td>Salvador dela Fuente; Cesar's heirs</td><td>Rebuttal only</td><td>H2, H5; the audit trail of every peso and of the other buyers</td></tr>
<tr><td>P9</td><td>Originals of Exh. 5 for examination: ink, pen pressure, form stock, staple holes, and whether the serial-order anomalies are consistent with later writing-up. Engage a questioned-document examiner only after the originals are produced. <b>Timing decision for counsel:</b> the second chair's ink-dating plan notes that solvent-loss ink-age methods read only within roughly six to twenty-four months of writing, so if any slip was written recently the window closes during 2027; an early motion for leave to sample conflicts with holding the records for rebuttal. Static comparison of inks and hands does not expire the same way. Counsel decides which; nothing is requested without that decision</td><td>Court, on production of the originals (JA Rule requires the originals be brought for comparison)</td><td>Defense stage, or earlier by counsel's decision</td><td>H5</td></tr>
<tr><td>P10</td><td>Owners' side: written confirmation from Patricia (and if possible her sisters) that no remittance, cheque, deposit or accounting was ever received from Cesar or Salvador from 1992 to 2017; any bank record of the heirs for the period</td><td>Patricia; the family's bank</td><td>None</td><td>H2</td></tr>
<tr><td>P11</td><td>The Agcaoili office's file: any accounting, remittance or correspondence from Cesar between 1992 and 2019 (its 2019 letter says every post-2005 act was unauthorized)</td><td>Agcaoili &amp; Associates</td><td>None</td><td>H2, H3</td></tr>
<tr><td>P12</td><td>Spec. Proc. 2156 record (Cesar's October 2016 petition): what he swore about the land, its income and his custody, three weeks after the deed</td><td>RTC Branch 41; quiet certified copy</td><td>Low</td><td>H1, H2</td></tr>
<tr><td>P13</td><td>The surveyor's file: Villafuerte's receipt 0460 and job record for the 2006 "subdivision survey"; whether a plan was ever filed from it</td><td>Villafuerte Eng'g &amp; Surveying Office, Daet; quiet</td><td>Low</td><td>Partition timeline; "owned by the Heirs" in 2006</td></tr>
<tr><td>P14</td><td>Room rentals since 22 Aug 2025: on cross of Princess and Erwin, the number of rooms, the monthly rate, who collects. Gloria's own affidavit concedes "limited and intermittent" room rentals (purpose 8)</td><td>Defense witnesses on cross</td><td>Defense stage</td><td>Damages figure (Art. 2234)</td></tr>
<tr><td>P15</td><td>Reconstruct the collector's full customer list from serial gaps: every missing number between 0019 and 0228 was issued to someone. Cross Salvador on who, and compare with Cesar's 1993 list of buyers on T-4497 (Annex AA)</td><td>Ledger (Appendix A); Salvador on cross</td><td>Defense stage</td><td>H3, H5; the class as it actually operated</td></tr>
</table>

<h2>8. What this gives counsel</h2>
<ul>
<li><b>On Salvador's cross,</b> the receipts prove themselves: price after the deed (E1); more than the price (E2); numbers out of order (E3, E4); his own hand on a ₱20,000 "Down payment" in 2005 and nothing earlier (H3); the tax explanation against the SPA's own recital that estate taxes were paid in 1991 (R1).</li>
<li><b>Against the class claim,</b> the only record of a 1980s payment is a ledger the defense does not hold, said by a dead man to be with the plaintiff's former counsel. P1 settles where it is and what it says before trial.</li>
<li><b>Against ratification,</b> no owner touched a peso; the "estate" name on the forms is the agent's own BIR registration (P4).</li>
<li><b>Against good faith,</b> a buyer who paid {P(TAXES_2020)} in taxes and penalties in 2020, mostly for lateness, on a deed from a man dead three years, with the first tax certificate issued against a title cancelled in 1999 (E14, E15).</li>
<li><b>For the damages figure,</b> Gloria's affidavit admits room rentals; the number and rate come from cross (P14).</li>
</ul>

<h2>9. Corrections and verification flags</h2>
<ul>
<li><b>Receipt 0219 is ₱50,000</b> ("Fifty Thousand Pesos," p. 32). An earlier note in this file claimed it had been verified at ₱40,000; that was wrong. The Track A table was right.</li>
<li><b>Receipt 0228:</b> words "Four Thousand Pesos"; figure ambiguous (4 or 5). Recorded at ₱4,000; the difference changes no conclusion.</li>
<li>Day digits read from the images and open to a second reading: 2003-10-25 (could be 20); 2008-01-25; 2008-10-17; 2012-01-01; 2014-12-04; 2016-03-07; 2016-12-14; 2017-02-14. None affects a finding.</li>
<li><b>Reconciliation with the second chair's examination record</b> (CASE_FILE/PARTIES/RECEIPTS_EXAMINATION_2026-10-18): same 111 slips. Its total is ₱602,950 against this ledger's ₱602,750; the whole difference is receipt 0134 (10 Apr 2016), read there as ₱700 and here as ₱500: the figure is "√00" in a hand whose 5 is written as a check mark (compare 0219, words "Fifty," figure "√0,000"). Day digits re-read at 300 dpi and confirmed as in this ledger: 30 May 2005, 4 Apr 2005, 2 Aug 2005, 3 Sep 2006, 17 Feb 2007, 4 Aug 2007, 30 Apr 2009, 30 Dec 2010, 7 Mar 2016. Still open to a second reading: 12 May 2005, 27 May 2006, 4 Dec 2014, 14 Feb 2017. The surveyor's receipt is No. 0460 (read 0160 there). None of these changes a finding.</li>
<li>The BIR column headings on the eCAR (p. 12) place "EXEMPT" under capital gains tax and the ₱287,866.73 under the withholding column; the reading is from the certified copy and should be confirmed from the BIR docket (P5).</li>
<li>The fraud examination method and PSA 240 are stated in substance; the Tax Code sections are quoted (Appendix B); the Rules on Evidence provisions on originals, business entries and private documents were not fetched this session and are to be quoted by counsel.</li>
</ul>

<h2 class="pb">Appendix A. The ledger, receipt by receipt (Def. Exh. 5)</h2>
<p class="small">Form codes: S surveyor's receipt; G1 to G4 generic pads (four designs); E printed "Heirs of Mary W. Keesey Estate" official receipt. Signatory: VON = "Von dela Fuente" written out; SDF = stylized signature; SURV = surveyor. Purpose is the handwritten line as read; [blank] where empty.</p>
<table class="ledger">
<tr><th>Pg</th><th>Form</th><th>Serial</th><th>Date</th><th>Payor as written</th><th>Amount</th><th>Purpose as written</th><th>Sig.</th><th>Auditor's note</th></tr>
{ledger_rows}
<tr><th colspan="5">Total to the collector ({len(rows)} slips; the surveyor's ₱3,000 excluded)</th><th style="text-align:right">{total:,}</th><th colspan="3"></th></tr>
</table>

<h2 class="pb">Appendix B. Law relied on</h2>
<p><b>National Internal Revenue Code (R.A. 8424), Section 237</b>, as published on lawphil: "All persons subject to an internal revenue tax shall, for each sale or transfer of merchandise or for services rendered valued at Twenty-five pesos (P25.00) or more, issue duly registered receipts or sales or commercial invoices, prepared at least in duplicate, showing the date of transaction, quantity, unit cost and description of merchandise or nature of service: Provided, however, That in the case of sales, receipts or transfers in the amount of One hundred pesos (P100.00) or more, or regardless of the amount, where the sale or transfer is made by a person liable to value-added tax to another person also liable to value-added tax; or where the receipt is issued to cover payment made as rentals, commissions, compensations or fees, receipts or invoices shall be issued which shall show the name, business style, if any, and address of the purchaser, customer or client …"</p>
<p><b>Section 238:</b> "All persons who are engaged in business shall secure from the Bureau of Internal Revenue an authority to print receipts or sales or commercial invoices before a printer can print the same. No authority to print receipts or sales or commercial invoices shall be granted unless the receipts or invoices to be printed are serially numbered and shall show, among other things, the name, business style, Taxpayer Identification Number (TIN) and business address of the person or entity to use the same … All persons who print receipt or sales or commercial invoices shall maintain a logbook/register of taxpayers who availed of their printing services."</p>
<p class="small">Bearing: the estate receipts are registered official receipts of a taxpayer "engaged in business," printed under an authority obtained in 1998 and serially numbered; their duplicates must exist; the printer must have a logbook naming who ordered them. All of that is independent evidence the defense has not produced.</p>
<p><b><i>Culaba v. Court of Appeals</i>, G.R. No. 125862, 15 April 2004</b> (read on lawphil): payments made to a man in the creditor's uniform who "issued SMC liquidation receipts which looked genuine" did not discharge the debt, because the payer "did not ascertain the identity and authority of the said supervisor"; "A person dealing with an agent is put upon inquiry and must discover upon his peril the authority of the agent"; "Persons dealing with an assumed agent are bound at their peril to ascertain not only the fact of agency but also the nature and extent" of the authority. Bearing: receipts from a collector whose authority the payer never verified are not payment to the principal, however genuine the forms look.</p>
<p><b>Exhibit E (the 1992 SPA), paragraph 5:</b> the estate and transfer taxes due on the estate "has been paid in full to the Bureau of Internal Revenue … on December 4, 1991." Salvador's "estate tax" explanation for part of the Balane money (S24) is tested against this recital.</p>
<p><b>Civil Code, Article 2234</b> and the damages predicate are as set out in the memorandum pack; not repeated here.</p>
</body></html>"""


from html2md import html_to_md

md_path = os.path.join(ROOT, "AUDIT_BALANE_PAYMENTS_2026-10-18.md")
open(md_path, "w").write("<!-- Generated by research/build_forensic_audit.py from research/balane_receipts_ledger.py; edit those, not this file. PDF/HTML: FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18 -->\n" + html_to_md(HTML))
html_path = os.path.join(ROOT, "FORENSIC_AUDIT_BALANE_PAYMENTS_2026-10-18.html")
open(html_path, "w").write(HTML)
pdf_path = html_path.replace(".html", ".pdf")
subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", "file://" + html_path], check=True, capture_output=True)
import fitz
d = fitz.open(pdf_path)
print(d.page_count, "pp", {(round(p.rect.width), round(p.rect.height)) for p in d}, "| total", total, "| pre/mid/post", pre, mid, post, "| from Nov 2014", from_nov14, "| 2016-17", y2016_17, "| taxes 2020", round(TAXES_2020, 2), "| RPT 2016", round(RPT_2016, 2))
