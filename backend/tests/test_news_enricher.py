import pytest

from app.services.enrichment import news_enricher
from app.services.enrichment.news_enricher import NewsArticle, NewsResult, build_news_query


def test_build_news_query_includes_company_and_terms():
    q = build_news_query("Acme Corp")
    assert '"Acme Corp"' in q
    assert "press release" in q
    assert "appoints" in q


def test_build_news_query_appends_location():
    q = build_news_query("Acme", "Austin")
    assert q.endswith("Austin")


def test_build_news_query_handles_blank_location():
    q = build_news_query("Acme", "")
    assert "Acme" in q
    assert not q.endswith(" ")


def test_news_result_combined_text():
    res = NewsResult(articles=[
        NewsArticle(url="https://a.com", html="", text="alpha"),
        NewsArticle(url="https://b.com", html="", text="beta"),
    ])
    assert res.combined_text == "alpha beta"


@pytest.mark.asyncio
async def test_find_news_returns_empty_when_provider_unconfigured(monkeypatch):
    monkeypatch.setattr(news_enricher, "search_configured", lambda: False)
    result = await news_enricher.find_news("Acme", "Austin")
    assert result.articles == []


@pytest.mark.asyncio
async def test_find_news_returns_empty_for_blank_company():
    result = await news_enricher.find_news("   ")
    assert result.articles == []


@pytest.mark.asyncio
async def test_find_news_dedupes_hosts_and_limits(monkeypatch):
    captured = {}

    class FakeProvider:
        async def search(self, query, count):
            captured["query"] = query
            return [
                "https://news.example.com/a",
                "https://news.example.com/b",  # same host -> dropped
                "https://other.example.org/c",
                "https://third.example.net/d",
            ]

    async def fake_fetch(client, url):
        return NewsArticle(url=url, html=f"<p>{url}</p>", text=url)

    monkeypatch.setattr(news_enricher, "get_search_provider", lambda: FakeProvider())
    monkeypatch.setattr(news_enricher, "search_configured", lambda: True)
    monkeypatch.setattr(news_enricher, "_fetch_article", fake_fetch)

    result = await news_enricher.find_news("Acme", "Austin", limit=2)
    urls = [a.url for a in result.articles]
    assert len(result.articles) == 2
    # Only one article per host, capped at the limit.
    assert "https://news.example.com/a" in urls
    assert "https://news.example.com/b" not in urls
    assert '"Acme"' in captured["query"]


@pytest.mark.asyncio
async def test_find_news_swallows_provider_errors(monkeypatch):
    class BoomProvider:
        async def search(self, query, count):
            raise RuntimeError("api key missing")

    monkeypatch.setattr(news_enricher, "get_search_provider", lambda: BoomProvider())
    monkeypatch.setattr(news_enricher, "search_configured", lambda: True)

    result = await news_enricher.find_news("Acme")
    assert result.articles == []
