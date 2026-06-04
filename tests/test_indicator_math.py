"""Unit tests for IndicatorMath._relative_strength."""

import sys

import pandas as pd
import pytest

from src.models.technical_schema import RelativeStrengthSignal
from src.services.indicator_math import IndicatorMath

sys.stdout.reconfigure(encoding="utf-8")


def _make_series(length: int, start_price: float = 100.0, growth_pct: float = 0.0) -> pd.Series:
    """Generate a close price series."""
    prices = [start_price * (1 + growth_pct / 100) ** i for i in range(length)]
    return pd.Series(prices)


class TestRelativeStrength:
    def test_short_history_returns_none(self) -> None:
        """Less than 63 bars should return None."""
        close = _make_series(60)
        result = IndicatorMath._relative_strength(close)
        assert result is None

    def test_empty_benchmark_defaults_to_50(self) -> None:
        """No benchmark_scores should default rs_rank to 50."""
        close = _make_series(300, start_price=100.0, growth_pct=1.0)
        result = IndicatorMath._relative_strength(close)
        assert result is not None
        assert isinstance(result, RelativeStrengthSignal)
        assert result.rs_rank == 50
        assert result.rs_score > 0
        assert result.perf_3m is not None
        assert result.perf_6m is not None
        assert result.perf_9m is not None
        assert result.perf_12m is not None
        assert result.tag is not None
        assert "rs_rank:" in result.tag
        assert "score:" in result.tag

    def test_benchmark_percentile_rank(self) -> None:
        """rs_rank should reflect percentile against benchmark scores."""
        close = _make_series(300, start_price=100.0, growth_pct=1.0)
        benchmark = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
        result = IndicatorMath._relative_strength(close, benchmark_scores=benchmark)
        assert result is not None
        assert result.rs_rank == 100  # our growth stock outperforms all

    def test_tag_format(self) -> None:
        """Tag should contain both rs_rank and rs_score."""
        close = _make_series(300, start_price=100.0, growth_pct=1.0)
        result = IndicatorMath._relative_strength(close)
        assert result is not None
        assert result.tag.startswith("rs_rank:")
        assert "|score:" in result.tag

    def test_partial_history_falls_back_weights(self) -> None:
        """If only 3 months available, still calculates with available data."""
        close = _make_series(70, start_price=100.0, growth_pct=0.5)
        result = IndicatorMath._relative_strength(close)
        assert result is not None
        assert result.perf_3m is not None
        assert result.perf_6m is None
        assert result.perf_9m is None
        assert result.perf_12m is None
        assert result.rs_score > 0

    def test_negative_returns_allowed(self) -> None:
        """Negative performance should still produce valid RS."""
        close = _make_series(300, start_price=100.0, growth_pct=-0.5)
        result = IndicatorMath._relative_strength(close)
        assert result is not None
        assert result.rs_score < 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
