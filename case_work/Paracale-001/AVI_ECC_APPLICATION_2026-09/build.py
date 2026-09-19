# ECC application pack (IEE Checklist, Category B) — AVI Gold Processing Plant, EMB Region V. Run: python3 build.py
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors

BN = "AVI GOLD PROCESSING PLANT"
DTI = "DTI Business Name No. 8480852 (Regional - Region V), valid 11 September 2026 to 11 September 2031"
SITE = ("Lot 4, Psu-143364, Original Certificate of Title No. P-1616 (Registry of Deeds for Camarines Norte), "
        "Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte 4606")
HEAD = [("b", BN), ("n", "Allan V. Inocalla, Proprietor"),
        ("n", "Residence: Purok 4, Barangay Capacuan, Paracale, Camarines Norte 4605 - Plant site: " + SITE),
        ("n", "Mobile 0917 155 4782  -  shiraction2@gmail.com  -  TIN 200-031-253")]
SIGN = ["Respectfully yours,", "", "", "", "<b>ALLAN V. INOCALLA</b>", f"Proprietor, {BN}", ""]
RCV = "Received by: ______________________  Position: ______________  Date/Time: ______________"
EMB = ["<b>GERI-GERONIMO R. SANEZ, MPA</b>", "Regional Director",
       "DENR - Environmental Management Bureau, Regional Office No. V", "Regional Center Site, Rawis, Legazpi City 4500", "",
       "Attention: The Chief, Clearance and Permitting Division / EIA Management Section"]

DOCS = []

# ---------------------------------------------------------------- 1. the request itself
DOCS.append({"title": "1 - Letter-request for the issuance of an Environmental Compliance Certificate (transmittal of the hard-copy set)",
 "addr": ["____ ____________ 2026", ""] + EMB,
 "subject": ("SUBJECT: APPLICATION FOR THE ISSUANCE OF AN ENVIRONMENTAL COMPLIANCE CERTIFICATE (INITIAL ENVIRONMENTAL EXAMINATION CHECKLIST, "
             "CATEGORY B) - AVI GOLD PROCESSING PLANT, LOT 4, PSU-143364 (OCT NO. P-1616), BARANGAY SANTA ROSA SUR, JOSE PANGANIBAN, "
             "CAMARINES NORTE - ECC ONLINE APPLICATION NO. ______________"),
 "body": ["Sir:",
  (f"I, <b>ALLAN VILLAFRIA INOCALLA</b>, Filipino, of legal age, sole proprietor of <b>{BN}</b> ({DTI}), respectfully apply for the "
   "issuance of an <b>Environmental Compliance Certificate</b> for a proposed mercury-free and cyanide-free gold gravity-concentration "
   f"plant on my own registered land at {SITE}, and submit herewith the hard copies of the application filed through the ECC Online "
   "System under the application number stated above."),
  ("<b>Coverage.</b> The project is <b>metallic mineral or ore processing</b> under Annex A, item 2.1.5(a) of EMB Memorandum Circular No. "
   "2014-005. Its design input is <b>ten (10) tonnes of ore per day, or about three thousand (3,000) tonnes per year</b>, and I undertake "
   "that the annual input to the plant shall not exceed <b>nine thousand (9,000) tonnes</b>, which is below the ten thousand (10,000) "
   "tonnes per year threshold. The project is therefore <b>Category B</b>, documented by an <b>Initial Environmental Examination (IEE) "
   "Checklist</b> and decided by this Regional Office."),
  ("<b>Process.</b> Run-of-mine ore and old tailings sourced from permitted small-scale mining contractors and mining-rights holders in the "
   "Paracale - Jose Panganiban gold district under written supply agreements are crushed and milled, classified, passed through a "
   "centrifugal gravity rougher and cleaned on locally fabricated shaking (concentrating) tables; the concentrate is smelted to dore and "
   "sold to the Bangko Sentral ng Pilipinas or its accredited traders. <b>No mercury is used at any stage, and no cyanide or any other "
   "substance in the Priority Chemical List or under a Chemical Control Order is used at any stage.</b> Process water is recirculated from "
   "the decant of a lined tailings storage facility; the plant is designed for zero discharge to any watercourse."),
  ("<b>Site.</b> The plant occupies approximately five thousand (5,000) square meters of Lot 4, which has an area of 15.2069 hectares and "
   "is titled solely in my name under Original Certificate of Title No. P-1616 (Free Patent No. 225537, 10 May 1963). The remainder of "
   "the lot stays in its present use."),
  ("<b>Enclosures.</b> Enclosed are: (1) the notarized IEE Checklist Report with the Sworn Statement of Accountability; (2) the Project "
   "Description and Fact Sheet with the geographic coordinates of the lot corners; (3) the Project Components and Operation Information "
   "table; (4) the Environmental Impact and Management Plan checklist; (5) the PEMAPS data sheet; (6) the Site Development Plan signed by "
   "______________________, PRC License No. ______________; (7) the certification of the Municipality of Jose Panganiban on land-use "
   "compatibility; (8) geotagged photographs of the site taken on ______________; (9) a certified true copy of Original Certificate of "
   "Title No. P-1616 and Tax Declaration No. ______________; (10) the DTI Certificate of Business Name Registration No. 8480852; "
   "(11) the DENR-CENRO certification of land classification status; and (12) the LandBank official receipt for the filing fee of "
   "five thousand seventy pesos (P5,070.00) paid on the Order of Payment issued by the System."),
  ("I undertake to comply with the conditions of the Certificate that may be issued, to have the Certificate notarized and uploaded to the "
   "System upon release, to appoint and have accredited a Pollution Control Officer, to secure a Permit to Operate for any stationary "
   "emission source before commissioning, and to submit the semi-annual Compliance Monitoring Reports required of the holder of a "
   "Certificate."),
  ("May I respectfully request that the application be evaluated and acted upon within the twenty (20) working days provided in the "
   "Citizen's Charter of this Office, and that any request for additional information be sent to the electronic mail address above so "
   "that it may be complied with promptly. Kindly acknowledge receipt on the enclosed copy of this letter.")] + SIGN + [RCV]})

