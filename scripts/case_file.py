#!/usr/bin/env python3
"""case_file.py — the single, ALWAYS-CURRENT case-file history for a matter. $0.

Reads the case_timeline view (every document + correspondence event + deadline for the matter, live —
no rebuild, no staleness) and prints ONE clean, dated, chronological history. No re-assembly per question.

  python3 case_file.py MWK-ARTA-1321        # one matter, retrieved in one call
  python3 case_file.py --all                 # write case_files/<MATTER>.txt for every matter
"""
import os, sys
import psycopg2, psycopg2.extras

DSN = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")


def _cur():
    return psycopg2.connect(DSN).cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def render(cur, matter):
    cur.execute("SELECT coalesce(title,court_or_agency,forum,'') t, coalesce(docket_number,'') dk "
                "FROM matters WHERE matter_code=%s", (matter,))
    m = cur.fetchone() or {"t": "", "dk": ""}
    cur.execute("SELECT DISTINCT event_date, event_type, title, ref, link FROM case_timeline WHERE matter=%s", (matter,))
    rows = cur.fetchall()
    rows.sort(key=lambda r: (r["event_date"] or "9999-99-99", r["ref"]))
    dated = [r for r in rows if r["event_date"]]
    last = dated[-1]["event_date"] if dated else "—"
    cur.execute("SELECT due_date, title, status FROM case_deadlines WHERE case_file=%s AND status='pending' ORDER BY due_date", (matter,))
    dls = cur.fetchall()

    out = ["━" * 66, f"CASE FILE · {matter}"]
    if m["t"]:
        out.append(m["t"][:84] + (f"   ·   {m['dk']}" if m["dk"] else ""))
    out.append(f"{len(rows)} events on file · last update {last}")
    if dls:
        out.append("OPEN DEADLINES: " + "  |  ".join(f"{d['due_date']} — {d['title'][:40]}" for d in dls))
    out.append("━" * 66)
    year = None
    for r in rows:
        yr = r["event_date"][:4] if r["event_date"] else "(undated)"
        if yr != year:
            year = yr
            out.append(f"\n  {yr}")
        out.append(f"    {(r['event_date'] or '          '):10}  {r['event_type'][:12]:12}  {r['title'][:54]}"
                   + (f"   {r['link']}" if r["link"] else ""))
    return "\n".join(out)


def main():
    cur = _cur()
    if "--all" in sys.argv:
        cur.execute("SELECT DISTINCT matter FROM case_timeline WHERE matter IS NOT NULL ORDER BY matter")
        os.makedirs("/root/landtek/case_files", exist_ok=True)
        n = 0
        for row in cur.fetchall():
            open(f"/root/landtek/case_files/{row['matter']}.txt", "w").write(render(cur, row["matter"]))
            n += 1
        print(f"[case_file] wrote {n} case files -> /root/landtek/case_files/")
        return
    matter = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    if not matter:
        sys.exit("usage: case_file.py <MATTER> | --all")
    print(render(cur, matter))


if __name__ == "__main__":
    main()
