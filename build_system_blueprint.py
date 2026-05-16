#!/usr/bin/env python3
"""Generate the complete LandTek Leo system blueprint PDF.

A from-scratch buildable architecture document covering:
  - Mission + goals + principles
  - Component architecture
  - Data model
  - Capabilities
  - Autonomous loops
  - Multi-channel reach
  - Truth-negotiation discipline
  - Meta-agent + back-test
  - Filing structure
  - Current state metrics
  - Gap analysis + roadmap

Output: PDF (investor-grade)
"""
import argparse, os, sys
from datetime import datetime, timezone
import psycopg2, psycopg2.extras
from weasyprint import HTML

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
MEMORY_DIR = "/root/.claude/projects/-root-landtek/memory"


def fetch(cur, sql, params=()):
    cur.execute(sql, params); return cur.fetchall()


def fmt(n):
    try: return f"{int(n):,}"
    except: return str(n)


def get_metrics(cur):
    m = {}
    cur.execute("SELECT count(*) AS n FROM documents"); m["docs_total"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM documents WHERE extracted_text IS NOT NULL AND length(extracted_text)>=200"); m["docs_extracted"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM documents WHERE case_file IS NOT NULL AND case_file<>''"); m["docs_correlated"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM documents WHERE execution_status IS NOT NULL AND execution_status<>'unknown'"); m["docs_classified"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM documents WHERE canonical_filename IS NOT NULL"); m["docs_canonical"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM matters WHERE status='active'"); m["matters_active"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM truth_negotiations"); m["verifications"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM gmail_messages"); m["emails"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM transactions"); m["transactions"] = cur.fetchone()["n"]
    cur.execute("SELECT to_char(sum(amount),'FM999,999,999') AS s FROM transactions WHERE direction='debit'"); m["total_paid"] = cur.fetchone()["s"]
    cur.execute("SELECT count(DISTINCT asset_title) AS n FROM asset_valuations WHERE is_active_tax_dec=true"); m["active_tax_decs"] = cur.fetchone()["n"]
    cur.execute("SELECT to_char(sum(market_price_value),'FM999,999,999,999') AS s FROM asset_current_valuation"); m["portfolio_market"] = cur.fetchone()["s"]
    cur.execute("SELECT count(*) AS n FROM asset_risks"); m["risks"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM firm_goals WHERE status='active'"); m["firm_goals"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM arta_cases"); m["arta_cases"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM channels WHERE active"); m["channels_active"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM channels WHERE NOT active"); m["channels_pending"] = cur.fetchone()["n"]
    cur.execute("SELECT count(*) AS n FROM back_test_suite WHERE active"); m["backtests"] = cur.fetchone()["n"]
    return m


def get_memory_principles():
    """Return list of (title, slug, summary) from feedback memories."""
    import os, re, glob
    principles = []
    for f in sorted(glob.glob(f"{MEMORY_DIR}/feedback_*.md")):
        with open(f) as fp:
            text = fp.read()
        slug = os.path.basename(f).replace(".md", "")
        m = re.search(r'description:\s*"([^"]+)"', text)
        desc = m.group(1) if m else ""
        # Pull the H1 line for title
        title = slug.replace("feedback_", "").replace("_", " ").title()
        principles.append((title, slug, desc[:240]))
    return principles


CSS = """<style>
@page { size: A4; margin: 18mm 14mm 18mm 14mm;
        @bottom-center { content: "LandTek Leo Platform · System Blueprint · " counter(page) " of " counter(pages); color: #888; font-size: 8.5pt; } }
body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; font-size: 10pt; line-height: 1.5; }
h1 { color: #0a3d62; font-size: 26pt; margin: 0 0 4px 0; letter-spacing: -0.5px; }
h2 { color: #0a3d62; font-size: 16pt; border-bottom: 2px solid #0a3d62; padding-bottom: 4px; margin-top: 28px; margin-bottom: 12px; }
h3 { color: #2c3e50; font-size: 12pt; margin-top: 16px; margin-bottom: 6px; }
h4 { color: #2c3e50; font-size: 10.5pt; margin-top: 12px; margin-bottom: 4px; font-weight: 600; }
.subtitle { color: #7f8c8d; font-size: 11pt; margin-bottom: 24px; }
.tagline { font-style: italic; color: #34495e; margin: 8px 0 20px 0; font-size: 11pt; padding-left: 12px; border-left: 3px solid #0a3d62; }
.principle { background: #f5f8fb; padding: 8px 12px; margin: 6px 0; border-left: 3px solid #2c3e50; font-size: 9.5pt; }
.principle .name { font-weight: 600; color: #0a3d62; }
table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 9pt; }
th { background: #e8eef4; text-align: left; padding: 6px 8px; border-bottom: 1.5px solid #0a3d62; font-weight: 600; }
td { padding: 5px 8px; border-bottom: 1px solid #eee; vertical-align: top; }
.num { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
.tag { display: inline-block; padding: 1px 6px; background: #e8eef4; color: #0a3d62; border-radius: 3px; font-size: 8.5pt; font-family: 'Courier New', monospace; }
.stat { padding: 10px 14px; background: #f5f8fb; border-left: 3px solid #0a3d62; margin: 6px 4px 6px 0; display: inline-block; min-width: 30%; vertical-align: top; }
.stat-label { color: #586e7a; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-size: 15pt; font-weight: 600; color: #0a3d62; }
.stat-sub { font-size: 8pt; color: #95a5a6; margin-top: 2px; }
.pagebreak { page-break-before: always; }
.callout { background: #fff8e7; border-left: 3px solid #e67e22; padding: 8px 12px; margin: 10px 0; font-size: 9.5pt; }
.box { background: #f5f8fb; border: 1px solid #c5d3e0; padding: 12px; border-radius: 4px; margin: 8px 0; font-size: 9.5pt; }
.flow-step { padding: 8px 12px; margin: 4px 0; background: #fff; border: 1.5px solid #0a3d62; border-radius: 4px; }
.flow-step .step-num { color: #0a3d62; font-weight: 700; margin-right: 8px; }
ul, ol { margin: 4px 0; padding-left: 22px; }
li { margin: 2px 0; }
code { background: #f5f8fb; padding: 1px 4px; border-radius: 3px; font-family: 'Courier New', monospace; font-size: 9pt; }
.toc { background: #f5f8fb; padding: 12px 18px; border-left: 4px solid #0a3d62; }
.toc ol { list-style: decimal; }
.toc li { margin: 3px 0; font-size: 10pt; }
.kpi-good { color: #27ae60; font-weight: 600; }
.kpi-warn { color: #e67e22; font-weight: 600; }
.kpi-bad  { color: #c0392b; font-weight: 600; }
</style>"""


