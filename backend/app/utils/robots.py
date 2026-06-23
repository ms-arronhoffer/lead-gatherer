import asyncio
import logging
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

_cache: dict[str, RobotFileParser] = {}
_USER_AGENT = "LeadGatherer"


async def is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    if robots_url not in _cache:
        rp = RobotFileParser(robots_url)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(robots_url)
                rp.parse(resp.text.splitlines())
        except Exception:
            _cache[robots_url] = None  # type: ignore
            return True  # if robots.txt is unreachable, assume allowed
        _cache[robots_url] = rp

    rp = _cache.get(robots_url)
    if rp is None:
        return True
    return rp.can_fetch(_USER_AGENT, url)
