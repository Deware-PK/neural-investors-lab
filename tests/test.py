import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import get_settings
from src.core.logging import configure_logging
from src.evaluation.backtest_engine import BacktestEngine
from src.evaluation.performance_logger import PerformanceLogger
from src.evaluation.synthetic_signal_generator import SyntheticSignalGenerator
from src.interfaces.formatter import format_boardroom_result_html, format_final_synthesis_html
from src.main_orchestrator import BoardroomOrchestrator
from src.models.agent_schema import ConflictAssessment, StrategyDraft
from src.models.edgar_schema import EdgarBundle
from src.models.evaluation_schema import HistoricalPrediction
from src.models.fundamental_schema import FundamentalAnalysis, FundamentalSnapshot
from src.models.market_data_schema import PriceBar
from src.models.research_schema import ResearchFinding
from src.models.synthesis_schema import Action, FinalSynthesis, RiskDecision
from src.models.technical_schema import (
    MomentumSignal,
    MovingAverageAlignment,
    TechnicalAnalysis,
    VolatilitySignal,
    VolumeSignal,
)
from src.models.vision_schema import VisualChartAnalysis


class FakeAuditor:
    def analyze(self, ticker: str, edgar_bundle: EdgarBundle | None = None) -> FundamentalAnalysis:
        return FundamentalAnalysis(
            ticker=ticker,
            snapshot=FundamentalSnapshot(ticker=ticker, currency="USD"),
            piotroski_f_score=8,
            peg_ratio=0.8,
            altman_z_score=4.2,
            strengths=["Strong deterministic fundamentals"],
            weaknesses=[],
            tags=["piotroski:8", "altman:safe"],
        )


class FakeChartist:
    def analyze(self, ticker: str) -> TechnicalAnalysis:
        return TechnicalAnalysis(
            ticker=ticker,
            close_price=100,
            moving_average=MovingAverageAlignment(state="bullish"),
            momentum=MomentumSignal(rsi=55, divergence="none"),
            volume=VolumeSignal(volume_trend="bullish"),
            volatility=VolatilitySignal(atr=2, historical_volatility=20, bollinger_state="normal"),
            support_levels=[95],
            resistance_levels=[110],
            tags=["trend:bullish", "volume:bullish"],
        )

    async def get_visual_analysis(self, ticker: str) -> VisualChartAnalysis:
        return VisualChartAnalysis(
            ticker=ticker,
            sentiment="bullish",
            confidence_score=0.7,
            summary="Synthetic visual chart analysis.",
            observed_patterns=["Higher highs"],
            support_zones=[95],
            resistance_zones=[110],
            risks=["Synthetic chart risk"],
        )


class FakeResearcher:
    def analyze(self, ticker: str, article_urls: list[str] | None = None, context: str | None = None, edgar_bundle: EdgarBundle | None = None) -> ResearchFinding:
        return ResearchFinding(
            ticker=ticker,
            sentiment="bullish",
            sentiment_score=0.5,
            summary="Offline narrative smoke test.",
            catalysts=["Synthetic catalyst"],
            concerns=[],
            articles=[],
        )

    def investigate_conflict(self, ticker: str, query: str, article_urls: list[str] | None = None) -> ResearchFinding:
        return self.analyze(ticker, article_urls=article_urls, context=query)


class FakeChiefStrategist:
    def identify_contradictions(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
    ) -> ConflictAssessment:
        return ConflictAssessment(ticker=fundamentals.ticker, has_conflict=False)

    def draft_strategy_with_assessment(
        self,
        fundamentals: FundamentalAnalysis,
        technicals: TechnicalAnalysis,
        research: ResearchFinding,
        conflict: ConflictAssessment,
        visual_chart_analysis: VisualChartAnalysis | None = None,
        macro_context: Any = None,
        options_flow: Any = None,
    ) -> StrategyDraft:
        return StrategyDraft(
            ticker=fundamentals.ticker,
            action=Action.BUY,
            conviction_score=70,
            entry_price=100,
            take_profit=115,
            stop_loss=95,
            proposed_position_size_pct=5,
            thesis="Offline boardroom smoke test passed deterministic handoffs.",
            key_risks=["Synthetic risk"],
            evidence=[],
            conflict_assessment=conflict,
        )


class FakeRiskManager:
    def finalize(self, draft: StrategyDraft, technicals: TechnicalAnalysis | None = None) -> FinalSynthesis:
        return FinalSynthesis(
            ticker=draft.ticker,
            action=draft.action,
            conviction_score=draft.conviction_score,
            entry_price=draft.entry_price,
            take_profit=draft.take_profit,
            stop_loss=draft.stop_loss,
            position_size_pct=4,
            risk_decision=RiskDecision.APPROVED,
            thesis=draft.thesis,
            key_risks=draft.key_risks,
            evidence=draft.evidence,
        )


