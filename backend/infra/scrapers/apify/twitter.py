"""
Apify Twitter/X scraper — satisfies the TweetScraper Protocol.

All ApifyClient usage AND Apify-specific normalization for tweets live here.
Swap vendors by implementing a new class with the same method and injecting it.
"""
import logging
from typing import Any, Dict, List

from apify_client import ApifyClient

logger = logging.getLogger(__name__)

_TWEET_ACTOR = "apidojo/tweet-scraper"


# ---------------------------------------------------------------------------
# Normalization — translates raw Apify tweet output into a consistent shape.
# ---------------------------------------------------------------------------

def normalize_tweet(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw Apify tweet dict into a consistent shape."""
    author = raw_item.get("author") or {}
    return {
        "tweet_id":   raw_item.get("id") or raw_item.get("tweetId"),
        "text":       raw_item.get("text") or raw_item.get("full_text"),
        "created_at": raw_item.get("createdAt") or raw_item.get("created_at"),
        "url":        raw_item.get("url") or raw_item.get("tweetUrl"),

        "author_name":      author.get("name") or raw_item.get("authorName"),
        "author_handle":    author.get("userName") or raw_item.get("authorUsername") or raw_item.get("handle"),
        "author_followers": author.get("followers") or raw_item.get("authorFollowers"),
        "author_verified":  author.get("isVerified") or raw_item.get("isVerified"),

        "likes":     raw_item.get("likeCount") or raw_item.get("likes") or 0,
        "retweets":  raw_item.get("retweetCount") or raw_item.get("retweets") or 0,
        "replies":   raw_item.get("replyCount") or raw_item.get("replies") or 0,
        "views":     raw_item.get("viewCount") or raw_item.get("views") or 0,
        "bookmarks": raw_item.get("bookmarkCount") or 0,

        "is_retweet": raw_item.get("isRetweet") or False,
        "is_reply":   raw_item.get("isReply") or False,
        "hashtags":   raw_item.get("hashtags") or [],
        "urls":       raw_item.get("urls") or [],
        "media":      raw_item.get("media") or [],

        "raw_data": raw_item,
    }


def normalize_tweets(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [normalize_tweet(item) for item in raw_items]


# ---------------------------------------------------------------------------
# Apify implementation — satisfies TweetScraper Protocol
# ---------------------------------------------------------------------------

class ApifyTweetScraper:
    """Fetches raw tweet data via Apify actors."""

    def __init__(self, token: str) -> None:
        self._token = token

    def scrape_raw_user_tweets(self, handle: str, max_tweets: int = 20) -> List[Dict[str, Any]]:
        """Fetch recent tweets for a handle. Returns raw un-normalized Apify dicts."""
        handle = handle.lstrip("@")
        client = ApifyClient(self._token)
        run = client.actor(_TWEET_ACTOR).call(
            run_input={
                "twitterHandles": [handle],
                "maxTweets": max_tweets,
                "addUserInfo": True,
            }
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info(f"Fetched {len(items)} raw tweets for @{handle}")
        return items

    def scrape_raw_tweets_by_query(self, query: str, max_tweets: int = 20) -> List[Dict[str, Any]]:
        """Search tweets by keyword. Returns raw un-normalized Apify dicts."""
        client = ApifyClient(self._token)
        run = client.actor(_TWEET_ACTOR).call(
            run_input={
                "searchTerms": [query],
                "maxTweets": max_tweets,
                "addUserInfo": True,
            }
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        logger.info(f"Fetched {len(items)} raw tweets for query '{query}'")
        return items
