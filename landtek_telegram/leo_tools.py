#!/usr/bin/env python3
"""leo_tools.py — function-calling tools Leo can invoke during a conversation.

Each tool is:
  - A schema entry in LEO_TOOLS (Anthropic tool-use format)
  - A Python function in TOOL_FUNCTIONS that takes the LLM's input dict
    and returns a string (or dict) Leo gets back as the tool result

Tools available to Leo:
  - query_documents     : search the digital corpus by name/date/keyword/matter
  - read_document       : pull a doc's classification, date, filename, text excerpt
  - search_drive        : find files in the LANDTEK Drive folder
  - vault_register      : create a new vault entry (CORR-N, SPA-N, etc.)
  - vault_find          : look up an existing vault entry
  - vault_queue         : see pending vault work
  - vault_missing       : docs that need vault entries for a matter
  - vault_last          : recent vault entries
  - find_matter_for_party : given a party name, find which matters they appear in
  - link_documents      : cross-reference two documents

These cover everything I (Claude) did manually today — Leo can now do it himself.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request

import psycopg2
import psycopg2.extras

PG_DSN = os.environ.get("LANDTEK_TG_PG_DSN",
                        "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
LEO_TOOLS_BASE = "http://127.0.0.1:8765"
DRIVE_CREDS_PATH = "/root/landtek/google-creds.json"


# ── tool schemas (Anthropic format) ─────────────────────────────────────────

LEO_TOOLS = [
    {
        "name": "semantic_search",
        "description": (
            "Search the corpus by MEANING (vector search) — finds the right "
            "document even when its filename is wrong or you only know what it's "
            "ABOUT. Use this FIRST for 'find the X document / the letter about Y' "
            "questions; it catches things keyword search misses. Returns docs with "
            "download links, ranked by relevance. If it returns nothing, that does "
            "NOT mean the doc is absent (coverage is still partial) — also try "
            "query_documents and search_drive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what the document is about, in natural language"},
                "limit": {"type": "integer", "description": "max results (default 6)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_documents",
        "description": (
            "Search the digital document corpus. Returns matching docs with "
            "id, smart_filename, doc_date, classification, matter_codes, "
            "and a short snippet. Use this BEFORE asking the user where a "
            "document is — most letters and filings are already in the "
            "corpus. Combine filters for precision."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "substring match against filename"},
                "text_contains": {"type": "string", "description": "substring match against extracted text"},
                "date_from":     {"type": "string", "description": "YYYY-MM-DD lower bound on doc_date"},
                "date_to":       {"type": "string", "description": "YYYY-MM-DD upper bound on doc_date"},
                "classification": {"type": "string", "description": "Letter, Court Filing, SPA, Affidavit, etc."},
                "matter_code":   {"type": "string", "description": "limit to docs linked to this matter"},
                "client":        {"type": "string", "description": "client scope — defaults to MWK-001 (Keesey). Allan Inocalla / Paracale is Paracale-001, a SEPARATE client; only set this to deliberately work a different client. Never mix clients."},
                "limit":         {"type": "integer", "description": "max results (default 10)"},
            },
            "required": [],
        },
    },
    {
        "name": "read_document",
        "description": (
            "Pull the classification, date, filename, drive_link, and a "
            "1500-char text excerpt for one document by id. Use after "
            "query_documents to confirm which result is the right one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "doc_id": {"type": "integer", "description": "the document id"},
            },
            "required": ["doc_id"],
        },
    },
    {
        "name": "search_drive",
        "description": (
            "Search the LANDTEK Google Drive — by BOTH filename AND the text "
            "INSIDE the files (Google indexes PDF/Doc content). Use this when "
            "query_documents finds nothing, OR to find a document by what it is "
            "about even when the filename is wrong/misleading (Drive filenames "
            "here often do NOT match their contents). Search by the distinctive "
            "term: a person ('Fortuno', 'Macale'), a doc type ('adverse claim', "
            "'rejoinder'), or a docket ('1210', 'PSD-12802'). Returns drive_id, "
            "name, modifiedTime. Then call read_drive on a hit to confirm what it "
            "actually says before trusting it. Image-only scans have no text and "
            "won't match a content search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "distinctive term to find in the filename OR the file's text content"},
                "name_contains": {"type": "string", "description": "(alias for query) substring to match"},
                "limit":         {"type": "integer", "description": "max results (default 10)"},
            },
            "required": [],
        },
    },
    {
        "name": "read_drive",
        "description": (
            "Read the actual TEXT of a Google Drive file by its drive_id (from "
            "search_drive). Use this to CONFIRM what a Drive file really is before "
            "linking it — the filename here is unreliable, the content is truth. "
            "Returns the first part of the extracted text. (Empty result = an "
            "image-only scan with no text layer.)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "string", "description": "the Drive file id from search_drive"},
            },
            "required": ["drive_id"],
        },
    },
    {
        "name": "vault_register",
        "description": (
            "Create a new physical-master vault entry (reserve the locator). Use "
            "this when you've determined the section, number, matter, and "
            "description. It registers the folder as 'needs scan' and does NOT "
            "auto-attach a scan (auto-matching kept linking the wrong document). "
            "After registering, FIND the correct scan by content and bind it with "
            "vault_bind_scan."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section":         {"type": "string", "description": "TCT|DEED|SPA|AFF|TAX|PSA|ID|CRT|RES|CONT|CORR|MISC"},
                "number":          {"type": "integer", "description": "next available within the section"},
                "description":     {"type": "string", "description": "plain description of what the document is"},
                "matter_code":     {"type": "string", "description": "primary matter, e.g. MWK-CV26360"},
                "related_matters": {"type": "array", "items": {"type": "string"},
                                    "description": "other matters this doc is materially relevant to"},
            },
            "required": ["section", "number", "description", "matter_code"],
        },
    },
    {
        "name": "vault_bind_scan",
        "description": (
            "Bind the CORRECT scan to a vault locator — also used to FIX a wrong "
            "link. Pass doc_id (an existing corpus document) OR drive_id (a Drive "
            "file, which gets ingested properly and made downloadable). ONLY call "
            "this after you've confirmed by READING it (read_document/read_drive) "
            "that the scan really is that document. This is how you complete the "
            "physical<->digital bridge — never trust a filename, verify content first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section":  {"type": "string", "description": "vault section, e.g. CORR"},
                "number":   {"type": "integer", "description": "vault number, e.g. 28"},
                "doc_id":   {"type": "integer", "description": "existing corpus doc id to bind (if already in corpus)"},
                "drive_id": {"type": "string", "description": "Drive file id to ingest + bind (if only in the Drive)"},
            },
            "required": ["section", "number"],
        },
    },
    {
        "name": "vault_find",
        "description": "Look up an existing vault entry by section+number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {"type": "string"},
                "number":  {"type": "integer"},
            },
            "required": ["section", "number"],
        },
    },
    {
        "name": "vault_queue",
        "description": "List vault entries pending scan or other action.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "vault_missing",
        "description": (
            "For a matter, list digital documents that look like they should "
            "have a physical-master vault entry but don't yet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "matter_code": {"type": "string"},
            },
            "required": ["matter_code"],
        },
    },
    {
        "name": "vault_last",
        "description": "Return the most recent N vault entries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "default 5"},
            },
            "required": [],
        },
    },
    {
        "name": "find_matter_for_party",
        "description": (
            "Given a party/person name, find which matters they appear in "
            "based on corpus content. Use when figuring out which case a "
            "letter or filing relates to."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "person or org name"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "link_documents",
        "description": (
            "Create a cross-reference between two documents (e.g., outgoing "
            "letter ↔ response received). link_type is reply_to, related, "
            "amends, supersedes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_doc_id": {"type": "integer"},
                "to_doc_id":   {"type": "integer"},
                "link_type":   {"type": "string"},
                "reason":      {"type": "string"},
            },
            "required": ["from_doc_id", "to_doc_id", "link_type", "reason"],
        },
    },
]


# ── tool implementations ───────────────────────────────────────────────────

def _db():
    conn = psycopg2.connect(PG_DSN)
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def _http_get(path, **params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    url = f"{LEO_TOOLS_BASE}{path}" + (f"?{qs}" if qs else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _http_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{LEO_TOOLS_BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "error": f"http {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def t_query_documents(args):
    name = args.get("name_contains")
    text = args.get("text_contains")
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    classification = args.get("classification")
    matter_code = args.get("matter_code")
    limit = max(1, min(int(args.get("limit", 10)), 30))

    conn, cur = _db()
    # NOTE: %% needed because psycopg2 parses % as parameter placeholder
    conditions = ["d.master_form = 'digital'",
                  "d.status NOT LIKE 'placeholder%%'"]
    params = []
    # CLIENT ISOLATION — never return another client's documents. Default to MWK
    # (Keesey); Inocalla is a SEPARATE client (INOCALLA-001). NULL = treat as MWK.
    client = (args.get("client") or "MWK-001")
    if client == "MWK-001":
        conditions.append("(d.case_file = 'MWK-001' OR d.case_file IS NULL)")
    else:
        conditions.append("d.case_file = %s"); params.append(client)
    if name:
        conditions.append("d.smart_filename ILIKE %s")
        params.append(f"%{name}%")
    if text:
        conditions.append("d.extracted_text ILIKE %s")
        params.append(f"%{text}%")
    if date_from:
        conditions.append("d.doc_date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("d.doc_date <= %s"); params.append(date_to)
    if classification:
        conditions.append("d.classification ILIKE %s")
        params.append(f"%{classification}%")
    join = ""
    if matter_code:
        join = "LEFT JOIN document_matter_links dml ON dml.doc_id = d.id"
        conditions.append("dml.matter_code = %s")
        params.append(matter_code)
    sql = f"""
        SELECT DISTINCT d.id, d.smart_filename, d.doc_date, d.classification,
               d.file_path, d.drive_file_id, LEFT(d.extracted_text, 250) AS snippet
          FROM documents d {join}
         WHERE {' AND '.join(conditions)}
         ORDER BY d.doc_date DESC NULLS LAST, d.id DESC
         LIMIT {limit}
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close(); conn.close()
    out = []
    for r in rows:
        # The downloadable URL is ALWAYS the proxy (never the raw drive_link /
        # server path). We deliberately do NOT return drive_link here so Leo
        # cannot paste a /root/... filesystem path into chat.
        downloadable = bool(r["file_path"] or r["drive_file_id"])
        out.append({
            "id": r["id"],
            "smart_filename": (r["smart_filename"] or "")[:100],
            "doc_date": str(r["doc_date"]) if r["doc_date"] else None,
            "classification": r["classification"],
            "download_link": (f"https://leo.hayuma.org/files/c/{r['id']}"
                              if downloadable else None),
            "downloadable": downloadable,
            "snippet": (r["snippet"] or "")[:200],
        })
    return f"Found {len(out)} documents:\n" + json.dumps(out, indent=2)


