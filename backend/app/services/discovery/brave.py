import logging
from typing import AsyncIterator
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.discovery.base import DiscoveredBusiness

logger = logging.getLogger(__name__)

_URL = "https://api.search.brave.com/res/v1/web/search"
_DIRECTORY_DOMAINS = {
    "yelp.com", "yellowpages.com", "facebook.com", "linkedin.com",
    "instagram.com", "twitter.com", "x.com", "tripadvisor.com",
    "mapquest.com", "bbb.org", "manta.com", "tiktok.com", "youtube.com",
    "pinterest.com", "reddit.com", "wikipedia.org",
}


class BraveSource:
    name = "brave"

    async def search(
        self, category: str, location: str, max_results: int
    ) -> AsyncIterator[DiscoveredBusiness]:
        if not settings.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY not set")

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": settings.brave_search_api_key,
        }
        seen_domains: set[str] = set()
        offset = 0
        per_page = 20

        async with httpx.AsyncClient(timeout=30) as client:
            while len(seen_domains) < max_results:
                params = {
                    "q": f'{category} in {location}',
                    "count": min(per_page, max_results),
                    "offset": offset,
                    "country": "us",
                    "result_filter": "web",
                }
                resp = await client.get(_URL, params=params, headers=headers)
                if resp.status_code >= 400:
                    detail = resp.text[:500]
                    logger.error("Brave API %s: %s", resp.status_code, detail)
                    raise RuntimeError(f"Brave API {resp.status_code}: {detail}")

                data = resp.json()
                results = data.get("web", {}).get("results", [])
                if not results:
                    break

                for r in results:
                    if len(seen_domains) >= max_results:
                        break
                    url = r.get("url") or ""
                    domain = urlparse(url).netloc.lower().lstrip("www.")
                    if not domain or domain in _DIRECTORY_DOMAINS or domain in seen_domains:
                        continue
                    seen_domains.add(domain)
                    yield DiscoveredBusiness(
                        name=_clean_title(r.get("title", "")) or domain,
                        source=self.name,
                        external_id=f"web:{domain}",
                        website=f"https://{domain}",
                    )

                offset += per_page
                if offset >= 100:
                    break


def _clean_title(title: str) -> str:
    for sep in [" | ", " - ", " — ", " :: "]:
        if sep in title:
            title = title.split(sep)[0]
    return title.strip()
