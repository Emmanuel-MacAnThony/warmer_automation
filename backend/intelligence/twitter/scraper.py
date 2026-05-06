"""
Twitter/X Post Scraper using Apify
Scrapes posts by username or search query
"""
import json
import logging
from typing import Any, Dict, List, Optional

from apify_client import ApifyClient

from backend.config import Config

logger = logging.getLogger(__name__)

ACTOR_ID = "apidojo/tweet-scraper"


def normalize_tweet(raw_item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise raw Apify tweet output into a consistent dict."""
    author = raw_item.get("author") or {}

    return {
        "tweet_id": raw_item.get("id") or raw_item.get("tweetId"),
        "text": raw_item.get("text") or raw_item.get("full_text"),
        "created_at": raw_item.get("createdAt") or raw_item.get("created_at"),
        "url": raw_item.get("url") or raw_item.get("tweetUrl"),

        # Author
        "author_name": author.get("name") or raw_item.get("authorName"),
        "author_handle": author.get("userName") or raw_item.get("authorUsername") or raw_item.get("handle"),
        "author_followers": author.get("followers") or raw_item.get("authorFollowers"),
        "author_verified": author.get("isVerified") or raw_item.get("isVerified"),

        # Engagement
        "likes": raw_item.get("likeCount") or raw_item.get("likes") or 0,
        "retweets": raw_item.get("retweetCount") or raw_item.get("retweets") or 0,
        "replies": raw_item.get("replyCount") or raw_item.get("replies") or 0,
        "views": raw_item.get("viewCount") or raw_item.get("views") or 0,
        "bookmarks": raw_item.get("bookmarkCount") or 0,

        # Content signals
        "is_retweet": raw_item.get("isRetweet") or False,
        "is_reply": raw_item.get("isReply") or False,
        "hashtags": raw_item.get("hashtags") or [],
        "urls": raw_item.get("urls") or [],
        "media": raw_item.get("media") or [],

        "raw_data": raw_item,
    }


def scrape_user_tweets(handle: str, max_tweets: int = 20) -> List[Dict[str, Any]]:
    """
    Scrape recent tweets from a Twitter/X user.

    Args:
        handle: Twitter handle without @ (e.g. "elonmusk")
        max_tweets: Max number of tweets to return

    Returns:
        List of normalized tweet dicts

    Raises:
        ValueError: If APIFY_API_TOKEN not configured
        Exception: If scraping fails
    """
    if not Config.APIFY_API_TOKEN:
        raise ValueError("APIFY_API_TOKEN not configured in .env file")

    client = ApifyClient(Config.APIFY_API_TOKEN)

    handle = handle.lstrip("@")

    run_input = {
        "twitterHandles": [handle],
        "maxTweets": max_tweets,
        "addUserInfo": True,
    }

    try:
        logger.info(f"Scraping tweets for @{handle} (max {max_tweets})")

        run = client.actor(ACTOR_ID).call(run_input=run_input)

        tweets = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            tweets.append(normalize_tweet(item))

        logger.info(f"Scraped {len(tweets)} tweets for @{handle}")
        return tweets

    except Exception as e:
        logger.error(f"Error scraping tweets for @{handle}: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to scrape tweets: {str(e)}")


def scrape_tweets_by_query(query: str, max_tweets: int = 20) -> List[Dict[str, Any]]:
    """
    Search tweets by keyword or hashtag.

    Args:
        query: Search term (e.g. "fundraising AI", "#venturecapital")
        max_tweets: Max number of tweets to return
    """
    if not Config.APIFY_API_TOKEN:
        raise ValueError("APIFY_API_TOKEN not configured in .env file")

    client = ApifyClient(Config.APIFY_API_TOKEN)

    run_input = {
        "searchTerms": [query],
        "maxTweets": max_tweets,
        "addUserInfo": True,
    }

    try:
        logger.info(f"Searching tweets for: '{query}' (max {max_tweets})")

        run = client.actor(ACTOR_ID).call(run_input=run_input)

        tweets = []
        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            tweets.append(normalize_tweet(item))

        logger.info(f"Found {len(tweets)} tweets for query '{query}'")
        return tweets

    except Exception as e:
        logger.error(f"Error searching tweets: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to search tweets: {str(e)}")


def print_tweets_summary(tweets: List[Dict[str, Any]], label: str = ""):
    """Print a readable summary of scraped tweets."""
    def safe_print(text: str):
        print(text.encode("ascii", errors="replace").decode("ascii"))

    safe_print("\n" + "=" * 80)
    safe_print(f"TWEETS SCRAPED{f' - {label}' if label else ''}")
    safe_print("=" * 80)
    safe_print(f"Total: {len(tweets)} tweets\n")

    for i, tweet in enumerate(tweets, 1):
        safe_print(f"[{i}] @{tweet.get('author_handle', 'unknown')} - {tweet.get('created_at', 'N/A')}")
        text = tweet.get("text", "")
        safe_print(f"    {text[:120]}{'...' if len(text) > 120 else ''}")
        safe_print(f"    Likes: {tweet.get('likes', 0)}  RT: {tweet.get('retweets', 0)}  Replies: {tweet.get('replies', 0)}  Views: {tweet.get('views', 0)}")
        safe_print("")

    safe_print("=" * 80)


if __name__ == "__main__":
    import asyncio
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Twitter/X Scraper - Test Mode\n")

    if not Config.APIFY_API_TOKEN:
        print("ERROR: APIFY_API_TOKEN not set in .env file")
        exit(1)

    # Accept full URL or handle
    raw_arg = sys.argv[1] if len(sys.argv) > 1 else "paulg"
    test_handle = raw_arg.rstrip("/").split("/")[-1].lstrip("@")

    print(f"Scraping tweets for: @{test_handle}")
    print("This may take 30-60 seconds...\n")

    async def run():
        from backend.intelligence.twitter.analyzer import extract_tweet_signals

        # Step 1 — scrape
        tweets = scrape_user_tweets(test_handle, max_tweets=50)

        if not tweets:
            print("ERROR: No tweets returned")
            exit(1)

        print_tweets_summary(tweets[:10], label=f"@{test_handle} (top 10 shown)")

        # Step 2 — analyze signals
        print("\nRunning signal analysis...\n")
        signals = await extract_tweet_signals(tweets)

        print("=" * 80)
        print("FUNDRAISING SIGNALS")
        print("=" * 80)
        for key, val in signals.items():
            if key == "tweet_analyzed_links":
                print(f"\n{key}:\n{val}")
            else:
                print(f"{key}: {val}")

        # Save full output
        output = {"handle": test_handle, "tweet_count": len(tweets), "signals": signals, "tweets": tweets}
        output_file = "twitter_analysis.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nFull data saved to: {output_file}")

    try:
        asyncio.run(run())
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
