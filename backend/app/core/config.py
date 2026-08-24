from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "Marketing Agent Studio"
    APP_MODE: Literal["offline", "online"] = "offline"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    MODEL_NAME: str = "gpt-4.1-mini"
    PUBLIC_DEMO: bool = False
    REQUIRE_INVITE_CODE: bool = False
    DEMO_ACCESS_CODE: str = "course-demo"
    DEMO_ACCESS_CODE_HASH: str = ""
    APP_SIGNING_KEY: str = "local-development-signing-key-change-me"
    SESSION_COOKIE_NAME: str = "marketing_agent_session"
    SESSION_COOKIE_SECURE: bool = False
    SESSION_TTL_MINUTES: int = 240
    MODEL_KEY_TTL_MINUTES: int = 30
    RATE_LIMIT_PER_MINUTE: int = 30
    MAX_ACTIVE_RUNS_PER_SESSION: int = 2
    MAX_REQUEST_BYTES: int = 32_768
    PUBLIC_ORIGIN: str = "http://localhost:5173"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"
    HITL_AUDIENCE_THRESHOLD: int = 50_000
    MAX_RETRIES: int = 3
    PREVIEW_LIMIT: int = 10
    DATA_SEED: int = 20260809
    ANALYTICS_DB: Path = BACKEND_DIR / "data" / "marketing.duckdb"
    STATE_DB: Path = BACKEND_DIR / "data" / "workflow.sqlite3"
    KNOWLEDGE_DIR: Path = BACKEND_DIR / "app" / "knowledge" / "docs"

    @property
    def online_ready(self) -> bool:
        # Public BYOK mode is always available; readiness means the connection UI is enabled.
        return True

    @property
    def allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.ALLOWED_HOSTS.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ANALYTICS_DB.parent.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
