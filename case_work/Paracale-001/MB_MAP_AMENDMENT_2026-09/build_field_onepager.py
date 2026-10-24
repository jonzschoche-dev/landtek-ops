#!/usr/bin/env python3
"""Build the printable field one-pager (titles KML on a phone, offline GPS).

Reads INOCALLA_TITLES_P1616_T2194.kml for the sketch, writes FIELD_GPS_ONEPAGER.html,
then renders FIELD_GPS_ONEPAGER.pdf with headless Chrome.
"""
import math
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
KML = HERE / "INOCALLA_TITLES_P1616_T2194.kml"
HTML = HERE / "FIELD_GPS_ONEPAGER.html"
PDF = HERE / "FIELD_GPS_ONEPAGER.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def polygons():
    src = KML.read_text()
    out = []
    for pm in re.findall(r"<Placemark>(.*?)</Placemark>", src, re.S):
        name = re.search(r"<name>(.*?)</name>", pm).group(1)
        coords = re.search(r"<coordinates>(.*?)</coordinates>", pm, re.S).group(1).split()
        pts = [tuple(map(float, c.split(",")[:2])) for c in coords]
        out.append((name, pts))
    return out


def sketch_svg(polys, w=300, h=300, pad=18):
    lat0 = sum(p[1] for _, pts in polys for p in pts) / sum(len(pts) for _, pts in polys)
    kx = math.cos(math.radians(lat0))  # equal-scale lon/lat
    xs = [p[0] * kx for _, pts in polys for p in pts]
    ys = [p[1] for _, pts in polys for p in pts]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    s = (min(w, h) - 2 * pad) / span
    ox = pad + ((w - 2 * pad) - (max(xs) - min(xs)) * s) / 2
    oy = pad + ((h - 2 * pad) - (max(ys) - min(ys)) * s) / 2

    def xy(lon, lat):
        return ox + (lon * kx - min(xs)) * s, oy + (max(ys) - lat) * s

    styles = [("#1f9d3a", "rgba(31,157,58,.18)"), ("#e07b00", "rgba(224,123,0,.18)")]
    labels = ["LOT 4\nOCT P-1616\n15.2 ha", "T-2194\nGracesen plant lot\n13.4 ha"]
    parts = []
    for (name, pts), (stroke, fill), label in zip(polys, styles, labels):
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(*p) for p in pts))
        parts.append(f'<polygon points="{d}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>')
        cx = sum(xy(*p)[0] for p in pts[:-1]) / (len(pts) - 1)
        cy = sum(xy(*p)[1] for p in pts[:-1]) / (len(pts) - 1)
        lines = label.split("\n")
        for i, ln in enumerate(lines):
            wt = "700" if i == 0 else "400"
            parts.append(
                f'<text x="{cx:.1f}" y="{cy + (i - (len(lines) - 1) / 2) * 13:.1f}" text-anchor="middle" '
                f'font-size="{11 if i == 0 else 9.5}" font-weight="{wt}" fill="#222">{ln}</text>'
            )
    # north arrow + 200 m scale bar
    m_per_deg = 111_320
    bar = 200 / m_per_deg * s
    parts.append(f'<g transform="translate({w - 22},26)"><path d="M0,-14 L6,4 L0,0 L-6,4 Z" fill="#222"/>'
                 f'<text y="16" text-anchor="middle" font-size="10" font-weight="700">N</text></g>')
    parts.append(f'<g transform="translate(14,{h - 12})"><rect width="{bar:.1f}" height="4" fill="#222"/>'
                 f'<text y="-4" font-size="9">200 m</text></g>')
    return f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Inocalla Titles Field Guide</title>