def t_read_document(args):
    doc_id = int(args["doc_id"])
    conn, cur = _db()
    cur.execute("""
        SELECT id, smart_filename, doc_date, classification, drive_link,
               file_path, drive_file_id,
               LEFT(extracted_text, 1500) AS excerpt
          FROM documents WHERE id = %s
    """, (doc_id,))
    r = cur.fetchone()
    # also pull matter links
    cur.execute("""
        SELECT relation_kind, matter_code FROM document_matter_links
         WHERE doc_id = %s ORDER BY relation_kind DESC
    """, (doc_id,))
    matters = cur.fetchall()
    cur.close(); conn.close()
    if not r:
        return f"No document with id {doc_id}"
    # A document is downloadable iff the public proxy can serve it — i.e. it has
    # a local file_path or a drive_file_id. The canonical downloadable URL is
    # always https://leo.hayuma.org/files/c/<id>; give THAT to humans, never the
    # raw drive_link (which may be a server filesystem path).
    downloadable = bool(r["file_path"] or r["drive_file_id"])
    download_link = f"https://leo.hayuma.org/files/c/{r['id']}" if downloadable else None
    return json.dumps({
        "id": r["id"],
        "smart_filename": r["smart_filename"],
        "doc_date": str(r["doc_date"]) if r["doc_date"] else None,
        "classification": r["classification"],
        "download_link": download_link,
        "downloadable": downloadable,
        "download_note": ("Give this download_link to the requester."
                          if downloadable else
                          "NOT downloadable yet — no scan file on record. Tell the "
                          "requester the scan still needs to be uploaded; do NOT "
                          "hand out a server file path."),
        "linked_matters": [{"kind": m["relation_kind"], "code": m["matter_code"]} for m in matters],
        "excerpt": r["excerpt"],
    }, indent=2)


