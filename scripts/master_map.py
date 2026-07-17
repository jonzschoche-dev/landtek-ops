#!/usr/bin/env python3
"""MASTER MAP — TCT T-4497 (Lot 2, Psd-12802): outer boundary derived as the UNION of its
subdivision lots (raster trace), every parcel nested inside, over satellite."""
import json, math, io, urllib.request, psycopg2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

Z=17
def ll2t(lat,lng,z):
    n=2**z
    return ((lng+180)/360*n,
            (1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n)

c=psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"); cur=c.cursor()
cur.execute("SELECT parcel_code, coalesce(label,title_no), geom_geojson, area_sqm FROM map_parcels WHERE geom_geojson IS NOT NULL")
sub=[]; others=[]; balane=None
for pc,lab,g,ar in cur.fetchall():
    g=g if isinstance(g,dict) else json.loads(g)
    ring=g["coordinates"][0]
    if pc.startswith("MWK-PSD221861") or pc=="MWK-T-32911":
        lot="Lot 2-A" if pc=="MWK-T-32911" else lab.replace(" (Psd-221861)","")
        sub.append((lot,ring,float(ar or 0)))
    elif pc=="MWK-BALANE": balane=("BALANE 2126",ring,float(ar or 0))
    else: others.append((lab.split("(")[-1].rstrip(")"),ring,float(ar or 0)))

pts=[p for _,r,_ in sub for p in r]
lngs=[p[0] for p in pts]; lats=[p[1] for p in pts]
pad=0.0011
x0,y0=ll2t(max(lats)+pad,min(lngs)-pad,Z); x1,y1=ll2t(min(lats)-pad,max(lngs)+pad,Z)
tx0,ty0,tx1,ty1=int(x0),int(y0),int(x1),int(y1)
W=(tx1-tx0+1)*256; H=(ty1-ty0+1)*256
base=Image.new("RGB",(W,H),(18,18,18))
for tx in range(tx0,tx1+1):
    for ty in range(ty0,ty1+1):
        url=f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{Z}/{ty}/{tx}"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"landtek-ops"})
            with urllib.request.urlopen(req,timeout=20) as r:
                base.paste(Image.open(io.BytesIO(r.read())).convert("RGB"),((tx-tx0)*256,(ty-ty0)*256))
        except Exception as e: print("tile fail",tx,ty,str(e)[:36])
# upscale 1.6x for label room
SC=1.6
W2,H2=int(W*SC),int(H*SC)
base=base.resize((W2,H2),Image.LANCZOS)
def px(lat,lng):
    x,y=ll2t(lat,lng,Z); return ((x-tx0)*256*SC,(y-ty0)*256*SC)

d=ImageDraw.Draw(base,"RGBA")
def font(sz):
    try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",sz)
    except Exception: return None

# 1. subdivision lots — fill + outline + label
cols=[(66,133,244),(255,127,14),(52,168,83),(234,67,53),(171,71,188),(255,213,79),
      (0,188,212),(255,112,67),(124,179,66),(240,98,146),(120,144,156),(255,183,77)]
f14=font(15); f22=font(22); f30=font(30)
for i,(lab,ring,ar) in enumerate(sorted(sub,key=lambda f:f[0])):
    pr=[px(p[1],p[0]) for p in ring]
    col=cols[i%len(cols)]
    d.polygon(pr,fill=col+(64,))
    d.line(pr+[pr[0]],fill=(255,255,255,200),width=2)
    cx=sum(x for x,_ in pr[:-1])/(len(pr)-1); cy=sum(y for _,y in pr[:-1])/(len(pr)-1)
    t=lab.replace("Lot ","")
    tw=d.textlength(t,font=f14)
    d.rectangle([cx-tw/2-3,cy-9,cx+tw/2+3,cy+9],fill=(0,0,0,150))
    d.text((cx-tw/2,cy-8),t,fill="white",font=f14)

# 2. T-4497 estate boundary = raster union trace, drawn HEAVY
mask=Image.new("L",(W2,H2),0); md=ImageDraw.Draw(mask)
for _,ring,_ in sub:
    md.polygon([px(p[1],p[0]) for p in ring],fill=255)
mask=mask.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))   # heal seams
m=np.array(mask)>127
er=np.array(mask.filter(ImageFilter.MinFilter(9)))>127
outline=(m & ~er)
ys,xs=np.where(outline)
ov=Image.new("RGBA",(W2,H2),(0,0,0,0))
ovp=ov.load()
for x,y in zip(xs,ys): ovp[x,y]=(255,255,0,255)
ov=ov.filter(ImageFilter.MaxFilter(3))
base.paste(ov,(0,0),ov)

# 3. derivative / contested parcels nested inside (Balane = red)
if balane:
    lab,ring,ar=balane
    pr=[px(p[1],p[0]) for p in ring]
    d.polygon(pr,fill=(255,0,0,90)); d.line(pr+[pr[0]],fill=(255,40,40,255),width=4)
    cx=sum(x for x,_ in pr[:-1])/(len(pr)-1); cy=sum(y for _,y in pr[:-1])/(len(pr)-1)
    t="BALANE ...2126"
    tw=d.textlength(t,font=f14)
    d.rectangle([cx-tw/2-3,cy+8,cx+tw/2+3,cy+26],fill=(120,0,0,220))
    d.text((cx-tw/2,cy+9),t,fill="white",font=f14)
for lab,ring,ar in others:
    pr=[px(p[1],p[0]) for p in ring]
    d.line(pr+[pr[0]],fill=(255,255,255,160),width=2)
    cx=sum(x for x,_ in pr[:-1])/(len(pr)-1); cy=sum(y for _,y in pr[:-1])/(len(pr)-1)
    t=lab.replace("TCT ","")
    tw=d.textlength(t,font=f14)
    d.text((cx-tw/2,cy-8),t,fill=(255,255,255,220),font=f14)

# 4. header + legend
d.rectangle([0,0,W2,86],fill=(0,0,0,185))
d.text((14,8),"MASTER MAP — TCT T-4497 (Lot 2, Psd-12802) · Heirs of Mary Worrick Keesey · Mercedes, Camarines Norte",fill=(255,255,60),font=f22)
d.text((14,40),"Estate boundary (yellow) = union of the 23 mapped Psd-221861 lots · 139,132 m2 stated · anchor Lot 2-A · BLLM No.2 tie-validated 0.01deg",fill="white",font=f14)
d.text((14,60),"Red = contested Balane title ...2126 (Lot 2-X-6-I-4-C-1) inside Lot 2-X · thin white = other placed derivative TCTs · 2-G (Marquez) unmapped",fill=(255,180,180),font=f14)
base.save("/tmp/master_map.png"); print("saved",W2,H2,"| sub lots:",len(sub),"| others:",len(others),"| balane:",bool(balane))
