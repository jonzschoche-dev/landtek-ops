"""Console Ask — pose ANY question to LandTek's own record (operator-only, internal).

Built 2026-10-03. Leo's client spine is deliberately narrow (exact lookups; refuses the rest), and
the Console's first probe showed every open question ("summarize the Balane case", "what should I
focus on this week?") collapsing to the same two title numbers. This is the operator's research
engine — two stages, $0, read-only:

  1. EXACT  — Leo's precise routes (title card, a matter's next date, document fetch, unknown-
              identifier refusal) run first, dry-run in an always-rolled-back transaction. A crisp
              hit is returned as-is.
  2. GROUNDED — otherwise: retrieve from the record in the chosen scope — verified/operator
              matter_facts (each with its quoted excerpt + source document), document passages
              (trigram-indexed extracted text), matter rows, title cards, and for planning questions
              the live §0 data (upcoming / overdue dates, stuck work orders, drip state) — then the
              local model (Mac Ollama, qwen2.5:14b) writes an answer that MUST cite every factual
              sentence as [n]. Nothing relevant retrieved → "not in the record", no model call.
              Every answer is then checked by Leo's own answer gate (leo_answer_gate.gate) and an
              uncited-sentence count, shown with the answer.

Client separation (A5): retrieval is always filtered to the scope's client(s); every source carries
its client; the model is told never to merge facts across clients. Jobs run in a background thread
and are polled (long answers never hit the 60 s proxy timeout). Mounted under /ops/ (basic-auth).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request

from ops_dashboard import PG_DSN

bp = Blueprint("console_ask", __name__, url_prefix="/ops/console/ask")

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.117.118.47:11434")
MODEL = os.environ.get("CONSOLE_ASK_MODEL", "qwen2.5:14b-instruct")

JOBS: dict = {}
FILES: dict = {}          # uploaded files: id → {name, status, text, …} — memory only, never the record
_LOCK = threading.Lock()
_JOB_TTL = 3600
_MAX_FILES = 30
_OCR_PAGES = 25           # cap on pages OCR'd per upload (tesseract, local, $0)
_FILE_EXT = (".pdf", ".docx", ".txt", ".md", ".csv", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")

# Leo routes whose output is a precise, trustworthy answer to return as-is.
_PRECISE_VIA = ("title_card", "title_history", "title_fetch", "unknown_identifier",
                "composer:deadlines:matter", "composer:title_inventory", "corpus_answer:")

_STOP = set("""a an the of to in on for and or but is are was were be been being do does did what whats
which who whom whose when where why how me my our we us you your i it its this that these those there here
about with from by as at into can could would should will shall may might must tell show give please
summarize summarise summary explain describe status update latest current any all some more most less
than then so if not no yes just also very know there their them they has have had get got need needs
case cases matter matters thing things stand stands record records says say said match matches compare
file attached uploaded upload document documents
focus week weeks today tomorrow next step steps plan planning urgent priority priorities prioritize agenda
todo to-do overdue due soon plate behind stuck slipping should""".split())
_PLAN_RE = re.compile(r"\b(focus|priorit\w*|this week|next week|today|tomorrow|next steps?|what should|"
                      r"urgent|agenda|to-?do|plan|overdue|due soon|on my plate|behind|stuck|slipp\w*)\b", re.I)
_REAL = ("matter_code NOT LIKE 'AUTO-%%' AND COALESCE(status,'') NOT IN ('closed','archived') "
         "AND client_code IS NOT NULL AND client_code NOT IN ('Archive','PENDING_TRIAGE')")


def _db():
    return psycopg2.connect(PG_DSN)


# ───────────────────────────── scopes ─────────────────────────────

def scopes(cur) -> list:
    """[{value, label, group}] — All clients, each client, each active matter (grouped by client)."""
    cur.execute("""SELECT m.client_code, COALESCE(c.name, m.client_code) AS cname,
                           m.matter_code, COALESCE(m.title, '') AS title
                      FROM matters m LEFT JOIN clients c ON c.client_code = m.client_code
                     WHERE m.matter_code NOT LIKE 'AUTO-%%' AND COALESCE(m.status,'') NOT IN ('closed','archived')
                       AND m.client_code IS NOT NULL AND m.client_code NOT IN ('Archive','PENDING_TRIAGE')
                     ORDER BY m.client_code, m.matter_code""")
    rows = cur.fetchall()
    out = [{"value": "all", "label": "All clients", "group": ""}]
    seen = set()
    for r in rows:
        if r["client_code"] not in seen:
            seen.add(r["client_code"])
            out.append({"value": f"client:{r['client_code']}",
                        "label": f"{r['cname']} ({r['client_code']})", "group": ""})
    for r in rows:
        t = r["title"][:60]
        out.append({"value": f"matter:{r['matter_code']}",
                    "label": f"{r['matter_code']}" + (f" — {t}" if t else ""), "group": r["client_code"]})
    return out


def _resolve_scope(cur, scope: str):
    """→ (clients, matters|None). Unknown scope → All clients."""
    cur.execute(f"SELECT DISTINCT client_code FROM matters WHERE {_REAL}")
    real = [r["client_code"] for r in cur.fetchall()]
    if scope.startswith("client:") and scope[7:] in real:
        return [scope[7:]], None
    if scope.startswith("matter:"):
        cur.execute(f"SELECT client_code FROM matters WHERE matter_code = %s AND {_REAL}", (scope[7:],))
        r = cur.fetchone()
        if r:
            return [r["client_code"]], [scope[7:]]
    return real, None


# ───────────────────────────── retrieval ─────────────────────────────

def _terms(q: str) -> list:
    phrases = [p.strip() for p in re.findall(r'"([^"]{3,60})"', q)]
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'\-]{2,}", q)
    keep = phrases + [w.strip(".'-") for w in words if w.lower().strip(".'-") not in _STOP]
    out = []
    for t in keep:
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:8]


def _window(text: str, terms: list, width: int = 700) -> str:
    """The passage of `text` with the densest cluster of term hits (never cut mid-word)."""
    if not text:
        return ""
    low = text.lower()
    hits = sorted(m.start() for t in terms for m in re.finditer(re.escape(t.lower()), low))
    if not hits:
        return re.sub(r"\s+", " ", text[:width]).strip()
    best, best_n = hits[0], 0
    for h in hits:
        n = sum(1 for x in hits if h <= x < h + width)
        if n > best_n:
            best, best_n = h, n
    start = max(0, best - width // 4)
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    seg = text[start:start + width]
    seg = seg.rsplit(" ", 1)[0] if len(text) > start + width else seg
    return ("…" if start > 0 else "") + re.sub(r"\s+", " ", seg).strip() + "…"


def _retrieve(cur, q: str, clients: list, matters, plan: bool) -> list:
    """Sources for the model, each {kind, label, client, matter, date, text, doc_id, prov}."""
    terms = _terms(q)
    pats = [f"%{t}%" for t in terms]
    src = []

    # 1) Matter rows — the scope's matters, or matters the question names.
    if matters:
        cur.execute("SELECT * FROM matters WHERE matter_code = ANY(%s)", (matters,))
    elif pats:
        cur.execute(f"""SELECT * FROM matters WHERE {_REAL} AND client_code = ANY(%s)
                          AND (title ILIKE ANY(%s) OR matter_code ILIKE ANY(%s)
                               OR next_event ILIKE ANY(%s) OR legal_theory ILIKE ANY(%s))
                        LIMIT 4""", (clients, pats, pats, pats, pats))
    else:
        cur.execute("SELECT * FROM matters WHERE false")
    for m in cur.fetchall():
        bits = [f"title: {m.get('title') or '—'}", f"stage: {m.get('current_stage') or '—'}",
                f"forum: {m.get('court_or_agency') or m.get('forum') or '—'}"]
        if m.get("lead_counsel"):
            bits.append(f"counsel: {m['lead_counsel']}")
        bits.append(f"next date: {m.get('next_deadline') or 'none set'}")
        if m.get("next_event"):
            bits.append(f"next event: {str(m['next_event'])[:380]}")
        if m.get("legal_theory"):
            bits.append(f"theory: {str(m['legal_theory'])[:450]}")
        src.append({"kind": "matter", "label": f"Matter {m['matter_code']}", "client": m["client_code"],
                    "matter": m["matter_code"], "date": None, "text": " · ".join(bits),
                    "doc_id": None, "prov": "operator"})

    # 2) Title cards — identifiers named in the question, or registrant names matched.
    ids = re.findall(r"(?<![0-9A-Za-z-])(?:T-)?([0-9]{3}-[0-9]{10}|[0-9]{4,6})(?![0-9])", q)
    if ids or pats:
        keys = [i for i in ids] + [f"T-{i}" for i in ids]
        cur.execute("""SELECT display_no, headline, client_code FROM title_brief
                        WHERE client_code = ANY(%s)
                          AND (upper(title_key) = ANY(%s) OR upper(display_no) = ANY(%s)
                               OR (%s AND registrant_name ILIKE ANY(%s)))
                        ORDER BY n_source_docs DESC NULLS LAST LIMIT 3""",
                    (clients, keys or ["-"], keys or ["-"], bool(pats), pats or ["-"]))
        for t in cur.fetchall():
            src.append({"kind": "title", "label": f"Title card {t['display_no']}", "client": t["client_code"],
                        "matter": None, "date": None, "text": t["headline"], "doc_id": None, "prov": "operator"})

    # 3) Verified / operator facts — each carries its quoted excerpt + source document.
    if pats:
        mclause = "AND f.matter_code = ANY(%s)" if matters else ""
        params = [clients] + ([matters] if matters else []) + [pats, pats]
        cur.execute(f"""SELECT f.id, f.matter_code, m.client_code, f.statement, f.excerpt, f.provenance_level,
                               f.source_kind, f.source_id, f.as_of
                          FROM matter_facts f JOIN matters m ON m.matter_code = f.matter_code
                         WHERE m.client_code = ANY(%s) {mclause}
                           AND f.provenance_level IN ('verified','operator')
                           AND (f.statement ILIKE ANY(%s) OR f.excerpt ILIKE ANY(%s))
                         ORDER BY (f.provenance_level = 'verified') DESC, f.as_of DESC NULLS LAST
                         LIMIT 120""", params)
        facts = cur.fetchall()
        tl = [t.lower() for t in terms]
        facts.sort(key=lambda f: -sum(1 for t in tl if t in f"{f['statement']} {f['excerpt'] or ''}".lower()))
        seen = set()
        for f in facts:
            key = (f["statement"] or "")[:120].lower()
            if key in seen:
                continue
            seen.add(key)
            ex = (f["excerpt"] or "").strip()
            txt = f["statement"] + (f' — quote: "{ex[:260]}"' if ex else "")
            src.append({"kind": "fact", "label": f"{f['provenance_level']} fact #{f['id']}",
                        "client": f["client_code"], "matter": f["matter_code"],
                        "date": str(f["as_of"])[:10] if f["as_of"] else None, "text": txt,
                        "doc_id": int(f["source_id"]) if f["source_kind"] == "doc" and str(f["source_id"]).isdigit() else None,
                        "prov": f["provenance_level"]})
            if sum(1 for s in src if s["kind"] == "fact") >= 10:
                break

    # 4) Document passages — trigram-indexed text, ranked by distinct term coverage.
    if pats:
        mclause = ("AND (d.matter_code = ANY(%s) OR d.id IN (SELECT doc_id FROM document_matter_links "
                   "WHERE matter_code = ANY(%s)))") if matters else ""
        params = [pats, clients, clients] + ([matters, matters] if matters else [])
        cur.execute(f"""SELECT d.id, COALESCE(NULLIF(d.smart_filename,''), d.original_filename) AS name,
                               d.case_file, d.matter_code, d.doc_date, d.classification, d.extracted_text
                          FROM documents d
                         WHERE d.extracted_text ILIKE ANY(%s)
                           AND (d.case_file = ANY(%s) OR d.id IN (
                                SELECT l.doc_id FROM document_matter_links l JOIN matters m
                                    ON m.matter_code = l.matter_code WHERE m.client_code = ANY(%s)))
                           {mclause}
                         LIMIT 60""", params)
        docs = cur.fetchall()
        tl = [t.lower() for t in terms]

        def _score(d):
            low = (d["extracted_text"] or "").lower()
            draft = "draft" in f"{d['name'] or ''} {d['classification'] or ''}".lower()
            return (sum(1 for t in tl if t in low), sum(low.count(t) for t in tl) / 50.0 - (1.5 if draft else 0))
        docs.sort(key=_score, reverse=True)
        cited_docs = {s["doc_id"] for s in src if s["doc_id"]}
        n = 0
        for d in docs:
            if d["id"] in cited_docs:
                continue
            draft = "draft" in f"{d['name'] or ''} {d['classification'] or ''}".lower()
            client = d["case_file"] if d["case_file"] in clients else clients[0] if len(clients) == 1 else d["case_file"]
            src.append({"kind": "document", "label": f"doc {d['id']}: {(d['name'] or '')[:70]}"
                                                     + (" [DRAFT]" if draft else ""),
                        "client": client, "matter": d["matter_code"],
                        "date": str(d["doc_date"])[:10] if d["doc_date"] else None,
                        "text": _window(d["extracted_text"] or "", terms), "doc_id": d["id"],
                        "prov": "draft" if draft else "document"})
            n += 1
            if n >= 6:
                break

    # 5) Planning questions — the live §0 picture for the scope.
    if plan:
        mfilter = "AND matter_code = ANY(%s)" if matters else ""
        mparam = [matters] if matters else []
        cur.execute(f"""SELECT matter_code, client_code, next_deadline, left(COALESCE(next_event,''),160) ev
                          FROM matters WHERE {_REAL} AND client_code = ANY(%s) {mfilter}
                           AND next_deadline BETWEEN CURRENT_DATE AND CURRENT_DATE + 21
                         ORDER BY next_deadline""", [clients] + mparam)
        for r in cur.fetchall():
            src.append({"kind": "live", "label": f"Upcoming date — {r['matter_code']}", "client": r["client_code"],
                        "matter": r["matter_code"], "date": str(r["next_deadline"]),
                        "text": f"{r['next_deadline']}: {r['ev']}", "doc_id": None, "prov": "operator"})
        cur.execute(f"""SELECT matter_code, client_code, next_deadline FROM matters
                         WHERE {_REAL} AND client_code = ANY(%s) {mfilter} AND next_deadline < CURRENT_DATE
                         ORDER BY next_deadline""", [clients] + mparam)
        od = cur.fetchall()
        if od:
            src.append({"kind": "live", "label": "Overdue — date passed, still open", "client": ",".join(clients),
                        "matter": None, "date": None,
                        "text": "; ".join(f"{r['matter_code']} ({r['next_deadline']})" for r in od),
                        "doc_id": None, "prov": "operator"})
        cur.execute(f"""SELECT count(*) AS n FROM matters WHERE {_REAL} AND client_code = ANY(%s) {mfilter}
                          AND next_deadline IS NULL""", [clients] + mparam)
        nd = (cur.fetchone() or {}).get("n") or 0
        cur.execute("""SELECT state, count(*) AS n FROM office_obligation GROUP BY state""")
        drip = ", ".join(f"{r['n']} {r['state']}" for r in cur.fetchall())
        cur.execute("""SELECT title, matter_code, status, updated_at::date AS d FROM work_orders
                        WHERE status NOT IN ('done','cancelled') AND updated_at < now() - interval '72 hours'
                        ORDER BY updated_at LIMIT 8""")
        wo = cur.fetchall()
        src.append({"kind": "live", "label": "Operating picture (§0)", "client": ",".join(clients), "matter": None,
                    "date": None, "doc_id": None, "prov": "operator",
                    "text": (f"{nd} active matters have no next date. Drip obligations: {drip or 'none'}. "
                             f"Work orders stuck >72h: {len(wo)}"
                             + (": " + "; ".join(f"{w['title'] or w['matter_code']} (since {w['d']})" for w in wo)
                                if wo else "."))})
        # the live picture leads — record passages are background, never the agenda
        src = [s for s in src if s["kind"] == "live"] + [s for s in src if s["kind"] != "live"]
    return src


# ───────────────────────────── uploaded files ─────────────────────────────
# "Ask about this file": the file is read on the VPS with LOCAL tools only (PyMuPDF text layer,
# python-docx, tesseract OCR for scans/photos — no paid vision call), held in memory for an hour,
# and offered to the model as sources labelled "uploaded file — NOT part of the record". Nothing is
# written to documents / Drive / the corpus; adding a file to the record stays the ingest pipeline's job.

def _ocr_image(path: str) -> str:
    import subprocess
    r = subprocess.run(["tesseract", path, "-", "--psm", "3"], capture_output=True, text=True, timeout=120)
    return r.stdout


def _extract(path: str, name: str, fid: str) -> tuple:
    """→ (text, method, pages). Text layer first; scanned pages fall back to tesseract."""
    ext = os.path.splitext(name.lower())[1]
    if ext == ".pdf":
        import fitz
        doc = fitz.open(path)
        pages = doc.page_count
        out, ocrd = [], 0
        for i, page in enumerate(doc):
            t = page.get_text("text") or ""
            if len(t.strip()) < 80 and ocrd < _OCR_PAGES:          # no usable text layer → OCR this page
                _upd_file(fid, stage=f"OCR page {i + 1} of {pages}…")
                png = f"{path}.p{i}.png"
                page.get_pixmap(dpi=220).save(png)
                try:
                    t = _ocr_image(png)
                finally:
                    os.unlink(png)
                ocrd += 1
            out.append(f"[page {i + 1}]\n{t.strip()}")
        doc.close()
        method = "text layer" if not ocrd else f"text layer + OCR ({ocrd} page{'s' * (ocrd != 1)})"
        if ocrd >= _OCR_PAGES and pages > ocrd:
            method += f" — OCR capped at {_OCR_PAGES} pages"
        return "\n\n".join(out), method, pages
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(parts), "docx", None
    if ext in (".txt", ".md", ".csv"):
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(), "plain text", None
    _upd_file(fid, stage="OCR…")
    return _ocr_image(path), "OCR", 1


def _upd_file(fid, **kw):
    with _LOCK:
        if fid in FILES:
            FILES[fid].update(kw)


def _extract_job(fid: str, path: str, name: str):
    try:
        text, method, pages = _extract(path, name, fid)
        text = re.sub(r"[ \t]+", " ", text or "").strip()
        if len(text) < 20:
            _upd_file(fid, status="error", error="No readable text found in this file.")
        else:
            _upd_file(fid, status="ready", text=text, chars=len(text), method=method, pages=pages,
                      preview=re.sub(r"\s+", " ", text[:240]))
    except Exception as e:
        _upd_file(fid, status="error", error=f"Could not read the file ({type(e).__name__}: {str(e)[:120]})")
    finally:
        try:
            os.unlink(path)                       # the upload itself is never kept
        except OSError:
            pass


def _file_public(f: dict) -> dict:
    return {k: f.get(k) for k in ("id", "name", "status", "stage", "error", "chars", "method", "pages", "preview")}


def _file_sources(fids: list, q: str) -> list:
    """Passages of the attached files most relevant to the question (or the opening, for 'summarize')."""
    with _LOCK:
        files = [dict(FILES[f]) for f in fids if f in FILES and FILES[f].get("status") == "ready"]
    if not files:
        return []
    terms = [t.lower() for t in _terms(q)]
    budget = 7000 // len(files)                              # keep the prompt inside the model's context
    src = []
    for f in files:
        text = f["text"]
        if len(text) <= budget:
            chunks = [(0, text)]
        else:
            size = 1100
            chunks = [(i, text[i:i + size]) for i in range(0, len(text), size - 150)]
            scored = sorted(chunks, key=lambda c: -sum(c[1].lower().count(t) for t in terms))
            n = max(1, budget // size)
            hit = [c for c in scored[:n] if terms and any(t in c[1].lower() for t in terms)]
            pick = hit or chunks[:n]                          # no term hit → the opening (summaries)
            if chunks[0] not in pick:                         # always give the model the file's opening
                pick = [chunks[0]] + pick[:n - 1]
            chunks = sorted(pick)
        for off, ch in chunks:
            pg =re.findall(r"\[page (\d+)\]", text[:off + 1])
            src.append({"kind": "upload", "label": f"Uploaded file “{f['name']}”"
                                                   + (f", p.{pg[-1]}" if pg else "") + " — NOT part of the record",
                        "client": "", "matter": None, "date": None, "doc_id": None, "prov": "upload",
                        "text": re.sub(r"\s+", " ", ch).strip()})
    return src


# ───────────────────────────── generation + checks ─────────────────────────────

def _prompt(q: str, src: list, clients: list) -> str:
    lines = []
    for i, s in enumerate(src, 1):
        meta = " · ".join(x for x in (s["kind"], s.get("matter") or "", s["client"] or "", s["date"] or "") if x)
        lines.append(f"[{i}] ({meta}) {s['label']}: {s['text']}")
    return (
        "You are LandTek's research assistant. You answer the operator (Jonathan) using ONLY the "
        "company's own record given below.\n\n"
        f"TODAY IS {time.strftime('%A %d %B %Y')}. Any date before today has PASSED — never present a "
        "past date as upcoming; call it past/overdue.\n\nRULES:\n"
        "- Use ONLY the SOURCES. End every factual sentence with its citation(s), like [2] or [1][4].\n"
        "- If the sources do not contain the answer, say plainly what is missing (\"The record doesn't "
        "show …\"). Never guess and never use outside knowledge for facts about these matters.\n"
        "- Mark any reasoning that goes beyond the sources with \"(inference)\".\n"
        f"- Sources may belong to different clients ({', '.join(clients)}). Never combine facts from "
        "different clients into one statement.\n"
        "- Prefer verified facts and received documents over drafts; if you rely on a DRAFT, say so.\n"
        + ("- Sources marked 'uploaded file — NOT part of the record' are a file the operator just "
           "attached. Cite them like any source, but never describe what they say as established in "
           "LandTek's record; where the file and the record agree or conflict, say so.\n"
           if any(s["kind"] == "upload" for s in src) else "") +
        "- Lead with the direct answer in 1–3 sentences, then supporting points as short '- ' bullets. "
        "Plain language. At most about 250 words.\n\n"
        f"QUESTION: {q}\n\nSOURCES:\n" + "\n".join(lines) + "\n\nANSWER:\n"
    )


def _llm(prompt: str, ctx: int = 8192) -> str:
    body = {"model": MODEL, "stream": False, "prompt": prompt,
            "options": {"temperature": 0.1, "num_ctx": ctx, "num_predict": 700}}
    req = urllib.request.Request(OLLAMA_URL + "/api/generate", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read()).get("response", "").strip()


def _checks(cur, answer: str, src: list) -> dict:
    """Uncited-sentence ratio + Leo's own answer gate (citations rewritten to its doc:N form)."""
    cited = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer) if 1 <= int(n) <= len(src)})
    bad = sorted({int(n) for n in re.findall(r"\[(\d{1,2})\]", answer) if not 1 <= int(n) <= len(src)})
    sents = [s for s in re.split(r"(?<=[.!?])\s+", re.sub(r"(?m)^\s*[-•]\s*", "", answer)) if len(s.strip()) > 25]
    uncited = [s for s in sents if not re.search(r"\[\d{1,2}\]", s) and "(inference)" not in s
               and not re.search(r"(?i)record doesn.t|not in the record|no (record|source)", s)]
    gate = {}
    try:
        if _SCRIPTS not in sys.path:
            sys.path.insert(0, _SCRIPTS)
        import leo_answer_gate as G
        gform = re.sub(r"\[(\d{1,2})\]",
                       lambda m: (f" (doc:{src[int(m.group(1)) - 1]['doc_id']})"
                                  if 1 <= int(m.group(1)) <= len(src) and src[int(m.group(1)) - 1]["doc_id"]
                                  else ""), answer)
        g = G.gate(cur, gform)
        gate = {"verdict": g.get("verdict"), "fails": g.get("fails", [])[:4], "warns": (g.get("warns") or [])[:4]}
    except Exception as e:
        gate = {"verdict": "unavailable", "error": f"{type(e).__name__}"}
    return {"cited": cited, "bad_citations": bad, "n_sentences": len(sents), "n_uncited": len(uncited),
            "uncited_examples": [u[:110] for u in uncited[:2]], "gate": gate}


