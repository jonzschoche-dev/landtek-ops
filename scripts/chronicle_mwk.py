#!/usr/bin/env python3
"""chronicle_mwk.py — Master chronicle for the MWK client across all matters.

Single chronological timeline of every dated event in the MWK corpus, with
cross-reference indexes (persons / titles / matters). No LLM. Every entry
cites a source row.

Sources unioned (chronologically):
  - documents (case_file='MWK-001') with doc_date IS NOT NULL
  - gmail_messages where MWK-* in matter_codes
  - resolutions affecting any MWK matter
  - escalations affecting any MWK matter
  - instruments_on_title (annotations on MWK titles)
  - title_transfers (per the title_transfers table)
  - Hardcoded memory keystones (MWK death, SPA grant/revoke, etc. — from
    project_title_origins_mwk and project_civil_case_26_360_load_bearing_dates
    memory rules).

Cross-references per event:
  - Entities: via doc_entities (for docs) and explicit regex search for known
    canonical entities (in gmail subject/body).
  - Titles: regex T-XXXX / OCT T-XXX in source text/subject/filename.
  - Matters: from source's matter_code(s).

Output:
  - drafts/chronicle_MWK_<date>.md

Usage:
  python3 scripts/chronicle_mwk.py
  python3 scripts/chronicle_mwk.py --out drafts/chronicle_MWK_2026-05-21.md
"""
import argparse
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/root/landtek")

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"


