"""Bootstrap case intelligence by Gemini-summarizing existing context.

Sources combined for the WHOLE corpus (then per-case profiles are derived):
  1. Qdrant landtek_conversations (Leo's accumulated chat memory) — per case_file
  2. Postgres documents — per case_file
  3. Postgres case_intelligence_log — per case_file
  4. Google Drive — auto-discover LandTek root, walk recursively, classify files by case

Drive access uses the existing service account (leolandtek-docai@landtek...).
The LandTek root folder must be shared with that service account as Viewer.
The script auto-discovers the root by name "LandTek" or via env var LANDTEK_DRIVE_ROOT.

Sequence per case:
  - Build a context blob from all four sources
  - If /root/landtek/case_analysis_prompts.json exists, use the case-specific prompt
    designed by design_case_prompts.py; otherwise use a generic template
  - Send to Gemini Flash, get structured profile
  - UPDATE cases + append to case_intelligence_log
"""
from __future__ import annotations
import os, sys, json, io, requests
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    GEMINI_API_KEY, QDRANT_URL, QDRANT_KEY, GOOGLE_CREDS,
    PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD,
)

GEMINI_MODEL = os.getenv("GEMINI_SUMMARY_MODEL", "gemini-1.5-flash")
QDRANT_COLLECTION = "landtek_conversations"
LANDTEK_ROOT_NAME = "LandTek"
LANDTEK_DRIVE_ROOT = os.getenv("LANDTEK_DRIVE_ROOT")  # optional explicit ID
MAX_TREE_DEPTH = 6
MAX_FILES_PER_CASE_FOR_EXCERPT = 12
MAX_FILE_BODY_CHARS = 2500
DESIGNED_PROMPTS_FILE = Path("/root/landtek/case_analysis_prompts.json")


# --------------------------- postgres helpers ---------------------------------
def pg_conn():
    import psycopg2
    return psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DATABASE,
                            user=PG_USER, password=PG_PASSWORD)


def list_cases():
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("SELECT case_file FROM cases ORDER BY case_file")
    cases = [r[0] for r in cur.fetchall()]
    cur.close(); conn.close()
    return cases


def fetch_postgres_documents(case_file: str):
    conn = pg_conn(); cur = conn.cursor()
    cur.execute("""SELECT id, original_filename, smart_filename, classification,
                          LEFT(extracted_text, 2000), strategic_relevance,
                          execution_status, document_title
                   FROM documents WHERE case_file = %s ORDER BY id""", (case_file,))
    docs = []
    for row in cur.fetchall():
        docs.append({"id": row[0], "filename": row[1], "smart_name": row[2],
                     "classification": row[3], "excerpt": row[4] or "",
                     "relevance": row[5], "execution_status": row[6], "title": row[7]})
    cur.close(); conn.close()
    return docs