# ───────────────────────────── jobs ─────────────────────────────

def _upd(jid, **kw):
    with _LOCK:
        if jid in JOBS:
            JOBS[jid].update(kw)


def _run(jid: str, q: str, scope: str, deep: bool, fids: list = ()):
    t0 = time.time()
    conn = _db()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        clients, matters = _resolve_scope(cur, scope)
        conn.rollback()
        # 1) EXACT — Leo's precise routes, dry-run, always rolled back. Client-scoped only; skipped
        #    when a file is attached (the question is about the file, not a record lookup).
        if not deep and not fids and len(clients) == 1:
            _upd(jid, stage="Checking exact lookups…")
            try:
                if _SCRIPTS not in sys.path:
                    sys.path.insert(0, _SCRIPTS)
                import leo_service as L
                r = L.try_purpose_route(cur, clients[0], q, dry_run=True) or {}
            except Exception:
                r = {}
            finally:
                conn.rollback()
            via = r.get("via") or ""
            if r.get("text") and via.startswith(_PRECISE_VIA):
                _upd(jid, status="done", mode="exact", answer=r["text"], via=via, sources=[], checks={},
                     clients=clients, ms=int((time.time() - t0) * 1000))
                return
        # 2) GROUNDED — retrieve, then write a cited answer on the local model.
        _upd(jid, stage="Searching the record…")
        plan = bool(_PLAN_RE.search(q))
        fsrc = _file_sources(list(fids), q)
        if fids and not fsrc:
            _upd(jid, status="error", error="The attached file is no longer available (files are kept for "
                                            "one hour) — attach it again.", ms=int((time.time() - t0) * 1000))
            return
        src = fsrc + _retrieve(cur, q, clients, matters, plan)[:max(6, 22 - len(fsrc))]
        conn.rollback()
        if not src:
            _upd(jid, status="done", mode="not_found", via="retrieval",
                 answer="Nothing in the record matches this question in the chosen scope. Try naming the "
                        "matter, a party, a title number, or widen the scope.",
                 sources=[], checks={}, clients=clients, ms=int((time.time() - t0) * 1000))
            return
        _upd(jid, stage=f"Reading {len(src)} sources — writing the answer on the local model…",
             n_sources=len(src))
        answer = _llm(_prompt(q, src, clients), ctx=12288 if fsrc else 8192)
        _upd(jid, stage="Checking the answer against the record…")
        checks = _checks(cur, answer, src)
        conn.rollback()
        for i, s in enumerate(src, 1):
            s["n"] = i
            s["cited"] = i in checks["cited"]
        _upd(jid, status="done", mode="grounded", answer=answer, via=f"retrieval+{MODEL}", sources=src,
             checks=checks, clients=clients, ms=int((time.time() - t0) * 1000))
    except urllib.error.URLError as e:
        _upd(jid, status="error", error=f"The local model on the Mac is unreachable ({e.reason}). Is the Mac "
                                         "awake with Ollama running?", ms=int((time.time() - t0) * 1000))
    except Exception as e:
        _upd(jid, status="error", error=f"{type(e).__name__}: {str(e)[:200]}", ms=int((time.time() - t0) * 1000))
    finally:
        try:
            conn.rollback()
        finally:
            cur.close()
            conn.close()


