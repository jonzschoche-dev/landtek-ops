"""vault_endpoints.py — deploy_362.

Six deterministic SQL endpoints exposing the master vault to Leo (via n8n
tool nodes) and to manual_ops scripts. No LLM in any of these. Each maps
1:1 to a vault verb Kristyle and Jonathan can use in Telegram.

Endpoints:
    POST /api/vault/register     — create a new physical-master document row
    POST /api/vault/attach_scan  — attach a digital scan to an existing entry
    GET  /api/vault/find         — look up an entry by SECTION-NNN
    GET  /api/vault/queue        — pending actions for a user (default Kristyle)
    GET  /api/vault/missing      — docs in a matter that look like they need masters
    GET  /api/vault/last         — recent vault entries (audit trail)

All errors return JSON: {"ok": false, "error": "<message>"}. Successful
responses include {"ok": true, ...payload}.

Schema reference: deploy_361_vault_schema.
"""
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
import psycopg2
import psycopg2.extras

PG_DSN = os.getenv("LEO_TOOLS_PG_DSN",
                   "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

bp = Blueprint("vault", __name__, url_prefix="/api/vault")

KNOWN_MATTER_PREFIXES = ("MWK-", "PAR-", "AUTO-", "ARCHIVE-")
SECTION_RE = re.compile(r"^[A-Z]{2,5}$")


def _db():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn


def _section_exists(cur, code):
    cur.execute("SELECT 1 FROM vault_sections WHERE code = %s AND active", (code,))
    return cur.fetchone() is not None


def _matter_exists(cur, matter_code):
    cur.execute("SELECT 1 FROM matters WHERE matter_code = %s", (matter_code,))
    return cur.fetchone() is not None


# ── 1. register ────────────────────────────────────────────────────────────
@bp.route("/register", methods=["POST"])
def register():
    """Create a new physical-master document row.

    Required: section, number, description, matter_code.
    Optional: vault_location (free-text geography), drive_file_id (initial scan).
    """
    data = request.get_json(force=True, silent=True) or {}
    section = (data.get("section") or "").strip().upper()
    number = data.get("number")
    description = (data.get("description") or "").strip()
    matter_code = (data.get("matter_code") or "").strip()
    vault_location = (data.get("vault_location") or "").strip() or None
    drive_file_id = (data.get("drive_file_id") or "").strip() or None

    # Validation
    if not SECTION_RE.match(section):
        return jsonify(ok=False, error=f"invalid_section_format: {section!r}"), 400
    try:
        number = int(number)
        if number < 1 or number > 9999:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(ok=False, error=f"invalid_number: {number!r}"), 400
    if len(description) < 3:
        return jsonify(ok=False, error="description_too_short"), 400
    if not matter_code or not matter_code.startswith(KNOWN_MATTER_PREFIXES):
        return jsonify(ok=False,
                       error=f"matter_code_required (must start with one of {KNOWN_MATTER_PREFIXES}): {matter_code!r}"), 400

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if not _section_exists(cur, section):
            return jsonify(ok=False,
                           error=f"unknown_section: {section!r} (run /api/vault/sections to list)"), 400
        if not _matter_exists(cur, matter_code):
            return jsonify(ok=False,
                           error=f"unknown_matter: {matter_code!r}"), 400

        # Check duplicate locator
        cur.execute("""
            SELECT id FROM documents
             WHERE vault_section = %s AND vault_number = %s
        """, (section, number))
        existing = cur.fetchone()
        if existing:
            return jsonify(ok=False,
                           error=f"locator_taken: {section}-{number:03d} already assigned to doc#{existing['id']}"), 409

        # Pull case_file from matter
        cur.execute("SELECT case_file FROM matters WHERE matter_code = %s",
                    (matter_code,))
        m = cur.fetchone()
        case_file = m["case_file"] if m else None

        smart_filename = f"{section}-{number:03d} {description}"

        cur.execute("""
            INSERT INTO documents
                (case_file, smart_filename, original_filename, mime_type,
                 master_form, vault_section, vault_number, vault_location,
                 drive_link, status, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'physical', %s, %s, %s, %s,
                    'vault_registered', NOW(), NOW())
            RETURNING id
        """, (case_file, smart_filename, smart_filename, "physical/paper",
              section, number, vault_location,
              f"drive_file_id:{drive_file_id}" if drive_file_id else None))
        new_id = cur.fetchone()["id"]

        # Link to matter via junction
        cur.execute("""
            INSERT INTO document_matter_links (doc_id, matter_code, link_type, confidence, created_at)
            VALUES (%s, %s, 'vault_registration', 1.0, NOW())
            ON CONFLICT DO NOTHING
        """, (new_id, matter_code))

        return jsonify(ok=True, doc_id=new_id,
                       locator=f"{section}-{number:03d}",
                       smart_filename=smart_filename,
                       matter_code=matter_code,
                       case_file=case_file)
    except Exception as e:
        return jsonify(ok=False, error=f"db_error: {type(e).__name__}: {str(e)[:200]}"), 500
    finally:
        cur.close()
        conn.close()


# ── 2. attach_scan ─────────────────────────────────────────────────────────
@bp.route("/attach_scan", methods=["POST"])
def attach_scan():
    """Attach a digital scan to an existing physical-master entry.

    Body: section, number, drive_file_id (or drive_link / scan_doc_id).
    Creates a digital-master document row for the scan, then sets
    documents.digital_scan_id on the physical master to point at it.
    If scan_doc_id is provided, links to that existing doc instead.
    """
    data = request.get_json(force=True, silent=True) or {}
    section = (data.get("section") or "").strip().upper()
    number = data.get("number")
    drive_file_id = (data.get("drive_file_id") or "").strip() or None
    drive_link = (data.get("drive_link") or "").strip() or None
    scan_doc_id = data.get("scan_doc_id")

    try:
        number = int(number)
    except (TypeError, ValueError):
        return jsonify(ok=False, error=f"invalid_number: {number!r}"), 400
    if not (drive_file_id or drive_link or scan_doc_id):
        return jsonify(ok=False,
                       error="need drive_file_id or drive_link or scan_doc_id"), 400

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, smart_filename, case_file
              FROM documents
             WHERE vault_section = %s AND vault_number = %s
               AND master_form = 'physical'
        """, (section, number))
        master = cur.fetchone()
        if not master:
            return jsonify(ok=False,
                           error=f"no_master_at_{section}-{number:03d}"), 404

        if scan_doc_id:
            cur.execute("SELECT id FROM documents WHERE id = %s", (scan_doc_id,))
            if not cur.fetchone():
                return jsonify(ok=False,
                               error=f"scan_doc_id_not_found: {scan_doc_id}"), 404
            scan_id = scan_doc_id
        else:
            # Create a digital-master shell row for the scan
            cur.execute("""
                INSERT INTO documents
                    (case_file, smart_filename, original_filename, mime_type,
                     master_form, drive_link, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'application/pdf',
                        'digital', %s, 'scan_of_vault_master', NOW(), NOW())
                RETURNING id
            """, (master["case_file"],
                  f"Scan of {master['smart_filename']}",
                  f"scan_of_{section}-{number:03d}.pdf",
                  drive_link or f"drive_file_id:{drive_file_id}"))
            scan_id = cur.fetchone()["id"]

        cur.execute("""
            UPDATE documents
               SET digital_scan_id = %s, updated_at = NOW()
             WHERE id = %s
        """, (scan_id, master["id"]))

        return jsonify(ok=True, master_doc_id=master["id"],
                       scan_doc_id=scan_id,
                       locator=f"{section}-{number:03d}")
    except Exception as e:
        return jsonify(ok=False, error=f"db_error: {type(e).__name__}: {str(e)[:200]}"), 500
    finally:
        cur.close()
        conn.close()


# ── 3. find ────────────────────────────────────────────────────────────────
@bp.route("/find", methods=["GET"])
def find():
    """Look up a vault entry by SECTION-NNN."""
    section = (request.args.get("section") or "").strip().upper()
    try:
        number = int(request.args.get("number"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="invalid_number"), 400

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT d.id, d.smart_filename, d.case_file, d.master_form,
                   d.vault_section, d.vault_number, d.vault_location,
                   d.digital_scan_id, d.status, d.created_at,
                   array_agg(DISTINCT dml.matter_code) FILTER (WHERE dml.matter_code IS NOT NULL) AS matter_codes
              FROM documents d
              LEFT JOIN document_matter_links dml ON dml.doc_id = d.id
             WHERE d.vault_section = %s AND d.vault_number = %s
             GROUP BY d.id
        """, (section, number))
        row = cur.fetchone()
        if not row:
            return jsonify(ok=False,
                           error=f"not_found: {section}-{number:03d}"), 404
        return jsonify(ok=True, **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                    for k, v in dict(row).items()})
    finally:
        cur.close()
        conn.close()


