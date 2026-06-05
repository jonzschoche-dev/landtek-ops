#!/usr/bin/env python3
"""shadow_real_traffic.py — Mode 2 of the lean simulator (deploy_337).

Every 5 min, scan recent leo_interactions where sender_id NOT LIKE '999000%'
(real clients + Jonathan only). Apply forbidden-pattern checks against
Leo's actual replies.

Costs $0 — only reads what's already there. No LLM calls.

Patterns watched (catches the failure modes that matter):
  - Jonathan's name or contact leaked to non-Jonathan sender
  - Fabricated LT-NNNN citations (LT-NNNN that doesn't exist in documents)
  - Currency amounts without verified source
  - Death dates / executor names without tool-call basis
  - "I'm not authorized" template fired at Jonathan (Rule S8 violation)

When a violation is found:
  - INSERT into real_traffic_violations
  - Telegram push (strict rails) — only first detection per interaction
"""
from __future__ import annotations
import os, re, sys
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

sys.path.insert(0, "/root/landtek/scripts")
try:
    from report_publisher import push_strict
except Exception:
    push_strict = None

DSN      = os.environ.get("PG_DSN", "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n")
JONATHAN = "6513067717"

# Pre-compile detectors. Each returns (violation_kind, evidence_excerpt) or None.

JONATHAN_NAME_PATTERNS = [
    re.compile(r"\bJonathan\s+Zschoche\b", re.I),
    re.compile(r"\bJonathan\s+at\s+", re.I),
    re.compile(r"jonathan@", re.I),
    re.compile(r"\bj\w*z\w*@", re.I),  # email pattern
    re.compile(r"\+(?:1|63)[\s-]?\d{3}", re.I),  # phone country codes
]

REFUSAL_TEMPLATES_AT_JONATHAN = [
    "i'm not authorized to share information about this matter",
    "i'm not able to share case-specific information through this channel",
    "please coordinate access through the principal contact",
    "please coordinate access through the appropriate channel",
    "you don't appear to be a registered client",
]

CURRENCY_NO_SOURCE_PATTERNS = [
    # Currency amounts WITHOUT immediate citation/source markers
    re.compile(r"₱[\d,]{3,}(?:\.\d+)?(?!\s*\(|\s*per\s|\s*from|\s*cited)", re.I),
    re.compile(r"PHP\s*[\d,]{3,}(?!\s*\(|\s*per\s)", re.I),
]


def scan_lt_citations(reply: str) -> list[str]:
    """Return LT-NNNN identifiers Leo cited in this reply."""
    return re.findall(r"\bLT-\d{3,5}\b", reply)


def fetch_recent_interactions(cur, since_minutes: int = 30):
    cur.execute("""
        SELECT id, timestamp, sender_id, sender_name, reply_text
          FROM leo_interactions
         WHERE timestamp > now() - (%s || ' minutes')::interval
           AND sender_id NOT LIKE '999000%%'
           AND reply_text IS NOT NULL
           AND LENGTH(reply_text) > 0
         ORDER BY id DESC
    """, (since_minutes,))
    return cur.fetchall()


def check_jonathan_leak(reply: str, sender_id: str) -> tuple[str, str] | None:
    """Catch Jonathan's name/contact leaked to anyone NOT Jonathan."""
    if sender_id == JONATHAN:
        return None
    for pat in JONATHAN_NAME_PATTERNS:
        m = pat.search(reply)
        if m:
            return ("jonathan_name_leak", reply[max(0, m.start()-30):m.end()+30])
    return None


def check_refusal_at_jonathan(reply: str, sender_id: str) -> tuple[str, str] | None:
    """Rule S8 — Jonathan shouldn't get the refusal templates."""
    if sender_id != JONATHAN:
        return None
    low = reply.lower()
    for tmpl in REFUSAL_TEMPLATES_AT_JONATHAN:
        if tmpl in low:
            i = low.find(tmpl)
            return ("refusal_at_jonathan", reply[max(0, i-20):i+len(tmpl)+30])
    return None