@bp.route("/", methods=["POST"])
def start():
    data = request.get_json(silent=True) or request.form
    q = (data.get("q") or "").strip()[:800]
    scope = (data.get("scope") or "all").strip()[:80]
    deep = str(data.get("deep") or "").lower() in ("1", "true", "yes")
    raw = data.get("files")
    fids = [str(f)[:16] for f in raw][:4] if isinstance(raw, list) else []
    if len(q) < 3:
        return jsonify({"error": "Ask a question (at least 3 characters)."}), 400
    now = time.time()
    with _LOCK:
        for k in [k for k, v in JOBS.items() if now - v["created"] > _JOB_TTL]:
            JOBS.pop(k, None)
        jid = uuid.uuid4().hex[:12]
        JOBS[jid] = {"id": jid, "q": q, "scope": scope, "status": "running", "stage": "Starting…",
                     "created": now}
    threading.Thread(target=_run, args=(jid, q, scope, deep, fids), daemon=True).start()
    return jsonify({"job_id": jid})


@bp.route("/file", methods=["POST"])
def upload():
    """Multipart `file` → {id, status:'reading'}; poll GET /file/<id> until ready."""
    import tempfile
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "No file received."}), 400
    name = os.path.basename(f.filename)[:120]
    if not name.lower().endswith(_FILE_EXT):
        return jsonify({"error": "Supported: PDF, Word (.docx), text/CSV, and photos/scans (JPG, PNG, TIFF)."}), 400
    fd, path = tempfile.mkstemp(prefix="console_upload_", suffix=os.path.splitext(name)[1].lower())
    with os.fdopen(fd, "wb") as fh:
        f.save(fh)
    now = time.time()
    with _LOCK:
        for k in [k for k, v in FILES.items() if now - v["created"] > _JOB_TTL]:
            FILES.pop(k, None)
        while len(FILES) >= _MAX_FILES:
            FILES.pop(min(FILES, key=lambda k: FILES[k]["created"]), None)
        fid = uuid.uuid4().hex[:12]
        FILES[fid] = {"id": fid, "name": name, "status": "reading", "stage": "Reading…", "created": now}
    threading.Thread(target=_extract_job, args=(fid, path, name), daemon=True).start()
    return jsonify({"id": fid, "name": name, "status": "reading"})


@bp.route("/file/<fid>", methods=["GET"])
def file_status(fid: str):
    with _LOCK:
        f = dict(FILES.get(fid) or {})
    if not f:
        return jsonify({"status": "error", "error": "This file expired — attach it again."}), 404
    return jsonify(_file_public(f))


@bp.route("/<jid>", methods=["GET"])
def poll(jid: str):
    with _LOCK:
        j = dict(JOBS.get(jid) or {})
    if not j:
        return jsonify({"status": "error", "error": "This answer expired — ask again."}), 404
    j["elapsed"] = int(time.time() - j["created"])
    return jsonify(j)
