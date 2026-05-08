import logging

from src.models.fundamental_schema import FundamentalAnalysis
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)


class AuditorAgent:
    def __init__(self, finance_api: FinanceAPI | None = None, indicator_math: IndicatorMath | None = None) -> None:
        self.finance_api = finance_api or FinanceAPI()
        self.indicator_math = indicator_math or IndicatorMath()

    def analyze(self, ticker: str) -> FundamentalAnalysis:
        symbol = ticker.upper()
        logger.info("Auditor started for %s", symbol)
        profile = self.finance_api.fetch_ticker_profile(symbol)
        income_statement = self.finance_api.fetch_income_statement(symbol)
        balance_sheet = self.finance_api.fetch_balance_sheet(symbol)
        result = self.indicator_math.analyze_fundamentals(symbol, profile, income_statement, balance_sheet)
        logger.info("Auditor completed for %s", symbol)
        return result
