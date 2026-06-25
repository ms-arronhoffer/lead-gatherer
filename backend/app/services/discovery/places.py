import logging
from typing import AsyncIterator

import httpx

from app.config import settings
from app.services.discovery.base import DiscoveredBusiness

logger = logging.getLogger(__name__)

_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.types"


class PlacesSource:
    name = "google_places"

    async def search(
        self, category: str, location: str, max_results: int
    ) -> AsyncIterator[DiscoveredBusiness]:
        if not settings.google_places_api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY not set")

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_places_api_key,
            "X-Goog-FieldMask": _FIELD_MASK,
        }
        body: dict = {
            "textQuery": f"{category} in {location}",
            "maxResultCount": min(20, max_results),
        }
        collected = 0

        async with httpx.AsyncClient(timeout=30) as client:
            while collected < max_results:
                resp = await client.post(_URL, json=body, headers=headers)
                if resp.status_code >= 400:
                    detail = resp.text[:500]
                    logger.error("Places API %s: %s", resp.status_code, detail)
                    raise RuntimeError(f"Places API {resp.status_code}: {detail}")

                data = resp.json()
                places = data.get("places", [])
                if not places:
                    break

                for place in places:
                    if collected >= max_results:
                        break
                    yield DiscoveredBusiness(
                        name=place.get("displayName", {}).get("text", "Unknown"),
                        source=self.name,
                        external_id=place.get("id"),
                        address=place.get("formattedAddress"),
                        phone=place.get("nationalPhoneNumber"),
                        website=place.get("websiteUri"),
                        types=place.get("types", []),
                    )
                    collected += 1

                next_token = data.get("nextPageToken")
                if not next_token:
                    break
                body = {
                    "textQuery": f"{category} in {location}",
                    "maxResultCount": min(20, max_results - collected),
                    "pageToken": next_token,
                }
