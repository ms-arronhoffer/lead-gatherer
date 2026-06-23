import json
import re

from bs4 import BeautifulSoup

_MAILTO_PATTERN = re.compile(
    r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE,
)
_EMAIL_PATTERN = re.compile(
    r'\b([a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]{1,253}\.[a-zA-Z]{2,6})\b',
    re.IGNORECASE,
)

_NOISE_DOMAINS = frozenset({
    "example.com", "domain.com", "yourdomain.com", "email.com",
    "sentry.io", "wixpress.com", "squarespace.com", "wordpress.com",
    "test.com", "sample.com", "user.com",
})
_NOISE_PREFIXES = frozenset({
    "noreply", "no-reply", "bounce", "mailer-daemon", "postmaster",
    "donotreply", "do-not-reply", "unsubscribe", "notifications",
})


def _is_noise(email: str) -> bool:
    if len(email) < 6:
        return True
    local, _, domain = email.rpartition("@")
    if domain.lower() in _NOISE_DOMAINS:
        return True
    if any(local.lower().startswith(p) for p in _NOISE_PREFIXES):
        return True
    return False


def extract_emails(html: str) -> list[tuple[str, float]]:
    results: dict[str, float] = {}  # email -> best confidence seen

    soup = BeautifulSoup(html, "lxml")

    # Priority 1: mailto: href (confidence 1.0)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        for m in _MAILTO_PATTERN.finditer(href):
            email = m.group(1)
            if not _is_noise(email):
                results[email.lower()] = max(results.get(email.lower(), 0), 1.0)

    # Priority 2: JSON-LD ContactPoint (confidence 0.95)
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        _extract_json_ld_emails(data, results)

    # Priority 3: microdata itemprop="email" (confidence 0.9)
    for tag in soup.find_all(itemprop="email"):
        email = tag.get("content") or tag.get_text(strip=True)
        if email and "@" in email and not _is_noise(email):
            results[email.lower()] = max(results.get(email.lower(), 0), 0.9)

    # Priority 4: plain text regex (confidence 0.7)
    text = soup.get_text(" ")
    for m in _EMAIL_PATTERN.finditer(text):
        email = m.group(1)
        if not _is_noise(email):
            results[email.lower()] = max(results.get(email.lower(), 0), 0.7)

    # Return as (original_case_email, confidence) — use lowercase as canonical
    return [(email, conf) for email, conf in results.items()]


def _extract_json_ld_emails(data, results: dict) -> None:
    if isinstance(data, list):
        for item in data:
            _extract_json_ld_emails(item, results)
        return
    if not isinstance(data, dict):
        return
    email = data.get("email")
    if email and isinstance(email, str) and "@" in email and not _is_noise(email):
        results[email.lower()] = max(results.get(email.lower(), 0), 0.95)
    for value in data.values():
        if isinstance(value, (dict, list)):
            _extract_json_ld_emails(value, results)