# ── 4. queue ───────────────────────────────────────────────────────────────
@bp.route("/queue", methods=["GET"])
def queue():
    """Pending actions for the filing assistant.

    Today's queue:
      - physical masters created without a digital scan attached
      - (future) returning-stamp filings overdue
    """
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, smart_filename, vault_section, vault_number,
                   case_file, created_at
              FROM documents
             WHERE master_form = 'physical'
               AND digital_scan_id IS NULL
             ORDER BY created_at DESC
             LIMIT 30
        """)
        unsanned = [
            {**dict(r), "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in cur.fetchall()
        ]
        return jsonify(ok=True,
                       pending_scans=unsanned,
                       counts={"pending_scans": len(unsanned)})
    finally:
        cur.close()
        conn.close()


# ── 5. missing ─────────────────────────────────────────────────────────────
@bp.route("/missing", methods=["GET"])
def missing():
    """Docs in a matter that look like they need physical masters but don't have one.

    Heuristic v1: smart_filename matches notarized/affidavit/deed/title/court-order
    keywords AND no row in documents has master_form='physical' linked to that
    same source doc (by filename or content_hash).
    """
    matter_code = (request.args.get("matter_code") or "").strip()
    if not matter_code:
        return jsonify(ok=False, error="matter_code_required"), 400

    KEYWORDS = [
        ("AFF", "%affidavit%"),
        ("AFF", "%sworn statement%"),
        ("SPA", "%special power of attorney%"),
        ("SPA", "%spa %"),
        ("DEED", "%deed of%"),
        ("TCT", "%transfer certificate of title%"),
        ("TCT", "%tct%"),
        ("CRT", "%manifestation%"),
        ("CRT", "%pleading%"),
        ("RES", "%resolution%"),
        ("RES", "%decision%"),
        ("RES", "%order dated%"),
        ("CONT", "%lease%"),
        ("CONT", "%mortgage%"),
        ("CONT", "%memorandum of agreement%"),
        ("PSA", "%birth certificate%"),
        ("PSA", "%death certificate%"),
        ("PSA", "%marriage certificate%"),
        ("TAX", "%tax declaration%"),
        ("TAX", "%real property tax%"),
    ]

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        suggestions = []
        seen = set()
        for section_hint, kw in KEYWORDS:
            cur.execute("""
                SELECT d.id, d.smart_filename, d.case_file
                  FROM documents d
                  LEFT JOIN document_matter_links dml ON dml.doc_id = d.id
                 WHERE (dml.matter_code = %s OR d.case_file IN (
                            SELECT DISTINCT case_file FROM matters WHERE matter_code = %s))
                   AND d.master_form = 'digital'
                   AND d.smart_filename ILIKE %s
                   AND NOT EXISTS (
                       SELECT 1 FROM documents pm
                        WHERE pm.master_form = 'physical'
                          AND pm.digital_scan_id = d.id
                   )
                 LIMIT 5
            """, (matter_code, matter_code, kw))
            for r in cur.fetchall():
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                suggestions.append({
                    "doc_id": r["id"],
                    "smart_filename": r["smart_filename"],
                    "case_file": r["case_file"],
                    "suggested_section": section_hint,
                    "matched_keyword": kw.strip("%"),
                })
            if len(suggestions) >= 25:
                break
        return jsonify(ok=True, matter_code=matter_code,
                       suggestions=suggestions[:25],
                       count=len(suggestions[:25]))
    finally:
        cur.close()
        conn.close()


# ── 6. last ────────────────────────────────────────────────────────────────
@bp.route("/last", methods=["GET"])
def last():
    """Recent vault entries — audit trail."""
    try:
        n = int(request.args.get("n", 10))
        n = max(1, min(n, 100))
    except (TypeError, ValueError):
        n = 10

    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, smart_filename, vault_section, vault_number,
                   vault_location, digital_scan_id, case_file, created_at
              FROM documents
             WHERE master_form = 'physical'
             ORDER BY created_at DESC
             LIMIT %s
        """, (n,))
        entries = [
            {**dict(r), "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in cur.fetchall()
        ]
        return jsonify(ok=True, entries=entries, count=len(entries))
    finally:
        cur.close()
        conn.close()


# ── helper: sections ───────────────────────────────────────────────────────
@bp.route("/sections", methods=["GET"])
def sections():
    """List active section codes — useful when Leo needs to remind Kristyle."""
    conn = _db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT code, label, description
              FROM vault_sections
             WHERE active
             ORDER BY code
        """)
        return jsonify(ok=True, sections=[dict(r) for r in cur.fetchall()])
    finally:
        cur.close()
        conn.close()
