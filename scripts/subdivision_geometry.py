#!/usr/bin/env python3
"""subdivision_geometry.py — collect + validate + map the Psd-221861 subdivision lots.

The single sheet doc 287 (LRC Psd-221861, "Subdivision Survey of Lot 2, LRC Psd-12802,
TCT T-4497", surveyed 1975 by Ernesto L. Velante) prints a per-lot LINES/BEARINGS/DISTANCES
table for every lot 2-A..2-X, plus a TIE-LINES table (each lot's corner-1 bearing/distance
from monument BLLM No. 2) and the aggregate area (139,132 m²). This module carries the
transcribed courses, validates each ring by the survey truth-gates, and writes the verified
shapes to `parcels` so they become mappable.

Truth discipline:
  * A lot is ACCEPTED only if its ring CLOSES (<=1.5 m) — closure is the gate.
  * The printed area is an INDEPENDENT validator (reported, flagged if off > a few %).
  * Where a single distance was ambiguous on the scan (this 1975 hand-lettering blurs
    9/4 and 3/7), it is RECOVERED from the closure constraint and accepted only if the
    recovered value is a plausible re-read AND the independent area then matches
    (courses tagged `_recovered`). Bearing-level errors are NOT auto-recovered — those
    lots are left FLAGGED for a dedicated re-read rather than fabricated.

  python3 subdivision_geometry.py            # validate + report
  python3 subdivision_geometry.py --ingest   # write verified lots to parcels (MWK-001)

Tie-line note: the tie-DISTANCE column on doc 287 is fold-damaged (only 2-A's 261.63 m
survives, corroborated by TCT T-32911). Absolute assembly of every lot off BLLM No. 2 is
therefore blocked on that column — the verified per-lot SHAPES are stored local (corner 1
at origin); georeferencing follows once the tie distances are re-OCR'd or a control point
is surveyed. Tie-line BEARINGS (readable) are retained here for that step.
"""
from __future__ import annotations
import argparse, math, os, sys, itertools

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
SOURCE_DOC = 287
MATTER = "MWK-001"
CLIENT = "MWK-001"
CLOSE_GATE = 1.5   # metres

def az(ns, dg, mn, ew):
    a = dg + mn / 60.0; ns = ns.upper(); ew = ew.upper()
    return {('N','E'): a, ('S','E'): 180-a, ('S','W'): 180+a, ('N','W'): 360-a}[(ns, ew)]

def ring(courses):
    x = y = 0.0; pts = [(0.0, 0.0)]
    for ns, dg, mn, ew, d in courses:
        r = math.radians(az(ns, dg, mn, ew)); x += d*math.sin(r); y += d*math.cos(r); pts.append((x, y))
    clo = math.hypot(x, y)
    s = sum(pts[i][0]*pts[i+1][1]-pts[i+1][0]*pts[i][1] for i in range(len(pts)-1))
    return clo, abs(s)/2.0, pts