# Hardcoded keystone memory facts. Each = a dated event with no row in any
# table. Sourced from memory/project_title_origins_mwk.md and
# memory/project_civil_case_26_360_load_bearing_dates.md.
MEMORY_KEYSTONES = [
    {
        "date": "1912-01-01",
        "type": "memory",
        "title": "TCT T-111 issued (1912, asserted)",
        "detail": "Joint owners: Mary Worrick, Helen Worrick, Alice Worrick. "
                  "26.9312 ha in Mercedes, Camarines Norte, bounded NE by Pacific Ocean. "
                  "Primary T-111 document NOT in corpus.",
        "titles": ["T-111"],
        "entities_names": ["Mary Worrick", "Helen Worrick", "Alice Worrick"],
        "matters": [],
        "provenance": "asserted_via_doc279",
        "source": "memory:project_title_origins_mwk",
    },
    {
        "date": "1934-10-23",
        "type": "memory",
        "title": "OCT T-106 issued (1934, cross-cited)",
        "detail": "Registry of Deeds Camarines Norte. Cross-cited in 5+ TCT extractions. "
                  "Physical OCT NOT in corpus. **Per Jonathan 2026-05-21: ghost title — "
                  "T-111 (1912) is the operative root, not T-106.**",
        "titles": ["OCT T-106"],
        "entities_names": [],
        "matters": [],
        "provenance": "ghost_title",
        "source": "memory:project_title_origins_mwk + title_chain_canon.py",
    },
    {
        "date": "1953-07-12",
        "type": "memory",
        "title": "Attempted Donation to Mercedes municipality",
        "detail": "Donors: Mary Worrick Kees(e)y + Manuel Garrido. Donee: Mun. Mercedes "
                  "(via Mayor Gideon Evalla, Resolution 21 s.1953). 8,951.22 sqm portion. "
                  "Object: 'site of market and municipal building.' Claimed result-title: "
                  "T-1111 (NOT in corpus). Validity AUDITED — RD registration MISSING, "
                  "Donor's Tax/BIR CAR MISSING, T-1111 NOT verified.",
        "titles": ["T-111", "T-1111"],
        "entities_names": ["Mary Worrick Keesey", "Manuel Garrido"],
        "matters": ["MWK-ESTATE"],
        "provenance": "doc#279",
        "source": "doc#279 (Deed of Donation)",
    },
    {
        "date": "1964-06-02",
        "type": "memory",
        "title": "TCT T-4497 issued",
        "detail": "Mary's mother title. Physical doc damaged (heavy OCR). "
                  "Relationship to T-111 NOT mapped in title_chain (operative parent "
                  "per canon is T-111).",
        "titles": ["T-4497", "T-111"],
        "entities_names": ["Mary Worrick Keesey"],
        "matters": ["MWK-ESTATE", "MWK-TCT4497"],
        "provenance": "doc#382",
        "source": "doc#382 (TCT T-4497, government_issued, OCR-damaged)",
    },
    {
        "date": "1988-03-17",
        "type": "memory",
        "title": "Mary Worrick Keesey died",
        "detail": "Testimonial only via memory. PSA death certificate NOT in corpus.",
        "titles": [],
        "entities_names": ["Mary Worrick Keesey"],
        "matters": ["MWK-ESTATE", "MWK-CV26360"],
        "provenance": "testimonial",
        "source": "memory:project_civil_case_26_360_load_bearing_dates",
    },
    {
        "date": "1992-03-16",
        "type": "memory",
        "title": "SPA executed in Los Angeles → Cesar de la Fuente as AIF",
        "detail": "Heirs of MWK granted SPA to Cesar to perfect partial sales. "
                  "Validity components NOT yet audited.",
        "titles": ["T-4497"],
        "entities_names": ["Cesar de la Fuente"],
        "matters": ["MWK-ESTATE", "MWK-CV26360"],
        "provenance": "doc#329",
        "source": "doc#329 (SPA, executed Los Angeles)",
    },
    {
        "date": "2005-08-15",
        "type": "memory",
        "title": "SPA to Cesar de la Fuente REVOKED",
        "detail": "Testimonial only via doc#441. Primary revocation instrument MISSING — "
                  "single biggest evidence gap on the void-SPA theory. KEYSTONE claim "
                  "for the void chain in MWK-CV26360.",
        "titles": [],
        "entities_names": ["Cesar de la Fuente"],
        "matters": ["MWK-CV26360"],
        "provenance": "testimonial (doc#441 Judicial Affidavit)",
        "source": "doc#441",
    },
    {
        "date": "2016-09-01",
        "type": "memory",
        "title": "Cesar's Deed of Absolute Sale → T-52540 cancellation",
        "detail": "Executed by Cesar de la Fuente in September 2016, POST-revocation "
                  "of his SPA → VOID at inception per case theory. The actual 2016 "
                  "Deed NOT directly in corpus per current scan.",
        "titles": ["T-52540"],
        "entities_names": ["Cesar de la Fuente"],
        "matters": ["MWK-CV26360"],
        "provenance": "asserted",
        "source": "memory + multiple referencing docs",
    },
    {
        "date": "2017-06-21",
        "type": "memory",
        "title": "Cesar de la Fuente died",
        "detail": "Court-filed admission by opposing party (LandBank). 'Cesar N. dela "
                  "Fuente, administrator of state of Mary Worrick Keesey, died on June "
                  "21, 2017.' This is primary evidence — strongest in the corpus on Cesar's death.",
        "titles": [],
        "entities_names": ["Cesar de la Fuente"],
        "matters": ["MWK-CV26360", "MWK-CV6839"],
        "provenance": "verified (doc#364)",
        "source": "doc#364 (LandBank Comment in Civil Case 6839, executed_filed)",
    },
    {
        "date": "2021-11-23",
        "type": "memory",
        "title": "TCT T-52540 cancelled → T-079-2021002127 issued to Gloria Balane",
        "detail": "Via subdivision plan Psd-05-026197 per deploy_220 backfill. "
                  "The contested Balane title that anchors MWK-CV26360.",
        "titles": ["T-52540", "T-079-2021002127"],
        "entities_names": ["Gloria Balane"],
        "matters": ["MWK-CV26360"],
        "provenance": "verified",
        "source": "title_chain edge + subdivision_plans Psd-05-026197 (deploy_220)",
    },
    {
        "date": "2026-06-02",
        "type": "memory",
        "title": "**UPCOMING — Mediation / Settlement Conference, Civil Case 26-360**",
        "detail": "RTC Camarines Norte (Daet). Forcing function for the void-chain "
                  "mediation pack.",
        "titles": ["T-4497", "T-52540", "T-079-2021002127"],
        "entities_names": ["Patricia Keesey Zschoche", "Gloria Balane",
                           "Atty. Bonifacio Barandon"],
        "matters": ["MWK-CV26360"],
        "provenance": "scheduled",
        "source": "memory:CLAUDE.md + case_deadlines",
    },
]


TITLE_RE = re.compile(r"\b(?:OCT\s+)?T-\d{2,5}(?:-\d{3,15})?\b")


def extract_titles_from_text(text):
    """Return set of TCT numbers mentioned in text."""
    if not text:
        return set()
    return set(TITLE_RE.findall(text))


