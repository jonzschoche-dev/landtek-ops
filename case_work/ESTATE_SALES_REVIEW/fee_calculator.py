"""Rule 141 fee estimator (internal estate review). Schedules: Rule 141 as amended by
A.M. 04-2-04-SC, rates 'Effective Nov. 11, 2006' (chanrobles.com/revisedrule141rulesofcourt.htm).
Run: python3 fee_calculator.py  -> prints headline + writes fee_calculator.xlsx"""
import math, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter as L

R = dict(level=0.08, mtc_cap=400000, lrf_pct=0.01, lrf_min=10, vcf=5, mediation=500,
         summons=200, sheriff_trust=1000, lis_pendens=0, cert_page=10, cert_cert=100,
         cert_pages=30, rd_ctc=0, lawyer=0)

def sec7a(v):
    """Sec. 7(a) RTC, eff. 11 Nov 2006. 'For each P1,000.00 in excess' read as each started P1,000 (ceil)."""
    for cap, fee in [(100000,1000),(150000,1600),(200000,2000),(250000,3000),(300000,3500),(350000,4000)]:
        if v < cap: return fee
    if v <= 400000: return 4500
    return 4500 + 20*math.ceil((v-400000)/1000)

def costs(fmv, defendants=1, titles=1, damages=0, av=None, r=R):
    av = fmv*r['level'] if av is None else av
    court = 'MTC' if av <= r['mtc_cap'] else 'RTC'
    fee = sec7a(fmv+damages)            # MTC proxy: see explainer (Sec. 8 table stops at 400k)
    lrf = max(r['lrf_min'], r['lrf_pct']*fee)
    sher = r['summons']*defendants + r['sheriff_trust']
    lp = r['lis_pendens']*titles
    cert = (r['cert_page']*r['cert_pages'] + r['cert_cert'])*titles + r['rd_ctc']*titles
    tot = fee+lrf+r['vcf']+r['mediation']+sher+lp+cert
    return dict(av=av, court=court, fee=fee, lrf=lrf, sheriff=sher, total=tot)

SEED = [  # id,title,lot,area,buyer,deed,src,tdmv,zonal_sqm,stated,av,defs,flags
 ("S1","TCT 079-2021002126 (from T-52540)","Lot 2-X-6-I-4-C-1",2587,"Gloria Hansol Balane","1996-09-29".replace("1996","2016"),
  "ARP GR-2023-II-07-001-00256 (dossier Annex); eCAR 201900675224",2509390,600,None,200750,1,
  "Already filed as 26-360 (MTC Mercedes). Zonal 1,552,200/2,587 = 600/sqm."),
 ("S2","T-52540 memo PE-290350 (15 Sep 2005)","Lot 2-X-6-I-4-C-2, Psd-05-026197","","Mariquita A. Era","2005-04-28",
  "Exh. B p.3; price P70,000",None,None,None,None,1,"Area, TD value unknown. Pre-revocation (15 Aug 2005)."),
 ("S3","?","?","","Hansol","1999","Def. Exh. 4 [VERIFY]; Delafuente signatures.pdf",None,None,None,None,1,"Values unknown; 1991 SPA."),
 ("S4","?","?","","Nacasa","2002","Delafuente signatures.pdf",None,None,None,None,1,"Values unknown"),
 ("S5","?","?","","Pascual","1998","Delafuente signatures.pdf",None,None,None,None,1,"Values unknown"),
 ("S6","?","?","","Victa","2004","Delafuente signatures.pdf",None,None,None,None,1,"Values unknown (2004 & 2007 papers)"),
 ("S7","?","?","","Ramirez","1996","Delafuente signatures.pdf",None,None,None,None,1,"Values unknown"),
 ("S8","?","?","","Vela","2000","Delafuente signatures.pdf",None,None,None,None,1,"Values unknown"),
]
PRESC = ("If void (Art. 1409/1410): action to declare inexistence does not prescribe. "
         "Reconveyance on implied trust (Art. 1456 + Art. 1144): 10 yrs from registration; "
         "plaintiff in actual possession: treated as quieting of title (confirm with counsel).")

