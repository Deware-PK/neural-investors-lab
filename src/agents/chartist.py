import logging

from src.models.technical_schema import TechnicalAnalysis
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)


class ChartistAgent:
    def __init__(self, finance_api: FinanceAPI | None = None, indicator_math: IndicatorMath | None = None) -> None:
        self.finance_api = finance_api or FinanceAPI()
        self.indicator_math = indicator_math or IndicatorMath()

    def analyze(self, ticker: str, period: str = "2y", interval: str = "1d") -> TechnicalAnalysis:
        symbol = ticker.upper()
        logger.info("Chartist started for %s", symbol)
        history = self.finance_api.fetch_historical_prices(symbol, period=period, interval=interval)
        result = self.indicator_math.analyze_technical(symbol, history)
        logger.info("Chartist completed for %s", symbol)
        return result
