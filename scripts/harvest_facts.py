#!/usr/bin/env python3
"""harvest_facts.py — FREE structured-fact accretion (no LLM, no quota, $0).

A large slice of "awareness" needs no model at all: title/lot numbers, dates, peso amounts, areas,
and known party names are STRUCTURED facts that regex pulls straight from the OCR'd text. This
harvests them per matter into matter_facts (grounded: source doc + verbatim excerpt), which moves
the awareness meter at zero cost and with no quota dependency — the LLM comprehension layer is then
reserved only for judgment (clean vs clouded, valuation, strategy). Idempotent (created_by='harvest').

Also continuously fills matter_parties from:
  - documents.parties JSON (classification-time structured parties)
  - entities (type=person with a role) whose first/last-seen doc is linked to the matter

  python3 harvest_facts.py --all --go
  python3 harvest_facts.py --matter MWK-CV26360 --go
"""
import json
import re
import sys
import os

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_gate  # noqa: E402 — A77 writer-side owner gate (unresolved doc never forms an edge)
import contradiction as CONTRA  # noqa: E402 — A78 ingest gate (conflict with verified => HOLD)

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

RE_TITLE = re.compile(r"\b(?:TCT|OCT)?[\s-]?(?:T|P|OCT)-\d{3,6}(?:-\d+)*\b", re.I)
RE_DATE = re.compile(
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
RE_MONEY = re.compile(r"(?:₱|PHP|Php|P)\s?\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{2})?\s*(?:pesos|PHP)\b", re.I)
RE_AREA = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:sq\.?\s?m\.?|square\s+meters?|hectares?|has?\.|sqm)\b", re.I)

# role-text → side for continuous party table fill
_SIDE_PATTERNS = [
    (re.compile(r"\b(plaintiff|petitioner|complainant|claimant)\b", re.I), "plaintiff"),
    (re.compile(r"\b(defendant|respondent|accused)\b", re.I), "defendant"),
    (re.compile(r"\b(heir|co-heir|coheir|legatee)\b", re.I), "heir"),
    (re.compile(r"\b(decedent|deceased|testator)\b", re.I), "decedent"),
    (re.compile(r"\b(transferee|buyer|vendee|grantee)\b", re.I), "transferee"),
    (re.compile(r"\b(transferor|seller|vendor|grantor)\b", re.I), "transferor"),
    (re.compile(r"\b(counsel|attorney|lawyer|notary)\b", re.I), "counsel"),
    (re.compile(r"\b(witness|affiant)\b", re.I), "witness"),
    (re.compile(r"\b(administrator|executor|guardian)\b", re.I), "fiduciary"),
]


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("ALTER TABLE matter_facts ADD COLUMN IF NOT EXISTS created_by text")
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_parties (
        id serial PRIMARY KEY, matter_code text, entity_id int, party_name text, side text, role text,
        provenance_level text DEFAULT 'inferred_strong', source_doc_id int, source_excerpt text,
        created_at timestamptz DEFAULT now(), UNIQUE(matter_code, entity_id, side))""")
    # allow multiple null-entity rows keyed by name+side (harvest path)
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS matter_parties_name_side_uidx
        ON matter_parties (matter_code, lower(party_name), side)
        WHERE entity_id IS NULL AND party_name IS NOT NULL
    """)


def _ctx(text, m, pad=45):
    s = max(0, m.start() - pad); e = min(len(text), m.end() + pad)
    return re.sub(r"\s+", " ", text[s:e]).strip()


def _side_from_text(text):
    if not text:
        return "party"
    for rx, side in _SIDE_PATTERNS:
        if rx.search(text):
            return side
    return "party"


def _harvest_doc(text):
    """Return list of (fact_kind, statement, excerpt) — capped, deduped, high-value only."""
    out = []
    titles = sorted({m.group(0).upper().replace(" ", "").replace("TCT", "").replace("OCT", "").lstrip("-")
                     for m in RE_TITLE.finditer(text)})
    titles = [t for t in titles if re.search(r"\d{3,}", t)][:12]
    if titles:
        out.append(("reference", f"References title(s): {', '.join(titles)}", ", ".join(titles)))
    for kind, rx, lbl, cap in [("event", RE_DATE, "Dated reference", 3),
                               ("financial", RE_MONEY, "Amount", 2),
                               ("area", RE_AREA, "Area", 2)]:
        seen = set()
        for m in rx.finditer(text):
            v = m.group(0).strip()
            if v in seen:
                continue
            seen.add(v)
            out.append((kind, f"{lbl}: {v}", _ctx(text, m)))
            if len(seen) >= cap:
                break
    return out