def build_html(cur):
    m = get_metrics(cur)
    principles = get_memory_principles()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pct = lambda a, b: f"{a*100//b}%" if b else "—"

    h = f"""<!DOCTYPE html><html><head>{CSS}</head><body>

<h1>LandTek Leo Platform</h1>
<div class="subtitle">System Blueprint — buildable-from-scratch architecture document</div>
<div class="tagline">"Evidence-grade legal-ops AI for Philippine property law — truth-negotiated retrieval, procedural-stage awareness, financial integrity, and continuous self-audit."</div>

<div class="toc">
<b>Contents</b>
<ol>
  <li>Mission &amp; Strategic Goals</li>
  <li>First Principles (the immutable rules)</li>
  <li>System Architecture</li>
  <li>Data Model</li>
  <li>The Truth-Negotiation Engine (keystone)</li>
  <li>Procedural-Stage Awareness</li>
  <li>Agency Layer — Deadlines + Goal Accelerator</li>
  <li>Financial Layer</li>
  <li>Asset Valuation, Risk &amp; Opportunity</li>
  <li>Multi-Channel Reach + Onboarding</li>
  <li>Meta-Agent — Systems Analyzer &amp; Back-Test</li>
  <li>Filing System — Digital Mirror of Physical</li>
  <li>Current State Metrics</li>
  <li>Gap Analysis</li>
  <li>Roadmap</li>
</ol>
</div>

<!-- ─────────────────── 1. MISSION ─────────────────── -->
<div class="pagebreak"></div>
<h2>1. Mission &amp; Strategic Goals</h2>
<div class="callout">
<b>Leo's mission:</b> never miss a deadline, expedite every process toward our clients' goals, and proactively push both client agendas AND Landtek's firm-level agenda forward — without being asked.
</div>

<h3>Three operating layers</h3>
<table>
<tr><th>Layer</th><th>What it does</th><th>Why it matters</th></tr>
<tr><td><b>Client agenda</b></td><td>Per-case goals (e.g., recover T-52540 from Balane)</td><td>Why each client hires Landtek</td></tr>
<tr><td><b>Firm agenda</b></td><td>Landtek's strategic objectives (diaspora market, licensable platform, capital attraction)</td><td>Why Landtek exists beyond any one client</td></tr>
<tr><td><b>Leo platform agenda</b></td><td>Build the truth-graded RAG that becomes a licensable product</td><td>Recurring revenue beyond legal fees · investor-grade asset</td></tr>
</table>

<h3>Strategic goals (firm-level, currently active)</h3>
<table>
<tr><th>Goal</th><th>Why</th><th>Target</th></tr>
<tr><td>Win Civil Case 26-360</td><td>Demonstrates accion reinvindicatoria mastery against fraudulent title chains</td><td>2027-06-30</td></tr>
<tr><td>Diaspora-market dominance</td><td>US-based heirs of PH land = under-served niche</td><td>2027-12-31</td></tr>
<tr><td>Camarines Norte territory</td><td>Deep title-chain coverage</td><td>2026-12-31</td></tr>
<tr><td>Leo as licensable product</td><td>Recurring revenue beyond legal fees</td><td>2027-06-30</td></tr>
<tr><td>Attract outside capital</td><td>Investor-grade reports demonstrate scalability</td><td>2026-12-31</td></tr>
<tr><td>Evidence-grade reputation</td><td>Every claim cited; every doc provenance-tagged</td><td>2027-12-31</td></tr>
<tr><td>Sustainable monthly revenue</td><td>Manifest money to keep Leo alive</td><td>2026-09-30</td></tr>
</table>

<!-- ─────────────────── 2. PRINCIPLES ─────────────────── -->
<div class="pagebreak"></div>
<h2>2. First Principles</h2>
<div class="subtitle">{len(principles)} immutable rules — saved to permanent memory, enforced by all subsystems.</div>
"""
    for title, slug, desc in principles:
        h += f'<div class="principle"><span class="name">{title.replace("Feedback ", "")}</span> — {desc}</div>'

    # ─────────── 3. ARCHITECTURE ───────────
    h += """
<div class="pagebreak"></div>
<h2>3. System Architecture</h2>

<h3>Component layout</h3>
<div class="box">
<pre style="font-family: 'Courier New', monospace; font-size: 9pt; line-height: 1.4; margin: 0">
   ┌───────────────── INPUTS ─────────────────┐
   │ Telegram · WhatsApp · Web · Email · SMS  │
   │ Voice (Twilio) · REST API · Drive · Gmail │
   └────────────────────┬─────────────────────┘
                        │
            ┌───────────▼────────────┐
            │  Onboarding gate +     │  ← unknown senders run state machine
            │  Whitelist / approval  │
            └───────────┬────────────┘
                        │ (if approved)
            ┌───────────▼────────────┐
            │   n8n workflow         │   ← orchestrates AI Agent + slash router
            │   "Leos Workflow"      │
            └───────────┬────────────┘
                        │
        ┌───────────────▼──────────────────────┐
        │  PRIMARY LEO (Claude Sonnet/Haiku)   │
        │  Backed by:                          │
        │   • truth_negotiator (4-dir probe)   │
        │   • classifiers (exec_status,        │
        │     case_stage, case_correlator)     │
        │   • goal_accelerator                 │
        └───────────────┬──────────────────────┘
                        │
            ┌───────────▼────────────┐
            │  leo_tools Flask API   │   ← /api/* + /api/v1/leo/*
            │  (port 8765)           │
            └───────────┬────────────┘
                        │
            ┌───────────▼────────────┐
            │  Postgres + Qdrant     │   ← source of truth
            └────────────────────────┘
                  ▲             ▲
                  │             │ HEARTBEATS
   ┌──────────────┴───┐    ┌────┴──────────────────────┐
   │ AUTONOMOUS LOOPS │    │  META-AGENT               │
   │ • watchdog 60s   │    │  Systems Analyzer (1h)    │
   │ • deadline 15m   │    │  • audits coverage gaps   │
   │ • gmail 15m      │    │  • back-tests truth_neg.  │
   │ • drive 30m      │    │  • auto-remediates        │
   │ • orchestr. 30m  │    │  • DMs Jonathan on issues │
   │ • goal_accel 1d  │    └───────────────────────────┘
   └──────────────────┘
</pre>
</div>

<h3>Core technology stack</h3>
<table>
<tr><th>Component</th><th>Tech</th><th>Purpose</th></tr>
<tr><td>Orchestration</td><td>n8n v2.16 (Docker)</td><td>Workflow engine — Telegram trigger → AI Agent → tool calls → response</td></tr>
<tr><td>Primary LLM (synthesis)</td><td>Claude Sonnet 4.5</td><td>Case reports, complex reasoning</td></tr>
<tr><td>Per-doc LLM (extraction)</td><td>Claude Haiku 4.5</td><td>Tax doc extraction, case-stage detection, payment receipts</td></tr>
<tr><td>Vision / OCR</td><td>Gemini 2.5 Flash + PyMuPDF</td><td>PDF text extraction</td></tr>
<tr><td>Vector index</td><td>Qdrant (landtek_documents, landtek_conversations)</td><td>Semantic retrieval</td></tr>
<tr><td>Source-of-truth DB</td><td>PostgreSQL (Docker, container n8n-postgres-1)</td><td>All metadata, transactions, relationships</td></tr>
<tr><td>File storage</td><td>Google Drive (service-account) + local /root/landtek/uploads</td><td>Master file repository, dedup-hashed</td></tr>
<tr><td>Scheduler</td><td>systemd timers (six active loops)</td><td>Autonomous, no external cron deps</td></tr>
<tr><td>Reports</td><td>weasyprint (HTML → PDF)</td><td>Investor-grade PDF rendering</td></tr>
<tr><td>Memory</td><td>Markdown files in ~/.claude/projects/-root-landtek/memory/</td><td>Principles + project context across sessions</td></tr>
</table>
"""

    # ─────────── 4. DATA MODEL ───────────
    h += """
<div class="pagebreak"></div>
<h2>4. Data Model</h2>

<p>The schema is organized in seven semantic layers. Every table cites a source — provenance is enforced at every join.</p>

<h3>Layer A — Documents &amp; Evidence</h3>
<table>
<tr><th>Table</th><th>Rows</th><th>Purpose</th></tr>
<tr><td><code>documents</code></td><td>688+</td><td>Every file Leo knows about: drive_file_id, content_hash, extracted_text, canonical_filename, classification, execution_status</td></tr>
<tr><td><code>extraction_chunks</code></td><td>—</td><td>Per-field RAG chunks for embedding</td></tr>
<tr><td><code>document_entities</code></td><td>—</td><td>Entity-doc many-to-many</td></tr>
<tr><td><code>extraction_runs</code></td><td>331+</td><td>Per-doc extraction history</td></tr>
<tr><td><code>fraud_indicators</code></td><td>6</td><td>Visual anomalies on title docs</td></tr>
<tr><td><code>title_tax_links</code></td><td>5+</td><td>TCT ↔ ARP many-to-many linkage</td></tr>
<tr><td><code>duplicate_groups</code> + members</td><td>31 groups</td><td>Exact/near/content dedup tracking</td></tr>
</table>

<h3>Layer B — Cases, Matters &amp; Procedure</h3>
<table>
<tr><th>Table</th><th>Purpose</th></tr>
<tr><td><code>clients</code></td><td>The actual clients of Landtek</td></tr>
<tr><td><code>matters</code></td><td>Per-client legal matters · current_stage, next_event, next_deadline</td></tr>
<tr><td><code>case_stage_transitions</code></td><td>Versioned history of procedural stage changes per matter</td></tr>
<tr><td><code>case_deadlines</code></td><td>Procedural and admin deadlines per case</td></tr>
<tr><td><code>case_keywords</code></td><td>Keyword scoring weights for orphan-doc case correlation</td></tr>
<tr><td><code>arta_cases</code></td><td>ARTA inventory — 9 distinct CTN numbers discovered</td></tr>
<tr><td><code>title_chain</code> + <code>title_transfers</code></td><td>Title derivation graph + transfer events</td></tr>
<tr><td><code>titles</code></td><td>TCT/OCT records with lifecycle_status (active/cancelled/contested)</td></tr>
<tr><td><code>title_matter_links</code></td><td>Title → matter relationship (subject/evidence/forthcoming)</td></tr>
</table>

<h3>Layer C — Truth, Goals &amp; Agency</h3>
<table>
<tr><th>Table</th><th>Purpose</th></tr>
<tr><td><code>truth_negotiations</code></td><td>Audit trail of every verification — claim, verdict, citation_tag, challenger response</td></tr>
<tr><td><code>client_goals</code></td><td>Per-client goals with priority + progress_pct</td></tr>
<tr><td><code>landtek_duties</code></td><td>Landtek's obligations per goal</td></tr>
<tr><td><code>bottlenecks</code></td><td>What's blocking progress · severity + mitigation_status</td></tr>
<tr><td><code>firm_goals</code></td><td>Landtek strategic agenda</td></tr>
<tr><td><code>proposed_actions</code></td><td>goal_accelerator output · accept/decline tracking</td></tr>
<tr><td><code>deadline_alerts</code></td><td>T-14/T-7/T-3/T-1/T-0/overdue audit trail</td></tr>
</table>

<h3>Layer D — Financial</h3>
<table>
<tr><th>Table</th><th>Purpose</th></tr>
<tr><td><code>accounts</code></td><td>Chart of accounts · firm + per-client</td></tr>
<tr><td><code>transactions</code></td><td>Every money event with source_doc citation</td></tr>
<tr><td><code>monthly_overhead</code></td><td>Recurring obligations · firm + client</td></tr>
<tr><td><code>value_extraction_events</code></td><td>Sale, lease, settlement, recovery events</td></tr>
<tr><td><code>asset_valuations</code></td><td>Per-asset time-series · assessed, zonal, MPV, intrinsic, opportunity_score</td></tr>
<tr><td><code>asset_risks</code></td><td>Per-asset risk profile · severity + mitigation</td></tr>
<tr><td><code>asset_development_plans</code></td><td>Playbook per asset · tied to client + firm goals</td></tr>
<tr><td><code>market_observations</code></td><td>Comparables + distressed-sale signals</td></tr>
<tr><td><code>leo_operational_costs</code></td><td>Per-day Leo infra spend</td></tr>
</table>

<h3>Layer E — Communications &amp; Channels</h3>
<table>
<tr><th>Table</th><th>Purpose</th></tr>
<tr><td><code>channels</code></td><td>Registered I/O channels (telegram, whatsapp, web, email, sms, voice, api)</td></tr>
<tr><td><code>channel_users</code></td><td>Per-channel user identity · onboarding_state · approved_role · scope</td></tr>
<tr><td><code>channel_messages</code></td><td>Every inbound/outbound message · audit + content</td></tr>
<tr><td><code>channel_audit</code></td><td>Auth, rate-limit, delivery audit</td></tr>
<tr><td><code>gmail_messages</code></td><td>Email ingested · classified · case-correlated</td></tr>
<tr><td><code>pending_questions</code></td><td>Open clarification questions for Jonathan</td></tr>
<tr><td><code>conversation_context</code></td><td>Back-channel context Jonathan adds for Leo</td></tr>
<tr><td><code>api_keys</code></td><td>Licensable-product key registry</td></tr>
</table>

<h3>Layer F — Meta &amp; Audit</h3>
<table>
<tr><th>Table</th><th>Purpose</th></tr>
<tr><td><code>system_heartbeat</code></td><td>Every cron emits a heartbeat row on each run</td></tr>
<tr><td><code>system_analyzer_findings</code></td><td>Coverage gaps + staleness + verification drift</td></tr>
<tr><td><code>back_test_suite</code></td><td>Known-correct truth_negotiator claims</td></tr>
<tr><td><code>back_test_runs</code></td><td>Historical pass/fail per test</td></tr>
<tr><td><code>audit_events</code></td><td>Generic audit log · rename, dedup, access, integrity</td></tr>
</table>
"""

    # ─────────── 5. TRUTH NEGOTIATION ───────────
    h += """
<div class="pagebreak"></div>
<h2>5. The Truth-Negotiation Engine (keystone)</h2>

<p>The fundamental discipline: no claim leaves Leo without a citation, no draft is treated as fact, no English-only search misses Filipino testimony.</p>

<h3>4-direction probe</h3>
<div class="flow-step"><span class="step-num">A.</span> <b>Entity-anchor grep</b> — for each entity in the claim (TCT, docket, person), find every doc that contains it.</div>
<div class="flow-step"><span class="step-num">B.</span> <b>Phrase-grep</b> — search the most specific 4-6-word window of the claim across the corpus.</div>
<div class="flow-step"><span class="step-num">C.</span> <b>Graph cross-reference</b> — for TCTs, traverse <code>title_chain</code> + <code>title_transfers</code> to find related docs.</div>
<div class="flow-step"><span class="step-num">D.</span> <b>Provenance check</b> — every cited doc carries its execution_status; the citation rule reads this.</div>
<div class="flow-step"><span class="step-num">E.</span> <b>Bilingual concept probe</b> (added after Cesar-death miss) — concepts in claim trigger search across English AND Filipino synonyms with HIGH-precision Filipino terms weighted 5×.</div>

<h3>Citation tier rules (execution_status driven)</h3>
<table>
<tr><th>Tier</th><th>Status</th><th>Citation policy</th></tr>
<tr><td><span class="tag">V·N</span></td><td>executed_notarized</td><td>Full legal force</td></tr>
<tr><td><span class="tag">V·F</span></td><td>executed_filed</td><td>Full legal force</td></tr>
<tr><td><span class="tag">V·G</span></td><td>government_issued</td><td>Full legal force</td></tr>
<tr><td><span class="tag">V·S</span></td><td>executed_signed_only</td><td>Citable with caveat</td></tr>
<tr><td><span class="tag">V·E</span></td><td>email_sent/received</td><td>Citable for fact-of-communication ONLY; not for content truth</td></tr>
<tr><td><span class="tag">D</span></td><td>draft_unsigned</td><td><b>NEVER citable as fact</b></td></tr>
<tr><td><span class="tag">?</span></td><td>template / unknown</td><td>Not citable</td></tr>
</table>

<h3>Adversarial challenger</h3>
<p>After fact-backers are gathered, a SEPARATE Claude Haiku instance is told to <b>disprove</b> the claim from the same evidence. The challenger reads:
the claim, the top-10 evidence excerpts (ranked by execution_status + classification weight), and tries to find:
contradiction, evidence-of-the-opposite, unsupported leaps. Verdict outputs:</p>
<ul>
<li><b>verified</b> — ≥1 fact-backer, no contradictions, challenger agrees</li>
<li><b>refuted</b> — challenger found contradicting evidence</li>
<li><b>uncertain</b> — only communication evidence (email) or single weak source</li>
<li><b>unsourced</b> — no evidence found</li>
<li><b>uncitable_draft</b> — only evidence is draft_unsigned</li>
</ul>
"""

    # ─────────── 6-11 (compressed) ───────────
    h += """
<div class="pagebreak"></div>
<h2>6. Procedural-Stage Awareness</h2>
<p>Every active matter has a <code>current_stage</code> in PH civil procedure (18 stages: pre_filing → complaint_filed → … → decision_rendered → final). The classifier reads filings + Notices to detect transitions. Civil Case 26-360 is currently at <b>pretrial_pending</b> (per Notice doc #392).</p>
<p>Each stage triggers expected next events (next_event, next_deadline) which feed the deadline sentinel.</p>

<h2>7. Agency Layer — Deadlines + Goal Accelerator</h2>
<h3>deadline_sentinel</h3>
<p>Runs every 15 minutes via systemd. For each active case_deadline:</p>
<ul>
<li>Days-until → tier: T-14 / T-7 / T-3 / T-1 / T-0 / overdue</li>
<li>If tier reminder not yet sent → fire Telegram alert + log to <code>deadline_alerts</code></li>
<li>Overdue: pulse every 4h with bottleneck context</li>
<li>Audit trail proves Leo flagged it at every step</li>
</ul>

<h3>goal_accelerator</h3>
<p>Runs daily at 00:00 UTC (8 AM Manila). For each active case + firm-level goals:</p>
<ul>
<li>Claude Haiku proposes 1-3 concrete actions per case + 1-2 firm-level actions</li>
<li>Each action backed by truth_negotiator (no hallucinated suggestions)</li>
<li>Inserts into <code>proposed_actions</code> table</li>
<li>Top 5 picks DM'd to Jonathan with one-tap accept/decline</li>
</ul>

<h2>8. Financial Layer</h2>

<table>
<tr><th>Component</th><th>What it tracks</th></tr>
<tr><td>Chart of accounts (26 rows)</td><td>Firm revenue/expense/asset accounts + per-client buckets</td></tr>
<tr><td>Transactions (174+)</td><td>Every payment with source_doc citation (RPT, filing, registration, etc.)</td></tr>
<tr><td>Monthly overhead</td><td>Recurring obligations · firm + per-case · auto-updated when ≥2 bills from same vendor</td></tr>
<tr><td>Value extraction events</td><td>Sale proceeds, lease income, settlement recoveries (future, when matters resolve)</td></tr>
<tr><td>Leo operational costs</td><td>Per-day Anthropic/Gemini/server spend</td></tr>
</table>

<h3>Investor-grade output</h3>
<ul>
<li><code>/cashflow &lt;case&gt;</code> — per-client cash flow PDF</li>
<li><code>/pnl</code> — firm trailing-12mo P&amp;L PDF</li>
<li><code>/valuation &lt;asset&gt;</code> — per-asset valuation memo</li>
<li><code>/pack &lt;case&gt;</code> — bundled financial pack (cashflow + P&amp;L + top valuations)</li>
</ul>
"""

    h += """
<div class="pagebreak"></div>
<h2>9. Asset Valuation, Risk &amp; Opportunity</h2>

<h3>Per-asset record (versioned, append-only)</h3>
<table>
<tr><th>Dimension</th><th>Captured</th></tr>
<tr><td>Identifiers</td><td>TCT/OCT no, ARP no, PIN, PSD plan, lot code</td></tr>
<tr><td>Valuations</td><td>Assessed (LGU), Zonal (BIR), Market Price (actual), Appraised (bank/independent), Acquisition Cost</td></tr>
<tr><td>Physical</td><td>Area sqm, current_use, highest_best_use, location</td></tr>
<tr><td>Legal</td><td>Lifecycle status (active/cancelled/contested), tax_status, liens/encumbrances</td></tr>
<tr><td>Risk</td><td>severity, likelihood_pct, expected_loss, mitigation_strategy, mitigation_cost</td></tr>
<tr><td>Strategic</td><td>intrinsic_value (market − Σ risk-weighted losses), opportunity_score</td></tr>
</table>

<h3>The "low-hanging-fruit" engine</h3>
<p>When (intrinsic_value &gt; 1.4 × actual_market_price) AND (mitigation_strategy known) AND (mitigation_cost &lt; spread) → flag as opportunity. Surfaces in reports as buy/sell candidates.</p>
<p>This is Landtek's competitive moat: the accumulated risk database grows with every case. Investors fund firms that spot opportunities others can't.</p>

<h2>10. Multi-Channel Reach + Onboarding</h2>

<h3>Channels registered</h3>
<table>
<tr><th>Channel</th><th>Status</th><th>Provider</th></tr>
<tr><td>Telegram</td><td>ACTIVE</td><td>@LeoLandtekBot (Bot API)</td></tr>
<tr><td>WhatsApp Business</td><td>pending</td><td>Meta / 360dialog (awaiting WABA token)</td></tr>
<tr><td>Web chat widget</td><td>pending</td><td>Embed on landtek.com</td></tr>
<tr><td>Email reply</td><td>pending</td><td>Gmail API send (refresh token wired)</td></tr>
<tr><td>SMS</td><td>pending</td><td>Twilio / Globe / Smart</td></tr>
<tr><td>Voice (phone Leo)</td><td>pending</td><td>Twilio Voice + STT/TTS</td></tr>
<tr><td>Slack</td><td>pending</td><td>Slack Bolt</td></tr>
<tr><td>Public REST API</td><td>ACTIVE (with API keys)</td><td>The licensable product</td></tr>
</table>

<h3>Onboarding state machine (for unknown senders)</h3>
<div class="flow-step"><span class="step-num">1.</span> Unknown sender → CREATE channel_users row with state=<code>awaiting_intro</code> → Leo greets in Filipino+English asking name + intent</div>
<div class="flow-step"><span class="step-num">2.</span> Sender replies with name + intent → state=<code>awaiting_classification</code> → Leo asks for case/matter details</div>
<div class="flow-step"><span class="step-num">3.</span> Sender details captured → state=<code>awaiting_jonathan_approval</code> → Leo DMs Jonathan with action commands</div>
<div class="flow-step"><span class="step-num">4.</span> Jonathan runs <code>/approve &lt;id&gt; &lt;role&gt;</code> → state=<code>approved</code> → AI Agent engages with scoped access</div>
"""

    h += """
<div class="pagebreak"></div>
<h2>11. Meta-Agent — Systems Analyzer &amp; Back-Test</h2>

<p>The principle: <b>Jonathan should never be the first to spot system drift.</b></p>

<h3>Hourly audit dimensions</h3>
<table>
<tr><th>Dimension</th><th>Signal</th><th>Threshold</th></tr>
<tr><td>Data freshness</td><td>System heartbeats from every cron</td><td>&gt;1 hour gap = staleness</td></tr>
<tr><td>Coverage</td><td>% case-correlated, exec-classified</td><td>&lt;80% on any axis</td></tr>
<tr><td>Drive ingestion</td><td>Drive total vs ingested count</td><td>&gt;50 unsynced files</td></tr>
<tr><td>Deadline integrity</td><td>Deadlines within 7d lacking alerts</td><td>any</td></tr>
<tr><td>Bottleneck staleness</td><td>Bottlenecks open &gt;14d, no progress</td><td>any</td></tr>
<tr><td>Verification discipline</td><td>Back-test pass rate</td><td>&lt;90%</td></tr>
<tr><td>Onboarding queue</td><td>Pending approvals &gt;4h old</td><td>any</td></tr>
</table>

<h3>Back-test suite</h3>
<p>5 seeded tests of known-correct truth_negotiator claims (e.g., "Cesar is dead → VERIFIED from doc 407").
Run hourly. Any drift → DM Jonathan + create remediation finding.</p>

<h3>Auto-remediation</h3>
<p>Findings flagged <code>auto_remediable=true</code> trigger the relevant fix script directly:</p>
<ul>
<li>Stale Gmail → invoke <code>gmail_watcher.py</code></li>
<li>Stale Drive → invoke <code>drive_backfill.py</code></li>
<li>Uncorrelated docs → invoke <code>correlate_orphan_cases.py</code></li>
<li>Unclassified exec status → invoke <code>classify_execution_status.py</code></li>
</ul>

<h2>12. Filing System — Digital Mirror of Physical</h2>

<p>The standard: <b>If the server is down, any paralegal can find any document in &lt;60 seconds with no computer.</b></p>

<h3>Canonical filename convention</h3>
<div class="box">
<code>{CASE}_{YYYY-MM-DD}_{TYPE}_{detail-slug}_{leo-id}.{ext}</code><br>
Example: <code>MWK_2026-04-24_NOTICE_pretrial-26-360_0392.pdf</code>
</div>

<h3>Hierarchical structure</h3>
<pre style="font-family: 'Courier New', monospace; font-size: 8pt; line-height: 1.4">
STRUCTURED/
├── README.md                              ← human navigation guide
├── 00-INDEX.csv                            ← top-level manifest
├── MWK-001-Heirs-of-Mary-Worrick-Keesey/  ← BINDER A
│   ├── 00-INDEX.csv
│   ├── 01-Pleadings/
│   │   ├── Civil-Case-26-360/{complaint, answer, replies, orders, pretrial}
│   │   ├── ARTA-2026-0423-1891/
│   │   └── Drafts-Pending-Filing/{Ombudsman, Supreme-Court, RTC}
│   ├── 02-Titles/{Active, Cancelled, Contested, Lost-or-Damaged}
│   ├── 03-Tax-Declarations/{1990-2010-Historic, 2011-2025-Series, 2026-Current}
│   ├── 04-Deeds-SPAs/{Donations, Sales, Powers-of-Attorney}
│   ├── 05-Correspondence/{Atty-Barandon, Atty-Botor, LGU-Mercedes, Heirs, ...}
│   ├── 06-Financial/{Bills, Receipts, Bank-Statements, Retainer-Agreements}
│   └── 07-Affidavits-Witnesses/
├── Paracale-001-Allan-Inocalla/
└── LANDTEK-FIRM/
</pre>

<p>Each folder contains <code>00-INDEX.csv</code> listing every document with canonical_filename, doc_id, doc_date, classification, execution_status. Regenerated nightly. Printable for paper binders.</p>
"""

    # ─────────── 13. CURRENT STATE ───────────
    h += f"""
<div class="pagebreak"></div>
<h2>13. Current State Metrics</h2>

<h3>Knowledge base</h3>
<div class="stat"><div class="stat-label">Documents indexed</div>
  <div class="stat-value">{fmt(m['docs_total'])}</div>
  <div class="stat-sub">{fmt(m['docs_extracted'])} ({pct(m['docs_extracted'],m['docs_total'])}) extracted</div></div>
<div class="stat"><div class="stat-label">Case-correlated</div>
  <div class="stat-value">{pct(m['docs_correlated'],m['docs_total'])}</div>
  <div class="stat-sub">{fmt(m['docs_correlated'])} of {fmt(m['docs_total'])}</div></div>
<div class="stat"><div class="stat-label">Execution-status classified</div>
  <div class="stat-value">{pct(m['docs_classified'],m['docs_total'])}</div>
  <div class="stat-sub">{fmt(m['docs_classified'])} have notarized/filed/email/draft tag</div></div>

<h3>Cases &amp; matters</h3>
<div class="stat"><div class="stat-label">Active matters</div>
  <div class="stat-value">{m['matters_active']}</div>
  <div class="stat-sub">Civil 26-360 · ARTA-DILG · TCT-4497 · Estate</div></div>
<div class="stat"><div class="stat-label">ARTA cases discovered</div>
  <div class="stat-value">{m['arta_cases']}</div>
  <div class="stat-sub">from Gmail pull (was 1-2)</div></div>
<div class="stat"><div class="stat-label">Active tax decs (MWK-001)</div>
  <div class="stat-value">{m['active_tax_decs']}</div>
  <div class="stat-sub">Mercedes assessor roster</div></div>

<h3>Truth + agency</h3>
<div class="stat"><div class="stat-label">Truth verifications</div>
  <div class="stat-value">{fmt(m['verifications'])}</div>
  <div class="stat-sub">logged in audit table</div></div>
<div class="stat"><div class="stat-label">Asset risks profiled</div>
  <div class="stat-value">{m['risks']}</div>
  <div class="stat-sub">with mitigation strategy</div></div>
<div class="stat"><div class="stat-label">Firm goals active</div>
  <div class="stat-value">{m['firm_goals']}</div>
  <div class="stat-sub">strategic objectives</div></div>

<h3>Financial</h3>
<div class="stat"><div class="stat-label">Transactions captured</div>
  <div class="stat-value">{fmt(m['transactions'])}</div>
  <div class="stat-sub">₱{m['total_paid']} cumulative spend</div></div>
<div class="stat"><div class="stat-label">Portfolio market value</div>
  <div class="stat-value">₱{m['portfolio_market']}</div>
  <div class="stat-sub">across {m['active_tax_decs']} active tax decs</div></div>
<div class="stat"><div class="stat-label">Emails ingested</div>
  <div class="stat-value">{fmt(m['emails'])}</div>
  <div class="stat-sub">9 ARTA cases surfaced</div></div>

<h3>Channels + meta</h3>
<div class="stat"><div class="stat-label">Channels active</div>
  <div class="stat-value">{m['channels_active']} active</div>
  <div class="stat-sub">{m['channels_pending']} pending adapters</div></div>
<div class="stat"><div class="stat-label">Back-test cases</div>
  <div class="stat-value">{m['backtests']}</div>
  <div class="stat-sub">run hourly against truth_negotiator</div></div>
<div class="stat"><div class="stat-label">Autonomous loops</div>
  <div class="stat-value">7</div>
  <div class="stat-sub">watchdog · sentinel · gmail · drive · accelerator · analyzer</div></div>
"""

    # ─────────── 14. GAP ANALYSIS ───────────
    h += """
<div class="pagebreak"></div>
<h2>14. Gap Analysis</h2>

<p>Honest accounting of what's still missing.</p>

<table>
<tr><th>Domain</th><th>Gap</th><th>Severity</th><th>Fix</th></tr>
<tr><td>Drive ingestion</td><td>341 of 937 files not yet pulled</td><td class="kpi-warn">Medium</td><td>drive-sync timer now active every 30m — closes within hours</td></tr>
<tr><td>Image-PDF OCR</td><td>19 docs need Gemini Vision fallback</td><td class="kpi-warn">Low</td><td>Run gemini fallback pass when API quota permits</td></tr>
<tr><td>Bills + real overhead</td><td>5 monthly_overhead rows are estimates · no real bills ingested</td><td class="kpi-bad">High</td><td>Email bill classifier (built · runs hourly)</td></tr>
<tr><td>Real Leo API spend</td><td>11 seeded cost rows · no Anthropic billing API connected</td><td class="kpi-warn">Medium</td><td>Anthropic Usage API integration</td></tr>
<tr><td>Email body → transactions</td><td>0 bills, 0 receipts extracted from email bodies yet</td><td class="kpi-bad">High</td><td>extract_bills_from_emails.py — next deploy</td></tr>
<tr><td>Year-by-year RPT</td><td>Captured totals only · not the 1990-2023 grid per ARP</td><td class="kpi-warn">Medium</td><td>Re-extract Mercedes Statements with detailed schema</td></tr>
<tr><td>Filing-party tagging</td><td>0 docs tagged plaintiff vs respondent</td><td class="kpi-bad">High</td><td>party_filing_classifier.py — deploy_119 pending</td></tr>
<tr><td>TCT ↔ ARP linkage</td><td>Only 5 confirmed links</td><td class="kpi-warn">Medium</td><td>Haiku batch on Mercedes Statements + 2x lot-code inference</td></tr>
<tr><td>Heir positions</td><td>121 Keesey/Zschoche entities but Marcia/Geraldine/Ellen positions unknown</td><td class="kpi-warn">Medium</td><td>Onboard remaining heirs via Telegram or email</td></tr>
<tr><td>Mercedes assessor master list</td><td>Jonathan has it · not yet uploaded</td><td class="kpi-bad">High</td><td>Operator action — upload to bot</td></tr>
<tr><td>Draft pleadings (Ombudsman, SC, RTC)</td><td>Jonathan has them · not yet ingested</td><td class="kpi-bad">High</td><td>Operator action — upload to bot</td></tr>
<tr><td>WhatsApp adapter</td><td>Schema + handler built · awaiting WABA token</td><td class="kpi-warn">Medium</td><td>360dialog or Twilio provisioning</td></tr>
<tr><td>Physical filing tree</td><td>Schema designed · not yet generated</td><td class="kpi-warn">Medium</td><td>organize_filing_structure.py — deploy_120 pending</td></tr>
<tr><td>Truth_negotiator regression</td><td>4 of 5 back-tests failed (challenger too aggressive)</td><td class="kpi-bad">High</td><td>Tune challenger prompt + evidence ranking</td></tr>
</table>

<div class="pagebreak"></div>
<h2>15. Roadmap</h2>

<h3>Immediate (next 7 days)</h3>
<ol>
<li>Fix truth_negotiator regression (challenger prompt tuning)</li>
<li>Ship party_filing_classifier — tag plaintiff vs respondent per doc</li>
<li>Ship organize_filing_structure — generate hierarchical filing tree with INDEX.csv per folder</li>
<li>Build extract_bills_from_emails — populate transactions + monthly_overhead from real bills</li>
<li>Continue Mercedes Statements re-extraction with detailed per-year RPT</li>
</ol>

<h3>Near-term (30 days)</h3>
<ol>
<li>WhatsApp Business adapter provisioning + Meta verification</li>
<li>Web chat widget for landtek.com</li>
<li>Email reply bot (send via Gmail API)</li>
<li>Drive write-perms for file rename + structured-folder mirror</li>
<li>Per-asset development plans for top 10 valuable assets</li>
<li>Anthropic Usage API integration (real Leo billing)</li>
</ol>

<h3>Strategic (90+ days)</h3>
<ol>
<li>Public REST API documentation + first licensee outreach</li>
<li>Investor pitch deck + financial pack (using /pack output as Exhibit A)</li>
<li>Branded iOS/Android app</li>
<li>Voice channel (Twilio + STT/TTS)</li>
<li>Court e-filing portal scraper (when APIs become available)</li>
<li>Expand to second flagship case (Paracale-001 or new client)</li>
</ol>
"""

    h += f"""
<div style="margin-top: 30px; padding: 12px; background: #f5f8fb; border-left: 3px solid #0a3d62; font-size: 9pt; color: #586e7a;">
<i>Generated by Leo Platform v0.121 · {now} · This document is auto-regeneratable via <code>/blueprint</code> or <code>python3 build_system_blueprint.py</code>.</i>
</div>

</body></html>
"""
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/landtek/reports/leo_system_blueprint.pdf")
    ap.add_argument("--send-tg", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    html = build_html(cur)
    cur.close(); conn.close()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    HTML(string=html).write_pdf(args.out)
    print(f"  ✓ wrote {args.out} ({os.path.getsize(args.out):,} bytes)")

    if args.send_tg:
        import requests
        env = {}
        with open("/root/landtek/.env") as f:
            for l in f:
                if "=" in l and not l.startswith("#"):
                    k, _, v = l.strip().partition("="); env[k.strip()] = v.strip()
        with open(args.out, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendDocument",
                data={"chat_id": "6513067717",
                      "caption": "📐 LandTek Leo Platform — Complete System Blueprint · build-from-scratch architecture document"},
                files={"document": (os.path.basename(args.out), f, "application/pdf")},
                timeout=60,
            )
        print(f"  TG: {r.status_code}")


if __name__ == "__main__":
    main()