def run_offline_smoke_test() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    missing = settings.missing_runtime_secrets()
    print("Settings load: OK")
    print(f"Runtime secrets present: {'yes' if not missing else 'no'}")
    if missing:
        print(f"Missing runtime secrets: {', '.join(missing)}")

    final = FinalSynthesis(
        ticker="SMOKE",
        action=Action.HOLD,
        conviction_score=50,
        position_size_pct=0,
        risk_decision=RiskDecision.APPROVED,
        thesis="Offline schema validation.",
    )
    html = format_final_synthesis_html(final)
    assert "SMOKE" in html
    print("Schema and formatter: OK")

    synthetic_final = FinalSynthesis(
        ticker="TEST",
        action=Action.BUY,
        conviction_score=70,
        entry_price=100,
        take_profit=110,
        stop_loss=95,
        position_size_pct=4,
        risk_decision=RiskDecision.APPROVED,
        thesis="Synthetic backtest fixture.",
    )
    prediction = HistoricalPrediction(
        record_id="offline-1",
        ticker="TEST",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        synthesis=synthetic_final,
    )
    bars = [
        PriceBar(
            date=date(2024, 1, 1) + timedelta(days=index),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1000,
        )
        for index in range(31)
    ]
    outcome = BacktestEngine.calculate_outcome(prediction, bars)
    report = PerformanceLogger().build_report([outcome])
    assert outcome.outcome == "take_profit_hit"
    assert report.win_rate_pct == 100
    print("Backtest and performance analytics: OK")

    result = asyncio.run(
        BoardroomOrchestrator(
            auditor=FakeAuditor(),
            chartist=FakeChartist(),
            researcher=FakeResearcher(),
            chief_strategist=FakeChiefStrategist(),
            risk_manager=FakeRiskManager(),
        ).analyze_ticker("TEST", persist=False)
    )
    boardroom_html = format_boardroom_result_html(result)
    assert result.final_synthesis.action == Action.BUY
    assert "Boardroom Signals" in boardroom_html
    print("Offline boardroom orchestration: OK")
    print("Offline smoke test completed successfully.")


def run_live_test(ticker: str, article_urls: list[str], persist: bool) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.openrouter_api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is required for live mode.")
    result = asyncio.run(
        BoardroomOrchestrator(settings=settings).analyze_ticker(
            ticker=ticker,
            article_urls=article_urls,
            persist=persist,
        )
    )
    print(format_boardroom_result_html(result))


def run_synthetic_backtest_generation(tickers: list[str]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    generator = SyntheticSignalGenerator()
    total = 0
    for ticker in tickers:
        symbol = ticker.upper()
        count = generator.generate(symbol)
        print(f"Synthetic signals generated for {symbol}: {count}")
        total += count
    print(f"\nTotal signals generated across {len(tickers)} tickers: {total}")
    if total > 0:
        print("Running backtest on all data...")
        run_backtest_report()


def run_backtest_report() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = BacktestEngine()
    outcomes = engine.run()
    report = PerformanceLogger().build_report(outcomes)
    print("\nBacktest Report")
    print(f"Total trades: {report.total_trades}")
    print(f"Win rate: {report.win_rate_pct:.2f}%")
    t7 = f"{report.average_t7_return_pct:.2f}%" if report.average_t7_return_pct is not None else "N/A"
    t30 = f"{report.average_t30_return_pct:.2f}%" if report.average_t30_return_pct is not None else "N/A"
    mdd = f"{report.average_max_drawdown_pct:.2f}%" if report.average_max_drawdown_pct is not None else "N/A"
    print(f"Avg T+7 return: {t7}")
    print(f"Avg T+30 return: {t30}")
    print(f"Avg max drawdown: {mdd}")
    print(f"Outcomes: {', '.join(f'{k}={v}' for k, v in sorted(report.outcomes.items()))}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("reports") / f"backtest_{timestamp}.json"
    PerformanceLogger().write_json_report(report, report_path)
    print(f"Saved JSON report to: {report_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Neural Investors Lab console test runner")
    parser.add_argument("--live", metavar="TICKER", help="run live Boardroom analysis for a ticker")
    parser.add_argument("--article-url", action="append", default=[], help="article URL for live researcher context")
    parser.add_argument("--no-persist", action="store_true", help="skip PostgreSQL persistence in live mode")
    parser.add_argument("--backtest-report", action="store_true", help="run backtest on historical predictions and save JSON report")
    parser.add_argument("--generate-synthetic-backtest", metavar="TICKER", nargs="+", help="generate synthetic historical signals for one or more tickers then backtest")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.generate_synthetic_backtest:
        run_synthetic_backtest_generation(args.generate_synthetic_backtest)
        return
    if args.backtest_report:
        run_backtest_report()
        return
    if args.live:
        run_live_test(args.live.upper(), args.article_url, persist=not args.no_persist)
        return
    run_offline_smoke_test()


if __name__ == "__main__":
    main()