def fetch_intelligence_log(case_file: str):
    conn = pg_conn(); cur = conn.cursor()
    try:
        cur.execute("""SELECT created_at, source_filename, intelligence_update
                       FROM case_intelligence_log WHERE case_file = %s
                       ORDER BY created_at""", (case_file,))
        return [{"date": r[0], "src": r[1], "text": r[2]} for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        cur.close(); conn.close()


# --------------------------- qdrant -------------------------------------------
def fetch_qdrant_conversations(case_file: str, limit: int = 500):
    headers = {"api-key": QDRANT_KEY, "Content-Type": "application/json"}
    url = f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll"
    body = {"limit": limit, "with_payload": True, "with_vector": False,
            "filter": {"must": [{"key": "case_file", "match": {"value": case_file}}]}}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json().get("result", {}).get("points", [])
    except Exception as e:
        print(f"    [warn] Qdrant fetch failed: {e}")
        return []


# --------------------------- google drive -------------------------------------
def get_drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS, scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_landtek_root(service, name=LANDTEK_ROOT_NAME):
    resp = service.files().list(
        q=f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name, owners(emailAddress), createdTime)",
        pageSize=20, supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    folders = resp.get("files", [])
    return folders[0] if folders else None


def walk_drive_tree(service, root_id, root_name=""):
    """BFS through the Drive tree starting at root_id. Returns flat list with computed paths."""
    all_items = []
    queue = [(root_id, root_name)]
    seen = set()
    while queue:
        folder_id, folder_path = queue.pop(0)
        if folder_id in seen:
            continue
        seen.add(folder_id)
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
                print(f"    [warn] list under {folder_path}: {type(e).__name__}: {str(e)[:120]}")
                break
            for f in resp.get("files", []):
                child_path = f"{folder_path}/{f['name']}".lstrip("/")
                f["_path"] = child_path
                f["_parent_path"] = folder_path
                all_items.append(f)
                if f.get("mimeType") == "application/vnd.google-apps.folder":
                    if child_path.count("/") < MAX_TREE_DEPTH:
                        queue.append((f["id"], child_path))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
    return all_items


def extract_drive_file_text(service, file_id, mime_type, max_chars=MAX_FILE_BODY_CHARS):
    try:
        if mime_type == "application/pdf":
            data = service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
            import fitz
            with fitz.open(stream=data, filetype="pdf") as doc:
                text = "".join(page.get_text() for page in doc[:5])
            return text[:max_chars]
        elif mime_type == "application/vnd.google-apps.document":
            data = service.files().export(fileId=file_id, mimeType="text/plain").execute()
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="ignore")
            return data[:max_chars]
        elif mime_type.startswith("text/"):
            data = service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
            return data.decode("utf-8", errors="ignore")[:max_chars]
        elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            data = service.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
            try:
                import docx
                doc = docx.Document(io.BytesIO(data))
                return "\n".join(p.text for p in doc.paragraphs)[:max_chars]
            except Exception:
                return ""
    except Exception as e:
        print(f"      [warn] extract failed for {file_id}: {type(e).__name__}: {str(e)[:120]}")
    return ""


def gemini_classify_files_by_case(file_inventory, case_files):
    """Ask Gemini to assign each file to a case_file (or 'unassigned')."""
    # Build a compact inventory listing for Gemini
    listing = []
    for i, f in enumerate(file_inventory):
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            continue
        listing.append({
            "idx": i,
            "name": f.get("name", ""),
            "path": f.get("_path", ""),
            "mime": f.get("mimeType", ""),
            "modified": (f.get("modifiedTime") or "")[:10],
        })
    if not listing:
        return {}
    prompt = f"""You are organizing a Philippine legal/property case file system.
Below is a flat inventory of all files in the LandTek Drive (each file with its full
folder path). Assign each file to exactly one of these case_files based on filename and
folder path signals: {case_files + ['unassigned']}

The cases:
- Paracale-001: Allan Inocalla, Paracale Camarines Norte gold mining (MPSA, DENR, mining)
- MWK-001: Mary Worrick Keesey estate, Mercedes Camarines Norte (heirship, ARTA, CART, Pajarillo, Patricia Keesey Zschoche)
- unassigned: doesn't clearly match either case

INVENTORY:
{json.dumps(listing, indent=1)}

Return JSON: {{"assignments": [{{"idx": <int>, "case_file": "<case>"}}]}}.
Use folder path strongly — files inside a folder named "MWK" or "Mercedes" or "Keesey" → MWK-001.
Files inside "Paracale" or "Mining" or "Inocalla" → Paracale-001.
When ambiguous from path, use filename hints. Default to "unassigned" if genuinely unclear."""
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
           f"?key={GEMINI_API_KEY}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 8000,
                                 "responseMimeType": "application/json"}}
    r = requests.post(url, json=body, timeout=180)
    r.raise_for_status()
    out = json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    # Build idx -> case_file map
    return {a["idx"]: a["case_file"] for a in out.get("assignments", [])}


# --------------------------- context + gemini ---------------------------------
def load_designed_prompts():
    if DESIGNED_PROMPTS_FILE.exists():
        try:
            data = json.loads(DESIGNED_PROMPTS_FILE.read_text())
            return {p["case_file"]: p for p in data.get("prompts", [])}
        except Exception as e:
            print(f"  [warn] designed prompts file invalid: {e}")
    return {}


