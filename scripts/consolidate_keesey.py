#!/usr/bin/env python3
"""Consolidate the Keesey client folder to the canonical template: reparent each
ad-hoc top-level folder UNDER its canonical category (move-only, nothing flattened
or deleted, groupings preserved as sub-folders). After this the Keesey top level
matches TEMPLATE-CLIENT-LTC-000."""
import sys
from googleapiclient.discovery import build
from google.oauth2 import service_account

ROOT = "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP"
CONSOLIDATE = {  # ad-hoc folder -> canonical parent (becomes parent/adhoc)
    "Titles": "Properties",
    "SPA": "Legal",
    "ATTY BOTOR": "Legal",
    "Surveys/Maps": "Evidence",
    "Google Earth": "Evidence",
    "Transfer Investigation": "Evidence",
    "DAR/Landbank": "Correspondence",
    "LGU MERCEDES": "Correspondence",
    "TAXES/Municipal Assesor ": "Finance",
    "Candy": "_Needs Review",
}
CANONICAL = {"Cases", "Conversations", "Correspondence", "Documents", "Evidence",
             "Finance", "Financials", "Legal", "Projects", "Properties",
             "_Needs Review", "_Processed"}

creds = service_account.Credentials.from_service_account_file(
    "/root/landtek/google-creds.json", scopes=["https://www.googleapis.com/auth/drive"])
svc = build("drive", "v3", credentials=creds, cache_discovery=False)
apply = "--apply" in sys.argv


def kids(fid):
    return svc.files().list(q=f"'{fid}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'",
                            fields="files(id,name)", pageSize=1000, supportsAllDrives=True,
                            includeItemsFromAllDrives=True).execute()["files"]


top = svc.files().list(q=f"'{ROOT}' in parents and trashed=false",
                       fields="files(id,name)", supportsAllDrives=True,
                       includeItemsFromAllDrives=True).execute()["files"]
clients_id = [f["id"] for f in top if f["name"] == "01 - Clients"][0]
clients = {f["name"]: f["id"] for f in kids(clients_id)}
keesey = [v for k, v in clients.items() if "Worrick" in k][0]
subs = {f["name"]: f["id"] for f in kids(keesey)}

for adhoc, parent in CONSOLIDATE.items():
    if adhoc not in subs:
        print(f"  (not found, skip): {adhoc!r}")
        continue
    if parent not in subs:
        print(f"  (parent missing, skip): {parent!r}")
        continue
    print(f"  {'MOVE' if apply else 'PLAN'}  {adhoc!r}  ->  {parent}/")
    if apply:
        svc.files().update(fileId=subs[adhoc], addParents=subs[parent],
                           removeParents=keesey, fields="id", supportsAllDrives=True).execute()

after = sorted(f["name"] for f in kids(keesey))
extra = [n for n in after if n not in CANONICAL]
print(f"\nKeesey top level now: {len(after)} folders")
print("  non-canonical remaining:", extra or "NONE — clean ✓")
