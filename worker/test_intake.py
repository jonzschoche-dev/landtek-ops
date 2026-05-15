"""End-to-end smoke test for the LEAN pipeline:
  Pass 1 XML -> Pass 2 intake (entity+classify+execution) -> Pass 4 synthesis memo.

Reads from /root/landtek/pass1_out/, writes intake JSON to /root/landtek/intake_out/
and memos to /root/landtek/memo_out/.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import active_provider
from intake import pass2_intake
from synthesis import pass4_synthesis


def load_cases_from_postgres():
    try:
        import psycopg2
        from config import PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
        conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DATABASE,
                                user=PG_USER, password=PG_PASSWORD)
        cur = conn.cursor()
        cur.execute("""SELECT case_file, client_name, current_goals, intelligence_summary, key_risks
                       FROM cases""")
        cases = []
        for row in cur.fetchall():
            cases.append({
                "case_file": row[0], "client_name": row[1],
                "current_goals": row[2], "intelligence_summary": row[3], "key_risks": row[4]
            })
        cur.close(); conn.close()
        return cases
    except Exception as e:
        print(f"  cases load failed: {e}")
        return []


def main():
    print(f"LLM provider: {active_provider()}")
    deep_mode = "--deep" in sys.argv
    print(f"Deep mode: {deep_mode}")
    cases = load_cases_from_postgres()
    print(f"Loaded {len(cases)} active cases: {[c['case_file'] for c in cases]}")

    xml_dir = Path("/root/landtek/pass1_out")
    intake_dir = Path("/root/landtek/intake_out"); intake_dir.mkdir(exist_ok=True)
    memo_dir = Path("/root/landtek/memo_out"); memo_dir.mkdir(exist_ok=True)

    xmls = sorted(xml_dir.glob("*.xml"))
    print(f"Found {len(xmls)} XML files")

    for xml_path in xmls:
        print(f"\n{'='*72}\n{xml_path.name}\n{'='*72}")
        xml = xml_path.read_text()

        # Pass 2: intake
        try:
            intake = pass2_intake(xml, cases)
        except Exception as e:
            print(f"  INTAKE FAILED: {type(e).__name__}: {e}")
            continue
        intake_file = intake_dir / (xml_path.stem + ".json")
        intake_file.write_text(json.dumps(intake, indent=2))

        cls = intake.get("classification", {})
        meta = intake.get("document_meta", {})
        ex = intake.get("execution_status", {})
        ents = intake.get("entities", {})
        print(f"  → case_file: {cls.get('case_file')} (conf {cls.get('confidence')})")
        print(f"  → reasoning: {(cls.get('reasoning') or '')[:200]}")
        print(f"  → doc_type: {meta.get('document_type')} | date: {meta.get('document_date')}")
        print(f"  → smart_filename: {meta.get('smart_filename')}")
        print(f"  → execution: {ex.get('completion_state')} (signed={ex.get('is_signed')}, notarized={ex.get('is_notarized')})")
        if ex.get("notary", {}).get("name"):
            n = ex["notary"]
            print(f"     notary: {n.get('name')} (Comm. {n.get('commission_number')}) Doc {n.get('doc_no')}/Pg {n.get('page_no')}/Bk {n.get('book_no')}/Sr {n.get('series_of')}")
        print(f"  → entities: {len(ents.get('people',[]))} people, {len(ents.get('organizations',[]))} orgs, "
              f"{len(ents.get('reference_numbers',[]))} ref#s, {len(ents.get('dates',[]))} dates")
        ref_missing = [r for r in ents.get("document_references", []) if not r.get("is_attached")]
        if ref_missing:
            print(f"  → REFERENCED BUT MISSING ({len(ref_missing)}):")
            for r in ref_missing[:5]:
                print(f"     - {r.get('reference')}: {r.get('what_it_is','')}")
        print(f"  → novelty_score: {intake.get('novelty_score')}")

        # Pass 4: synthesis
        try:
            memo = pass4_synthesis(xml, intake, deep_mode=deep_mode)
        except Exception as e:
            print(f"  SYNTHESIS FAILED: {type(e).__name__}: {e}")
            continue
        memo_file = memo_dir / (xml_path.stem + ".memo.json")
        memo_file.write_text(json.dumps(memo, indent=2))

        print(f"\n  MEMO:")
        print(f"  Headline: {memo.get('headline')}")
        print(f"  Action required: {memo.get('owner_action_required')}")
        print(f"  Executive summary: {memo.get('executive_summary')}")
        if memo.get("key_facts"):
            print(f"  Key facts:")
            for f in memo["key_facts"][:5]:
                print(f"    - {f}")
        if memo.get("questions_raised"):
            print(f"  Questions raised:")
            for q in memo["questions_raised"]:
                print(f"    - {q}")
        if memo.get("procedural_dates"):
            print(f"  Procedural dates:")
            for d in memo["procedural_dates"]:
                print(f"    - {d.get('date')}: {d.get('event')} → {d.get('implication')}")
        print(f"  Strategic implication: {memo.get('strategic_implication')}")
        print(f"\n  -> intake: {intake_file}")
        print(f"  -> memo:   {memo_file}")


if __name__ == "__main__":
    main()