def build_context_block(case_file, convos, docs, intel_log, drive_files, drive_excerpts):
    parts = [f"# Case: {case_file}"]
    if convos:
        parts.append(f"\n## Conversation history ({len(convos)} entries)")
        for c in convos:
            p = c.get("payload", {})
            ts = p.get("timestamp", p.get("sent_at", "?"))
            sender = p.get("sender_name", p.get("client_name", "?"))
            msg = p.get("message", p.get("text", p.get("rawText", "")))
            cat = p.get("category", p.get("classification", ""))
            parts.append(f"[{ts}] {sender} ({cat}): {msg[:600]}")
    else:
        parts.append("\n## Conversation history\n(none)")

    if docs:
        parts.append(f"\n## Postgres documents ({len(docs)})")
        for d in docs:
            title = d['title'] or d['smart_name'] or d['filename'] or f"doc#{d['id']}"
            parts.append(f"[Doc {d['id']}] {title} ({d['classification'] or '?'}, "
                         f"{d['execution_status'] or '?'})")
            if d['excerpt']:
                parts.append(f"  excerpt: {d['excerpt'][:400]}")

    if drive_files:
        parts.append(f"\n## Google Drive files for this case ({len(drive_files)})")
        # Group by parent path
        by_folder = defaultdict(list)
        for f in drive_files:
            by_folder[f.get("_parent_path", "")].append(f)
        for folder, files in sorted(by_folder.items()):
            parts.append(f"\n### {folder or '(root)'} — {len(files)} files")
            for f in files[:60]:
                size_kb = (int(f.get("size", 0) or 0)) // 1024
                parts.append(f"  - {f.get('name')} | {f.get('mimeType','?').split('.')[-1]} | "
                             f"{size_kb}KB | {(f.get('modifiedTime') or '')[:10]}")

    if drive_excerpts:
        parts.append(f"\n## Drive file excerpts ({len(drive_excerpts)})")
        for b in drive_excerpts:
            parts.append(f"\n--- {b['name']} ({b['path']}) ---\n{b['excerpt']}")

    if intel_log:
        parts.append(f"\n## Prior intelligence updates ({len(intel_log)})")
        for e in intel_log:
            parts.append(f"[{e['date']}] from {e['src']}: {e['text']}")
    return "\n".join(parts)


_GEMINI_FALLBACK_CHAIN = [
    GEMINI_MODEL, "gemini-2.0-flash", "gemini-2.5-flash",
    "gemini-1.5-flash-002", "gemini-1.5-flash",
]


def call_gemini_json(prompt: str, max_tokens: int = 6000):
    seen = set(); last_err = None
    for model in _GEMINI_FALLBACK_CHAIN:
        if not model or model in seen: continue
        seen.add(model)
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={GEMINI_API_KEY}")
        body = {"contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": max_tokens,
                                     "responseMimeType": "application/json"}}
        try:
            r = requests.post(url, json=body, timeout=240)
            if r.status_code == 404:
                last_err = f"{model}: 404 not found"
                continue
            if r.status_code >= 400:
                last_err = f"{model}: {r.status_code} {r.text[:200]}"
                continue
            print(f"  [gemini] using model: {model}")
            return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
        except Exception as e:
            last_err = f"{model}: {type(e).__name__}: {str(e)[:200]}"
            continue
    raise RuntimeError(f"All Gemini models failed. Tried {sorted(seen)}. Last: {last_err}")


