#!/usr/bin/env python3
"""matter_elements.py — instantiate the legal-element framework per matter and map evidence.

For each matter we know the cause/proceeding type; PH law fixes the elements that must be proven
for that type (accion reinvindicatoria, R.A. 11032, just compensation, estate, title-chain, ...).
This stamps those elements onto each matter as the rows of its evidence matrix, then maps the
matter's already-linked corpus docs to each element by keyword/role match — yielding a real
element -> evidence -> gap grid. Deterministic + creditless. The mapping is inference-grade
(provenance_level inferred_*); LLM/counsel verification + AnyCase authority-grounding come later.

  python3 matter_elements.py --seed-all --go      # build the matrix for every matter
  python3 matter_elements.py --seed MWK-CV26360 --go
  python3 matter_elements.py --matrix MWK-CV26360  # render one matter's matrix
  python3 matter_elements.py --summary             # coverage across all matters
"""
import os
import sys

import psycopg2
import psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")

# element = (code, priority 1-5, label, [keywords that evidence it])
FRAMEWORKS = {
    "accion_reinvindicatoria": [
        ("ownership", 5, "Plaintiff's ownership / valid title to the property",
         ["title", "tct", "t-4497", "tax declaration", "owner", "heirs", "keesey", "mother title", "ownership"]),
        ("identity", 4, "Identity of the land — technical description, boundaries, area",
         ["technical description", "bounded", "boundaries", "area", "hectare", "square meter", "sq. m", "survey", "psu", "psd", "lot ", "parcel"]),
        ("adverse_claim", 4, "Defendant's possession / adverse title",
         ["balane", "t-079", "deed of sale", "deed of absolute sale", "possession", "occupant", "adverse"]),
        ("defect", 5, "Defect invalidating defendant's claim (void SPA -> void deed -> void title)",
         ["revocation", "revoked", "special power", "attorney-in-fact", "spa", "void", "forged", "falsified", "fraud", "de la fuente"]),
        ("procedure", 2, "Jurisdiction/forum, prescription/laches, barangay conciliation",
         ["summons", "order", "jurisdiction", "barangay", "certification to file", "pre-trial", "mediation", "complaint"]),
    ],
    "just_compensation": [
        ("taking", 5, "Taking/expropriation by government or CARP coverage",
         ["notice of coverage", "expropriation", "landbank", "land bank", "carp", "agrarian", "taking", "compulsory acquisition"]),
        ("ownership", 4, "Claimant's ownership + property identity",
         ["title", "tct", "tax declaration", "owner", "heirs"]),
        ("valuation", 5, "Fair market value / just valuation",
         ["valuation", "appraisal", "fair market", "zonal", "just compensation", "land valuation", "dar valuation"]),
        ("interest_delay", 3, "Interest from time of taking / delay in payment",
         ["interest", "deposit", "payment", "delay", "provisional"]),
        ("procedure", 2, "Proper forum (SAC/RTC), commissioners",
         ["order", "commissioner", "special agrarian", "sac", "petition"]),
    ],
    "ra11032": [
        ("covered_transaction", 4, "A covered government transaction / records request",
         ["request", "foi", "freedom of information", "records", "certification", "application"]),
        ("prescribed_period", 3, "Citizen's Charter prescribed processing period",
         ["citizen's charter", "processing time", "prescribed period", "working days", "3-7-20"]),
        ("violation", 5, "Official's act/omission/delay/refusal (RA 11032 Sec. 21)",
         ["complaint", "affidavit", "no response", "failure", "delay", "refus", "denied", "section 21", "11032", "fixing"]),
        ("notice_exhaustion", 3, "Notice / follow-up given (exhaustion)",
         ["follow-up", "follow up", "demand", "letter", "reminder", "second request"]),
        ("respondent_forum", 3, "Proper respondent identity + jurisdiction (ARTA/OP)",
         ["arta", "office of the president", "resolution", "notice of", "respondent", "noc"]),
        ("damage", 2, "Prejudice / harm",
         ["damage", "prejudice", "injury", "harm", "loss"]),
    ],
    "estate_admin": [
        ("death", 5, "Death of the decedent (death certificate)",
         ["death certificate", "certificate of death", "died", "deceased", "ssdi", "date of death"]),
        ("heirs", 4, "Heirs identification + filiation",
         ["birth certificate", "marriage certificate", "heirs", "filiation", "legitimate", "son", "daughter", "spouse"]),
        ("assets", 4, "Estate inventory / assets (titles, accounts)",
         ["title", "tct", "tax declaration", "inventory", "property", "account", "asset"]),
        ("liabilities_tax", 3, "Debts, claims, estate tax",
         ["estate tax", "bir", "debt", "claim", "liabilit", "car", "amnesty"]),
        ("settlement", 4, "Settlement instrument (EJS/partition) + publication + bond",
         ["extrajudicial", "settlement", "partition", "publication", "bond", "deed of"]),
    ],
    "title_chain": [
        ("mother_authentic", 5, "Mother title authenticity (RD-certified)",
         ["certified true copy", "register of deeds", "registry of deeds", "lra", "authentic", "title", "judicial form"]),
        ("derivative_edges", 4, "Each derivative title edge verified",
         ["derivative", "cancelled", "from t-", "issued from", "transfer", "subdivision"]),
        ("encumbrances", 3, "Annotations / encumbrances status",
         ["encumbrance", "annotation", "lien", "memorandum of encumbrance", "adverse claim", "lis pendens", "mortgage"]),
        ("defects", 5, "Spurious-title flags / void instruments",
         ["fraud", "void", "revoked", "forged", "falsified", "spurious", "double title", "fake"]),
        ("custody", 3, "Owner's duplicate custody",
         ["owner's duplicate", "owners duplicate", "affidavit of loss", "lost", "reconstitution"]),
    ],
    "criminal": [
        ("offense_elements", 5, "Elements of the specific offense", ["information", "offense", "crime", "violation", "penal"]),
        ("accused_identity", 4, "Identity of the accused", ["accused", "respondent", "people vs", "people of the philippines"]),
        ("corpus_delicti", 5, "Corpus delicti / the act", ["death", "killing", "murder", "injury", "act", "incident", "autopsy"]),
        ("witnesses", 4, "Witness statements / sworn accounts", ["affidavit", "witness", "sworn", "statement", "testimony"]),
        ("procedure", 2, "Venue/jurisdiction, information filed", ["information", "prosecutor", "court", "venue", "warrant"]),
    ],
    "guardianship": [
        ("ward_status", 5, "Ward's incapacity / minority", ["incapacit", "minor", "ward", "incompetent", "disab"]),
        ("guardian_qualification", 4, "Proposed guardian's qualification", ["guardian", "petitioner", "qualif", "fit"]),
        ("estate_to_protect", 4, "Property/estate to be protected", ["property", "title", "estate", "asset", "real propert"]),
        ("notice_publication", 3, "Notice + publication", ["notice", "publication", "hearing", "order"]),
    ],
    "generic": [
        ("facts", 4, "The operative facts", ["letter", "affidavit", "deed", "notice", "complaint", "agreement", "contract"]),
        ("legal_basis", 4, "Legal basis / cause of action", ["law", "section", "code", "rule", "violation", "obligation"]),
        ("evidence", 3, "Supporting evidence", ["receipt", "title", "certificate", "record", "proof", "exhibit"]),
        ("relief", 2, "Relief sought / current status", ["relief", "prayer", "demand", "resolution", "order", "status"]),
    ],
}


