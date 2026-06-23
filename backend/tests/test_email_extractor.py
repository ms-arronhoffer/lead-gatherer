import pytest
from app.utils.email_extractor import extract_emails


def test_mailto_extracted():
    html = '<a href="mailto:hello@example.biz">Email us</a>'
    results = extract_emails(html)
    assert any(e == "hello@example.biz" for e, _ in results)


def test_mailto_has_max_confidence():
    html = '<a href="mailto:hello@mybusiness.com">Email us</a>'
    results = dict(extract_emails(html))
    assert results.get("hello@mybusiness.com") == 1.0


def test_noise_filtered():
    html = '<a href="mailto:noreply@example.com">x</a><a href="mailto:info@realco.com">x</a>'
    emails = [e for e, _ in extract_emails(html)]
    assert "noreply@example.com" not in emails
    assert "info@realco.com" in emails


def test_plain_text_regex_fallback():
    html = "<p>Contact us at sales@myshop.net for inquiries.</p>"
    emails = [e for e, _ in extract_emails(html)]
    assert "sales@myshop.net" in emails


def test_json_ld_email():
    html = '''<script type="application/ld+json">
    {"@type": "LocalBusiness", "email": "info@jsonld.co"}
    </script>'''
    results = dict(extract_emails(html))
    assert results.get("info@jsonld.co", 0) >= 0.9


def test_dedup_same_email_different_sources():
    html = '''
    <a href="mailto:contact@biz.io">Email</a>
    <p>Reach us at contact@biz.io too.</p>
    '''
    results = dict(extract_emails(html))
    # Same email from two sources — only one entry, best confidence wins
    count = sum(1 for e in results if e == "contact@biz.io")
    assert count == 1
    assert results["contact@biz.io"] == 1.0


def test_example_domain_noise_filtered():
    html = "<p>Send to test@example.com please</p>"
    emails = [e for e, _ in extract_emails(html)]
    assert "test@example.com" not in emails