# ---------------------------------------------------------------- 2. project description (Step 3 paste text)
PD = [
 ("<b>AVI Gold Processing Plant</b> is a mercury-free and cyanide-free gold gravity-concentration plant proposed by Allan V. Inocalla, sole "
  "proprietor (DTI Business Name No. 8480852, \"AVI Gold Processing Plant\", Regional - Region V), on his own titled land, Lot 4, Psu-143364, "
  "Original Certificate of Title No. P-1616, area 15.2069 hectares, Purok ______, Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte. "
  "The plant occupies about 5,000 square meters of the lot; the remainder stays in its present use."),
 ("The plant receives run-of-mine ore and old tailings from permitted small-scale mining contractors and mining-rights holders in the "
  "Paracale - Jose Panganiban gold district under written supply agreements, at a design throughput of 10 tonnes per day, about 3,000 tonnes "
  "per year, with a declared ceiling of 9,000 tonnes per year. Ore is crushed and milled, classified, passed through a centrifugal gravity "
  "rougher and cleaned on shaking (concentrating) tables of the Wilfley / 6-S type fabricated locally; the concentrate is smelted to dore. "
  "No mercury and no cyanide or other chemicals in the Priority Chemical List or under a Chemical Control Order are used at any stage. All "
  "gold produced is sold to the Bangko Sentral ng Pilipinas or its accredited traders."),
 ("Components: covered crushing and milling shed; classification and gravity circuit (rougher and concentrating tables) on a rigid concrete "
  "pad; concentrate and smelting room; ore receiving and stockpile yard; process-water tank and recirculation sump; lined tailings storage "
  "facility with settling pond and decant; silt traps and perimeter drainage; materials recovery facility; septic tank; rainwater cistern; "
  "oil-water separator at the generator and fuel bay; office and store; workers' quarters. Power is taken from CANORECO with a standby "
  "generator; water is from rainwater catchment and ______________, with recirculation of process water."),
 ("Process water is recirculated from the tailings decant; the tailings are chemical-free gravity tailings, contained in the lined facility, "
  "and are not discharged to any watercourse. Dust is controlled by wet processing and enclosure; noise by enclosure and by the rigid "
  "foundation of the tables. Domestic waste is segregated at the materials recovery facility and turned over to the municipal collection; "
  "used oil is stored in a bunded bay and turned over to an accredited treater."),
 ("Construction takes about ______ months with about ______ workers. Operation employs three (3) workers at start, preferentially residents "
  "of Barangay Santa Rosa Sur, rising to ______ at full operation. The estimated project cost is P______________. The project is proposed as "
  "a formal, Minahang Bayan-aligned processing facility serving the district's small-scale miners in place of mercury-based backyard "
  "processing."),
]
COORD = [["Corner", "Latitude (WGS 84)", "Longitude (WGS 84)", "Source"],
         ["1", "__ deg __' __.__\" N", "___ deg __' __.__\" E", "from Psu-143364 / GPS at site"],
         ["2", "__ deg __' __.__\" N", "___ deg __' __.__\" E", ""],
         ["3", "__ deg __' __.__\" N", "___ deg __' __.__\" E", ""],
         ["4", "__ deg __' __.__\" N", "___ deg __' __.__\" E", ""],
         ["Plant centre", "__ deg __' __.__\" N", "___ deg __' __.__\" E", ""]]
