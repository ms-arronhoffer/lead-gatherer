"""Email quality validation: syntax, MX, role-based, disposable."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import dns.asyncresolver
import dns.exception

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

_ROLE_LOCAL_PARTS = {
    "info", "sales", "admin", "administrator", "support", "help", "contact",
    "hello", "office", "team", "noreply", "no-reply", "donotreply",
    "marketing", "press", "media", "billing", "accounts", "accounting",
    "hr", "jobs", "careers", "webmaster", "postmaster", "abuse",
    "feedback", "service", "inquiry", "enquiries", "general",
}

# Small bundled list — most common throwaway providers. Real-world deployments
# would mirror a curated repo like disposable-email-domains/disposable-email-domains.
_DISPOSABLE_DOMAINS = {
    "10minutemail.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "mailinator.com", "tempmail.com", "throwawaymail.com", "yopmail.com",
    "trashmail.com", "fakeinbox.com", "getnada.com", "maildrop.cc",
    "sharklasers.com", "spam4.me", "tempinbox.com", "dispostable.com",
    "tempr.email", "mintemail.com", "moakt.com", "throwam.com",
    "emailondeck.com", "mailnesia.com", "mvrht.com", "tempemail.com",
    "emailtemporanea.com", "discard.email", "burnermail.io", "mailcatch.com",
    "anonbox.net", "mytemp.email", "armyspy.com", "cuvox.de",
    "dayrep.com", "einrot.com", "fleckens.hu", "gustr.com", "jourrapide.com",
    "rhyta.com", "superrito.com", "teleworm.us",
}

# (mx_valid, expires_at_unix)
_MxCacheEntry = tuple[bool, float]
_MX_CACHE: dict[str, _MxCacheEntry] = {}
_MX_TTL_SECONDS = 60 * 60 * 24  # 24h


@dataclass
class EmailValidation:
    valid_syntax: bool
    mx_valid: bool | None
    role_based: bool
    disposable: bool
    validated_at: int


def _local_and_domain(email: str) -> tuple[str, str] | None:
    if "@" not in email:
        return None
    local, _, domain = email.rpartition("@")
    if not local or not domain:
        return None
    return local.lower(), domain.lower()


def _syntax_ok(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _is_role_based(local: str) -> bool:
    base = local.split("+", 1)[0]
    return base in _ROLE_LOCAL_PARTS


def _is_disposable(domain: str) -> bool:
    return domain in _DISPOSABLE_DOMAINS


async def _has_mx(domain: str) -> bool:
    now = time.time()
    cached = _MX_CACHE.get(domain)
    if cached and cached[1] > now:
        return cached[0]
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 5.0
    resolver.timeout = 5.0
    try:
        answers = await resolver.resolve(domain, "MX")
        valid = len(answers) > 0
    except (dns.exception.DNSException, OSError) as exc:
        logger.debug("MX lookup failed for %s: %s", domain, exc)
        valid = False
    _MX_CACHE[domain] = (valid, now + _MX_TTL_SECONDS)
    return valid


async def validate_email(email: str) -> EmailValidation:
    parts = _local_and_domain(email)
    if not parts or not _syntax_ok(email):
        return EmailValidation(
            valid_syntax=False,
            mx_valid=None,
            role_based=False,
            disposable=False,
            validated_at=int(time.time()),
        )
    local, domain = parts
    role = _is_role_based(local)
    disposable = _is_disposable(domain)
    mx_valid = await _has_mx(domain)
    return EmailValidation(
        valid_syntax=True,
        mx_valid=mx_valid,
        role_based=role,
        disposable=disposable,
        validated_at=int(time.time()),
    )
