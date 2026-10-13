from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "MYNE AI"
    environment: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=list)

    llm_provider: Literal["openai", "gemini"] = "openai"
    llm_fallback_enabled: bool = True
    llm_timeout_seconds: float = Field(default=90.0, gt=0)
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    serp_api_key: SecretStr | None = None
    serper_api_key: SecretStr | None = None
    google_vision_api_key: SecretStr | None = None
    search_country: str = Field(default="us", min_length=2, max_length=2)
    search_language: str = "en"

    default_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    fx_rates_url: str = "https://api.frankfurter.dev/v1/latest"
    price_history_months: int = Field(default=6, ge=1, le=24)
    price_cache_ttl_seconds: int = Field(default=6 * 3600, ge=0)
    price_source_timeout_seconds: float = Field(default=60.0, gt=0)
    wayback_max_pages: int = Field(default=3, ge=0, le=10)

    max_image_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    image_fetch_timeout_seconds: float = Field(default=15.0, gt=0)
    sse_keepalive_seconds: float = Field(default=15.0, gt=0)
    auto_confirm_confidence: float = Field(default=0.85, ge=0, le=1)
    auto_confirm_margin: float = Field(default=0.2, ge=0, le=1)

    http_user_agent: str = "MYNE-AI/0.1.0 (+https://github.com/fahiiim/MYNE-AI)"
    http_timeout_seconds: float = Field(default=20.0, gt=0)
    http_max_attempts: int = Field(default=3, ge=1, le=6)

    @property
    def json_logs(self) -> bool:
        return self.environment != "local"


def secret_value(secret: SecretStr | None) -> str | None:
    if secret is None:
        return None
    value = secret.get_secret_value().strip()
    return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
