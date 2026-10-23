"""Drip Interface MVP — chat + files + drafts. Tailscale-only. NEVER sends outward."""
import os, json, hashlib, mimetypes, subprocess, zipfile, re, datetime, html
import psycopg2, psycopg2.extras, requests
from flask import Flask, request, jsonify, send_file, abort, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.environ.get("DRIP_INBOX", "/root/landtek/drip_inbox")
MODEL = os.environ.get("DRIP_UI_MODEL", "llama-3.3-70b-versatile")
sys_path_added = __import__("sys").path.insert(0, "/root/landtek/scripts")
SPA_GENERAL = "/root/landtek/files/MWK-001/2025/general/original/SPA-001_Apostilled_SPA_Patricia_to_Jonathan_exec2025-02-12_apostille61887.pdf"
LIVE_CLOCK = ("served_running", "replied_not_performed", "partial", "lapsed", "consequence_staged")
app = Flask(__name__)


def dict_cursor():
    c = db(); return c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def client_of(ladder):
    return "Paracale-001" if (ladder or "").startswith("PAR-") else ("NIBDC-001" if (ladder or "").startswith("NIBDC") else "MWK-001")


def run_gate(body, to_addr, ladder):
    """scripts/drip_gate.py — Charter, posture (X17), Br.41 hold, cadence, tone, follows-not-positions."""
    import drip_gate
    c, cur = dict_cursor()
    try:
        return drip_gate.gate(cur, body, to_addr=to_addr, client=client_of(ladder))
    except Exception as e:  # the gate must never crash the UI; an unchecked draft is marked so
        return {"mark": "⚠", "lines": [["GATE", "⚠", f"gate error: {e}"]]}
    finally:
        c.close()


def next_targets(limit=7):
    import drip_board
    c, cur = dict_cursor()
    try:
        rows, off = drip_board.build(cur, datetime.date.today())
        return drip_board.pick_targets(rows, datetime.date.today(), off, top=limit)
    except Exception as e:
        return [{"score": 0, "ladder": "(error)", "matter": "", "what": f"board error: {e}", "channel": ""}]
    finally:
        c.close()
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

def db():
    c = psycopg2.connect(""); c.autocommit = True; return c

def q(sql, args=(), one=False):
    c = db()
    try:
        cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor); cur.execute(sql, args)
        rows = cur.fetchall() if cur.description else []
        return (rows[0] if rows else None) if one else rows
    finally: c.close()

def extract(path, mime):
    try:
        if path.lower().endswith(".pdf"):
            return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60).stdout[:200000]
        if path.lower().endswith(".docx"):
            x = zipfile.ZipFile(path).read("word/document.xml").decode("utf8", "ignore")
            x = re.sub(r"</w:p>", "\n", x); return html.unescape(re.sub(r"<[^>]+>", "", x))[:200000]
        if (mime or "").startswith("text/") or path.lower().endswith((".md", ".txt", ".csv", ".json", ".eml")):
            return open(path, errors="ignore").read()[:200000]
    except Exception as e:
        return f"[extract failed: {e}]"
    return None

@app.route("/")
def index(): return send_from_directory(HERE, "index.html")
@app.route("/orb.html")
def orb(): return send_from_directory(HERE, "orb.html")
@app.route("/health")
def health(): return jsonify(ok=True, model=MODEL)

@app.route("/api/upload", methods=["POST"])
def upload():
    out = []
    day = os.path.join(INBOX, datetime.date.today().isoformat()); os.makedirs(day, exist_ok=True)
    for f in request.files.getlist("files"):
        name = re.sub(r"[^\w.\- ()]", "_", f.filename or "pasted")[:150] or "file"
        path = os.path.join(day, datetime.datetime.now().strftime("%H%M%S_") + name)
        f.save(path)
        data = open(path, "rb").read(); mime = f.mimetype or mimetypes.guess_type(name)[0]
        txt = extract(path, mime)
        r = q("INSERT INTO drip_ui_upload(filename,path,mime,size_bytes,sha256,extracted_text) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,filename,mime,size_bytes,created_at",
              (name, path, mime, len(data), hashlib.sha256(data).hexdigest(), txt), one=True)
        r["has_text"] = bool(txt); out.append(r)
    return jsonify(files=out)