def _drive_client():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        DRIVE_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"])
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def t_search_drive(args):
    q = (args.get("query") or args.get("name_contains") or "").strip()
    limit = int(args.get("limit", 10))
    if not q:
        return "search_drive needs a 'query' term."
    q_esc = q.replace("'", "\\'")
    try:
        svc = _drive_client()
        out, seen = [], set()
        # Search BOTH filename and full-text content; merge, de-dupe.
        for clause in (f"name contains '{q_esc}'", f"fullText contains '{q_esc}'"):
            resp = svc.files().list(
                q=f"({clause}) and trashed = false",
                pageSize=limit, orderBy="modifiedTime desc",
                fields="files(id, name, modifiedTime, mimeType, size)",
                supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            for f in resp.get("files", []):
                if f["id"] in seen:
                    continue
                seen.add(f["id"])
                out.append({
                    "drive_id": f["id"],
                    "name": f.get("name", ""),
                    "matched": "filename" if "name contains" in clause else "content",
                    "modified": f.get("modifiedTime", "")[:19],
                    "mime": f.get("mimeType", "").split(".")[-1],
                })
        if not out:
            return (f"No Drive files match '{q}' by name or content. "
                    "It may be an image-only scan (no searchable text) or not uploaded yet.")
        return f"Found {len(out)} Drive files for '{q}':\n" + json.dumps(out[:limit*2], indent=2)
    except Exception as e:
        return f"Drive search failed: {e}"


def t_read_drive(args):
    """Download a Drive file and return its extracted text so Leo can CONFIRM
    what it actually is (filenames here lie)."""
    import io, subprocess, tempfile, os
    drive_id = (args.get("drive_id") or "").strip()
    if not drive_id:
        return "read_drive needs a drive_id."
    try:
        from googleapiclient.http import MediaIoBaseDownload
        svc = _drive_client()
        meta = svc.files().get(fileId=drive_id, fields="name,mimeType",
                               supportsAllDrives=True).execute()
        mime = meta.get("mimeType", "")
        if mime == "application/vnd.google-apps.document":
            txt = svc.files().export(fileId=drive_id, mimeType="text/plain").execute().decode("utf-8", "ignore")
        else:
            req = svc.files().get_media(fileId=drive_id, supportsAllDrives=True)
            buf = io.BytesIO(); dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
                tf.write(buf.getvalue()); path = tf.name
            try:
                txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                                     capture_output=True, text=True, timeout=45).stdout
            finally:
                os.unlink(path)
        txt = (txt or "").strip()
        if not txt:
            return json.dumps({"name": meta.get("name"), "text": "",
                               "note": "no text — image-only scan; cannot confirm content from text"})
        return json.dumps({"name": meta.get("name"), "text_excerpt": txt[:1800]}, indent=2)
    except Exception as e:
        return f"read_drive failed: {e}"


