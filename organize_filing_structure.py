#!/usr/bin/env python3
"""Organize files into a human-navigable hierarchy (deploy 120).

For each document in the DB, creates a symlink with its canonical_filename
inside the appropriate folder under /root/landtek/uploads/STRUCTURED/.

Hierarchy:
  STRUCTURED/{case_folder}/{section}/{subsection}/canonical_filename
  STRUCTURED/00-INDEX.csv + 00-INDEX.pdf (top-level)

Idempotent. Symlinks are recreated on re-run.
"""
import argparse, csv, os, re, sys
from datetime import datetime, date
import psycopg2, psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
UPLOADS = "/root/landtek/uploads"
STRUCT = os.path.join(UPLOADS, "STRUCTURED")

CASE_LABEL = {
    "MWK-001":     "MWK-001-Heirs-of-Mary-Worrick-Keesey",
    "Paracale-001": "Paracale-001-Allan-Inocalla",
    None:          "UNKNOWN",
    "":            "UNKNOWN",
    "unknown":     "UNKNOWN",
    "Unknown":     "UNKNOWN",
    "Owner":       "LANDTEK-FIRM",
}

# Section assignment by execution_status + classification
SECTION_RULES = [
    # (predicate_fn, section)
    (lambda d: d["classification"] in ("Complaint", "Court Filing", "Motion", "Answer",
                                       "Reply", "Order", "Notice", "Memorandum", "Resolution"),
     "01-Pleadings"),
    (lambda d: d["classification"] in ("Judicial Affidavit", "Affidavit"), "07-Affidavits-Witnesses"),
    (lambda d: d["classification"] == "Title (TCT/OCT)" or
                  (d["classification"] or "").startswith("Title"), "02-Titles"),
    (lambda d: d["classification"] == "Tax Document", "03-Tax-Declarations"),
    (lambda d: d["classification"] in ("Deed", "Special Power of Attorney", "Power of Attorney"),
     "04-Deeds-and-SPAs"),
    (lambda d: d["classification"] in ("Letter", "Correspondence", "Demand Letter", "Email"),
     "05-Correspondence"),
    (lambda d: d["classification"] in ("Receipt", "Tax Document") and (d["execution_status"] == "executed_signed_only"),
     "06-Financial"),
    (lambda d: d["execution_status"] == "draft_unsigned",
     "01-Pleadings/Drafts-Pending-Filing"),
]


def pick_section(d):
    for pred, section in SECTION_RULES:
        try:
            if pred(d): return section
        except: pass
    return "99-Other"


def safe(s, maxlen=80):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(s or "")).strip("_")
    return s[:maxlen] or "unnamed"


