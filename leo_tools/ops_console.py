"""LandTek Console — the ONE place to test the product and the stack.

Built 2026-10-03 after the surface audit found ~60 working-but-disconnected pages and
no single view that MEASURES the product (MASTER_PLAN §0.9) or lets the operator TEST it.
Three panels, all live SQL, no new framework (reuses the /ops cockpit chrome):

  1. STACK   — the §0 scorecard (fronts dated, overdue, goals dated, drip clocks, stuck
               orders, the next 14 days) + machine health (failed units, disk, truth tests).
  2. PRODUCT — each client as they would see it (the same render the token portal serves),
               with that client's numbers and how many live client links exist.
  0. ASK     — pose ANY question to the record (console_ask.py): exact lookups via Leo's
               precise routes, else retrieval + a cited answer on the local model, checked by
               Leo's answer gate. Async (polled), read-only, $0. The page's centrepiece.

Internal only: mounted under /ops/ (nginx basic-auth). Read-only except the rolled-back ask.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import date

import psycopg2
import psycopg2.extras
from flask import Blueprint

from ops_dashboard import PG_DSN, _esc, _layout, _safe_fetch, _stat_card

bp = Blueprint("ops_console", __name__, url_prefix="/ops/console")

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

# Active = a real matter that is not closed (AUTO- triage stubs excluded) — same
# definition the §0 survey and the client portal use.
_ACTIVE = ("matter_code NOT LIKE 'AUTO-%%' AND COALESCE(status,'') NOT IN ('closed','archived')")



def _db():
    return psycopg2.connect(PG_DSN)


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception as e:  # degrade, never crash the page
        return f"(unavailable: {type(e).__name__})"


# ───────────────────────────── 1. STACK ─────────────────────────────

def _scorecard(cur, conn) -> str:
    today = date.today()
    tot = _safe_fetch(cur, conn, f"SELECT count(*) AS n FROM matters WHERE {_ACTIVE}", one=True) or {}
    fut = _safe_fetch(cur, conn, f"SELECT count(*) AS n FROM matters WHERE {_ACTIVE} "
                      "AND next_deadline >= CURRENT_DATE", one=True) or {}
    overdue = _safe_fetch(cur, conn, f"""
        SELECT matter_code, client_code, next_deadline, left(COALESCE(next_event,''),110) AS ev
          FROM matters WHERE {_ACTIVE} AND next_deadline < CURRENT_DATE
         ORDER BY next_deadline""", default=[])
    upcoming = _safe_fetch(cur, conn, f"""
        SELECT matter_code, client_code, next_deadline, left(COALESCE(next_event,''),110) AS ev
          FROM matters WHERE {_ACTIVE}
           AND next_deadline BETWEEN CURRENT_DATE AND CURRENT_DATE + 14
         ORDER BY next_deadline""", default=[])
    goals = _safe_fetch(cur, conn, """
        SELECT count(*) AS n, count(*) FILTER (WHERE target_date IS NOT NULL) AS dated
          FROM client_goals WHERE COALESCE(status,'active') NOT IN ('achieved','cancelled','dropped')""",
                        one=True) or {}
    drip = _safe_fetch(cur, conn, """
        SELECT count(*) AS n,
               count(*) FILTER (WHERE served_at IS NOT NULL) AS served,
               count(*) FILTER (WHERE served_at IS NOT NULL AND due_at >= now()) AS running,
               string_agg(DISTINCT state, ', ') AS states
          FROM office_obligation""", one=True) or {}
    wo = _safe_fetch(cur, conn, """
        SELECT count(*) FILTER (WHERE status NOT IN ('done','cancelled')) AS open,
               count(*) FILTER (WHERE status NOT IN ('done','cancelled')
                                AND updated_at < now() - interval '72 hours') AS stuck,
               count(*) FILTER (WHERE status = 'done') AS done
          FROM work_orders""", one=True) or {}

    n_tot, n_fut = tot.get("n") or 0, fut.get("n") or 0
    pct = f"{round(100 * n_fut / n_tot)}%" if n_tot else "—"
    cards = "".join([
        _stat_card("Fronts with a dated next move", f"{n_fut} / {n_tot}", f"{pct} · target 100%"),
        _stat_card("Overdue — date passed, still open", len(overdue), "each needs a re-date or outcome"),
        _stat_card("Client goals dated", f"{goals.get('dated') or 0} / {goals.get('n') or 0}",
                   "§0: an undated goal does not exist"),
        _stat_card("Drip clocks running", drip.get("running") or 0,
                   f"{drip.get('served') or 0} of {drip.get('n') or 0} served · {_esc(drip.get('states') or '')}"),
        _stat_card("Work orders stuck > 72h", wo.get("stuck") or 0,
                   f"{wo.get('open') or 0} open · {wo.get('done') or 0} done"),
    ])

    def _rows(rows, empty):
        if not rows:
            return f'<p class="empty">{empty}</p>'
        body = "".join(
            f"<tr><td style='white-space:nowrap'>{_esc(r['next_deadline'])}</td>"
            f"<td><a href='/ops/matter/{_esc(r['matter_code'])}'>{_esc(r['matter_code'])}</a></td>"
            f"<td class='muted'>{_esc(r['client_code'])}</td><td>{_esc(r['ev'])}</td></tr>"
            for r in rows)
        return f"<table><tr><th>Date</th><th>Matter</th><th>Client</th><th>Next event</th></tr>{body}</table>"

    return (f'<div class="grid-4">{cards}</div>'
            f'<div class="section-title">Next 14 days</div><div class="card">'
            f'{_rows(upcoming, "Nothing dated in the next 14 days.")}</div>'
            f'<div class="section-title">Overdue — date passed, still open '
            f'<span class="muted">({len(overdue)})</span></div><div class="card">'
            f'{_rows(overdue, "Nothing overdue.")}</div>')


def _health() -> str:
    failed = _run(["systemctl", "--failed", "--no-legend", "--plain"])
    failed_units = [ln.split()[0] for ln in failed.splitlines() if ln.strip() and not ln.startswith("(")]
    du = shutil.disk_usage("/")
    disk_pct = round(100 * du.used / du.total)
    tt = _run(["systemctl", "show", "landtek-truth-tests.service",
               "-p", "Result", "-p", "ExecMainExitTimestamp", "--value"]).splitlines()
    tt_result = tt[0] if tt else "?"
    tt_when = tt[1] if len(tt) > 1 else ""
    leo = _run(["systemctl", "is-active", "leo-tools.service"])
    cards = "".join([
        _stat_card("Failed units", len(failed_units), ", ".join(failed_units) or "none — target 0"),
        _stat_card("Disk used", f"{disk_pct}%", "target under 85%"),
        _stat_card("Truth tests (nightly)", "passing" if tt_result == "success" else tt_result,
                   _esc(tt_when)),
        _stat_card("leo-tools service", leo, "serves /ops, /client, the APIs"),
    ])
    return f'<div class="grid-4">{cards}</div>'


# ───────────────────────────── 2. PRODUCT ─────────────────────────────

def _product(cur, conn) -> str:
    clients = _safe_fetch(cur, conn, """
        SELECT c.client_code, c.name,
               (SELECT count(*) FROM matters m WHERE m.client_code = c.client_code
                  AND m.matter_code NOT LIKE 'AUTO-%%'
                  AND COALESCE(m.status,'') NOT IN ('closed','archived')) AS active,
               (SELECT count(*) FROM matters m WHERE m.client_code = c.client_code
                  AND m.matter_code NOT LIKE 'AUTO-%%'
                  AND COALESCE(m.status,'') NOT IN ('closed','archived')
                  AND m.next_deadline >= CURRENT_DATE) AS dated,
               (SELECT min(next_deadline) FROM matters m WHERE m.client_code = c.client_code
                  AND m.next_deadline >= CURRENT_DATE) AS next_date,
               (SELECT score FROM client_dependability d WHERE d.client_code = c.client_code
                 ORDER BY run_at DESC LIMIT 1) AS dep_score,
               (SELECT count(*) FROM client_access_tokens t WHERE t.client_code = c.client_code
                  AND t.revoked_at IS NULL) AS live_links
          FROM clients c
         WHERE c.client_code IS NOT NULL AND c.client_code <> ''
           AND c.client_code NOT IN ('Archive','PENDING_TRIAGE')
           AND EXISTS (SELECT 1 FROM matters m WHERE m.client_code = c.client_code
                         AND m.matter_code NOT LIKE 'AUTO-%%'
                         AND COALESCE(m.status,'') NOT IN ('closed','archived'))
         ORDER BY c.client_code""", default=[])
    if not clients:
        return '<p class="empty">No clients found.</p>'
    rows = []
    for c in clients:
        cc = _esc(c["client_code"])
        links = c["live_links"] or 0
        link_badge = (f"<span class='badge badge-warn'>{links} live client link(s)</span>"
                      if links else "<span class='badge badge-off'>no live links</span>")
        dep = "—" if c["dep_score"] is None else f"{float(c['dep_score']):.1f}"
        rows.append(
            f"<tr><td><strong>{_esc(c['name'] or c['client_code'])}</strong>"
            f"<div class='muted'>{cc}</div></td>"
            f"<td>{c['dated']} / {c['active']}</td>"
            f"<td>{_esc(c['next_date'] or '—')}</td>"
            f"<td>{dep}</td><td>{link_badge}</td>"
            f"<td style='white-space:nowrap'>"
            f"<a class='badge badge-ok' href='/ops/portal/{cc}/portfolio'>Home as client sees it</a> "
            f"<a class='badge badge-ok' href='/ops/portal/{cc}'>Cases view</a></td></tr>")
    return ("<p class='muted'>The client views below are the same render the client's private link "
            "serves (verified identical by the 2026-10-03 audit). §0: nothing is shown to a client "
            "until you say <strong>ready</strong> — live links are flagged.</p>"
            "<div class='card'><table><tr><th>Client</th><th>Matters dated</th><th>Next date</th>"
            "<th>Dependability</th><th>Client links</th><th>Open</th></tr>"
            f"{''.join(rows)}</table></div>")


# ───────────────────────────── 0. ASK (UI) ─────────────────────────────

EXAMPLES = [
    ("client:MWK-001", "Summarize the Balane case and where it stands"),
    ("client:MWK-001", "What are the weaknesses in our case against Balane?"),
    ("all", "What should I focus on this week?"),
    ("client:MWK-001", "Where does the CV6839 just compensation money stand?"),
    ("client:MWK-001", "Who holds TCT 079-2021002126?"),
    ("client:Paracale-001", "What is the status of the AVI mining permits?"),
]

_ASK_CSS = """<style>
.ask{border:1px solid var(--border,#d0d7e2);border-radius:12px;padding:14px;margin:6px 0 18px;
  background:var(--card,#fff)}
.ask form{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end}
.ask select{padding:8px;border-radius:8px;max-width:100%;min-width:220px}
.ask textarea{flex:1 1 380px;min-height:52px;padding:10px;border-radius:8px;font:inherit;resize:vertical}
.ask button.go{padding:10px 18px;border-radius:8px;border:0;background:#0b2545;color:#fff;font-weight:600;cursor:pointer}
.ask button.go:disabled{opacity:.5;cursor:wait}
.ask .chips{margin:10px 0 4px;display:flex;flex-wrap:wrap;gap:6px}
.ask .chip{border:1px solid #c9d3e3;background:transparent;border-radius:14px;padding:4px 10px;font-size:12px;cursor:pointer;color:inherit}
.ask .bar{display:flex;justify-content:space-between;align-items:center;margin-top:10px;font-size:12px;opacity:.75}
.ask .bar button{font-size:12px;background:none;border:0;text-decoration:underline;cursor:pointer;color:inherit}
.qa{margin-top:14px;border-top:1px solid #e3e8f0;padding-top:12px}
.qa .q{font-weight:600;margin-bottom:6px}
.qa .q .sc{font-weight:400;font-size:12px;opacity:.65;margin-left:6px}
.qa .a{line-height:1.5}
.qa .a ul{margin:6px 0 6px 18px;padding:0}
.qa .meta{font-size:12px;opacity:.75;margin-top:8px}
.qa .tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;margin-right:6px;font-weight:600}
.tag.exact{background:#e3f4ea;color:#14532d}.tag.grounded{background:#e6eefc;color:#1e3a8a}
.tag.nf{background:#f1f1f1;color:#444}.tag.err{background:#fde8e8;color:#991b1b}
.tag.ok{background:#e3f4ea;color:#14532d}.tag.warn{background:#fff4e0;color:#8a4b00}.tag.bad{background:#fde8e8;color:#991b1b}
.qa a.cite{font-size:11px;vertical-align:super;text-decoration:none;font-weight:600}
.qa details{margin-top:8px}.qa details summary{cursor:pointer;font-size:12px}
.qa ol.src{font-size:12px;margin:6px 0 0 18px;padding:0}
.qa ol.src li{margin:4px 0}.qa ol.src li.cited{font-weight:500}
.qa ol.src .ex{opacity:.75}.qa .tools button{font-size:12px;margin-right:8px;cursor:pointer}
.spin{display:inline-block;width:10px;height:10px;border:2px solid #9aa9c2;border-top-color:transparent;
  border-radius:50%;animation:sp 1s linear infinite;margin-right:6px;vertical-align:-1px}
@keyframes sp{to{transform:rotate(360deg)}}
.ask button.att{padding:9px 12px;border-radius:8px;border:1px solid #c9d3e3;background:transparent;color:inherit;cursor:pointer}
.ask.drag{outline:2px dashed #3b6fd8;outline-offset:3px}
.files{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.fchip{font-size:12px;border:1px solid #c9d3e3;border-radius:8px;padding:4px 8px;max-width:100%}
.fchip.ready{border-color:#9fd3b0}.fchip.error{border-color:#f0a8a8}
.fchip .x{background:none;border:0;cursor:pointer;margin-left:6px;color:inherit;font-weight:700}
.fchip .m{opacity:.7}
@media (max-width:640px){.ask select,.ask textarea{min-width:0;width:100%}}
</style>"""

_ASK_JS = r"""<script>
(function(){
const KEY='landtek_console_thread_v1', MAX=25;
const $=s=>document.querySelector(s), thread=$('#thread'), form=$('#askf'), q=$('#q'), sc=$('#scope'), go=$('#go');
let items=[]; try{items=JSON.parse(localStorage.getItem(KEY)||'[]')}catch(e){items=[]}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(items.slice(-MAX)))}catch(e){}};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const scopeLabel=v=>{const o=[...sc.options].find(o=>o.value===v);return o?o.textContent.trim():v};
function md(text,id,n){
  let h=esc(text).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\[(\d{1,2})\]/g,(m,k)=>(+k>=1&&+k<=n)?`<a class="cite" href="#${id}-s${k}">[${k}]</a>`:m);
  const out=[];let ul=false;
  for(const ln of h.split(/\n/)){const t=ln.trim();
    if(/^[-•*]\s+/.test(t)){if(!ul){out.push('<ul>');ul=true}out.push('<li>'+t.replace(/^[-•*]\s+/,'')+'</li>')}
    else{if(ul){out.push('</ul>');ul=false}if(t)out.push('<p>'+t+'</p>')}}
  if(ul)out.push('</ul>');return out.join('');
}
function render(it){
  let el=document.getElementById(it.id);
  if(!el){el=document.createElement('div');el.className='qa';el.id=it.id;thread.prepend(el)}
  const r=it.r||{};let body='';
  if(!r.status||r.status==='running'){
    body=`<div class="meta"><span class="spin"></span>${esc(r.stage||'Starting…')} · ${r.elapsed||0}s</div>`;
  }else if(r.status==='error'){
    body=`<span class="tag err">Error</span> ${esc(r.error||'')}`+`<div class="tools"><button data-retry="${it.id}">Retry</button></div>`;
  }else{
    const n=(r.sources||[]).length, mode=r.mode;
    const tag=mode==='exact'?'<span class="tag exact">Exact lookup</span>'
      :mode==='grounded'?`<span class="tag grounded">Grounded answer · ${(r.checks&&r.checks.cited||[]).length}/${n} sources cited</span>`
      :'<span class="tag nf">Not in the record</span>';
    let chk='';
    if(mode==='grounded'&&r.checks){const c=r.checks,g=(c.gate||{}).verdict;
      chk+=g==='pass'?'<span class="tag ok">Answer gate: pass</span>':g==='fail'?'<span class="tag bad">Answer gate: FAIL</span>':'<span class="tag warn">Answer gate: '+esc(g||'n/a')+'</span>';
      chk+=c.n_uncited?`<span class="tag warn">${c.n_uncited} of ${c.n_sentences} sentences uncited — check them</span>`:'<span class="tag ok">every factual sentence cited</span>';
      if((c.bad_citations||[]).length)chk+='<span class="tag bad">cites a source that does not exist</span>';
      const gf=(c.gate||{}).fails||[]; if(gf.length)chk+='<div class="meta">'+gf.map(esc).join('<br>')+'</div>';}
    let src='';
    if(n){const lis=r.sources.map(s=>{
        const link=s.doc_id?` · <a href="/files/${s.doc_id}" target="_blank">open doc ${s.doc_id}</a>`:'';
        return `<li id="${it.id}-s${s.n}" class="${s.cited?'cited':''}">${s.cited?'✓ ':''}${esc(s.label)} <span class="ex">— ${esc([s.client,s.matter,s.date].filter(Boolean).join(' · '))}${link}<br>${esc((s.text||'').slice(0,320))}</span></li>`}).join('');
      src=`<details${mode==='grounded'?' open':''}><summary>Sources (${n}) — ✓ = cited in the answer</summary><ol class="src">${lis}</ol></details>`;}
    const deep=mode==='exact'?`<button data-deep="${it.id}">Go deeper</button>`:'';
    body=`${tag}<div class="a">${md(r.answer||'',it.id,n)}</div><div>${chk}</div>${src}
      <div class="meta">${esc(r.via||'')} · ${((r.ms||0)/1000).toFixed(1)}s</div>
      <div class="tools"><button data-copy="${it.id}">Copy</button>${deep}<button data-retry="${it.id}">Ask again</button></div>`;
  }
  const fl=(it.files||[]).length?`<span class="sc">📎 ${esc(it.files.join(', '))}</span>`:'';
  el.innerHTML=`<div class="q">${esc(it.q)}<span class="sc">${esc(scopeLabel(it.scope))}</span>${fl}</div>${body}`;
}
// ── attachments: read on the server, held 1 hour, never added to the record ──
const box=$('.ask'), fin=$('#fin'), flist=$('#files'); let files=[];
function drawFiles(){
  flist.innerHTML=files.map(f=>{
    const st=f.status==='ready'?`<span class="m"> · ${(f.chars||0).toLocaleString()} chars · ${esc(f.method||'')}${f.pages?' · '+f.pages+' p':''}</span>`
      :f.status==='error'?`<span class="m"> · ${esc(f.error||'failed')}</span>`
      :`<span class="m"><span class="spin"></span>${esc(f.stage||'Reading…')}</span>`;
    return `<span class="fchip ${f.status}">📎 ${esc(f.name)}${st}<button type="button" class="x" data-rm="${f.id}" title="Remove">×</button></span>`}).join('');
  const reading=files.some(f=>f.status==='reading');
  go.disabled=reading; q.placeholder=files.length?'Ask about the attached file — or leave empty for a summary and how it relates to the record':PH;
}
async function attach(file){
  const tmp={id:'t'+Math.random().toString(36).slice(2),name:file.name,status:'reading',stage:'Uploading…'};
  files.push(tmp);drawFiles();
  if(file.size>45*1024*1024){Object.assign(tmp,{status:'error',error:'over 45 MB'});drawFiles();return}
  try{
    const fd=new FormData();fd.append('file',file);
    const res=await fetch('/ops/console/ask/file',{method:'POST',body:fd});
    const j=await res.json().catch(()=>({error:'upload rejected ('+res.status+')'}));
    if(!j.id){Object.assign(tmp,{status:'error',error:j.error||'upload failed'});drawFiles();return}
    tmp.id=j.id;drawFiles();
    for(;;){await new Promise(r=>setTimeout(r,1200));
      const p=await (await fetch('/ops/console/ask/file/'+j.id)).json();Object.assign(tmp,p);drawFiles();
      if(p.status!=='reading')break;}
  }catch(e){Object.assign(tmp,{status:'error',error:String(e)});drawFiles()}
}
const PH=q.placeholder;
$('#att').addEventListener('click',()=>fin.click());
fin.addEventListener('change',()=>{for(const f of fin.files)attach(f);fin.value=''});
['dragenter','dragover'].forEach(ev=>box.addEventListener(ev,e=>{e.preventDefault();box.classList.add('drag')}));
['dragleave','drop'].forEach(ev=>box.addEventListener(ev,e=>{e.preventDefault();box.classList.remove('drag')}));
box.addEventListener('drop',e=>{for(const f of e.dataTransfer.files)attach(f)});
async function ask(text,scope,deep,fl){
  fl=fl||[];
  const it={id:'q'+Date.now().toString(36),q:text,scope,files:fl.map(f=>f.name),r:{status:'running',stage:'Starting…'}};
  items.push(it);render(it);go.disabled=true;
  try{
    const res=await fetch('/ops/console/ask/',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({q:text,scope,deep:!!deep,files:fl.map(f=>f.id)})});
    const j=await res.json(); if(!j.job_id){it.r={status:'error',error:j.error||'could not start'};render(it);return}
    for(;;){await new Promise(r=>setTimeout(r,1500));
      const p=await fetch('/ops/console/ask/'+j.job_id);const pj=await p.json();it.r=pj;render(it);
      if(pj.status!=='running')break;}
  }catch(e){it.r={status:'error',error:String(e)};render(it)}
  finally{go.disabled=files.some(f=>f.status==='reading');save()}
}
const ready=()=>files.filter(f=>f.status==='ready').map(f=>({id:f.id,name:f.name}));
form.addEventListener('submit',e=>{e.preventDefault();const fl=ready();let t=q.value.trim();
  if(!t&&fl.length)t='Summarize the attached file and how it relates to what the record shows.';
  if(t.length<3)return;q.value='';ask(t,sc.value,false,fl)});
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();form.requestSubmit()}});
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.ex){sc.value=b.dataset.scope;ask(b.dataset.ex,b.dataset.scope,false)}
  const find=id=>items.find(x=>x.id===id);
  if(b.dataset.rm){files=files.filter(f=>f.id!==b.dataset.rm);drawFiles()}
  const again=it=>(it.files||[]).length?ready().filter(f=>it.files.includes(f.name)):[];
  if(b.dataset.retry){const it=find(b.dataset.retry);if(it)ask(it.q,it.scope,false,again(it))}
  if(b.dataset.deep){const it=find(b.dataset.deep);if(it)ask(it.q,it.scope,true)}
  if(b.dataset.copy){const it=find(b.dataset.copy);if(it&&it.r)navigator.clipboard.writeText(it.r.answer||'')}
  if(b.id==='clear'){items=[];save();thread.innerHTML=''}});
for(const it of items){if(it.r&&it.r.status==='running')it.r={status:'error',error:'Interrupted — ask again.'};render(it)}
})();
</script>"""


def _ask_panel(cur) -> str:
    try:
        import console_ask as CA
        opts = CA.scopes(cur)
    except Exception as e:
        return f"<div class='card alert-warn'>Ask is unavailable: {_esc(type(e).__name__)}</div>"
    o_top = "".join(f"<option value='{_esc(o['value'])}'{' selected' if o['value'] == 'client:MWK-001' else ''}>"
                    f"{_esc(o['label'])}</option>" for o in opts if not o["group"])
    groups = {}
    for o in opts:
        if o["group"]:
            groups.setdefault(o["group"], []).append(o)
    o_m = "".join(f"<optgroup label='Matters — {_esc(g)}'>" + "".join(
        f"<option value='{_esc(o['value'])}'>{_esc(o['label'])}</option>" for o in lst) + "</optgroup>"
        for g, lst in groups.items())
    chips = "".join(f"<button type='button' class='chip' data-ex='{_esc(q)}' data-scope='{_esc(s)}'>{_esc(q)}</button>"
                    for s, q in EXAMPLES)
    return (_ASK_CSS +
            "<div class='ask'><form id='askf'>"
            f"<select id='scope' aria-label='Scope'>{o_top}{o_m}</select>"
            "<textarea id='q' placeholder='Ask anything — a case, a title, a person, a deadline, what to do next… "
            "(Enter to ask, Shift+Enter for a new line)' aria-label='Question'></textarea>"
            "<button class='att' id='att' type='button' title='Attach a file (or drop it here)'>📎 Attach</button>"
            "<input type='file' id='fin' multiple hidden "
            "accept='.pdf,.docx,.txt,.md,.csv,.png,.jpg,.jpeg,.tif,.tiff,.webp'>"
            "<button class='go' id='go' type='submit'>Ask</button></form>"
            "<div class='files' id='files'></div>"
            f"<div class='chips'>{chips}</div>"
            "<div class='bar'><span>Answers come only from LandTek's record. Exact lookups first; otherwise a cited "
            "answer written on your local model ($0) and checked by Leo's answer gate. Nothing is sent to anyone. "
            "Attached files (PDF, Word, text, photos; drop them here) are read on the server for your question only "
            "and are NOT added to the record.</span>"
            "<button id='clear' type='button'>Clear thread</button></div>"
            "<div id='thread'></div></div>" + _ASK_JS)


# ───────────────────────────── page ─────────────────────────────

@bp.route("/", methods=["GET"])
def console():
    conn = _db()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        ask = _ask_panel(cur)
        stack = _scorecard(cur, conn)
        product = _product(cur, conn)
    finally:
        cur.close()
        conn.close()

    body = (
        "<h1>Console</h1><p class='muted'>Ask LandTek anything, see the product as clients see it, and check "
        "whether the machine is honest. Every number is live (MASTER_PLAN §0).</p>"
        + ask +
        "<div class='section-title'>Stack — the §0 scorecard</div>" + stack +
        "<div class='section-title'>Machine health</div>" + _health() +
        "<div class='section-title'>Product — each client as they see it</div>" + product
    )
    return _layout("Console", body, active="console")
