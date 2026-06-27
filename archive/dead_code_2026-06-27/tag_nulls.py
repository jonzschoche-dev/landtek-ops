#!/usr/bin/env python3
"""Tighten client tags on NULL-case_file docs. Priority: pull PARACALE (Inocalla)
docs out of the MWK-scoped NULL pool by content/filename signal, then tag the
clearly-MWK ones in. Anything ambiguous stays NULL (still MWK-scoped, low risk).
Uses only registered client codes (MWK-001, Paracale-001)."""
import psycopg2

conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
conn.autocommit = True
cur = conn.cursor()

SIG = ("lower(coalesce(smart_filename,original_filename,'') || ' ' || "
       "coalesce(left(extracted_text,6000),''))")

# Paracale/Inocalla-SPECIFIC signals (avoid bare 'inocalla' — Allan is also an MWK
# witness; require terms unique to the Paracale matter).
PARACALE = (r"paracale|bombita|nibdc|gumamela|capacuan|13-131220|98-88750|"
            r"vicente inocalla|ace inocalla|marilou inocalla|jesus inocalla|"
            r"beatriz villafria|jose panganiban|apsa|mineral|illegal min|civil case 4992|labo civil")
MWK = (r"keesey|worrick|balane|t-4497|de la fuente|dela fuente|mercedes|zschoche|"
       r"26-360|32917|52540|32911|pajarillo|macale")

cur.execute(f"""UPDATE documents SET case_file='Paracale-001'
    WHERE master_form='digital' AND case_file IS NULL AND {SIG} ~ %s""", (PARACALE,))
para = cur.rowcount
cur.execute(f"""UPDATE documents SET case_file='MWK-001'
    WHERE master_form='digital' AND case_file IS NULL AND {SIG} ~ %s""", (MWK,))
mwk = cur.rowcount

cur.execute("SELECT coalesce(case_file,'(null)'), count(*) FROM documents WHERE master_form='digital' GROUP BY 1 ORDER BY 2 DESC")
print(f"tagged {para} NULL docs -> Paracale-001, {mwk} NULL docs -> MWK-001\n")
print("case_file distribution now:")
for cf, n in cur.fetchall():
    print(f"  {n:4}  {cf}")
cur.close(); conn.close()
