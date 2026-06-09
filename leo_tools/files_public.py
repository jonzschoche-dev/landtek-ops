"""files_public - unauthenticated /files/c/<doc_id> blueprint.

Streams docs to Jonathan's phone from Telegram replies without depending on
Drive's preview UI, in-app browser auth state, or Google session cookies.

Nginx is already configured to proxy /files/c/ to this port without
basic-auth (vs /files/ which DOES require it).

Strategy per doc:
  1. If documents.file_path exists locally -> stream from disk
  2. Else if drive_file_id is set -> stream from Drive via service account
  3. Else 404

Service-account creds at /root/landtek/google-creds.json; the LANDTEK Drive
folder is shared with leolandtek-docai@landtek.iam.gserviceaccount.com.
"""
from __future__ import annotations

import io
import os
from flask import Blueprint, Response, abort, send_file

import psycopg2

bp = Blueprint("files_public", __name__, url_prefix="/files/c")

GOOGLE_CREDS_PATH = "/root/landtek/google-creds.json"


def _db():
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "172.18.0.3"),
        dbname=os.environ.get("PGDATABASE", "n8n"),
        user=os.environ.get("PGUSER", "n8n"),
        password=os.environ.get("PGPASSWORD", "n8npassword"),
    )


_drive_client = None
def _drive():
    """Lazy-init the Drive service-account client. Cached for the process."""
    global _drive_client
    if _drive_client is not None:
        return _drive_client
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDS_PATH,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    _drive_client = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _drive_client


def _stream_drive(drive_file_id, filename, mime):
    """Fetch the file bytes from Drive and return as a Flask Response."""
    from googleapiclient.http import MediaIoBaseDownload
    svc = _drive()
    buf = io.BytesIO()
    req = svc.files().get_media(fileId=drive_file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)
    safe_name = (filename or f"{drive_file_id}.pdf").replace('"', "_")
    return Response(
        buf.read(),
        mimetype=mime or "application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
            "Cache-Control": "private, max-age=3600",
            "X-Source": "drive-proxy",
        },
    )


@bp.route("/<int:doc_id>")
def serve(doc_id):
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, file_path, drive_file_id, mime_type, original_filename, smart_filename
             FROM documents WHERE id = %s""",
        (doc_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404, "doc not found")
    _id, file_path, drive_id, mime, orig_name, smart_name = row
    name = smart_name or orig_name or f"doc-{doc_id}.pdf"

    # 1. Local file path (fastest)
    if file_path and os.path.exists(file_path):
        return send_file(
            file_path,
            as_attachment=False,
            download_name=name,
            mimetype=mime or "application/pdf",
        )

    # 2. Drive fallback
    if drive_id:
        try:
            return _stream_drive(drive_id, name, mime)
        except Exception as e:
            return Response(
                f"failed to stream from Drive: {type(e).__name__}: {e}",
                status=502,
                mimetype="text/plain",
            )

    return Response(
        f"doc {doc_id} has no file_path and no drive_file_id",
        status=404,
        mimetype="text/plain",
    )


@bp.route("/vault")
def vault_table():
    """Live HTML table: every physical vault entry <-> its digital corpus copy
    and a download link. Public (same as the file proxy), mobile-friendly, and
    always current. Leo links here when anyone asks for "the vault table" or the
    physical<->digital correlation, instead of trying to paste a table into chat.
    """
    import html
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.vault_section, d.vault_number, d.smart_filename,
               d.digital_scan_id, s.smart_filename, s.doc_date,
               (s.file_path IS NOT NULL OR s.drive_file_id IS NOT NULL) AS dl
          FROM documents d
          LEFT JOIN documents s ON s.id = d.digital_scan_id
         WHERE d.master_form = 'physical' AND d.vault_section IS NOT NULL
         ORDER BY d.vault_section, d.vault_number
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    body = []
    linked = 0
    for sec, num, pname, scan_id, dname, ddate, dl in rows:
        locator = f"{sec}-{num:03d}"
        # physical_name usually starts with the locator — strip it for clarity
        desc = (pname or "").strip()
        if desc.upper().startswith(locator):
            desc = desc[len(locator):].strip()
        desc = html.escape(desc[:90])
        dname_e = html.escape((dname or "")[:60])
        ddate_e = html.escape(str(ddate) if ddate else "")
        if scan_id and dl:
            link = (f'<a href="/files/c/{scan_id}">open / download</a>'
                    f' <span class="muted">(doc#{scan_id})</span>')
            linked += 1
        elif scan_id:
            link = f'<span class="warn">linked but no scan uploaded (doc#{scan_id})</span>'
        else:
            link = '<span class="warn">no digital copy yet</span>'
        body.append(
            f"<tr><td class='loc'>{locator}</td><td>{desc}</td>"
            f"<td>{dname_e}<br><span class='muted'>{ddate_e}</span></td>"
            f"<td>{link}</td></tr>"
        )

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LandTek Vault &harr; Digital Corpus</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;color:#1a1a1a;background:#fafafa}}
 h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}}
 th{{background:#f4f4f6;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#555}}
 td.loc{{font-weight:600;white-space:nowrap}} a{{color:#0a58ca;text-decoration:none}} a:hover{{text-decoration:underline}}
 .muted{{color:#999;font-size:11px}} .warn{{color:#b54708;font-size:12px}}
</style></head><body>
<h1>LandTek Physical Vault &harr; Digital Corpus</h1>
<div class="sub">{len(rows)} vault entries &middot; {linked} with a downloadable digital copy &middot; live view</div>
<table><thead><tr><th>Vault</th><th>Document</th><th>Digital copy</th><th>Link</th></tr></thead>
<tbody>{''.join(body)}</tbody></table>
</body></html>"""
    return Response(page, mimetype="text/html")


