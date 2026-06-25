"""SMTP RCPT TO email verification (F2).

Best-effort probe: opens an SMTP connection to a recipient's MX host, issues
HELO/MAIL FROM/RCPT TO, and interprets the response. Greylist/temporary
failures (4xx) leave verification as `unverifiable` (None) rather than False.
"""
from __future__ import annotations

import logging
import time

import dns.asyncresolver
import dns.exception
from aiosmtplib import SMTP, SMTPException

from app.config import settings

logger = logging.getLogger(__name__)

_MX_CACHE: dict[str, tuple[list[str], float]] = {}
_MX_TTL = 60 * 60 * 24  # 24h


async def _mx_hosts(domain: str) -> list[str]:
    now = time.time()
    cached = _MX_CACHE.get(domain)
    if cached and cached[1] > now:
        return cached[0]
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 5.0
    resolver.timeout = 5.0
    try:
        answers = await resolver.resolve(domain, "MX")
        hosts = sorted(
            ((a.preference, str(a.exchange).rstrip(".")) for a in answers),
            key=lambda t: t[0],
        )
        out = [h for _, h in hosts]
    except (dns.exception.DNSException, OSError) as exc:
        logger.debug("MX lookup failed %s: %s", domain, exc)
        out = []
    _MX_CACHE[domain] = (out, now + _MX_TTL)
    return out


async def smtp_verify(email: str) -> bool | None:
    """Return True if mailbox exists, False if rejected, None if inconclusive."""
    if "@" not in email:
        return False
    _, _, domain = email.rpartition("@")
    domain = domain.lower().strip()
    hosts = await _mx_hosts(domain)
    if not hosts:
        return False

    sender = settings.smtp_verify_sender or "verify@example.com"
    last_err: str | None = None
    for host in hosts[:2]:
        smtp = SMTP(hostname=host, port=25, timeout=15)
        try:
            await smtp.connect()
            await smtp.ehlo()
            code, _ = await smtp.mail(sender)
            if code >= 500:
                return False
            code, msg = await smtp.rcpt(email)
            if 200 <= code < 300:
                return True
            if 500 <= code < 600:
                return False
            last_err = f"{code} {msg}"
        except (SMTPException, OSError, TimeoutError) as exc:
            last_err = str(exc)
            logger.debug("SMTP probe %s via %s failed: %s", email, host, exc)
        finally:
            try:
                await smtp.quit()
            except Exception:
                pass
    logger.debug("SMTP probe inconclusive %s: %s", email, last_err)
    return None
