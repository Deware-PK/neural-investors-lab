"""Unit tests for config-driven and adaptive IndicatorMath thresholds."""

import sys

import numpy as np
import pandas as pd
import pytest

from src.core.config import Settings
from src.models.market_data_schema import FinancialStatement, TickerProfile
from src.services.indicator_math import IndicatorMath

sys.stdout.reconfigure(encoding="utf-8")


def _make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def _flat_price_frame(length: int = 300, start_price: float = 100.0) -> pd.DataFrame:
    """A mildly oscillating price series long enough for full technical analysis."""
    rng = np.random.default_rng(42)
    noise = rng.normal(0, 0.5, length)
    close = start_price + np.cumsum(noise)
    close = np.clip(close, start_price * 0.5, start_price * 1.5)
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.2
    volume = np.full(length, 1_000_000.0)
    dates = pd.date_range("2023-01-01", periods=length, freq="D")
    return pd.DataFrame(
        {"date": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


class TestConfigDrivenTechnicalThresholds:
    def test_default_settings_match_previous_hardcoded_behavior(self) -> None:
        """Default Settings values must reproduce the original hardcoded thresholds."""
        settings = _make_settings()
        assert settings.rsi_overbought == 70.0
        assert settings.rsi_oversold == 30.0
        assert settings.mfi_overbought == 80.0
        assert settings.mfi_oversold == 20.0
        assert settings.volume_trend_bullish_multiplier == 1.25
        assert settings.volume_trend_bearish_multiplier == 0.75
        assert settings.bollinger_squeeze_quantile == 0.2
        assert settings.bollinger_low_quantile == 0.35
        assert settings.bollinger_high_quantile == 0.8
        assert (settings.rs_weight_3m, settings.rs_weight_6m, settings.rs_weight_9m, settings.rs_weight_12m) == (
            0.4,
            0.2,
            0.2,
            0.2,
        )
        assert settings.supertrend_atr_period == 10
        assert settings.supertrend_multiplier == 3.0
        assert settings.adaptive_thresholds is False

    def test_custom_rsi_threshold_changes_momentum_tag(self) -> None:
        """Lowering the overbought threshold should flip a mid-range RSI into 'overbought'."""
        loose = IndicatorMath(settings=_make_settings(rsi_overbought=50.0, rsi_oversold=30.0))
        strict = IndicatorMath(settings=_make_settings(rsi_overbought=70.0, rsi_oversold=30.0))
        tag_loose = loose._momentum_tag(60.0, 0.5, "none", overbought=loose.settings.rsi_overbought, oversold=loose.settings.rsi_oversold)
        tag_strict = strict._momentum_tag(60.0, 0.5, "none", overbought=strict.settings.rsi_overbought, oversold=strict.settings.rsi_oversold)
        assert tag_loose == "momentum:overbought"
        assert tag_strict == "momentum:positive"

    def test_volume_trend_multiplier_is_configurable(self) -> None:
        volume = pd.Series([1_000_000.0] * 19 + [1_100_000.0])
        default_trend = IndicatorMath._volume_trend(volume)
        assert default_trend == "neutral"
        loose_trend = IndicatorMath._volume_trend(volume, bullish_multiplier=1.05)
        assert loose_trend == "bullish"

    def test_relative_strength_weights_are_configurable(self) -> None:
        close = pd.Series([100.0 * (1.01 ** i) for i in range(300)])
        default_result = IndicatorMath._relative_strength(close)
        custom_result = IndicatorMath._relative_strength(close, weights=(0.1, 0.1, 0.1, 0.7))
        assert default_result is not None
        assert custom_result is not None
        assert default_result.rs_score != custom_result.rs_score


class TestConfigDrivenFundamentalThresholds:
    def test_peg_regime_threshold_configurable(self) -> None:
        default_vi = IndicatorMath._compute_vi_scores(piotroski=None, peg=0.9, altman=None)
        assert default_vi["valuation_regime"] == "reasonable"
        custom_vi = IndicatorMath._compute_vi_scores(
            piotroski=None, peg=0.9, altman=None, peg_regime_cheap=1.0
        )
        assert custom_vi["valuation_regime"] == "cheap"

    def test_altman_insolvency_threshold_configurable(self) -> None:
        default_vi = IndicatorMath._compute_vi_scores(piotroski=None, peg=None, altman=1.2)
        assert default_vi["hard_block_fundamental"] == "none"
        custom_vi = IndicatorMath._compute_vi_scores(
            piotroski=None, peg=None, altman=1.2, altman_insolvency_threshold=1.5
        )
        assert custom_vi["hard_block_fundamental"] == "insolvency_risk"

    def test_analyze_fundamentals_uses_settings_piotroski_cutoff(self) -> None:
        income_statement = FinancialStatement(
            ticker="TEST",
            statement_type="income_statement",
            period="annual",
            columns=["2024"],
            rows={
                "Net Income": {"2024": 100.0},
                "Total Revenue": {"2024": 1000.0},
                "Gross Profit": {"2024": 400.0},
            },
        )
        balance_sheet = FinancialStatement(
            ticker="TEST",
            statement_type="balance_sheet",
            period="annual",
            columns=["2024"],
            rows={
                "Total Assets": {"2024": 1000.0},
                "Current Assets": {"2024": 500.0},
                "Current Liabilities": {"2024": 200.0},
            },
        )
        profile = TickerProfile(ticker="TEST", currency="USD", market_cap=1_000_000.0)

        loose = IndicatorMath(settings=_make_settings(piotroski_strong_threshold=1))
        result = loose.analyze_fundamentals("TEST", profile, income_statement, balance_sheet)
        if result.piotroski_f_score is not None and result.piotroski_f_score >= 1:
            assert "Strong Piotroski F-Score" in result.strengths


class TestAdaptiveThresholds:
    def test_adaptive_disabled_by_default_uses_fixed_thresholds(self) -> None:
        math = IndicatorMath(settings=_make_settings())
        rsi = pd.Series(np.linspace(20, 80, 300))
        overbought, oversold = math._resolve_rsi_thresholds(rsi)
        assert overbought == 70.0
        assert oversold == 30.0

    def test_adaptive_enabled_uses_percentile_of_own_history(self) -> None:
        math = IndicatorMath(
            settings=_make_settings(
                adaptive_thresholds=True,
                adaptive_lookback=252,
                adaptive_percentile_overbought=0.9,
                adaptive_percentile_oversold=0.1,
            )
        )
        rsi = pd.Series(np.linspace(20, 60, 252))
        overbought, oversold = math._resolve_rsi_thresholds(rsi)
        assert overbought == pytest.approx(rsi.quantile(0.9))
        assert oversold == pytest.approx(rsi.quantile(0.1))
        assert overbought != 70.0

    def test_adaptive_falls_back_when_insufficient_history(self) -> None:
        math = IndicatorMath(settings=_make_settings(adaptive_thresholds=True, adaptive_lookback=252))
        rsi = pd.Series(np.linspace(20, 60, 60))
        overbought, oversold = math._resolve_rsi_thresholds(rsi)
        assert overbought == 70.0
        assert oversold == 30.0

    def test_adaptive_mfi_thresholds(self) -> None:
        math = IndicatorMath(
            settings=_make_settings(
                adaptive_thresholds=True,
                adaptive_lookback=252,
                adaptive_percentile_overbought=0.9,
                adaptive_percentile_oversold=0.1,
            )
        )
        mfi = pd.Series(np.linspace(10, 90, 252))
        overbought, oversold = math._resolve_mfi_thresholds(mfi)
        assert overbought == pytest.approx(mfi.quantile(0.9))
        assert oversold == pytest.approx(mfi.quantile(0.1))

    def test_analyze_technical_end_to_end_adaptive_vs_fixed(self) -> None:
        frame = _flat_price_frame()
        fixed_math = IndicatorMath(settings=_make_settings(adaptive_thresholds=False))
        adaptive_math = IndicatorMath(settings=_make_settings(adaptive_thresholds=True))
        fixed_result = fixed_math.analyze_technical("TEST", frame)
        adaptive_result = adaptive_math.analyze_technical("TEST", frame)
        assert fixed_result.momentum.tag is not None
        assert adaptive_result.momentum.tag is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