@bp.route("/m/<matter_code>")
def matter_table(matter_code):
    """Live HTML table of every document linked to a matter, with download
    links. Public, mobile-friendly. Leo links here when asked for "all the
    documents / links for ARTA-NNNN" instead of pasting URLs into chat."""
    import html
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d.id, COALESCE(NULLIF(d.smart_filename,''), d.original_filename),
               d.doc_date, d.classification,
               (d.file_path IS NOT NULL OR d.drive_file_id IS NOT NULL) AS dl
          FROM documents d
          JOIN document_matter_links l ON l.doc_id = d.id
         WHERE l.matter_code = %s
         ORDER BY d.doc_date NULLS LAST, d.id
        """,
        (matter_code,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    body = []
    avail = 0
    for did, fname, ddate, cls, dl in rows:
        nm = html.escape((fname or f"doc {did}")[:78])
        dt = html.escape(str(ddate) if ddate else "")
        cl = html.escape((cls or "")[:24])
        if dl:
            link = f'<a href="/files/c/{did}">download</a>'
            avail += 1
        else:
            link = '<span class="warn">no scan yet</span>'
        body.append(
            f"<tr><td>{dt}</td><td>{nm}<br><span class='muted'>{cl} · doc#{did}</span></td>"
            f"<td>{link}</td></tr>"
        )
    title = html.escape(matter_code)
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — documents</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;background:#fafafa;color:#1a1a1a}}
 h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}}
 th{{background:#f4f4f6;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#555}}
 a{{color:#0a58ca;text-decoration:none}} a:hover{{text-decoration:underline}}
 .muted{{color:#999;font-size:11px}} .warn{{color:#b54708;font-size:12px}}
</style></head><body>
<h1>{title} — documents</h1>
<div class="sub">{len(rows)} documents · {avail} downloadable · live view</div>
<table><thead><tr><th>Date</th><th>Document</th><th>File</th></tr></thead>
<tbody>{''.join(body) or '<tr><td colspan=3>No documents linked to this matter.</td></tr>'}</tbody></table>
</body></html>"""
    return Response(page, mimetype="text/html")


