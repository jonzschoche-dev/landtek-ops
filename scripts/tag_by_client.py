#!/usr/bin/env python3
"""tag_by_client.py — stop cross-client contamination. The Drive folder
'/01 - Clients/<Client>/' IS the authoritative client boundary. Walk the tree
once, map every file_id -> its client, and set documents.case_file accordingly so
Inocalla (LTC-001) docs can never be retrieved as Keesey (MWK-001) docs.

Dry-run by default; pass --apply to write."""
import argparse, sys
import psycopg2, psycopg2.extras
from googleapiclient.discovery import build
from google.oauth2 import service_account

ROOT = "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP"
# client folder name -> case_file code
# case_file codes MUST match the registered clients (clients table / case_theories._clients).
# Allan Inocalla's matters are coded Paracale-001 (Paracale Gold Co. + Inocalla Estate).
CLIENT_MAP = {
    "Allan Inocalla - LTC-001": "Paracale-001",
    "Heirs of Mary Worrick Keesey- LTC-002": "MWK-001",
    "Owner": "Owner",
}
creds = service_account.Credentials.from_service_account_file(
    "/root/landtek/google-creds.json", scopes=["https://www.googleapis.com/auth/drive.readonly"])
svc = build("drive", "v3", credentials=creds, cache_discovery=False)


def walk(fid, client):
    """Return {file_id: client_code} for every file under a client subtree."""
    out, pt = {}, None
    while True:
        r = svc.files().list(q=f"'{fid}' in parents and trashed=false",
                             fields="nextPageToken, files(id,name,mimeType)", pageSize=1000,
                             pageToken=pt, supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        for f in r.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                out.update(walk(f["id"], client))
            else:
                out[f["id"]] = client
        pt = r.get("nextPageToken")
        if not pt:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    # find the /01 - Clients folder
    r = svc.files().list(q="name='01 - Clients' and mimeType='application/vnd.google-apps.folder'",
                         fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    clients_fid = r["files"][0]["id"]
    subs = svc.files().list(q=f"'{clients_fid}' in parents and mimeType='application/vnd.google-apps.folder'",
                            fields="files(id,name)", pageSize=100, supportsAllDrives=True,
                            includeItemsFromAllDrives=True).execute()["files"]

    file_client = {}
    for s in subs:
        code = CLIENT_MAP.get(s["name"])
        if not code or "TEMPLATE" in s["name"]:
            continue
        file_client.update(walk(s["id"], code))
    print(f"mapped {len(file_client)} Drive files to a client")

    conn = psycopg2.connect("postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, drive_file_id, case_file FROM documents WHERE drive_file_id IS NOT NULL")
    rows = cur.fetchall()

    changes = {}
    for r in rows:
        want = file_client.get(r["drive_file_id"])
        # never override intentional system buckets: 'Owner' (cross-link contract,
        # e.g. doc#326 stays Owner + surfaces to MWK via matter_code) and 'Archive'.
        if want and want != r["case_file"] and r["case_file"] not in ("Owner", "Archive"):
            changes.setdefault((r["case_file"], want), []).append(r["id"])

    print("\n=== retag plan (current -> client) ===")
    for (cur_cf, want), ids in sorted(changes.items(), key=lambda x: -len(x[1])):
        print(f"  {str(cur_cf):14} -> {want:14}  {len(ids)} docs   e.g. {ids[:6]}")
    total = sum(len(v) for v in changes.values())
    print(f"\n{total} docs would be re-tagged")

    if args.apply and total:
        for (cur_cf, want), ids in changes.items():
            cur.execute("UPDATE documents SET case_file=%s WHERE id = ANY(%s)", (want, ids))
        print(f"APPLIED — {total} docs re-tagged to their true client")
    elif not args.apply:
        print("(dry-run — pass --apply to write)")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