@app.route("/api/files")
def files():
    src = request.args.get("src", "uploads"); kw = request.args.get("q", "").strip()
    if src == "uploads":
        rows = q("SELECT id,filename,mime,size_bytes,created_at FROM drip_ui_upload WHERE filename ILIKE %s ORDER BY id DESC LIMIT 200", (f"%{kw}%",))
    else:
        rows = q("""SELECT id, COALESCE(document_title,smart_filename,original_filename) AS filename, mime_type AS mime, matter_code,
                    COALESCE(doc_date,document_date) AS date, drive_link FROM documents
                    WHERE %s='' OR document_title ILIKE %s OR smart_filename ILIKE %s OR extracted_text ILIKE %s
                    ORDER BY id DESC LIMIT 100""", (kw, f"%{kw}%", f"%{kw}%", f"%{kw}%"))
    return jsonify(files=rows)

@app.route("/api/raw/upload/<int:i>")
def raw_upload(i):
    r = q("SELECT path,mime,filename FROM drip_ui_upload WHERE id=%s", (i,), one=True)
    if not r or not r["path"].startswith(INBOX): abort(404)
    return send_file(r["path"], mimetype=r["mime"], download_name=r["filename"])

@app.route("/api/doc/<int:i>")
def doc(i):
    r = q("""SELECT id, COALESCE(document_title,smart_filename) AS title, matter_code, COALESCE(doc_date,document_date) AS date,
             summary, drive_link, LEFT(extracted_text,20000) AS text FROM documents WHERE id=%s""", (i,), one=True)
    return jsonify(r or {})

@app.route("/api/upload_text/<int:i>")
def upload_text(i):
    return jsonify(q("SELECT id,filename,LEFT(extracted_text,20000) AS text FROM drip_ui_upload WHERE id=%s", (i,), one=True) or {})

@app.route("/api/history")
def history():
    rows = q("SELECT id,role,content,upload_ids,meta,created_at FROM drip_ui_message ORDER BY id DESC LIMIT 30")[::-1]
    ids = [d for r in rows for d in ((r["meta"] or {}).get("drafts") or [])]
    drafts = {d["id"]: d for d in q("SELECT * FROM drip_ui_draft WHERE id = ANY(%s)", (ids or [0],))}
    for r in rows: r["drafts"] = [drafts[i] for i in ((r["meta"] or {}).get("drafts") or []) if i in drafts]
    return jsonify(messages=json.loads(json.dumps(rows, default=str)))

@app.route("/api/queue")
def queue():
    # The drip core (23 Oct 2026): live clocks + every ladder's status + the ranked next targets.
    obl = q("""SELECT id,matter_code,ladder,officer,office,obligation,served_at,due_at,state,service_proof_doc_id
                 FROM office_obligation WHERE ladder IS NOT NULL AND state = ANY(%s) ORDER BY due_at NULLS LAST""", (list(LIVE_CLOCK),))
    lad = q("SELECT * FROM drip_ladder_status ORDER BY due_at NULLS LAST, last_sent DESC NULLS LAST LIMIT 120")
    ev = q("SELECT id,kind,ladder,event_date,detail,created_at FROM drip_event_v ORDER BY id DESC LIMIT 15")
    dr = q("SELECT * FROM drip_ui_draft ORDER BY id DESC LIMIT 50")
    return jsonify(targets=next_targets(), obligations=obl, ladders=lad, events=ev, drafts=dr)

