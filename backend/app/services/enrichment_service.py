# Placeholder for Apollo.io / Hunter.io enrichment
# No-op until API keys are configured (Phase 5)

async def apollo_enrich(lead_id: str, name: str, domain: str) -> None:
    from app.config import settings
    if not settings.apollo_api_key:
        return
    # TODO Phase 5: POST https://api.apollo.io/v1/people/match

async def hunter_enrich(lead_id: str, domain: str) -> None:
    from app.config import settings
    if not settings.hunter_api_key:
        return
    # TODO Phase 5: GET https://api.hunter.io/v2/domain-search