@bp.route("/<int:doc_id>/info")
def info(doc_id):
    """Metadata JSON so Leo or n8n can confirm what the URL serves."""
    from flask import jsonify
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, case_file, matter_code, smart_filename, original_filename,
                  mime_type, drive_file_id, file_path, document_title, summary
             FROM documents WHERE id = %s""",
        (doc_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        abort(404)
    keys = ["id", "case_file", "matter_code", "smart_filename", "original_filename",
            "mime_type", "drive_file_id", "file_path", "document_title", "summary"]
    return jsonify(dict(zip(keys, row)))


# ─── Evidence Matrix ─────────────────────────────────────────────────────────
@bp.route("/matrix")
def evidence_matrix_index():
    return _render_matrix(None)


@bp.route("/matrix/<case_file>")
def evidence_matrix_case(case_file):
    return _render_matrix(case_file)


def _render_matrix(case_file):
    """Live evidence matrix: each claim/allegation with its CONFIRMED exhibits
    (accepted into evidence_trail) vs SUGGESTED exhibits (pending Opus proposals,
    confidence-scored). This is the 'annexes existing vs suggested' tracker."""
    import html, json
    conn = _db()
    cur = conn.cursor()
    q = ("SELECT id, case_file, short_label, claim_text, claim_kind, "
         "required_to_prove, status, priority FROM claims")
    params = ()
    if case_file:
        q += " WHERE case_file = %s"
        params = (case_file,)
    q += " ORDER BY priority DESC NULLS LAST, id"
    cur.execute(q, params)
    claims = cur.fetchall()

    cur.execute("SELECT claim_id, supporting_doc_id, relation_kind, weight, "
                "provenance_level, narrative FROM evidence_trail")
    confirmed = {}
    for cid, doc, rel, wt, prov, narr in cur.fetchall():
        confirmed.setdefault(cid, []).append((doc, rel, wt, prov, narr))

    cur.execute("SELECT claim_id, supporting_doc_id, relation_kind, weight, "
                "confidence, rationale FROM evidence_trail_proposals "
                "WHERE status = 'pending'")
    suggested = {}
    for cid, doc, rel, wt, conf, rat in cur.fetchall():
        suggested.setdefault(cid, []).append((doc, rel, wt, conf, rat))

    docids = set()
    for d in list(confirmed.values()) + list(suggested.values()):
        for t in d:
            docids.add(t[0])
    names = {}
    if docids:
        cur.execute("SELECT id, COALESCE(NULLIF(smart_filename,''), original_filename), "
                    "(file_path IS NOT NULL OR drive_file_id IS NOT NULL) "
                    "FROM documents WHERE id = ANY(%s)", (list(docids),))
        for did, nm, dl in cur.fetchall():
            names[did] = (nm or f"doc {did}", dl)
    cur.close(); conn.close()

    def doclink(did):
        nm, dl = names.get(did, (f"doc {did}", False))
        nm = html.escape(nm[:54])
        if dl:
            return f'<a href="/files/c/{did}">{nm}</a> <span class="muted">#{did}</span>'
        return f'{nm} <span class="warn">#{did} no scan</span>'

    PROV = {"verified": "verified", "inferred_strong": "inferred",
            "inferred_weak": "weak"}
    cards = []
    n_conf = n_sugg = 0
    for cid, cf, label, text, kind, req, status, prio in claims:
        elems = req
        if isinstance(elems, str):
            try:
                elems = json.loads(elems)
            except Exception:
                elems = [elems]
        elems = elems or []
        cfm = confirmed.get(cid, [])
        sug = suggested.get(cid, [])
        n_conf += len(cfm)
        n_sugg += len(sug)

        conf_rows = "".join(
            f"<tr><td>{doclink(doc)}</td><td class='rel'>{html.escape(rel or '')}</td>"
            f"<td>{html.escape(wt or '')}</td>"
            f"<td><span class='prov prov-{PROV.get(prov,'weak')}'>{PROV.get(prov, prov or '?')}</span></td></tr>"
            for doc, rel, wt, prov, narr in cfm
        ) or "<tr><td colspan=4 class='warn'>No exhibits confirmed yet — gap.</td></tr>"

        sug_rows = "".join(
            f"<tr><td>{doclink(doc)}</td><td class='rel'>{html.escape(rel or '')}</td>"
            f"<td>{html.escape(wt or '')}</td><td>{('%.2f' % conf) if conf is not None else ''}</td>"
            f"<td class='muted'>{html.escape((rat or '')[:70])}</td></tr>"
            for doc, rel, wt, conf, rat in sug
        ) or "<tr><td colspan=5 class='muted'>No pending suggestions.</td></tr>"

        elem_html = "".join(f"<li>{html.escape(str(e))}</li>" for e in elems)
        cards.append(f"""
