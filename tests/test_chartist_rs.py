"""Tests for ChartistAgent SPY benchmark RS rank integration."""

import sys

import pandas as pd
import pytest
from unittest.mock import MagicMock

from src.agents.chartist import ChartistAgent
from src.models.market_data_schema import PriceBar
from src.models.technical_schema import RelativeStrengthSignal
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath

sys.stdout.reconfigure(encoding="utf-8")


def _make_bars(n: int = 300, start: float = 100.0, growth: float = 1.0) -> list[PriceBar]:
    """Return a list of mock PriceBar-like objects."""
    from datetime import date, timedelta
    bars: list[PriceBar] = []
    base = date(2022, 1, 1)
    price = start
    for i in range(n):
        bars.append(
            PriceBar(
                date=base + timedelta(days=i),
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1_000_000,
            )
        )
        price *= 1 + growth / 100
    return bars


class TestChartistSPYBenchmark:
    def test_spy_rs_score_injected_when_available(self) -> None:
        """analyze() must send benchmark_scores=[spy_score] into analyze_technical."""
        ticker_bars = _make_bars(300, start=100.0, growth=2.0)
        spy_bars = _make_bars(300, start=450.0, growth=0.5)
        mock_finance = MagicMock(spec=FinanceAPI)
        mock_finance.fetch_historical_prices.side_effect = lambda sym, **kw: (
            ticker_bars if sym != "SPY" else spy_bars
        )
        mock_finance.fetch_multi_timeframe.side_effect = Exception("skip mtf")

        mock_math = MagicMock(spec=IndicatorMath)
        spy_signal = RelativeStrengthSignal(
            rs_score=25.0, rs_rank=50, tag="rs_rank:50|score:25.0"
        )
        mock_math._relative_strength.return_value = spy_signal
        mock_math.normalize_price_frame.return_value = pd.DataFrame({"close": [1.0] * 300})

        fake_result = MagicMock()
        fake_result.close_price = 5.0
        fake_result.moving_average.state = "uptrend"
        fake_result.momentum.rsi = 60.0
        fake_result.momentum.tag = "bullish"
        fake_result.volume.volume_trend = "rising"
        fake_result.volatility.bollinger_state = "normal"
        fake_result.support_levels = []
        fake_result.resistance_levels = []
        fake_result.multi_timeframe = None
        fake_result.relative_strength = spy_signal
        mock_math.analyze_technical.return_value = fake_result

        agent = ChartistAgent(finance_api=mock_finance, indicator_math=mock_math)
        agent.analyze("NOK")

        call_kwargs = mock_math.analyze_technical.call_args
        benchmark = call_kwargs.kwargs.get("benchmark_scores") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        )
        assert benchmark is not None, "benchmark_scores must not be None when SPY fetch succeeds"
        assert isinstance(benchmark, list)
        assert len(benchmark) == 1

    def test_spy_fetch_failure_falls_back_to_none(self) -> None:
        """If SPY fetch fails, benchmark_scores must be None and no exception raised."""
        ticker_bars = _make_bars(300)
        mock_finance = MagicMock(spec=FinanceAPI)
        mock_finance.fetch_historical_prices.side_effect = lambda sym, **kw: (
            ticker_bars if sym != "SPY" else (_ for _ in ()).throw(RuntimeError("SPY failed"))
        )
        mock_finance.fetch_multi_timeframe.side_effect = Exception("skip mtf")

        mock_math = MagicMock(spec=IndicatorMath)
        fake_result = MagicMock()
        fake_result.close_price = 5.0
        fake_result.moving_average.state = "uptrend"
        fake_result.momentum.rsi = 55.0
        fake_result.momentum.tag = "neutral"
        fake_result.volume.volume_trend = "flat"
        fake_result.volatility.bollinger_state = "normal"
        fake_result.support_levels = []
        fake_result.resistance_levels = []
        fake_result.multi_timeframe = None
        fake_result.relative_strength = None
        mock_math.analyze_technical.return_value = fake_result

        agent = ChartistAgent(finance_api=mock_finance, indicator_math=mock_math)
        result = agent.analyze("NOK")

        call_kwargs = mock_math.analyze_technical.call_args
        benchmark = call_kwargs.kwargs.get("benchmark_scores") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        )
        assert benchmark is None, "benchmark_scores must be None when SPY fetch fails"
        assert result is fake_result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
