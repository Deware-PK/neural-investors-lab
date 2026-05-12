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
        logger.info(
            "Auditor completed for %s: piotroski=%s, peg=%s, altman_z=%s, roe=%s, debt_to_equity=%s, revenue_growth=%s",
            symbol,
            result.piotroski_f_score,
            f"{result.peg_ratio:.2f}" if result.peg_ratio is not None else "N/A",
            f"{result.altman_z_score:.2f}" if result.altman_z_score is not None else "N/A",
            f"{result.snapshot.return_on_equity:.2f}" if result.snapshot.return_on_equity is not None else "N/A",
            f"{result.snapshot.debt_to_equity:.2f}" if result.snapshot.debt_to_equity is not None else "N/A",
            f"{result.snapshot.revenue_growth:.2f}" if result.snapshot.revenue_growth is not None else "N/A",
        )
        return result
