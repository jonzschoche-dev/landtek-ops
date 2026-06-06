#!/usr/bin/env python3
"""report_publisher.py — publish a markdown report + return a URL (deploy_329).

Every Telegram push that has substantive content should:
  1. Write the full content as a markdown report via publish_report()
  2. Get back a URL like https://leo.hayuma.org/reports/2026/06/05/HHMM-slug.md
  3. Send only a short headline + that URL via tg_send

Centralizes the "strict rails" pattern so push sites stay disciplined.

Report storage:
  /var/www/leo-reports/YYYY/MM/DD/HHMM-NNN-<slug>.md
  served via nginx alias /reports/ -> /var/www/leo-reports/

If nginx isn't yet wired, reports still write to disk and a temp HTTPS-less
URL is returned — alerts you to set up the serve route.
"""
from __future__ import annotations
import os, re
from datetime import datetime, timezone
from pathlib import Path

REPORTS_DIR = Path(os.environ.get("LEO_REPORTS_DIR", "/var/www/leo-reports"))
REPORTS_BASE_URL = os.environ.get("LEO_REPORTS_BASE_URL", "https://leo.hayuma.org/reports")
MAX_TELEGRAM_BODY = 280   # hard cap on Telegram body chars (link replaces the dump)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9-]+", "-", text.lower()).strip("-")
    return s[:48] or "report"


def publish_report(slug: str, body_md: str, source: str = "leo") -> str:
    """Write markdown to disk, return URL. Slug becomes part of the URL.

    Returns the URL even if it's not yet servable (nginx not configured) —
    operator can copy the file path from the URL pattern.
    """
    now = datetime.now(timezone.utc)
    date_path = now.strftime("%Y/%m/%d")
    filename = f"{now.strftime('%H%M%S')}-{slugify(slug)}.md"
    full_dir = REPORTS_DIR / date_path
    full_dir.mkdir(parents=True, exist_ok=True)
    full_path = full_dir / filename

    header = (
        f"# {slug}\n\n"
        f"_Source: {source} · generated {now.strftime('%Y-%m-%d %H:%M UTC')}_\n\n"
        f"---\n\n"
    )
    full_path.write_text(header + body_md, encoding="utf-8")
    try:
        full_path.chmod(0o644)
    except Exception:
        pass

    url = f"{REPORTS_BASE_URL.rstrip('/')}/{date_path}/{filename}"
    return url


def push_strict(headline: str, body_md: str | None = None, source: str = "watchdog",
                slug: str | None = None, force_inline: bool = False) -> str | None:
    """Wraps tg_send with strict rails:
      - headline ≤ MAX_TELEGRAM_BODY chars (truncated with ellipsis if longer)
      - if body_md is present and non-trivial, publishes report and appends URL
      - tg_send called with the wrapped text
    Returns the URL if a report was published, else None.
    """
    import sys
    sys.path.insert(0, "/root/landtek/scripts")
    try:
        from tg_send import send as tg_send
    except Exception:
        tg_send = None

    JONATHAN = "6513067717"

    url = None
    if body_md and len(body_md.strip()) > 20:
        url = publish_report(slug or "leo-report", body_md, source)

    text = headline.strip()
    if url:
        # Reserve space for the URL line
        max_body = MAX_TELEGRAM_BODY - len(url) - 12
        if len(text) > max_body:
            text = text[:max_body - 1].rstrip() + "…"
        text = f"{text}\n\nreport: {url}"
    else:
        if len(text) > MAX_TELEGRAM_BODY:
            text = text[:MAX_TELEGRAM_BODY - 1].rstrip() + "…"

    if tg_send is None:
        print(f"[push_strict] (would push)\n{text}\n")
        return url
    try:
        tg_send(JONATHAN, text, source=source,
                recipient_name="Jonathan", override_rate_limit=True)
    except Exception as e:
        print(f"[push_strict] send failed: {e}\n{text}\n")
    return url


if __name__ == "__main__":
    # Smoke test
    url = push_strict(
        headline="📋 Test push — checking strict rails",
        body_md="## Test\n\nThis is a test report.\n\n- item 1\n- item 2\n",
        source="watchdog",
        slug="rails-smoke-test",
    )
    print(f"URL: {url}")
