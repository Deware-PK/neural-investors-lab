from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    openrouter_api_key: SecretStr | None = Field(default=None, alias="OPENROUTER_API_KEY")
    ceo_model: str = Field(default="google/gemini-3.1-flash-lite", alias="CEO_MODEL")
    ceo_model_reasoning: bool = Field(default=True, alias="CEO_MODEL_REASONING")
    cro_model: str = Field(default="google/gemini-3.1-flash-lite", alias="CRO_MODEL")
    cro_model_reasoning: bool = Field(default=True, alias="CRO_MODEL_REASONING")
    news_analyst_model: str = Field(default="openai/gpt-4o-mini", alias="NEWS_ANALYST_MODEL")
    news_analyst_model_reasoning: bool = Field(default=False, alias="NEWS_ANALYST_MODEL_REASONING")
    postgres_url: str = Field(default="postgresql://user:password@localhost:5432/arena_db", alias="POSTGRES_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def normalize_model_names(self) -> "Settings":
        self.ceo_model = self.ceo_model.strip()
        self.cro_model = self.cro_model.strip()
        self.news_analyst_model = self.news_analyst_model.strip()
        return self

    def missing_runtime_secrets(self) -> list[str]:
        missing_fields: list[str] = []
        if self.telegram_bot_token is None:
            missing_fields.append("TELEGRAM_BOT_TOKEN")
        if self.openrouter_api_key is None:
            missing_fields.append("OPENROUTER_API_KEY")
        return missing_fields


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