@app.route("/api/draft/<int:i>/decide", methods=["POST"])
def decide(i):
    b = request.get_json(force=True); d = b.get("decision")
    if d not in ("go", "edit", "hold"): abort(400)
    cur_d = q("SELECT * FROM drip_ui_draft WHERE id=%s", (i,), one=True)
    if not cur_d: abort(404)
    body = b.get("body") or cur_d["body"]
    ladder = (b.get("ladder") or cur_d.get("ladder") or "").strip() or None
    note = b.get("note") or ""
    staged = None
    if d == "go":
        # Go = gate again on the final text, then stage it in Gmail DRAFTS (never sends) and log it in the drip.
        g = run_gate(body, cur_d["to_addr"], ladder)
        q("UPDATE drip_ui_draft SET gate=%s, body=%s, ladder=%s WHERE id=%s", (json.dumps(g), body, ladder, i))
        if not ladder:
            return jsonify(error="Assign a ladder before Go (every drip belongs to a ladder).", gate=g), 400
        if not cur_d["to_addr"]:
            return jsonify(error="No recipient (to) on this draft.", gate=g), 400
        if g["mark"] == "⛔" and "override" not in note.lower():
            return jsonify(error="Blocked by the gate. Fix the ⛔ items, or Go with a note containing 'override'.", gate=g), 409
        import drip_stage_gmail
        atts = [SPA_GENERAL] if re.search(r'(?i)annex\s*"?a"?|special power of attorney (is )?attached', body) else []
        try:
            staged = drip_stage_gmail.stage_draft(cur_d["to_addr"], cur_d["subject"], body, cc=cur_d["cc"], attachments=atts)
        except Exception as e:
            return jsonify(error=f"Gmail draft failed: {e}", gate=g), 502
        import drip_log
        c2, cur2 = drip_log.conn()
        try:
            drip_log.ensure_ladder(cur2, ladder, drip_log.matter_for(cur2, ladder), cur_d["to_addr"], cur_d["subject"])
            drip_log.event(cur2, "drafted", ladder=ladder, at=str(datetime.date.today()), where="jonzschoche Gmail Drafts",
                           subject=cur_d["subject"], to=cur_d["to_addr"], gmail_draft_id=staged, ui_draft_id=i, source="drip_ui")
            drip_log.set_step(cur2, ladder, "drafted")
            c2.commit()
        finally:
            c2.close()
    sets, args = ["state=%s", "decided_at=now()", "decision_note=%s"], [d, note or None]
    if d in ("edit", "go") and b.get("body"): sets.append("body=%s"); args.append(b["body"])
    if ladder: sets.append("ladder=%s"); args.append(ladder)
    if staged: sets += ["gmail_draft_id=%s", "account=%s", "staged_at=now()"]; args += [staged, "jonzschoche@gmail.com"]
    r = q(f"UPDATE drip_ui_draft SET {','.join(sets)} WHERE id=%s RETURNING *", (*args, i), one=True)
    q("INSERT INTO drip_event(kind,obligation_id,detail) VALUES('ui_decision',%s,%s)",
      (r["obligation_id"], json.dumps({"source": "drip_ui", "draft_id": i, "decision": d, "note": note, "ladder": ladder,
                                       "gmail_draft_id": staged})))
    return jsonify(draft=r, staged=staged)

# ---------- actions on everything (Jonathan, 23 Oct 2026: "anything that's on a page should have options") ----------
def _dl():
    import drip_log
    return drip_log


@app.route("/api/ladder/<path:name>")
def ladder_detail(name):
    ev = q("SELECT id,kind,event_date,detail,created_at FROM drip_event_v WHERE ladder=%s ORDER BY id DESC LIMIT 60", (name,))
    clock = q("SELECT * FROM office_obligation WHERE ladder=%s ORDER BY id DESC", (name,))
    steps = q("SELECT seq,state,addressee,the_ask,to_address FROM step_plan WHERE ladder=%s ORDER BY seq", (name,))
    drafts = q("SELECT id,state,subject,gmail_draft_id FROM drip_ui_draft WHERE ladder=%s ORDER BY id DESC", (name,))
    return jsonify(ladder=name, events=ev, clocks=clock, steps=steps, drafts=drafts)


