"""Centralized LinkedIn URLs and DOM selectors.

LinkedIn rewrites its markup frequently, so every selector the scraper depends on
lives here. When the scraper stops finding elements, this is the only file that
should need updating. Each logical element exposes a *list* of candidate
selectors tried in order, so a single layout change degrades gracefully instead
of breaking the whole flow.
"""
from __future__ import annotations

BASE_URL = "https://www.linkedin.com"
LOGIN_URL = f"{BASE_URL}/login"
FEED_URL = f"{BASE_URL}/feed/"


def people_search_url(query: str) -> str:
    """Search URL scoped to people for a free-text query."""
    from urllib.parse import quote

    return f"{BASE_URL}/search/results/people/?keywords={quote(query)}"


def company_search_url(query: str) -> str:
    """Search URL scoped to companies for a free-text query."""
    from urllib.parse import quote

    return f"{BASE_URL}/search/results/companies/?keywords={quote(query)}"


# --- Login flow ---
LOGIN_USERNAME = ["#username", "input[name='session_key']"]
LOGIN_PASSWORD = ["#password", "input[name='session_password']"]
LOGIN_SUBMIT = ["button[type='submit']", "button[data-litms-control-urn='login-submit']"]

# Markers that indicate we are NOT logged in / hit a wall.
LOGIN_WALL_MARKERS = [
    "input[name='session_key']",
    "form.login__form",
    "a[href*='/authwall']",
]
# Markers for a security checkpoint / verification challenge (MFA, captcha).
CHECKPOINT_URL_MARKERS = ["/checkpoint/", "/challenge/", "/uas/"]
CHECKPOINT_DOM_MARKERS = [
    "input[name='pin']",
    "#captcha-internal",
    "div.challenge",
    "h1.challenge__heading",
]
# Element proving an authenticated session (global nav present).
AUTHED_MARKERS = ["#global-nav", "div.feed-identity-module", "header.global-nav"]

# --- People search result cards ---
SEARCH_RESULT_CONTAINER = [
    "div.search-results-container",
    "ul.reusable-search__entity-result-list",
]
SEARCH_RESULT_ITEM = [
    "li.reusable-search__result-container",
    "div.entity-result",
    "li.search-results__result-item",
]
RESULT_PROFILE_LINK = ["a.app-aware-link[href*='/in/']", "a[href*='/in/']"]
RESULT_NAME = ["span[aria-hidden='true']", "span.entity-result__title-text"]
RESULT_HEADLINE = ["div.entity-result__primary-subtitle"]
RESULT_LOCATION = ["div.entity-result__secondary-subtitle"]

# --- Company search result cards ---
COMPANY_RESULT_LINK = ["a.app-aware-link[href*='/company/']", "a[href*='/company/']"]

# --- Profile page ---
PROFILE_NAME = ["h1.text-heading-xlarge", "h1"]
PROFILE_HEADLINE = ["div.text-body-medium.break-words", "div.text-body-medium"]
PROFILE_LOCATION = ["span.text-body-small.inline.t-black--light.break-words"]
PROFILE_ABOUT = ["div#about ~ div .inline-show-more-text", "section.pv-about-section"]

# --- Activity / posts page ---
PROFILE_POSTS_SUFFIX = "/recent-activity/all/"
COMPANY_POSTS_SUFFIX = "/posts/"
POST_ITEM = [
    "div.feed-shared-update-v2",
    "div.occludable-update",
    "li.profile-creator-shared-feed-update__container",
]
POST_TEXT = [
    "div.feed-shared-update-v2__description span.break-words",
    "div.update-components-text span.break-words",
    "span.break-words",
]
