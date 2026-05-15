#!/usr/bin/env python3
"""
Test script for Leo 1.0 logging.
Run this to simulate a message from Don Qi Style and verify logging works.
"""

from log_telegram_event import log_telegram_event

# Simulate a message from Don Qi Style
test_message = {
    "sender_id": 8575986732,
    "sender_name": "Don Qi Style",
    "text": "Test message from Don Qi Style - checking if logging works",
    "has_file": False,
    "attempted_case_file": "MWK-001",
    "workflow_node": "Test Script"
}

result = log_telegram_event(test_message)
print("Test completed. Result:", result)
print("Check the log at: /root/landtek/logs/telegram_activity.log")
