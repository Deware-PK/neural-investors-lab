import logging
import time
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from edgar import Company, set_identity
from redis import Redis

from src.core.config import Settings, get_settings
from src.core.db_redis import get_json_cache, set_json_cache
from src.models.edgar_schema import EdgarBundle, EdgarFinancials, FilingEvent, InsiderTrade, InsiderTradeSummary

EDGAR_8K_TTL = 60 * 60 * 6      # 6 hours
EDGAR_FORM4_TTL = 60 * 60 * 6   # 6 hours
EDGAR_FIN_TTL = 60 * 60 * 24    # 24 hours
EDGAR_BUNDLE_TTL = 60 * 60 * 6  # 6 hours

logger = logging.getLogger(__name__)
_EDGAR_FETCH_LOCK = Lock()


class EdgarAPI:
    def __init__(self, redis_client: Redis | None = None, settings: Settings | None = None) -> None:
        self.redis_client = redis_client
        self.settings = settings or get_settings()
        try:
            set_identity(self.settings.edgar_identity)
        except Exception:
            logger.exception("Failed to set EDGAR identity to %s", self.settings.edgar_identity)

    def fetch_edgar_bundle(self, ticker: str) -> EdgarBundle:
        symbol = ticker.upper()
        cache_key = f"edgar:bundle:{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return EdgarBundle.model_validate(cached)

        # Let's perform individual calls or load company info once
        company_name = None
        cik = None
        try:
            self._throttle_external_fetch(f"company:{symbol}")
            company = Company(symbol)
            company_name = str(company.name) if company.name is not None else None
            cik = str(company.cik) if company.cik is not None else None
        except Exception:
            logger.warning("Failed to fetch Company info for %s", symbol)

        filings_8k = self.fetch_8k_filings(symbol)
        insider_trades, insider_summary = self.fetch_insider_trades(symbol)
        financials = self.fetch_edgar_financials(symbol)

        bundle = EdgarBundle(
            ticker=symbol,
            company_name=company_name,
            cik=cik,
            filings_8k=filings_8k,
            insider_trades=insider_trades,
            insider_summary=insider_summary,
            financials=financials,
            fetched_at=datetime.now(UTC),
        )

        self._set_cached(cache_key, bundle.model_dump(mode="json"), EDGAR_BUNDLE_TTL)
        return bundle

    def fetch_8k_filings(self, ticker: str, count: int = 5) -> list[FilingEvent]:
        symbol = ticker.upper()
        cache_key = f"edgar:8k:{symbol}:{count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return [FilingEvent.model_validate(item) for item in cached]

        events: list[FilingEvent] = []
        try:
            self._throttle_external_fetch(f"8k:{symbol}")
            company = Company(symbol)
            filings_8k = company.get_filings(form="8-K")
            if filings_8k is not None:
                # head() gets top N filings
                filings_head = filings_8k.head(count)
                for filing in filings_head:
                    items_list = []
                    try:
                        report = filing.obj()
                        if report is not None and hasattr(report, "items"):
                            items_list = [str(item) for item in report.items if item]
                    except Exception:
                        logger.warning("Failed to retrieve filing object for 8-K %s", filing.accession_number)

                    # Extract text preview using fallback logic
                    text_preview = ""
                    try:
                        attachments = list(filing.attachments) if hasattr(filing, "attachments") else []
                        # 1. Try filing document text
                        if not text_preview and hasattr(filing, "document") and filing.document is not None:
                            try:
                                if hasattr(filing.document, "text"):
                                    text_preview = filing.document.text()[:900]
                            except Exception:
                                pass
                        # 2. Try primary attachment text
                        if not text_preview and attachments:
                            try:
                                primary = attachments[0]
                                if hasattr(primary, "text"):
                                    text_preview = primary.text()[:900]
                            except Exception:
                                pass
                        # 3. Try any attachment with text
                        if not text_preview:
                            for att in attachments:
                                try:
                                    if hasattr(att, "text"):
                                        text_preview = att.text()[:900]
                                        if text_preview:
                                            break
                                except Exception:
                                    continue
                    except Exception:
                        pass

                    # filing.filing_date can be a string or date, ensure it's mapped correctly
                    f_date = filing.filing_date
                    if isinstance(f_date, str):
                        try:
                            f_date = date.fromisoformat(f_date)
                        except ValueError:
                            f_date = date.today()

                    events.append(FilingEvent(
                        filing_date=f_date,
                        form_type="8-K",
                        accession_number=filing.accession_number,
                        items=items_list,
                        text_preview=text_preview if text_preview else None
                    ))
        except Exception:
            logger.warning("Failed to fetch 8-K filings for %s", symbol)

        self._set_cached(cache_key, [e.model_dump(mode="json") for e in events], EDGAR_8K_TTL)
        return events

    def fetch_insider_trades(self, ticker: str, count: int = 10) -> tuple[list[InsiderTrade], InsiderTradeSummary | None]:
        symbol = ticker.upper()
        cache_key = f"edgar:insider:{symbol}:{count}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            trades = [InsiderTrade.model_validate(item) for item in cached.get("trades", [])]
            summary = InsiderTradeSummary.model_validate(cached["summary"]) if cached.get("summary") else None
            return trades, summary

        trades: list[InsiderTrade] = []
        try:
            self._throttle_external_fetch(f"form4:{symbol}")
            company = Company(symbol)
            filings_4 = company.get_filings(form="4")
            if filings_4 is not None:
                filings_head = filings_4.head(count)
                for filing in filings_head:
                    try:
                        # filing.obj().get_ownership_summary()
                        report = filing.obj()
                        if report is not None:
                            summary_obj = report.get_ownership_summary()
                            if summary_obj is not None:
                                f_date = filing.filing_date
                                if isinstance(f_date, str):
                                    try:
                                        f_date = date.fromisoformat(f_date)
                                    except ValueError:
                                        f_date = date.today()

                                # net_change can be positive, negative, or 0/None. Ensure we default to 0 if None
                                net_change = getattr(summary_obj, "net_change", 0)
                                if net_change is None:
                                    net_change = 0

                                trades.append(InsiderTrade(
                                    date=f_date,
                                    insider_name=getattr(summary_obj, "insider_name", "Unknown"),
                                    position=getattr(summary_obj, "position", None),
                                    net_shares=int(net_change),
                                ))
                    except Exception:
                        logger.warning("Failed to retrieve Form 4 ownership summary for filing in %s", symbol)
        except Exception:
            logger.warning("Failed to fetch Form 4 filings for %s", symbol)

        # Compute summary
        summary = None
        if trades:
            buy_count = 0
            sell_count = 0
            zero_count = 0
            total_net = 0
            largest_tx_name = None
            largest_tx_date = None
            largest_tx_shares = 0

            for t in trades:
                total_net += t.net_shares
                if t.net_shares > 0:
                    buy_count += 1
                elif t.net_shares < 0:
                    sell_count += 1
                else:
                    zero_count += 1

                abs_shares = abs(t.net_shares)
                if abs_shares > largest_tx_shares:
                    largest_tx_shares = abs_shares
                    largest_tx_name = t.insider_name
                    largest_tx_date = t.date

            summary = InsiderTradeSummary(
                total_filings=len(trades),
                buy_count=buy_count,
                sell_count=sell_count,
                zero_count=zero_count,
                total_net_shares=total_net,
                largest_tx_name=largest_tx_name,
                largest_tx_date=largest_tx_date,
                largest_tx_shares=largest_tx_shares if largest_tx_shares > 0 else None,
            )

        cached_val = {
            "trades": [t.model_dump(mode="json") for t in trades],
            "summary": summary.model_dump(mode="json") if summary else None
        }
        self._set_cached(cache_key, cached_val, EDGAR_FORM4_TTL)
        return trades, summary

    def fetch_edgar_financials(self, ticker: str) -> EdgarFinancials:
        symbol = ticker.upper()
        cache_key = f"edgar:financials:{symbol}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return EdgarFinancials.model_validate(cached)

        financials = EdgarFinancials()
        try:
            self._throttle_external_fetch(f"financials:{symbol}")
            company = Company(symbol)
            fin = company.get_financials()
            if fin is not None:
                # get_revenue(), get_net_income(), get_total_assets(), get_total_liabilities()
                try:
                    revenue = fin.get_revenue()
                    if revenue is not None:
                        financials.revenue = float(revenue)
                except Exception:
                    pass

                try:
                    net_income = fin.get_net_income()
                    if net_income is not None:
                        financials.net_income = float(net_income)
                except Exception:
                    pass

                try:
                    total_assets = fin.get_total_assets()
                    if total_assets is not None:
                        financials.total_assets = float(total_assets)
                except Exception:
                    pass

                try:
                    total_liabilities = fin.get_total_liabilities()
                    if total_liabilities is not None:
                        financials.total_liabilities = float(total_liabilities)
                except Exception:
                    pass
        except Exception:
            logger.warning("Failed to fetch annual financials from EDGAR for %s", symbol)

        self._set_cached(cache_key, financials.model_dump(mode="json"), EDGAR_FIN_TTL)
        return financials

    def _get_cached(self, key: str) -> Any | None:
        if self.redis_client is None:
            return None
        try:
            return get_json_cache(self.redis_client, key)
        except Exception:
            return None

    def _set_cached(self, key: str, value: dict[str, Any] | list[Any], ttl_seconds: int) -> None:
        if self.redis_client is None:
            return
        try:
            set_json_cache(self.redis_client, key, value, ttl_seconds)
        except Exception:
            return

    def _throttle_external_fetch(self, label: str) -> None:
        delay_seconds = self.settings.finance_fetch_delay_seconds
        if delay_seconds <= 0:
            return
        with _EDGAR_FETCH_LOCK:
            logger.debug("Throttling EDGAR fetch %s for %.2fs", label, delay_seconds)
            time.sleep(delay_seconds)
