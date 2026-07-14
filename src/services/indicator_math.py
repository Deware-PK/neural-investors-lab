from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from src.core.config import Settings

from src.models.fundamental_schema import FundamentalAnalysis, FundamentalSnapshot
from src.models.macro_schema import MultiTimeframeConfluence
from src.models.market_data_schema import FinancialStatement, PriceBar, TickerProfile
from src.models.technical_schema import (
    MomentumSignal,
    MovingAverageAlignment,
    PatternSignal,
    RelativeStrengthSignal,
    SupertrendDirection,
    SupertrendSignal,
    TechnicalAnalysis,
    TrendlineSignal,
    VolatilitySignal,
    VolumeSignal,
)
from src.models.vi_schema import MandateContext

try:
    import pandas_ta as ta
except ImportError:
    ta = None


class IndicatorMath:
    def __init__(self, settings: "Settings | None" = None) -> None:
        if settings is None:
            from src.core.config import get_settings

            settings = get_settings()
        self.settings = settings

    def _resolve_rsi_thresholds(self, rsi: pd.Series) -> tuple[float, float]:
        """Resolve RSI overbought/oversold thresholds.

        Fixed by default. When ``settings.adaptive_thresholds`` is enabled and enough
        history is available, thresholds become the ticker's own trailing percentile
        distribution instead of the fixed 70/30 convention.
        """
        overbought = self.settings.rsi_overbought
        oversold = self.settings.rsi_oversold
        if not self.settings.adaptive_thresholds:
            return overbought, oversold
        history = rsi.dropna().tail(self.settings.adaptive_lookback)
        if len(history) < self.settings.adaptive_lookback:
            return overbought, oversold
        adaptive_overbought = float(history.quantile(self.settings.adaptive_percentile_overbought))
        adaptive_oversold = float(history.quantile(self.settings.adaptive_percentile_oversold))
        if pd.isna(adaptive_overbought) or pd.isna(adaptive_oversold) or adaptive_overbought <= adaptive_oversold:
            return overbought, oversold
        return adaptive_overbought, adaptive_oversold

    def _resolve_mfi_thresholds(self, mfi: pd.Series) -> tuple[float, float]:
        """Resolve MFI overbought/oversold thresholds. See `_resolve_rsi_thresholds`."""
        overbought = self.settings.mfi_overbought
        oversold = self.settings.mfi_oversold
        if not self.settings.adaptive_thresholds:
            return overbought, oversold
        history = mfi.dropna().tail(self.settings.adaptive_lookback)
        if len(history) < self.settings.adaptive_lookback:
            return overbought, oversold
        adaptive_overbought = float(history.quantile(self.settings.adaptive_percentile_overbought))
        adaptive_oversold = float(history.quantile(self.settings.adaptive_percentile_oversold))
        if pd.isna(adaptive_overbought) or pd.isna(adaptive_oversold) or adaptive_overbought <= adaptive_oversold:
            return overbought, oversold
        return adaptive_overbought, adaptive_oversold

    def analyze_technical(
        self,
        ticker: str,
        history: pd.DataFrame | list[PriceBar],
        benchmark_scores: list[float] | None = None,
    ) -> TechnicalAnalysis:
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
        volume_trend = self._volume_trend(
            volume,
            bullish_multiplier=self.settings.volume_trend_bullish_multiplier,
            bearish_multiplier=self.settings.volume_trend_bearish_multiplier,
        )

        atr = self._atr(high, low, close)
        historical_volatility = self._historical_volatility(close)
        bollinger_state = self._bollinger_state(
            close,
            squeeze_quantile=self.settings.bollinger_squeeze_quantile,
            low_quantile=self.settings.bollinger_low_quantile,
            high_quantile=self.settings.bollinger_high_quantile,
        )
        support_levels, resistance_levels = self._support_resistance(close)

        trendline = self._fit_trendlines(high, low, close)
        pattern = self._detect_patterns(frame["open"], high, low, close)
        supertrend = self._supertrend(
            high,
            low,
            close,
            atr_period=self.settings.supertrend_atr_period,
            multiplier=self.settings.supertrend_multiplier,
        )
        relative_strength = self._relative_strength(
            close,
            benchmark_scores,
            weights=(
                self.settings.rs_weight_3m,
                self.settings.rs_weight_6m,
                self.settings.rs_weight_9m,
                self.settings.rs_weight_12m,
            ),
        )

        rsi_overbought, rsi_oversold = self._resolve_rsi_thresholds(rsi)
        mfi_overbought, mfi_oversold = self._resolve_mfi_thresholds(mfi)

        tags = [
            ma_state,
            self._momentum_tag(
                self._latest(rsi),
                self._latest(macd_histogram),
                divergence,
                overbought=rsi_overbought,
                oversold=rsi_oversold,
            ),
            self._volume_tag(
                self._latest(mfi),
                volume_trend,
                overbought=mfi_overbought,
                oversold=mfi_oversold,
            ),
            self._volatility_tag(self._latest(atr), historical_volatility, bollinger_state),
            supertrend.tag if supertrend else "supertrend:unknown",
            relative_strength.tag if relative_strength else "rs_rank:unknown",
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
            supertrend=supertrend,
            relative_strength=relative_strength,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            trendline=trendline,
            pattern=pattern,
            tags=tags,
        )

    def analyze_multi_timeframe(
        self,
        weekly_bars: list[PriceBar],
        monthly_bars: list[PriceBar],
        daily_close: float,
    ) -> MultiTimeframeConfluence:
        weekly_frame = self.normalize_price_frame(weekly_bars)
        monthly_frame = self.normalize_price_frame(monthly_bars)

        weekly_trend = None
        weekly_close_vs_ma20 = None
        if not weekly_frame.empty and len(weekly_frame) >= 20:
            weekly_close = weekly_frame["close"]
            weekly_ma20 = float(weekly_close.rolling(20).mean().iloc[-1])
            latest_weekly = float(weekly_close.iloc[-1])
            weekly_close_vs_ma20 = "above" if latest_weekly > weekly_ma20 else "below"
            if latest_weekly > weekly_ma20 * 1.02:
                weekly_trend = "bullish"
            elif latest_weekly < weekly_ma20 * 0.98:
                weekly_trend = "bearish"
            else:
                weekly_trend = "neutral"

        monthly_trend = None
        monthly_close_vs_ma20 = None
        if not monthly_frame.empty and len(monthly_frame) >= 20:
            monthly_close = monthly_frame["close"]
            monthly_ma20 = float(monthly_close.rolling(20).mean().iloc[-1])
            latest_monthly = float(monthly_close.iloc[-1])
            monthly_close_vs_ma20 = "above" if latest_monthly > monthly_ma20 else "below"
            if latest_monthly > monthly_ma20 * 1.02:
                monthly_trend = "bullish"
            elif latest_monthly < monthly_ma20 * 0.98:
                monthly_trend = "bearish"
            else:
                monthly_trend = "neutral"

        confluence_tag = "insufficient_data"
        if weekly_trend and monthly_trend:
            if weekly_trend == monthly_trend:
                confluence_tag = f"aligned_{weekly_trend}"
            else:
                confluence_tag = "conflicting"
        elif weekly_trend:
            confluence_tag = f"aligned_{weekly_trend}"
        elif monthly_trend:
            confluence_tag = f"aligned_{monthly_trend}"

        return MultiTimeframeConfluence(
            weekly_trend=weekly_trend,
            monthly_trend=monthly_trend,
            weekly_close_vs_ma20=weekly_close_vs_ma20,
            monthly_close_vs_ma20=monthly_close_vs_ma20,
            confluence_tag=confluence_tag,
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
            if piotroski >= self.settings.piotroski_strong_threshold:
                strengths.append("Strong Piotroski F-Score")
            elif piotroski <= self.settings.piotroski_weak_threshold:
                weaknesses.append("Weak Piotroski F-Score")
        if peg is not None:
            tags.append(f"peg:{round(peg, 2)}")
            if peg < self.settings.peg_cheap_threshold:
                strengths.append("Growth-adjusted valuation appears attractive")
            elif peg > self.settings.peg_expensive_threshold:
                weaknesses.append("Growth-adjusted valuation appears stretched")
        if altman is not None:
            tags.append(f"altman_z:{round(altman, 2)}")
            if altman > self.settings.altman_safe_threshold:
                strengths.append("Altman Z-Score indicates low distress risk")
            elif altman < self.settings.altman_distress_threshold:
                weaknesses.append("Altman Z-Score indicates elevated distress risk")

        vi = self._compute_vi_scores(
            piotroski,
            peg,
            altman,
            altman_bucket_high=self.settings.altman_bucket_high,
            altman_bucket_mid=self.settings.altman_bucket_mid,
            altman_bucket_low=self.settings.altman_bucket_low,
            peg_regime_cheap=self.settings.peg_regime_cheap,
            peg_regime_reasonable=self.settings.peg_regime_reasonable,
            altman_insolvency_threshold=self.settings.altman_insolvency_threshold,
        )

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
            quality_score=vi["quality_score"],
            balance_sheet_score=vi["balance_sheet_score"],
            cash_flow_quality_score=vi["cash_flow_quality_score"],
            dilution_risk=vi["dilution_risk"],
            cyclicality_risk=vi["cyclicality_risk"],
            thesis_durability=vi["thesis_durability"],
            valuation_regime=vi["valuation_regime"],
            margin_of_safety_pct=vi["margin_of_safety_pct"],
            thesis_impairment_flag=vi["thesis_impairment_flag"],
            hard_block_fundamental=vi["hard_block_fundamental"],
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
        net_income = _row_values(income_statement, ["Net Income", "Net Income Common Stockholders"])
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
    def _compute_vi_scores(
        piotroski: int | None,
        peg: float | None,
        altman: float | None,
        altman_bucket_high: float = 3.0,
        altman_bucket_mid: float = 2.0,
        altman_bucket_low: float = 1.0,
        peg_regime_cheap: float = 0.8,
        peg_regime_reasonable: float = 1.5,
        altman_insolvency_threshold: float = 1.0,
    ) -> dict[str, object]:
        quality_score: float | None = None
        if piotroski is not None:
            quality_score = round(piotroski / 9 * 10, 1)

        balance_sheet_score: float | None = None
        if altman is not None:
            if altman >= altman_bucket_high:
                balance_sheet_score = 8.0
            elif altman >= altman_bucket_mid:
                balance_sheet_score = 6.0
            elif altman >= altman_bucket_low:
                balance_sheet_score = 4.0
            else:
                balance_sheet_score = 2.0

        valuation_regime: str | None = None
        if peg is not None:
            if peg < peg_regime_cheap:
                valuation_regime = "cheap"
            elif peg <= peg_regime_reasonable:
                valuation_regime = "reasonable"
            else:
                valuation_regime = "expensive"

        hard_block: str = "none"
        if altman is not None and altman < altman_insolvency_threshold:
            hard_block = "insolvency_risk"

        return {
            "quality_score": quality_score,
            "balance_sheet_score": balance_sheet_score,
            "cash_flow_quality_score": None,
            "dilution_risk": "medium",
            "cyclicality_risk": "medium",
            "thesis_durability": "medium",
            "valuation_regime": valuation_regime,
            "margin_of_safety_pct": None,
            "thesis_impairment_flag": False,
            "hard_block_fundamental": hard_block,
        }

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
    def _supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr_period: int = 10,
        multiplier: float = 3.0,
    ) -> SupertrendSignal | None:
        if len(close) < atr_period + 1:
            return None

        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1 / atr_period, adjust=False).mean()

        hl2 = (high + low) / 2
        basic_upper = hl2 + multiplier * atr
        basic_lower = hl2 - multiplier * atr

        upper = basic_upper.copy()
        lower = basic_lower.copy()
        direction = pd.Series(index=close.index, dtype=int)

        for i in range(1, len(close)):
            lower.iloc[i] = (
                basic_lower.iloc[i]
                if basic_lower.iloc[i] > lower.iloc[i - 1] or close.iloc[i - 1] < lower.iloc[i - 1]
                else lower.iloc[i - 1]
            )
            upper.iloc[i] = (
                basic_upper.iloc[i]
                if basic_upper.iloc[i] < upper.iloc[i - 1] or close.iloc[i - 1] > upper.iloc[i - 1]
                else upper.iloc[i - 1]
            )
            if close.iloc[i] > upper.iloc[i - 1]:
                direction.iloc[i] = 1
            elif close.iloc[i] < lower.iloc[i - 1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i - 1] if i > 0 else 1

        supertrend_line = pd.Series(index=close.index, dtype=float)
        supertrend_line[direction == 1] = lower[direction == 1]
        supertrend_line[direction == -1] = upper[direction == -1]

        latest_dir = int(direction.iloc[-1])
        prev_dir = int(direction.iloc[-2]) if len(direction) >= 2 else latest_dir
        st_value = float(supertrend_line.iloc[-1])
        latest_close = float(close.iloc[-1])

        if pd.isna(st_value) or st_value <= 0:
            return None

        trend: SupertrendDirection = "bullish" if latest_dir == 1 else "bearish"
        just_flipped = latest_dir != prev_dir
        distance_pct = round(abs(latest_close - st_value) / st_value * 100, 2)

        return SupertrendSignal(
            direction=trend,
            supertrend_value=round(st_value, 4),
            just_flipped=just_flipped,
            distance_pct=distance_pct,
            atr_period=atr_period,
            multiplier=multiplier,
            tag=f"supertrend:{'flipped_' if just_flipped else ''}{trend}",
        )

    @staticmethod
    def _relative_strength(
        close: pd.Series,
        benchmark_scores: list[float] | None = None,
        weights: tuple[float, float, float, float] = (0.4, 0.2, 0.2, 0.2),
    ) -> RelativeStrengthSignal | None:
        """Calculate IBD-style RS score and rank."""
        if len(close) < 63:
            return None

        def _perf(bars: int) -> float | None:
            if len(close) < bars + 1:
                return None
            start = float(close.iloc[-(bars + 1)])
            end = float(close.iloc[-1])
            if start <= 0:
                return None
            return round((end - start) / start * 100, 2)

        perf_3m = _perf(63)
        perf_6m = _perf(126)
        perf_9m = _perf(189)
        perf_12m = _perf(252)

        w3, w6, w9, w12 = weights
        resolved_weights = []
        values = []
        for w, v in [(w3, perf_3m), (w6, perf_6m), (w9, perf_9m), (w12, perf_12m)]:
            if v is not None:
                resolved_weights.append(w)
                values.append(v)
        weights = resolved_weights

        if not values:
            return None

        total_weight = sum(weights)
        rs_score = round(sum(w * v for w, v in zip(weights, values)) / total_weight, 4)

        if benchmark_scores and len(benchmark_scores) > 0:
            below = sum(1 for s in benchmark_scores if s < rs_score)
            rs_rank = round(below / len(benchmark_scores) * 100)
        else:
            rs_rank = 50

        rs_rank = max(0, min(100, rs_rank))

        return RelativeStrengthSignal(
            rs_score=rs_score,
            rs_rank=rs_rank,
            perf_3m=perf_3m,
            perf_6m=perf_6m,
            perf_9m=perf_9m,
            perf_12m=perf_12m,
            tag=f"rs_rank:{rs_rank}|score:{rs_score}",
        )

    @staticmethod
    def _historical_volatility(close: pd.Series, length: int = 30) -> float | None:
        returns = close.pct_change().dropna()
        if len(returns) < length:
            return None
        return float(returns.tail(length).std() * (252 ** 0.5) * 100)

    @staticmethod
    def _bollinger_state(
        close: pd.Series,
        length: int = 20,
        squeeze_quantile: float = 0.2,
        low_quantile: float = 0.35,
        high_quantile: float = 0.8,
    ) -> str:
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
        if latest_bandwidth <= bandwidth.dropna().quantile(squeeze_quantile):
            return "squeeze"
        if latest_bandwidth >= bandwidth.dropna().quantile(high_quantile):
            return "high"
        if latest_bandwidth <= bandwidth.dropna().quantile(low_quantile):
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
    def _volume_trend(
        volume: pd.Series,
        bullish_multiplier: float = 1.25,
        bearish_multiplier: float = 0.75,
    ) -> str:
        average_volume = volume.rolling(20).mean().iloc[-1]
        latest_volume = volume.iloc[-1]
        if pd.isna(average_volume) or average_volume == 0:
            return "neutral"
        if latest_volume > average_volume * bullish_multiplier:
            return "bullish"
        if latest_volume < average_volume * bearish_multiplier:
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
    def _momentum_tag(
        rsi: float | None,
        histogram: float | None,
        divergence: str,
        overbought: float = 70.0,
        oversold: float = 30.0,
    ) -> str:
        if divergence != "none":
            return f"momentum:{divergence}"
        if rsi is not None and rsi >= overbought:
            return "momentum:overbought"
        if rsi is not None and rsi <= oversold:
            return "momentum:oversold"
        if histogram is not None and histogram > 0:
            return "momentum:positive"
        if histogram is not None and histogram < 0:
            return "momentum:negative"
        return "momentum:neutral"

    @staticmethod
    def _volume_tag(
        mfi: float | None,
        volume_trend: str,
        overbought: float = 80.0,
        oversold: float = 20.0,
    ) -> str:
        if mfi is not None and mfi >= overbought:
            return "volume:overbought_flow"
        if mfi is not None and mfi <= oversold:
            return "volume:oversold_flow"
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
    def _fit_trendlines(high: pd.Series, low: pd.Series, close: pd.Series) -> TrendlineSignal:
        n = len(close)
        if n < 30:
            return TrendlineSignal(state="undefined")
        x = np.arange(n)
        coefs = np.polyfit(x, close.values, 1)
        line_points = coefs[0] * x + coefs[1]
        upper_pivot = int((high.values - line_points).argmax())
        lower_pivot = int((low.values - line_points).argmin())

        try:
            support_coefs = _optimize_slope(True, lower_pivot, coefs[0], low.values)
            resist_coefs = _optimize_slope(False, upper_pivot, coefs[0], high.values)
        except Exception:
            return TrendlineSignal(state="undefined")

        support_slope, support_intercept = support_coefs
        resistance_slope, resistance_intercept = resist_coefs

        support_price = float(support_slope * (n - 1) + support_intercept)
        resistance_price = float(resistance_slope * (n - 1) + resistance_intercept)

        support_err = _check_trend_line(True, lower_pivot, support_slope, low.values)
        resistance_err = _check_trend_line(False, upper_pivot, resistance_slope, high.values)

        support_quality = float(1.0 / (1.0 + support_err)) if support_err >= 0 else None
        resistance_quality = float(1.0 / (1.0 + resistance_err)) if resistance_err >= 0 else None

        slope_diff = resistance_slope - support_slope
        if abs(slope_diff) < abs(support_slope) * 0.15:
            state = "parallel"
        elif slope_diff < 0:
            state = "compressing"
        else:
            state = "expanding"

        return TrendlineSignal(
            support_slope=round(float(support_slope), 6),
            support_intercept=round(float(support_intercept), 4),
            resistance_slope=round(float(resistance_slope), 6),
            resistance_intercept=round(float(resistance_intercept), 4),
            support_price=round(support_price, 2),
            resistance_price=round(resistance_price, 2),
            support_quality=round(support_quality, 4) if support_quality is not None else None,
            resistance_quality=round(resistance_quality, 4) if resistance_quality is not None else None,
            state=state,
            tag=f"trendline:{state}",
        )

    @staticmethod
    def _detect_patterns(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series) -> PatternSignal:
        patterns: list[str] = []
        bullish_count = 0
        bearish_count = 0

        body = (close - open_).abs()
        upper_shadow = high - close.combine(open_, max)
        lower_shadow = close.combine(open_, min) - low
        total_range = high - low

        latest_body = body.iloc[-1]
        latest_upper = upper_shadow.iloc[-1]
        latest_lower = lower_shadow.iloc[-1]
        latest_range = total_range.iloc[-1]

        if latest_range > 0:
            body_ratio = latest_body / latest_range
        else:
            body_ratio = 1.0

        if body_ratio < 0.1:
            patterns.append("doji")
        elif body_ratio < 0.35 and latest_lower > latest_body * 2 and latest_upper < latest_body * 0.5:
            patterns.append("hammer")
            bullish_count += 1
        elif body_ratio < 0.35 and latest_upper > latest_body * 2 and latest_lower < latest_body * 0.5:
            patterns.append("shooting_star")
            bearish_count += 1

        if len(close) >= 2:
            prev_open = open_.iloc[-2]
            prev_close = close.iloc[-2]
            curr_open = open_.iloc[-1]
            curr_close = close.iloc[-1]

            if prev_close < prev_open and curr_close > curr_open:
                if curr_close > prev_open and curr_open < prev_close:
                    patterns.append("bullish_engulfing")
                    bullish_count += 1
            elif prev_close > prev_open and curr_close < curr_open:
                if curr_close < prev_open and curr_open > prev_close:
                    patterns.append("bearish_engulfing")
                    bearish_count += 1

            if prev_close < prev_open and curr_close > curr_open:
                if curr_open < prev_close and curr_close > (prev_open + prev_close) / 2:
                    patterns.append("piercing_line")
                    bullish_count += 1

        if len(close) >= 3:
            first_open = open_.iloc[-3]
            first_close = close.iloc[-3]
            second_open = open_.iloc[-2]
            second_close = close.iloc[-2]
            curr_open = open_.iloc[-1]
            curr_close = close.iloc[-1]

            second_body = abs(second_close - second_open)
            first_body = abs(first_close - first_open)
            curr_body = abs(curr_close - curr_open)

            if first_close < first_open and curr_close > curr_open:
                if second_body < first_body * 0.3 and curr_body > first_body * 0.6:
                    if curr_close > (first_open + first_close) / 2:
                        patterns.append("morning_star")
                        bullish_count += 1
            elif first_close > first_open and curr_close < curr_open:
                if second_body < first_body * 0.3 and curr_body > first_body * 0.6:
                    if curr_close < (first_open + first_close) / 2:
                        patterns.append("evening_star")
                        bearish_count += 1

        if bullish_count > bearish_count:
            sentiment = "bullish"
        elif bearish_count > bullish_count:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        primary = patterns[0] if patterns else None
        return PatternSignal(
            detected_patterns=patterns,
            primary_pattern=primary,
            pattern_sentiment=sentiment,
            tag=f"pattern:{sentiment}",
        )

    @staticmethod
    def _latest(series: pd.Series) -> float | None:
        cleaned = series.dropna()
        if cleaned.empty:
            return None
        return float(cleaned.iloc[-1])