def find_source_file(doc_id, smart_filename):
    """Find the actual file on disk."""
    candidates = []
    if smart_filename:
        safe_fn = re.sub(r"[^A-Za-z0-9._-]", "_", smart_filename)[:120]
        candidates += [
            os.path.join(UPLOADS, f"{doc_id}_{safe_fn}"),
            os.path.join(UPLOADS, "MWK-001", f"{doc_id}_{safe_fn}"),
            os.path.join(UPLOADS, "MWK-001", "email_attachments", f"em{doc_id}_{safe_fn}"),
            os.path.join(UPLOADS, "uncorrelated", "email_attachments", f"em{doc_id}_{safe_fn}"),
            os.path.join(UPLOADS, "Paracale-001", f"{doc_id}_{safe_fn}"),
        ]
    candidates += [
        os.path.join(UPLOADS, f"{doc_id}_drive.pdf"),
        os.path.join(UPLOADS, f"drive_{doc_id}_*.pdf"),
    ]
    for p in candidates:
        if "*" in p:
            import glob
            for g in glob.glob(p):
                if os.path.exists(g): return g
        elif os.path.exists(p):
            return p
    # Last resort: scan uploads for any file starting with the doc_id
    for root, _, files in os.walk(UPLOADS):
        if "STRUCTURED" in root: continue
        for f in files:
            if f.startswith(f"{doc_id}_") or f.startswith(f"em{doc_id}_"):
                return os.path.join(root, f)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true",
                    help="wipe and rebuild STRUCTURED/")
    ap.add_argument("--case", default=None)
    args = ap.parse_args()

    if args.rebuild and os.path.exists(STRUCT):
        import shutil
        shutil.rmtree(STRUCT)
        print(f"  ↺ wiped {STRUCT}")

    os.makedirs(STRUCT, exist_ok=True)

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    where = ["canonical_filename IS NOT NULL"]
    params = []
    if args.case:
        where.append("case_file = %s"); params.append(args.case)
    cur.execute(f"""
        SELECT id, canonical_filename, smart_filename, case_file, classification,
               execution_status, doc_date, doc_type AS dtype
          FROM documents
         WHERE {' AND '.join(where)}
         ORDER BY case_file, id
    """, params) if False else cur.execute(f"""
        SELECT id, canonical_filename, smart_filename, case_file, classification,
               execution_status, doc_date, '' AS dtype
          FROM documents
         WHERE {' AND '.join(where)}
         ORDER BY case_file, id
    """, params)
    docs = cur.fetchall()
    print(f"  organizing {len(docs)} docs …")

    linked = missing = 0
    by_folder = {}
    for d in docs:
        case_folder = CASE_LABEL.get(d["case_file"], "UNKNOWN")
        section = pick_section(d)
        target_dir = os.path.join(STRUCT, case_folder, section)
        os.makedirs(target_dir, exist_ok=True)

        src = find_source_file(d["id"], d["smart_filename"])
        link_path = os.path.join(target_dir, safe(d["canonical_filename"]))
        if not src:
            # No physical file — create a 0-byte placeholder with a .MISSING.txt note
            note_path = link_path + ".MISSING.txt"
            with open(note_path, "w") as f:
                f.write(f"Doc #{d['id']} canonical={d['canonical_filename']}\n")
                f.write(f"smart_filename={d['smart_filename']}\n")
                f.write(f"No source file found locally — exists only in DB.\n")
                f.write(f"If on Drive, drive_file_id is set; download via Drive UI.\n")
            missing += 1
        else:
            # Create symlink
            if os.path.islink(link_path) or os.path.exists(link_path):
                os.remove(link_path)
            os.symlink(src, link_path)
            linked += 1

        by_folder.setdefault(target_dir, []).append(d)

    print(f"  ✓ symlinks created: {linked}")
    print(f"  ⊘ missing physical: {missing}  (note files written)")

    # Per-folder INDEX.csv
    print(f"\n  generating INDEX.csv at {len(by_folder)} folders …")
    for folder, items in by_folder.items():
        idx_path = os.path.join(folder, "00-INDEX.csv")
        with open(idx_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["canonical_filename", "doc_id", "doc_date", "classification",
                        "execution_status", "smart_filename"])
            def _sort_key(x):
                dd = x.get("doc_date")
                if isinstance(dd, str):
                    try: dd = date.fromisoformat(dd)
                    except: dd = date(1900, 1, 1)
                if not dd: dd = date(1900, 1, 1)
                return (dd, x["id"])
            for d in sorted(items, key=_sort_key):
                w.writerow([d["canonical_filename"], d["id"],
                            d["doc_date"] or "", d["classification"] or "",
                            d["execution_status"] or "", d["smart_filename"] or ""])
    print(f"  ✓ wrote {len(by_folder)} INDEX.csv files")

    # Top-level INDEX.csv (manifest of all cases + folder counts)
    top_idx = os.path.join(STRUCT, "00-INDEX.csv")
    with open(top_idx, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_folder", "section", "file_count"])
        # Walk folder counts
        counts = {}
        for folder, items in by_folder.items():
            rel = os.path.relpath(folder, STRUCT)
            counts[rel] = len(items)
        for path, n in sorted(counts.items()):
            parts = path.split(os.sep)
            w.writerow([parts[0] if parts else "—",
                        os.sep.join(parts[1:]) if len(parts) > 1 else "—", n])

    # Top-level README
    readme = os.path.join(STRUCT, "README.md")
    with open(readme, "w") as f:
        f.write("# LandTek Law — Master Filing Structure\n\n")
        f.write(f"_Generated {datetime.now().isoformat(timespec='minutes')}_\n\n")
        f.write("This folder mirrors the office's physical filing cabinet.\n")
        f.write("If the server is down, every file is still here on this disk under its canonical name.\n\n")
        f.write("## Cases\n\n")
        cases_seen = set()
        for folder in sorted(by_folder.keys()):
            rel = os.path.relpath(folder, STRUCT)
            case = rel.split(os.sep)[0]
            if case in cases_seen: continue
            cases_seen.add(case)
            cur.execute("SELECT count(*) FROM documents WHERE COALESCE(case_file,'') = ANY(%s)",
                        ([k for k,v in CASE_LABEL.items() if v == case],))
            n = cur.fetchone()["count"]
            f.write(f"- **{case}/** — {n} documents\n")
        f.write("\n## Navigation\n\n")
        f.write("- `01-Pleadings/` — Complaints, Answers, Motions, Replies, Court Orders\n")
        f.write("  - `Civil-Case-26-360/` — Zschoche v Balane RTC matter\n")
        f.write("  - `ARTA-*/` — Anti-Red Tape filings\n")
        f.write("  - `Drafts-Pending-Filing/` — unfiled drafts (Ombudsman, SC, RTC)\n")
        f.write("- `02-Titles/` — TCT/OCT registry copies, active and cancelled\n")
        f.write("- `03-Tax-Declarations/` — ARP records from Mercedes assessor\n")
        f.write("- `04-Deeds-and-SPAs/` — Deeds of Sale/Donation, Special Powers of Attorney\n")
        f.write("- `05-Correspondence/` — letters between counsel, LGU, heirs\n")
        f.write("- `06-Financial/` — bills, receipts, bank statements, retainer agreements\n")
        f.write("- `07-Affidavits-Witnesses/` — sworn affidavits, judicial affidavits\n\n")
        f.write("Each folder contains `00-INDEX.csv` listing every document with its canonical name, doc-id, date, classification, and execution status.\n\n")
        f.write("## Naming convention\n\n")
        f.write("`{CASE}_{YYYY-MM-DD}_{TYPE}_{detail-slug}_{leo-id}.{ext}`\n\n")
        f.write("Example: `MWK_2026-04-24_NOTICE_pretrial-26-360_0392.pdf`\n\n")
        f.write("## Operator contact\n\n")
        f.write("- Atty. Jonathan P. Zschoche · jonathan@hayuma.org · Telegram @jjmoreno\n")
        f.write("- Atty. Bonifacio T. Barandon Jr. · Barandon Law Offices, Daet\n")

    print(f"  ✓ {top_idx}")
    print(f"  ✓ {readme}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
