#!/usr/bin/env python3
"""jurisprudence_steward.py — keep the SHARED LandTek law library growing for ALL clients & matters.

The legal corpus (statutes + jurisprudence) is ONE firm-wide asset: law is common, so a case enriches
every matter that draws on it — only FACTS are client-separated. This steward keeps that shared library
self-auditing and current across the whole book of business, on a timer, at $0:

  --gap-scan   For every active matter (all clients), compare its legal theory to its case-law coverage;
               write a prioritized jurisprudence_wishlist (dark/thin/covered + the doctrines to research).
               Deterministic. This is the queue the assisted AnyCase sessions burn down.
  --harvest    Pull the month's NEW Supreme Court decisions from lawphil's index, keep only those relevant
               to our practice domains (property/agency/donation/agrarian/mining/admin), and embed them into
               the shared library so retrieval is always current. Dry-run unless --apply. Idempotent.
  --board      Phone-friendly firm-wide coverage scorecard + top dark matters + wishlist.

  python3 scripts/jurisprudence_steward.py --gap-scan
  python3 scripts/jurisprudence_steward.py --harvest --apply --max 60          # current month
  python3 scripts/jurisprudence_steward.py --harvest --year 2026 --month 6 --apply
  python3 scripts/jurisprudence_steward.py --board

NOTE the division of labor: ingest/gap-scan/harvest are autonomous (headless, $0). The doctrinal FINDER
(AnyCase) needs a logged-in browser, so wishlist items get depth in assisted sessions — not on the timer.
"""
from __future__ import annotations
import argparse
import datetime
import re
import sys

sys.path.insert(0, "/root/landtek"); sys.path.insert(0, "/root/landtek/scripts")
import ingest_jurisprudence as ij   # reuse verified fetch/verify/embed/upsert
import legal_authority as la        # _conn/_chunks/_embed

# Practice-domain keyword sets — a new SC decision is HARVESTED only if it touches our work (firm-wide,
# across every client). tag -> (forum bucket for legal_chunks, [keywords]).
DOMAINS = {
    "property":      ("CIVIL",     ["torrens", "certificate of title", "reconveyance", "reivindicatoria",
                                     "accion publiciana", "quieting of title", "land registration", "pd 1529",
                                     "innocent purchaser", "double sale", "annulment of title"]),
    "agency_sale":   ("CIVIL",     ["special power of attorney", "power of attorney", "deed of sale", "forgery",
                                     "forged", "article 1874", "article 1544", "article 1878", "agent exceeded"]),
    "donation_est":  ("CIVIL",     ["donation", "article 749", "settlement of estate", "guardian", "ward",
                                     "intestate", "partition", "heirs", "extrajudicial settlement"]),
    "agrarian":      ("DAR-DARAB", ["agrarian", "just compensation", "comprehensive agrarian", "r.a. 6657",
                                     "ra 6657", "special agrarian court", "land bank", "coverage under carp"]),
    "mining":        ("MINING",    ["mining", "mineral", "mpsa", "exploration permit", "r.a. 7942", "ra 7942",
                                     "regalian", "fpic", "ancestral domain", "mines adjudication"]),
    "admin_redtape": ("ARTA",      ["ease of doing business", "r.a. 11032", "ra 11032", "anti-red tape",
                                     "mandamus", "ministerial duty", "grave misconduct", "administrative liability"]),
    "lgu":           ("DILG",      ["local government", "expropriation", "eminent domain", "sangguniang",
                                     "public use without", "taking of private property"]),
}
HARVEST_MIN_SCORE = 2   # a decision must hit >=2 distinct domains' keywords to be embedded (relevance gate)

# theory-text -> the doctrines an assisted AnyCase session should research (feeds the wishlist)
THEORY_MAP = [
    (r"donation|art\.?\s*749|lgu.*recover|expropriat", "void donation (Art. 749) + just-compensation/taking (Mariano v. Naga)"),
    (r"agrarian|6657|just compensation|carp",          "just compensation + Special Agrarian Court jurisdiction (RA 6657)"),
    (r"mining|mpsa|exploration|apsa|expa|tenement",     "mining rights perfection (RA 7942), FPIC/NCIP, Regalian doctrine"),
    (r"guardian|incompeten|ward",                       "guardian's authority to sell ward's property (needs court approval)"),
    (r"spa|power of attorney|void.?deed|de la fuente|agency", "void agency/SPA sale (Arts. 1874/1878), forged-deed conveys no title"),
    (r"reinvindicat|reivindicat|accion|title.?chain|tct|recover", "accion reivindicatoria elements; direct vs collateral attack (Sec 48 PD 1529)"),
    (r"ejectment|unlawful detainer|forcible|summary proc", "ejectment/Summary Procedure — provisional ownership vs title"),
    (r"11032|arta|red.?tape|penro|assessor|inaction|undue delay", "RA 11032 duties; mandamus; administrative liability of officers"),
    (r"criminal|murder|9221|3019|graft|malversation",   "elements + Ombudsman/RPC public-officer liability; probable cause"),
    (r"family|conjugal|partition|succession|estate",    "succession/partition; conjugal-property disposition rules"),
    (r"quiet",                                          "quieting of title (Arts. 476-477) requisites"),
]


