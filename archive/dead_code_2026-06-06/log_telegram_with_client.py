#!/usr/bin/env python3
"""
Combined logging + client assignment for Leo 1.0
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

# Client mapping
TELEGRAM_ID_TO_CLIENT = {
    8575986732: "mwk",      # Don Qi Style
    6513067717: "owner",    # Jonathan
}

def get_client_for_telegram_id(telegram_id: int) -> str:
    return TELEGRAM_ID_TO_CLIENT.get(telegram_id)

def log_telegram_with_client(data: dict):
    sender_id = data.get("sender_id")
    client = get_client_for_telegram_id(sender_id)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "sender_id": sender_id,
        "sender_name": data.get("sender_name"),
        "text": data.get("text", "")[:300],
        "has_file": data.get("has_file", False),
        "client": client,
        "workflow_node": data.get("workflow_node", "unknown")
    }
    logging.info(json.dumps(entry, ensure_ascii=False))
    return {"status": "logged", "client": client}

if __name__ == "__main__":
    raw = sys.stdin.read().strip()
    if raw:
        data = json.loads(raw)
        result = log_telegram_with_client(data)
        print(json.dumps(result))
    else:
        print("log_telegram_with_client() ready")
