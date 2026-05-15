"""Smoke test for Pass 2 entity extraction.

Reads Pass 1 XML output from /root/landtek/pass1_out/, runs Pass 2 on each,
prints rich entity extraction to stdout and writes JSON to
/root/landtek/pass2_out/<name>.json.
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from llm import active_provider
from entities import pass2_extract_entities


def main():
    print(f"LLM provider: {active_provider()}")
    xml_dir = Path("/root/landtek/pass1_out")
    out_dir = Path("/root/landtek/pass2_out"); out_dir.mkdir(exist_ok=True)
    if len(sys.argv) > 1:
        xmls = [Path(sys.argv[1])]
    else:
        xmls = sorted(xml_dir.glob("*.xml"))
    print(f"Found {len(xmls)} XML file(s) in {xml_dir}")
    if not xmls:
        print("Run test_pass1.py first to populate /root/landtek/pass1_out/")
        return

    for xml_path in xmls:
        print(f"\n{'='*72}\n{xml_path.name}\n{'='*72}")
        xml = xml_path.read_text()
        try:
            entities = pass2_extract_entities(xml)
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")
            continue
        out_file = out_dir / (xml_path.stem + ".json")
        out_file.write_text(json.dumps(entities, indent=2))
        # Summary print
        for k in ("people", "organizations", "places", "dates", "amounts",
                  "reference_numbers", "document_references"):
            items = entities.get(k, [])
            print(f"  {k}: {len(items)}")
        # Print details for the meaty categories
        if entities.get("people"):
            print("\n  PEOPLE:")
            for p in entities["people"][:8]:
                title = p.get("title") or ""
                role = p.get("role") or ""
                org = p.get("organization") or ""
                sig = "[signed]" if p.get("appears_in_signature_block") else ""
                print(f"    - {title} {p.get('name')} ({role}, {org}) {sig}")
        if entities.get("organizations"):
            print("\n  ORGANIZATIONS:")
            for o in entities["organizations"][:8]:
                print(f"    - {o.get('name')} ({o.get('type')}, {o.get('jurisdiction','')})")
        if entities.get("reference_numbers"):
            print("\n  REFERENCE NUMBERS:")
            for r in entities["reference_numbers"]:
                print(f"    - {r.get('number')} [{r.get('type')}] {r.get('context','')[:80]}")
        if entities.get("dates"):
            print("\n  DATES:")
            for d in entities["dates"][:8]:
                print(f"    - {d.get('date')} ({d.get('context')}) {d.get('associated_event','')[:60]}")
        if entities.get("document_references"):
            print("\n  DOCUMENT REFERENCES (referenced-but-may-be-missing):")
            for dr in entities["document_references"]:
                attached = "ATTACHED" if dr.get("is_attached") else "*** REFERENCED, NOT ATTACHED ***"
                print(f"    - {dr.get('reference')}: {dr.get('what_it_is','')} [{attached}]")
        if entities.get("extraction_notes"):
            print("\n  NOTES:")
            for n in entities["extraction_notes"]:
                print(f"    - {n}")
        print(f"\n  full JSON -> {out_file}")


if __name__ == "__main__":
    main()
