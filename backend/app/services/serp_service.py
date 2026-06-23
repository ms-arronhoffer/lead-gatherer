import logging
import re
import time
import uuid

import httpx

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import LeadEmail
from app.utils.email_extractor import _EMAIL_PATTERN, _is_noise

logger = logging.getLogger(__name__)

_BING_URL = "https://api.bing.microsoft.com/v7.0/search"


async def enrich_with_serp(lead_id: str, name: str, city: str) -> None:
    if not settings.bing_search_api_key:
        return

    query = f'"{name}" "{city}" contact email'
    headers = {"Ocp-Apim-Subscription-Key": settings.bing_search_api_key}
    params = {"q": query, "count": 10, "responseFilter": "Webpages"}

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(_BING_URL, headers=headers, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Bing SERP error for %s: %s", name, exc)
            return

    data = resp.json()
    snippets = [
        page.get("snippet", "") + " " + page.get("name", "")
        for page in data.get("webPages", {}).get("value", [])
    ]
    text = " ".join(snippets)
    found = set(_EMAIL_PATTERN.findall(text))

    emails_to_save = [(e, 0.6) for e in found if not _is_noise(e)]
    if not emails_to_save:
        return

    async with AsyncSessionLocal() as session:
        for email, confidence in emails_to_save:
            normalized = email.lower().strip()
            from sqlalchemy import select
            existing = await session.execute(
                select(LeadEmail).where(
                    LeadEmail.lead_id == lead_id,
                    LeadEmail.email_normalized == normalized,
                )
            )
            if existing.scalar_one_or_none():
                continue
            session.add(LeadEmail(
                id=str(uuid.uuid4()),
                lead_id=lead_id,
                email=email,
                email_normalized=normalized,
                source="serp",
                confidence=confidence,
                created_at=int(time.time()),
            ))
        await session.commit()