@app.route("/api/ladder/<path:name>/log", methods=["POST"])
def ladder_log(name):
    """Log anything on a ladder from the page: reply · receipt (proof doc) · call · note · refused · performed.
    Everything goes through scripts/drip_log.py, so the board, clocks and UI stay one truth. Never sends."""
    b = request.get_json(force=True); act = b.get("action"); dl = _dl(); today = str(datetime.date.today())
    at = b.get("at") or today
    c, cur = dl.conn()
    try:
        m = dl.matter_for(cur, name)
        dl.ensure_ladder(cur, name, m)
        if act == "reply":
            ns = argparse_ns(ladder=name, at=at, frm=b.get("from") or "(office)", gist=b.get("note") or "reply",
                             doc=b.get("doc") or None, outcome=b.get("outcome") or "ack", next=None, matter=None, office=None,
                             note=None, source="drip_ui")
            msg = dl.cmd_reply(cur, ns)
        elif act == "receipt":
            if not b.get("doc"):
                return jsonify(error="A receipt needs the corpus document that proves it (doc #)."), 400
            msg = dl.cmd_receipt(cur, argparse_ns(ladder=name, at=at, proof_doc=int(b["doc"]), by=b.get("by"), office=b.get("office"),
                                                  matter=None, note=b.get("note"), source="drip_ui"))
        elif act == "performed":
            cur.execute("UPDATE office_obligation SET state='performed', updated_at=now() WHERE ladder=%s AND state=ANY(%s) RETURNING id",
                        (name, list(LIVE_CLOCK)))
            n = len(cur.fetchall()); dl.set_step(cur, name, "done")
            dl.event(cur, "state_change", ladder=name, at=at, to="performed", note=b.get("note"), source="drip_ui")
            msg = f"{n} clock(s) closed as performed"
        elif act in ("call", "note", "refused"):
            kind = {"call": "field", "note": "field", "refused": "field"}[act]
            dl.event(cur, kind, ladder=name, at=at, channel="phone" if act == "call" else None,
                     outcome="REFUSED_TO_RECEIVE" if act == "refused" else None, note=b.get("note"), source="drip_ui")
            msg = f"{act} logged"
        else:
            return jsonify(error="unknown action"), 400
        c.commit()
        return jsonify(ok=True, message=msg)
    except SystemExit as e:
        c.rollback(); return jsonify(error=str(e)), 400
    finally:
        c.close()


def argparse_ns(**kw):
    import argparse
    return argparse.Namespace(**kw)


@app.route("/api/search")
def search():
    """Dig into a matter (Jonathan, 23 Oct 2026): one query over matters, ladders, clocks, prospects, drip events,
    documents and e-mails. A matter code (e.g. MWK-CV6839) filters everything to that matter."""
    qq = (request.args.get("q") or "").strip()
    if len(qq) < 2:
        return jsonify(error="type at least 2 characters"), 400
    like = f"%{qq}%"
    is_matter = bool(re.match(r"(?i)^(MWK|PAR|NIBDC)-[A-Z0-9-]+$", qq))
    out = {"query": qq, "matter_mode": is_matter}
    out["matters"] = q("""SELECT matter_code,title,status,current_stage,next_event,lead_counsel FROM matters
                          WHERE matter_code ILIKE %s OR title ILIKE %s ORDER BY matter_code LIMIT 15""", (like, like))
    out["ladders"] = q("""SELECT DISTINCT ON (s.ladder) s.ladder, s.matter_code, s.state, s.addressee, l.clock_state, l.due_at, l.last_sent
                          FROM step_plan s LEFT JOIN drip_ladder_status l ON l.ladder=s.ladder
                          WHERE s.ladder ILIKE %s OR s.matter_code ILIKE %s OR s.addressee ILIKE %s OR s.the_ask ILIKE %s
                          ORDER BY s.ladder LIMIT 40""", (like, like, like, like))
    out["clocks"] = q("""SELECT ladder,office,state,served_at,due_at,matter_code FROM office_obligation
                         WHERE ladder IS NOT NULL AND (ladder ILIKE %s OR office ILIKE %s OR matter_code ILIKE %s)
                         ORDER BY due_at NULLS LAST LIMIT 30""", (like, like, like))
    out["prospects"] = q("""SELECT id,matter_code,kind,title,lane,score,source_ref FROM drip_prospect
                            WHERE status='new' AND (title ILIKE %s OR detail ILIKE %s OR matter_code ILIKE %s OR office ILIKE %s)
                            ORDER BY score DESC LIMIT 40""", (like, like, like, like))
    out["events"] = q("""SELECT id,kind,ladder,event_date,left(detail::text,220) AS detail FROM drip_event_v
                         WHERE detail::text ILIKE %s OR ladder ILIKE %s ORDER BY id DESC LIMIT 25""", (like, like))
    if is_matter:
        out["documents"] = q("""SELECT id, coalesce(document_title,smart_filename,original_filename) AS title, matter_code,
                                coalesce(doc_date,document_date) AS date FROM documents WHERE matter_code ILIKE %s OR case_file ILIKE %s
                                ORDER BY coalesce(doc_date_norm, created_at::date) DESC NULLS LAST LIMIT 40""", (qq, qq))
    else:
        out["documents"] = q("""SELECT id, coalesce(document_title,smart_filename,original_filename) AS title, matter_code,
                                coalesce(doc_date,document_date) AS date FROM documents
                                WHERE coalesce(document_title,smart_filename,original_filename,'') ILIKE %s OR extracted_text ILIKE %s
                                ORDER BY (coalesce(document_title,'') ILIKE %s) DESC, coalesce(doc_date_norm, created_at::date) DESC NULLS LAST
                                LIMIT 40""", (like, like, like))
    out["emails"] = q("""SELECT id, from_addr, subject, received_at FROM gmail_messages
                         WHERE subject ILIKE %s OR from_addr ILIKE %s OR (%s AND case_file ILIKE %s)
                         ORDER BY received_at DESC LIMIT 20""", (like, like, is_matter, qq.split('-')[0] + '%'))
    return jsonify(json.loads(json.dumps(out, default=str)))


