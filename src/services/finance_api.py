import logging
import time
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

import pandas as pd
import yfinance as yf
from redis import Redis

from src.core.config import Settings, get_settings
from src.core.db_redis import get_json_cache, set_json_cache
from src.models.market_data_schema import FinanceBundle, FinancialStatement, PriceBar, TickerProfile
from src.models.macro_schema import MacroContext, OptionsFlow
from src.models.research_schema import NewsArticle


PROFILE_TTL_SECONDS = 60 * 60 * 12
HISTORY_TTL_SECONDS = 60 * 15
STATEMENT_TTL_SECONDS = 60 * 60 * 24
BUNDLE_TTL_SECONDS = 60 * 15
NEWS_TTL_SECONDS = 60 * 15
MACRO_TTL_SECONDS = 60 * 60 * 4
OPTIONS_TTL_SECONDS = 60 * 30

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

    def fetch_ticker_news(self, ticker: str, limit: int = 10) -> list[NewsArticle]:
        symbol = ticker.upper()
        cache_key = f"finance:news:{symbol}:{limit}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return [NewsArticle.model_validate(item) for item in cached]

        self._throttle_external_fetch(f"news:{symbol}:{limit}")
        try:
            raw_items = yf.Ticker(symbol).news or []
        except Exception:
            logger.exception("Failed to fetch yfinance news for %s", symbol)
            raw_items = []

        articles: list[NewsArticle] = []
        for item in raw_items[:limit]:
            article = self._news_item_to_article(item)
            if article is not None:
                articles.append(article)
        self._set_cached(cache_key, [article.model_dump(mode="json") for article in articles], NEWS_TTL_SECONDS)
        return articles

    def fetch_macro_context(self) -> MacroContext:
        cache_key = "finance:macro:snapshot"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return MacroContext.model_validate(cached)

        MACRO_TICKERS = {
            "vix": "^VIX",
            "yield_10y": "^TNX",
            "yield_5y": "^FVX",
            "yield_2y": "^IRX",
            "dxy": "DX-Y.NYB",
            "sp500": "^GSPC",
        }

        latest: dict[str, float | None] = {}
        histories: dict[str, list] = {}

        for key, symbol in MACRO_TICKERS.items():
            try:
                self._throttle_external_fetch(f"macro:{symbol}")
                ticker_obj = yf.Ticker(symbol)
                hist = ticker_obj.history(period="3mo", interval="1d")
                if not hist.empty:
                    latest[key] = float(hist["Close"].iloc[-1])
                    histories[key] = hist["Close"].tolist()
                else:
                    latest[key] = None
                    histories[key] = []
            except Exception:
                logger.warning("Failed to fetch macro ticker %s", symbol)
                latest[key] = None
                histories[key] = []

        spread = None
        inverted = None
        if latest.get("yield_10y") and latest.get("yield_2y"):
            spread = latest["yield_10y"] - latest["yield_2y"]
            inverted = spread < 0

        vix_val = latest.get("vix")
        vix_regime = None
        if vix_val is not None:
            if vix_val < 15:
                vix_regime = "low"
            elif vix_val < 25:
                vix_regime = "normal"
            elif vix_val < 35:
                vix_regime = "elevated"
            else:
                vix_regime = "extreme"

        dxy_trend = None
        dxy_hist = histories.get("dxy", [])
        if len(dxy_hist) >= 20 and latest.get("dxy"):
            ma20 = sum(dxy_hist[-20:]) / 20
            dxy_trend = "strengthening" if latest["dxy"] > ma20 else "weakening"

        sp500_above_200ma = None
        market_regime = None
        sp500_hist = histories.get("sp500", [])
        if len(sp500_hist) >= 60 and latest.get("sp500"):
            ma60 = sum(sp500_hist[-60:]) / 60
            sp500_above_200ma = latest["sp500"] > ma60
            if sp500_above_200ma:
                market_regime = "bull"
            else:
                pct_diff = abs(latest["sp500"] - ma60) / ma60
                market_regime = "bear" if pct_diff > 0.05 else "sideways"
        elif latest.get("sp500"):
            market_regime = "unknown"

        summary_parts = []
        if vix_regime:
            summary_parts.append(f"Market volatility is {vix_regime} (VIX={vix_val:.1f})" if vix_val else f"VIX regime: {vix_regime}")
        if inverted is not None:
            summary_parts.append(f"Yield curve is {'INVERTED (recession warning)' if inverted else 'normal'} (spread={spread:.2f}%)" if spread else "Yield curve data available")
        if market_regime:
            summary_parts.append(f"S&P 500 is in a {market_regime} market regime")
        if dxy_trend:
            summary_parts.append(f"US Dollar is {dxy_trend}")
        macro_summary = ". ".join(summary_parts) + "." if summary_parts else None

        context = MacroContext(
            vix=latest.get("vix"),
            vix_regime=vix_regime,
            yield_10y=latest.get("yield_10y"),
            yield_5y=latest.get("yield_5y"),
            yield_2y=latest.get("yield_2y"),
            yield_curve_spread=spread,
            yield_curve_inverted=inverted,
            dxy=latest.get("dxy"),
            dxy_trend=dxy_trend,
            sp500_price=latest.get("sp500"),
            sp500_above_200ma=sp500_above_200ma,
            market_regime=market_regime,
            macro_summary=macro_summary,
        )
        self._set_cached(cache_key, context.model_dump(mode="json"), MACRO_TTL_SECONDS)
        return context

    def fetch_options_flow(self, ticker: str) -> OptionsFlow:
        symbol = ticker.upper()
        cache_key = f"finance:options:{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return OptionsFlow.model_validate(cached)

        try:
            self._throttle_external_fetch(f"options:{symbol}")
            t = yf.Ticker(symbol)
            expiries = t.options
            if not expiries:
                flow = OptionsFlow(ticker=symbol)
                self._set_cached(cache_key, flow.model_dump(mode="json"), OPTIONS_TTL_SECONDS)
                return flow

            nearest_expiry = expiries[0]
            chain = t.option_chain(nearest_expiry)
            calls = chain.calls
            puts = chain.puts

            total_call_oi = int(calls["openInterest"].sum()) if "openInterest" in calls.columns else 0
            total_put_oi = int(puts["openInterest"].sum()) if "openInterest" in puts.columns else 0

            pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else None
            options_sentiment = None
            if pc_ratio is not None:
                if pc_ratio < 0.7:
                    options_sentiment = "bullish"
                elif pc_ratio > 1.2:
                    options_sentiment = "bearish"
                else:
                    options_sentiment = "neutral"

            max_pain = self._calculate_max_pain(calls, puts)

            flow = OptionsFlow(
                ticker=symbol,
                nearest_expiry=nearest_expiry,
                put_call_ratio=round(pc_ratio, 3) if pc_ratio else None,
                options_sentiment=options_sentiment,
                total_call_oi=total_call_oi,
                total_put_oi=total_put_oi,
                max_pain=max_pain,
            )
        except Exception:
            logger.warning("Failed to fetch options flow for %s", symbol)
            flow = OptionsFlow(ticker=symbol)

        self._set_cached(cache_key, flow.model_dump(mode="json"), OPTIONS_TTL_SECONDS)
        return flow

    def fetch_multi_timeframe(self, ticker: str) -> dict[str, list]:
        symbol = ticker.upper()
        return {
            "weekly": self.fetch_historical_prices(symbol, period="2y", interval="1wk"),
            "monthly": self.fetch_historical_prices(symbol, period="5y", interval="1mo"),
        }

    @staticmethod
    def _calculate_max_pain(calls, puts) -> float | None:
        try:
            all_strikes = set(
                calls["strike"].dropna().tolist() + puts["strike"].dropna().tolist()
            )
            if not all_strikes:
                return None

            min_pain = float("inf")
            max_pain_price = None

            for test_price in all_strikes:
                call_pain = sum(
                    max(0, test_price - s) * int(oi)
                    for s, oi in zip(calls["strike"], calls["openInterest"])
                    if pd.notna(s) and pd.notna(oi)
                )
                put_pain = sum(
                    max(0, s - test_price) * int(oi)
                    for s, oi in zip(puts["strike"], puts["openInterest"])
                    if pd.notna(s) and pd.notna(oi)
                )
                total_pain = call_pain + put_pain
                if total_pain < min_pain:
                    min_pain = total_pain
                    max_pain_price = test_price

            return float(max_pain_price) if max_pain_price else None
        except Exception:
            return None

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
    def _news_item_to_article(item: dict[str, Any]) -> NewsArticle | None:
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        title = FinanceAPI._as_optional_str(item.get("title") or item.get("headline") or content.get("title"))
        canonical_url = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
        click_url = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
        url = FinanceAPI._as_optional_str(
            item.get("link")
            or item.get("url")
            or canonical_url.get("url")
            or click_url.get("url")
        )
        if title is None or url is None:
            return None
        provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        source = FinanceAPI._as_optional_str(
            item.get("publisher")
            or item.get("source")
            or provider.get("displayName")
        )
        published_at = FinanceAPI._as_optional_datetime(
            item.get("providerPublishTime")
            or item.get("published_at")
            or content.get("pubDate")
            or content.get("displayTime")
        )
        summary = FinanceAPI._as_optional_str(item.get("summary") or item.get("snippet") or content.get("summary"))
        try:
            return NewsArticle(
                title=title,
                url=url,
                source=source,
                published_at=published_at,
                extracted_text=summary,
            )
        except Exception:
            return None

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

    @staticmethod
    def _as_optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(timestamp, tz=UTC)