# ---- transcribed lot tables from doc 287 (Psd-221861). EW '?' = uncertain quadrant.
# Distances marked "# rec" were closure-recovered from an ambiguous digit (9/4, 3/7) and
# confirmed by the independent stated area.
LOTS = {
 "2-A": (8706, [('N',76,12,'W',70.45),('N',14,46,'E',12.48),('N',14,46,'E',55.81),('N',14,46,'E',55.00),
                ('S',79,47,'E',66.00),('S',10,44,'W',74.63),('S',15,27,'W',52.82)]),
 "2-B": (266, [('S',14,46,'W',12.48),('N',76,12,'W',21.50),('N',12,25,'E',11.95),('S',77,35,'E',22.00)]),
 "2-C": (169, [('N',14,54,'E',12.72),('S',72,56,'E',13.49),('S',12,25,'W',11.95),('N',76,12,'W',14.00)]),
 "2-D": (211, [('N',76,12,'W',16.50),('N',15,37,'E',13.00),('S',75,12,'E',16.33),('S',14,54,'W',12.72)]),
 "2-E": (934, [('N',11,52,'E',53.29),('S',74,53,'E',17.71),('S',11,11,'W',29.19),
               ('S',15,37,'W',10.71),('S',15,37,'W',13.00),('N',76,12,'W',16.50)]),
 "2-F": (1622,[('S',14,46,'W',55.00),('N',75,40,'W',30.27),('N',15,10,'E',52.85),('S',79,47,'E',30.00)]),
 "2-H": (2047,[('N',13,52,'E',10.25),('N',13,51,'E',54.83),('S',79,47,'E',32.00),('S',15,20,'W',67.12),
               ('N',74,53,'W',17.71),('N',77,58,'W',12.51)]),
 "2-I": (105, [('N',77,58,'W',10.29),('N',13,53,'E',10.25),('S',77,58,'E',10.29),('S',13,52,'W',10.25)]),
 "2-J": (1079,[('N',77,58,'W',10.29),('S',15,52,'W',10.25),('N',77,58,'W',6.71),('N',12,51,'E',10.06),
               ('N',12,51,'E',30.00),('N',3,51,'E',24.54),('S',79,41,'E',22.00),('S',13,51,'W',54.83)]),  # 6-7 29.54->24.54 rec
 "2-K": (1866,[('N',76,12,'W',29.50),('N',1,23,'E',22.34),('N',76,30,'W',5.00),('N',13,15,'E',30.22),
               ('S',78,28,'E',8.30),('S',77,58,'E',6.71),('S',77,58,'E',10.29),('S',77,58,'E',12.51),('S',11,52,'W',53.29)]),
 "2-L": (223, [('N',7,46,'E',21.89),('S',76,30,'E',4.00),('S',76,30,'E',5.00),('S',1,23,'W',22.34),('N',76,12,'W',11.50)]),
 # 2-M from its TITLE — TCT T-32912 (doc 142), back-page technical description.
 # Settles three things the plan couldn't: course 3-4 is N 74-05 W 37.78 (the plan's hand
 # "24" is a 7; my closure search had already fingered 74 as the only fit), course 11-12 is
 # 4.00 (not 9.00), and the area is 1,895 (not the 2,000/2,047 floating in other docs).
 # Course 6-7 is S 79-35 E — the cert's faint typewriter S reads as N, but N gives closure
 # 7.16 vs 0.027 for S, and S puts it collinear with 5-6/7-8 as the plan shows.
 "2-M": (1895, [('N',76,12,'W',4.00),('N',7,46,'E',21.89),('N',74,5,'W',37.78),('N',15,18,'E',36.15),
                ('S',79,36,'E',15.01),('S',79,35,'E',19.74),('S',79,35,'E',18.00),('S',12,51,'W',10.06),
                ('N',78,28,'W',8.30),('S',13,15,'W',30.22),('N',76,30,'W',4.00),('S',7,46,'W',21.89)]),
 # 2-N: HELD. The earlier "recovery" of the closing course 6-1 (53.50->57.42) was cosmetic —
 # course 6-1 is the LAST course, so its length changes the closure metric but moves NO vertex.
 # The real ~3.9 m defect is in courses 1-5 and is unidentified. Leaving it in corrupted every
 # lot assembled through it (2-X and its dependents drifted ~4.1 m off their printed tie
 # distances). Held until its true course is recovered. Lesson: closure alone can be gamed by
 # editing the closing course — the tie table is what caught this.
 "2-O": (172, [('N',14,44,'E',16.00),('S',76,12,'E',10.50),('S',12,58,'W',16.00),('N',76,12,'W',11.00)]),
 "2-P": (172, [('N',76,12,'W',11.00),('N',16,31,'E',16.01),('S',76,12,'E',10.50),('S',16,31,'W',16.00)]),
 "2-Q": (1022,[('S',79,43,'E',17.50),('S',2,51,'W',24.54),('S',12,51,'W',30.00),('N',79,35,'W',18.00),('N',9,20,'E',54.30)]),
 "2-R": (1010,[('S',9,20,'W',54.30),('N',79,35,'W',19.79),('N',11,42,'E',54.29),('S',79,47,'E',17.50)]),
 "2-S": (877, [('N',20,9,'E',25.00),('S',70,9,'E',34.00),('S',11,41,'W',24.21),('N',71,43,'W',37.59)]),
 "2-T": (522, [('S',70,9,'E',18.00),('S',20,9,'W',25.00),('S',20,9,'W',4.00),('N',70,9,'W',18.00),('N',20,9,'E',29.01)]),
 "2-U": (1283,[('S',10,30,'W',16.00),('N',70,9,'W',15.00),('S',20,0,'W',20.00),('N',70,9,'W',30.00),
               ('N',20,36,'E',35.79),('S',70,9,'E',42.00)]),
 "2-V": (635, [('S',20,0,'W',38.50),('N',70,9,'W',16.00),('N',18,31,'E',38.51),('S',70,9,'E',17.00)]),
 # 2-W from its TITLE (doc 289, Agcaoili, Lot 2-W) — clean typed technical description.
 # NB: the plan's hand-lettering reads 49/41 which I had wrongly "corrected" to 79/11; the title
 # settles it. Closure+area are rotation-invariant, so the gate could NOT catch that error —
 # the title (and the tie-bearing cross-check) is what catches a rotated ring.
 "2-W": (1250, [('S',49,0,'E',50.00),('S',41,0,'W',25.00),('N',49,0,'W',50.00),('N',41,0,'E',25.00)]),
 # 2-X — the residual, from its TITLE technical description (doc 562). Course 7-8 reads 39.09
 # in that doc's OCR but MUST be 50.00: points 6..9 are the notch Lot 2-W occupies, and 2-W's
 # own title gives that side as 50.00. With it, the 36-course ring closes 0.047 m and encloses
 # 106,901.7 vs the stated 106,918 (0.015%) — two documents corroborating each other.
 "2-X": (106918, [('N',76,12,'W',89.97),('N',72,54,'W',453.46),('N',72,8,'W',145.05),('N',18,19,'E',240.99),
                  ('S',49,0,'E',21.10),('S',41,0,'W',25.00),('S',49,0,'E',50.00),('N',41,0,'E',25.00),
                  ('S',49,0,'E',45.90),('S',60,11,'E',285.36),('S',70,9,'E',142.62),('S',18,31,'W',38.51),
                  ('S',70,9,'E',16.00),('N',20,0,'E',38.50),('S',70,9,'E',33.50),('S',20,36,'W',35.79),
                  ('S',70,9,'E',30.00),('N',20,0,'E',20.00),('S',70,9,'E',15.00),('N',10,30,'E',16.00),
                  ('S',70,9,'E',24.50),('S',20,9,'W',29.01),('S',70,9,'E',18.00),('N',20,9,'E',4.00),
                  ('S',71,43,'E',37.59),('N',11,41,'E',24.21),('S',79,47,'E',45.10),('S',11,42,'W',54.24),
                  ('N',79,36,'W',15.01),('N',57,49,'W',19.99),('S',13,18,'W',65.61),('N',76,12,'W',11.50),
                  ('N',12,58,'E',16.00),('N',76,12,'W',10.50),('N',76,12,'W',10.50),('S',16,31,'W',16.01)]),
}