@app.route("/api/prospects")
def prospects():
    lane = request.args.get("lane"); kw = request.args.get("q", "")
    where, args = ["status='new'"], []
    if lane: where.append("lane=%s"); args.append(lane)
    if kw: where.append("(title ILIKE %s OR detail ILIKE %s)"); args += [f"%{kw}%", f"%{kw}%"]
    rows = q(f"SELECT id,matter_code,kind,title,lane,score,source_ref,office FROM drip_prospect WHERE {' AND '.join(where)} ORDER BY score DESC, id LIMIT 150", tuple(args))
    counts = q("SELECT lane, count(*) n FROM drip_prospect WHERE status='new' GROUP BY lane")
    return jsonify(prospects=rows, counts={r["lane"]: r["n"] for r in counts})


@app.route("/api/prospect/<int:i>")
def prospect_detail(i):
    p = q("SELECT * FROM drip_prospect WHERE id=%s", (i,), one=True)
    if not p: abort(404)
    src_text = None
    m = re.match(r"(.+\.md):(\d+)$", p["source_ref"] or "")
    if m:   # a desk file: show the lines around the item
        path = os.path.join("/root/landtek", m.group(1)); ln = int(m.group(2))
        if os.path.isfile(path):
            lines = open(path, errors="ignore").read().splitlines()
            src_text = "\n".join(f"{n + 1:>4}  {l}" for n, l in enumerate(lines) if ln - 8 <= n + 1 <= ln + 8)
    return jsonify(json.loads(json.dumps({"prospect": p, "source_text": src_text}, default=str)))