def load_events(cur, client_config=None):
    """Union all dated events from all source tables + memory keystones,
    scoped to the given client_config (defaults to MWK behavior for back-compat)."""
    events = []
    case_file = (client_config or {}).get("case_file", "MWK-001")
    matter_prefix = (client_config or {}).get("matter_prefix", "MWK-")
    client_id = (client_config or {}).get("client_id", "MWK")

    # --- Memory keystones (currently MWK-only; other clients add their own keystones) ---
    if client_id == "MWK":
        for k in MEMORY_KEYSTONES:
            events.append({
                "date": k["date"],
                "kind": "memory",
                "title": k["title"],
                "detail": k.get("detail", ""),
                "source": k["source"],
                "source_ref": k["source"],
                "titles": set(k.get("titles") or []),
                "entities": [],  # resolved via grep below
                "entities_names": k.get("entities_names") or [],
                "matters": set(k.get("matters") or []),
                "provenance": k.get("provenance", "memory"),
            })

    # --- Documents (client's case_file OR matter-code cross-linked) with doc_date ---
    # Cross-link rule: a doc in another case_file (e.g., 'Owner' for Jonathan's
    # personal copies) but tagged with a matter_code under the client's prefix
    # should still appear in the client's chronicle. This is how Owner-bucket
    # MWK family material surfaces under Mary Worrick Keesey's timeline.
    if matter_prefix:
        cur.execute("""
            SELECT id, doc_date, classification, execution_status, smart_filename,
                   matter_code, COALESCE(extracted_text, '') AS extracted_text
              FROM documents
             WHERE doc_date IS NOT NULL
               AND (case_file = %s OR matter_code LIKE %s)
             ORDER BY doc_date, id
        """, (case_file, matter_prefix + "%"))
    else:
        # Client has no matter namespace (e.g., OWNER) — case_file only
        cur.execute("""
            SELECT id, doc_date, classification, execution_status, smart_filename,
                   matter_code, COALESCE(extracted_text, '') AS extracted_text
              FROM documents
             WHERE doc_date IS NOT NULL AND case_file = %s
             ORDER BY doc_date, id
        """, (case_file,))
    for r in cur.fetchall():
        events.append({
            "date": r["doc_date"].isoformat() if hasattr(r["doc_date"], "isoformat")
                    else str(r["doc_date"]),
            "kind": "document",
            "title": f"[{r['classification'] or '?'}] {r['smart_filename'] or '(unnamed)'}",
            "detail": "",
            "source": f"doc#{r['id']}",
            "source_ref": r["id"],
            "titles": extract_titles_from_text(r["extracted_text"][:2000]) |
                      extract_titles_from_text(r["smart_filename"] or ""),
            "entities": [],  # populated from doc_entities below
            "entities_names": [],
            "matters": set([r["matter_code"]] if r["matter_code"] else []),
            "provenance": r["execution_status"] or "?",
        })

    # --- Emails (linked to this client's matters) ---
    cur.execute("""
        SELECT id, sent_at::date AS sent_date, from_name, from_addr, subject,
               matter_codes
          FROM gmail_messages
         WHERE cardinality(matter_codes) > 0
           AND EXISTS (SELECT 1 FROM unnest(matter_codes) mc WHERE mc LIKE %s)
           AND sent_at IS NOT NULL
         ORDER BY sent_at, id
    """, (matter_prefix + "%",))
    for r in cur.fetchall():
        sender = (r["from_name"] or r["from_addr"] or "?")[:40]
        events.append({
            "date": r["sent_date"].isoformat(),
            "kind": "email",
            "title": f"({sender}) {r['subject'] or '(no subject)'}",
            "detail": "",
            "source": f"gmail#{r['id']}",
            "source_ref": r["id"],
            "titles": extract_titles_from_text(r["subject"] or ""),
            "entities": [],
            "entities_names": [],
            "matters": set([m for m in (r["matter_codes"] or []) if m.startswith(matter_prefix)]),
            "provenance": "email_received" if "in" in (r.get("from_addr") or "") else "email",
        })

    # --- Resolutions ---
    cur.execute("""
        SELECT id, resolution_date, forum, disposition, source_doc_id,
               adjudicator_name_raw, affected_matter_codes, affected_ctn_nos,
               disposition_summary
          FROM resolutions
         WHERE resolution_date IS NOT NULL
           AND EXISTS (SELECT 1 FROM unnest(affected_matter_codes) mc WHERE mc LIKE %s)
         ORDER BY resolution_date, id
    """, (matter_prefix + "%",))
    for r in cur.fetchall():
        events.append({
            "date": r["resolution_date"].isoformat() if hasattr(r["resolution_date"], "isoformat")
                    else str(r["resolution_date"]),
            "kind": "resolution",
            "title": f"{r['forum'] or '?'} Resolution — disp=`{r['disposition'] or '?'}` "
                     f"({r['disposition_summary'] or 'no summary'})",
            "detail": f"Adjudicator: {r['adjudicator_name_raw'] or '?'}",
            "source": f"res#{r['id']} (doc#{r['source_doc_id']})" if r["source_doc_id"] else f"res#{r['id']}",
            "source_ref": r["id"],
            "titles": set(),
            "entities": [],
            "entities_names": [r["adjudicator_name_raw"]] if r["adjudicator_name_raw"] else [],
            "matters": set([m for m in (r["affected_matter_codes"] or []) if m.startswith(matter_prefix)]),
            "provenance": "resolution",
        })

    # --- Escalations ---
    cur.execute("""
        SELECT id, escalation_date, escalation_type, forum_from, forum_to,
               source_resolution_id, escalation_doc_id, escalation_email_id,
               affected_matter_codes, filed_by, addressed_to, status
          FROM escalations
         WHERE escalation_date IS NOT NULL
           AND EXISTS (SELECT 1 FROM unnest(affected_matter_codes) mc WHERE mc LIKE %s)
         ORDER BY escalation_date, id
    """, (matter_prefix + "%",))
    for r in cur.fetchall():
        src = (f"doc#{r['escalation_doc_id']}" if r['escalation_doc_id']
               else f"gmail#{r['escalation_email_id']}" if r['escalation_email_id']
               else "—")
        events.append({
            "date": r["escalation_date"].isoformat() if hasattr(r["escalation_date"], "isoformat")
                    else str(r["escalation_date"]),
            "kind": "escalation",
            "title": f"**{r['escalation_type']}** → {r['forum_to'][:40] if r['forum_to'] else '?'}",
            "detail": (f"by {r['filed_by'] or '?'}"
                       + (f" → {r['addressed_to']}" if r['addressed_to'] else "")
                       + f" · status=`{r['status']}` · esc-ref={src}"),
            "source": f"esc#{r['id']}",
            "source_ref": r["id"],
            "titles": set(),
            "entities": [],
            "entities_names": [],
            "matters": set([m for m in (r["affected_matter_codes"] or []) if m.startswith(matter_prefix)]),
            "provenance": "escalation",
        })

    # --- Instruments on titles (annotations) — scoped by source doc's case_file ---
    cur.execute("""
        SELECT i.id, i.entry_date, i.parent_tct_number, i.instrument_type,
               i.executor_full_name, i.pe_number, i.doc_id
          FROM instruments_on_title i
          LEFT JOIN documents d ON d.id = i.doc_id
         WHERE i.entry_date IS NOT NULL AND i.parent_tct_number IS NOT NULL
           AND (d.case_file = %s OR d.case_file IS NULL)
         ORDER BY i.entry_date, i.id
    """, (case_file,))
    for r in cur.fetchall():
        events.append({
            "date": r["entry_date"].isoformat() if hasattr(r["entry_date"], "isoformat")
                    else str(r["entry_date"]),
            "kind": "annotation",
            "title": f"Annotation on `{r['parent_tct_number']}`: {r['instrument_type'] or '?'}",
            "detail": (f"PE: {r['pe_number'] or '—'}"
                       + (f" · executor: {r['executor_full_name']}"
                          if r['executor_full_name'] else "")),
            "source": f"inst#{r['id']}" + (f" (doc#{r['doc_id']})" if r['doc_id'] else ""),
            "source_ref": r["id"],
            "titles": {r["parent_tct_number"]},
            "entities": [],
            "entities_names": [r["executor_full_name"]] if r["executor_full_name"] else [],
            "matters": set(),
            "provenance": "instrument_extracted",
        })

    # --- Title transfers ---
    try:
        cur.execute("""
            SELECT id, transfer_date, parent_title, derivative_title,
                   transferee_name, area_hectares, instrument_type
              FROM title_transfers
             WHERE transfer_date IS NOT NULL
             ORDER BY transfer_date, id
        """)
        for r in cur.fetchall():
            events.append({
                "date": r["transfer_date"].isoformat() if hasattr(r["transfer_date"], "isoformat")
                        else str(r["transfer_date"]),
                "kind": "transfer",
                "title": (f"Transfer: `{r['parent_title']}` → `{r['derivative_title']}` "
                          f"({r['instrument_type'] or '?'})"
                          + (f" to {r['transferee_name']}" if r['transferee_name'] else "")),
                "detail": (f"area: {r['area_hectares']} ha"
                           if r.get('area_hectares') else ""),
                "source": f"tt#{r['id']}",
                "source_ref": r["id"],
                "titles": {t for t in (r["parent_title"], r["derivative_title"]) if t},
                "entities": [],
                "entities_names": [r["transferee_name"]] if r["transferee_name"] else [],
                "matters": set(),
                "provenance": "transfer_record",
            })
    except Exception:
        pass  # title_transfers may have different shape

    return events