DOCS.append({"title": "2 - Project Description / Fact Sheet (text for Step 3 of the ECC Online form; limit 4,000 characters)",
 "addr": [], "subject": "", "body": PD,
 "tables": [("Geographic coordinates of the lot corners (required with the Project Description)", COORD, [3.0, 4.5, 4.5, 4.5])],
 "after": [("<i>Character count of the five paragraphs above: %d characters (limit 4,000). Re-count after the blanks are filled.</i>"
            % sum(len(p.replace('<b>','').replace('</b>','')) for p in PD))]})

# ---------------------------------------------------------------- 3. components and operation
COMP = [["Component", "Area (sq m)", "Capacity / rating", "Notes"],
 ["Ore receiving and stockpile yard", "600", "300 t live stock (30 days at 10 tpd)", "bunded, graded to silt trap"],
 ["Crushing and milling shed", "300", "10 tpd design; 30 tpd installed maximum", "enclosed; wet operation"],
 ["Gravity circuit pad (centrifugal rougher + concentrating tables)", "200", "2 tables (expandable)", "rigid concrete pad, mass about 10 t per table"],
 ["Concentrate and smelting room", "40", "dore", "flux only; no PCL/CCO chemical"],
 ["Tailings storage facility, settling pond and decant", "1,800", "about 2,150 cu m per year; capacity ______ cu m (______ years)", "lined; decant recirculated; no discharge"],
 ["Process-water tank and recirculation sump", "100", "______ cu m", "closed circuit"],
 ["Materials recovery facility", "30", "10 kg per day", "RA 9003 segregation"],
 ["Septic tank / domestic wastewater facility", "20", "______ cu m", "3 workers at start"],
 ["Rainwater catchment and cistern", "30", "______ cu m", "make-up water"],
 ["Oil-water separator, generator and fuel bay (bunded)", "60", "______ cu m separator; genset ______ kVA", "standby power only"],
 ["Office, store and records", "80", "-", ""],
 ["Workers' quarters and mess", "100", "3 persons at start", ""],
 ["Motorpool, parking and internal access road", "400", "-", ""],
 ["Perimeter drainage, silt traps, buffer / greenbelt and open space", "1,240", "-", "tree planting to compensate vegetation removed"],
 ["<b>TOTAL - declared project size</b>", "<b>5,000</b>", "", "<b>must equal the project size in the Project Description</b>"]]
DOCS.append({"title": "3 - Project Components and Operation Information (ECC Online requirement 2)",
 "addr": [], "subject": "", "tables": [("", COMP, [6.2, 1.9, 4.6, 4.0])],
 "body": [("Every figure in the column of areas is a <b>planning estimate</b> and is to be replaced by the corresponding figure in the Site "
   "Development Plan before the application is submitted. The total must equal the project size declared in the Project Description "
   "(5,000 square meters), which is the footprint of the plant and not the area of the lot (15.2069 hectares).")],
 "after": [("<b>Mandatory components confirmed present:</b> materials recovery facility; septic tank / domestic wastewater facility; rainwater "
   "catchment and cistern; oil-water separator at the generator and fuel bay. <b>Hazardous waste storage:</b> not applicable - the plant is "
   "gravity-only and uses no chemical in the Priority Chemical List or under a Chemical Control Order; used oil from the standby generator "
   "is held in a bunded drum bay and turned over to a DENR-accredited treater, and registration as a hazardous waste generator will be made "
   "if and when the quantities generated require it.")]})

