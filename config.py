import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

BITUNIX_API_KEY = os.getenv("BITUNIX_API_KEY")
BITUNIX_SECRET = os.getenv("BITUNIX_SECRET")


def parse_telegram_ids(value):
    if not value:
        return frozenset()

    return frozenset(
        int(user_id.strip())
        for user_id in value.split(",")
        if user_id.strip()
    )


ALLOWED_TELEGRAM_IDS = parse_telegram_ids(
    os.getenv("ALLOWED_TELEGRAM_IDS")
)
ADMIN_TELEGRAM_IDS = parse_telegram_ids(
    os.getenv("ADMIN_TELEGRAM_IDS")
) or ALLOWED_TELEGRAM_IDS


def is_authorized(telegram_id):
    return telegram_id in ALLOWED_TELEGRAM_IDS


def is_admin(telegram_id):
    return telegram_id in ADMIN_TELEGRAM_IDS
