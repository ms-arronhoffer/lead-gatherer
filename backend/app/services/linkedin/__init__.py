"""LinkedIn headless-browser enrichment (optional, off by default).

This package logs into LinkedIn with a service account, searches for a company
and its people, keeps the top decision-maker candidates, and mines their recent
posts for buying signals. It is gated behind ``settings.enable_linkedin_enrichment``
because automated LinkedIn access violates LinkedIn's Terms of Service.

Modules:
  * ``selectors``       — centralized DOM selectors / URLs (LinkedIn changes often).
  * ``browser_session`` — Playwright session: login + cookie persistence + detection.
  * ``company_search``  — navigate search/company/profile pages, return raw data.
  * ``decision_makers`` — title filtering + LLM normalization/ranking (top N).
  * ``post_signals``    — classify recent posts into first-class buying signals.
  * ``enricher``        — orchestrator that wires scraping + persistence + signals.
"""