# ---------------------------------------------------------------- 4. EMP checklist
EMP = [["Aspect", "Impact", "Management measure committed"],
 ["Land and erosion", "site clearing; pad and tailings-facility earthworks; loss of vegetation",
  "silt traps and temporary settling ponds during construction; perimeter drainage led to the settling pond; spoils placed on flat ground away from drainage lines; slope stabilisation; tree planting to compensate the vegetation removed; progressive rehabilitation"],
 ["Water", "process water; gravity tailings; domestic wastewater",
  "closed-circuit recirculation of process water from the tailings decant; lined tailings storage facility; design target of zero discharge to any watercourse, and no discharge in exceedance of the effluent standards under DENR Administrative Order No. 2021-19; septic tank for domestic wastewater; a Wastewater Discharge Permit to be applied for if any discharge is later designed"],
 ["Tailings", "storage and containment; structural safety",
  "tailings storage facility designed and operated in accordance with Section 30 of DENR Administrative Order No. 2022-03; registration of the facility with this Office; maintained freeboard, decant system and periodic inspection; the tailings are chemical-free"],
 ["Air", "dust from crushing, milling and ore handling; generator exhaust",
  "wet crushing and milling and enclosure of the shed; watering of the yard and access road; a Permit to Operate to be secured for the standby generator before commissioning"],
 ["Noise and vibration", "mill, tables and generator",
  "enclosure; rigid concrete foundations for the tables; operations confined to daytime hours; the standard of 85 dBA at the plant boundary observed"],
 ["Chemicals", "none",
  "no mercury (banned by Section 14 of DENR Administrative Order No. 2022-03) and no cyanide; no substance in the Priority Chemical List or under a Chemical Control Order is stored or used; only flux and ordinary consumables are kept on site"],
 ["Solid and hazardous waste", "domestic waste; scrap; used oil",
  "materials recovery facility and segregation under RA 9003 with turnover to the municipal collection; scrap sold to accredited buyers; used oil stored in a bunded drum bay and turned over to a DENR-accredited treater with the corresponding manifests"],
 ["Occupational safety and health", "machinery, smelting, manual handling",
  "personal protective equipment issued and enforced; the mine safety rules under DENR Administrative Order No. 97-30 observed; training in chemical handling and emergency response, with proof of training submitted to this Office within sixty (60) days from the start of operations"],
 ["Social", "employment; traffic; community relations",
  "preferential hiring of residents of Barangay Santa Rosa Sur; coordination with the Barangay and the Municipality; a grievance desk at the Barangay Hall and a named contact person at the plant; information on the mercury-free process given to supplier miners"],
 ["Monitoring", "compliance verification",
  "an Environmental Unit established and a Pollution Control Officer appointed and accredited with this Office; semi-annual Compliance Monitoring Reports submitted from the first semester of operations; self-monitoring at the rates declared in the PEMAPS; records kept on site and open to inspection"]]
DOCS.append({"title": "4 - Environmental Impact and Management Plan checklist (ECC Online requirement 4) - commitments offered as conditions",
 "addr": [], "subject": "", "body": [], "tables": [("", EMP, [3.2, 4.3, 9.2])],
 "after": [("These commitments are offered for incorporation as conditions of the Certificate. They are written to meet the conditions this "
   "Office customarily imposes on a plant of this class, and each of them is within the proponent's own control.")]})

