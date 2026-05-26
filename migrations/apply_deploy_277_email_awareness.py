#!/usr/bin/env python3
"""Deploy 277 — email awareness.

Diagnosis (May 26 16:30 Manila): 352 emails ingested since May 20 went
unlinked to any matter. Three time-sensitive ARTA Orders/Resolutions landed
today (gmail_messages #38220, #38638, #38989) — Leo had no awareness.

Root cause: deploy_226 / 261 regex-linkage was BATCH-only. Gmail watcher
inserts rows with matter_codes='{}' and nothing re-runs the regex.

This deploy:

  A. Trigger: gmail_messages_autolink_matters_trigger runs the same regex
     on each INSERT and assigns matter_codes inline. From this moment
     forward, new emails arrive pre-linked.

  B. Reconcile the 352 unlinked emails by running scripts/email_briefer.py
     --only reconcile.

  C. Install systemd timer landtek-email-briefer.timer (every 15 min) that
     runs scripts/email_briefer.py — reconcile + critical push + 7am daily
     digest.

  D. Extend ACTIVE LANDSCAPE with recent_email_subjects (last 24h, top 5)
     so Leo sees them in every turn's context.

  E. Force one critical-push pass now to surface the 3 ARTA Orders that
     already landed today.

Idempotent. Audited via app.actor='jonathan_deploy_277'.
"""
import json
import os
import subprocess
import sys

import psycopg2
import psycopg2.extras

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
WORKFLOW_ID = "vSDQv1vfn6627bnA"

SERVICE_UNIT = "/etc/systemd/system/landtek-email-briefer.service"
TIMER_UNIT = "/etc/systemd/system/landtek-email-briefer.timer"

SERVICE_CONTENT = """[Unit]
Description=LandTek email briefer (auto-link + critical push + daily digest)
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/root/landtek
ExecStart=/usr/bin/python3 /root/landtek/scripts/email_briefer.py
StandardOutput=append:/var/log/landtek/email_briefer.log
StandardError=append:/var/log/landtek/email_briefer.log
"""

TIMER_CONTENT = """[Unit]
Description=Run LandTek email briefer every 15 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=15min
AccuracySec=15s
Unit=landtek-email-briefer.service

[Install]
WantedBy=timers.target
"""

# ─── A. Inline auto-link trigger on gmail_messages ───────────────────────
TRIGGER_SQL = r"""
-- deploy_277: auto-assign matter_codes on every gmail_messages INSERT.
-- Mirrors the regex from deploy_226 / 261. Validates against matters table.

CREATE OR REPLACE FUNCTION gmail_autolink_matters()
RETURNS TRIGGER AS $$
DECLARE
    haystack TEXT;
    sender_lower TEXT;
    mc_set TEXT[] := ARRAY[]::TEXT[];
    candidate TEXT;
    suffix TEXT;
    m RECORD;
    valid_codes TEXT[];
BEGIN
    -- Only act if matter_codes is empty
    IF cardinality(COALESCE(NEW.matter_codes, '{}'::text[])) > 0 THEN
        RETURN NEW;
    END IF;

    haystack := COALESCE(NEW.from_addr,'') || ' ' || COALESCE(NEW.subject,'') || ' ' || COALESCE(NEW.body_plain,'');
    sender_lower := LOWER(COALESCE(NEW.from_addr,''));

    -- Sender-based defaults
    IF sender_lower LIKE '%barandon_lawoffice%' THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    IF sender_lower LIKE '%colenacious%'        THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    IF sender_lower LIKE '%dilgcamarinesnorte%' THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    IF sender_lower LIKE '%litigationdivision@arta%' THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    IF sender_lower LIKE '%lourdestotanes%'     THEN mc_set := mc_set || 'MWK-CV26360'; END IF;

    -- CTN SL-YYYY-MMDD-NNNN → MWK-ARTA-<4-digit suffix>
    FOR m IN
        SELECT (regexp_matches(haystack,
                '\bCTN\s*[-:]?\s*SL\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{4})\s*[-]?\s*(\d{3,4})\b',
                'gi'))[3] AS s
    LOOP
        suffix := m.s;
        IF length(suffix) = 3 THEN suffix := '0' || suffix; END IF;
        candidate := 'MWK-ARTA-' || suffix;
        IF NOT (candidate = ANY(mc_set)) THEN
            mc_set := mc_set || candidate;
        END IF;
    END LOOP;

    -- Known Civil Case patterns
    IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*26-?360' THEN
        IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    END IF;
    IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*6839' THEN
        IF NOT ('MWK-CV6839' = ANY(mc_set)) THEN mc_set := mc_set || 'MWK-CV6839'; END IF;
    END IF;
    IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*13-?131220' THEN
        IF NOT ('PAR-CV13-131220' = ANY(mc_set)) THEN mc_set := mc_set || 'PAR-CV13-131220'; END IF;
    END IF;
    IF haystack ~* '(civil\s+case|cv|case)\s+(no\.?)?\s*-?\s*8563' THEN
        IF NOT ('MWK-CV26360' = ANY(mc_set)) THEN mc_set := mc_set || 'MWK-CV26360'; END IF;
    END IF;

    -- Filter against valid matters
    IF cardinality(mc_set) > 0 THEN
        SELECT array_agg(DISTINCT mc) INTO valid_codes
          FROM unnest(mc_set) mc
         WHERE mc IN (SELECT matter_code FROM matters);
        IF cardinality(COALESCE(valid_codes, '{}'::text[])) > 0 THEN
            NEW.matter_codes := valid_codes;
            -- relevance_reasons audit trail
            NEW.relevance_reasons := COALESCE(NEW.relevance_reasons, '{}'::text[])
                                     || ARRAY['deploy_277:trigger_autolink'];
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS gmail_messages_autolink_matters_trigger ON gmail_messages;
CREATE TRIGGER gmail_messages_autolink_matters_trigger
    BEFORE INSERT ON gmail_messages
    FOR EACH ROW
    EXECUTE FUNCTION gmail_autolink_matters();
"""

