import logging

from src.core.config import Settings, get_settings
from src.models.research_schema import NewsArticle


logger = logging.getLogger(__name__)

CONTENT_MAX_CHARS = 1500


class TavilyResearchService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def search_news(self, ticker: str, company_name: str = "") -> list[NewsArticle]:
        if not self.settings.tavily_api_key:
            logger.warning("TAVILY_API_KEY not configured — skipping Tavily search")
            return []

        try:
            from tavily import TavilyClient
        except ImportError:
            logger.warning("tavily-python not installed — run: uv add tavily-python")
            return []

        query = f"{ticker} {company_name} stock news".strip()
        api_key = self.settings.tavily_api_key.get_secret_value()
        client = TavilyClient(api_key=api_key)

        try:
            response = client.search(
                query=query,
                search_depth=self.settings.tavily_search_depth,
                topic="finance",
                time_range="week",
                max_results=self.settings.tavily_max_results,
                include_raw_content=False,
                include_answer=False,
                include_usage=True,
            )
        except Exception:
            logger.warning("Tavily search failed for %s", ticker, exc_info=True)
            return []

        usage = response.get("usage", {})
        credits_used = usage.get("credits", "?")
        logger.info(
            "Tavily search completed for %s — results: %d, credits used: %s, depth: %s",
            ticker,
            len(response.get("results", [])),
            credits_used,
            self.settings.tavily_search_depth,
        )

        articles: list[NewsArticle] = []
        for r in response.get("results", []):
            content = (r.get("content") or "").strip()
            if not content:
                continue
            url = r.get("url", "")
            source = url.split("/")[2] if url else ""
            articles.append(NewsArticle(
                title=r.get("title") or ticker,
                url=url,
                source=source,
                published_at=None,
                extracted_text=content[:CONTENT_MAX_CHARS],
            ))

        return articles
