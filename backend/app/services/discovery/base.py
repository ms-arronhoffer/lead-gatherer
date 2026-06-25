from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


@dataclass
class DiscoveredBusiness:
    name: str
    source: str
    external_id: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    types: list[str] = field(default_factory=list)
    llm_summary: str | None = None
    llm_fit_score: int | None = None


class DiscoverySource(Protocol):
    name: str

    def search(
        self, category: str, location: str, max_results: int
    ) -> AsyncIterator[DiscoveredBusiness]: ...