# ─── D. ACTIVE LANDSCAPE extension ───────────────────────────────────────
EMAIL_LANDSCAPE_SQL = r""", -- EMAIL (deploy_277) -----------------------------------------------------
  (
    SELECT json_agg(em ORDER BY ingested_at DESC)
    FROM (
      SELECT id, ingested_at, from_name, from_addr, subject, matter_codes
        FROM gmail_messages
       WHERE ingested_at >= now() - INTERVAL '24 hours'
       ORDER BY ingested_at DESC
       LIMIT 8
    ) em
  ) as recent_emails_24h"""

# Insertion point in SQL: after "as now_manila" line, before "FROM clients c"
NEW_CONTEXT_EMAIL_BLOCK = r"""
const recentEmails = clientRow?.recent_emails_24h || [];
const emailBlock = recentEmails.length === 0
  ? '  (no inbound in last 24h)'
  : recentEmails.slice(0, 8).map(em => {
      const mc = (em.matter_codes && em.matter_codes.length) ? '[' + em.matter_codes.join(',') + ']' : '[UNLINKED]';
      const when = (em.ingested_at || '').replace('T',' ').substr(0,16);
      const who = (em.from_name || em.from_addr || '?').substr(0,40);
      return '  ' + when + ' ' + mc + ' ' + (em.subject || '(no subject)').substr(0,80) + '\n      from ' + who;
    }).join('\n');
"""


def patch_landscape_sql(cur):
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    for n in nodes:
        if n.get("name") == "Execute a SQL query" and n.get("type") == "n8n-nodes-base.postgres":
            old = n.get("parameters", {}).get("query", "")
            if "recent_emails_24h" in old:
                print("  Execute a SQL query: recent_emails_24h already present (no-op)")
                return False
            # Insert before "FROM clients c"
            anchor = "FROM clients c"
            idx = old.rfind(anchor)
            if idx < 0:
                print("  Execute a SQL query: anchor not found")
                return False
            # Find the previous newline that ends with closing ) and "as now_manila" likely
            # Insert email JSON aggregate just before FROM clients c
            new = old[:idx] + EMAIL_LANDSCAPE_SQL + "\n" + old[idx:]
            n["parameters"]["query"] = new
            print(f"  Execute a SQL query: {len(old)} -> {len(new)} chars (email aggregate added)")
            break
    else:
        return False

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    return True