GENERIC_PROMPT_TEMPLATE = """You are bootstrapping the intelligence profile for a Philippine
legal/property case management system. Read the conversation history, document excerpts, and
Google Drive inventory below. Produce a structured profile of case "{case_file}" based ONLY on
what's actually present. Do not invent facts.

{context_block}

Return STRICT JSON:
{{
  "client_name": "<primary client/owner full name, or null>",
  "case_type": "estate | mining | property | tenancy | regulatory | corporate | other",
  "key_parties": ["<full names>"],
  "key_locations": ["<barangay/municipality/province>"],
  "key_agencies": ["<ARTA, DENR, DAR, DILG, LGU of X, courts, etc.>"],
  "key_reference_numbers": ["<docket numbers, CTNs, MPSA numbers, TCT/OCT numbers>"],
  "current_goals": "<2-3 sentences>",
  "key_risks": "<top 1-3 risks, semicolon-separated>",
  "open_gaps": "<missing information or documents>",
  "next_milestone": "<next action, deadline, or expected event>",
  "intelligence_summary": "<3-5 paragraph rich background, parties, posture, history, procedural context>",
  "drive_observations": "<2-3 sentences on what the Drive inventory tells you about case maturity, document volume, recent activity>",
  "confidence": 0.0-1.0
}}
"""


def gemini_summarize(case_file: str, context_block: str, designed_prompts: dict):
    designed = designed_prompts.get(case_file)
    if designed and designed.get("draft_analysis_prompt"):
        prompt = designed["draft_analysis_prompt"].format(
            case_file=case_file, context_block=context_block)
    else:
        prompt = GENERIC_PROMPT_TEMPLATE.format(case_file=case_file, context_block=context_block)
    return call_gemini_json(prompt, max_tokens=6000)


def update_case(case_file: str, intel: dict):
    conn = pg_conn(); cur = conn.cursor()
    summary = intel.get("intelligence_summary", "") or ""
    if intel.get("key_parties"):
        summary += f"\n\nKey parties: {', '.join(intel['key_parties'])}"
    if intel.get("key_locations"):
        summary += f"\nKey locations: {', '.join(intel['key_locations'])}"
    if intel.get("key_agencies"):
        summary += f"\nKey agencies: {', '.join(intel['key_agencies'])}"
    if intel.get("key_reference_numbers"):
        summary += f"\nKey reference numbers: {', '.join(intel['key_reference_numbers'])}"
    if intel.get("drive_observations"):
        summary += f"\n\nDrive observations: {intel['drive_observations']}"

    cur.execute("""UPDATE cases SET
                   client_name = COALESCE(NULLIF(%s,''), client_name),
                   current_goals = COALESCE(NULLIF(%s,''), current_goals),
                   key_risks = COALESCE(NULLIF(%s,''), key_risks),
                   open_gaps = COALESCE(NULLIF(%s,''), open_gaps),
                   next_milestone = COALESCE(NULLIF(%s,''), next_milestone),
                   intelligence_summary = %s,
                   updated_at = NOW()
                   WHERE case_file = %s""",
                (intel.get("client_name") or "", intel.get("current_goals") or "",
                 intel.get("key_risks") or "", intel.get("open_gaps") or "",
                 intel.get("next_milestone") or "", summary, case_file))
    try:
        cur.execute("""INSERT INTO case_intelligence_log
                       (case_file, source_filename, intelligence_update, novelty_score)
                       VALUES (%s, %s, %s, %s)""",
                    (case_file, "BOOTSTRAP_GEMINI_DRIVE", summary, intel.get("confidence", 0.5)))
    except Exception as e:
        print(f"    [warn] log insert failed: {e}")
    conn.commit(); cur.close(); conn.close()


