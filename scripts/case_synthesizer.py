#!/usr/bin/env python3
"""case_synthesizer.py — RAG-fed, element-driven legal synthesis. LOCAL-FIRST / offline-sovereign.

The pipeline: a matter playbook decomposes the theory into a dispositive FRAME + legal ELEMENTS →
coverage-gate (are the cited statutes embedded?) → PINPOINT the exact cited provision (scrubbed of
HTML/copyright boilerplate, not a blind 600-char dump) → per section, semantic-retrieve the best
record passages (rag_local) → SYNTHESIZE each section against an explicit THESIS (anti-drift,
anti-hallucination prompt) → assemble the full dossier (Applicable Law · dispositive frame · element
analyses · gaps · auto-built Document Index of named, hyperlinked sources) → markdown (→ finalize_docx).

The reasoner is frontier-by-default when an API key is present (the sharpener that makes it a good
product) and degrades to LOCAL Ollama (qwen2.5) so the stack still produces work UNPLUGGED — never a
hard dependency. Pass --local to force the offline reasoner.

  python3 scripts/case_synthesizer.py --playbook playbooks/ombudsman_1891.json --out 1891_output/synth.md [--finalize] [--local]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rag_embed_local as rag

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.environ.get("LANDTEK_SYNTH_MODEL", "qwen2.5:14b-instruct")
BASE_URL = os.environ.get("LEO_PUBLIC_BASE_URL", "https://leo.hayuma.org/files/c")
SSH = ["ssh", "-o", "ConnectTimeout=40", "root@100.85.203.58"]
# chunks that are front-matter / site boilerplate, never the operative provision
BOILER = ("COPYRIGHT", "Creative Commons", "Web Design and Programming", "LawPhil Project",
          "Arellano Law Foundation", "This work is licensed", "Begun and held", "REPUBLIC ACT No.")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"


def _vps_psql(sql):
    r = subprocess.run(SSH + ["docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"],
                       input=sql, capture_output=True, text=True, timeout=90)
    return r.stdout.strip()


def _ollama(prompt):
    body = {"model": LOCAL_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=400) as r:
        return json.loads(r.read().decode()).get("response", "").strip()


def _frontier(prompt):
    """Online sharpener — uses the Anthropic API if a key is configured; else None (falls back to local)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None
    try:
        body = {"model": "claude-sonnet-4-6", "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json", "x-api-key": key,
                                              "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=120) as r:
            return "".join(b.get("text", "") for b in json.loads(r.read().decode()).get("content", [])).strip()
    except Exception:
        return None


def _covered(citation_ilike):
    return (_vps_psql(f"SELECT count(*) FROM legal_chunks WHERE citation ILIKE '%{citation_ilike}%';") or "0") != "0"


def _pinpoint_law(citation_ilike, kw_ilike, cap=720):
    """Return the ONE cleanest chunk that holds the operative clause (kw), scrubbed of HTML/boilerplate.
    Fixes the old blind 600-char dump that surfaced copyright notices and the wrong section."""
    kw = kw_ilike.replace("'", "''")
    sql = (f"SELECT chunk_no || E'\\t' || replace(replace(text, E'\\n', ' '), E'\\t', ' ') "
           f"FROM legal_chunks WHERE citation ILIKE '%{citation_ilike}%' AND text ILIKE '%{kw}%' "
           f"ORDER BY chunk_no LIMIT 20;")
    cands = []
    for line in _vps_psql(sql).splitlines():
        if "\t" not in line:
            continue
        txt = re.sub(r"<!--.*?-->", " ", line.split("\t", 1)[1], flags=re.S)
        txt = re.sub(r"\s+", " ", txt).strip()
        if not txt or any(b in txt for b in BOILER):
            continue
        pos = txt.lower().find(kw_ilike.lower())
        cands.append((pos if pos >= 0 else 9999, txt))
    if not cands:
        return ""
    cands.sort(key=lambda c: c[0])          # provision that LEADS with the operative clause wins
    pos, txt = cands[0]
    # if the operative clause sits deep in a chunk shared by several subsections, trim to its own marker
    if 120 < pos < 9999:
        marks = list(re.finditer(r"\(?[a-z0-9]{1,2}[\)\.]\s", txt[:pos + 3]))
        if marks:
            txt = txt[marks[-1].start():]
    if len(txt) > cap:
        cut = txt.rfind(". ", 0, cap)
        txt = (txt[:cut + 1] if cut > cap * 0.5 else txt[:cap].rstrip() + "…")
    return txt


def _doc_title(fn):
    t = re.sub(r"\.(pdf|docx|doc|png|jpe?g|txt)$", "", fn or "", flags=re.I)
    t = re.sub(r"[_]+", " ", t)
    t = re.sub(r"\s*\(\d+\)\s*$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t or "source document"


_ACR = {"DILG", "ARTA", "NAPOLCOM", "RFO", "CART", "LGU", "SB", "RA", "PD", "RPC", "TCT", "OSCA",
        "FOI", "COA", "BAC", "DENR", "LRA", "SPA", "MTC", "RTC", "CSC", "RPT", "SALN", "DAR", "NBI",
        "OMB", "IRR", "MTO", "RD", "CTN", "SL"}
_SMALL = {"of", "to", "the", "a", "an", "and", "in", "on", "for", "vs", "v.", "v", "with", "by", "or"}


def _cap(w):
    for j, ch in enumerate(w):
        if ch.isalpha():
            return w[:j] + ch.upper() + w[j + 1:]
    return w


def _titlecaps(t):
    """Uniform Title Case: keep known acronyms upper, lower small connecting words, capitalize the rest."""
    out = []
    for i, w in enumerate(t.split()):
        bare = re.sub(r"[^A-Za-z]", "", w)
        if not bare:
            out.append(w)
        elif bare.upper() in _ACR:
            out.append(w.replace(bare, bare.upper()))
        elif i > 0 and w.lower() in _SMALL:
            out.append(w.lower())
        elif bare.isupper() and len(bare) > 1:
            out.append(w.replace(bare, bare.title()))
        else:
            out.append(_cap(w))
    return " ".join(out)


def _fmt_date(s):
    months = ["", "January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", (s or "").strip())
    if not m:
        return "", ""
    y, mo, d = m.groups()
    return f"{int(d)} {months[int(mo)]} {y}", f"{y}-{mo}-{d}"


def _index_meta(doc_ids):
    """Per-doc metadata for a clean back index: a usable name, the date, and a text snippet (for the
    docket-only / unnamed documents whose filename tells a human nothing)."""
    if not doc_ids:
        return {}
    sql = ("SELECT id || E'\\t' || coalesce(nullif(document_title,''), nullif(smart_filename,''), original_filename, '') "
           "|| E'\\t' || coalesce(doc_date::text,'') "
           "|| E'\\t' || replace(left(regexp_replace(coalesce(extracted_text,''), '[[:space:]]+', ' ', 'g'), 380), E'\\t', ' ') "
           f"FROM documents WHERE id IN ({','.join(doc_ids)});")
    meta = {}
    for line in _vps_psql(sql).splitlines():
        p = line.split("\t")
        if len(p) >= 4:
            disp, iso = _fmt_date(p[2])
            meta[p[0]] = {"name": p[1].strip(), "date": disp, "iso": iso, "snippet": p[3].strip()}
    return meta


def _index_label(m, use_model=True):
    """A clean, descriptive label: keep a usable filename, but for docket-only / ALL-CAPS / unnamed
    documents derive a short title from the content. Never a bare docket or 'source document'."""
    raw = _doc_title(m.get("name", ""))
    raw = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[ _]*", "", raw).strip()
    up = raw.upper()
    docketish = (not raw or raw.lower() == "source document" or "CTN" in up or "SL-" in up
                 or not re.search(r"[a-z]", raw)                                   # no lowercase = shouty/cryptic
                 or bool(re.fullmatch(r"(signed osca[ -]*)?(ctn[ -]*)?[a-z]{0,4}[ -]?sl[- 0-9a-z]+", raw, re.I)))
    if docketish and use_model and m.get("snippet"):
        try:
            g = _ollama("Name this Philippine legal document in 4 to 8 words: its document type and its subject "
                        "or the parties (e.g. 'Mayor's reply declining the records request'). Title Case, no docket "
                        "numbers, no quotation marks, no file name, no trailing period.\n\nDOCUMENT TEXT:\n" + m["snippet"][:380])
            g = g.strip().splitlines()[0].strip().strip('"').rstrip(".")
            if 4 <= len(g) <= 72 and not re.search(r"\bSL-?\d", g):
                raw = g
        except Exception:
            pass
    return _titlecaps(raw) or "Case document"


def _clean_analysis(text, rule):
    """Deterministic scrub of local-model artifacts: a re-dumped verbatim rule, echoed [source labels],
    and docket/annex parentheticals that belong in the index, not the prose."""
    rule_heads = [r.strip()[:30].lower() for r in re.split(r"\n\n+", rule) if r.strip()]
    keep = []
    for p in re.split(r"\n+", text):
        p = p.strip()
        if not p:
            continue
        low = p[:30].lower()
        if any(low.startswith(rh) for rh in rule_heads if rh):
            continue                                                            # standalone rule re-dump
        if re.match(r"^\(?[a-z]\)?[\.\)]?\s+(Causing|Neglecting|Imposition|Commitment|Professionalism)", p):
            continue
        keep.append(p)
    t = "\n\n".join(keep)
    # docket/annex citations belong in the back index, never woven into the prose
    t = re.sub(r"\s*\((?:Annex|CTN|ARTA|Case No\.?|SL-|G\.R\.)[^)]*\)", "", t)
    t = re.sub(r",?\s*(?:as\s+\w+\s+)?in\s+Annex\s+[A-Z0-9][A-Z0-9-]*(?:\s+of\s+ARTA\s+Case\s+No\.?\s*CTN\s*SL-[\d-]+)?", "", t, flags=re.I)
    t = re.sub(r"\s*\(?\bARTA\s+Case\s+No\.?\s*CTN\s*SL-[\d-]+\)?", "", t, flags=re.I)
    t = re.sub(r"\s*\bCTN\s*SL-[\d-]+", "", t)
    t = re.sub(r"\bas (?:detailed|stated|noted|shown) in \[[^\]]+\]", "the record shows", t, flags=re.I)
    t = re.sub(r"\[[^\]]{2,80}\]", "the record", t)                             # any other [label] echo
    t = re.sub(r"Ka[sz]+ey|Keesee\b", "Keesey", t)                             # the recurring name garble
    # one date format throughout: "Month D, YYYY" → "D Month YYYY"
    t = re.sub(rf"\b({MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})\b",
               lambda m: f"{int(m.group(2))} {m.group(1)} {m.group(3)}", t)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def synth_section(theory, rule, passages, use_frontier):
    pblock = "\n".join(f"- {p['text']} [{_doc_title(p['file'])}]" for p in passages) or "(no passages retrieved)"
    prompt = (
        "You are senior Philippine counsel writing one section of an evidence-grounded dossier for the "
        "Office of the Ombudsman.\n\n"
        f"THE THESIS OF THIS SECTION — argue exactly this; do NOT drift to any other issue:\n{theory}\n\n"
        "GOVERNING RULE — apply ONLY this verbatim text; cite no statute not given here:\n"
        f"{rule[:2500] or '(no separate rule text; argue the thesis without citing any statute not named in it)'}\n\n"
        "RECORD PASSAGES — each is from a real document; the bracket names it. Refer to documents by a short "
        "description, NEVER by number or filename:\n"
        f"{pblock}\n\n"
        "Write 2–4 tight paragraphs that PROVE THE THESIS: state the rule in one line, then apply it to the "
        "SPECIFIC facts in the passages, quoting the telling details verbatim. HARD RULES: (1) do not invent "
        "facts beyond the passages; (2) do NOT expand or guess what any acronym stands for — write it exactly as "
        "it appears (e.g. 'the CART'), never invent its meaning; (3) do not hedge — no 'may suggest', 'raises "
        "concerns', 'possibly', 'appears to' — state what the record shows; (4) no headings, no bullet lists, no "
        "document numbers, no markdown."
    )
    out = (_frontier(prompt) if use_frontier else None) or _ollama(prompt)
    return _clean_analysis(out, rule)


def build(playbook, out_path, use_frontier=True):
    pb = json.load(open(playbook))
    md = [f"# {pb['title']}", "", f"## {pb.get('subtitle', '')}", "", "---", ""]
    if pb.get("purpose_note"):
        md += [f"*{pb['purpose_note']}*", ""]

    frame = pb.get("dispositive_frame")
    order = ([frame] if frame else []) + pb["elements"]

    # ── coverage-gate + pinpoint each cited provision once (stable order: frame, then elements) ──
    law_cache, gate = {}, []
    for sec in order:
        rules = []
        for st in sec.get("statutes", []):
            cite = st["cite"]
            if cite not in law_cache:
                law_cache[cite] = _pinpoint_law(st["citation_ilike"], st["kw_ilike"]) if _covered(st["citation_ilike"]) else None
            if law_cache[cite]:
                rules.append((cite, law_cache[cite]))
            elif cite not in gate:
                gate.append(cite)
        sec["_rule"] = "\n\n".join(t for _, t in rules)
    if gate:
        print(f"[synth] COVERAGE GAP — not embedded: {', '.join(gate)}", file=sys.stderr)

    md += ["## Applicable law", ""]
    for cite, txt in law_cache.items():
        md.append(f"**{cite}.** {txt}" if txt else f"**{cite}** — *[not embedded in the law library — obtain official text before filing]*")
        md.append("")

    on_frontier = use_frontier and bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"[synth] reasoning on: {'frontier (online sharpener)' if on_frontier else f'local {LOCAL_MODEL}'}", file=sys.stderr)

    all_passages = []
    for sec in order:
        ps = rag.retrieve(sec["rag_query"], k=sec.get("k", 6))
        all_passages += ps
        print(f"[synth] · {sec['heading'][:52]} …", file=sys.stderr)
        md += [f"## {sec['heading']}", synth_section(sec["theory"], sec["_rule"], ps, use_frontier), ""]

    if pb.get("gaps"):
        md += ["## Gaps — what counsel must obtain or confirm", ""]
        md += [f"{i}. {g}" for i, g in enumerate(pb["gaps"], 1)]
        md.append("")

    # ── auto Document Index: clean descriptive labels, dated, chronological, deduped ──
    md += ["## Document index", ""]
    ids = []
    for p in all_passages:
        if p.get("doc_id") and p["doc_id"] not in ids:
            ids.append(p["doc_id"])
    meta = _index_meta(ids)
    entries = []
    for did in ids:
        m = meta.get(did, {"name": next((p["file"] for p in all_passages if p["doc_id"] == did), ""), "date": "", "iso": ""})
        label = _index_label(m)
        dated = f"{label} — {m['date']}" if m.get("date") else label
        entries.append((m.get("iso") or "9999", f"- **{dated}** — [open]({BASE_URL}/{did})"))
    for _, line in sorted(entries, key=lambda e: e[0]):
        md.append(line)
    md.append("")

    md += ["---",
           f"*Synthesized {'with a frontier sharpener' if on_frontier else 'locally (offline-capable)'} from the "
           f"corpus RAG and the embedded law library. LandTek — for counsel review; verify each cited document "
           f"before filing.*"]
    open(out_path, "w").write("\n".join(md))
    print(f"[synth] wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playbook", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--local", action="store_true", help="force the offline reasoner (skip frontier)")
    ap.add_argument("--frontier", action="store_true", help="(default behavior; kept for back-compat)")
    ap.add_argument("--selfheal", action="store_true", help="run the diligence gate + auto-fix loop after synthesis")
    ap.add_argument("--matter", default=None, help="matter-family prefix for the client-separation check (else playbook's 'matter')")
    a = ap.parse_args()
    build(a.playbook, a.out, use_frontier=not a.local)
    if a.selfheal:
        import dossier_fix
        matter = a.matter or json.load(open(a.playbook)).get("matter")
        healed, log, final = dossier_fix.heal(open(a.out).read(), matter)
        open(a.out, "w").write(healed)
        for line in log:
            print(f"[heal] {line}", file=sys.stderr)
        if final:
            print(f"[heal] {len(final)} issue(s) need human judgment — see dossier_verify", file=sys.stderr)
    if a.finalize:
        import finalize_docx
        docx = a.out.replace(".md", ".docx")
        finalize_docx.build(a.out, docx)
        print(f"[synth] finalized → {docx}")


if __name__ == "__main__":
    main()
