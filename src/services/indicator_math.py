from collections.abc import Iterable
from typing import Any

import pandas as pd

from src.models.fundamental_schema import FundamentalAnalysis, FundamentalSnapshot
from src.models.market_data_schema import FinancialStatement, PriceBar, TickerProfile
from src.models.technical_schema import (
    MomentumSignal,
    MovingAverageAlignment,
    TechnicalAnalysis,
    VolatilitySignal,
    VolumeSignal,
)

try:
    import pandas_ta as ta
except ImportError:
    ta = None


class IndicatorMath:
    def analyze_technical(self, ticker: str, history: pd.DataFrame | list[PriceBar]) -> TechnicalAnalysis:
        frame = self.normalize_price_frame(history)
        if frame.empty or len(frame) < 30:
            msg = "At least 30 price bars are required for technical analysis"
            raise ValueError(msg)

        close = frame["close"]
        high = frame["high"]
        low = frame["low"]
        volume = frame["volume"]
        latest_close = float(close.iloc[-1])

        ma50 = self._latest(close.rolling(50).mean())
        ma100 = self._latest(close.rolling(100).mean())
        ma200 = self._latest(close.rolling(200).mean())
        ma_state = self._moving_average_state(latest_close, ma50, ma100, ma200)

        rsi = self._rsi(close)
        macd, macd_signal, macd_histogram = self._macd(close)
        divergence = self._detect_divergence(close, rsi.fillna(macd_histogram))

        mfi = self._mfi(high, low, close, volume)
        vwap = self._vwap(high, low, close, volume)
        poc = self._point_of_control(close, volume)
        volume_trend = self._volume_trend(volume)

        atr = self._atr(high, low, close)
        historical_volatility = self._historical_volatility(close)
        bollinger_state = self._bollinger_state(close)
        support_levels, resistance_levels = self._support_resistance(close)

        tags = [
            ma_state,
            self._momentum_tag(self._latest(rsi), self._latest(macd_histogram), divergence),
            self._volume_tag(self._latest(mfi), volume_trend),
            self._volatility_tag(self._latest(atr), historical_volatility, bollinger_state),
        ]

        return TechnicalAnalysis(
            ticker=ticker.upper(),
            close_price=latest_close,
            moving_average=MovingAverageAlignment(
                ma50=ma50,
                ma100=ma100,
                ma200=ma200,
                state=ma_state,
                tag=f"ma_alignment:{ma_state}",
            ),
            momentum=MomentumSignal(
                rsi=self._latest(rsi),
                macd=self._latest(macd),
                macd_signal=self._latest(macd_signal),
                macd_histogram=self._latest(macd_histogram),
                divergence=divergence,
                tag=tags[1],
            ),
            volume=VolumeSignal(
                mfi=self._latest(mfi),
                vwap=self._latest(vwap),
                point_of_control=poc,
                volume_trend=volume_trend,
                tag=tags[2],
            ),
            volatility=VolatilitySignal(
                atr=self._latest(atr),
                historical_volatility=historical_volatility,
                bollinger_state=bollinger_state,
                tag=tags[3],
            ),
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            tags=tags,
        )

    def analyze_fundamentals(
        self,
        ticker: str,
        profile: TickerProfile,
        income_statement: FinancialStatement,
        balance_sheet: FinancialStatement,
    ) -> FundamentalAnalysis:
        piotroski = self.piotroski_f_score(income_statement, balance_sheet)
        peg = self.peg_ratio(profile)
        altman = self.altman_z_score(profile, income_statement, balance_sheet)
        strengths: list[str] = []
        weaknesses: list[str] = []
        tags: list[str] = []

        if piotroski is not None:
            tags.append(f"piotroski:{piotroski}")
            if piotroski >= 7:
                strengths.append("Strong Piotroski F-Score")
            elif piotroski <= 3:
                weaknesses.append("Weak Piotroski F-Score")
        if peg is not None:
            tags.append(f"peg:{round(peg, 2)}")
            if peg < 1:
                strengths.append("Growth-adjusted valuation appears attractive")
            elif peg > 2:
                weaknesses.append("Growth-adjusted valuation appears stretched")
        if altman is not None:
            tags.append(f"altman_z:{round(altman, 2)}")
            if altman > 3:
                strengths.append("Altman Z-Score indicates low distress risk")
            elif altman < 1.8:
                weaknesses.append("Altman Z-Score indicates elevated distress risk")

        return FundamentalAnalysis(
            ticker=ticker.upper(),
            piotroski_f_score=piotroski,
            peg_ratio=peg,
            altman_z_score=altman,
            tags=tags,
            strengths=strengths,
            weaknesses=weaknesses,
            snapshot=FundamentalSnapshot(
                ticker=ticker.upper(),
                currency=profile.currency,
                market_cap=profile.market_cap,
                revenue_growth=profile.revenue_growth,
                earnings_growth=profile.earnings_growth,
                debt_to_equity=None,
                return_on_equity=None,
                free_cash_flow=None,
            ),
        )

    @staticmethod
    def normalize_price_frame(history: pd.DataFrame | list[PriceBar]) -> pd.DataFrame:
        if isinstance(history, list):
            frame = pd.DataFrame([bar.model_dump() for bar in history])
        else:
            frame = history.copy()
        if frame.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
        frame = frame.rename(columns={column: str(column).lower().replace(" ", "_") for column in frame.columns})
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
            frame = frame.set_index("date")
        required = ["open", "high", "low", "close", "volume"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            msg = f"Missing required price columns: {', '.join(missing)}"
            raise ValueError(msg)
        frame = frame.sort_index()
        for column in required:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame.dropna(subset=required)

    @staticmethod
    def piotroski_f_score(income_statement: FinancialStatement, balance_sheet: FinancialStatement) -> int | None:
        net_income = _row_values(income_statement, ["Net Income", "Net Income Common Stockhnewers"])
        revenue = _row_values(income_statement, ["Total Revenue", "Operating Revenue"])
        gross_profit = _row_values(income_statement, ["Gross Profit"])
        total_assets = _row_values(balance_sheet, ["Total Assets"])
        long_term_debt = _row_values(balance_sheet, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"])
        current_assets = _row_values(balance_sheet, ["Current Assets", "Total Current Assets"])
        current_liabilities = _row_values(balance_sheet, ["Current Liabilities", "Total Current Liabilities Net Minority Interest"])
        shares = _row_values(balance_sheet, ["Ordinary Shares Number", "Share Issued"])

        checks: list[bool] = []
        roa = _ratio_series(net_income, total_assets)
        gross_margin = _ratio_series(gross_profit, revenue)
        asset_turnover = _ratio_series(revenue, total_assets)
        leverage = _ratio_series(long_term_debt, total_assets)
        current_ratio = _ratio_series(current_assets, current_liabilities)

        _append_positive(checks, _current(roa))
        _append_improved(checks, roa)
        _append_improved(checks, gross_margin)
        _append_improved(checks, asset_turnover)
        _append_decreased(checks, leverage)
        _append_improved(checks, current_ratio)
        if _has_pair(shares):
            checks.append(shares[0] <= shares[1])
        if _has_value(net_income):
            checks.append(net_income[0] > 0)

        if not checks:
            return None
        return int(sum(1 for check in checks if check))

    @staticmethod
    def peg_ratio(profile: TickerProfile) -> float | None:
        pe = profile.forward_pe or profile.trailing_pe
        growth = profile.earnings_growth or profile.revenue_growth
        if pe is None or growth is None or growth <= 0:
            return None
        growth_percent = growth * 100 if growth <= 1 else growth
        if growth_percent <= 0:
            return None
        return float(pe / growth_percent)

    @staticmethod
    def altman_z_score(
        profile: TickerProfile,
        income_statement: FinancialStatement,
        balance_sheet: FinancialStatement,
    ) -> float | None:
        total_assets = _first_value(balance_sheet, ["Total Assets"])
        total_liabilities = _first_value(balance_sheet, ["Total Liabilities Net Minority Interest", "Total Liabilities"])
        current_assets = _first_value(balance_sheet, ["Current Assets", "Total Current Assets"])
        current_liabilities = _first_value(balance_sheet, ["Current Liabilities", "Total Current Liabilities Net Minority Interest"])
        retained_earnings = _first_value(balance_sheet, ["Retained Earnings"])
        ebit = _first_value(income_statement, ["EBIT", "Operating Income"])
        revenue = _first_value(income_statement, ["Total Revenue", "Operating Revenue"])
        if total_assets is None or total_assets == 0 or total_liabilities is None or total_liabilities == 0:
            return None
        if current_assets is None or current_liabilities is None or retained_earnings is None or ebit is None or revenue is None:
            return None
        market_cap = profile.market_cap
        if market_cap is None:
            return None
        working_capital = current_assets - current_liabilities
        return float(
            1.2 * (working_capital / total_assets)
            + 1.4 * (retained_earnings / total_assets)
            + 3.3 * (ebit / total_assets)
            + 0.6 * (market_cap / total_liabilities)
            + 1.0 * (revenue / total_assets)
        )

    @staticmethod
    def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
        if ta is not None:
            result = ta.rsi(close, length=length)
            if result is not None:
                return result
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
        relative_strength = gain / loss.replace(0, pd.NA)
        return 100 - (100 / (1 + relative_strength))

    @staticmethod
    def _macd(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        if ta is not None:
            result = ta.macd(close)
            if result is not None and not result.empty:
                macd_column = next(column for column in result.columns if str(column).startswith("MACD_"))
                signal_column = next(column for column in result.columns if str(column).startswith("MACDs_"))
                histogram_column = next(column for column in result.columns if str(column).startswith("MACDh_"))
                return result[macd_column], result[signal_column], result[histogram_column]
        fast = close.ewm(span=12, adjust=False).mean()
        slow = close.ewm(span=26, adjust=False).mean()
        macd = fast - slow
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return macd, signal, histogram

    @staticmethod
    def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, length: int = 14) -> pd.Series:
        if ta is not None:
            result = ta.mfi(high, low, close, volume, length=length)
            if result is not None:
                return result.astype(float)
        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * volume
        positive_flow = raw_money_flow.where(typical_price.diff() > 0, 0).rolling(length).sum()
        negative_flow = raw_money_flow.where(typical_price.diff() < 0, 0).rolling(length).sum()
        money_ratio = positive_flow / negative_flow.replace(0, pd.NA)
        return 100 - (100 / (1 + money_ratio))

    @staticmethod
    def _vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        typical_price = (high + low + close) / 3
        cumulative_volume = volume.cumsum().replace(0, pd.NA)
        return (typical_price * volume).cumsum() / cumulative_volume

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        if ta is not None:
            result = ta.atr(high, low, close, length=length)
            if result is not None:
                return result
        previous_close = close.shift(1)
        true_range = pd.concat([(high - low), (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
        return true_range.ewm(alpha=1 / length, adjust=False).mean()

    @staticmethod
    def _historical_volatility(close: pd.Series, length: int = 30) -> float | None:
        returns = close.pct_change().dropna()
        if len(returns) < length:
            return None
        return float(returns.tail(length).std() * (252 ** 0.5) * 100)

    @staticmethod
    def _bollinger_state(close: pd.Series, length: int = 20) -> str:
        middle = close.rolling(length).mean()
        deviation = close.rolling(length).std()
        upper = middle + 2 * deviation
        lower = middle - 2 * deviation
        bandwidth = (upper - lower) / middle.replace(0, pd.NA)
        latest_bandwidth = bandwidth.iloc[-1]
        if pd.isna(latest_bandwidth):
            return "normal"
        if close.iloc[-1] > upper.iloc[-1] or close.iloc[-1] < lower.iloc[-1]:
            return "breakout"
        if latest_bandwidth <= bandwidth.dropna().quantile(0.2):
            return "squeeze"
        if latest_bandwidth >= bandwidth.dropna().quantile(0.8):
            return "high"
        if latest_bandwidth <= bandwidth.dropna().quantile(0.35):
            return "low"
        return "normal"

    @staticmethod
    def _point_of_control(close: pd.Series, volume: pd.Series, bins: int = 24) -> float | None:
        profile = pd.DataFrame({"close": close, "volume": volume}).dropna()
        if profile.empty or profile["close"].nunique() < 2:
            return None
        profile["bucket"] = pd.cut(profile["close"], bins=bins)
        grouped = profile.groupby("bucket", observed=False)["volume"].sum()
        if grouped.empty:
            return None
        interval = grouped.idxmax()
        return float((interval.left + interval.right) / 2)

    @staticmethod
    def _support_resistance(close: pd.Series, lookback: int = 120) -> tuple[list[float], list[float]]:
        recent = close.tail(lookback)
        latest = float(recent.iloc[-1])
        lows = recent[(recent.shift(1) > recent) & (recent.shift(-1) > recent)]
        highs = recent[(recent.shift(1) < recent) & (recent.shift(-1) < recent)]
        supports = sorted({round(float(value), 2) for value in lows if value < latest}, reverse=True)[:3]
        resistances = sorted({round(float(value), 2) for value in highs if value > latest})[:3]
        return supports, resistances

    @staticmethod
    def _moving_average_state(close: float, ma50: float | None, ma100: float | None, ma200: float | None) -> str:
        if ma50 is None or ma100 is None or ma200 is None:
            return "neutral"
        if close > ma50 > ma100 > ma200:
            return "bullish"
        if close < ma50 < ma100 < ma200:
            return "bearish"
        return "mixed"

    @staticmethod
    def _volume_trend(volume: pd.Series) -> str:
        average_volume = volume.rolling(20).mean().iloc[-1]
        latest_volume = volume.iloc[-1]
        if pd.isna(average_volume) or average_volume == 0:
            return "neutral"
        if latest_volume > average_volume * 1.25:
            return "bullish"
        if latest_volume < average_volume * 0.75:
            return "bearish"
        return "neutral"

    @staticmethod
    def _detect_divergence(close: pd.Series, oscillator: pd.Series, lookback: int = 60) -> str:
        frame = pd.DataFrame({"close": close, "oscillator": oscillator}).dropna().tail(lookback)
        if len(frame) < 10:
            return "none"
        lows = frame[(frame["close"].shift(1) > frame["close"]) & (frame["close"].shift(-1) > frame["close"])]
        highs = frame[(frame["close"].shift(1) < frame["close"]) & (frame["close"].shift(-1) < frame["close"])]
        if len(lows) >= 2:
            first = lows.iloc[-2]
            second = lows.iloc[-1]
            if second["close"] < first["close"] and second["oscillator"] > first["oscillator"]:
                return "bullish_divergence"
        if len(highs) >= 2:
            first = highs.iloc[-2]
            second = highs.iloc[-1]
            if second["close"] > first["close"] and second["oscillator"] < first["oscillator"]:
                return "bearish_divergence"
        return "none"

    @staticmethod
    def _momentum_tag(rsi: float | None, histogram: float | None, divergence: str) -> str:
        if divergence != "none":
            return f"momentum:{divergence}"
        if rsi is not None and rsi >= 70:
            return "momentum:overbought"
        if rsi is not None and rsi <= 30:
            return "momentum:oversnew"
        if histogram is not None and histogram > 0:
            return "momentum:positive"
        if histogram is not None and histogram < 0:
            return "momentum:negative"
        return "momentum:neutral"

    @staticmethod
    def _volume_tag(mfi: float | None, volume_trend: str) -> str:
        if mfi is not None and mfi >= 80:
            return "volume:overbought_flow"
        if mfi is not None and mfi <= 20:
            return "volume:oversnew_flow"
        return f"volume:{volume_trend}"

    @staticmethod
    def _volatility_tag(atr: float | None, historical_volatility: float | None, bollinger_state: str) -> str:
        if bollinger_state in {"squeeze", "breakout"}:
            return f"volatility:{bollinger_state}"
        if historical_volatility is not None and historical_volatility >= 60:
            return "volatility:high"
        if atr is not None:
            return "volatility:measured"
        return "volatility:unknown"

    @staticmethod
    def _latest(series: pd.Series) -> float | None:
        cleaned = series.dropna()
        if cleaned.empty:
            return None
        return float(cleaned.iloc[-1])


def _row_values(statement: FinancialStatement, aliases: Iterable[str]) -> list[float | None]:
    matched_key = _match_row_key(statement, aliases)
    if matched_key is None:
        return []
    row = statement.rows[matched_key]
    return [_coerce_float(row.get(column)) for column in statement.columns]


def _first_value(statement: FinancialStatement, aliases: Iterable[str]) -> float | None:
    values = _row_values(statement, aliases)
    return values[0] if values else None


def _match_row_key(statement: FinancialStatement, aliases: Iterable[str]) -> str | None:
    normalized_rows = {key.lower().replace(" ", ""): key for key in statement.rows}
    for alias in aliases:
        normalized_alias = alias.lower().replace(" ", "")
        if normalized_alias in normalized_rows:
            return normalized_rows[normalized_alias]
    for alias in aliases:
        normalized_alias = alias.lower().replace(" ", "")
        for normalized_key, original_key in normalized_rows.items():
            if normalized_alias in normalized_key:
                return original_key
    return None


def _ratio_series(numerator: list[float | None], denominator: list[float | None]) -> list[float | None]:
    ratios: list[float | None] = []
    for top, bottom in zip(numerator, denominator, strict=False):
        if top is None or bottom in (None, 0):
            ratios.append(None)
        else:
            ratios.append(top / bottom)
    return ratios


def _append_positive(checks: list[bool], value: float | None) -> None:
    if value is not None:
        checks.append(value > 0)


def _append_improved(checks: list[bool], values: list[float | None]) -> None:
    if _has_pair(values):
        checks.append(values[0] > values[1])


def _append_decreased(checks: list[bool], values: list[float | None]) -> None:
    if _has_pair(values):
        checks.append(values[0] < values[1])


def _has_value(values: list[float | None]) -> bool:
    return bool(values) and values[0] is not None


def _has_pair(values: list[float | None]) -> bool:
    return len(values) >= 2 and values[0] is not None and values[1] is not None


def _current(values: list[float | None]) -> float | None:
    return values[0] if values else None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(converted):
        return None
    return converted