def t_vault_register(args):
    body = {
        "section": args["section"],
        "number": int(args["number"]),
        "description": args["description"],
        "matter_code": args["matter_code"],
    }
    if args.get("related_matters"):
        body["related_matters"] = args["related_matters"]
    r = _http_post("/api/vault/register", body)
    return json.dumps(r, indent=2)


def t_vault_find(args):
    return json.dumps(_http_get("/api/vault/find",
                                section=args["section"],
                                number=args["number"]), indent=2)


def t_vault_queue(args):
    return json.dumps(_http_get("/api/vault/queue"), indent=2)


def t_vault_missing(args):
    return json.dumps(_http_get("/api/vault/missing",
                                matter_code=args["matter_code"]), indent=2)


def t_vault_last(args):
    return json.dumps(_http_get("/api/vault/last", n=args.get("n", 5)), indent=2)


def t_find_matter_for_party(args):
    name = args["name"]
    conn, cur = _db()
    cur.execute("""
        SELECT dml.matter_code, COUNT(*) AS hits
          FROM documents d
          JOIN document_matter_links dml ON dml.doc_id = d.id
         WHERE d.extracted_text ILIKE %s
         GROUP BY dml.matter_code
         ORDER BY hits DESC
         LIMIT 8
    """, (f"%{name}%",))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return json.dumps([{"matter_code": r["matter_code"], "doc_hits": r["hits"]}
                       for r in rows], indent=2)


def t_link_documents(args):
    conn, cur = _db()
    cur.execute("""
        INSERT INTO document_links (document_id, linked_case_file, link_type,
                                    link_reason, source_doc_id, link_confidence,
                                    created_by, created_at)
        VALUES (%s, 'MWK-001', %s, %s, %s, 0.9, 'leo_tool', NOW())
        RETURNING id
    """, (args["from_doc_id"], args["link_type"], args["reason"], args["to_doc_id"]))
    link_id = cur.fetchone()["id"]
    conn.commit()
    cur.close(); conn.close()
    return f"Created document_links #{link_id}: {args['from_doc_id']} -{args['link_type']}-> {args['to_doc_id']}"