# ---------------------------------------------------------------- 5. PEMAPS
PEM = [["Parameter", "Estimated rate", "Basis / control"],
 ["Ore and old tailings input", "10 t/day design; 3,000 t/yr; declared ceiling 9,000 t/yr", "300 operating days per year; weighbridge or truck count log"],
 ["Product", "dore, ______ g/day (estimate)", "sold to BSP or its accredited traders"],
 ["Process water - circulating", "about 50 cu m/day", "closed circuit from the tailings decant"],
 ["Process water - make-up", "about 5 cu m/day", "rainwater catchment and ______________; losses to evaporation and to moisture retained in the tailings"],
 ["Discharge to watercourse", "nil (design target zero discharge)", "lined facility with decant recirculation; monitored against DAO 2021-19 if any discharge occurs"],
 ["Gravity tailings to the storage facility", "about 9.8 t/day; about 2,150 cu m/yr", "dry density taken at 1.4 t/cu m; chemical-free"],
 ["Domestic wastewater", "about 0.5 cu m/day", "3 workers at start; septic tank"],
 ["Solid waste - domestic", "about 5 kg/day", "materials recovery facility; municipal collection"],
 ["Solid waste - scrap and packaging", "about ______ kg/month", "sold to accredited buyers"],
 ["Used oil", "about 20 L/month when the generator runs", "bunded drum bay; DENR-accredited treater"],
 ["Air emission - stationary source", "standby generator ______ kVA, ______ hours/month", "Permit to Operate before commissioning; outage backup only"],
 ["Particulates", "no point source; fugitive dust only", "wet processing; enclosure; yard and road watering"],
 ["Noise", "85 dBA at the plant boundary (limit adopted)", "enclosure; rigid foundations; daytime operation"]]
DOCS.append({"title": "5 - PEMAPS data sheet (ECC Online requirement 5; Annex 2-7d of the Revised Procedural Manual, DAO 2003-30)",
 "addr": [], "subject": "", "body": [], "tables": [("", PEM, [5.0, 5.2, 6.5])],
 "after": [("Every rate above is an <b>engineering estimate</b> derived from the declared throughput of 10 tonnes per day and is to be replaced "
   "by the figures of the final flowsheet and water balance before the application is submitted. The rates declared here become the basis "
   "of the self-monitoring required of the holder of a Certificate.")]})

# ---------------------------------------------------------------- 6. sworn statement of accountability
DOCS.append({"title": "6 - Sworn Statement of Accountability of the Proponent (EMB Memorandum Circular No. 2022-002)",
 "addr": ["Republic of the Philippines )", "Province of Camarines Norte )", "______________________ ) S.S.", "",
          "<b>SWORN STATEMENT OF ACCOUNTABILITY</b>"],
 "subject": "",
 "body": [("I, <b>ALLAN VILLAFRIA INOCALLA</b>, Filipino, of legal age, sole proprietor of <b>AVI GOLD PROCESSING PLANT</b> and a resident of "
   "Purok 4, Barangay Capacuan, Paracale, Camarines Norte, after having been duly sworn in accordance with law, hereby depose and state:"),
  ("1. That I am the proponent of the <b>AVI Gold Processing Plant</b>, a gold gravity-concentration plant proposed at Lot 4, Psu-143364, "
   "covered by Original Certificate of Title No. P-1616, Barangay Santa Rosa Sur, Jose Panganiban, Camarines Norte, for which an "
   "application for an Environmental Compliance Certificate has been filed with the Environmental Management Bureau, Regional Office "
   "No. V, under ECC Online Application No. ______________;"),
  ("2. That I have caused the preparation of the Initial Environmental Examination Checklist Report and its annexes and have read and "
   "understood the same, and that I take <b>full responsibility for the accuracy, completeness and truthfulness</b> of all the information, "
   "data, plans and representations contained therein;"),
  ("3. That the plant uses <b>no mercury and no cyanide</b>, and uses no substance included in the Priority Chemical List or subject to a "
   "Chemical Control Order, at any stage of its operations;"),
  ("4. That the annual input of ore and old tailings to the plant shall <b>not exceed nine thousand (9,000) tonnes per year</b>, and that "
   "should the project require an input at or above ten thousand (10,000) tonnes per year, or the introduction of any leaching or other "
   "chemical process, I shall <b>first</b> apply for and obtain the corresponding amendment or new Environmental Compliance Certificate "
   "before undertaking the change;"),
  ("5. That the land on which the plant is to be established is registered in my name and that no part of the project is located within a "
   "protected area, a critical watershed or an ancestral domain, as the certifications submitted with the application show;"),
  ("6. That I bind myself to <b>comply with all the conditions and restrictions</b> of the Environmental Compliance Certificate that may be "
   "issued, to implement the Environmental Management Plan submitted, to appoint and have accredited a Pollution Control Officer, to "
   "secure the other permits and clearances required before commissioning, and to submit the semi-annual Compliance Monitoring Reports;"),
  ("7. That I understand that any misrepresentation in the application, or any violation of the conditions of the Certificate, is a ground "
   "for the <b>suspension or cancellation</b> of the Certificate and for the imposition of fines and other sanctions under Presidential "
   "Decree No. 1586 and its implementing rules, without prejudice to the other liabilities provided by law; and"),
  ("8. That I execute this Statement to attest to the truth of the foregoing and for the purpose of supporting the said application for an "
   "Environmental Compliance Certificate."),
  "IN WITNESS WHEREOF, I have hereunto set my hand this ____ day of ____________ 2026 at ______________, Camarines Norte.",
  "", "", "", "<b>ALLAN VILLAFRIA INOCALLA</b>", "Proponent - TIN 200-031-253 - ID: ______________________ No. ______________", "",
  ("SUBSCRIBED AND SWORN to before me this ____ day of ____________ 2026 at ______________, Camarines Norte, affiant exhibiting to me his "
   "______________________ No. ______________ issued on __________ at __________."),
  "", "", "NOTARY PUBLIC", "Doc. No. ____; Page No. ____; Book No. ____; Series of 2026.", "",
  ("(Use the form generated by the ECC Online System if it differs from this text; this text is the substance required by EMB Memorandum "
   "Circular No. 2022-002 and Annexes 2-21 / 2-22 of the Revised Procedural Manual.)")]})

