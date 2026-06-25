"""Page-intent scoring for visitor-pixel traffic.

The pixel already records the ``url`` of every visit; this turns those URLs into a
buying-intent strength. High-intent pages (pricing, demo, contact, checkout)
signal active evaluation far more strongly than a blog or careers page.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Path substrings mapped to a per-visit intent weight. Checked longest-signal
# first via simple membership; the highest matching weight for a URL wins.
_PAGE_WEIGHTS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("/pricing", "/plans", "/quote", "/get-a-quote", "/buy", "/checkout", "/cart"), 30),
    (("/demo", "/request-demo", "/book-a-demo", "/trial", "/free-trial", "/get-started", "/signup", "/sign-up"), 25),
    (("/contact", "/contact-us", "/sales", "/talk-to-sales", "/request"), 20),
    (("/product", "/products", "/features", "/solutions", "/platform", "/integrations", "/use-cases"), 10),
    (("/case-stud", "/customers", "/testimonial", "/roi", "/compare", "/vs-", "/alternatives"), 12),
    (("/docs", "/documentation", "/api", "/developers"), 6),
)

# Anything below this is treated as a low-intent page (blog, careers, home, …).
_DEFAULT_WEIGHT = 2

# Cap so a single noisy visitor can't dominate the intent score.
MAX_VISIT_STRENGTH = 60


def score_page(url: str) -> int:
    """Return the intent weight for a single visited URL."""
    if not url:
        return 0
    try:
        path = (urlparse(url).path or "").lower()
    except ValueError:
        return _DEFAULT_WEIGHT
    best = _DEFAULT_WEIGHT
    for needles, weight in _PAGE_WEIGHTS:
        if any(n in path for n in needles) and weight > best:
            best = weight
    return best


def aggregate_intent(urls: list[str]) -> tuple[int, dict]:
    """Aggregate a visitor session's URLs into an intent strength + breakdown.

    Strength is the sum of per-page weights with diminishing returns (each
    additional visit to pages of the same tier counts a little less), capped at
    ``MAX_VISIT_STRENGTH``. Returns ``(strength, breakdown)``.
    """
    if not urls:
        return 0, {"visits": 0, "top_page": None, "top_weight": 0}

    scored = sorted(((score_page(u), u) for u in urls if u), reverse=True)
    if not scored:
        return 0, {"visits": 0, "top_page": None, "top_weight": 0}

    total = 0.0
    for idx, (weight, _url) in enumerate(scored):
        total += weight / (1 + idx * 0.5)  # diminishing returns

    strength = max(0, min(MAX_VISIT_STRENGTH, int(round(total))))
    top_weight, top_url = scored[0]
    breakdown = {
        "visits": len(scored),
        "top_page": top_url,
        "top_weight": top_weight,
        "high_intent": top_weight >= 20,
    }
    return strength, breakdown
