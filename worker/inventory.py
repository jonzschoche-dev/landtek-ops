"""Phase 1 — scan and catalog three Drive folders, report counts/types/empty subfolders.

Outputs:
  stdout summary
  /root/landtek/drive_inventory.json (full file list with paths)
"""
import sys, json
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, str(Path(__file__).parent))

from config import GOOGLE_CREDS

FOLDERS = {
    "Paracale-001 (Allan Inocalla - LTC-001)": "1AWqoEaWGI4_d-s3zOrAHnA9pOFTFgPCm",
    "MWK-001 (Heirs of Mary Worrick Keesey - LTC-002)": "1S_FftmsxCJIZuKEUycHpJwzCbkxW0BGR",
    "AI Processing inbox": "1eDLECG_Lu9dXh-FLeCTvjI3fJclMid2b",
}


def get_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def walk(service, folder_id, folder_path="", depth=0, max_depth=8):
    items = []
    if depth > max_depth:
        return items
    page_token = None
    while True:
        try:
            resp = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id,name,mimeType,size,modifiedTime,createdTime,webViewLink)",
                pageSize=200, pageToken=page_token,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
        except Exception as e:
            print(f"  [warn] list failed under {folder_path}: {e}")
            return items
        for f in resp.get("files", []):
            f["_path"] = f"{folder_path}/{f['name']}".lstrip("/")
            f["_depth"] = depth
            f["_parent_id"] = folder_id
            items.append(f)
            if f.get("mimeType") == "application/vnd.google-apps.folder":
                items.extend(walk(service, f["id"], f["_path"], depth + 1, max_depth))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def report(name, folder_id, items):
    files = [i for i in items if i.get("mimeType") != "application/vnd.google-apps.folder"]
    folders = [i for i in items if i.get("mimeType") == "application/vnd.google-apps.folder"]

    type_counts = Counter()
    total_size = 0
    for f in files:
        mime = f.get("mimeType", "?")
        ext = mime.split("/")[-1] if "/" in mime else mime
        type_counts[ext] += 1
        try:
            total_size += int(f.get("size", 0) or 0)
        except Exception:
            pass

    print(f"\n{'='*72}")
    print(f"{name}")
    print(f"{'='*72}")
    print(f"  root id: {folder_id}")
    print(f"  total FILES: {len(files)}  ({total_size // 1024} KB)")
    print(f"  total SUBFOLDERS: {len(folders)}")
    print(f"  file types:")
    for t, c in type_counts.most_common(15):
        print(f"    {t:50s} {c}")

    print(f"  subfolder population:")
    children_by_parent = defaultdict(list)
    for i in items:
        children_by_parent[i.get("_parent_id")].append(i)

    for folder in sorted(folders, key=lambda f: f["_path"]):
        direct_files = [c for c in children_by_parent[folder["id"]]
                        if c.get("mimeType") != "application/vnd.google-apps.folder"]
        descendants = [i for i in items
                       if i.get("_path", "").startswith(folder["_path"] + "/")
                       and i.get("mimeType") != "application/vnd.google-apps.folder"]
        marker = "EMPTY" if len(descendants) == 0 else f"{len(direct_files)} direct, {len(descendants)} total"
        print(f"    {folder['_path']:60s} {marker}")


def main():
    try:
        service = get_service()
    except Exception as e:
        print(f"Drive auth failed: {e}")
        sys.exit(1)

    full_inventory = {}
    for name, fid in FOLDERS.items():
        print(f"\nScanning: {name}...")
        items = walk(service, fid)
        full_inventory[name] = items
        report(name, fid, items)

    out = Path("/root/landtek/drive_inventory.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({n: i for n, i in full_inventory.items()},
                              indent=2, default=str))
    print(f"\n→ Full inventory saved to {out}")


if __name__ == "__main__":
    main()
