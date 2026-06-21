#!/usr/bin/env python3
"""relevance.py — classify the surrounding corpus around a focal matter, labeled, never conflated. $0.

The fix for "extensive + conflated": for a focal matter (e.g., CV-26360) this fingerprints the matter
from its OWN verified record (party names + title numbers + key instruments), scans the surrounding
corpus, and tiers every document by its relevance — with a stated connection:

  CORE        — about this matter's property/chain (title + instrument/parties overlap)
  RELATED     — shares the chain/actors but is a DISTINCT proceeding (labeled with its real matter)
  CONTEXTUAL  — only a name in common (loose connection / background) — labeled, not discarded
  OFF-PROFILE — tagged to this matter but reads like a different proceeding (possible mis-file → verify)

Nothing is conflated or deleted; everything gets a label. Written to `matter_relevance` for outputs.

  python3 scripts/relevance.py --matter MWK-CV26360 [--apply]
"""
import argparse
import re

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
INSTRUMENTS = ["deed of absolute sale", "special power of attorney", "adverse claim",
               "deed of confirmation", "de la fuente", "keesey", "llamanzares", "buenaventura"]
OFF_MARKERS = ["supreme court", "certiorari", "perjury", "sandiganbayan", "court of appeals",
               "criminal case", "people of the philippines"]


def fingerprint(cur, mc):
    cur.execute("SELECT lower(party_name) FROM matter_parties WHERE matter_code=%s AND provenance_level='verified'", (mc,))
    parties = {r[0] for r in cur.fetchall() if r[0]}
    cur.execute("SELECT docket_number, respondent_entity_ids, plaintiff_entity_ids FROM matters WHERE matter_code=%s", (mc,))
    docket_raw, resp, plf = cur.fetchone() or (None, None, None)
    ids = list(resp or []) + list(plf or [])
    if ids:
        cur.execute("SELECT lower(canonical_name) FROM entities WHERE id = ANY(%s)", (ids,))
        parties |= {r[0] for r in cur.fetchall() if r[0] and len(r[0]) > 4}
    cur.execute("SELECT coalesce(statement,'')||' '||coalesce(excerpt,'') FROM matter_facts WHERE matter_code=%s AND provenance_level='verified'", (mc,))
    blob = " ".join(r[0] for r in cur.fetchall()).lower()
    titles = set(re.findall(r"\bt-?\d{3,5}\b", blob)) | set(re.findall(r"\b0\d{2}-\d{6,}\b", blob))
    dockets = set()
    if docket_raw:  # distinctive case code, e.g. sl-2026-0423-1891, cv-2026-360
        dockets |= {t for t in re.findall(r"[a-z]{1,4}-?\d[\d-]{4,}\d", docket_raw.lower()) if len(t) >= 6}
    return parties, titles, dockets


def classify(text, mc_doc, focal, parties, titles, dockets):
    t = (text or "").lower()
    ph = [p for p in parties if p and p in t]
    th = [x for x in titles if x in t]
    dh = [d for d in dockets if d in t]          # docket-code hit = definitively THIS case
    ih = [x for x in INSTRUMENTS if x in t]
    off = [x for x in OFF_MARKERS if x in t]
    anchors = th + dh
    conn = []
    if dh: conn.append("docket " + dh[0])
    if th: conn.append("titles " + ", ".join(sorted(th)[:3]))
    if ih: conn.append(", ".join(ih[:3]))
    if ph: conn.append("parties " + ", ".join(sorted(ph)[:2]))
    connection = "; ".join(conn) or "name/keyword overlap"
    if mc_doc == focal and off and not anchors and not ih:
        return "OFF-PROFILE", f"off-profile markers ({', '.join(off[:2])}) + no case anchor — possible mis-file, verify"
    if dh or (th and (ih or len(ph) >= 2)):
        tier = "CORE"
    elif anchors or len(ih) >= 2:
        tier = "RELATED"
    elif ph or ih:
        tier = "CONTEXTUAL"
    else:
        return None, None
    if mc_doc and mc_doc != focal and tier in ("CORE", "RELATED"):
        if not dh:                                # a docket match overrides cross-tag demotion
            tier = "RELATED"
        connection = f"belongs to {mc_doc}; shares " + connection
    return tier, connection


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matter", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    focal = a.matter
    c = psycopg2.connect(DSN); c.autocommit = True; cur = c.cursor()
    parties, titles, dockets = fingerprint(cur, focal)
    if not parties and not titles and not dockets:
        print(f"[relevance] {focal}: no verified fingerprint yet."); return
    # candidate docs: anything mentioning a strong token (titles, docket codes, or core actors)
    toks = list(titles) + list(dockets) + ["de la fuente", "keesey", "balane", "torralba"]
    like = " OR ".join(["extracted_text ILIKE %s"] * len(toks))
    cur.execute(f"""SELECT id, matter_code, coalesce(original_filename,smart_filename,'?'), left(extracted_text,16000)
                    FROM documents WHERE ({like}) ORDER BY id""", tuple(f"%{x}%" for x in toks))
    rows = cur.fetchall()
    if a.apply:
        cur.execute("""CREATE TABLE IF NOT EXISTS matter_relevance (
            focal_matter text, doc_id int, doc_matter text, tier text, connection text,
            filename text, updated_at timestamptz DEFAULT now(), UNIQUE(focal_matter, doc_id))""")
        cur.execute("DELETE FROM matter_relevance WHERE focal_matter=%s", (focal,))
    buckets = {"CORE": [], "RELATED": [], "CONTEXTUAL": [], "OFF-PROFILE": []}
    for did, mc_doc, fn, text in rows:
        tier, conn = classify(text, mc_doc, focal, parties, titles, dockets)
        if not tier:
            continue
        buckets[tier].append((did, mc_doc, fn, conn))
        if a.apply:
            cur.execute("""INSERT INTO matter_relevance (focal_matter,doc_id,doc_matter,tier,connection,filename)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (focal_matter,doc_id)
                DO UPDATE SET tier=EXCLUDED.tier, connection=EXCLUDED.connection""",
                (focal, did, mc_doc, tier, conn, fn[:120]))
    print("=" * 84)
    print(f"RELEVANCE MAP — surrounding corpus for {focal}  (fingerprint: {len(parties)} parties, {len(titles)} titles, {len(dockets)} dockets)")
    print("=" * 84)
    for tier in ("CORE", "RELATED", "CONTEXTUAL", "OFF-PROFILE"):
        items = buckets[tier]
        print(f"\n[{tier}] {len(items)}")
        for did, mc_doc, fn, conn in items[:12]:
            tag = f"({mc_doc})" if mc_doc and mc_doc != focal else ""
            print(f"   doc:{did:<5} {fn[:44]:44} {tag} — {conn[:60]}")
        if len(items) > 12:
            print(f"   …+{len(items)-12} more")
    if a.apply:
        print(f"\n[relevance] written to matter_relevance for {focal}")


if __name__ == "__main__":
    main()
