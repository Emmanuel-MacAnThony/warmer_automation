"""
Tests for the scraper boundary layer.

Covers:
  1. LinkedIn normalization (preserve_apify_data) — harvestapi and dev_fusion schemas
  2. Tweet normalization (normalize_tweet)
  3. Protocol conformance — fake scrapers satisfy LinkedInScraper / TweetScraper
  4. BatchExecutor accepts injected scraper factories (no real Apify calls)
"""
import pytest

from backend.infra.scrapers import LinkedInScraper, TweetScraper
from backend.infra.scrapers.apify.linkedin import normalize_profile as preserve_apify_data
from backend.infra.scrapers.apify.twitter import normalize_tweet, normalize_tweets


# ---------------------------------------------------------------------------
# Fake implementations (satisfy the Protocols without hitting Apify)
# ---------------------------------------------------------------------------

class FakeLinkedInScraper:
    def __init__(self, token: str = "fake") -> None:
        self.token = token
        self.profile_calls: list[str] = []
        self.posts_calls: list[str] = []

    def scrape_raw_profile(self, url: str) -> dict:
        self.profile_calls.append(url)
        return {
            "fullName": "Alice Example",
            "headline": "Founder at Acme",
            "location": {"linkedinText": "San Francisco Bay Area", "parsed": {"city": "San Francisco"}},
            "emails": ["alice@acme.com"],
            "experience": [{"companyName": "Acme", "position": "Founder"}],
        }

    def scrape_raw_posts(self, url: str, limit: int = 20) -> list[dict]:
        self.posts_calls.append(url)
        return []


class FakeTweetScraper:
    def __init__(self, token: str = "fake") -> None:
        self.token = token
        self.calls: list[str] = []

    def scrape_raw_user_tweets(self, handle: str, max_tweets: int = 20) -> list[dict]:
        self.calls.append(handle)
        return [
            {
                "id": "1",
                "text": "Excited about our new fundraising round!",
                "likeCount": 42,
                "retweetCount": 5,
                "author": {"name": "Alice", "userName": "alice"},
            }
        ]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

def test_fake_linkedin_scraper_satisfies_protocol():
    assert isinstance(FakeLinkedInScraper(), LinkedInScraper)


def test_fake_tweet_scraper_satisfies_protocol():
    assert isinstance(FakeTweetScraper(), TweetScraper)


# ---------------------------------------------------------------------------
# LinkedIn normalization — harvestapi schema
# ---------------------------------------------------------------------------

def test_preserve_apify_data_harvestapi_name():
    raw = {"fullName": "John Doe"}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/johndoe")
    assert profile["full_name"] == "John Doe"


def test_preserve_apify_data_harvestapi_email_array():
    raw = {"emails": ["john@acme.com", "john@personal.com"]}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/johndoe")
    assert profile["email"] == "john@acme.com"  # first wins


def test_preserve_apify_data_harvestapi_location_nested():
    raw = {
        "location": {
            "linkedinText": "San Francisco Bay Area",
            "parsed": {"city": "San Francisco", "country": "US"},
        }
    }
    profile = preserve_apify_data(raw, "https://linkedin.com/in/johndoe")
    assert profile["location"] == "San Francisco Bay Area"
    assert profile["city"] == "San Francisco"


def test_preserve_apify_data_harvestapi_current_role():
    raw = {
        "experience": [
            {"companyName": "Acme Corp", "position": "CEO"},
            {"companyName": "Previous Co", "position": "VP"},
        ]
    }
    profile = preserve_apify_data(raw, "https://linkedin.com/in/johndoe")
    assert profile["current_company"] == "Acme Corp"
    assert profile["current_title"] == "CEO"


# ---------------------------------------------------------------------------
# LinkedIn normalization — dev_fusion schema
# ---------------------------------------------------------------------------

def test_preserve_apify_data_dev_fusion_name_parts():
    raw = {"firstName": "Jane", "lastName": "Smith"}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/janesmith")
    assert profile["full_name"] == "Jane Smith"


def test_preserve_apify_data_dev_fusion_email_string():
    raw = {"email": "jane@startup.com"}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/janesmith")
    assert profile["email"] == "jane@startup.com"


def test_preserve_apify_data_dev_fusion_location_string():
    raw = {"location": "New York, NY"}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/janesmith")
    assert profile["location"] == "New York, NY"


def test_preserve_apify_data_dev_fusion_experiences_key():
    raw = {"experiences": [{"company": "Startup", "title": "CTO"}]}
    profile = preserve_apify_data(raw, "https://linkedin.com/in/janesmith")
    assert profile["current_title"] == "CTO"
    assert profile["current_company"] == "Startup"


def test_preserve_apify_data_profile_url_preserved():
    url = "https://linkedin.com/in/testuser"
    profile = preserve_apify_data({}, url)
    assert profile["profile_url"] == url


def test_preserve_apify_data_empty_raw_returns_defaults():
    profile = preserve_apify_data({}, "https://linkedin.com/in/nobody")
    assert profile["full_name"] == ""
    assert profile["experience"] == []
    assert profile["posts"] == []


# ---------------------------------------------------------------------------
# Tweet normalization
# ---------------------------------------------------------------------------

def test_normalize_tweet_fields():
    raw = {
        "id": "123",
        "text": "Hello fundraising world",
        "likeCount": 10,
        "retweetCount": 2,
        "replyCount": 1,
        "author": {"name": "Test User", "userName": "testuser", "isVerified": True},
    }
    tweet = normalize_tweet(raw)
    assert tweet["tweet_id"] == "123"
    assert tweet["text"] == "Hello fundraising world"
    assert tweet["likes"] == 10
    assert tweet["retweets"] == 2
    assert tweet["author_handle"] == "testuser"
    assert tweet["author_verified"] is True


def test_normalize_tweet_engagement_defaults_to_zero():
    tweet = normalize_tweet({"id": "1", "text": "hi"})
    assert tweet["likes"] == 0
    assert tweet["retweets"] == 0
    assert tweet["views"] == 0


def test_normalize_tweets_batch():
    raws = [{"id": str(i), "text": f"tweet {i}"} for i in range(3)]
    tweets = normalize_tweets(raws)
    assert len(tweets) == 3
    assert tweets[0]["tweet_id"] == "0"


# ---------------------------------------------------------------------------
# BatchExecutor injection (no I/O — verifies the factory wiring compiles)
# ---------------------------------------------------------------------------

def test_batch_executor_accepts_fake_factories():
    from backend.pipeline.executor import BatchExecutor
    ex = BatchExecutor(
        linkedin_scraper_factory=lambda token: FakeLinkedInScraper(token),
        tweet_scraper_factory=lambda token: FakeTweetScraper(token),
    )
    # Verify factories produce scrapers that satisfy the Protocol
    li = ex._li_factory("tok")
    tw = ex._tw_factory("tok")
    assert isinstance(li, LinkedInScraper)
    assert isinstance(tw, TweetScraper)
    assert li.scrape_raw_profile("https://linkedin.com/in/test")["fullName"] == "Alice Example"