<div class="claim">
  <div class="chead"><span class="pill">{html.escape(kind or '')}</span>
    <span class="lbl">{html.escape(label or ('claim ' + str(cid)))}</span>
    <span class="muted">&middot; {html.escape(cf or '')} &middot; priority {prio}</span></div>
  <div class="ctext">{html.escape(text or '')}</div>
  <div class="req"><b>Must prove:</b><ul>{elem_html or '<li class=muted>&mdash;</li>'}</ul></div>
  <div class="grid">
   <div class="col"><div class="ch ch-conf">CONFIRMED &mdash; filed / accepted ({len(cfm)})</div>
     <table><thead><tr><th>Exhibit</th><th>Role</th><th>Weight</th><th>Proof</th></tr></thead>
     <tbody>{conf_rows}</tbody></table></div>
   <div class="col"><div class="ch ch-sugg">SUGGESTED &mdash; review &amp; accept ({len(sug)})</div>
     <table><thead><tr><th>Exhibit</th><th>Role</th><th>Weight</th><th>Conf</th><th>Why</th></tr></thead>
     <tbody>{sug_rows}</tbody></table></div>
  </div>
</div>""")

    scope = html.escape(case_file) if case_file else "all matters"
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Evidence Matrix &mdash; {scope}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;background:#f4f5f7;color:#1a1a1a}}
 h1{{font-size:19px;margin:0 0 3px}} .sub{{color:#666;font-size:13px;margin-bottom:16px}}
 .claim{{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.12);padding:14px;margin-bottom:16px}}
 .chead{{font-size:15px;margin-bottom:6px}} .lbl{{font-weight:700}}
 .ctext{{font-size:13px;color:#333;margin-bottom:8px}}
 .req{{font-size:12px;color:#444;margin-bottom:10px}} .req ul{{margin:3px 0 0 18px;padding:0}}
 .grid{{display:flex;gap:14px;flex-wrap:wrap}} .col{{flex:1;min-width:280px}}
 .ch{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;padding:5px 8px;border-radius:5px 5px 0 0}}
 .ch-conf{{background:#e7f5ec;color:#11703a}} .ch-sugg{{background:#fff4e5;color:#9a5b00}}
 table{{border-collapse:collapse;width:100%;background:#fff}}
 th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid #eee;font-size:12px;vertical-align:top}}
 th{{background:#fafafa;font-size:10px;text-transform:uppercase;color:#666}}
 a{{color:#0a58ca;text-decoration:none}} a:hover{{text-decoration:underline}}
 .muted{{color:#999;font-size:11px}} .warn{{color:#b54708}} .rel{{text-transform:capitalize}}
 .pill{{font-size:10px;padding:2px 6px;border-radius:10px;background:#eef;color:#334;margin-right:6px;text-transform:uppercase}}
 .prov{{font-size:10px;padding:1px 6px;border-radius:8px}}
 .prov-verified{{background:#d6f0df;color:#11703a}} .prov-inferred{{background:#fde9c8;color:#9a5b00}} .prov-weak{{background:#f3d6d6;color:#a11}}
</style></head><body>
<h1>Evidence Matrix &mdash; {scope}</h1>
<div class="sub">{len(claims)} claims &middot; {n_conf} confirmed exhibits &middot; {n_sugg} suggested (pending review) &middot; live view</div>
{''.join(cards) or '<div class=claim>No claims defined for this matter yet.</div>'}
</body></html>"""
    return Response(page, mimetype="text/html")


# ─── Annex Assembler ─────────────────────────────────────────────────────────
import sys as _sys
_sys.path.insert(0, os.path.dirname(__file__))