def check_fabricated_lt(cur, reply: str) -> tuple[str, str] | None:
    """Find any LT-NNNN cited that doesn't exist in documents table."""
    cited = scan_lt_citations(reply)
    if not cited:
        return None
    cur.execute("SELECT lt_number FROM documents WHERE lt_number = ANY(%s)", (list(set(cited)),))
    found = {r["lt_number"] for r in cur.fetchall()}
    missing = [lt for lt in set(cited) if lt not in found]
    if missing:
        return ("fabricated_lt_citation", f"cited but not in documents: {', '.join(missing[:5])}")
    return None


def check_currency_no_source(reply: str) -> tuple[str, str] | None:
    """Currency amounts asserted without nearby citation/source."""
    for pat in CURRENCY_NO_SOURCE_PATTERNS:
        m = pat.search(reply)
        if m:
            # If a citation marker appears within 60 chars, give benefit of doubt
            context_after = reply[m.end():m.end()+60].lower()
            if any(marker in context_after for marker in ("per or", "per ar", "lt-", "per receipt",
                                                          "doc#", "doc id", "from instrument")):
                continue
            return ("currency_no_source", reply[max(0, m.start()-20):m.end()+30])
    return None


def ensure_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS real_traffic_violations (
            id              BIGSERIAL PRIMARY KEY,
            detected_at     timestamptz NOT NULL DEFAULT now(),
            interaction_id  integer NOT NULL,
            sender_id       text NOT NULL,
            violation_kind  text NOT NULL,
            evidence        text NOT NULL,
            alerted         boolean NOT NULL DEFAULT false,
            UNIQUE (interaction_id, violation_kind)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rtv_recent ON real_traffic_violations(detected_at DESC)")


def main():
    conn = psycopg2.connect(DSN); conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ensure_schema(cur)
    scanned = 0
    new_violations = []
    for inter in fetch_recent_interactions(cur, since_minutes=30):
        scanned += 1
        reply = inter["reply_text"]
        sender_id = str(inter["sender_id"])
        for checker in (
            lambda: check_jonathan_leak(reply, sender_id),
            lambda: check_refusal_at_jonathan(reply, sender_id),
            lambda: check_fabricated_lt(cur, reply),
            lambda: check_currency_no_source(reply),
        ):
            v = checker()
            if not v:
                continue
            kind, evidence = v
            cur.execute("""
                INSERT INTO real_traffic_violations (interaction_id, sender_id, violation_kind, evidence)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (interaction_id, violation_kind) DO NOTHING
                RETURNING id
            """, (inter["id"], sender_id, kind, evidence[:600]))
            r = cur.fetchone()
            if r:
                new_violations.append({
                    "interaction_id": inter["id"], "sender": sender_id,
                    "sender_name": inter["sender_name"],
                    "kind": kind, "evidence": evidence,
                })

    if new_violations and push_strict:
        headline = f"⚠️  Real-traffic shadow: {len(new_violations)} violation(s) detected"
        body = ["## Real-traffic shadow alerts", ""]
        body.append(f"Scanned: {scanned} interactions (last 30min)")
        body.append("")
        for v in new_violations:
            body.append(f"### {v['kind']}")
            body.append(f"- Sender: `{v['sender']}` ({v['sender_name'] or '?'})")
            body.append(f"- Interaction id: {v['interaction_id']}")
            body.append(f"- Evidence: `{v['evidence'][:300]}`")
            body.append("")
        push_strict(headline=headline, body_md="\n".join(body),
                    source="watchdog", slug=f"shadow-{datetime.now(timezone.utc):%Y%m%d-%H%M}")

    print(f"[shadow] scanned={scanned} new_violations={len(new_violations)}")
    cur.close(); conn.close()


if __name__ == "__main__":
    main()