# ---------------------------------------------------------------- 7. authorization
DOCS.append({"title": "7 - Authorization to file, follow up and receive documents (ECC Online requirement R2)",
 "addr": ["____ ____________ 2026", ""] + EMB,
 "subject": ("SUBJECT: AUTHORIZATION TO FILE, FOLLOW UP AND RECEIVE DOCUMENTS - ECC APPLICATION OF AVI GOLD PROCESSING PLANT, "
             "ECC ONLINE APPLICATION NO. ______________"),
 "body": ["Sir:",
  (f"I, <b>ALLAN VILLAFRIA INOCALLA</b>, proprietor of <b>{BN}</b> and proponent of the above application, hereby authorize "
   "<b>______________________________</b>, holder of ______________________ No. ______________, to do the following acts for me and in my "
   "name in connection with the said application:"),
  "1. File and transmit the application and its annexes, and submit additional documents required by your Office;",
  "2. Follow up the status of the application and receive notices, orders of payment and requests for additional information;",
  "3. Pay the filing fee and secure the corresponding official receipt; and",
  "4. Receive and sign for the documents released by your Office, including the Environmental Compliance Certificate.",
  ("This authorization <b>does not include</b> the power to sign the application, the IEE Checklist Report, the Sworn Statement of "
   "Accountability or any other sworn document, all of which I sign personally. It is valid from the date hereof until 31 December 2026 "
   "unless sooner revoked in writing."),
  "", "", "", "<b>ALLAN VILLAFRIA INOCALLA</b>", f"Proponent - Proprietor, {BN}",
  "TIN 200-031-253 - ID: ______________________ No. ______________", "", "",
  "______________________________", "Representative (signature over printed name) - ID: ______________________ No. ______________", "",
  "(Attach photocopies of both identification cards.)"]})

