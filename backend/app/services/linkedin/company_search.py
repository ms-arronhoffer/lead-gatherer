"""Navigate LinkedIn search/company/profile/activity pages and return raw data.

Everything here is best-effort and defensive: LinkedIn markup shifts constantly,
so each extraction tolerates missing elements and never raises on a single bad
card. The scraped, un-normalized data is handed to :mod:`decision_makers` and
:mod:`post_signals` (which use the LLM) for cleanup and classification.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.config import settings

from . import selectors
from .browser_session import LinkedInSession

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import ElementHandle, Page

logger = logging.getLogger(__name__)


@dataclass
class RawProfile:
    name: str
    profile_url: str
    headline: str = ""
    location: str = ""
    about: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "profile_url": self.profile_url,
            "headline": self.headline,
            "location": self.location,
            "about": self.about,
        }


@dataclass
class RawPost:
    text: str
    url: str = ""
    author: str = ""


@dataclass
class CompanyScrape:
    query: str
    company_url: str = ""
    profiles: list[RawProfile] = field(default_factory=list)
    posts: list[RawPost] = field(default_factory=list)


async def _text_first(node: "ElementHandle | Page", candidates: list[str]) -> str:
    for sel in candidates:
        try:
            el = await node.query_selector(sel)
            if el is None:
                continue
            text = (await el.inner_text()).strip()
            if text:
                return text
        except Exception:  # noqa: BLE001 - defensive against selector errors
            continue
    return ""


async def _attr_first(node: "ElementHandle | Page", candidates: list[str], attr: str) -> str:
    for sel in candidates:
        try:
            el = await node.query_selector(sel)
            if el is None:
                continue
            val = await el.get_attribute(attr)
            if val:
                return val
        except Exception:  # noqa: BLE001
            continue
    return ""


def _clean_profile_url(url: str) -> str:
    """Strip query/fragment from a /in/ profile URL for stable dedupe."""
    if not url:
        return ""
    base = url.split("?")[0].split("#")[0]
    if base.startswith("/"):
        base = selectors.BASE_URL + base
    return base.rstrip("/")


async def resolve_company_url(session: LinkedInSession, query: str) -> str:
    """Return the best-matching LinkedIn company page URL, or empty string."""
    try:
        page = await session.goto(selectors.company_search_url(query))
    except Exception as exc:  # noqa: BLE001 - fail soft
        logger.warning("LinkedIn company search failed for %s: %s", query, exc)
        return ""
    href = await _attr_first(page, selectors.COMPANY_RESULT_LINK, "href")
    return _clean_profile_url(href)


async def collect_people(
    session: LinkedInSession, query: str, max_profiles: int
) -> list[RawProfile]:
    """Collect people from a company-scoped people search."""
    try:
        page = await session.goto(selectors.people_search_url(query))
    except Exception as exc:  # noqa: BLE001 - fail soft
        logger.warning("LinkedIn people search failed for %s: %s", query, exc)
        return []

    items: list["ElementHandle"] = []
    for sel in selectors.SEARCH_RESULT_ITEM:
        try:
            found = await page.query_selector_all(sel)
        except Exception:  # noqa: BLE001
            found = []
        if found:
            items = found
            break

    profiles: list[RawProfile] = []
    seen: set[str] = set()
    for item in items:
        if len(profiles) >= max_profiles:
            break
        href = _clean_profile_url(
            await _attr_first(item, selectors.RESULT_PROFILE_LINK, "href")
        )
        if not href or "/in/" not in href or href in seen:
            continue
        seen.add(href)
        name = await _text_first(item, selectors.RESULT_NAME)
        headline = await _text_first(item, selectors.RESULT_HEADLINE)
        location = await _text_first(item, selectors.RESULT_LOCATION)
        if not name:
            continue
        profiles.append(
            RawProfile(name=name, profile_url=href, headline=headline, location=location)
        )
    return profiles


async def hydrate_profile(session: LinkedInSession, profile: RawProfile) -> RawProfile:
    """Visit a profile to fill in headline/location/about when search was sparse."""
    try:
        page = await session.goto(profile.profile_url)
    except Exception as exc:  # noqa: BLE001 - fail soft
        logger.debug("LinkedIn profile fetch failed for %s: %s", profile.profile_url, exc)
        return profile
    profile.name = (await _text_first(page, selectors.PROFILE_NAME)) or profile.name
    profile.headline = (await _text_first(page, selectors.PROFILE_HEADLINE)) or profile.headline
    profile.location = (await _text_first(page, selectors.PROFILE_LOCATION)) or profile.location
    profile.about = (await _text_first(page, selectors.PROFILE_ABOUT)) or profile.about
    return profile


async def collect_posts_from(session: LinkedInSession, activity_url: str, author: str, limit: int) -> list[RawPost]:
    """Collect recent post texts from an activity/posts page."""
    if limit <= 0:
        return []
    try:
        page = await session.goto(activity_url)
    except Exception as exc:  # noqa: BLE001 - fail soft
        logger.debug("LinkedIn posts fetch failed for %s: %s", activity_url, exc)
        return []

    items: list["ElementHandle"] = []
    for sel in selectors.POST_ITEM:
        try:
            found = await page.query_selector_all(sel)
        except Exception:  # noqa: BLE001
            found = []
        if found:
            items = found
            break

    posts: list[RawPost] = []
    for item in items:
        if len(posts) >= limit:
            break
        text = await _text_first(item, selectors.POST_TEXT)
        if text:
            posts.append(RawPost(text=text, url=activity_url, author=author))
    return posts


async def scrape_company(query: str) -> CompanyScrape:
    """High-level scrape: open a session, gather people + recent posts.

    Returns a :class:`CompanyScrape`. Best-effort — partial failures degrade to
    fewer profiles/posts rather than raising.
    """
    result = CompanyScrape(query=query)
    async with LinkedInSession() as session:
        result.company_url = await resolve_company_url(session, query)

        scanned = await collect_people(session, query, settings.linkedin_max_profiles_scanned)
        # Enrich the most-promising handful with full profile detail.
        for profile in scanned:
            await hydrate_profile(session, profile)
        result.profiles = scanned

        # Company-level posts first; they're the strongest buying-signal source.
        if result.company_url:
            company_posts = await collect_posts_from(
                session,
                result.company_url.rstrip("/") + selectors.COMPANY_POSTS_SUFFIX,
                author=query,
                limit=settings.linkedin_max_posts,
            )
            result.posts.extend(company_posts)
    return result