# lots whose bearings (not distances) are still ambiguous on the scan — held, NOT fabricated
FLAGGED = {
 "2-G": (4148, "return-course bearing ambiguous (closure 70 m); needs frontier re-OCR"),
 "2-N": (2000, "closes only by editing the closing course (cosmetic); real ~3.9 m defect in courses 1-5 — corrupts anything assembled through it"),
}

# tie-line bearings from BLLM No. 2 to each lot's corner 1 (distances fold-damaged on doc 287)
TIE_BEARING = {"2-A":('N',86,31,'W',261.63),"2-B":('N',82,11,'W',None),"2-C":('N',83,33,'W',None),
 "2-D":('N',83,33,'W',None),"2-E":('N',82,56,'W',None),"2-F":('N',63,0,'W',None),"2-G":('N',82,11,'W',None),
 "2-H":('N',75,22,'W',None),"2-I":('N',75,22,'W',None),"2-J":('N',73,56,'W',None),"2-K":('N',82,50,'W',None),
 "2-L":('N',82,19,'W',None),"2-M":('N',82,19,'W',439.86),"2-N":('N',81,39,'W',None),"2-O":('N',81,20,'W',None),
 "2-P":('N',81,20,'W',None),"2-Q":('N',67,32,'W',None),"2-R":('N',67,32,'W',None),"2-S":('N',71,40,'W',None),
 "2-T":('N',69,6,'W',None),"2-U":('N',69,9,'W',None),"2-V":('N',69,16,'W',None),"2-W":('N',65,39,'W',1202.29),   # tie from title doc 289
 # 2-X tie from title doc 562. Its text reads "N 81 deg 14' E" but the E is an OCR slip for W:
 # the assembled mesh puts 2-X's corner 1 at N 81-14 W, 534.4 m — degrees, minutes AND distance
 # match the title exactly, only the quadrant letter differs. Geometry settles it.
 "2-X":('N',81,14,'W',534.40)}

