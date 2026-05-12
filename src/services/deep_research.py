import logging
import time
from datetime import datetime
from threading import Lock
from typing import Any

from redis import Redis

from src.core.config import Settings, get_settings
from src.core.db_redis import get_json_cache, set_json_cache
from src.models.research_schema import NewsArticle


ARTICLE_TTL_SECONDS = 60 * 60 * 24
logger = logging.getLogger(__name__)
_RESEARCH_FETCH_LOCK = Lock()


class ArticleExtractionError(RuntimeError):
    pass


class DeepResearchService:
    def __init__(self, redis_client: Redis | None = None, settings: Settings | None = None) -> None:
        self.redis_client = redis_client
        self.settings = settings or get_settings()

    def extract_article(self, url: str, source: str | None = None) -> NewsArticle:
        cache_key = f"research:article:{url}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return NewsArticle.model_validate(cached)

        try:
            from newspaper import Article
        except ImportError as error:
            msg = "newspaper3k is required for article extraction"
            raise ArticleExtractionError(msg) from error

        article = Article(url)
        try:
            self._throttle_external_fetch(url)
            article.download()
            article.parse()
        except Exception as error:
            msg = f"Failed to extract article text from {url}"
            raise ArticleExtractionError(msg) from error

        published_at = article.publish_date
        if published_at is not None and not isinstance(published_at, datetime):
            published_at = None

        extracted = NewsArticle(
            title=article.title or url,
            url=url,
            source=source or article.source_url,
            published_at=published_at,
            extracted_text=article.text or None,
        )
        self._set_cached(cache_key, extracted.model_dump(mode="json"), ARTICLE_TTL_SECONDS)
        return extracted

    def extract_articles(self, urls: list[str]) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for url in urls:
            try:
                articles.append(self.extract_article(url))
            except ArticleExtractionError:
                logger.warning("Failed to extract article from %s - skipping", url)
        return articles

    def _get_cached(self, key: str) -> Any | None:
        if self.redis_client is None:
            return None
        try:
            return get_json_cache(self.redis_client, key)
        except Exception:
            return None

    def _set_cached(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        if self.redis_client is None:
            return
        try:
            set_json_cache(self.redis_client, key, value, ttl_seconds)
        except Exception:
            return

    def _throttle_external_fetch(self, label: str) -> None:
        delay_seconds = self.settings.research_fetch_delay_seconds
        if delay_seconds <= 0:
            return
        with _RESEARCH_FETCH_LOCK:
            logger.debug("Throttling research fetch %s for %.2fs", label, delay_seconds)
            time.sleep(delay_seconds)
