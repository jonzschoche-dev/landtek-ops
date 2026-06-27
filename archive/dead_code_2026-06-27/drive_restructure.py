#!/usr/bin/env python3
"""drive_restructure.py — file loose Drive documents into their client/category
folder, using the corpus's client tag (case_file) + classification. Moves only
(canDelete is False, so nothing is ever destroyed). Dry-run by default.

  python3 drive_restructure.py --source root            # plan
  python3 drive_restructure.py --source root --apply     # execute
  --source one of: root | ScannerPro | Drafts
"""
import argparse
import psycopg2, psycopg2.extras
from googleapiclient.discovery import build
from google.oauth2 import service_account

ROOT = "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP"
CLIENT_FOLDER = {  # case_file -> client folder NAME under '01 - Clients'
    "MWK-001": "Heirs of Mary Worrick Keesey- LTC-002",
    "Paracale-001": "Allan Inocalla - LTC-001",
    "Owner": "Owner",
}
creds = service_account.Credentials.from_service_account_file(
    "/root/landtek/google-creds.json", scopes=["https://www.googleapis.com/auth/drive"])
svc = build("drive", "v3", credentials=creds, cache_discovery=False)


def kids(fid, folders_only=False, name=None):
    q = f"'{fid}' in parents and trashed=false"
    if folders_only:
        q += " and mimeType='application/vnd.google-apps.folder'"
    if name:
        q += f" and name='{name}'"
    return svc.files().list(q=q, fields="files(id,name,mimeType)", pageSize=1000,
                            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()["files"]


def ensure_folder(parent_id, name, apply):
    found = [f for f in kids(parent_id, True) if f["name"] == name]
    if found:
        return found[0]["id"]
    if not apply:
        return f"<new:{name}>"
    f = svc.files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder",
                                 "parents": [parent_id]}, fields="id", supportsAllDrives=True).execute()
    return f["id"]


def client_from_name(name):
    """Fallback client detection for untagged files (e.g. Google-Doc drafts not in
    the corpus): infer from distinctive names in the filename."""
    n = (name or "").lower()
    if any(k in n for k in ("inocalla", "paracale", "bombita", "vicente", "panganiban",
                            "gumamela", "capacuan", "pgc", "nibdc")):
        return "Allan Inocalla - LTC-001"
    if any(k in n for k in ("keesey", "worrick", "patricia", "balane", "mercedes",
                            "zschoche", "de la fuente", "dela fuente", "botor", "macale",
                            "pajarillo", "4497", "26-360", "1378", "1210", "guardianship")):
        return "Heirs of Mary Worrick Keesey- LTC-002"
    return None


def category(classification, doc_date, fname=""):
    # classification is often NULL on loose scans — the FILENAME usually says the type.
    c = ((classification or "") + " " + (fname or "")).lower()
    yr = (str(doc_date)[:4] if doc_date and str(doc_date)[:4].isdigit() else None)
    if any(k in c for k in ("letter", "correspond", "reply", "notice", "government",
                            "inquiry", "request")):
        return ["Correspondence", yr] if yr else ["Correspondence"]
    if any(k in c for k in ("complaint", "motion", "order", "resolution", "court", "pleading",
                            "affidavit", "power of attorney", "spa", "verification", "petition",
                            "manifestation", "submission")):
        return ["Legal"]
    if any(k in c for k in ("title", "tct", "tax")):
        return ["Properties"]
    if any(k in c for k in ("receipt", "invoice", "payment", "finance", "statement")):
        return ["Finance"]
    return ["_Needs Review"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="root", help="root | ScannerPro | Drafts")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--into", help="force all files into this client subfolder (overrides category, e.g. Drafts)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    top = kids(ROOT)
    clients_id = [f["id"] for f in top if f["name"] == "01 - Clients"][0]
    client_ids = {f["name"]: f["id"] for f in kids(clients_id, True)}

    if args.source == "root":
        src_id, items = ROOT, [f for f in top if f["mimeType"] != "application/vnd.google-apps.folder"]
    else:
        src_id = [f["id"] for f in top if f["name"] == args.source][0]
        items = [f for f in kids(src_id) if f["mimeType"] != "application/vnd.google-apps.folder"]

    conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    moved = skipped = 0
    for f in items:
        if args.limit and moved >= args.limit:
            break
        cur.execute("""SELECT case_file, classification, doc_date FROM documents
                       WHERE drive_file_id=%s LIMIT 1""", (f["id"],))
        r = cur.fetchone()
        cf = (r or {}).get("case_file")
        folder_name = CLIENT_FOLDER.get(cf)
        if not folder_name or folder_name not in client_ids:
            folder_name = client_from_name(f["name"])  # fallback for untagged drafts
        if not folder_name or folder_name not in client_ids:
            print(f"  SKIP  {f['name'][:46]:46}  (client={cf or 'untagged'})")
            skipped += 1
            continue
        path = [args.into] if args.into else category((r or {}).get("classification"), (r or {}).get("doc_date"), f["name"])
        parent = client_ids[folder_name]
        for seg in path:
            parent = ensure_folder(parent, seg, args.apply)
        dest = f"{folder_name}/" + "/".join(path)
        print(f"  {'MOVE' if args.apply else 'PLAN'}  {f['name'][:42]:42} -> {dest}")
        if args.apply and isinstance(parent, str) and not parent.startswith("<new"):
            prev = ",".join(svc.files().get(fileId=f["id"], fields="parents",
                            supportsAllDrives=True).execute().get("parents", []))
            svc.files().update(fileId=f["id"], addParents=parent, removeParents=prev,
                               fields="id", supportsAllDrives=True).execute()
        moved += 1
    print(f"\n[{args.source}] {moved} {'moved' if args.apply else 'to move'}, {skipped} skipped (untagged/unknown client)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
