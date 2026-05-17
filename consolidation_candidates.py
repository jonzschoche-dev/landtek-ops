#!/usr/bin/env python3
"""consolidation_candidates — find near-duplicate document clusters.

Per Jonathan 2026-05-17: "generally repeat entries are candidates for
consolidation." This script identifies clusters of MWK-001 documents that
likely represent the SAME underlying instrument captured via multiple ingest
paths (Drive uploads, Gmail forwards, scanner re-scans).

NO legal interpretation. NO assumptions about what the clusters mean. Just
structural-feature matching at 5 tiers of confidence:

  TIER 1  same content_hash                     → byte-identical (certain dup)
  TIER 2  same text_hash                        → text-identical OCR (certain dup)
  TIER 3  same lot+area+price+grantor+grantee   → very likely same instrument
  TIER 4  same area+price+grantor+grantee       → likely same (lot string differs by OCR)
  TIER 5  same classification + |date_diff|<=90d + filename-stem similarity → possible

For each cluster:
  - Proposes a canonical doc# (richest metadata + longest text + earliest id)
  - Lists members with their differing fields
  - Outputs CSV row per cluster + per member, with cluster_id linkage

NO consolidation is applied by this script. The CSV is the artifact you
batch-approve from. A separate --apply pass would write to
documents.related_to_doc_id with relationship_kind='near_duplicate'.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
sys.path.insert(0, "/root/landtek")
import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


def normalize_party(s):
    if not s: return ""
    s = s.lower()
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^a-z ]', '', s)
    # Strip role qualifiers
    for noise in ("attorney in fact of the heirs of mary w keesey",
                  "attorney in fact",
                  "attorneyinfact",
                  "as attorneyinfact",
                  "married to ",
                  "filipino",
                  "of legal age"):
        s = s.replace(noise, "")
    return s.strip()


def normalize_lot(s):
    if not s: return ""
    # Strip portion qualifier, all non-alphanumerics
    s = re.sub(r'\(portion\)|portion', '', s.lower())
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def fetch_docs(cur, case_file):
    cur.execute("""
        SELECT id, classification, smart_filename, original_filename,
               document_title, doc_date_norm,
               content_hash, text_hash,
               lot_number, area_sqm, consideration_price,
               grantor_seller, grantee_buyer,
               length(coalesce(extracted_text, '')) AS text_len,
               drive_link, drive_file_id,
               strategic_relevance AS description,
               related_to_doc_id, relationship_kind
          FROM documents
         WHERE case_file = %s
         ORDER BY id
    """, (case_file,))
    return cur.fetchall()


def filename_stem(d):
    """Normalize filename for fuzzy comparison.
    Strips gmail hex-hash prefix, extension, special chars, dates."""
    raw = d.get("smart_filename") or d.get("original_filename") or ""
    raw = re.sub(r'^[0-9a-f]{8,}__', '', raw)         # strip gmail hash
    raw = re.sub(r'\.(pdf|docx|jpg|jpeg|png|heic|tif|tiff)$', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', raw)   # strip ISO dates
    raw = re.sub(r'\bYYYY-MM-DD\b', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'\((\d+)\)', '', raw)               # strip "(3)" copy markers
    raw = re.sub(r'\bcopy of\b', '', raw, flags=re.IGNORECASE)
    raw = re.sub(r'[^a-zA-Z0-9]+', '', raw).lower()
    return raw[:40]


def canonical_pick(members):
    """Pick the canonical doc within a cluster. Heuristic:
       1. Most populated metadata fields (classification, date, lot, price, grantor, grantee).
       2. Then longest extracted_text.
       3. Then lowest id.
    """
    def score(d):
        meta = sum(1 for k in ("classification","doc_date_norm","lot_number",
                                "area_sqm","consideration_price",
                                "grantor_seller","grantee_buyer") if d.get(k))
        return (meta, d.get("text_len") or 0, -d["id"])
    return max(members, key=score)


def apply_from_csv(case_file):
    """Read the most recent consolidation_candidates_<case>_<date>.csv and apply
    UPDATEs ONLY for rows where APPROVED_FOR_MERGE is 'Y' or 'TRUE' (case-insensitive)."""
    out_dir = Path("/root/landtek/drafts")
    matching = sorted(out_dir.glob(f"consolidation_candidates_{case_file}_*.csv"))
    if not matching:
        print(f"No CSV found for {case_file}. Run without --apply first.")
        return
    csv_path = matching[-1]
    print(f"Reading {csv_path}")

    # Group rows by cluster
    from collections import defaultdict
    clusters = defaultdict(list)
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            clusters[row["cluster_id"]].append(row)

    conn = psycopg2.connect(DSN); conn.autocommit = False
    cur = conn.cursor()

    applied = 0
    skipped_no_approval = 0
    skipped_no_canonical = 0
    for cid, rows in clusters.items():
        # Any approval in this cluster?
        approved = [r for r in rows if (r.get("APPROVED_FOR_MERGE") or "").strip().upper() in ("Y", "TRUE", "YES", "1")]
        if not approved:
            skipped_no_approval += 1
            continue
        # Identify the canonical (must be marked CANONICAL in is_canonical column)
        canon_rows = [r for r in rows if r["is_canonical"] == "CANONICAL"]
        if not canon_rows:
            skipped_no_canonical += 1
            print(f"  cluster {cid}: ⚠ no row marked CANONICAL — skipping")
            continue
        canon_id = int(canon_rows[0]["doc_id"])
        # For each approved dup row, set related_to_doc_id = canon
        for r in approved:
            doc_id = int(r["doc_id"])
            if doc_id == canon_id:
                continue  # canonical can be approved but doesn't link to itself
            cur.execute("""
                UPDATE documents
                   SET related_to_doc_id  = %s,
                       relationship_kind  = 'near_duplicate',
                       updated_at         = NOW()
                 WHERE id = %s
                   AND (related_to_doc_id IS NULL OR related_to_doc_id <> %s)
            """, (canon_id, doc_id, canon_id))
            if cur.rowcount > 0:
                print(f"  cluster {cid}: doc#{doc_id} → near_duplicate of doc#{canon_id}")
                applied += 1
    conn.commit()
    print(f"\n✓ Applied: {applied} consolidations")
    print(f"  Skipped: {skipped_no_approval} clusters (no APPROVED_FOR_MERGE marks)")
    print(f"  Skipped: {skipped_no_canonical} clusters (no row marked CANONICAL)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="MWK-001")
    ap.add_argument("--apply", action="store_true",
                    help="Read latest CSV and apply consolidations for APPROVED_FOR_MERGE='Y' rows")
    args = ap.parse_args()

    if args.apply:
        apply_from_csv(args.case)
        return

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    docs = fetch_docs(cur, args.case)
    print(f"Scanning {len(docs)} documents for near-duplicate clusters...")

    # Build per-doc fingerprints at each tier
    by_content_hash = defaultdict(list)
    by_text_hash    = defaultdict(list)
    by_amount_area  = defaultdict(list)   # area+price (loose; group then verify)
    by_lot_amount   = defaultdict(list)   # normalized-lot+area+price

    def _surname_tokens(s):
        """Extract 2+ unique surname-like tokens (4+ chars, no role words)."""
        if not s: return set()
        s = re.sub(r'[^a-zA-Z ]', ' ', s.lower())
        words = [w for w in s.split() if len(w) >= 4]
        # Drop role/legal-status words that aren't names
        drop = {"legal","filipino","married","attorney","fact","heirs","mary",
                "worrick","keesey","representative","authority","resident","extension"}
        return {w for w in words if w not in drop}

    # Cache token sets per doc
    doc_tokens = {}
    for d in docs:
        if d.get("content_hash"):
            by_content_hash[d["content_hash"]].append(d)
        if d.get("text_hash"):
            by_text_hash[d["text_hash"]].append(d)
        if d.get("area_sqm") is not None and d.get("consideration_price") is not None:
            fp_aa = (float(d["area_sqm"]), float(d["consideration_price"]))
            by_amount_area[fp_aa].append(d)
            lot = normalize_lot(d.get("lot_number"))
            if lot:
                by_lot_amount[(lot, fp_aa)].append(d)
        doc_tokens[d["id"]] = {
            "grantor": _surname_tokens(d.get("grantor_seller")),
            "grantee": _surname_tokens(d.get("grantee_buyer")),
        }

    # Tier 3 + Tier 4: from area+price groups, sub-cluster by party overlap
    by_tier3, by_tier4 = defaultdict(list), defaultdict(list)
    for (lot, aa), members in by_lot_amount.items():
        if len(members) < 2: continue
        by_tier3[(lot, aa)] = members  # already lot-matched
    for aa, members in by_amount_area.items():
        if len(members) < 2: continue
        # Require at least one party-name token in common across all members
        token_intersection = None
        for m in members:
            tokens = doc_tokens[m["id"]]["grantee"] | doc_tokens[m["id"]]["grantor"]
            if token_intersection is None:
                token_intersection = tokens
            else:
                token_intersection &= tokens
        if token_intersection:
            by_tier4[aa] = members

    # ── TIER 5 — loose: same date + same instrument_type + shared party token ──
    # Per Jonathan 2026-05-17: catches SPAs / tax decs / LRA certs ingested
    # multiple times where price/area aren't extracted but date + type + a
    # party in common is enough signal to flag as candidate dup.
    by_date_type = defaultdict(list)
    for d in docs:
        if not d.get("doc_date_norm") or not d.get("classification"):
            continue
        by_date_type[(d["doc_date_norm"], d["classification"].lower())].append(d)
    by_tier5 = defaultdict(list)
    for fp, members in by_date_type.items():
        if len(members) < 2: continue
        # Sub-cluster by shared party token (grantor OR grantee)
        token_to_docs = defaultdict(list)
        for m in members:
            mt = doc_tokens[m["id"]]["grantor"] | doc_tokens[m["id"]]["grantee"]
            for tok in mt:
                token_to_docs[tok].append(m)
        for tok, group in token_to_docs.items():
            if len(group) >= 2:
                # Dedup by id within group
                seen = set(); uniq = []
                for m in group:
                    if m["id"] not in seen:
                        seen.add(m["id"]); uniq.append(m)
                if len(uniq) >= 2:
                    by_tier5[(fp, tok)] = uniq

    # ── TIER 6 — looser still: same date + similar filename stem ──
    # Catches ingest-path duplicates where party fields aren't populated
    # at all (untyped scans, screenshots, gmail attachments) but the
    # filename gives away the duplication.
    by_date_stem = defaultdict(list)
    for d in docs:
        if not d.get("doc_date_norm"): continue
        stem = filename_stem(d)
        if len(stem) < 6: continue   # skip too-short stems (high false-pos rate)
        by_date_stem[(d["doc_date_norm"], stem)].append(d)
    by_tier6 = defaultdict(list)
    for fp, members in by_date_stem.items():
        if len(members) >= 2:
            by_tier6[fp] = members

    # Union-find cluster collection: each tier ADDS to or EXTENDS clusters.
    # When a tier's fingerprint group includes docs already in cluster X, it
    # merges new members into X (instead of skipping the whole tier).
    cluster_membership = {}   # doc_id → cluster_id
    cluster_data = {}         # cluster_id → {tier, fp, members:[doc_dict,...]}
    cluster_tier_origin = {}  # cluster_id → tier_name (where it started)
    next_cid = 1

    def merge_or_create(members, tier_name, fp):
        nonlocal next_cid
        if len(members) < 2: return
        existing_cids = {cluster_membership[m["id"]] for m in members
                          if m["id"] in cluster_membership}
        if not existing_cids:
            cid = next_cid; next_cid += 1
            cluster_data[cid] = {"tier": tier_name, "fp": fp, "members": list(members)}
            cluster_tier_origin[cid] = tier_name
            for m in members:
                cluster_membership[m["id"]] = cid
            return
        # Merge into the lowest existing cid; absorb any others
        target = min(existing_cids)
        for cid in existing_cids - {target}:
            for m in cluster_data[cid]["members"]:
                cluster_data[target]["members"].append(m)
                cluster_membership[m["id"]] = target
            del cluster_data[cid]
        # Add any new docs
        existing_ids = {m["id"] for m in cluster_data[target]["members"]}
        for m in members:
            if m["id"] not in existing_ids:
                cluster_data[target]["members"].append(m)
                cluster_membership[m["id"]] = target

    # Process in confidence order (most-specific first)
    for fp, members in by_content_hash.items():
        merge_or_create(members, "TIER1_content_hash", fp)
    for fp, members in by_text_hash.items():
        merge_or_create(members, "TIER2_text_hash", fp)
    for fp, members in by_tier3.items():
        merge_or_create(members, "TIER3_lot+area+price+parties", fp)
    for fp, members in by_tier4.items():
        merge_or_create(members, "TIER4_area+price+parties_(lot_fuzzy)", fp)
    for fp, members in by_tier5.items():
        merge_or_create(members, "TIER5_date+type+party_token", fp)
    for fp, members in by_tier6.items():
        merge_or_create(members, "TIER6_date+filename_stem", fp)

    # Convert to the same shape downstream code expects
    clusters = []
    for cid, data in cluster_data.items():
        clusters.append({
            "tier": cluster_tier_origin[cid] + (
                " +extensions" if data["tier"] != cluster_tier_origin[cid] else ""),
            "fingerprint": str(data["fp"])[:200],
            "members": data["members"],
        })
    clusters.sort(key=lambda c: (-len(c["members"]), c["tier"]))

    # Write CSV
    out_dir = Path("/root/landtek/drafts"); out_dir.mkdir(exist_ok=True)
    today = date.today().isoformat()
    csv_path = out_dir / f"consolidation_candidates_{args.case}_{today}.csv"
    md_path  = out_dir / f"consolidation_candidates_{args.case}_{today}.md"

    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["APPROVED_FOR_MERGE",   # ← far-left blank approval column
                    "cluster_id","tier","member_count","is_canonical",
                    "doc_id","date","classification","filename",
                    "lot_number","area_sqm","price","grantor","grantee",
                    "text_len","drive_link","fingerprint"])
        for cid, cluster in enumerate(clusters, 1):
            canon = canonical_pick(cluster["members"])
            for m in cluster["members"]:
                w.writerow([
                    "",   # APPROVED_FOR_MERGE — blank by default; user marks Y/TRUE
                    cid, cluster["tier"], len(cluster["members"]),
                    "CANONICAL" if m["id"] == canon["id"] else "dup",
                    m["id"], m.get("doc_date_norm"), m.get("classification"),
                    (m.get("smart_filename") or m.get("original_filename") or "")[:80],
                    m.get("lot_number"), m.get("area_sqm"), m.get("consideration_price"),
                    (m.get("grantor_seller") or "")[:60],
                    (m.get("grantee_buyer") or "")[:60],
                    m.get("text_len"),
                    m.get("drive_link") or "",
                    cluster["fingerprint"],
                ])

    # Write Markdown summary
    md = [f"# Consolidation Candidates — {args.case} ({today})", "",
          f"_{len(clusters)} clusters identified · {sum(len(c['members']) for c in clusters)} documents involved._",
          "",
          "_Tiered confidence: TIER1/2 = byte- or text-identical (certain). "
          "TIER3 = same lot+area+price+parties (very likely same instrument). "
          "TIER4 = same area+price+parties, lot string differs (likely same; OCR variance on lot)._",
          "",
          "_NO consolidation applied. Review CSV, designate canonicals, then "
          "apply via separate UPDATE pass._",
          ""]
    for cid, cluster in enumerate(clusters, 1):
        canon = canonical_pick(cluster["members"])
        md.append(f"## Cluster {cid} — {cluster['tier']} — {len(cluster['members'])} docs")
        md.append("")
        md.append(f"| doc# | role | date | classification | filename | text_len |")
        md.append("|---|---|---|---|---|---|")
        for m in cluster["members"]:
            role = "**CANONICAL**" if m["id"] == canon["id"] else "dup"
            fname = (m.get("smart_filename") or m.get("original_filename") or "")[:55]
            md.append(f"| {m['id']} | {role} | {m.get('doc_date_norm') or '—'} | "
                       f"{m.get('classification') or '—'} | {fname} | {m.get('text_len')} |")
        md.append("")
        # Shared facts
        if cluster["members"][0].get("area_sqm") and cluster["members"][0].get("consideration_price"):
            m0 = cluster["members"][0]
            md.append(f"- **Shared**: area={m0['area_sqm']} sqm · price=P{float(m0['consideration_price']):,.2f} · "
                       f"grantor={(m0.get('grantor_seller') or '')[:50]} → grantee={(m0.get('grantee_buyer') or '')[:50]}")
            md.append("")

    md_path.write_text("\n".join(md))

    print(f"\n{len(clusters)} clusters identified involving {sum(len(c['members']) for c in clusters)} documents")
    print(f"  Tier breakdown:")
    tier_counts = defaultdict(int)
    for c in clusters:
        tier_counts[c["tier"]] += 1
    for t, n in sorted(tier_counts.items()):
        print(f"    {t:50s}: {n} cluster(s)")
    print(f"\nWrote:")
    print(f"  {csv_path}")
    print(f"  {md_path}")
    print(f"\nReview the CSV. To apply, run with --apply once you've confirmed.")

    # Print top clusters to terminal
    print("\n" + "═"*80)
    print("TOP CLUSTERS (by member count)")
    print("═"*80)
    for cid, cluster in enumerate(clusters[:5], 1):
        canon = canonical_pick(cluster["members"])
        print(f"\nCluster {cid} ({cluster['tier']}, {len(cluster['members'])} members):")
        for m in cluster["members"]:
            role = "CANONICAL" if m["id"] == canon["id"] else "       dup"
            print(f"  {role}  doc#{m['id']:>4d}  {(m.get('classification') or '?')[:18]:18s}  "
                  f"{(m.get('doc_date_norm') or '—').__str__():12s}  "
                  f"text_len={m.get('text_len'):>6d}  "
                  f"{(m.get('smart_filename') or '')[:45]}")


if __name__ == "__main__":
    main()
