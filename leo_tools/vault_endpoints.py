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

# Section → keyword hints that boost corpus-search confidence
SECTION_KEYWORDS = {
    "SPA":  ["special power of attorney", "spa", "attorney-in-fact",
             "attorney in fact", "apostille"],
    "AFF":  ["affidavit"],
    "DEED": ["deed of", "deed of sale", "deed of donation", "deed of absolute"],
    "TCT":  ["transfer certificate of title", "tct"],
    "TAX":  ["tax declaration", "tax receipt", "real property tax"],
    "PSA":  ["birth certificate", "death certificate", "marriage certificate"],
    "CRT":  ["pleading", "manifestation", "order", "stamped received"],
    "RES":  ["resolution", "decision", "ruling"],
    "CONT": ["contract", "lease", "memorandum of agreement", "mortgage"],
    "CORR": ["letter", "correspondence", "inquiry", "request"],
}

# Section → classification values in the documents.classification column
# that are EXACT-MATCH boosts for corpus search.
SECTION_CLASSIFICATIONS = {
    "SPA":  ["Special Power of Attorney", "Power of Attorney"],
    "AFF":  ["Affidavit"],
    "DEED": ["Deed"],
    "TCT":  ["Title (TCT/OCT)"],
    "TAX":  ["Tax Document"],
    "PSA":  ["Birth Certificate", "Death Certificate", "Marriage Certificate"],
    "CRT":  ["Court Filing", "Pleading", "Manifestation"],
    "RES":  ["Resolution", "Decision", "Court Order"],
    "CONT": ["Contract"],
    "CORR": ["Letter", "Correspondence", "Government Submission"],
}

# Stopwords + section-name noise that shouldn't drive matching
_STOP = set("""a an and as at be by for from has have he her his i in is it
its of on or our she that the their this to was with you your we
under upon dated re subject regarding letter document file folder
matter case section number entry document zschoche""".split())

_NAME_RE = re.compile(r"\b([A-Z][a-z'\-]{2,}(?:\s+[A-Z][a-z'\-]{2,}){0,3})\b")
_DATE_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4}|"
    r"\w+\s+\d{1,2},?\s+\d{4})\b", re.IGNORECASE)


def _tokenize_description(description, section):
    """Pull proper names + dates + section keywords as searchable tokens."""
    names = set(_NAME_RE.findall(description or ""))
    names = {n for n in names if n.lower() not in _STOP and len(n) >= 4}
    dates = set(_DATE_RE.findall(description or ""))
    kw_hits = []
    for kw in SECTION_KEYWORDS.get(section, []):
        if kw.lower() in (description or "").lower():
            kw_hits.append(kw)
    return {"names": sorted(names), "dates": sorted(dates), "keywords": kw_hits}


