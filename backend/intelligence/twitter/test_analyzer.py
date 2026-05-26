"""Unit tests for twitter/analyzer.py — pure functions only, no LLM."""

import pytest

from backend.intelligence.twitter.analyzer import (
    _parse,
    build_analyzed_links,
    pre_filter_tweets,
)


# ─────────────────────────────────────────────────────────────────────────────
# pre_filter_tweets
# ─────────────────────────────────────────────────────────────────────────────

def _make_tweet(tid, likes=0, retweets=0, replies=0, views=0, ts="2024-01-01", is_retweet=False):
    return {
        "tweet_id": tid,
        "url": f"https://x.com/user/status/{tid}",
        "likes": likes,
        "retweets": retweets,
        "replies": replies,
        "views": views,
        "created_at": ts,
        "is_retweet": is_retweet,
    }

def test_pre_filter_returns_at_most_13():
    tweets = [_make_tweet(i, likes=i) for i in range(20)]
    assert len(pre_filter_tweets(tweets)) <= 13

def test_pre_filter_deduplicates():
    tweet = _make_tweet(1, likes=50)
    result = pre_filter_tweets([tweet, tweet, tweet])
    assert len(result) == 1

def test_pre_filter_empty():
    assert pre_filter_tweets([]) == []

def test_pre_filter_original_beats_retweet():
    # Original adds +10 to score; retweet adds 0
    rt   = _make_tweet("rt",   likes=5, is_retweet=True)
    orig = _make_tweet("orig", likes=0, is_retweet=False)
    result = pre_filter_tweets([rt, orig])
    scores = {t["tweet_id"]: t["_signal_score"] for t in result}
    assert scores["orig"] > scores["rt"]

def test_pre_filter_reply_weight_higher_than_like():
    # Both are retweets (is_original=0) so the +10 original bonus cancels out.
    # 1 reply (×3=3) > 2 likes (×1=2).
    by_likes   = _make_tweet("lk", likes=2, replies=0, is_retweet=True)
    by_replies = _make_tweet("rp", likes=0, replies=1, is_retweet=True)
    result = pre_filter_tweets([by_likes, by_replies])
    scores = {t["tweet_id"]: t["_signal_score"] for t in result}
    assert scores["rp"] > scores["lk"]

def test_pre_filter_includes_recent_even_if_low_score():
    # 10 high-engagement tweets with old timestamps + 3 low-engagement but newest timestamps.
    # The 3 newest should still appear via the "3 most recent" path even though they'd
    # lose to the high-engagement ones on score alone.
    high_signal = [_make_tweet(10 + i, likes=1000, ts=f"2023-01-{i+1:02d}") for i in range(10)]
    low_signal  = [_make_tweet(i,      likes=0,    ts=f"2024-06-{i+1:02d}") for i in range(3)]
    result = pre_filter_tweets(high_signal + low_signal)
    result_ids = {t["tweet_id"] for t in result}
    low_ids = {t["tweet_id"] for t in low_signal}
    assert low_ids.issubset(result_ids)


# ─────────────────────────────────────────────────────────────────────────────
# build_analyzed_links
# ─────────────────────────────────────────────────────────────────────────────

def test_build_analyzed_links_format():
    tweets = [
        {"url": "https://x.com/u/status/1", "likes": 30, "retweets": 5,
         "created_at": "2024-04-11T12:00:00Z"},
    ]
    result = build_analyzed_links(tweets)
    assert "https://x.com/u/status/1" in result
    assert "30 likes" in result
    assert "5 RT" in result
    assert "2024-04-11" in result

def test_build_analyzed_links_empty():
    assert build_analyzed_links([]) == ""

def test_build_analyzed_links_multiple():
    tweets = [
        {"url": f"https://x.com/u/status/{i}", "likes": i, "retweets": 0, "created_at": "2024-01-01"}
        for i in range(3)
    ]
    result = build_analyzed_links(tweets)
    assert result.count("https://") == 3


# ─────────────────────────────────────────────────────────────────────────────
# _parse
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_clean_json():
    assert _parse('{"tweet_wealth_signal": "IPO proceeds"}') == {"tweet_wealth_signal": "IPO proceeds"}

def test_parse_markdown_fenced():
    content = '```json\n{"k": "v"}\n```'
    assert _parse(content) == {"k": "v"}

def test_parse_invalid_json_returns_empty():
    assert _parse("sorry, I cannot assist with that") == {}

def test_parse_array_returns_empty():
    assert _parse("[1, 2, 3]") == {}
