"""
Scraper Protocols — vendor-neutral interfaces for data acquisition.

Implementations live in infra/scrapers/<vendor>/. Swap vendors by
providing a different implementation that satisfies the Protocol.

Apify implementation: infra/scrapers/apify/
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class LinkedInScraper(Protocol):
    """Scrapes raw LinkedIn profile and post data."""
    def scrape_raw_profile(self, url: str) -> dict: ...
    def scrape_raw_posts(self, url: str, limit: int = 20) -> list[dict]: ...


@runtime_checkable
class TweetScraper(Protocol):
    """Scrapes raw tweet data for a user handle."""
    def scrape_raw_user_tweets(self, handle: str, max_tweets: int = 20) -> list[dict]: ...


__all__ = ["LinkedInScraper", "TweetScraper"]