def _client(code: str) -> str:
    if code.startswith("MWK"):
        return "MWK"
    if code.startswith("PAR") or "INOCALLA" in code:
        return "Paracale/Inocalla"
    if code.startswith("NIBDC"):
        return "NIBDC"
    return "other"


def _suggest(theory: str, mtype: str) -> list[str]:
    hay = f"{theory} {mtype}".lower()
    out = [label for rx, label in THEORY_MAP if re.search(rx, hay)]
    return out or ["identify the controlling SC decisions for this matter's cause of action"]


def _ensure_wishlist(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS jurisprudence_wishlist (
        matter_code text PRIMARY KEY, client text, matter_type text, theory text,
        case_law_count int, coverage text, suggested_doctrines text[], priority int,
        updated_at timestamptz DEFAULT now())""")


def gap_scan():
    c = la._conn(); cur = c.cursor(); _ensure_wishlist(cur)
    cur.execute("""
        SELECT m.matter_code, coalesce(m.matter_type,''), coalesce(m.legal_theory,''),
               count(DISTINCT ma.authority_id) FILTER (WHERE lax.authority_type='case') AS cases
        FROM matters m
        LEFT JOIN matter_authorities ma ON ma.matter_code=m.matter_code
        LEFT JOIN legal_authorities lax ON lax.id=ma.authority_id
        WHERE m.status NOT IN ('closed','archived','out_of_scope','pending_triage')
        GROUP BY m.matter_code, m.matter_type, m.legal_theory
        ORDER BY cases ASC, m.matter_code""")
    rows = cur.fetchall()
    dark = thin = covered = 0
    for code, mtype, theory, cases in rows:
        cov = "dark" if cases == 0 else ("thin" if cases <= 2 else "covered")
        # priority: dark civil/recovery/property/criminal = 1; dark admin = 2; thin = 2; covered = 3
        admin = bool(re.search(r"admin|arta|red.?tape", f"{mtype} {theory}".lower()))
        prio = 3 if cov == "covered" else (2 if (cov == "thin" or admin) else 1)
        sugg = _suggest(theory, mtype)
        cur.execute("""INSERT INTO jurisprudence_wishlist
            (matter_code, client, matter_type, theory, case_law_count, coverage, suggested_doctrines, priority, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (matter_code) DO UPDATE SET client=EXCLUDED.client, matter_type=EXCLUDED.matter_type,
              theory=EXCLUDED.theory, case_law_count=EXCLUDED.case_law_count, coverage=EXCLUDED.coverage,
              suggested_doctrines=EXCLUDED.suggested_doctrines, priority=EXCLUDED.priority, updated_at=now()""",
            (code, _client(code), mtype, theory[:2000], cases, cov, sugg, prio))
        dark += cov == "dark"; thin += cov == "thin"; covered += cov == "covered"
    print(f"[gap-scan] {len(rows)} active matters — dark:{dark} thin:{thin} covered:{covered} "
          f"(wishlist refreshed {datetime.datetime.utcnow():%Y-%m-%dT%H:%MZ})")


def _index_url(y, m):
    mon = ij._ALLMON[m - 1]
    return f"https://lawphil.net/judjuris/juri{y}/{mon}{y}/{mon}{y}.html"


def _relevance(text: str):
    low = text.lower()
    hits = {tag: sum(low.count(k) for k in kws) for tag, (_, kws) in DOMAINS.items()}
    tags = [t for t, n in hits.items() if n > 0]
    score = len(tags)
    forum = DOMAINS[max(hits, key=hits.get)][0] if score else "CIVIL"
    return score, tags, forum


def harvest(year, month, apply, maxn):
    idx = _index_url(year, month)
    import urllib.request
    try:
        raw = urllib.request.urlopen(urllib.request.Request(idx, headers={"User-Agent": ij._UA}),
                                     timeout=25).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"[harvest] index fetch failed {idx}: {e}"); return
    # main decision files only: gr_<digits>_<year>.html (excludes gr_<n>_<justice>.html concurring opinions)
    stems = sorted(set(re.findall(rf"gr_(\d+)_{year}\.html", raw)))
    print(f"[harvest] {idx} — {len(stems)} decisions in index; scanning (min domain-score {HARVEST_MIN_SCORE})")
    c = la._conn(); cur = c.cursor(); la._ensure(cur)
    seen = emb = skip_irr = skip_have = 0
    for d in stems:
        if maxn and emb >= maxn:
            print(f"[harvest] cap {maxn} reached"); break
        citation_like = f"G.R. No. {d} ({year})"
        cur.execute("SELECT 1 FROM legal_authorities WHERE citation ILIKE %s", (f"G.R. No. {d}%",))
        if cur.fetchone():
            skip_have += 1; continue
        url = f"https://lawphil.net/judjuris/juri{year}/{ij._ALLMON[month-1]}{year}/gr_{d}_{year}.html"
        try:
            text = ij._fetch_text(url)
        except Exception:
            continue
        seen += 1
        if len(text) < ij.MIN_DECISION_CHARS:
            continue
        score, tags, forum = _relevance(text)
        if score < HARVEST_MIN_SCORE:
            skip_irr += 1; continue
        title = _title_from(text)
        if not apply:
            print(f"  [dry] relevant (score {score} {tags}) {citation_like}  {title[:60]}")
            emb += 1; continue
        aid = ij._upsert_authority(cur, citation_like, title, "", text, url, forum)
        n = ij._embed_fulltext(cur, forum, citation_like, title, url, text)
        print(f"  ✓ harvested {citation_like} [{forum}] ({len(text)}c, {n} chunks; domains {tags})")
        emb += 1
    print(f"[harvest] {'DRY-RUN ' if not apply else ''}embedded/flagged {emb} · already-have {skip_have} · "
          f"irrelevant {skip_irr} · scanned {seen}")


def _title_from(text: str) -> str:
    # crude party-line extraction: the "X VS. Y" line near the header
    m = re.search(r"([A-Z][A-Z.,'&\- ]{4,80}?\s+V(?:S|ERSUS)?\.\s+[A-Z][A-Z.,'&\- ]{4,80})", text[:4000])
    return re.sub(r"\s+", " ", m.group(1)).title().strip() if m else "Supreme Court decision (harvested)"


def board():
    c = la._conn(); cur = c.cursor(); _ensure_wishlist(cur)
    cur.execute("SELECT count(*), sum((authority_type='case')::int) FROM legal_authorities")
    tot, cases = cur.fetchone()
    cur.execute("SELECT count(*) FROM legal_chunks")
    chunks = cur.fetchone()[0]
    print("=" * 68)
    print(f"LANDTEK LAW LIBRARY (shared, firm-wide) — {cases or 0} cases · {tot or 0} authorities · {chunks} chunks")
    print("=" * 68)
    cur.execute("""SELECT client, coverage, count(*) FROM jurisprudence_wishlist
                   GROUP BY client, coverage ORDER BY client, coverage""")
    print("\nCoverage by client:")
    for client, cov, n in cur.fetchall():
        print(f"  {client:20s} {cov:8s} {n}")
    cur.execute("""SELECT matter_code, client, case_law_count, suggested_doctrines
                   FROM jurisprudence_wishlist WHERE coverage='dark' ORDER BY priority, client, matter_code LIMIT 20""")
    print("\nTOP DARK MATTERS (no case-law yet) — assisted-session queue:")
    for code, client, n, sugg in cur.fetchall():
        s = (sugg or [""])[0]
        print(f"  [{client}] {code}  → {s}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap-scan", action="store_true")
    ap.add_argument("--harvest", action="store_true")
    ap.add_argument("--board", action="store_true")
    ap.add_argument("--apply", action="store_true", help="harvest: actually embed (default dry-run)")
    ap.add_argument("--year", type=int); ap.add_argument("--month", type=int)
    ap.add_argument("--max", type=int, default=60, help="harvest cap per run")
    a = ap.parse_args()
    if not (a.gap_scan or a.harvest or a.board):
        a.gap_scan = a.board = True  # default: audit + show
    if a.gap_scan:
        gap_scan()
    if a.harvest:
        now = datetime.datetime.utcnow()
        harvest(a.year or now.year, a.month or now.month, a.apply, a.max)
    if a.board:
        board()


if __name__ == "__main__":
    main()