def _find_corpus_match(cur, section, description, matter_code, case_file):
    """Search corpus for an existing digital match. Returns (best_doc_id,
    confidence:0-1, candidates:list). Confidence 0.8+ is auto-link
    threshold."""
    tokens = _tokenize_description(description, section)
    name_tokens = [t for t in tokens["names"] if len(t) >= 4][:4]
    if not name_tokens and not tokens["keywords"]:
        return None, 0.0, []

    # Build ILIKE patterns — at least one name OR a section keyword must hit
    patterns = []
    args = []
    if name_tokens:
        for n in name_tokens:
            patterns.append("(extracted_text ILIKE %s OR smart_filename ILIKE %s)")
            args.extend([f"%{n}%", f"%{n}%"])
    kw_patterns = []
    for kw in (tokens["keywords"] or SECTION_KEYWORDS.get(section, []))[:3]:
        kw_patterns.append("(extracted_text ILIKE %s OR smart_filename ILIKE %s)")
        args.extend([f"%{kw}%", f"%{kw}%"])

    where_pieces = ["master_form = 'digital'"]
    if case_file:
        where_pieces.append("(case_file = %s OR case_file IS NULL)")
        args.insert(0, case_file)
    if kw_patterns:
        where_pieces.append("(" + " OR ".join(kw_patterns) + ")")
    if patterns:
        # at least one name match required
        where_pieces.append("(" + " OR ".join(patterns) + ")")

    # First pull: classification-correct docs (guaranteed inclusion).
    # These get priority regardless of name/keyword matches.
    classification_rows = []
    expected_clf = SECTION_CLASSIFICATIONS.get(section, [])
    if expected_clf:
        clf_args = []
        clf_args.extend(expected_clf)
        clf_q = f"""
            SELECT id, smart_filename, doc_date, classification, drive_link,
                   extracted_text
              FROM documents
             WHERE master_form = 'digital'
               AND classification IN ({','.join(['%s'] * len(expected_clf))})
             {"AND (case_file = %s OR case_file IS NULL)" if case_file else ""}
             ORDER BY doc_date DESC NULLS LAST
             LIMIT 25
        """
        if case_file:
            clf_args.append(case_file)
        cur.execute(clf_q, clf_args)
        classification_rows = list(cur.fetchall())

    # Second pull: keyword / name match candidates
    sql = f"""
        SELECT id, smart_filename, doc_date, classification, drive_link,
               extracted_text
          FROM documents
         WHERE {' AND '.join(where_pieces)}
         ORDER BY doc_date DESC NULLS LAST
         LIMIT 25
    """
    cur.execute(sql, args)
    keyword_rows = list(cur.fetchall())

    # Merge unique
    seen_ids = set()
    rows = []
    for r in classification_rows + keyword_rows:
        if r["id"] in seen_ids:
            continue
        seen_ids.add(r["id"])
        rows.append(r)
    if not rows:
        return None, 0.0, []

    # Score candidates: classification match (heaviest) + name + kw + date
    expected_classifications = [c.lower() for c
                                in SECTION_CLASSIFICATIONS.get(section, [])]
    scored = []
    for r in rows:
        haystack = ((r.get("extracted_text") or "") + " " +
                    (r.get("smart_filename") or "")).lower()
        name_hits = sum(1 for n in name_tokens if n.lower() in haystack)
        kw_hits = sum(1 for k in (tokens["keywords"] or
                                  SECTION_KEYWORDS.get(section, []))
                      if k.lower() in haystack)
        date_hits = sum(1 for d in tokens["dates"]
                        if d.lower() in haystack)
        # Classification match — the single strongest signal that this doc
        # IS the kind of thing the vault entry represents
        clf = (r.get("classification") or "").lower()
        classification_hit = 1 if clf and clf in expected_classifications else 0
        # filename keyword match (e.g. "special_power_of_attorney.pdf" for SPA)
        filename = (r.get("smart_filename") or "").lower()
        filename_kw_hit = 1 if any(kw.lower().replace(" ", "_") in filename
                                    or kw.lower() in filename
                                    for kw in SECTION_KEYWORDS.get(section, [])) else 0
        # Tiebreakers — signed PDFs beat working .docx, dated beats undated
        is_pdf = filename.endswith(".pdf")
        is_docx = filename.endswith(".docx") or filename.endswith(".doc")
        has_doc_date = 1 if r.get("doc_date") else 0
        format_bonus = (2 if is_pdf else 0) + (-2 if is_docx else 0)
        total = (classification_hit * 8 +     # heaviest — IS this thing
                 filename_kw_hit * 4 +         # strong — filename signals type
                 name_hits * 2 +
                 kw_hits +
                 date_hits * 2 +
                 format_bonus +                # prefer PDF over docx
                 has_doc_date * 2)             # dated docs over undated
        scored.append({
            "doc_id": r["id"],
            "smart_filename": r["smart_filename"],
            "doc_date": str(r["doc_date"]) if r["doc_date"] else None,
            "classification": r["classification"],
            "drive_link": r["drive_link"],
            "score": total,
            "classification_hit": classification_hit,
            "filename_kw_hit": filename_kw_hit,
            "name_hits": name_hits,
            "kw_hits": kw_hits,
            "date_hits": date_hits,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Confidence: top score normalized. Max possible includes the heavy bonuses.
    max_possible = (8 + 4 + len(name_tokens) * 2 + 3 + len(tokens["dates"]) * 2) or 1
    top = scored[0]
    confidence = min(1.0, top["score"] / max_possible)
    # Auto-link requires EITHER classification match + 1 other hit,
    # OR filename match + name hit + date hit.
    auto_link = False
    if top["classification_hit"] and (top["name_hits"] or top["filename_kw_hit"]):
        auto_link = True
    elif top["filename_kw_hit"] and top["name_hits"] and top["date_hits"]:
        auto_link = True
    if auto_link and confidence >= 0.4:
        return top["doc_id"], confidence, scored[:5]
    return None, confidence, scored[:5]


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
    Optional: auto_attach_sender_id — telegram sender id. If set, the most
       recent unattached photo from this sender in telegram_inbox (within
       the last hour) becomes the digital scan automatically.

    BRIDGE-TO-DIGITAL INVARIANT: every physical master MUST have a
    digital corpus row. If none can be auto-attached, the register call
    still succeeds but a placeholder digital row is created so the
    digital_scan_id is always non-null.
    """
    data = request.get_json(force=True, silent=True) or {}
    section = (data.get("section") or "").strip().upper()
    number = data.get("number")
    description = (data.get("description") or "").strip()
    matter_code = (data.get("matter_code") or "").strip()
    vault_location = (data.get("vault_location") or "").strip() or None
    drive_file_id = (data.get("drive_file_id") or "").strip() or None
    auto_attach_sender_id = (data.get("auto_attach_sender_id") or "").strip() or None
    # Multi-matter: array of matter_codes this doc is materially relevant to
    # beyond the primary. Default empty — caller can add via subsequent
    # /api/vault/cross_link calls.
    related_matters = data.get("related_matters") or []
    if isinstance(related_matters, str):
        related_matters = [m.strip() for m in related_matters.split(",") if m.strip()]

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

        # Link to PRIMARY matter via junction (deploy_279 schema, relation_kind enum)
        cur.execute("""
            INSERT INTO document_matter_links
                (doc_id, matter_code, case_file, relation_kind, provenance_level,
                 linked_by, note, created_at, updated_at)
            VALUES (%s, %s, %s, 'primary', 'verified',
                    'vault_register_endpoint',
                    'physical master vaulted via vault command',
                    NOW(), NOW())
            ON CONFLICT DO NOTHING
        """, (new_id, matter_code, case_file))

        # Link to additional RELATED matters (multi-matter relevance)
        for rm in related_matters:
            if rm == matter_code:
                continue
            # Validate the related matter exists
            cur.execute("SELECT case_file FROM matters WHERE matter_code = %s", (rm,))
            mrow = cur.fetchone()
            if not mrow:
                continue
            cur.execute("""
                INSERT INTO document_matter_links
                    (doc_id, matter_code, case_file, relation_kind, provenance_level,
                     linked_by, note, created_at, updated_at)
                VALUES (%s, %s, %s, 'cross_proof', 'verified',
                        'vault_register_endpoint',
                        'multi-matter relevance declared at vault registration',
                        NOW(), NOW())
                ON CONFLICT DO NOTHING
            """, (new_id, rm, mrow["case_file"]))

        # ── BRIDGE-TO-DIGITAL: find or create the digital scan row ──────
        # Order of preference:
        #   1. SEARCH CORPUS for existing digital match (deterministic, scored)
        #   2. AUTO-ATTACH recent photo from sender (Telegram inbox)
        #   3. PLACEHOLDER (real gap — surfaces for follow-up)
        scan_doc_id = None
        scan_source = None
        scan_candidates = []
        scan_confidence = None

        # Corpus search — SUGGEST ONLY, never auto-attach. The keyword matcher
        # has repeatedly bound the WRONG document (CRT-001/002, CORR-015..020/028,
        # AFF-001/003/007 all got mislinked to drafts or unrelated docs). So we no
        # longer auto-attach anything, and we no longer create placeholder shells.
        # The entry is registered as 'needs scan'; Leo confirms the correct scan
        # by CONTENT (search_drive/query_documents + read_drive/read_document) and
        # binds it explicitly with /api/vault/attach_scan.
        best, conf, candidates = _find_corpus_match(
            cur, section, description, matter_code, case_file)
        scan_candidates = candidates
        scan_confidence = conf

        cur.execute("""
            UPDATE documents SET status = 'vault_registered_needs_scan',
                   updated_at = NOW()
             WHERE id = %s
        """, (new_id,))

        return jsonify(ok=True, doc_id=new_id,
                       locator=f"{section}-{number:03d}",
                       smart_filename=smart_filename,
                       matter_code=matter_code,
                       case_file=case_file,
                       digital_scan_id=None,
                       needs_scan=True,
                       note=("Registered with NO scan attached. Auto-matching is "
                             "OFF — it kept linking the wrong document. CONFIRM the "
                             "correct scan by its CONTENT, then bind it with "
                             "attach_scan. Treat scan_suggestions as hints only."),
                       scan_suggestions=scan_candidates,
                       scan_confidence=scan_confidence)
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
