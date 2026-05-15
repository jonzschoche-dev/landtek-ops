#!/usr/bin/env python3
"""
Telegram ID → Client mapping for Leo 1.0
This is the correct foundation (client-level, not just case-level).
"""

# Mapping: Telegram ID → client_slug
TELEGRAM_ID_TO_CLIENT = {
    8575986732: "mwk",           # Don Qi Style → MWK client (Heirs of Mary Worrick Keesey)
    6513067717: "owner",         # Jonathan Zschoche → Owner / full access
}

def get_client_for_telegram_id(telegram_id: int) -> str:
    """
    Returns the client_slug for a given Telegram ID.
    Returns None if the ID is not recognized.
    """
    return TELEGRAM_ID_TO_CLIENT.get(telegram_id)

def is_authorized(telegram_id: int) -> bool:
    """Check if this Telegram ID is allowed to use the system."""
    return telegram_id in TELEGRAM_ID_TO_CLIENT

if __name__ == "__main__":
    print("Client mapping ready.")
    print("Don Qi Style (8575986732) → mwk")
    print("Jonathan (6513067717) → owner")