def main():
    cases = list_cases()
    print(f"Bootstrapping {len(cases)} cases via Gemini ({GEMINI_MODEL}): {cases}")
    if not cases:
        print("No cases found. Insert rows into cases table first."); return

    designed_prompts = load_designed_prompts()
    if designed_prompts:
        print(f"Using designed prompts from {DESIGNED_PROMPTS_FILE} for: {list(designed_prompts.keys())}")
    else:
        print("No designed prompts found — using generic template.")

    # ---- Drive: discover root, walk tree, classify files by case ----
    print("\n=== Drive: discovering LandTek root ===")
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"  Drive auth failed: {e}")
        service = None
    drive_files_by_case = defaultdict(list)
    drive_excerpts_by_case = defaultdict(list)
    if service:
        if LANDTEK_DRIVE_ROOT:
            root = {"id": LANDTEK_DRIVE_ROOT, "name": LANDTEK_ROOT_NAME}
            print(f"  Using explicit root: {LANDTEK_DRIVE_ROOT}")
        else:
            root = find_landtek_root(service)
            if root:
                print(f"  Found '{root['name']}' → {root['id']}")
            else:
                print(f"  '{LANDTEK_ROOT_NAME}' folder not found. Set LANDTEK_DRIVE_ROOT env var or share the folder with the service account.")
        if root:
            print(f"  Walking tree from root...")
            tree = walk_drive_tree(service, root["id"], root["name"])
            non_folder = [f for f in tree if f.get("mimeType") != "application/vnd.google-apps.folder"]
            print(f"  Found {len(tree)} items ({len(non_folder)} files, {len(tree) - len(non_folder)} folders)")
            if non_folder:
                print("  Asking Gemini to classify each file by case...")
                try:
                    assignments = gemini_classify_files_by_case(tree, cases)
                except Exception as e:
                    print(f"  classification failed: {e}")
                    assignments = {}
                for idx, case in assignments.items():
                    if 0 <= idx < len(tree) and tree[idx].get("mimeType") != "application/vnd.google-apps.folder":
                        drive_files_by_case[case].append(tree[idx])
                for case in cases:
                    print(f"    {case}: {len(drive_files_by_case[case])} files assigned")
                print(f"    unassigned: {len(drive_files_by_case.get('unassigned', []))} files")
                # Pull excerpts: top N most-recent files per case
                for case in cases:
                    files = sorted(drive_files_by_case[case],
                                   key=lambda f: f.get("modifiedTime", ""), reverse=True)
                    print(f"  Pulling excerpts for {case} (top {min(MAX_FILES_PER_CASE_FOR_EXCERPT, len(files))} of {len(files)} files)...")
                    for f in files[:MAX_FILES_PER_CASE_FOR_EXCERPT]:
                        text = extract_drive_file_text(service, f["id"], f.get("mimeType", ""))
                        if text.strip():
                            drive_excerpts_by_case[case].append({
                                "name": f["name"], "path": f.get("_path", ""), "excerpt": text})

    # ---- per-case profile generation ----
    for case_file in cases:
        print(f"\n{'='*70}\n{case_file}\n{'='*70}")
        convos = fetch_qdrant_conversations(case_file)
        docs = fetch_postgres_documents(case_file)
        intel_log = fetch_intelligence_log(case_file)
        drive_files = drive_files_by_case.get(case_file, [])
        drive_excerpts = drive_excerpts_by_case.get(case_file, [])
        print(f"  Sources: {len(convos)} convos, {len(docs)} pg-docs, "
              f"{len(drive_files)} drive files, {len(drive_excerpts)} excerpts, {len(intel_log)} intel entries")

        ctx = build_context_block(case_file, convos, docs, intel_log, drive_files, drive_excerpts)
        print(f"  Context size: {len(ctx)} chars")

        try:
            intel = gemini_summarize(case_file, ctx, designed_prompts)
        except Exception as e:
            print(f"  Gemini failed: {e}"); continue

        print(f"  Client: {intel.get('client_name')}")
        print(f"  Type: {intel.get('case_type')}")
        print(f"  Parties: {intel.get('key_parties')}")
        print(f"  Locations: {intel.get('key_locations')}")
        print(f"  Agencies: {intel.get('key_agencies')}")
        print(f"  Ref numbers: {intel.get('key_reference_numbers')}")
        print(f"  Goals: {intel.get('current_goals')}")
        print(f"  Risks: {intel.get('key_risks')}")
        print(f"  Next: {intel.get('next_milestone')}")
        print(f"  Drive obs: {intel.get('drive_observations')}")
        print(f"  Confidence: {intel.get('confidence')}")
        print(f"  Summary: {(intel.get('intelligence_summary') or '')[:400]}...")

        update_case(case_file, intel)
        print(f"  → cases.{case_file} updated")

    print("\nBootstrap complete. Re-run test_intake.py to verify case classification improves.")


if __name__ == "__main__":
    main()
