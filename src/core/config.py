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
    finance_fetch_delay_seconds: float = Field(default=1.5, ge=0, alias="FINANCE_FETCH_DELAY_SECONDS")
    research_fetch_delay_seconds: float = Field(default=1.5, ge=0, alias="RESEARCH_FETCH_DELAY_SECONDS")
    edgar_identity: str = Field(default="", alias="EDGAR_IDENTITY")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO", alias="LOG_LEVEL")
    debug_prompts: bool = Field(default=False, alias="DEBUG_PROMPTS")
    show_ai_data: bool = Field(default=False, alias="SHOW_AI_DATA")
    output_language: str = Field(default="en", alias="OUTPUT_LANGUAGE")
    tavily_api_key: SecretStr | None = Field(default=None, alias="TAVILY_API_KEY")
    advanced_search: bool = Field(default=False, alias="ADVANCED_SEARCH")
    tavily_max_results: int = Field(default=5, ge=1, le=10, alias="TAVILY_MAX_RESULTS")
    tavily_search_depth: Literal["ultra-fast", "basic", "fast", "advanced"] = Field(
        default="fast", alias="TAVILY_SEARCH_DEPTH"
    )
    investment_style: Literal["swing_trader", "deep_value_vi"] = Field(
        default="swing_trader", alias="INVESTMENT_STYLE"
    )

    # --- Technical indicator thresholds (indicator_math.py) ---
    rsi_overbought: float = Field(default=70.0, alias="RSI_OVERBOUGHT")
    rsi_oversold: float = Field(default=30.0, alias="RSI_OVERSOLD")
    mfi_overbought: float = Field(default=80.0, alias="MFI_OVERBOUGHT")
    mfi_oversold: float = Field(default=20.0, alias="MFI_OVERSOLD")
    volume_trend_bullish_multiplier: float = Field(default=1.25, alias="VOLUME_TREND_BULLISH_MULTIPLIER")
    volume_trend_bearish_multiplier: float = Field(default=0.75, alias="VOLUME_TREND_BEARISH_MULTIPLIER")
    bollinger_squeeze_quantile: float = Field(default=0.2, ge=0, le=1, alias="BOLLINGER_SQUEEZE_QUANTILE")
    bollinger_low_quantile: float = Field(default=0.35, ge=0, le=1, alias="BOLLINGER_LOW_QUANTILE")
    bollinger_high_quantile: float = Field(default=0.8, ge=0, le=1, alias="BOLLINGER_HIGH_QUANTILE")
    rs_weight_3m: float = Field(default=0.4, alias="RS_WEIGHT_3M")
    rs_weight_6m: float = Field(default=0.2, alias="RS_WEIGHT_6M")
    rs_weight_9m: float = Field(default=0.2, alias="RS_WEIGHT_9M")
    rs_weight_12m: float = Field(default=0.2, alias="RS_WEIGHT_12M")
    supertrend_atr_period: int = Field(default=10, ge=1, alias="SUPERTREND_ATR_PERIOD")
    supertrend_multiplier: float = Field(default=3.0, alias="SUPERTREND_MULTIPLIER")

    # --- Fundamental thresholds (indicator_math.py) ---
    piotroski_strong_threshold: int = Field(default=7, alias="PIOTROSKI_STRONG_THRESHOLD")
    piotroski_weak_threshold: int = Field(default=3, alias="PIOTROSKI_WEAK_THRESHOLD")
    peg_cheap_threshold: float = Field(default=1.0, alias="PEG_CHEAP_THRESHOLD")
    peg_expensive_threshold: float = Field(default=2.0, alias="PEG_EXPENSIVE_THRESHOLD")
    altman_safe_threshold: float = Field(default=3.0, alias="ALTMAN_SAFE_THRESHOLD")
    altman_distress_threshold: float = Field(default=1.8, alias="ALTMAN_DISTRESS_THRESHOLD")
    altman_bucket_high: float = Field(default=3.0, alias="ALTMAN_BUCKET_HIGH")
    altman_bucket_mid: float = Field(default=2.0, alias="ALTMAN_BUCKET_MID")
    altman_bucket_low: float = Field(default=1.0, alias="ALTMAN_BUCKET_LOW")
    peg_regime_cheap: float = Field(default=0.8, alias="PEG_REGIME_CHEAP")
    peg_regime_reasonable: float = Field(default=1.5, alias="PEG_REGIME_REASONABLE")
    altman_insolvency_threshold: float = Field(default=1.0, alias="ALTMAN_INSOLVENCY_THRESHOLD")

    # --- Adaptive threshold mode (opt-in) ---
    adaptive_thresholds: bool = Field(default=False, alias="ADAPTIVE_THRESHOLDS")
    adaptive_lookback: int = Field(default=252, ge=30, alias="ADAPTIVE_LOOKBACK")
    adaptive_percentile_overbought: float = Field(default=0.9, ge=0.5, le=1.0, alias="ADAPTIVE_PERCENTILE_OVERBOUGHT")
    adaptive_percentile_oversold: float = Field(default=0.1, ge=0.0, le=0.5, alias="ADAPTIVE_PERCENTILE_OVERSOLD")

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
        self.output_language = self.output_language.strip().lower()
        if self.output_language not in {"en", "th"}:
            self.output_language = "en"
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
