"""Tests for page-intent scoring and fuzzy lead matching."""
from app.services.signals import lead_match
from app.services.signals.page_intent import aggregate_intent, score_page


def test_high_intent_pages_score_higher():
    assert score_page("https://acme.com/pricing") > score_page("https://acme.com/blog/post")
    assert score_page("https://acme.com/request-demo") >= 25
    assert score_page("https://acme.com/contact-us") >= 20


def test_unknown_page_gets_default():
    assert score_page("https://acme.com/") == 2
    assert score_page("") == 0


def test_aggregate_intent_diminishing_returns():
    strength, breakdown = aggregate_intent([
        "https://acme.com/pricing",
        "https://acme.com/demo",
        "https://acme.com/",
    ])
    assert strength > 0
    assert breakdown["visits"] == 3
    assert "/pricing" in breakdown["top_page"]
    assert breakdown["high_intent"] is True


def test_aggregate_intent_capped():
    urls = ["https://acme.com/pricing"] * 20
    strength, _ = aggregate_intent(urls)
    assert strength <= 60


def test_aggregate_empty():
    strength, breakdown = aggregate_intent([])
    assert strength == 0
    assert breakdown["visits"] == 0


# --- fuzzy matching --------------------------------------------------------

def test_normalize_company_strips_suffixes():
    assert lead_match.normalize_company("Acme, Inc.") == "acme"
    assert lead_match.normalize_company("Acme Technologies LLC") == "acme"


def test_name_similarity():
    assert lead_match.name_similarity("Acme Inc", "Acme, LLC") == 1.0
    assert lead_match.name_similarity("Acme", "Globex") < 0.5


def test_domain_of():
    assert lead_match.domain_of("https://www.acme.com/path") == "acme.com"
    assert lead_match.domain_of("acme.com") == "acme.com"
    assert lead_match.domain_of(None) is None


def test_phones_match():
    assert lead_match.phones_match("+1 (512) 555-1234", "512-555-1234")
    assert not lead_match.phones_match("512-555-1234", "512-555-9999")
    assert not lead_match.phones_match(None, "512-555-1234")
