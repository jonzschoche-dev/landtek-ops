#!/usr/bin/env python3
"""Walk the LANDTEK Drive structure with the SA, return folder IDs for each case's Legal/."""
import os, sys, json
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY = "/root/landtek/google-creds.json"
LANDTEK_ROOT = "1BMnZL7LWoH9tWq0C9RdCTaAQBGhtL8CP"

creds = service_account.Credentials.from_service_account_file(
    SA_KEY, scopes=["https://www.googleapis.com/auth/drive.readonly"]
)
drive = build("drive", "v3", credentials=creds)

def list_folder(parent_id):
    """Return [{'id', 'name'}] of all sub-folders of parent_id."""
    out, token = [], None
    while True:
        resp = drive.files().list(
            q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="nextPageToken, files(id,name)",
            pageToken=token, pageSize=200,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        out.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token: break
    return out

# Level 1: LANDTEK root
landtek_subs = list_folder(LANDTEK_ROOT)
print("LANDTEK root subfolders:")
for f in landtek_subs:
    print(f"  {f['id']}  {f['name']}")

# Find "01 - Clients" (tolerant match)
clients_root = None
for f in landtek_subs:
    if "client" in f["name"].lower():
        clients_root = f
        break
if not clients_root:
    sys.exit("Could not find '01 - Clients' folder under LANDTEK root")
print(f"\nClients root: {clients_root['id']}  {clients_root['name']}")

# Level 2: each client folder
client_folders = list_folder(clients_root["id"])
print(f"\nClient folders ({len(client_folders)}):")
for f in client_folders:
    print(f"  {f['id']}  {f['name']}")

# Map: case_file → Legal folder ID
MAPPING_HINTS = {
    "MWK-001":     ["mary worrick", "mwk", "heirs of mary"],
    "Paracale-001":["allan inocalla", "ltc-001", "paracale"],
    "Owner":       ["owner"],
}

case_to_legal_id = {}
for case_file, hints in MAPPING_HINTS.items():
    matched_client = None
    for cf in client_folders:
        if any(h in cf["name"].lower() for h in hints):
            matched_client = cf
            break
    if not matched_client:
        print(f"\n  ⚠ no client folder matched {case_file!r}")
        continue
    legals = list_folder(matched_client["id"])
    legal = next((l for l in legals if l["name"].strip().lower() == "legal"), None)
    if not legal:
        print(f"\n  ⚠ no Legal/ subfolder inside {matched_client['name']!r}")
        continue
    case_to_legal_id[case_file] = legal["id"]
    print(f"\n  ✓ {case_file:14s} → {legal['id']}  ({matched_client['name']} / Legal)")

print("\n=== RESULT ===")
print(json.dumps(case_to_legal_id, indent=2))