def attach_entities_from_doc_entities(cur, events):
    """For document and resolution events, attach entity_ids via doc_entities."""
    # Build doc_id → events index
    doc_id_to_events = defaultdict(list)
    for e in events:
        if e["kind"] == "document":
            doc_id_to_events[e["source_ref"]].append(e)
    if not doc_id_to_events:
        return

    cur.execute("""
        SELECT de.doc_id, e.id, e.canonical_name
          FROM doc_entities de JOIN entities e ON e.id = de.entity_id
         WHERE de.doc_id = ANY(%s)
    """, (list(doc_id_to_events.keys()),))
    for r in cur.fetchall():
        for ev in doc_id_to_events[r["doc_id"]]:
            ev["entities"].append((r["id"], r["canonical_name"]))


def render_chronicle(events, run_date, client_label="Mary Worrick Keesey"):
    lines = []
    lines.append(f"# Master Chronicle — {client_label} client")
    lines.append("")
    lines.append(f"**Generated:** {run_date} · Deterministic — every entry cites a source row.")
    lines.append(f"**Total events:** {len(events)}")
    lines.append("")
    lines.append("## Cross-reference index")
    lines.append("")
    lines.append("- [Timeline by year](#timeline)")
    lines.append("- [Persons](#persons)")
    lines.append("- [Titles (TCT/OCT)](#titles)")
    lines.append("- [Matters](#matters)")
    lines.append("")

    # Sort events chronologically
    events.sort(key=lambda e: (e["date"], e["source"]))

    # ─── Timeline by year ─────────────────────────────────────────────────
    lines.append('## <a id="timeline"></a>Timeline')
    lines.append("")
    by_year = defaultdict(list)
    for e in events:
        year = e["date"][:4]
        by_year[year].append(e)

    for year in sorted(by_year.keys()):
        lines.append(f"### {year}")
        lines.append("")
        for e in by_year[year]:
            tags = []
            for t in sorted(e["titles"]):
                tags.append(f"`{t}`")
            for m in sorted(e["matters"]):
                tags.append(f"`{m}`")
            tag_str = " · ".join(tags) if tags else ""
            kind_emoji = {
                "memory": "📜", "document": "📄", "email": "✉",
                "resolution": "⚖", "escalation": "↗", "annotation": "🗒",
                "transfer": "🔄",
            }.get(e["kind"], "·")
            lines.append(f"- **{e['date']}** {kind_emoji} {e['title']}  "
                         f"`{e['source']}`  {tag_str}")
            if e.get("detail"):
                lines.append(f"    > {e['detail']}")
        lines.append("")

    # ─── Persons index ────────────────────────────────────────────────────
    lines.append('## <a id="persons"></a>Persons')
    lines.append("")
    person_events = defaultdict(list)
    for e in events:
        for eid, name in e["entities"]:
            person_events[name].append(e)
        for name in e["entities_names"]:
            if name:
                person_events[name].append(e)

    # Filter to persons appearing ≥2 times (otherwise too noisy)
    for name, evs in sorted(person_events.items()):
        if len(evs) < 2:
            continue
        lines.append(f"### {name}")
        lines.append("")
        for e in sorted(evs, key=lambda x: x["date"]):
            lines.append(f"- {e['date']} · {e['title'][:90]} · `{e['source']}`")
        lines.append("")

    # ─── Titles index ─────────────────────────────────────────────────────
    lines.append('## <a id="titles"></a>Titles (TCT / OCT)')
    lines.append("")
    title_events = defaultdict(list)
    for e in events:
        for t in e["titles"]:
            title_events[t].append(e)

    for t in sorted(title_events.keys()):
        evs = title_events[t]
        if len(evs) < 2:
            continue
        lines.append(f"### `{t}`")
        lines.append("")
        for e in sorted(evs, key=lambda x: x["date"]):
            lines.append(f"- {e['date']} · {e['title'][:100]} · `{e['source']}`")
        lines.append("")

    # ─── Matters index ────────────────────────────────────────────────────
    lines.append('## <a id="matters"></a>Matters')
    lines.append("")
    matter_events = defaultdict(list)
    for e in events:
        for m in e["matters"]:
            matter_events[m].append(e)

    for m in sorted(matter_events.keys()):
        evs = matter_events[m]
        lines.append(f"### {m}  ({len(evs)} events)")
        lines.append("")
        # Show last 10 for navigability
        for e in sorted(evs, key=lambda x: x["date"])[-10:]:
            lines.append(f"- {e['date']} · {e['title'][:100]} · `{e['source']}`")
        if len(evs) > 10:
            lines.append(f"- _… {len(evs) - 10} earlier events_")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default="MWK", help="Client id from case_theories._clients.CLIENTS (default: MWK)")
    ap.add_argument("--matter", default=None,
                    help="Scope chronicle to a single matter_code (e.g., MWK-CV26360). "
                         "Filter keeps events where the matter is in event.matters OR the event "
                         "has no matter binding (memory keystones, ambient annotations).")
    ap.add_argument("--all-matters", action="store_true",
                    help="Generate one per-matter chronicle for every matter under the client's prefix.")
    ap.add_argument("--out", default=None, help="Output path (default: drafts/chronicle_<client>[_<matter>]_<date>.md)")
    args = ap.parse_args()
    # Reading the registry as a smoke check so the dependency is explicit:
    from case_theories._clients import get
    client_config = get(args.client)

    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print(f"Loading events for client={args.client} from 7 sources (memory + 6 tables)…")
    events = load_events(cur, client_config=client_config)
    print(f"  → {len(events)} events loaded")
    attach_entities_from_doc_entities(cur, events)
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def write_for_matter(matter_code):
        """Render a chronicle scoped to matter_code (or full if None)."""
        if matter_code:
            # Keep events that explicitly bind to this matter OR are matter-agnostic
            # (memory keystones, annotations on parent titles) so the chronological
            # context isn't lost.
            scoped = [e for e in events
                      if matter_code in e["matters"] or len(e["matters"]) == 0]
        else:
            scoped = events
        if matter_code:
            slug = matter_code.replace("/", "_")
            out_path = args.out or f"/root/landtek/drafts/chronicle_{args.client}_{slug}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        else:
            out_path = args.out or f"/root/landtek/drafts/chronicle_{args.client}_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        md = render_chronicle(scoped, run_date, client_label=client_config.get("label", args.client))
        if matter_code:
            # Inject matter-scope banner after the first H1
            banner = f"\n**Scope:** {matter_code} only (plus matter-agnostic keystones/annotations).\n"
            md = md.replace("\n", banner + "\n", 1) if "\n" in md else md
        Path(out_path).write_text(md)
        print(f"  · {out_path}  ({len(scoped)} events, {len(md.splitlines())} lines)")
        return out_path

    if args.all_matters:
        cur.execute("SELECT matter_code FROM matters WHERE matter_code LIKE %s ORDER BY matter_code",
                    (client_config["matter_prefix"] + "%",))
        matter_codes = [r["matter_code"] for r in cur.fetchall()]
        print(f"\nGenerating per-matter chronicles for {len(matter_codes)} matters under {args.client}:")
        for mc in matter_codes:
            write_for_matter(mc)
        # Also emit the master chronicle
        print(f"\nGenerating master {args.client} chronicle:")
        write_for_matter(None)
    else:
        out_path = write_for_matter(args.matter)
        print(f"\nChronicle written: {out_path}")
        print(f"  events: {len(events) if not args.matter else sum(1 for e in events if args.matter in e['matters'] or not e['matters'])}")
        if events:
            print(f"  years covered: {min(e['date'][:4] for e in events)} → {max(e['date'][:4] for e in events)}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