def _conn():
    c = psycopg2.connect(DSN); c.autocommit = True; return c


def _ensure(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS matter_elements (
        id serial PRIMARY KEY,
        matter_code text NOT NULL,
        framework_key text,
        element_code text NOT NULL,
        priority int DEFAULT 3,
        label text,
        status text DEFAULT 'missing',        -- have | partial | missing
        n_support int DEFAULT 0,
        supporting_doc_ids int[] DEFAULT '{}',
        any_verified boolean DEFAULT false,
        gap_note text,
        provenance_level text DEFAULT 'inferred_strong',
        updated_at timestamptz DEFAULT now(),
        UNIQUE (matter_code, element_code))""")


def resolve_framework(matter_type, legal_theory, title):
    t = " ".join([x or "" for x in (matter_type, legal_theory, title)]).lower()
    if "reinvindicatoria" in t or "reivindicatoria" in t or "void-spa" in t or "void-deed" in t or "recovery of" in t or "accion" in t:
        return "accion_reinvindicatoria"
    if "just compensation" in t or "expropriation" in t or "carp" in t or "landbank" in t or "land bank" in t or "agrarian" in t:
        return "just_compensation"
    if (matter_type or "") == "administrative" or "11032" in t or "arta" in t:
        return "ra11032"
    if (matter_type or "") == "transactional" or "estate administration" in t or "estate admin" in t:
        return "estate_admin"
    if (matter_type or "") == "regulatory" or ("title" in t and ("chain" in t or "verification" in t)):
        return "title_chain"
    if (matter_type or "") == "criminal":
        return "criminal"
    if (matter_type or "") == "special_proceeding" or "guardian" in t:
        return "guardianship"
    return "generic"


def _linked_docs(cur, matter_code):
    cur.execute("""SELECT l.doc_id, lower(coalesce(d.original_filename,'')) AS fn,
                          left(lower(coalesce(d.extracted_text,'')), 3000) AS txt,
                          coalesce(l.provenance_level,'') AS prov
                   FROM document_matter_links l JOIN documents d ON d.id = l.doc_id
                   WHERE l.matter_code = %s ORDER BY l.doc_id""", (matter_code,))
    return cur.fetchall()


def seed(matter_code, go=False):
    c = _conn(); cur = c.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    _ensure(cur)
    cur.execute("SELECT matter_type, legal_theory, title FROM matters WHERE matter_code=%s", (matter_code,))
    m = cur.fetchone()
    if not m:
        cur.close(); c.close(); return {"matter": matter_code, "error": "no such matter"}
    fw = resolve_framework(m["matter_type"], m["legal_theory"], m["title"])
    docs = _linked_docs(cur, matter_code)
    out = {"matter": matter_code, "framework": fw, "elements": [], "n_docs": len(docs)}
    for code, prio, label, kws in FRAMEWORKS[fw]:
        support, verified = [], False
        for d in docs:
            hay = d["fn"] + " " + d["txt"]
            if any(k in hay for k in kws):
                support.append(d["doc_id"])
                if d["prov"] == "verified":
                    verified = True
        support = support[:15]
        status = "missing" if not support else ("have" if (verified or len(support) >= 2) else "partial")
        gap = None if support else "no linked document matches this element — collect/link evidence"
        out["elements"].append({"code": code, "priority": prio, "status": status, "n": len(support)})
        if go:
            cur.execute("""INSERT INTO matter_elements
                (matter_code, framework_key, element_code, priority, label, status, n_support,
                 supporting_doc_ids, any_verified, gap_note, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (matter_code, element_code) DO UPDATE SET
                    framework_key=EXCLUDED.framework_key, priority=EXCLUDED.priority, label=EXCLUDED.label,
                    status=EXCLUDED.status, n_support=EXCLUDED.n_support,
                    supporting_doc_ids=EXCLUDED.supporting_doc_ids, any_verified=EXCLUDED.any_verified,
                    gap_note=EXCLUDED.gap_note, updated_at=now()""",
                (matter_code, fw, code, prio, label, status, len(support), support, verified, gap))
    cur.close(); c.close()
    return out


def seed_all(go=False):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT matter_code FROM matters ORDER BY matter_code")
    codes = [r[0] for r in cur.fetchall()]
    cur.close(); c.close()
    tot_gaps = 0
    for mc in codes:
        r = seed(mc, go=go)
        if "elements" in r:
            gaps = sum(1 for e in r["elements"] if e["status"] == "missing")
            tot_gaps += gaps
            print(f"  {mc:<26} {r['framework']:<22} docs={r['n_docs']:<4} gaps={gaps}/{len(r['elements'])}")
    print(f"[matter_elements] {'WROTE' if go else 'DRY'} matters={len(codes)} total_gaps={tot_gaps}")


def matrix(matter_code):
    c = _conn(); cur = c.cursor()
    cur.execute("""SELECT element_code, priority, status, n_support, supporting_doc_ids, label, gap_note
                   FROM matter_elements WHERE matter_code=%s ORDER BY priority DESC, element_code""", (matter_code,))
    rows = cur.fetchall()
    if not rows:
        print(f"no matrix for {matter_code} — run --seed {matter_code} --go"); cur.close(); c.close(); return
    cur.execute("SELECT framework_key FROM matter_elements WHERE matter_code=%s LIMIT 1", (matter_code,))
    fw = cur.fetchone()[0]
    print(f"\nEVIDENCE MATRIX — {matter_code}  (framework: {fw})\n" + "=" * 72)
    cov = 0
    for code, prio, status, n, docs, label, gap in rows:
        if status != "missing":
            cov += 1
        mark = {"have": "✓ HAVE   ", "partial": "~ PARTIAL", "missing": "✗ MISSING"}[status]
        cells = (", ".join(f"#{d}" for d in (docs or [])[:10])) if docs else (gap or "")
        print(f" [{prio}] {mark}  {code:<20} {label}")
        print(f"        evidence: {cells}")
    print("-" * 72)
    print(f" coverage: {cov}/{len(rows)} elements have evidence · {len(rows)-cov} gap(s)")
    cur.close(); c.close()


def summary():
    c = _conn(); cur = c.cursor()
    cur.execute("""SELECT e.matter_code, max(e.framework_key),
                   count(*) AS n_el,
                   count(*) FILTER (WHERE e.status='missing') AS gaps,
                   count(*) FILTER (WHERE e.status='have') AS have
                   FROM matter_elements e GROUP BY e.matter_code ORDER BY gaps DESC, n_el DESC""")
    rows = cur.fetchall()
    print(f"{'MATTER':<26}{'FRAMEWORK':<22}{'ELEMS':>6}{'HAVE':>6}{'GAPS':>6}  coverage")
    for mc, fw, n_el, gaps, have in rows:
        bar = "█" * have + "·" * (n_el - have)
        print(f"{mc:<26}{(fw or ''):<22}{n_el:>6}{have:>6}{gaps:>6}  {bar}")
    cur.close(); c.close()


if __name__ == "__main__":
    a = sys.argv
    if "--seed-all" in a:
        seed_all(go="--go" in a)
    elif "--seed" in a:
        import json
        print(json.dumps(seed(a[a.index("--seed") + 1], go="--go" in a), indent=2))
    elif "--matrix" in a:
        matrix(a[a.index("--matrix") + 1])
    elif "--summary" in a:
        summary()
    else:
        print(__doc__)
