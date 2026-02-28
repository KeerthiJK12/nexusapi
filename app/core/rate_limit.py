from __future__ import annotations

from datetime import UTC, datetime

from redis.asyncio import Redis

from app.core.config import get_settings


class RateLimitExceededError(Exception):
    def __init__(self, retry_after: int):
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


async def enforce_org_rate_limit(redis: Redis, organisation_id: str) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    window = now.strftime("%Y%m%d%H%M")
    key = f"rate:{organisation_id}:{window}"

    try:
        count = await redis.incr(key)
        ttl = await redis.ttl(key)
        if count == 1:
            await redis.expire(key, 60)
            ttl = 60
        if count > settings.rate_limit_per_minute:
            retry_after = ttl if isinstance(ttl, int) and ttl > 0 else 60
            raise RateLimitExceededError(retry_after=retry_after)
    except RateLimitExceededError:
        raise
    except Exception:
        # Fail open on Redis outage to protect API availability.
        return
