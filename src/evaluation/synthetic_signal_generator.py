import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from src.core.db_postgres import create_session_factory, initialize_database, persist_analysis_output
from src.models.market_data_schema import PriceBar
from src.models.synthesis_schema import Action, EvidenceItem, FinalSynthesis, RiskDecision
from src.models.technical_schema import TechnicalAnalysis
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)

MIN_BARS = 200
COOLDOWN_DAYS = 20
RSI_MIN = 30
RSI_MAX = 55
ATR_STOP_MULTIPLIER = 2.0
ATR_TAKE_PROFIT_MULTIPLIER = 3.0
DEFAULT_POSITION_SIZE_PCT = 5.0


class SyntheticSignalGenerator:
    def __init__(
        self,
        finance_api: FinanceAPI | None = None,
        indicator_math: IndicatorMath | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.finance_api = finance_api or FinanceAPI()
        self.indicator_math = indicator_math or IndicatorMath()
        self.session_factory = session_factory or create_session_factory()

    def generate(self, ticker: str, years: int = 5) -> int:
        symbol = ticker.upper()
        period = f"{years}y"
        logger.info("Fetching %s of daily prices for %s", period, symbol)
        all_bars = self.finance_api.fetch_historical_prices(symbol, period=period, interval="1d")
        if len(all_bars) < MIN_BARS:
            logger.warning(
                "%s has only %d bars (need %d). Skipping.",
                symbol,
                len(all_bars),
                MIN_BARS,
            )
            return 0

        all_bars_sorted = sorted(all_bars, key=lambda bar: bar.date)
        signals_generated = 0
        last_signal_date: datetime | None = None

        session = self.session_factory()
        try:
            initialize_database(session.get_bind())
            for i in range(MIN_BARS, len(all_bars_sorted)):
                window = all_bars_sorted[:i]
                current_bar = all_bars_sorted[i]
                signal_date = current_bar.date

                if last_signal_date is not None:
                    days_since = (signal_date - last_signal_date.date()).days
                    if days_since < COOLDOWN_DAYS:
                        continue

                try:
                    analysis = self.indicator_math.analyze_technical(symbol, window)
                except ValueError:
                    continue

                if not self._signal_conditions_met(analysis):
                    continue

                synthesis = self._build_synthesis(symbol, analysis, signal_date)
                output = synthesis.model_dump(mode="json")
                created_dt = datetime(signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC)
                persist_analysis_output(
                    session,
                    symbol,
                    output,
                    created_at_override=created_dt,
                )
                last_signal_date = created_dt
                signals_generated += 1
                logger.debug(
                    "Signal #%d for %s on %s @ %.2f",
                    signals_generated,
                    symbol,
                    signal_date,
                    analysis.close_price,
                )

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        logger.info("Generated %d synthetic signals for %s", signals_generated, symbol)
        return signals_generated

    @staticmethod
    def _signal_conditions_met(analysis: TechnicalAnalysis) -> bool:
        if analysis.moving_average.state != "bullish":
            return False
        rsi = analysis.momentum.rsi
        if rsi is None or rsi < RSI_MIN or rsi > RSI_MAX:
            return False
        histogram = analysis.momentum.macd_histogram
        if histogram is None or histogram <= 0:
            return False
        if analysis.momentum.divergence == "bearish_divergence":
            return False
        if analysis.volume.volume_trend != "bullish":
            return False
        return True

    @staticmethod
    def _build_synthesis(ticker: str, analysis: TechnicalAnalysis, signal_date: datetime.date) -> FinalSynthesis:
        entry_price = analysis.close_price
        atr = analysis.volatility.atr or (entry_price * 0.02)

        supports = analysis.support_levels
        resistances = analysis.resistance_levels

        atr_stop = entry_price - ATR_STOP_MULTIPLIER * atr
        if supports:
            stop_loss = round(max(supports[0], atr_stop), 2)
        else:
            stop_loss = round(atr_stop, 2)

        atr_tp = entry_price + ATR_TAKE_PROFIT_MULTIPLIER * atr
        if resistances:
            take_profit = round(min(resistances[0], atr_tp), 2)
        else:
            take_profit = round(atr_tp, 2)

        conviction = SyntheticSignalGenerator._compute_conviction(analysis)

        created_dt = datetime(signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC)

        return FinalSynthesis(
            ticker=ticker,
            action=Action.BUY,
            conviction_score=conviction,
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            position_size_pct=DEFAULT_POSITION_SIZE_PCT,
            risk_decision=RiskDecision.APPROVED,
            thesis=SyntheticSignalGenerator._build_thesis(analysis, entry_price, stop_loss, take_profit),
            key_risks=SyntheticSignalGenerator._build_risks(analysis),
            evidence=[
                EvidenceItem(source="moving_average", claim=f"MA alignment: {analysis.moving_average.state}", weight=0.3),
                EvidenceItem(source="momentum", claim=f"RSI={analysis.momentum.rsi}, MACD_hist={analysis.momentum.macd_histogram}", weight=0.3),
                EvidenceItem(source="volume", claim=f"Volume trend: {analysis.volume.volume_trend}", weight=0.2),
                EvidenceItem(source="volatility", claim=f"ATR={atr:.2f}, Bollinger: {analysis.volatility.bollinger_state}", weight=0.2),
            ],
            created_at=created_dt,
        )

    @staticmethod
    def _compute_conviction(analysis: TechnicalAnalysis) -> int:
        score = 0
        if analysis.moving_average.state == "bullish":
            score += 30
        rsi = analysis.momentum.rsi
        if rsi is not None and RSI_MIN <= rsi <= RSI_MAX:
            rsi_mid = (RSI_MIN + RSI_MAX) / 2
            rsi_range = RSI_MAX - RSI_MIN
            rsi_score = 25 - int(abs(rsi - rsi_mid) / rsi_range * 25)
            score += max(0, rsi_score)
        histogram = analysis.momentum.macd_histogram
        if histogram is not None and histogram > 0:
            score += 25
        if analysis.volume.volume_trend == "bullish":
            score += 20
        return min(100, max(0, score))

    @staticmethod
    def _build_thesis(analysis: TechnicalAnalysis, entry: float, stop: float, tp: float) -> str:
        parts = [
            f"Synthetic BUY signal on {analysis.ticker} @ ${entry:.2f}.",
            f"MA alignment is {analysis.moving_average.state} (close > MA50 > MA100 > MA200).",
            f"RSI={analysis.momentum.rsi:.1f}, MACD histogram={analysis.momentum.macd_histogram:.4f}, volume trend={analysis.volume.volume_trend}.",
            f"Stop-loss: ${stop:.2f} (ATR-based), Take-profit: ${tp:.2f}.",
        ]
        return " ".join(parts)

    @staticmethod
    def _build_risks(analysis: TechnicalAnalysis) -> list[str]:
        risks: list[str] = []
        if analysis.momentum.divergence != "none":
            risks.append(f"Divergence present: {analysis.momentum.divergence}")
        if analysis.volatility.bollinger_state in ("squeeze", "breakout"):
            risks.append(f"Bollinger state is {analysis.volatility.bollinger_state} — elevated volatility risk")
        if analysis.volatility.historical_volatility is not None and analysis.volatility.historical_volatility >= 50:
            risks.append(f"High historical volatility: {analysis.volatility.historical_volatility:.1f}%")
        if not risks:
            risks.append("Standard market risk — no elevated technical warnings detected")
        return risks
