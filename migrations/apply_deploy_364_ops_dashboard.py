#!/usr/bin/env python3
"""Deploy 364 — LandTek ops dashboard v0 on leo_tools (/ops/).

- leo_tools/ops_dashboard.py: Home, Clients, MWK, Health, Search (SQL-only)
- nginx: proxy /ops/ behind same basic auth as /files/
- restart leo-tools + smoke curl
"""
from __future__ import annotations

import subprocess
import sys
import urllib.request

import psycopg2

DSN = "postgresql://n8n:n8npassword@172.18.0.3:5432/n8n"
NGINX_SITE = "/etc/nginx/sites-available/leo"
OPS_BLOCK = """
    location /ops/ {
        auth_basic "LandTek Ops";
        auth_basic_user_file /etc/nginx/htpasswd.landtek;
        proxy_pass http://127.0.0.1:8765/ops/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120;
    }
"""


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _patch_nginx() -> None:
    with open(NGINX_SITE) as f:
        body = f.read()
    if "location /ops/" in body:
        print("✓ nginx /ops/ already configured")
        return
    marker = "    location /files/ {"
    if marker not in body:
        raise RuntimeError(f"nginx marker not found in {NGINX_SITE}")
    body = body.replace(marker, OPS_BLOCK + "\n" + marker, 1)
    with open(NGINX_SITE, "w") as f:
        f.write(body)
    print("✓ nginx /ops/ block added")
    _run(["nginx", "-t"])
    _run(["systemctl", "reload", "nginx"])
    print("✓ nginx reloaded")


def _smoke() -> None:
    _run(["systemctl", "restart", "leo-tools"])
    import time

    time.sleep(2)
    with urllib.request.urlopen("http://127.0.0.1:8765/ops/", timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    if "Morning briefing" not in html:
        raise RuntimeError("ops home smoke failed — expected 'Morning briefing'")
    print("✓ /ops/ smoke OK")


def main() -> int:
    print("Deploy 364 — ops dashboard v0")
    _patch_nginx()
    _smoke()
    conn = psycopg2.connect(DSN)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO deploy_log (deploy_id, summary)
        VALUES (
          'deploy_364',
          'Ops dashboard v0: /ops/ on leo_tools (home briefing, clients, MWK lanes, health/timers, search). '
          'nginx basic-auth same as /files/. SQL-only — no LLM on dashboard pages.'
        )
        ON CONFLICT (deploy_id) DO UPDATE SET summary = EXCLUDED.summary
        """
    )
    cur.close()
    conn.close()
    print("✓ deploy_log updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())