<style>
@page {{ size: A4; margin: 12mm 13mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 10.6pt/1.38 -apple-system, "Helvetica Neue", Arial, sans-serif; color: #1a1a1a; margin: 0; }}
h1 {{ font-size: 17pt; margin: 0 0 2px; }}
.sub {{ color: #555; margin: 0 0 10px; font-size: 10pt; }}
.grid {{ display: grid; grid-template-columns: 1fr 300px; gap: 14px; }}
h2 {{ font-size: 11.5pt; margin: 10px 0 4px; padding: 3px 8px; background: #1a1a1a; color: #fff; border-radius: 3px; }}
ol {{ margin: 0; padding-left: 20px; }}
li {{ margin-bottom: 4px; }}
.box {{ border: 1.5px solid #1a1a1a; border-radius: 6px; padding: 8px 10px; margin-top: 10px; }}
.warn {{ border-color: #b3261e; background: #fdf1f0; }}
.key {{ margin: 6px 0 0; font-size: 9.8pt; }}
.sw {{ display: inline-block; width: 12px; height: 12px; border: 2px solid; vertical-align: -2px; margin-right: 5px; }}
.map {{ border: 1px solid #bbb; border-radius: 6px; padding: 4px; }}
.cap {{ font-size: 8.6pt; color: #555; margin-top: 3px; }}
.check li {{ list-style: none; margin-left: -18px; }}
.check li::before {{ content: "\\2610  "; font-size: 12pt; }}
b.k {{ background: #fff3b0; padding: 0 2px; }}
.foot {{ margin-top: 10px; font-size: 8.4pt; color: #666; border-top: 1px solid #ccc; padding-top: 4px; }}
</style></head><body>
<h1>Inocalla Titles: Find the Boundaries on Your Phone</h1>
<p class="sub">Capacuan, Paracale, Camarines Norte · Works with <b>no cell signal</b>, because GPS needs only open sky · App: <b>Organic Maps</b> (free, iPhone &amp; Android)</p>

<div class="grid"><div>
<h2>PART 1 · AT HOME, ON WI-FI (do this first)</h2>
<ol>
<li><b>Install Organic Maps</b> from the App Store or Google Play.</li>
<li>Open it, search <b>“Paracale”</b>, and tap <b>Download</b> for the offline map. Wait until it finishes.</li>
<li>Open the file <b>INOCALLA_TITLES.gpx</b> (sent by Messenger, email or Drive).<br>
<b>iPhone:</b> tap the file → <b>Share</b> → <b>Organic Maps</b>.<br>
<b>Android:</b> tap the file → <b>Open with</b> → <b>Organic Maps</b>.</li>
<li>Tap the <b>★ star icon</b> and check that <b>“Inocalla titles”</b> is listed and turned on. You should see two boundary lines with a label pin in the middle of each lot.</li>
<li><b>Test:</b> turn on Airplane Mode, keep Location ON, and open the app. The two lots must still show.</li>
</ol>

<h2>PART 2 · ONSITE</h2>
<ol>
<li>Location <b>ON</b> (Airplane Mode is fine and saves battery). Tap the <b>➤ arrow</b> to show your <b>blue dot</b>.</li>
<li>Stand in the open <b>1–2 minutes</b> so the GPS can lock on.</li>
<li><b>Tap a boundary line or label pin</b> to see which title it is (see map at right). Inside the lines = inside that title.</li>
<li><b>Mark spots:</b> long-press where you stand → <b>Save</b> → give it a name.</li>
<li>Optional: <b>record a track</b> while walking a boundary.</li>
</ol>

<div class="box">
<b>PLEASE PIN THESE AND SEND THEM BACK:</b>
<ul class="check" style="margin:4px 0 0;padding-left:18px">
<li><b class="k">The Gracesen processing plant</b>. No document records its exact location.</li>
<li>Any <b>corner monument / concrete marker</b> found on a boundary</li>
<li>Houses, fences, roads or diggings near or across a line</li>
</ul>
</div>
</div>

<div>
<div class="map">{svg}</div>
<div class="cap">Sketch of the two titled lots as plotted (not a survey).</div>
<div class="key"><span class="sw" style="border-color:#1f9d3a;background:rgba(31,157,58,.18)"></span><b>Lot 4, Psu-143364 · OCT P-1616</b><br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Allan V. Inocalla · 15.2069 ha</div>
<div class="key"><span class="sw" style="border-color:#e07b00;background:rgba(224,123,0,.18)"></span><b>T-2194 / H-44920 · Gracesen plant lot</b><br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;13.3690 ha · touches Lot 4 on its north side</div>

<div class="box warn">
<b>HOW ACCURATE?</b><br>
Phone GPS: about <b>5–10 m</b>.<br>
Title lines: approximate, <b>±20–30 m</b>.<br>
Within <b>~30 m</b> of a line, you can't tell from the phone which side you're on.<br>
<b>Do NOT use the phone to set fences or corners.</b> That needs a geodetic engineer.
</div>

<div class="box">
<b>BATTERY:</b> bring a power bank · dim the screen · Airplane Mode ON, Location ON.
</div>
</div></div>

<div class="foot">LandTek · Inocalla (Paracale-001) · Internal field use only. Do not share outside the team. · Prepared {date}</div>
</body></html>"""


def main():
    import datetime
    html = PAGE.format(svg=sketch_svg(polygons()), date=datetime.date.today().strftime("%d %b %Y"))
    HTML.write_text(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={PDF}", HTML.as_uri()], check=True, capture_output=True)
    print(PDF)


if __name__ == "__main__":
    main()