def _upsert_party(cur, matter_code, name, side, role, entity_id, source_doc_id, excerpt, go):
    """Write one inferred_strong party row. Never upgrades verified/operator rows."""
    from party_name_gate import is_party_name
    name = (name or "").strip()
    # NAME-shape gate: documents.parties JSON and entity names carry email/OCR
    # junk ("On Tue") — reject anything not name-shaped before it lands.
    if not is_party_name(name):
        return 0
    side = (side or "party")[:40]
    role = (role or "")[:300]
    excerpt = (excerpt or name)[:400]
    if not go:
        return 1
    if entity_id is not None:
        cur.execute("""
            SELECT id, provenance_level FROM matter_parties
            WHERE matter_code=%s AND entity_id=%s AND side=%s
            LIMIT 1
        """, (matter_code, entity_id, side))
        existing = cur.fetchone()
        if existing:
            if existing["provenance_level"] in ("inferred_strong", "inferred_weak"):
                cur.execute("""
                    UPDATE matter_parties SET
                        party_name=%s,
                        role=COALESCE(NULLIF(%s,''), role),
                        source_doc_id=COALESCE(%s, source_doc_id),
                        source_excerpt=COALESCE(NULLIF(%s,''), source_excerpt)
                    WHERE id=%s
                """, (name[:200], role, source_doc_id, excerpt, existing["id"]))
            return 1
        cur.execute("""
            INSERT INTO matter_parties
                (matter_code, entity_id, party_name, side, role, provenance_level,
                 source_doc_id, source_excerpt)
            VALUES (%s,%s,%s,%s,%s,'inferred_strong',%s,%s)
        """, (matter_code, entity_id, name[:200], side, role, source_doc_id, excerpt))
        return 1

    cur.execute("""
        SELECT id, provenance_level FROM matter_parties
        WHERE matter_code=%s AND lower(party_name)=lower(%s) AND side=%s
        LIMIT 1
    """, (matter_code, name, side))
    existing = cur.fetchone()
    if existing:
        if existing["provenance_level"] in ("inferred_strong", "inferred_weak"):
            cur.execute("""
                UPDATE matter_parties SET
                    role=COALESCE(NULLIF(%s,''), role),
                    source_doc_id=COALESCE(%s, source_doc_id),
                    source_excerpt=COALESCE(NULLIF(%s,''), source_excerpt)
                WHERE id=%s
            """, (role, source_doc_id, excerpt, existing["id"]))
        return 0  # already present
    cur.execute("""
        INSERT INTO matter_parties
            (matter_code, entity_id, party_name, side, role, provenance_level,
             source_doc_id, source_excerpt)
        VALUES (%s,NULL,%s,%s,%s,'inferred_strong',%s,%s)
    """, (matter_code, name[:200], side, role, source_doc_id, excerpt))
    return 1


def harvest_parties(cur, matter_code, go):
    """Fill matter_parties continuously from documents.parties JSON + role-bearing entities."""
    n = 0
    # 1) Classification-time parties JSON on matter-linked docs
    cur.execute("""
        SELECT d.id AS doc_id, d.parties
        FROM document_matter_links l
        JOIN documents d ON d.id = l.doc_id
        WHERE l.matter_code = %s
          AND d.parties IS NOT NULL
          AND d.parties::text NOT IN ('[]','null','{}')
    """, (matter_code,))
    for row in cur.fetchall():
        if not ingest_gate.owner_gate(cur, matter_code, row["doc_id"], "harvest_facts", record=go):
            continue
        parties = row["parties"]
        if isinstance(parties, str):
            try:
                parties = json.loads(parties)
            except Exception:
                continue
        items = []
        if isinstance(parties, list):
            for p in parties:
                if isinstance(p, str):
                    items.append((p, "party", "named party"))
                elif isinstance(p, dict):
                    nm = p.get("name") or p.get("party_name") or p.get("party") or ""
                    role = p.get("role") or p.get("side") or "named party"
                    items.append((nm, _side_from_text(role), role))
        elif isinstance(parties, dict):
            for key, val in parties.items():
                side = _side_from_text(key)
                names = val if isinstance(val, list) else [val]
                for nm in names:
                    if isinstance(nm, str) and nm.strip():
                        items.append((nm.strip(), side, key))
        for nm, side, role in items:
            n += _upsert_party(cur, matter_code, nm, side, role, None, row["doc_id"], nm, go)

    # 2) Role-bearing person entities whose first/last-seen doc is linked to this matter
    cur.execute("""
        SELECT DISTINCT e.id AS entity_id, e.canonical_name, e.role,
               coalesce(e.first_seen_doc, e.last_seen_doc) AS doc_id
        FROM entities e
        JOIN document_matter_links l
          ON l.doc_id IN (e.first_seen_doc, e.last_seen_doc)
        WHERE l.matter_code = %s
          AND e.type = 'person'
          AND coalesce(e.canonical_name,'') <> ''
          AND (
                (e.role IS NOT NULL AND e.role <> '')
                OR coalesce(e.mentions_count, 0) >= 20
              )
        LIMIT 80
    """, (matter_code,))
    for e in cur.fetchall():
        doc_id = e["doc_id"]
        if doc_id and not ingest_gate.owner_gate(cur, matter_code, doc_id, "harvest_facts", record=go):
            continue
        role = e["role"] or "mentioned person"
        side = _side_from_text(role)
        # Prefer matter-code mention in role text as relevance signal
        n += _upsert_party(
            cur, matter_code, e["canonical_name"], side, role,
            e["entity_id"], doc_id, (role or e["canonical_name"])[:400], go,
        )
    return n


