from bs4 import BeautifulSoup

from app.services.scraper_service import _CONTACT_KEYWORDS, _discover_contact_links


def _links(html: str, website: str):
    soup = BeautifulSoup(html, "lxml")
    from urllib.parse import urlparse
    domain = urlparse(website).netloc
    return _discover_contact_links(soup, website, domain)


def test_discovers_contact_and_team_pages():
    html = """
    <a href="/contact">Contact</a>
    <a href="/our-team">Team</a>
    <a href="/leadership">Leadership</a>
    <a href="/products">Products</a>
    """
    urls = _links(html, "https://acme.com")
    assert "https://acme.com/contact" in urls
    assert "https://acme.com/our-team" in urls
    assert "https://acme.com/leadership" in urls
    assert "https://acme.com/products" not in urls


def test_ignores_offdomain_links():
    html = '<a href="https://other.com/team">Team</a><a href="/about">About</a>'
    urls = _links(html, "https://acme.com")
    assert urls == ["https://acme.com/about"]


def test_dedupes_repeated_links_and_skips_homepage():
    html = '<a href="/contact">C</a><a href="/contact">C2</a><a href="https://acme.com">Home</a>'
    urls = _links(html, "https://acme.com")
    assert urls.count("https://acme.com/contact") == 1


def test_keyword_set_expanded():
    # Regression guard: deeper exploration keywords are present.
    for kw in ("/leadership", "/management", "/our-team", "/founders"):
        assert kw in _CONTACT_KEYWORDS
