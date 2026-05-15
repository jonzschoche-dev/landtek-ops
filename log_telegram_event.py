#!/usr/bin/env python3
"""
Fixed logging function for Leo 1.0
Now correctly reads JSON from stdin when called from n8n Code node.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
import sys

LOG_DIR = Path("/root/landtek/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
TELEGRAM_LOG = LOG_DIR / "telegram_activity.log"

logging.basicConfig(
    filename=TELEGRAM_LOG,
    level=logging.INFO,
    format="%(asctime)s | %(message)s"
)

def log_telegram_event(data: dict):
    entry = {
        "timestamp": datetime.now().isoformat(),
        **data
    }
    logging.info(json.dumps(entry, ensure_ascii=False))
    return {"status": "logged", "sender_id": data.get("sender_id")}

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        try:
            data = json.loads(raw)
            result = log_telegram_event(data)
            print(json.dumps(result))
        except Exception as e:
            print(json.dumps({"status": "error", "message": str(e)}))
    else:
        print("log_telegram_event() is ready to be called from n8n.")