def recovered_lots():
    """Lots whose courses were later recovered by frontier re-OCR (subdivision_reocr_retry.py)
    and written to subdivision_recovered_lots. Merged into the validated set so they flow into
    ingest + assembly automatically once unlocked."""
    try:
        import psycopg2
        c = psycopg2.connect(DSN); cur = c.cursor()
        cur.execute("SELECT to_regclass('public.subdivision_recovered_lots')")
        if not cur.fetchone()[0]:
            cur.close(); c.close(); return {}
        cur.execute("SELECT lot, stated_area, courses_json FROM subdivision_recovered_lots")
        out = {}
        for lot, area, cj in cur.fetchall():
            cs = cj if isinstance(cj, list) else __import__("json").loads(cj)
            out[lot] = (area, [tuple(x) for x in cs])
        cur.close(); c.close(); return out
    except Exception:
        return {}

def validate():
    out = {}
    lots = dict(LOTS); lots.update(recovered_lots())   # DB-recovered lots join the set
    for name, (stated, courses) in lots.items():
        clo, area, pts = ring(courses)
        out[name] = {"stated": stated, "closure": clo, "area": area, "pts": pts,
                     "ok": clo <= CLOSE_GATE, "courses": courses}
    return out

def wkt_local(pts):
    ring_pts = pts + [pts[0]] if pts[0] != pts[-1] else pts
    return "POLYGON((" + ", ".join(f"{x:.3f} {y:.3f}" for x, y in ring_pts) + "))"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", action="store_true", help="write verified lots to parcels")
    a = ap.parse_args()
    res = validate()
    npass = sum(1 for r in res.values() if r["ok"])
    print(f"Psd-221861 subdivision — {npass}/{len(res)} lots close within {CLOSE_GATE} m "
          f"(+{len(FLAGGED)} flagged for re-OCR)\n")
    tot = 0.0
    for name in sorted(res):
        r = res[name]
        off = abs(r["area"]-r["stated"])/r["stated"]*100 if r["stated"] else 0
        flag = "" if off <= 3 else "  <area check>"
        print(f"  {name:4s} {'OK ' if r['ok'] else 'HOLD'} closure={r['closure']:6.3f} m  "
              f"area={r['area']:9.1f} vs {r['stated']:>7} ({off:.2f}%){flag}")
        if r["ok"]:
            tot += r["area"]
    for name, (st, why) in FLAGGED.items():
        if name in res:            # recovered by re-OCR — no longer flagged
            continue
        print(f"  {name:4s} FLAG  {why}")
    held = sum(st for st, _ in FLAGGED.values())
    print(f"\n  verified lot area total: {tot:,.0f} m² + held {held:,.0f} m² = {tot+held:,.0f} m² "
          f"vs the plan's stated aggregate 139,132 m² (delta {abs(tot+held-139132):,.0f} m²)")

    if a.ingest:
        import psycopg2
        conn = psycopg2.connect(DSN); conn.autocommit = True; cur = conn.cursor()
        cur.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS lot_label text")
        cur.execute("ALTER TABLE parcels ADD COLUMN IF NOT EXISTS tie_bearing text")
        n = 0
        for name in sorted(res):
            r = res[name]
            if not r["ok"] or name == "2-A":   # 2-A already held as T-32911 parcel 166
                continue
            title = f"PSD-221861 Lot {name}"
            tb = TIE_BEARING.get(name)
            tbtxt = (f"{tb[0]} {tb[1]}-{tb[2]:02d} {tb[3]} from BLLM No.2" if tb else None)
            cur.execute("""INSERT INTO parcels
                (matter_code, title_no, source_doc_id, area_sqm, area_ha, closure_error_m,
                 calls, geom_wkt, stated_ha, area_matches, provenance_level, client_code,
                 lot_label, tie_bearing)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'inferred_corroborated',%s,%s,%s)
                ON CONFLICT DO NOTHING""",
                (MATTER, title, SOURCE_DOC, round(r["area"],1), round(r["area"]/10000,4),
                 round(r["closure"],3), len(r["courses"]), wkt_local(r["pts"]),
                 round(r["stated"]/10000,4), abs(r["area"]-r["stated"])/r["stated"]<=0.03,
                 CLIENT, name, tbtxt))
            n += cur.rowcount
        print(f"\ningested {n} verified subdivision lots into parcels (matter {MATTER}).")
        cur.close(); conn.close()

if __name__ == "__main__":
    main()
