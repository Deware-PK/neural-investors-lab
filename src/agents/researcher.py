import logging

from src.agents.json_utils import parse_json_model
from src.core.config import Settings, get_settings
from src.core.i18n import localize_prompt
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
from src.models.edgar_schema import EdgarBundle
from src.models.research_schema import NewsArticle, ResearchFinding
from src.services.deep_research import DeepResearchService
from src.services.finance_api import FinanceAPI


logger = logging.getLogger(__name__)


class ResearcherAgent:
    def __init__(
        self,
        llm_client: OpenRouterClient | None = None,
        deep_research: DeepResearchService | None = None,
        finance_api: FinanceAPI | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm_client = llm_client
        self.deep_research = deep_research or DeepResearchService(settings=self.settings)
        self.finance_api = finance_api or FinanceAPI(settings=self.settings)

    def analyze(self, ticker: str, article_urls: list[str] | None = None, context: str | None = None, edgar_bundle: EdgarBundle | None = None) -> ResearchFinding:
        symbol = ticker.upper()
        logger.info("Researcher started for %s", symbol)
        articles = self.deep_research.extract_articles(article_urls) if article_urls else self.finance_api.fetch_ticker_news(symbol)
        logger.info("Researcher fetched %d articles for %s", len(articles), symbol)
        if articles:
            for i, article in enumerate(articles, 1):
                logger.info("Researcher article %d/%d for %s: %s", i, len(articles), symbol, article.title.encode("ascii", errors="replace").decode("ascii"))
        finding = self._generate_research_finding(symbol, articles, context, edgar_bundle)
        logger.info(
            "Researcher completed for %s: sentiment=%s, score=%.2f, catalysts=%d, concerns=%d",
            symbol,
            finding.sentiment,
            finding.sentiment_score,
            len(finding.catalysts),
            len(finding.concerns),
        )
        return finding

    def investigate_conflict(self, ticker: str, query: str, article_urls: list[str] | None = None, edgar_bundle: EdgarBundle | None = None) -> ResearchFinding:
        symbol = ticker.upper()
        logger.info("Researcher conflict investigation started for %s", symbol)
        articles = self.deep_research.extract_articles(article_urls or []) if article_urls else []
        finding = self._generate_research_finding(symbol, articles, query, edgar_bundle)
        logger.info("Researcher conflict investigation completed for %s", symbol)
        return finding

    def _generate_research_finding(self, ticker: str, articles: list[NewsArticle], context: str | None, edgar_bundle: EdgarBundle | None = None) -> ResearchFinding:
        client = self.llm_client or get_openrouter_client(self.settings)
        article_payload = [article.model_dump(mode="json") for article in articles]

        edgar_prompt_section = ""
        if edgar_bundle:
            filings_str = "None found."
            if edgar_bundle.filings_8k:
                filings_str = "\n".join(
                    f"- {f.filing_date}: {', '.join(f.items) if f.items else 'No items listed'}" + 
                    (f" (Preview: {f.text_preview[:300]}...)" if f.text_preview else "")
                    for f in edgar_bundle.filings_8k
                )

            summary_str = "No recent Form 4 insider transactions found."
            if edgar_bundle.insider_summary:
                s = edgar_bundle.insider_summary
                largest_shares_str = f"{s.largest_tx_shares:,}" if s.largest_tx_shares is not None else "0"
                total_net_shares_str = f"{s.total_net_shares:,}" if s.total_net_shares is not None else "0"
                summary_str = (
                    f"- Buys: {s.buy_count}, Sells: {s.sell_count}\n"
                    f"- Total net change: {total_net_shares_str} shares\n"
                    f"- Largest transaction: {s.largest_tx_name or 'N/A'} on {s.largest_tx_date or 'N/A'} ({largest_shares_str} shares)"
                )

            edgar_prompt_section = (
                f"\n\n### SEC EDGAR DATA\n"
                f"Recent 8-K Filings:\n{filings_str}\n"
                f"Insider Trading (last 10 Form 4):\n{summary_str}"
            )

        lang = self.settings.output_language
        messages = [
            ChatMessage(
                role="system",
                content=localize_prompt(
                    (
                        "You are a Senior Quantitative News Analyst. Your job is to filter out market noise and identify true actionable catalysts from the provided news snippets. "
                        "RULES: "
                        "1. Return ONLY strict JSON matching the ResearchFinding schema. "
                        "2. Evaluate sentiment strictly based on potential short-term price impact. Ignore generic corporate PR. "
                        "3. In 'catalysts', list ONLY concrete events (e.g., M&A, earnings beats, regulatory approvals, institutional flow). "
                        "4. In 'concerns', list explicit risks (e.g., macroeconomic headwinds, legal issues, missed estimates). "
                        "5. Each article object must ONLY contain: title, url, source, published_at, extracted_text. Do NOT add extra fields. "
                        "6. Be highly skeptical. If the news is mundane or lacks clear financial impact, classify the sentiment as 'neutral' with a low sentiment_score."
                    ),
                    lang,
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Ticker: {ticker}\nContext: {context or 'Initial news scan'}\nArticles: {article_payload}{edgar_prompt_section}",
            ),
        ]
        response = client.generate_completion(
            model=self.settings.news_analyst_model,
            messages=messages,
            use_reasoning=self.settings.news_analyst_model_reasoning,
            temperature=0.1,
        )
        try:
            parsed = parse_json_model(response.content, ResearchFinding)
        except Exception:
            logger.warning("Failed to parse ResearchFinding JSON for %s, using safe default", ticker)
            parsed = ResearchFinding(
                ticker=ticker,
                sentiment="neutral",
                sentiment_score=0,
                summary="Research analysis could not be parsed; defaulting to neutral.",
                catalysts=[],
                concerns=[],
                articles=[],
            )
        if parsed.ticker.upper() != ticker:
            parsed = parsed.model_copy(update={"ticker": ticker})
        return parsed
