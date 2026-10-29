"""Runtime configuration. Everything secret comes from environment variables."""
import os
from dataclasses import dataclass


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Env:
    database_path: str
    data_dir: str
    app_base_url: str
    cookie_secure: bool
    trust_proxy: bool
    ai_provider: str
    ai_api_key: str
    ai_base_url: str
    ai_model: str
    image_api_key: str
    image_base_url: str
    image_model: str
    search_api_key: str
    search_base_url: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    max_upload_bytes: int


def env() -> Env:
    """Read the environment on every call so tests and restarts pick up changes."""
    g = os.environ.get
    provider = g("AI_PROVIDER", "anthropic").strip().lower()
    default_base = "https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com/v1"
    default_model = "claude-sonnet-5-5" if provider == "anthropic" else "gpt-4o-mini"
    data_dir = g("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    return Env(
        database_path=g("DATABASE_PATH", os.path.join(data_dir, "arnet.sqlite3")),
        data_dir=data_dir,
        app_base_url=g("APP_BASE_URL", "http://localhost:8000").rstrip("/"),
        cookie_secure=_flag("COOKIE_SECURE", False),
        trust_proxy=_flag("TRUST_PROXY", False),
        ai_provider=provider,
        ai_api_key=g("AI_API_KEY", ""),
        ai_base_url=g("AI_BASE_URL", default_base).rstrip("/"),
        ai_model=g("AI_MODEL", default_model),
        image_api_key=g("IMAGE_API_KEY", ""),
        image_base_url=g("IMAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        image_model=g("IMAGE_MODEL", "gpt-image-1"),
        search_api_key=g("SEARCH_API_KEY", ""),
        search_base_url=g("SEARCH_BASE_URL", "https://api.tavily.com").rstrip("/"),
        smtp_host=g("SMTP_HOST", ""),
        smtp_port=int(g("SMTP_PORT", "587")),
        smtp_user=g("SMTP_USER", ""),
        smtp_password=g("SMTP_PASSWORD", ""),
        smtp_from=g("SMTP_FROM", ""),
        max_upload_bytes=int(g("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
    )
