"""Triple diagnostic: Gemini models, Qdrant collection schema, Drive access."""
import sys, json, requests
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from config import GEMINI_API_KEY, QDRANT_URL, QDRANT_KEY, GOOGLE_CREDS


def section(title):
    print(f"\n{'='*70}\n{title}\n{'='*70}")


# 1. Gemini models accessible
section("1. Gemini models accessible by this API key (generateContent only)")
try:
    r = requests.get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}",
        timeout=30)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:400]}")
    else:
        models = r.json().get("models", [])
        for m in models:
            if "generateContent" in m.get("supportedGenerationMethods", []):
                print(f"  ✓ {m['name']}")
        if not models:
            print("  (no models returned)")
except Exception as e:
    print(f"  FAILED: {e}")


# 2. Qdrant collection info
section("2. Qdrant collection info: landtek_conversations")
try:
    r = requests.get(f"{QDRANT_URL}/collections/landtek_conversations",
                     headers={"api-key": QDRANT_KEY}, timeout=30)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:400]}")
    else:
        info = r.json()
        result = info.get("result", {})
        print(f"  status: {result.get('status')}")
        print(f"  points_count: {result.get('points_count')}")
        print(f"  vectors_count: {result.get('vectors_count')}")
        cfg = result.get("config", {}).get("params", {})
        print(f"  vector size: {cfg.get('vectors', {}).get('size')}")
        print(f"  distance: {cfg.get('vectors', {}).get('distance')}")
except Exception as e:
    print(f"  FAILED: {e}")


# 3. Qdrant: scroll first 3 points (no filter) to see actual payload structure
section("3. Qdrant: actual payload structure (first 3 points, no filter)")
try:
    r = requests.post(
        f"{QDRANT_URL}/collections/landtek_conversations/points/scroll",
        headers={"api-key": QDRANT_KEY, "Content-Type": "application/json"},
        json={"limit": 3, "with_payload": True, "with_vector": False},
        timeout=30)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:400]}")
    else:
        for p in r.json().get("result", {}).get("points", []):
            print(f"  point id={p.get('id')}")
            payload = p.get("payload", {})
            print(f"    keys: {list(payload.keys())}")
            print(f"    sample: {json.dumps(payload, default=str)[:500]}")
            print()
except Exception as e:
    print(f"  FAILED: {e}")


# 4. Drive access — check service account, list visible folders
section("4. Drive: service account, visible folders")
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    print(f"  service account: {creds.service_account_email}")

    print("\n  Searching for ALL folders visible to the service account...")
    resp = service.files().list(
        q="mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name, owners(emailAddress), createdTime, parents)",
        pageSize=100, supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    folders = resp.get("files", [])
    print(f"  Total folders visible: {len(folders)}")
    for f in folders[:30]:
        owner = (f.get("owners", [{}])[0]).get("emailAddress", "?")
        parents = f.get("parents", [])
        print(f"    - {f['name']} (id: {f['id']}, owner: {owner}, parent: {parents[0] if parents else 'ROOT'})")
    if len(folders) > 30:
        print(f"    ... and {len(folders)-30} more")

    print("\n  Specifically searching for any folder with 'land' in name (case-insensitive)...")
    resp2 = service.files().list(
        q="mimeType = 'application/vnd.google-apps.folder' and name contains 'land' and trashed = false",
        fields="files(id, name, owners(emailAddress))",
        pageSize=20, supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    for f in resp2.get("files", []):
        print(f"    - {f['name']} (id: {f['id']})")
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {str(e)[:300]}")


print(f"\n{'='*70}\nDiagnostic complete.\n{'='*70}")