@app.route("/api/prospect/<int:i>/action", methods=["POST"])
def prospect_action(i):
    """promote → a planned ladder · dismiss · lane change. Promotion is Jonathan's call; nothing is sent."""
    b = request.get_json(force=True); act = b.get("action")
    p = q("SELECT * FROM drip_prospect WHERE id=%s", (i,), one=True)
    if not p: abort(404)
    if act == "dismiss":
        q("UPDATE drip_prospect SET status='dismissed', decided_at=now(), decision_note=%s WHERE id=%s", (b.get("note"), i))
        return jsonify(ok=True, message="dismissed")
    if act == "lane":
        if b.get("lane") not in ("drip", "legal_desk", "counsel", "hold"): abort(400)
        q("UPDATE drip_prospect SET lane=%s, decision_note=%s WHERE id=%s", (b["lane"], b.get("note"), i))
        return jsonify(ok=True, message=f"moved to {b['lane']}")
    if act == "promote":
        if p["lane"] != "drip":
            return jsonify(error=f"This prospect is in the {p['lane']} lane. The drip only carries drip-lane items; move it first if you decide so."), 400
        ladder = re.sub(r"[^A-Z0-9-]+", "-", (b.get("ladder") or f"PROSPECT-{i}").upper()).strip("-")
        dl = _dl(); c, cur = dl.conn()
        try:
            dl.ensure_ladder(cur, ladder, p["matter_code"] or "MWK-001", p["office"], p["title"][:300])
            cur.execute("UPDATE step_plan SET state='planned', notes=coalesce(notes,'')||%s WHERE ladder=%s AND seq=1",
                        (f" | from prospect #{i}: {p['source_ref']}", ladder))
            dl.event(cur, "planned", ladder=ladder, at=str(datetime.date.today()), prospect_id=i, title=p["title"][:200], source="drip_ui")
            c.commit()
        finally:
            c.close()
        q("UPDATE drip_prospect SET status='promoted', ladder=%s, decided_at=now(), decision_note=%s WHERE id=%s", (ladder, b.get("note"), i))
        return jsonify(ok=True, message=f"promoted to ladder {ladder} (planned)", ladder=ladder)
    abort(400)

# ---------- bot ----------
SYSTEM = """You are Drip Bot, LandTek's drip assistant for Jonathan (Boss). Reply in short Taglish (mostly English, light Tagalog).
Rules: you NEVER send anything outward — you have no send tool. You can only create DRAFTS with create_draft; Jonathan decides Go/Edit/Hold. Go puts the letter in his Gmail Drafts; Jonathan sends it himself.
Drips are calm, routine, one ask, no accusations, no blanks or [TO FILL] placeholders. Lawyers only sign/file/appear.
Drip Charter (adopted 20 Oct 2026), always:
- Write for Patricia Keesey Zschoche, a co-owner, through her attorney-in-fact; sign "Jonathan Paul Zschoche, Attorney-in-Fact for Patricia Keesey Zschoche, a co-owner". Never speak for "the heirs".
- The drip FOLLOWS decided positions: records requests, acknowledgments, tracers, status asks. Never a new legal position, demand, threat, statute fight or forum name.
- Never write to a respondent in our live cases (X17) or to a represented party; never to RTC Branch 41 while SP 2680 is pending.
- One touch per office per 21 days unless it replied; history before every ask: never re-ask what was answered or refused.
- Every draft names its ladder (from list_drip_queue). Every draft passes the gate; if the gate shows ⛔, fix it before presenting.
- Reply in the office's thread from jonzschoche@gmail.com; the 2025 general SPA (Annex "A") is the default annex.
Always ground facts in tools: use search_corpus / get_document / read_upload / list_drip_queue, and cite sources as [doc #id] or [upload #id]. Quote the document's own words for conclusions; never state the opposite of what the text says. If you can't find it, say so."""
TOOLS = [
 {"type":"function","function":{"name":"search_corpus","description":"Keyword search over the LandTek document corpus (2k+ docs). Returns ids, titles and snippets.","parameters":{"type":"object","properties":{"keywords":{"type":"string","description":"2-6 distinctive keywords; results ranked by how many match"},"matter_code":{"type":"string"}},"required":["keywords"]}}},
 {"type":"function","function":{"name":"get_document","description":"Read a corpus document by id. Pass focus (a word/phrase) to get the passage around it.","parameters":{"type":"object","properties":{"id":{"type":"integer"},"focus":{"type":"string"}},"required":["id"]}}},
 {"type":"function","function":{"name":"read_upload","description":"Read the extracted text of a file Jonathan uploaded in this chat.","parameters":{"type":"object","properties":{"id":{"type":"integer"}},"required":["id"]}}},
 {"type":"function","function":{"name":"list_drip_queue","description":"The drip's ranked next targets across all matters, the live 15-working-day clocks, and pending drafts. Start here.","parameters":{"type":"object","properties":{}}}},
 {"type":"function","function":{"name":"create_draft","description":"Stage a drip DRAFT for Jonathan's Go/Edit/Hold. Does not send.","parameters":{"type":"object","properties":{"to_addr":{"type":["string","null"]},"cc":{"type":["string","null"]},"subject":{"type":"string"},"body":{"type":"string"},"obligation_id":{"type":["integer","null"]},"rationale":{"type":["string","null"]},"ladder":{"type":"string","description":"the drip ladder this belongs to, e.g. RD-T52540-ENTRIES (see list_drip_queue)"}},"required":["subject","body","ladder"]}}},
]

