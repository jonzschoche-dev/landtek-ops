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
            "Search the LANDTEK Google Drive for files (recently uploaded "
            "files often aren't ingested into the corpus yet). Returns "
            "drive_id, name, modifiedTime. Use when query_documents returns "
            "nothing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name_contains": {"type": "string", "description": "substring of filename"},
                "limit":         {"type": "integer", "description": "max results (default 10)"},
            },
            "required": ["name_contains"],
        },
    },
    {
        "name": "vault_register",
        "description": (
            "Create a new physical-master vault entry. Use this when you've "
            "determined the section, number, matter, and description from "
            "the conversation. The system will auto-link the digital scan "
            "by corpus search."
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


def t_search_drive(args):
    name = args["name_contains"]
    limit = int(args.get("limit", 10))
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            DRIVE_CREDS_PATH,
            scopes=["https://www.googleapis.com/auth/drive.readonly"])
        svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        resp = svc.files().list(
            q=f"name contains '{name}' and trashed = false",
            pageSize=limit, orderBy="modifiedTime desc",
            fields="files(id, name, modifiedTime, mimeType, size)",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files = resp.get("files", [])
        return json.dumps([{
            "drive_id": f["id"],
            "name": f.get("name", ""),
            "modified": f.get("modifiedTime", "")[:19],
            "mime": f.get("mimeType", ""),
            "size": f.get("size"),
        } for f in files], indent=2)
    except Exception as e:
        return f"Drive search failed: {e}"


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


TOOL_FUNCTIONS = {
    "query_documents":       t_query_documents,
    "read_document":         t_read_document,
    "search_drive":          t_search_drive,
    "vault_register":        t_vault_register,
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
