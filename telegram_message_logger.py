#!/usr/bin/env python3
"""
Simple Telegram message logger for Leo 1.0 debugging.
This will help us see exactly what messages are coming in from Don Qi Style.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("/root/landtek/logs/telegram_messages.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(message)s"
)

def log_telegram_message(sender_id: int, sender_name: str, text: str, has_file: bool, case_file: str = None):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "sender_id": sender_id,
        "sender_name": sender_name,
        "text": text[:500] if text else "",
        "has_file": has_file,
        "case_file": case_file
    }
    logging.info(json.dumps(entry, ensure_ascii=False))

if __name__ == "__main__":
    print("Telegram message logger created. Use log_telegram_message() in n8n or other scripts.")
