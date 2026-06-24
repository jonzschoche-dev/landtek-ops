#!/usr/bin/env python3
"""case_synthesizer.py — RAG-fed, element-driven legal synthesis. LOCAL-FIRST / offline-sovereign.

The upgrade pipeline: a matter playbook decomposes the theory into legal ELEMENTS → coverage-gate (are the
cited statutes embedded in the law library?) → per element, semantic-retrieve the best record passages
(rag_local) + the governing rule text (legal_chunks) → SYNTHESIZE each element → assemble (Applicable Law +
element analyses) → markdown (→ finalize_docx).

The reasoner is LOCAL by default (Ollama qwen2.5 on the Mac) so the stack produces work UNPLUGGED. A frontier
brain is used ONLY as an optional online sharpener (--frontier) and degrades to local if unavailable —
never a hard dependency. Runs on the Mac: local embed (fastembed) + local reason (Ollama); the DB is reached
over the tailnet (works on LAN without the broader internet).

  python3 scripts/case_synthesizer.py --playbook playbooks/ombudsman_1891.json --out 1891_output/synth.md [--finalize] [--frontier]
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rag_embed_local as rag

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LOCAL_MODEL = os.environ.get("LANDTEK_SYNTH_MODEL", "qwen2.5:14b-instruct")
SSH = ["ssh", "-o", "ConnectTimeout=40", "root@100.85.203.58"]


def _vps_psql(sql):
    r = subprocess.run(SSH + ["docker exec -i n8n-postgres-1 psql -U n8n -d n8n -t -A"],
                       input=sql, capture_output=True, text=True, timeout=90)
    return r.stdout.strip()


def _ollama(prompt):
    body = {"model": LOCAL_MODEL, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 8192}}
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=400) as r:
        return json.loads(r.read().decode()).get("response", "").strip()


def _frontier(prompt):
    """Optional online sharpener. Uses the Anthropic API if a key is configured; else falls back to local."""
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


def _rule_text(citation_ilike, kw_ilike, limit=2):
    sql = (f"SELECT string_agg(text, E'\\n\\n') FROM (SELECT text FROM legal_chunks "
           f"WHERE citation ILIKE '%{citation_ilike}%' AND text ILIKE '%{kw_ilike}%' "
           f"ORDER BY chunk_no LIMIT {limit}) s;")
    return _vps_psql(sql)


def _covered(citation_ilike):
    return (_vps_psql(f"SELECT count(*) FROM legal_chunks WHERE citation ILIKE '%{citation_ilike}%';") or "0") != "0"


def synth_element(el, use_frontier):
    passages = rag.retrieve(el["rag_query"], k=el.get("k", 6))
    rule = el.get("_rule", "")
    pblock = "\n".join(f"- {p['text']} [{p['file']}]" for p in passages) or "(no passages retrieved)"
    prompt = (
        "You are senior Philippine counsel writing one section of an evidence-grounded analysis.\n\n"
        f"SECTION: {el['heading']}\n\n"
        f"GOVERNING RULE (verbatim statutory text — apply ONLY this; cite no other statute):\n{rule[:2500]}\n\n"
        "SUPPORTING PASSAGES FROM THE RECORD (each is from a real document; the bracket is the document's "
        "name — refer to documents by a short description, NEVER by a number or filename):\n"
        f"{pblock}\n\n"
        "Write 2–4 tight paragraphs: state the rule briefly, then apply it to the SPECIFIC facts in the "
        "passages, quoting the telling details. Do not invent facts beyond the passages. Professional, "
        "judicious prose — no headings, no bullet lists, no document IDs."
    )
    out = (_frontier(prompt) if use_frontier else None) or _ollama(prompt)
    return out, passages


def build(playbook, out_path, use_frontier=False):
    pb = json.load(open(playbook))
    md = [f"# {pb['title']}", f"## {pb.get('subtitle','')}", "", "---", ""]
    # coverage-gate: fetch each statute's rule text once; attach to every element that cites it
    law_section, gate = {}, []
    for el in pb["elements"]:
        el["_rule_pool"] = []
        for st in el.get("statutes", []):
            cite, ilike, kw = st["cite"], st["citation_ilike"], st["kw_ilike"]
            if cite not in law_section:
                law_section[cite] = _rule_text(ilike, kw) if _covered(ilike) else None
            if law_section[cite]:
                el["_rule_pool"].append((cite, law_section[cite]))
            elif cite not in gate:
                gate.append(cite)
    md.append("## Applicable law")
    for cite, txt in law_section.items():
        md.append(f"**{cite}.** {txt[:600]}" if txt else f"**{cite}** — *[not embedded in the law library — obtain before filing]*")
    md.append("")
    if gate:
        print(f"[synth] COVERAGE GAP — statutes not embedded: {', '.join(gate)}", file=sys.stderr)
    # elements
    brain = "frontier (online sharpener)" if (use_frontier and os.environ.get("ANTHROPIC_API_KEY")) else f"local {LOCAL_MODEL}"
    print(f"[synth] reasoning on: {brain}", file=sys.stderr)
    for el in pb["elements"]:
        el["_rule"] = "\n\n".join(t for _, t in el.get("_rule_pool", []))
        print(f"[synth] · {el['heading'][:50]} …", file=sys.stderr)
        analysis, _ = synth_element(el, use_frontier)
        md.append(f"## {el['heading']}")
        md.append(analysis)
        md.append("")
    md.append("---")
    md.append(f"*Synthesized {('with a frontier sharpener' if use_frontier else 'locally (offline-capable)')} "
              f"from the corpus RAG and the embedded law library. LandTek — for counsel review.*")
    open(out_path, "w").write("\n".join(md))
    print(f"[synth] wrote {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--playbook", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--frontier", action="store_true")
    a = ap.parse_args()
    build(a.playbook, a.out, a.frontier)
    if a.finalize:
        import finalize_docx
        docx = a.out.replace(".md", ".docx")
        finalize_docx.build(a.out, docx)
        print(f"[synth] finalized → {docx}")


if __name__ == "__main__":
    main()