def snippet(t, kws):
    t = t or ""; lo = t.lower()
    hits = [lo.find(k.lower()) for k in sorted(kws, key=len, reverse=True) if lo.find(k.lower()) >= 0]
    p = max(0, (hits[0] if hits else 0) - 150); return re.sub(r"\s+", " ", t[p:p + 450])

def call_tool(name, a, cards):
    if name == "search_corpus":
        kws = [k for k in re.split(r"\s+", a.get("keywords", "")) if len(k) > 2][:6]
        if not kws: return {"results": []}
        score = " + ".join(["(CASE WHEN extracted_text ILIKE %s OR document_title ILIKE %s THEN 1 ELSE 0 END)"] * len(kws))
        args = [x for k in kws for x in (f"%{k}%",) * 2]
        mc = ""
        if a.get("matter_code"): mc = " AND matter_code=%s"
        need = min(len(kws), max(2, len(kws) - 2))
        rows = q(f"""SELECT * FROM (SELECT id, COALESCE(document_title,smart_filename,original_filename) AS title, matter_code, COALESCE(doc_date,document_date) AS date,
                     extracted_text, ({score}) AS score, doc_date_norm, created_at FROM documents WHERE extracted_text IS NOT NULL{mc}) z
                     WHERE score >= %s ORDER BY score DESC, COALESCE(doc_date_norm, created_at::date) DESC NULLS LAST LIMIT 5""",
                 args + ([a["matter_code"]] if mc else []) + [need])
        up = q(f"SELECT id, filename, extracted_text FROM drip_ui_upload WHERE " + " AND ".join(["extracted_text ILIKE %s"] * len(kws)) + " ORDER BY id DESC LIMIT 3", [f"%{k}%" for k in kws])
        return {"results": [{"doc_id": r["id"], "title": r["title"], "matter": r["matter_code"], "date": r["date"], "snippet": snippet(r["extracted_text"], kws)} for r in rows],
                "uploads": [{"upload_id": r["id"], "filename": r["filename"], "snippet": snippet(r["extracted_text"], kws)} for r in up]}
    if name == "get_document":
        r = q("SELECT id, COALESCE(document_title,smart_filename,original_filename) AS title, matter_code, COALESCE(doc_date,document_date) AS date, extracted_text AS text FROM documents WHERE id=%s", (a["id"],), one=True)
        if not r: return {"error": "not found"}
        t = r["text"] or ""; f = (a.get("focus") or "").lower(); p = t.lower().find(f) if f else -1
        st = max(0, p - 300) if p >= 0 else 0
        r["text"] = re.sub(r"\s+", " ", t[st:st + 2000]); return r
    if name == "read_upload":
        return q("SELECT id, filename, LEFT(extracted_text,1500) AS text, mime FROM drip_ui_upload WHERE id=%s", (a["id"],), one=True) or {"error": "not found"}
    if name == "list_drip_queue":
        d = queue().get_json()
        return {"next_targets": d["targets"],
                "live_clocks": [{k: o[k] for k in ("ladder", "office", "state", "served_at", "due_at")} for o in d["obligations"]],
                "pending_drafts": [{k: x.get(k) for k in ("id", "ladder", "to_addr", "subject", "state")} for x in d["drafts"] if x["state"] == "pending"][:10]}
    if name == "create_draft":
        g = run_gate(a["body"], a.get("to_addr"), a.get("ladder"))
        r = q("INSERT INTO drip_ui_draft(obligation_id,to_addr,cc,subject,body,rationale,ladder,gate) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
              (a.get("obligation_id"), a.get("to_addr"), a.get("cc"), a["subject"], a["body"], a.get("rationale"), a.get("ladder"), json.dumps(g)), one=True)
        cards.append(r)
        return {"draft_id": r["id"], "state": "pending", "gate": g,
                "note": "staged for Jonathan's Go/Edit/Hold; NOT sent. If the gate shows ⛔, revise the draft before he sees it."}
    return {"error": "unknown tool"}

