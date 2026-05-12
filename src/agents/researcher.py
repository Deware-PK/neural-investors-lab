import logging

from src.agents.json_utils import extract_json_object, normalize_research_finding
from src.core.config import Settings, get_settings
from src.core.llm_client import ChatMessage, OpenRouterClient, get_openrouter_client
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

    def analyze(self, ticker: str, article_urls: list[str] | None = None, context: str | None = None) -> ResearchFinding:
        symbol = ticker.upper()
        logger.info("Researcher started for %s", symbol)
        articles = self.deep_research.extract_articles(article_urls) if article_urls else self.finance_api.fetch_ticker_news(symbol)
        logger.info("Researcher fetched %d articles for %s", len(articles), symbol)
        if articles:
            for i, article in enumerate(articles, 1):
                logger.info("Researcher article %d/%d for %s: %s", i, len(articles), symbol, article.title)
        finding = self._generate_research_finding(symbol, articles, context)
        logger.info(
            "Researcher completed for %s: sentiment=%s, score=%.2f, catalysts=%d, concerns=%d",
            symbol,
            finding.sentiment,
            finding.sentiment_score,
            len(finding.catalysts),
            len(finding.concerns),
        )
        return finding

    def investigate_conflict(self, ticker: str, query: str, article_urls: list[str] | None = None) -> ResearchFinding:
        symbol = ticker.upper()
        logger.info("Researcher conflict investigation started for %s", symbol)
        articles = self.deep_research.extract_articles(article_urls or []) if article_urls else []
        finding = self._generate_research_finding(symbol, articles, query)
        logger.info("Researcher conflict investigation completed for %s", symbol)
        return finding

    def _generate_research_finding(self, ticker: str, articles: list[NewsArticle], context: str | None) -> ResearchFinding:
        client = self.llm_client or get_openrouter_client(self.settings)
        article_payload = [article.model_dump(mode="json") for article in articles]
        messages = [
            ChatMessage(
                role="system",
                content=(
                    "You are a Senior Financial News Analyst. Analyze the provided news headlines and snippets. "
                    "Evaluate overall sentiment and identify potential market catalysts or risks. "
                    "If only headlines are provided, perform a surface-level sentiment scan. "
                    "Return only strict JSON matching: ticker, sentiment, sentiment_score, summary, catalysts, concerns, articles. "
                    "Use bullish, bearish, neutral, or mixed for sentiment. Do not calculate financial metrics. "
                    "Each article object must ONLY contain: title, url, source, published_at, extracted_text. "
                    "Do NOT add sentiment, sentiment_contribution, or any other extra fields to articles."
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Ticker: {ticker}\nContext: {context or 'Initial news scan'}\nArticles: {article_payload}",
            ),
        ]
        response = client.generate_completion(
            model=self.settings.news_analyst_model,
            messages=messages,
            use_reasoning=self.settings.news_analyst_model_reasoning,
            temperature=0.1,
        )
        payload = extract_json_object(response.content)
        payload = normalize_research_finding(payload)
        parsed = ResearchFinding.model_validate(payload)
        if parsed.ticker.upper() != ticker:
            parsed = parsed.model_copy(update={"ticker": ticker})
        return parsed
