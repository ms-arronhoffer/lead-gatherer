from app.services.discovery.base import DiscoverySource
from app.services.discovery.brave import BraveSource
from app.services.discovery.osm import OsmSource
from app.services.discovery.places import PlacesSource
from app.services.discovery.url_harvester import UrlHarvesterSource

_SOURCES: dict[str, type[DiscoverySource]] = {
    "google_places": PlacesSource,
    "brave": BraveSource,
    "osm": OsmSource,
    "url_harvester": UrlHarvesterSource,
}

AVAILABLE_SOURCES = list(_SOURCES.keys())


def get_source(name: str) -> DiscoverySource:
    cls = _SOURCES.get(name)
    if not cls:
        raise ValueError(f"Unknown discovery source: {name}. Available: {AVAILABLE_SOURCES}")
    return cls()
