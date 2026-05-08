import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from src.core.db_postgres import create_session_factory, fetch_historical_analysis_outputs
from src.models.evaluation_schema import BacktestOutcome, HistoricalPrediction
from src.models.market_data_schema import PriceBar
from src.models.synthesis_schema import Action, FinalSynthesis
from src.services.finance_api import FinanceAPI


logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(self, finance_api: FinanceAPI | None = None, session_factory: sessionmaker[Session] | None = None) -> None:
        self.finance_api = finance_api or FinanceAPI()
        self.session_factory = session_factory or create_session_factory()

    def load_buy_recommendations(self) -> list[HistoricalPrediction]:
        session = self.session_factory()
        try:
            rows = fetch_historical_analysis_outputs(session, actions=[Action.BUY.value, Action.ACCUMULATE.value])
        finally:
            session.close()
        predictions: list[HistoricalPrediction] = []
        for row in rows:
            synthesis = FinalSynthesis.model_validate(row["output"])
            if synthesis.entry_price is None or synthesis.take_profit is None or synthesis.stop_loss is None:
                continue
            predictions.append(
                HistoricalPrediction(
                    record_id=str(row["id"]),
                    ticker=str(row["ticker"]),
                    created_at=row["created_at"],
                    synthesis=synthesis,
                )
            )
        return predictions

    def run(self) -> list[BacktestOutcome]:
        outcomes: list[BacktestOutcome] = []
        for prediction in self.load_buy_recommendations():
            try:
                outcomes.append(self.evaluate_prediction(prediction))
            except Exception:
                logger.exception("Failed to evaluate prediction %s for %s", prediction.record_id, prediction.ticker)
        return outcomes

    def evaluate_prediction(self, prediction: HistoricalPrediction) -> BacktestOutcome:
        start_date = prediction.created_at.date()
        end_date = start_date + timedelta(days=35)
        bars = self.finance_api.fetch_historical_prices(
            prediction.ticker,
            period="60d",
            interval="1d",
        )
        window = self._filter_forward_window(bars, start_date, end_date)
        return self.calculate_outcome(prediction, window)

    @staticmethod
    def calculate_outcome(prediction: HistoricalPrediction, bars: list[PriceBar]) -> BacktestOutcome:
        synthesis = prediction.synthesis
        if synthesis.entry_price is None or synthesis.take_profit is None or synthesis.stop_loss is None:
            msg = "Prediction does not contain complete trade levels"
            raise ValueError(msg)
        if not bars:
            return BacktestOutcome(
                record_id=prediction.record_id,
                ticker=prediction.ticker,
                action=synthesis.action,
                created_at=prediction.created_at,
                entry_price=synthesis.entry_price,
                take_profit=synthesis.take_profit,
                stop_loss=synthesis.stop_loss,
                outcome="insufficient_data",
            )

        sorted_bars = sorted(bars, key=lambda bar: bar.date)
        hit_take_profit = any(bar.high >= synthesis.take_profit for bar in sorted_bars)
        hit_stop_loss = any(bar.low <= synthesis.stop_loss for bar in sorted_bars)
        outcome = BacktestEngine._resolve_outcome(sorted_bars, synthesis.take_profit, synthesis.stop_loss)
        t7_return = BacktestEngine._forward_return(sorted_bars, synthesis.entry_price, days=7)
        t30_return = BacktestEngine._forward_return(sorted_bars, synthesis.entry_price, days=30)
        max_drawdown = BacktestEngine._max_drawdown(sorted_bars, synthesis.entry_price)
        return BacktestOutcome(
            record_id=prediction.record_id,
            ticker=prediction.ticker,
            action=synthesis.action,
            created_at=prediction.created_at,
            entry_price=synthesis.entry_price,
            take_profit=synthesis.take_profit,
            stop_loss=synthesis.stop_loss,
            t7_return_pct=t7_return,
            t30_return_pct=t30_return,
            max_drawdown_pct=max_drawdown,
            outcome=outcome,
            hit_take_profit=hit_take_profit,
            hit_stop_loss=hit_stop_loss,
        )

    @staticmethod
    def _filter_forward_window(bars: list[PriceBar], start_date: date, end_date: date) -> list[PriceBar]:
        return [bar for bar in bars if start_date <= bar.date <= end_date]

    @staticmethod
    def _resolve_outcome(bars: list[PriceBar], take_profit: float, stop_loss: float) -> str:
        for bar in bars:
            stop_hit = bar.low <= stop_loss
            profit_hit = bar.high >= take_profit
            if stop_hit and profit_hit:
                return "stop_loss_hit"
            if profit_hit:
                return "take_profit_hit"
            if stop_hit:
                return "stop_loss_hit"
        return "expired" if len(bars) >= 30 else "open"

    @staticmethod
    def _forward_return(bars: list[PriceBar], entry_price: float, days: int) -> float | None:
        if not bars:
            return None
        target_date = bars[0].date + timedelta(days=days)
        candidates = [bar for bar in bars if bar.date >= target_date]
        if not candidates:
            return None
        close_price = candidates[0].close
        return round(((close_price - entry_price) / entry_price) * 100, 2)

    @staticmethod
    def _max_drawdown(bars: list[PriceBar], entry_price: float) -> float | None:
        if not bars:
            return None
        lowest_low = min(bar.low for bar in bars)
        return round(((lowest_low - entry_price) / entry_price) * 100, 2)