def _doc_bytes(doc_id):
    """(bytes, mime, name) for a doc from local file_path or Drive."""
    conn = _db()
    cur = conn.cursor()
    cur.execute("SELECT file_path, drive_file_id, mime_type, "
                "COALESCE(NULLIF(smart_filename,''), original_filename) "
                "FROM documents WHERE id=%s", (doc_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None, None, f"doc {doc_id}"
    fp, drive_id, mime, name = row
    name = name or f"doc-{doc_id}"
    if fp and os.path.exists(fp):
        with open(fp, "rb") as fh:
            return fh.read(), (mime or "application/pdf"), name
    if drive_id:
        from googleapiclient.http import MediaIoBaseDownload
        svc = _drive()
        buf = io.BytesIO()
        req = svc.files().get_media(fileId=drive_id, supportsAllDrives=True)
        dl = MediaIoBaseDownload(buf, req, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = dl.next_chunk()
        buf.seek(0)
        return buf.read(), (mime or "application/pdf"), name
    return None, None, name


def _matter_annex_items(case_file):
    """Ordered CONFIRMED exhibits for a case_file -> annex items A,B,C...
    Ordered by claim priority desc, then weight (primary>strong>moderate)."""
    conn = _db()
    cur = conn.cursor()
    cur.execute("""
        SELECT et.supporting_doc_id, c.short_label, et.weight, et.relation_kind,
               COALESCE(NULLIF(d.smart_filename,''), d.original_filename)
          FROM evidence_trail et
          JOIN claims c ON c.id = et.claim_id
          JOIN documents d ON d.id = et.supporting_doc_id
         WHERE c.case_file = %s
         ORDER BY c.priority DESC NULLS LAST,
                  CASE et.weight WHEN 'primary' THEN 0 WHEN 'strong' THEN 1
                                 WHEN 'moderate' THEN 2 ELSE 3 END,
                  et.supporting_doc_id
    """, (case_file,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    items, seen = [], set()
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for doc_id, label, weight, rel, name in rows:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        i = len(items)
        tag = letters[i] if i < 26 else f"A{i - 25}"
        items.append({"label": tag, "doc_id": doc_id,
                      "desc": f"{name or ('doc ' + str(doc_id))} — {rel} ({label})"})
    return items


@bp.route("/annex/m/<case_file>")
def annex_bundle(case_file):
    import html
    items = _matter_annex_items(case_file)
    rows = "".join(
        f"<tr><td class='loc'>Annex {it['label']}</td>"
        f"<td><a href='/files/c/{it['doc_id']}'>{html.escape(it['desc'][:84])}</a> "
        f"<span class='muted'>#{it['doc_id']}</span></td></tr>"
        for it in items
    ) or "<tr><td colspan=2>No confirmed exhibits for this matter yet.</td></tr>"
    title = html.escape(case_file)
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Annex bundle &mdash; {title}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px;background:#f4f5f7;color:#1a1a1a}}
 h1{{font-size:18px;margin:0 0 4px}} .sub{{color:#666;font-size:13px;margin-bottom:14px}}
 .btn{{display:inline-block;background:#0a58ca;color:#fff;padding:10px 16px;border-radius:6px;text-decoration:none;font-size:14px;margin-bottom:16px}}
 table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
 th,td{{text-align:left;padding:9px 10px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}}
 td.loc{{font-weight:600;white-space:nowrap}} a{{color:#0a58ca;text-decoration:none}}
 .muted{{color:#999;font-size:11px}}
</style></head><body>
<h1>Annex bundle &mdash; {title}</h1>
<div class="sub">{len(items)} confirmed exhibits, in filing order (priority &rarr; weight).</div>
<a class="btn" href="/files/c/annex/m/{title}/pdf">&#11015; Assemble all into one ordered PDF (with annex separators)</a>
<table><tbody>{rows}</tbody></table>
</body></html>"""
    return Response(page, mimetype="text/html")


@bp.route("/annex/m/<case_file>/pdf")
def annex_pdf(case_file):
    import annex_assembler
    items = _matter_annex_items(case_file)
    if not items:
        return Response("no confirmed exhibits for this matter", status=404,
                        mimetype="text/plain")
    pdf, manifest = annex_assembler.assemble(
        items, _doc_bytes, title=f"{case_file} annexes", draft=True)
    return Response(
        pdf, mimetype="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{case_file}_annexes_DRAFT.pdf"',
                 "X-Annex-Count": str(len(items))},
    )