@app.route("/api/chat", methods=["POST"])
def chat():
    b = request.get_json(force=True); msg = b.get("message", ""); ups = b.get("upload_ids") or []
    q("INSERT INTO drip_ui_message(role,content,upload_ids) VALUES('user',%s,%s)", (msg, ups))
    hist = q("SELECT role,content FROM drip_ui_message WHERE role IN ('user','assistant') ORDER BY id DESC LIMIT 6")[::-1]
    msgs = [{"role": "system", "content": SYSTEM}] + [{"role": h["role"], "content": h["content"] or ""} for h in hist]
    if ups:
        msgs[-1]["content"] += f"\n\n(Attached upload ids: {ups} — use read_upload.)"
    cards, used = [], []
    key = os.environ["GROQ_API_KEY"]
    step, waits, ans = 0, 0, None
    while step < 5 and waits < 10:
        final = step == 4
        payload = {"model": MODEL, "messages": msgs, "temperature": 0.2, "max_tokens": 1800, "reasoning_effort": "low"}
        payload["tools"] = TOOLS
        if final and not msgs[-1].get("_nudge"):
            msgs.append({"role": "system", "content": "Stop calling tools. Answer Jonathan now with what you have, citing [doc #id]/[upload #id].", "_nudge": 1})
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                          json={**payload, "messages": [{k: v for k, v in x.items() if k != "_nudge"} for x in msgs]}, timeout=90)
        if r.status_code == 429:
            import time; m_ = re.search(r"try again in ([\d.]+)s", r.text); time.sleep(min(float(m_.group(1)) + 1 if m_ else 15, 30)); waits += 1; continue
        if r.status_code == 400 and "tool_use_failed" in r.text and waits < 9:
            waits += 1; continue
        if r.status_code != 200: return jsonify(error=f"groq {r.status_code}: {r.text[:300]}"), 502
        step += 1
        m = r.json()["choices"][0]["message"]
        if not m.get("tool_calls"):
            ans = m.get("content") or ""; break
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": m["tool_calls"]})
        for tc in m["tool_calls"]:
            try: a = json.loads(tc["function"]["arguments"] or "{}")
            except Exception: a = {}
            used.append({"tool": tc["function"]["name"], "args": a})
            res = call_tool(tc["function"]["name"], a, cards)
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res, default=str)[:2500]})
    if ans is None and step >= 5:
        # Summarise-from-evidence pass with no tools (avoids endless tool calls).
        ev = "\n\n".join(x["content"][:1500] for x in msgs if x.get("role") == "tool")[-6000:]
        flat = [msgs[0], {"role": "user", "content": msg + "\n\nEVIDENCE FROM TOOLS (cite as [doc #id]/[upload #id]):\n" + ev}]
        for _ in range(6):
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"},
                              json={"model": MODEL, "messages": flat, "temperature": 0.2, "max_tokens": 1800, "reasoning_effort": "low"}, timeout=90)
            if r.status_code == 429:
                import time; m_ = re.search(r"try again in ([\d.]+)s", r.text); time.sleep(min(float(m_.group(1)) + 1 if m_ else 15, 30)); continue
            if r.status_code != 200: print("evidence pass", r.status_code, r.text[:300], flush=True)
            if r.status_code == 200: ans = r.json()["choices"][0]["message"].get("content") or None; used.append({"tool": "answer_from_evidence", "args": {}})
            break
    if ans is None:
        ans = "(Groq free tier is rate-limited right now — try again in a minute.)"
    q("INSERT INTO drip_ui_message(role,content,meta) VALUES('assistant',%s,%s)", (ans, json.dumps({"tools": used, "drafts": [c["id"] for c in cards]})))
    return jsonify(reply=ans, tools=used, drafts=json.loads(json.dumps(cards, default=str)))

if __name__ == "__main__":
    app.run(host=os.environ.get("DRIP_UI_HOST", "100.85.203.58"), port=int(os.environ.get("DRIP_UI_PORT", "8790")), threaded=True)
