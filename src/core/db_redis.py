import json
from typing import Any

from redis import Redis

from src.core.config import Settings, get_settings


JsonCacheValue = dict[str, Any] | list[Any]


def create_redis_client(settings: Settings | None = None) -> Redis:
    resolved_settings = settings or get_settings()
    return Redis.from_url(resolved_settings.redis_url, decode_responses=True)


def create_optional_redis_client(settings: Settings | None = None) -> Redis | None:
    client = create_redis_client(settings)
    try:
        client.ping()
    except Exception:
        return None
    return client


def get_json_cache(client: Redis, key: str) -> JsonCacheValue | None:
    cached = client.get(key)
    if cached is None:
        return None
    return json.loads(cached)


def set_json_cache(client: Redis, key: str, value: JsonCacheValue, ttl_seconds: int) -> None:
    client.setex(key, ttl_seconds, json.dumps(value, default=str))