def _check_trend_line(support: bool, pivot: int, slope: float, y: np.ndarray) -> float:
    intercept = -slope * pivot + y[pivot]
    line_vals = slope * np.arange(len(y)) + intercept
    diffs = line_vals - y
    if support and diffs.max() > 1e-5:
        return -1.0
    if not support and diffs.min() < -1e-5:
        return -1.0
    return float((diffs ** 2.0).sum())


def _optimize_slope(support: bool, pivot: int, init_slope: float, y: np.ndarray) -> tuple[float, float]:
    slope_unit = (y.max() - y.min()) / len(y)
    opt_step = 1.0
    min_step = 0.0001
    curr_step = opt_step
    best_slope = init_slope
    best_err = _check_trend_line(support, pivot, init_slope, y)
    if best_err < 0:
        raise ValueError("Initial slope invalid")
    get_derivative = True
    derivative = None
    while curr_step > min_step:
        if get_derivative:
            slope_change = best_slope + slope_unit * min_step
            test_err = _check_trend_line(support, pivot, slope_change, y)
            derivative = test_err - best_err
            if test_err < 0.0:
                slope_change = best_slope - slope_unit * min_step
                test_err = _check_trend_line(support, pivot, slope_change, y)
                derivative = best_err - test_err
            if test_err < 0.0:
                raise ValueError("Derivative failed")
            get_derivative = False
        if derivative > 0.0:
            test_slope = best_slope - slope_unit * curr_step
        else:
            test_slope = best_slope + slope_unit * curr_step
        test_err = _check_trend_line(support, pivot, test_slope, y)
        if test_err < 0 or test_err >= best_err:
            curr_step *= 0.5
        else:
            best_err = test_err
            best_slope = test_slope
            get_derivative = True
    return (best_slope, -best_slope * pivot + y[pivot])


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