# ---------------------------------------------------------------- 8. filing checklist
CHK = [["#", "Requirement", "Who secures it", "Status"],
 ["R1", "Government identification card of the proponent (for the ECC Online account)", "Allan", "in hand"],
 ["R2", "Authorization letter, if a representative files", "Allan signs - page 7 of this pack", "ready"],
 ["R3", "DTI Certificate of Business Name Registration", "issued 11 Sep 2026, BN No. 8480852", "in hand"],
 ["1", "Project Description / Fact Sheet with the coordinates of the lot corners", "page 2 of this pack; coordinates from Psu-143364 or GPS", "draft - coordinates blank"],
 ["2", "Project Components and Operation Information", "page 3 of this pack", "draft - areas are estimates"],
 ["3", "IEE Checklist Report (System template)", "System generates at Step 6; content from pages 2 to 5", "pending the System account"],
 ["4", "Environmental Impact and Management Plan checklist", "page 4 of this pack", "ready"],
 ["5", "PEMAPS", "page 5 of this pack", "draft - rates are estimates"],
 ["6", "Notarized Sworn Statement of Accountability", "page 6 of this pack; notary in Daet or Jose Panganiban", "ready to sign"],
 ["7", "LGU certification of land-use compatibility (zoning / locational clearance)", "MPDO, Jose Panganiban - request letter 5 of the ancillary bundle", "not yet requested"],
 ["8", "Geotagged photographs, at least four, facing inward from N, S, E and W, with GPS and date imprinted, taken within 30 days of submission", "Allan or the crew, using a GPS camera application", "to be taken in the week of filing"],
 ["9", "Site Development Plan signed by a PRC-licensed professional", "Stephen Lloyd's drawings, signed by a licensed engineer or architect", "OPEN - blocks the filing"],
 ["10", "Proof of authority over the site: OCT and tax declaration", "fresh certified true copy from the Registry of Deeds, Daet; tax declaration from the Municipal Assessor - request letters 3 and 4 of the ancillary bundle", "OCT copy on file; tax declaration not yet in Allan's name"],
 ["11", "Proof of payment of P5,070.00 at LandBank on the System's Order of Payment", "Allan", "at Step 6"],
 ["12", "DENR-CENRO certification of land classification status", "CENRO with jurisdiction over Jose Panganiban - request letter 6 of the ancillary bundle", "not yet requested"],
 ["13-15", "Protected area, ancestral domain and tenurial instruments", "not expected to apply; confirmed by item 12", "-"],
 ["16-17", "Amendment-only items", "not applicable - this is a new application", "-"]]
DOCS.append({"title": "8 - Filing checklist and route (ECC Online, IEE Checklist, new application)",
 "addr": [], "subject": "", "body": [], "tables": [("", CHK, [1.4, 6.6, 5.3, 3.4])],
 "after": [("<b>Route.</b> Register once at ecconline.emb.gov.ph/live and upload R1 to R3. At Step 2 screen the project as <i>metallic mineral "
   "or ore processing</i> with an annual input of 3,000 tonnes, which returns Category B, IEE Checklist, Regional Office. Fill Steps 3 to 5 "
   "from pages 2, 3 and 5 of this pack. At Step 6 the System issues the Order of Payment; pay P5,070.00 at any LandBank branch; notarize "
   "the IEE Checklist Report and the Sworn Statement of Accountability; upload everything and submit. The Citizen's Charter of the Regional "
   "Office gives twenty (20) working days from a complete set with proof of payment; a request for additional information or a site "
   "inspection stops the clock. On release, have the Certificate notarized and upload it back - the System requires it."),
  ("<b>Afterwards.</b> Register the tailings storage facility with the Regional Office; secure the Permit to Operate for the standby "
   "generator before commissioning; have the Pollution Control Officer accredited; calendar the semi-annual Compliance Monitoring Reports "
   "from the first semester of operations. The Certificate is then filed with the Mines and Geosciences Bureau as acceptance requirement A6 "
   "of the Mineral Processing Permit application.")]})

# ---------- shared renderers ----------
def plain(t): return t.replace('<b>','').replace('</b>','').replace('<i>','').replace('</i>','')

doc = Document()
for s in doc.sections:
    s.top_margin = s.bottom_margin = Inches(0.8); s.left_margin = s.right_margin = Inches(0.9)
doc.styles['Normal'].font.name = 'Times New Roman'; doc.styles['Normal'].font.size = Pt(11)
def para(text, bold=False, align=None, size=None, space=5):
    p = doc.add_paragraph(); r = p.add_run(plain(text)); r.bold = bold or text.startswith('<b>')
    if size: r.font.size = Pt(size)
    if align == 'c': p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == 'j': p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space); return p
para("AVI GOLD PROCESSING PLANT - APPLICATION FOR AN ENVIRONMENTAL COMPLIANCE CERTIFICATE (IEE CHECKLIST, CATEGORY B) - EMB REGION V - "
     "DRAFT-HELD, prepared 19 September 2026, nothing filed", bold=True, align='c', size=11)
