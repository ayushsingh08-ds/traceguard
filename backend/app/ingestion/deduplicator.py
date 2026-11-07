import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass(frozen=True)
class DeduplicationResult:
    is_duplicate: bool
    occurrence_count: int
    fingerprint: str


class InMemorySlidingWindowCache:
    def __init__(self, window_seconds: int = 300) -> None:
        self.window_seconds = window_seconds
        # In-memory store: fingerprint -> list of monotonic timestamps
        self._store: Dict[str, List[float]] = {}

    def process(self, fingerprint: str) -> DeduplicationResult:
        now = time.monotonic()
        cutoff = now - self.window_seconds

        timestamps = self._store.get(fingerprint, [])
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]

        is_duplicate = len(valid_timestamps) > 0
        valid_timestamps.append(now)
        self._store[fingerprint] = valid_timestamps

        return DeduplicationResult(
            is_duplicate=is_duplicate,
            occurrence_count=len(valid_timestamps),
            fingerprint=fingerprint,
        )


class AlertDeduplicator:
    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        window_seconds: int = settings.DEDUPLICATION_WINDOW_SECONDS,
    ) -> None:
        self.redis_client = redis_client
        self.window_seconds = window_seconds
        self._memory_fallback = InMemorySlidingWindowCache(window_seconds=window_seconds)

    async def evaluate_and_record(self, fingerprint: str) -> DeduplicationResult:
        if self.redis_client is None:
            return self._memory_fallback.process(fingerprint)

        now = time.time()
        window_start = now - self.window_seconds
        key = f"tg:dedup:{fingerprint}"
        member = f"{now}:{uuid.uuid4().hex[:8]}"

        try:
            # Atomic multi-command pipeline guarantees zero race conditions between
            # reading the window cardinality and appending the new occurrence.
            async with self.redis_client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, "-inf", window_start)
                pipe.zcard(key)
                pipe.zadd(key, {member: now})
                # Key TTL is set to window + buffer so idle keys expire automatically without active sweeps
                pipe.expire(key, self.window_seconds + 60)
                results = await pipe.execute()

            existing_count = results[1]
            is_duplicate = existing_count > 0
            occurrence_count = existing_count + 1

            return DeduplicationResult(
                is_duplicate=is_duplicate,
                occurrence_count=occurrence_count,
                fingerprint=fingerprint,
            )
        except (RedisError, ConnectionError, OSError):
            # Degrade gracefully to in-memory sliding window when Redis cluster is unreachable
            return self._memory_fallback.process(fingerprint)