def patch_context_builder(cur):
    cur.execute("SELECT nodes FROM workflow_entity WHERE id = %s", (WORKFLOW_ID,))
    nodes = cur.fetchone()["nodes"]
    if isinstance(nodes, str):
        nodes = json.loads(nodes)

    for n in nodes:
        if n.get("name") == "Context Builder" and n.get("type") == "n8n-nodes-base.code":
            old = n.get("parameters", {}).get("jsCode", "")
            if "recent_emails_24h" in old or "emailBlock" in old:
                print("  Context Builder: email block already present (no-op)")
                return False

            # Insert the var declarations right after the calendar block
            anchor_var = "const calFollowupBlock"
            idx = old.find(anchor_var)
            if idx < 0:
                print("  Context Builder: calFollowupBlock anchor missing — skipping email block")
                return False
            # Find end of that line
            eol = old.find("\n", idx)
            # Then find the next line ending with "; (the calFollowupBlock = ... ; line)
            close_idx = old.find("';", eol)
            if close_idx < 0:
                close_idx = old.find("';\n", eol)
            # Just find the end of the const calFollowupBlock = ... ; statement
            # Simpler: find the next blank line after that variable
            blank_idx = old.find("\n\n", eol)
            if blank_idx < 0:
                blank_idx = eol + 200
            insert_at = blank_idx
            new = old[:insert_at] + "\n" + NEW_CONTEXT_EMAIL_BLOCK.lstrip() + old[insert_at:]

            # Now also weave emailBlock into the activeLandscape template literal
            # Add a section before "Open matters with next-event"
            anchor_template = "Open matters with next-event / deadline:"
            if anchor_template in new:
                new = new.replace(
                    anchor_template,
                    "Inbox (last 24h):\n${emailBlock}\n\n" + anchor_template,
                    1,
                )

            n["parameters"]["jsCode"] = new
            print(f"  Context Builder: {len(old)} -> {len(new)} chars (email block injected)")
            break
    else:
        return False

    cur.execute(
        "UPDATE workflow_entity SET nodes = %s::json, \"updatedAt\" = now() WHERE id = %s",
        (json.dumps(nodes), WORKFLOW_ID),
    )
    return True


def install_timer():
    os.makedirs("/var/log/landtek", exist_ok=True)
    with open(SERVICE_UNIT, "w") as f:
        f.write(SERVICE_CONTENT)
    os.chmod(SERVICE_UNIT, 0o644)
    with open(TIMER_UNIT, "w") as f:
        f.write(TIMER_CONTENT)
    os.chmod(TIMER_UNIT, 0o644)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now",
                    "landtek-email-briefer.timer"], check=False)
    print("  systemd timer installed + enabled")


def main():
    if os.geteuid() != 0:
        print("Run as root")
        sys.exit(1)

    conn = psycopg2.connect(DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET LOCAL app.actor = 'jonathan_deploy_277'")

    print("Deploy 277 — email awareness")
    print("=" * 60)

    print("\n[A] Install gmail_autolink_matters trigger")
    cur.execute(TRIGGER_SQL)
    conn.commit()
    print("  trigger installed")

    print("\n[B] email_briefs_sent schema")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS email_briefs_sent (
            id              SERIAL PRIMARY KEY,
            email_id        INTEGER REFERENCES gmail_messages(id) ON DELETE CASCADE,
            brief_type      TEXT NOT NULL CHECK (brief_type IN ('critical_push','daily_digest')),
            brief_date      DATE,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            telegram_ok     BOOLEAN,
            UNIQUE (email_id, brief_type),
            UNIQUE (brief_type, brief_date)
        );
        CREATE INDEX IF NOT EXISTS idx_email_briefs_email ON email_briefs_sent(email_id);
    """)
    conn.commit()
    print("  email_briefs_sent table ensured")

    print("\n[C] systemd timer install")
    install_timer()

    print("\n[D] Execute a SQL query — add recent_emails_24h")
    patch_landscape_sql(cur)

    print("\n[E] Context Builder — inject email block")
    patch_context_builder(cur)
    conn.commit()
    cur.close()
    conn.close()

    print("\n[F] sync workflow_history + webhook + smoke")
    for cmd in (
        ["python3", "/root/landtek/scripts/sync_workflow_history.py", WORKFLOW_ID],
        ["python3", "/root/landtek/scripts/sync_telegram_webhook.py"],
        ["python3", "/root/landtek/scripts/post_deploy_smoke.py"],
    ):
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = (r.stdout.strip().split("\n") or [""])[-1]
        print(f"  {' '.join(cmd[-2:])}: {out[-150:]}")

    print("\n[G] Reconcile 352 unlinked emails")
    r = subprocess.run(
        ["python3", "/root/landtek/scripts/email_briefer.py", "--only", "reconcile"],
        capture_output=True, text=True,
    )
    print("  " + r.stdout.strip().replace("\n", "\n  ")[-500:])

    print("\n[H] Critical-push pass (3-hour lookback to surface today's ARTA Orders)")
    r = subprocess.run(
        ["python3", "/root/landtek/scripts/email_briefer.py", "--only", "critical",
         "--window-min", "180"],
        capture_output=True, text=True,
    )
    print("  " + r.stdout.strip().replace("\n", "\n  ")[-500:])


if __name__ == "__main__":
    main()