def harvest_matter(cur, matter_code, go):
    cur.execute("""SELECT l.doc_id, d.extracted_text FROM document_matter_links l
                   JOIN documents d ON d.id=l.doc_id
                   WHERE l.matter_code=%s AND length(coalesce(d.extracted_text,''))>80""", (matter_code,))
    docs = cur.fetchall()
    n = held_conflicts = 0
    # A77(1): a doc whose client owner cannot be resolved never forms an edge — HELD, not guessed.
    # Held docs are EXCLUDED from the delete-rewrite: their existing facts stay frozen exactly as
    # they are (open holes_findings route them to the operator's disposition — never auto-deleted).
    ok, held = [], []
    for d in docs:
        (ok if ingest_gate.owner_gate(cur, matter_code, d["doc_id"], "harvest_facts", record=go)
         else held).append(d)
    # IDEMPOTENT in place — unchanged facts KEEP their ids. The old delete-first
    # sweep re-created ~35k rows/pass with new ids, and fact_fields (fact_id ON
    # DELETE CASCADE) lost its typed rows every time — a perpetual wipe+refill
    # sawtooth (agent_sim cycles 5/10/14 caught it). Upsert on uq_mf_writer_key
    # (matter_code, created_by, source_id, md5(statement) WHERE created_by IN
    # ('harvest','doc_populate')) so re-runs touch nothing; only genuinely
    # stale facts are swept afterwards, sparing held docs (A77 freeze).
    kept_ids = []
    vmap = CONTRA.verified_event_dates(cur, matter_code)  # A78: loaded once per matter
    for d in ok:
        for kind, stmt, excerpt in _harvest_doc(d["extracted_text"]):
            # A78: an incoming fact contradicting a VERIFIED fact is held at ingest, never written.
            conflicts = CONTRA.conflicts_with_verified(cur, matter_code, stmt + " " + excerpt,
                                                       verified_map=vmap)
            if conflicts:
                held_conflicts += 1
                ingest_gate.hold_contradiction(cur, "harvest_facts", matter_code, d["doc_id"],
                                               stmt, conflicts, record=go)
                continue
            n += 1
            if not go:
                continue
            cur.execute("""INSERT INTO matter_facts
                (matter_code, statement, fact_kind, source_kind, source_id, excerpt, provenance_level, created_by, created_at)
                VALUES (%s,%s,%s,'doc',%s,%s,'inferred_strong','harvest', now())
                ON CONFLICT (matter_code, created_by, source_id, md5(statement))
                  WHERE created_by IN ('harvest', 'doc_populate')
                DO UPDATE SET
                    fact_kind = EXCLUDED.fact_kind,
                    excerpt = EXCLUDED.excerpt,
                    updated_at = CASE WHEN (matter_facts.fact_kind, matter_facts.excerpt)
                                          IS DISTINCT FROM (EXCLUDED.fact_kind, EXCLUDED.excerpt)
                                      THEN now() ELSE matter_facts.updated_at END
                RETURNING id""",
                (matter_code, stmt[:500], kind, str(d["doc_id"]), excerpt[:400]))
            row = cur.fetchone()
            if row:
                kept_ids.append(row["id"])
    if go:
        # Stale = previously harvested, no longer produced this sweep, and not
        # from a held doc (A77: held docs' facts stay frozen exactly as they are).
        cur.execute("""DELETE FROM matter_facts
                       WHERE matter_code=%s AND created_by='harvest'
                         AND NOT (id = ANY(%s))
                         AND NOT (source_id = ANY(%s))""",
                    (matter_code, kept_ids or [-1],
                     [str(d["doc_id"]) for d in held] or ["__none__"]))
    n_parties = harvest_parties(cur, matter_code, go)
    if held or held_conflicts:
        print(f"  {matter_code:<26} HELD: {len(held)} unresolved-owner doc(s), "
              f"{held_conflicts} contradicting fact(s) (A77/A78 gate — visible in holes_findings)")
    return n, len(docs), n_parties


def run(matter=None, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    if matter:
        codes = [matter]
    else:
        cur.execute("SELECT matter_code FROM matters ORDER BY matter_code")
        codes = [r["matter_code"] for r in cur.fetchall()]
    tot_f = tot_d = tot_p = 0
    for mc in codes:
        nf, nd, np = harvest_matter(cur, mc, go)
        tot_f += nf; tot_d += nd; tot_p += np
        if nf or np:
            print(f"  {mc:<26} {nf} facts / {np} parties from {nd} docs")
    print(f"[harvest] {'WROTE' if go else 'DRY'} matters={len(codes)} facts={tot_f} parties={tot_p} (FREE — no LLM)")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    run(matter=(a[a.index("--matter") + 1] if "--matter" in a else None), go="--go" in a)