para("Contents: " + " | ".join(d["title"] for d in DOCS), align='j', size=9)
for d in DOCS:
    doc.add_page_break()
    for k, t in HEAD: para(t, bold=(k=='b'), align='c', size=(13 if k=='b' else 9.5), space=0)
    para(""); para(d["title"], bold=True, size=10, space=4)
    for t in d.get("addr", []): para(t, bold=t.startswith('<b>'), space=0)
    if d["subject"]: para(""); para(d["subject"], bold=True, align='j')
    para("")
    for t in d.get("body", []): para(t, align='j' if len(t) > 60 else None)
    for cap, rows, _w in d.get("tables", []):
        if cap: para(""); para(cap, bold=True, size=10)
        tb = doc.add_table(rows=0, cols=len(rows[0])); tb.style = 'Table Grid'
        for i, row in enumerate(rows):
            c = tb.add_row().cells
            for j, v in enumerate(row):
                c[j].text = plain(v)
                for pp in c[j].paragraphs:
                    for rr in pp.runs:
                        rr.font.size = Pt(8.5); rr.bold = (i == 0 or v.startswith('<b>'))
        para("")
    for t in d.get("after", []): para(t, align='j', size=9.5)
doc.save("AVI_ECC_APPLICATION_PACK_2026-09.docx")

ss = getSampleStyleSheet()
J = ParagraphStyle('J', parent=ss['Normal'], fontName='Times-Roman', fontSize=10.5, leading=13.5, alignment=TA_JUSTIFY, spaceAfter=5)
S = ParagraphStyle('S', parent=J, fontSize=8, leading=9.8, spaceAfter=1, alignment=0)
N = ParagraphStyle('N', parent=J, fontSize=9.5, leading=12)
L = ParagraphStyle('L', parent=J, alignment=0, spaceAfter=0)
C = ParagraphStyle('C', parent=J, alignment=TA_CENTER, spaceAfter=0, fontSize=9.5)
CB = ParagraphStyle('CB', parent=C, fontName='Times-Bold', fontSize=12.5)
B = ParagraphStyle('B', parent=J, fontName='Times-Bold')
T = ParagraphStyle('T', parent=J, fontName='Times-Bold', fontSize=10, textColor='#444444')
def P(t, st=J): return Paragraph(t if t else "&nbsp;", st)
story = [P("AVI GOLD PROCESSING PLANT - APPLICATION FOR AN ENVIRONMENTAL COMPLIANCE CERTIFICATE (IEE CHECKLIST, CATEGORY B) - EMB REGION V "
           "- DRAFT-HELD, prepared 19 September 2026, nothing filed", B),
         P("Contents: " + " | ".join(d["title"] for d in DOCS), N)]
for d in DOCS:
    story.append(PageBreak())
    for k, t in HEAD: story.append(P(t, CB if k=='b' else C))
    story.append(Spacer(1, 8)); story.append(P(d["title"], T)); story.append(Spacer(1, 4))
    for t in d.get("addr", []): story.append(P(t, L))
    if d["subject"]: story.append(Spacer(1, 8)); story.append(P(d["subject"], B))
    story.append(Spacer(1, 4))
    for t in d.get("body", []): story.append(P(t))
    for cap, rows, w in d.get("tables", []):
        if cap: story.append(Spacer(1, 6)); story.append(P(cap, B))
        tb = Table([[P(c, S) for c in row] for row in rows], colWidths=[x*cm for x in w], repeatRows=1)
        tb.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 0.5, colors.black),
                                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eeeeee')),
                                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                                ('LEFTPADDING', (0,0), (-1,-1), 3), ('RIGHTPADDING', (0,0), (-1,-1), 3),
                                ('TOPPADDING', (0,0), (-1,-1), 2), ('BOTTOMPADDING', (0,0), (-1,-1), 2)]))
        story.append(tb); story.append(Spacer(1, 6))
    for t in d.get("after", []): story.append(P(t, N))
SimpleDocTemplate("AVI_ECC_APPLICATION_PACK_2026-09.pdf", pagesize=A4, leftMargin=1.9*cm, rightMargin=1.9*cm,
                  topMargin=1.7*cm, bottomMargin=1.7*cm).build(story)
print("built %d instruments" % len(DOCS))