def t_vault_bind_scan(args):
    """Bind the CORRECT, content-verified scan to a vault locator (also used to
    FIX a wrong link). Pass doc_id (an existing corpus doc) OR drive_id (a Drive
    file, which is ingested properly: downloaded, text-extracted, made
    downloadable). Only call this AFTER you've confirmed by reading it that the
    scan is the right document."""
    import io, os, subprocess
    section = (args.get("section") or "").strip().upper()
    try:
        number = int(args.get("number"))
    except (TypeError, ValueError):
        return "vault_bind_scan needs section + number."
    doc_id = args.get("doc_id")
    drive_id = (args.get("drive_id") or "").strip() or None
    conn, cur = _db()
    cur.execute("""SELECT id FROM documents WHERE master_form='physical'
        AND vault_section=%s AND vault_number=%s""", (section, number))
    m = cur.fetchone()
    if not m:
        cur.close(); conn.close()
        return f"No vault entry {section}-{number:03d} exists."
    master = m["id"]

    if doc_id:
        scan = int(doc_id)
        cur.execute("SELECT 1 FROM documents WHERE id=%s", (scan,))
        if not cur.fetchone():
            cur.close(); conn.close()
            return f"doc#{scan} not found."
    elif drive_id:
        # Reuse an existing ingest of this exact Drive file (don't duplicate).
        cur.execute("SELECT id FROM documents WHERE drive_link=%s ORDER BY id LIMIT 1",
                    (f"drive://{drive_id}",))
        existing = cur.fetchone()
        if existing:
            scan = existing["id"]
            cur.execute("""UPDATE documents SET digital_scan_id=%s,
                status='vault_registered', updated_at=NOW() WHERE id=%s""", (scan, master))
            conn.commit(); cur.close(); conn.close()
            return json.dumps({"locator": f"{section}-{number:03d}", "linked_scan_doc": scan,
                               "download": f"https://leo.hayuma.org/files/c/{scan}",
                               "ok": True, "note": "reused existing ingest"}, indent=2)
        try:
            from googleapiclient.http import MediaIoBaseDownload
            svc = _drive_client()
            meta = svc.files().get(fileId=drive_id, fields="name",
                                   supportsAllDrives=True).execute()
            req = svc.files().get_media(fileId=drive_id, supportsAllDrives=True)
            buf = io.BytesIO(); dl = MediaIoBaseDownload(buf, req)
            done = False
            while not done:
                _, done = dl.next_chunk()
            d = "/root/landtek/uploads/MWK-001/drive_scans"
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, f"drive_{drive_id}.pdf")
            with open(path, "wb") as f:
                f.write(buf.getvalue())
            txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                                 capture_output=True, text=True, timeout=60).stdout
            cur.execute("""INSERT INTO documents (case_file, smart_filename,
                    original_filename, mime_type, master_form, file_path, drive_link,
                    classification, extracted_text, status, created_at, updated_at)
                VALUES ('MWK-001', %s, %s, 'application/pdf', 'digital', %s, %s,
                    'Document', %s, 'ingested_via_bind', NOW(), NOW()) RETURNING id""",
                (meta.get("name"), meta.get("name"), path, f"drive://{drive_id}",
                 txt[:200000]))
            scan = cur.fetchone()["id"]
        except Exception as e:
            cur.close(); conn.close()
            return f"Failed to ingest Drive file: {str(e)[:200]}"
    else:
        cur.close(); conn.close()
        return "vault_bind_scan needs doc_id or drive_id."

    cur.execute("""UPDATE documents SET digital_scan_id=%s,
        status='vault_registered', updated_at=NOW() WHERE id=%s""", (scan, master))
    conn.commit()
    cur.close(); conn.close()
    return json.dumps({"locator": f"{section}-{number:03d}", "linked_scan_doc": scan,
                       "download": f"https://leo.hayuma.org/files/c/{scan}",
                       "ok": True}, indent=2)


