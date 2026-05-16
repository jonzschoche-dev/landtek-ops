#!/usr/bin/env python3
"""Seed Landtek's firm-level agenda (deploy_111/112-F).

These are the Landtek strategic goals that run ALONGSIDE per-client goals.
Idempotent — only inserts if not already present.
"""
import psycopg2
DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"

GOALS = [
    {
        "goal_text": "Win Civil Case 26-360 (accion reinvindicatoria) to demonstrate accion reinvindicatoria mastery against fraudulent title chains",
        "goal_category": "flagship_case",
        "priority": "critical",
        "target_date": "2027-06-30",
    },
    {
        "goal_text": "Become the go-to PH property law firm for diaspora clients (US-based heirs of PH land)",
        "goal_category": "market",
        "priority": "high",
        "target_date": "2027-12-31",
    },
    {
        "goal_text": "Establish Camarines Norte as Landtek's core operational territory with deep title-chain coverage",
        "goal_category": "market",
        "priority": "high",
        "target_date": "2026-12-31",
    },
    {
        "goal_text": "Build a truth-graded RAG platform (Leo) that's licensable to other PH property firms — generate recurring revenue beyond legal fees",
        "goal_category": "product",
        "priority": "critical",
        "target_date": "2027-06-30",
    },
    {
        "goal_text": "Attract outside capital via investor-grade financial + operational reports — demonstrate scalability beyond founder",
        "goal_category": "capability",
        "priority": "critical",
        "target_date": "2026-12-31",
    },
    {
        "goal_text": "Set the standard for evidence-grade legal work in PH property law — every claim cited, every doc provenance-tagged",
        "goal_category": "reputation",
        "priority": "high",
        "target_date": "2027-12-31",
    },
    {
        "goal_text": "Manifest sustained monthly revenue sufficient to operate Leo + Landtek without external funding gap",
        "goal_category": "capability",
        "priority": "critical",
        "target_date": "2026-09-30",
    },
]


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor()
    new, existing = 0, 0
    for g in GOALS:
        cur.execute("""
            SELECT id FROM firm_goals
             WHERE LEFT(goal_text, 60) = LEFT(%s, 60)
             LIMIT 1
        """, (g["goal_text"],))
        if cur.fetchone():
            existing += 1
            continue
        cur.execute("""
            INSERT INTO firm_goals (goal_text, goal_category, priority, status, target_date)
            VALUES (%s,%s,%s,'active',%s)
        """, (g["goal_text"], g["goal_category"], g["priority"], g["target_date"]))
        new += 1
    print(f"  firm_goals: {new} inserted, {existing} already present")
    cur.execute("SELECT id, priority, goal_category, LEFT(goal_text,80) FROM firm_goals ORDER BY id")
    for r in cur.fetchall():
        print(f"    #{r[0]} [{r[1]:8s}/{r[2]:14s}] {r[3]}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
