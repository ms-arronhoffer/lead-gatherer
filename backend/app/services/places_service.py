import logging
from typing import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.types"


async def search_places(category: str, location: str, max_results: int) -> AsyncGenerator[dict, None]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.google_places_api_key,
        "X-Goog-FieldMask": _FIELD_MASK,
    }
    body: dict = {"textQuery": f"{category} in {location}", "maxResultCount": min(20, max_results)}
    collected = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while collected < max_results:
            try:
                resp = await client.post(_PLACES_URL, json=body, headers=headers)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.error("Places API error: %s", exc)
                break

            data = resp.json()
            places = data.get("places", [])
            if not places:
                break

            for place in places:
                if collected >= max_results:
                    break
                yield {
                    "id": place.get("id"),
                    "name": place.get("displayName", {}).get("text", ""),
                    "address": place.get("formattedAddress", ""),
                    "phone": place.get("nationalPhoneNumber"),
                    "website": place.get("websiteUri"),
                    "types": place.get("types", []),
                }
                collected += 1

            next_token = data.get("nextPageToken")
            if not next_token:
                break
            body = {
                "textQuery": f"{category} in {location}",
                "maxResultCount": min(20, max_results - collected),
                "pageToken": next_token,
            }
