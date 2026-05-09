import logging
import time
from datetime import date
from threading import Lock
from typing import Any

import pandas as pd
import yfinance as yf
from redis import Redis

from src.core.config import Settings, get_settings
from src.core.db_redis import get_json_cache, set_json_cache
from src.models.market_data_schema import FinanceBundle, FinancialStatement, PriceBar, TickerProfile


PROFILE_TTL_SECONDS = 60 * 60 * 12
HISTORY_TTL_SECONDS = 60 * 15
STATEMENT_TTL_SECONDS = 60 * 60 * 24
BUNDLE_TTL_SECONDS = 60 * 15

logger = logging.getLogger(__name__)
_FINANCE_FETCH_LOCK = Lock()


class FinanceAPI:
    def __init__(self, redis_client: Redis | None = None, settings: Settings | None = None) -> None:
        self.redis_client = redis_client
        self.settings = settings or get_settings()

    def fetch_ticker_profile(self, ticker: str) -> TickerProfile:
        symbol = ticker.upper()
        cache_key = f"finance:profile:{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return TickerProfile.model_validate(cached)

        self._throttle_external_fetch(f"profile:{symbol}")
        info = yf.Ticker(symbol).get_info()
        profile = TickerProfile(
            ticker=symbol,
            short_name=self._as_optional_str(info.get("shortName") or info.get("longName")),
            sector=self._as_optional_str(info.get("sector")),
            industry=self._as_optional_str(info.get("industry")),
            currency=self._as_optional_str(info.get("currency")),
            market_cap=self._as_optional_float(info.get("marketCap")),
            beta=self._as_optional_float(info.get("beta")),
            trailing_pe=self._as_optional_float(info.get("trailingPE")),
            forward_pe=self._as_optional_float(info.get("forwardPE")),
            dividend_yield=self._as_optional_float(info.get("dividendYield")),
            earnings_growth=self._as_optional_float(info.get("earningsGrowth")),
            revenue_growth=self._as_optional_float(info.get("revenueGrowth")),
        )
        self._set_cached(cache_key, profile.model_dump(mode="json"), PROFILE_TTL_SECONDS)
        return profile

    def fetch_historical_prices(self, ticker: str, period: str = "2y", interval: str = "1d") -> list[PriceBar]:
        symbol = ticker.upper()
        cache_key = f"finance:history:{symbol}:{period}:{interval}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return [PriceBar.model_validate(item) for item in cached]

        self._throttle_external_fetch(f"history:{symbol}:{period}:{interval}")
        frame = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        bars = self.price_frame_to_bars(frame)
        self._set_cached(cache_key, [bar.model_dump(mode="json") for bar in bars], HISTORY_TTL_SECONDS)
        return bars

    def fetch_income_statement(self, ticker: str, period: str = "annual") -> FinancialStatement:
        symbol = ticker.upper()
        cache_key = f"finance:income:{symbol}:{period}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return FinancialStatement.model_validate(cached)

        self._throttle_external_fetch(f"income:{symbol}:{period}")
        ticker_obj = yf.Ticker(symbol)
        frame = ticker_obj.quarterly_income_stmt if period == "quarterly" else ticker_obj.income_stmt
        statement = self.statement_frame_to_model(symbol, "income_statement", period, frame)
        self._set_cached(cache_key, statement.model_dump(mode="json"), STATEMENT_TTL_SECONDS)
        return statement

    def fetch_balance_sheet(self, ticker: str, period: str = "annual") -> FinancialStatement:
        symbol = ticker.upper()
        cache_key = f"finance:balance:{symbol}:{period}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return FinancialStatement.model_validate(cached)

        self._throttle_external_fetch(f"balance:{symbol}:{period}")
        ticker_obj = yf.Ticker(symbol)
        frame = ticker_obj.quarterly_balance_sheet if period == "quarterly" else ticker_obj.balance_sheet
        statement = self.statement_frame_to_model(symbol, "balance_sheet", period, frame)
        self._set_cached(cache_key, statement.model_dump(mode="json"), STATEMENT_TTL_SECONDS)
        return statement

    def fetch_finance_bundle(self, ticker: str, period: str = "2y", interval: str = "1d") -> FinanceBundle:
        symbol = ticker.upper()
        cache_key = f"finance:bundle:{symbol}:{period}:{interval}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return FinanceBundle.model_validate(cached)

        bundle = FinanceBundle(
            ticker=symbol,
            profile=self.fetch_ticker_profile(symbol),
            history=self.fetch_historical_prices(symbol, period=period, interval=interval),
            income_statement=self.fetch_income_statement(symbol),
            balance_sheet=self.fetch_balance_sheet(symbol),
        )
        self._set_cached(cache_key, bundle.model_dump(mode="json"), BUNDLE_TTL_SECONDS)
        return bundle

    @staticmethod
    def price_frame_to_bars(frame: pd.DataFrame) -> list[PriceBar]:
        normalized = frame.reset_index()
        if "Date" not in normalized.columns and "Datetime" in normalized.columns:
            normalized = normalized.rename(columns={"Datetime": "Date"})
        bars: list[PriceBar] = []
        for row in normalized.to_dict(orient="records"):
            row_date = row.get("Date")
            if hasattr(row_date, "date"):
                row_date = row_date.date()
            if not isinstance(row_date, date):
                row_date = pd.to_datetime(row_date).date()
            bars.append(
                PriceBar(
                    date=row_date,
                    open=float(row.get("Open") or 0),
                    high=float(row.get("High") or 0),
                    low=float(row.get("Low") or 0),
                    close=float(row.get("Close") or 0),
                    adj_close=FinanceAPI._as_optional_float(row.get("Adj Close")),
                    volume=int(row.get("Volume") or 0),
                )
            )
        return bars

    @staticmethod
    def bars_to_frame(bars: list[PriceBar]) -> pd.DataFrame:
        frame = pd.DataFrame([bar.model_dump() for bar in bars])
        if frame.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.set_index("date").sort_index()

    @staticmethod
    def statement_frame_to_model(ticker: str, statement_type: str, period: str, frame: pd.DataFrame) -> FinancialStatement:
        if frame is None or frame.empty:
            return FinancialStatement(ticker=ticker, statement_type=statement_type, period=period)
        normalized = frame.copy()
        normalized.columns = [str(column) for column in normalized.columns]
        rows: dict[str, dict[str, float | None]] = {}
        for index, values in normalized.iterrows():
            rows[str(index)] = {
                str(column): FinanceAPI._as_optional_float(value)
                for column, value in values.items()
            }
        return FinancialStatement(
            ticker=ticker,
            statement_type=statement_type,
            period=period,
            columns=[str(column) for column in normalized.columns],
            rows=rows,
        )

    def _get_cached(self, key: str) -> Any | None:
        if self.redis_client is None:
            return None
        try:
            return get_json_cache(self.redis_client, key)
        except Exception:
            return None

    def _set_cached(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        if self.redis_client is None:
            return
        try:
            set_json_cache(self.redis_client, key, value, ttl_seconds)
        except Exception:
            return

    def _throttle_external_fetch(self, label: str) -> None:
        delay_seconds = self.settings.finance_fetch_delay_seconds
        if delay_seconds <= 0:
            return
        with _FINANCE_FETCH_LOCK:
            logger.debug("Throttling finance fetch %s for %.2fs", label, delay_seconds)
            time.sleep(delay_seconds)

    @staticmethod
    def _as_optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            converted = float(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(converted):
            return None
        return converted

    @staticmethod
    def _as_optional_str(value: Any) -> str | None:
        if value is None:
            return None
        converted = str(value).strip()
        return converted or None
