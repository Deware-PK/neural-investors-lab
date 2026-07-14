import logging

from src.core.config import Settings, get_settings
from src.models.edgar_schema import EdgarBundle
from src.models.fundamental_schema import FundamentalAnalysis
from src.services.finance_api import FinanceAPI
from src.services.indicator_math import IndicatorMath


logger = logging.getLogger(__name__)


class AuditorAgent:
    def __init__(
        self,
        finance_api: FinanceAPI | None = None,
        indicator_math: IndicatorMath | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.finance_api = finance_api or FinanceAPI(settings=self.settings)
        self.indicator_math = indicator_math or IndicatorMath(settings=self.settings)

    def analyze(self, ticker: str, edgar_bundle: EdgarBundle | None = None) -> FundamentalAnalysis:
        symbol = ticker.upper()
        logger.info("Auditor started for %s", symbol)
        profile = self.finance_api.fetch_ticker_profile(symbol)
        income_statement = self.finance_api.fetch_income_statement(symbol)
        balance_sheet = self.finance_api.fetch_balance_sheet(symbol)
        result = self.indicator_math.analyze_fundamentals(symbol, profile, income_statement, balance_sheet)

        if edgar_bundle and edgar_bundle.financials:
            fin = edgar_bundle.financials
            def format_large_number(val: float | None) -> str | None:
                if val is None:
                    return None
                abs_val = abs(val)
                sign = "-" if val < 0 else ""
                if abs_val >= 1_000_000_000:
                    return f"{sign}{abs_val / 1_000_000_000:.1f}B"
                elif abs_val >= 1_000_000:
                    return f"{sign}{abs_val / 1_000_000:.1f}M"
                elif abs_val >= 1_000:
                    return f"{sign}{abs_val / 1_000:.1f}K"
                else:
                    return f"{sign}{abs_val:.1f}"

            rev_fmt = format_large_number(fin.revenue)
            ni_fmt = format_large_number(fin.net_income)
            assets_fmt = format_large_number(fin.total_assets)
            liab_fmt = format_large_number(fin.total_liabilities)

            if rev_fmt:
                result.tags.append(f"edgar_revenue:{rev_fmt}")
            if ni_fmt:
                result.tags.append(f"edgar_net_income:{ni_fmt}")
            if assets_fmt:
                result.tags.append(f"edgar_assets:{assets_fmt}")
            if liab_fmt:
                result.tags.append(f"edgar_liabilities:{liab_fmt}")

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
