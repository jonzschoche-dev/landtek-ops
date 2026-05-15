#!/usr/bin/env python3
"""
Conversation logging helper for Leo 1.0
Use this to track when messages arrive and whether they get properly assigned to a case_file.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

LOG_FILE = Path("/root/landtek/logs/conversation_attempts.log")
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(message)s"
)

def log_conversation_attempt(
    sender_id: int,
    sender_name: str,
    text: str,
    has_file: bool,
    attempted_case_file: str = None,
    success: bool = False,
    error: str = None
):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "sender_id": sender_id,
        "sender_name": sender_name,
        "text_preview": text[:300] if text else "",
        "has_file": has_file,
        "attempted_case_file": attempted_case_file,
        "success": success,
        "error": error
    }
    logging.info(json.dumps(entry, ensure_ascii=False))

if __name__ == "__main__":
    print("Conversation logging helper ready.")