def build(path):
    wb = openpyxl.Workbook(); b = Font(bold=True); inp = PatternFill("solid", fgColor="FFF2CC")
    I = wb.active; I.title = "Inputs"
    rows = [("Assessment level, residential (Mercedes ARP 00256 shows 8%)","level",R['level']),
            ("MTC ceiling, assessed value (BP 129 s33(3) as amended by RA 11576)","mtc_cap",R['mtc_cap']),
            ("Legal Research Fund % of filing fee (RA 3870; matches SP 2156 form P20 on P2,000)","lrf_pct",R['lrf_pct']),
            ("LRF minimum","lrf_min",R['lrf_min']),("Victims Compensation Fund per case (SP 2156 form)","vcf",R['vcf']),
            ("Mediation fee, Sec. 9","mediation",R['mediation']),("Sheriff: summons per defendant, Sec. 10(a)","summons",R['summons']),
            ("Sheriff trust/travel deposit per case [UNVERIFIED estimate - ask clerk]","sheriff_trust",R['sheriff_trust']),
            ("RD lis pendens entry fee per title [UNVERIFIED - fill from RD Daet/LRA schedule]","lis_pendens",R['lis_pendens']),
            ("Court certified copy per page, Sec. 21(d)/8","cert_page",R['cert_page']),("Court certification each","cert_cert",R['cert_cert']),
            ("Pages of court CTCs per lot (assumption)","cert_pages",R['cert_pages']),
            ("RD certified title/deed copies per lot [UNVERIFIED - fill]","rd_ctc",R['rd_ctc']),
            ("LAWYER FEES (input; not estimated)","lawyer",R['lawyer']),
            ("Headline: market value per sq m (Jonathan)","pps_hi",3000),("Zonal per sq m (eCAR 201900675224, San Roque/Brgy 1 residential)","pps_lo",600),
            ("Tax-declaration market value per sq m (ARP 00256: 2,509,390/2,587)","pps_mid",970),
            ("Headline total area sq m","area",30000),("Headline: number of separate lots","nlots",10),("Headline damages claimed (total)","dmg",0)]
    I.append(["Parameter","Name","Value"]); [c.__setattr__('font',b) for c in I[1]]
    for i,(d,n,v) in enumerate(rows, start=2):
        I.append([d,n,v]); I.cell(i,3).fill = inp
        wb.defined_names.add(openpyxl.workbook.defined_name.DefinedName(n, attr_text=f"Inputs!$C${i}"))
    I.column_dimensions['A'].width = 80; I.column_dimensions['C'].width = 14
    def FEE(x):
        return (f"IF({x}<100000,1000,IF({x}<150000,1600,IF({x}<200000,2000,IF({x}<250000,3000,"
                f"IF({x}<300000,3500,IF({x}<350000,4000,IF({x}<=400000,4500,4500+20*ROUNDUP(({x}-400000)/1000,0))))))))")
    S = wb.create_sheet("Lots")
    hdr = ["ID","Title no.","Lot","Area sqm","Buyer","Deed date","Source","TD market value","Zonal /sqm","Zonal value",
           "Stated value (if no TD/zonal)","Assessed value (TD)","AV used","Court","Causes","Damages claimed","Fee base",
           "Filing fee s7(a)","LRF","VCF","Mediation","Defendants","Sheriff","Lis pendens","Certified copies","Total (excl. lawyer)",
           "Prescription triage","Flags / missing"]
    S.append(hdr); [c.__setattr__('font',b) for c in S[1]]
    for k,s in enumerate(SEED, start=2):
        id_,t,lot,a,buyer,d,src,mv,zs,st,av,defs,fl = s
        S.append([id_,t,lot,a,buyer,d,src,mv,zs,None,st,av]); r=k
        S[f"J{r}"] = f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(I{r})),D{r}*I{r},"")'
        S[f"M{r}"] = f'=IF(ISNUMBER(L{r}),L{r},IF(ISNUMBER(H{r}),H{r}*level,""))'
        S[f"N{r}"] = f'=IF(M{r}="","NEEDS VALUE",IF(M{r}<=mtc_cap,"MTC","RTC"))'
        S[f"O{r}"] = "Annulment/declaration of nullity + reconveyance/cancellation of title + damages"
        S[f"P{r}"] = 0
        S[f"Q{r}"] = f'=IF(AND(N(H{r})=0,N(J{r})=0,N(K{r})=0),"",IF(MAX(N(H{r}),N(J{r}))>0,MAX(N(H{r}),N(J{r})),N(K{r}))+N(P{r}))'
        S[f"R{r}"] = f'=IF(Q{r}="","",{FEE(f"Q{r}")})'
        S[f"S{r}"] = f'=IF(R{r}="","",MAX(lrf_min,lrf_pct*R{r}))'
        S[f"T{r}"] = f'=IF(R{r}="","",vcf)'; S[f"U{r}"] = f'=IF(R{r}="","",mediation)'
        S[f"V{r}"] = defs
        S[f"W{r}"] = f'=summons*V{r}+sheriff_trust'; S[f"X{r}"] = "=lis_pendens"
        S[f"Y{r}"] = "=cert_page*cert_pages+cert_cert+rd_ctc"
        S[f"Z{r}"] = f'=IF(R{r}="","NEEDS VALUE",SUM(R{r}:U{r},W{r}:Y{r}))'
        S[f"AA{r}"] = PRESC; S[f"AB{r}"] = fl
        for c in "HIKLP": S[f"{c}{r}"].fill = inp
    n = len(SEED)+1
    S.append([]); S.append(["JOINDER","One complaint, all seed lots with values (Rule 3 s6 permissive joinder; only if same series of transactions + common question - counsel to confirm)"])
    j = n+3
    S[f"Q{j}"] = f"=SUM(Q2:Q{n})"; S[f"R{j}"] = f'={FEE(f"Q{j}")}'; S[f"S{j}"]=f"=MAX(lrf_min,lrf_pct*R{j})"
    S[f"T{j}"]="=vcf"; S[f"U{j}"]="=mediation"; S[f"V{j}"]=f"=SUMPRODUCT(ISNUMBER(R2:R{n})*V2:V{n})"; S[f"W{j}"]=f"=summons*V{j}+sheriff_trust"
    S[f"X{j}"]=f"=lis_pendens*COUNT(R2:R{n})"; S[f"Y{j}"]=f"=(cert_page*cert_pages+cert_cert+rd_ctc)*COUNT(R2:R{n})"
    S[f"Z{j}"]=f"=SUM(R{j}:U{j},W{j}:Y{j})"
    S.append([]); S.append(["","Lawyer fees (input)"]); S[f"Z{j+2}"]="=lawyer"
    for i,w in enumerate([5,26,24,9,20,11,30,14,9,13,12,13,12,12,30,12,14,13,9,6,9,6,9,9,10,14,60,45],1): S.column_dimensions[L(i)].width=w
    H = wb.create_sheet("Headline_3ha", 0)
    H.append(["3 ha (30,000 sq m) worked example - all cells are live formulas on Inputs"]); H['A1'].font=b
    H.append(["Scenario","P/sqm","Total market value","Combined: AV","Combined court","Combined filing fee","Combined total",
              "Per-lot value","Per-lot AV","Per-lot court","Per-lot filing fee","Separate suits total (all lots)","Extra cost of separate suits"])
    for c in H[2]: c.font=b
    for i,(lab,nm) in enumerate([("Low: BIR zonal","pps_lo"),("Mid: tax-declaration MV","pps_mid"),("High: Jonathan 3,000","pps_hi")], start=3):
        H[f"A{i}"]=lab; H[f"B{i}"]=f"={nm}"; H[f"C{i}"]=f"=B{i}*area"; H[f"D{i}"]=f"=C{i}*level"
        H[f"E{i}"]=f'=IF(D{i}<=mtc_cap,"MTC","RTC")'; fb=f"(C{i}+dmg)"
        H[f"F{i}"]=f"={FEE(fb)}"
        H[f"G{i}"]=f"=F{i}+MAX(lrf_min,lrf_pct*F{i})+vcf+mediation+summons*nlots+sheriff_trust+(lis_pendens+cert_page*cert_pages+cert_cert+rd_ctc)*nlots"
        H[f"H{i}"]=f"=C{i}/nlots"; H[f"I{i}"]=f"=H{i}*level"; H[f"J{i}"]=f'=IF(I{i}<=mtc_cap,"MTC","RTC")'
        pb=f"(H{i}+dmg/nlots)"; H[f"K{i}"]=f"={FEE(pb)}"
        H[f"L{i}"]=f"=nlots*(K{i}+MAX(lrf_min,lrf_pct*K{i})+vcf+mediation+summons+sheriff_trust+lis_pendens+cert_page*cert_pages+cert_cert+rd_ctc)"
        H[f"M{i}"]=f"=L{i}-G{i}"
    H.append([]); H.append(["Excludes lawyer fees (Inputs!lawyer), appeal fees, publication. Lis pendens/RD copies are 0 until filled. MTC fee uses s7(a) schedule as proxy (see explainer)."])
    for i,w in enumerate([24,8,16,13,10,14,14,14,12,10,13,16,14],1): H.column_dimensions[L(i)].width=w

    P = wb.create_sheet("PRIMARY_Combined_RTC", 0)
    P.append(["PRIMARY: one combined RTC action, all sales, Cesar's estate/heirs + all buyers (live formulas)"]); P['A1'].font=b
    P.append(["Area sqm",30000]); P.append(["P/sqm",3000]); P.append(["Defendants (buyers + heirs; adjust)",20]); P.append(["Titles to annotate/certify",10])
    for r in range(2,6): P.cell(r,2).fill=inp
    P.append([]); P.append(["Damages scenario","Fee base","Filing fee s7(a)","LRF","VCF+Mediation","Sheriff (summons x defs + deposit)","Lis pendens + copies","TOTAL excl. lawyer","Assessed value","Court"])
    for c in P[7]: c.font=b
    for i,d in enumerate([0,5000000,20000000], start=8):
        P[f"A{i}"]=d; P[f"A{i}"].fill=inp; P[f"B{i}"]=f"=$B$2*$B$3+A{i}"; P[f"C{i}"]="="+FEE(f"B{i}")
        P[f"D{i}"]=f"=MAX(lrf_min,lrf_pct*C{i})"; P[f"E{i}"]="=vcf+mediation"; P[f"F{i}"]="=summons*$B$4+sheriff_trust"
        P[f"G{i}"]="=(lis_pendens+cert_page*cert_pages+cert_cert+rd_ctc)*$B$5"; P[f"H{i}"]=f"=SUM(C{i}:G{i})"
        P[f"I{i}"]="=$B$2*$B$3*level"; P[f"J{i}"]=f'=IF(I{i}<=mtc_cap,"MTC","RTC")'
    P.append([]); P.append(["Lawyer fees (input)","=lawyer"]); P.append(["Grand total incl. lawyer (P0 damages)","=H8+B12"])
    for i,w in enumerate([34,14,14,10,12,18,14,16,14,8],1): P.column_dimensions[L(i)].width=w
    for row in P.iter_rows(min_row=2):
        for c in row:
            if c.column>1 or c.row>=8: c.number_format='#,##0.00'
    for ws in (H,S):
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value,(int,float)) or (isinstance(c.value,str) and c.value.startswith("=")): c.number_format='#,##0.00'
    wb.save(path)

if __name__ == "__main__":
    build("/workspace/cv360/fees/fee_calculator.xlsx")
    for lab,p in [("low 600",600),("mid 970",970),("high 3000",3000)]:
        V=p*30000; c=costs(V,defendants=10,titles=10); per=costs(V/10)
        print(lab, f"V={V:,.0f} AV={c['av']:,.0f} {c['court']} fee={c['fee']:,.0f} total={c['total']:,.2f} | per-lot V={V/10:,.0f} AV={per['av']:,.0f} {per['court']} fee={per['fee']:,.0f} x10 total={10*per['total']:,.2f}")
    print("Balane", costs(2509390, av=200750))
