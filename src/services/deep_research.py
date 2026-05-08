from datetime import datetime
from typing import Any

from redis import Redis

from src.core.db_redis import get_json_cache, set_json_cache
from src.models.research_schema import NewsArticle


ARTICLE_TTL_SECONDS = 60 * 60 * 24


class ArticleExtractionError(RuntimeError):
    pass


class DeepResearchService:
    def __init__(self, redis_client: Redis | None = None) -> None:
        self.redis_client = redis_client

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
        return [self.extract_article(url) for url in urls]

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
