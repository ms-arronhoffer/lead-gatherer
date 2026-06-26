"""Playwright-backed LinkedIn session: login, cookie persistence, detection.

A single, serialized browser context is used per session — LinkedIn punishes
concurrency, so callers should never run two sessions in parallel. The
authenticated storage state (cookies + localStorage) is persisted to disk so
subsequent runs skip the interactive login. Login failures, MFA/checkpoint
challenges, and bot-detection walls raise distinct exceptions so the caller can
fail soft without crashing the worker.

Playwright is imported lazily so the rest of the app (and the test suite) does
not require the browser binaries to be installed.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

from app.config import settings
from app.utils.rate_limiter import RateLimiter

from . import selectors

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.async_api import BrowserContext, Page

logger = logging.getLogger(__name__)

# All LinkedIn navigation is paced through one shared key so a single delay
# applies across the whole session regardless of host.
_RATE_KEY = "linkedin"


class LinkedInError(RuntimeError):
    """Base class for LinkedIn session errors."""


class LinkedInNotConfigured(LinkedInError):
    """Feature disabled or credentials/Playwright missing."""


class LinkedInAuthError(LinkedInError):
    """Login failed (bad credentials or unexpected login wall)."""


class LinkedInChallengeError(LinkedInError):
    """A security checkpoint / MFA challenge blocked automated login."""


class LinkedInDetectedError(LinkedInError):
    """Bot-detection / rate-limit wall encountered mid-session."""


def is_configured() -> bool:
    """True when the feature is enabled and credentials are present."""
    return bool(
        settings.enable_linkedin_enrichment
        and settings.linkedin_username
        and settings.linkedin_password
    )


def _playwright_available() -> bool:
    try:
        import playwright.async_api  # noqa: F401
        return True
    except Exception:  # pragma: no cover - import guard
        return False


async def _first_matching(page: "Page", candidates: list[str]) -> str | None:
    """Return the first selector from ``candidates`` present on the page."""
    for sel in candidates:
        try:
            if await page.query_selector(sel) is not None:
                return sel
        except Exception:  # noqa: BLE001 - defensive against selector errors
            continue
    return None


class LinkedInSession:
    """Async context manager owning a logged-in LinkedIn browser context."""

    def __init__(self) -> None:
        self._rate = RateLimiter(delay=settings.linkedin_action_delay_seconds)
        self._pw = None
        self._browser = None
        self._context: "BrowserContext | None" = None
        self.page: "Page | None" = None

    async def __aenter__(self) -> "LinkedInSession":
        if not is_configured():
            raise LinkedInNotConfigured(
                "LinkedIn enrichment disabled or credentials missing"
            )
        if not _playwright_available():
            raise LinkedInNotConfigured("Playwright is not installed")
        await self._launch()
        await self._ensure_logged_in()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=settings.linkedin_headless)
        storage = settings.linkedin_storage_state_path
        ctx_kwargs: dict = {
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 900},
        }
        if storage and os.path.exists(storage):
            ctx_kwargs["storage_state"] = storage
            logger.info("LinkedIn: reusing persisted storage state")
        self._context = await self._browser.new_context(**ctx_kwargs)
        self._context.set_default_navigation_timeout(settings.linkedin_nav_timeout_ms)
        self.page = await self._context.new_page()

    async def _ensure_logged_in(self) -> None:
        """Verify or perform login; persist storage state on success."""
        assert self.page is not None
        await self._goto(selectors.FEED_URL)
        if await self._is_authenticated():
            logger.info("LinkedIn: existing session is authenticated")
            await self._save_state()
            return
        await self._perform_login()
        await self._save_state()

    async def _perform_login(self) -> None:
        assert self.page is not None
        await self._goto(selectors.LOGIN_URL)
        user_sel = await _first_matching(self.page, selectors.LOGIN_USERNAME)
        pass_sel = await _first_matching(self.page, selectors.LOGIN_PASSWORD)
        submit_sel = await _first_matching(self.page, selectors.LOGIN_SUBMIT)
        if not (user_sel and pass_sel and submit_sel):
            await self._raise_for_challenge()
            raise LinkedInAuthError("Login form not found")

        await self.page.fill(user_sel, settings.linkedin_username)
        await self.page.fill(pass_sel, settings.linkedin_password)
        await self._rate.wait(_RATE_KEY)
        await self.page.click(submit_sel)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=settings.linkedin_nav_timeout_ms)
        except Exception:  # noqa: BLE001 - timeout is non-fatal; we re-check state
            pass

        await self._raise_for_challenge()
        if not await self._is_authenticated():
            raise LinkedInAuthError("Login did not produce an authenticated session")
        logger.info("LinkedIn: login succeeded")

    async def _is_authenticated(self) -> bool:
        assert self.page is not None
        if await _first_matching(self.page, selectors.LOGIN_WALL_MARKERS):
            return False
        return await _first_matching(self.page, selectors.AUTHED_MARKERS) is not None

    async def _raise_for_challenge(self) -> None:
        """Raise if the current page is a checkpoint/MFA/captcha challenge."""
        assert self.page is not None
        url = (self.page.url or "").lower()
        if any(m in url for m in selectors.CHECKPOINT_URL_MARKERS):
            raise LinkedInChallengeError(f"Security checkpoint encountered: {url}")
        if await _first_matching(self.page, selectors.CHECKPOINT_DOM_MARKERS):
            raise LinkedInChallengeError("Security challenge form encountered")

    async def _save_state(self) -> None:
        path = settings.linkedin_storage_state_path
        if not path or self._context is None:
            return
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            await self._context.storage_state(path=path)
        except Exception as exc:  # noqa: BLE001 - persistence is best-effort
            logger.debug("LinkedIn: failed to persist storage state: %s", exc)

    async def _goto(self, url: str) -> None:
        assert self.page is not None
        await self._rate.wait(_RATE_KEY)
        await self.page.goto(url, wait_until="domcontentloaded")

    async def goto(self, url: str) -> "Page":
        """Rate-limited navigation that fails on detection walls."""
        await self._goto(url)
        await self._raise_for_challenge()
        if await _first_matching(self.page, selectors.LOGIN_WALL_MARKERS):
            raise LinkedInDetectedError(f"Hit an auth/detection wall at {url}")
        # Small settle delay so dynamically-rendered content can load.
        await asyncio.sleep(min(2.0, settings.linkedin_action_delay_seconds))
        return self.page  # type: ignore[return-value]

    async def close(self) -> None:
        for closer in (
            lambda: self._context.close() if self._context else None,
            lambda: self._browser.close() if self._browser else None,
            lambda: self._pw.stop() if self._pw else None,
        ):
            try:
                result = closer()
                if result is not None:
                    await result
            except Exception:  # noqa: BLE001 - cleanup must never raise
                pass
        self._context = self._browser = self._pw = self.page = None