def _env_key(name):
    """Read a key from the environment, falling back to /root/landtek/.env so the
    tool works regardless of how the router service was started."""
    v = os.environ.get(name)
    if v:
        return v
    try:
        for line in open("/root/landtek/.env"):
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def t_semantic_search(args):
    """Search the corpus by MEANING (vector search over Qdrant) — robust to wrong
    or misleading filenames, which keyword search is not. Returns the best-matching
    documents with their download links. DEGRADES to keyword search automatically
    if the vector layer is unreachable — it never errors out, so Leo never freezes
    on it. (Coverage is currently partial — a miss here does NOT mean 'not in the
    corpus'; also try query_documents / search_drive.)"""
    query = (args.get("query") or "").strip()
    limit = int(args.get("limit", 6))
    if not query:
        return "semantic_search needs a query."
    gk = _env_key("GEMINI_API_KEY")
    qurl = _env_key("QDRANT_URL")
    qkey = _env_key("QDRANT_KEY")
    if not (gk and qurl and qkey):
        return ("(semantic layer not configured — using keyword search)\n"
                + t_query_documents({"text_contains": query, "limit": limit}))
    try:
        ebody = json.dumps({
            "model": "models/gemini-embedding-001",
            "content": {"parts": [{"text": query}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": 768,
        }).encode()
        ereq = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-embedding-001:embedContent?key={gk}",
            data=ebody, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(ereq, timeout=20) as r:
            vec = json.loads(r.read().decode())["embedding"]["values"]
        sbody = json.dumps({
            "vector": vec, "limit": limit * 4,
            "with_payload": ["doc_id_postgres", "smart_filename", "case_file"],
        }).encode()
        sreq = urllib.request.Request(
            f"{qurl}/collections/landtek_documents/points/search",
            data=sbody,
            headers={"api-key": qkey, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(sreq, timeout=20) as r:
            hits = json.loads(r.read().decode())["result"]
    except Exception as e:
        kw = t_query_documents({"text_contains": query, "limit": limit})
        return (f"(semantic layer unavailable: {str(e)[:70]} — fell back to "
                f"keyword search)\n{kw}")

    # Dedup to doc-level (keep best chunk score per doc), drop orphan points.
    best = {}
    for h in hits:
        p = h.get("payload") or {}
        did = p.get("doc_id_postgres")
        if did is None:
            continue
        did = int(did)
        if did not in best or h["score"] > best[did]["score"]:
            best[did] = {"doc_id": did, "score": round(h["score"], 3),
                         "name": (p.get("smart_filename") or "")[:80]}
    # CLIENT ISOLATION — drop any hit that belongs to another client. Qdrant indexes
    # every client's vectors, so without this an MWK query can surface Inocalla docs.
    client = (args.get("client") or "MWK-001")
    if best:
        try:
            conn, cur = _db()
            cur.execute("SELECT id, case_file FROM documents WHERE id = ANY(%s)", (list(best.keys()),))
            cf = {r["id"]: r["case_file"] for r in cur.fetchall()}
            cur.close(); conn.close()
            best = {d: v for d, v in best.items()
                    if cf.get(d) == client or (client == "MWK-001" and cf.get(d) is None)}
        except Exception:
            pass
    out = sorted(best.values(), key=lambda x: -x["score"])[:limit]
    if not out:
        return (f"Semantic search returned nothing for {query!r}. It may not be "
                "embedded yet — try query_documents or search_drive by a key term.")
    # Enrich with downloadable links from Postgres.
    try:
        conn, cur = _db()
        cur.execute("SELECT id, (file_path IS NOT NULL OR drive_file_id IS NOT NULL) AS dl "
                    "FROM documents WHERE id = ANY(%s)", ([d["doc_id"] for d in out],))
        dlmap = {r["id"]: r["dl"] for r in cur.fetchall()}
        cur.close(); conn.close()
        for d in out:
            d["download_link"] = (f"https://leo.hayuma.org/files/c/{d['doc_id']}"
                                  if dlmap.get(d["doc_id"]) else None)
    except Exception:
        pass
    return f"Semantic matches for {query!r} (ranked by meaning):\n" + json.dumps(out, indent=2)


TOOL_FUNCTIONS = {
    "semantic_search":       t_semantic_search,
    "query_documents":       t_query_documents,
    "read_document":         t_read_document,
    "search_drive":          t_search_drive,
    "read_drive":            t_read_drive,
    "vault_register":        t_vault_register,
    "vault_bind_scan":       t_vault_bind_scan,
    "vault_find":            t_vault_find,
    "vault_queue":           t_vault_queue,
    "vault_missing":         t_vault_missing,
    "vault_last":            t_vault_last,
    "find_matter_for_party": t_find_matter_for_party,
    "link_documents":        t_link_documents,
}


def run_tool(name, args):
    """Dispatch a tool call. Returns the result string."""
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return f"Unknown tool: {name}"
    try:
        return fn(args or {})
    except Exception as e:
        return f"Tool {name} raised {type(e).__name__}: {str(e)[:300]}"
