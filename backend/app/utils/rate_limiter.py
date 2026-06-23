import asyncio
import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, delay: float | None = None):
        self._last: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._delay = delay

    async def wait(self, domain: str) -> None:
        from app.config import settings
        delay = self._delay if self._delay is not None else settings.request_delay_seconds
        async with self._locks[domain]:
            now = time.monotonic()
            elapsed = now - self._last[domain]
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)
            self._last[domain] = time.monotonic()
