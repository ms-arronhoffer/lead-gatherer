import logging
from typing import AsyncIterator

import httpx

from app.services.discovery.base import DiscoveredBusiness

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_USER_AGENT = "lead-gatherer/0.1 (https://github.com/local)"

# Map free-text category keywords to OSM tag values. Matches are substring-based,
# so "coffee shop" hits the "coffee" entry. Each entry returns (osm_key, [values]).
_CATEGORY_TAG_MAP: dict[str, tuple[str, list[str]]] = {
    "coffee": ("amenity", ["cafe"]),
    "cafe": ("amenity", ["cafe"]),
    "restaurant": ("amenity", ["restaurant", "fast_food"]),
    "bar": ("amenity", ["bar", "pub"]),
    "pub": ("amenity", ["pub", "bar"]),
    "fast food": ("amenity", ["fast_food"]),
    "dentist": ("amenity", ["dentist"]),
    "doctor": ("amenity", ["doctors", "clinic"]),
    "clinic": ("amenity", ["clinic", "doctors"]),
    "pharmacy": ("amenity", ["pharmacy"]),
    "bank": ("amenity", ["bank"]),
    "auto repair": ("shop", ["car_repair"]),
    "car repair": ("shop", ["car_repair"]),
    "hair salon": ("shop", ["hairdresser"]),
    "barber": ("shop", ["hairdresser"]),
    "salon": ("shop", ["hairdresser", "beauty"]),
    "gym": ("leisure", ["fitness_centre"]),
    "fitness": ("leisure", ["fitness_centre"]),
    "hotel": ("tourism", ["hotel", "motel"]),
    "lawyer": ("office", ["lawyer"]),
    "accountant": ("office", ["accountant"]),
    "real estate": ("office", ["estate_agent"]),
    "insurance": ("office", ["insurance"]),
    "veterinarian": ("amenity", ["veterinary"]),
    "vet": ("amenity", ["veterinary"]),
    "property management": ("office", ["estate_agent", "property_management"]),
    "property": ("office", ["estate_agent", "property_management"]),
    "realtor": ("office", ["estate_agent"]),
    "auto": ("shop", ["car_repair", "car"]),
    "mechanic": ("shop", ["car_repair"]),
    "car wash": ("amenity", ["car_wash"]),
    "plumber": ("craft", ["plumber"]),
    "electrician": ("craft", ["electrician"]),
    "contractor": ("craft", ["builder", "carpenter", "electrician", "plumber"]),
    "construction": ("craft", ["builder", "carpenter"]),
    "physical therapy": ("healthcare", ["physiotherapist"]),
    "chiropractor": ("healthcare", ["chiropractor"]),
    "spa": ("leisure", ["spa"]),
}


def _resolve_tag(keyword: str) -> tuple[str, list[str]] | None:
    for cat, mapping in _CATEGORY_TAG_MAP.items():
        if cat in keyword or keyword in cat:
            return mapping
    return None


class OsmSource:
    name = "osm"

    async def search(
        self, category: str, location: str, max_results: int
    ) -> AsyncIterator[DiscoveredBusiness]:
        bbox = await _geocode_bbox(location)
        if not bbox:
            logger.warning("OSM: could not geocode %s", location)
            return

        keyword = category.lower().strip()
        mapped = _resolve_tag(keyword)
        # For multi-word queries, also build an OR-regex of individual words ≥4 chars
        words = [w for w in keyword.split() if len(w) >= 4]
        name_regex = keyword if not words or len(words) == 1 else "|".join(words)

        clauses: list[str] = []
        if mapped:
            key, values = mapped
            regex = "|".join(values)
            clauses.append(f'node["{key}"~"^({regex})$"]["name"]({bbox});')
            clauses.append(f'way["{key}"~"^({regex})$"]["name"]({bbox});')
        # Always also try a literal name match so brand searches like "Starbucks" still work
        clauses.append(f'node["name"~"{name_regex}",i]({bbox});')
        clauses.append(f'way["name"~"{name_regex}",i]({bbox});')
        # For unmapped multi-word queries, also pull commercial POIs and post-filter by name
        if not mapped:
            clauses.append(f'node["office"]["name"]({bbox});')
            clauses.append(f'node["shop"]["name"]({bbox});')
            clauses.append(f'way["office"]["name"]({bbox});')

        query = f"""
        [out:json][timeout:25];
        (
          {chr(10).join(clauses)}
        );
        out tags center {max_results * 3};
        """
        logger.info("OSM Overpass query for '%s' in bbox %s (mapped=%s)", keyword, bbox, mapped)

        async with httpx.AsyncClient(timeout=60, headers={"User-Agent": _USER_AGENT}) as client:
            resp = await client.post(_OVERPASS_URL, data={"data": query})
            if resp.status_code >= 400:
                detail = resp.text[:500]
                raise RuntimeError(f"Overpass API {resp.status_code}: {detail}")
            data = resp.json()

        elements = data.get("elements", [])
        logger.info("OSM returned %d raw elements before filtering", len(elements))

        count = 0
        for el in elements:
            if count >= max_results:
                break
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            if mapped:
                key, values = mapped
                if tags.get(key) not in values and keyword not in name.lower():
                    continue
            else:
                name_lc = name.lower()
                match_words = words or [keyword]
                if not any(w in name_lc for w in match_words) and not _tag_matches(tags, keyword):
                    continue
            elem_id = f"osm:{el.get('type')}/{el.get('id')}"
            yield DiscoveredBusiness(
                name=name,
                source=self.name,
                external_id=elem_id,
                address=_build_address(tags),
                phone=tags.get("phone") or tags.get("contact:phone"),
                website=tags.get("website") or tags.get("contact:website"),
                types=[t for t in (tags.get("amenity"), tags.get("shop"), tags.get("office")) if t],
            )
            count += 1


async def _geocode_bbox(location: str) -> str | None:
    params = {"q": location, "format": "json", "limit": 1}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": _USER_AGENT}) as client:
        resp = await client.get(_NOMINATIM_URL, params=params)
        if resp.status_code >= 400:
            return None
        results = resp.json()
        if not results:
            return None
        bb = results[0].get("boundingbox")
        if not bb or len(bb) != 4:
            return None
        return f"{bb[0]},{bb[2]},{bb[1]},{bb[3]}"


def _tag_matches(tags: dict, keyword: str) -> bool:
    for k in ("amenity", "shop", "office", "craft", "tourism"):
        v = tags.get(k, "")
        if keyword in v.lower():
            return True
    return False


def _build_address(tags: dict) -> str | None:
    parts = [
        tags.get("addr:housenumber"),
        tags.get("addr:street"),
        tags.get("addr:city"),
        tags.get("addr:state"),
        tags.get("addr:postcode"),
    ]
    cleaned = [p for p in parts if p]
    if not cleaned:
        return None
    street = " ".join(p for p in parts[:2] if p)
    rest = ", ".join(p for p in parts[2:] if p)
    return f"{street}, {rest}".strip(", ")
