"""Owner-editable settings stored in the database, with validation and defaults."""
import re

from .config import env
from .db import db

DEFAULTS: dict[str, str] = {
    "brand_name": "ARNET AI",
    "tagline": "One Intelligence. Infinite Possibilities.",
    "owner_name": "Chris",
    "creator": "Chris (ZYNTHEX)",
    "contact_email": "realchrris@gmail.com",
    "whatsapp": "0746940886",
    "whatsapp_country_code": "254",
    "ai_provider": "",       # empty = use AI_PROVIDER from the environment
    "ai_model": "",          # empty = use AI_MODEL from the environment
    "free_daily_messages": "20",
    "pro_daily_messages": "500",
    "free_daily_images": "3",
    "pro_daily_images": "30",
    "registration_open": "true",
    "max_message_chars": "8000",
}

TEXT_LIMITS = {"brand_name": 40, "tagline": 120, "owner_name": 60, "creator": 80, "contact_email": 120,
               "whatsapp": 20, "whatsapp_country_code": 4, "ai_model": 100}
INT_KEYS = {"free_daily_messages": (0, 100000), "pro_daily_messages": (0, 100000),
            "free_daily_images": (0, 10000), "pro_daily_images": (0, 10000), "max_message_chars": (100, 50000)}
BOOL_KEYS = {"registration_open"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def all_settings() -> dict[str, str]:
    with db() as conn:
        stored = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}


def get(key: str) -> str:
    return all_settings()[key]


def get_int(key: str) -> int:
    return int(get(key))


def validate_and_save(updates: dict) -> dict[str, str]:
    """Raise ValueError with a user-facing message on bad input; otherwise persist and return all settings."""
    clean: dict[str, str] = {}
    for key, raw in updates.items():
        if key not in DEFAULTS:
            raise ValueError(f"Unknown setting: {key}")
        if key in INT_KEYS:
            lo, hi = INT_KEYS[key]
            try:
                n = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a whole number")
            if not lo <= n <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi}")
            clean[key] = str(n)
        elif key in BOOL_KEYS:
            if not isinstance(raw, bool):
                raise ValueError(f"{key} must be true or false")
            clean[key] = "true" if raw else "false"
        else:
            if not isinstance(raw, str):
                raise ValueError(f"{key} must be text")
            val = raw.strip()
            if key in ("brand_name", "tagline", "owner_name", "creator", "contact_email") and not val:
                raise ValueError(f"{key} cannot be empty")
            if len(val) > TEXT_LIMITS.get(key, 100):
                raise ValueError(f"{key} is too long")
            if key == "contact_email" and not EMAIL_RE.match(val):
                raise ValueError("contact_email is not a valid email address")
            if key == "ai_provider" and val not in ("", "anthropic", "openai"):
                raise ValueError("ai_provider must be anthropic, openai, or empty")
            if key == "whatsapp" and val and not re.fullmatch(r"[0-9+ ]{6,20}", val):
                raise ValueError("whatsapp may contain only digits, spaces and +")
            if key == "whatsapp_country_code" and not re.fullmatch(r"[0-9]{1,4}", val):
                raise ValueError("whatsapp_country_code must be digits only")
            clean[key] = val
    with db() as conn:
        for k, v in clean.items():
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, v))
    return all_settings()


def whatsapp_link(number: str, country_code: str) -> str:
    digits = re.sub(r"\D", "", number)
    if not digits:
        return ""
    if number.strip().startswith("+"):
        intl = digits
    elif digits.startswith("0"):
        intl = country_code + digits[1:]
    else:
        intl = digits
    return f"https://wa.me/{intl}"


def effective_ai() -> dict:
    """Provider/model in force: admin override if set, otherwise environment."""
    e = env()
    s = all_settings()
    provider = s["ai_provider"] or e.ai_provider
    base = e.ai_base_url
    if provider != e.ai_provider:  # provider overridden in the dashboard: use that provider's standard endpoint
        base = "https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com/v1"
    return {"provider": provider, "model": s["ai_model"] or e.ai_model, "base_url": base,
            "configured": bool(e.ai_api_key)}
