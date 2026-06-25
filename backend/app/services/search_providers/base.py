"""Search provider protocol. Implementations turn a free-text query into a
list of result URLs filtered to non-directory hosts."""
from __future__ import annotations

from typing import Protocol
from urllib.parse import urlparse

DIRECTORY_DOMAINS = {
    "yelp.com", "yellowpages.com", "facebook.com", "linkedin.com",
    "instagram.com", "twitter.com", "x.com", "tripadvisor.com",
    "mapquest.com", "bbb.org", "manta.com", "tiktok.com", "youtube.com",
    "pinterest.com", "reddit.com", "wikipedia.org",
}


def is_directory(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return not host or host in DIRECTORY_DOMAINS


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, count: int) -> list[str]:
        ...
